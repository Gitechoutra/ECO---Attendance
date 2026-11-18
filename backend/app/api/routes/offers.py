from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, get_current, require, require_any
from app.core.config import settings
from app.core.ratelimit import limiter
from app.core.security import new_opaque_token, sha256
from app.db.base import utcnow
from app.db.session import get_db
from app.models import (
    Candidate, Department, EmailAccount, Employee, OfferLetter, OfferLetterVersion, OfferTemplate, StoredFile,
)
from app.schemas.people import OfferDecisionIn, OfferIn, OfferResponseIn, TemplateIn
from app.services.common import audit, get_company, get_or_404, notify, paginate, user_ids_with_permission
from app.services.pdf import money, offer_letter_pdf, render_template
from app.services.storage import get_storage, store_bytes

router = APIRouter(tags=["Offer Letters"])
viewer = require_any("offers.manage", "offers.approve")
EDITABLE = ("draft", "rejected")


def _company_dict(db: Session) -> dict:
    c = get_company(db)
    return {"company_name": c.company_name, "legal_name": c.legal_name, "email": c.email, "phone": c.phone,
            "website": c.website, "address": c.address}


def _ref(db: Session) -> str:
    year = date.today().year
    n = db.scalar(select(func.count()).select_from(OfferLetter).where(OfferLetter.reference_no.like(f"EIS/OL/{year}/%"))) or 0
    while True:
        n += 1
        ref = f"EIS/OL/{year}/{n:04d}"
        if not db.scalar(select(OfferLetter.id).where(OfferLetter.reference_no == ref)):
            return ref


def _offer(o: OfferLetter, db: Session, detail=False) -> dict:
    d = {"id": o.id, "reference_no": o.reference_no, "recipient_name": o.recipient_name,
         "recipient_email": o.recipient_email, "designation": o.designation,
         "department": o.department.name if o.department else None, "department_id": o.department_id,
         "joining_date": o.joining_date, "annual_ctc": float(o.annual_ctc), "status": o.status,
         "current_version": o.current_version, "candidate_id": o.candidate_id, "employee_id": o.employee_id,
         "created_at": o.created_at, "sent_at": o.sent_at, "responded_at": o.responded_at}
    if detail:
        d.update({"salary_breakup": o.salary_breakup or [], "work_location": o.work_location,
                  "valid_until": o.valid_until, "additional_terms": o.additional_terms, "template_id": o.template_id,
                  "approved_by": o.approved_by.email if o.approved_by else None, "approved_at": o.approved_at,
                  "approval_note": o.approval_note, "response_signature": o.response_signature,
                  "response_note": o.response_note, "response_ip": o.response_ip,
                  "versions": [{"version": v.version, "file_id": v.file_id, "change_note": v.change_note,
                                "created_at": v.created_at, "created_by": v.created_by.email if v.created_by else None}
                               for v in db.scalars(select(OfferLetterVersion).where(OfferLetterVersion.offer_id == o.id)
                                                   .order_by(OfferLetterVersion.version.desc()))]})
    return d


def _render_body(db: Session, o: OfferLetter) -> str:
    tpl = db.get(OfferTemplate, o.template_id) if o.template_id else None
    tpl = tpl or db.scalar(select(OfferTemplate).where(OfferTemplate.is_default.is_(True))) or db.scalar(select(OfferTemplate))
    if not tpl:
        raise HTTPException(422, "No offer letter template is configured")
    cs = get_company(db)
    return render_template(tpl.body, {
        "candidate_name": o.recipient_name, "first_name": o.recipient_name.split()[0], "designation": o.designation,
        "department": o.department.name if o.department else "", "company_name": cs.company_name,
        "joining_date": f"{o.joining_date:%d %B %Y}", "annual_ctc": money(o.annual_ctc, cs.currency),
        "work_location": o.work_location or "our office", "valid_until": f"{o.valid_until:%d %B %Y}" if o.valid_until else "the date of joining",
        "additional_terms": o.additional_terms or "", "reference_no": o.reference_no,
    }).replace("\n\n\n", "\n\n")


def _new_version(db: Session, o: OfferLetter, user, note: str, acceptance: str | None = None) -> OfferLetterVersion:
    body = _render_body(db, o)
    payload = {"reference_no": o.reference_no, "recipient_name": o.recipient_name, "recipient_email": o.recipient_email,
               "issue_date": date.today(), "annual_ctc": float(o.annual_ctc), "salary_breakup": o.salary_breakup or [],
               "acceptance": acceptance}
    pdf = offer_letter_pdf(_company_dict(db), payload, body)
    o.current_version += 1
    f = store_bytes(db, pdf, f"Offer-{o.reference_no.replace('/', '-')}-v{o.current_version}.pdf", "application/pdf",
                    user, "offer_letter", o.id, "offer_letter")
    v = OfferLetterVersion(offer_id=o.id, version=o.current_version, file_id=f.id, change_note=note,
                           created_by_id=user.id if user else None,
                           snapshot=jsonable_encoder({**_offer(o, db), "body": body}))
    db.add(v)
    db.flush()
    return v


def _attach_to_employee(db: Session, o: OfferLetter, v: OfferLetterVersion, user) -> None:
    """Approved letters for existing employees are filed in their document records."""
    if not o.employee_id:
        return
    src = db.get(StoredFile, v.file_id)
    store_bytes(db, get_storage().load(src.storage_key), src.original_name, "application/pdf", user, "employee",
                o.employee_id, "offer_letter", f"Offer/appointment letter v{v.version}")


def _apply(db: Session, o: OfferLetter, body: OfferIn) -> None:
    data = body.model_dump()
    if body.candidate_id:
        c = get_or_404(db, Candidate, body.candidate_id, "Candidate")
        data["recipient_name"] = data.get("recipient_name") or c.full_name
        data["recipient_email"] = data.get("recipient_email") or c.email
    if body.employee_id:
        e = get_or_404(db, Employee, body.employee_id, "Employee")
        data["recipient_name"] = data.get("recipient_name") or e.full_name
        data["recipient_email"] = data.get("recipient_email") or e.email
    if body.department_id and not db.get(Department, body.department_id):
        raise HTTPException(422, "Department not found")
    if body.template_id and not db.get(OfferTemplate, body.template_id):
        raise HTTPException(422, "Template not found")
    data["salary_breakup"] = [x for x in data["salary_breakup"]]
    for k, v in data.items():
        setattr(o, k, v)


# ------------------------------------------------------------------ templates

@router.get("/offers/templates")
def templates(current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "body": t.body, "is_default": t.is_default, "is_active": t.is_active}
            for t in db.scalars(select(OfferTemplate).order_by(OfferTemplate.name))]


@router.post("/offers/templates", status_code=201)
def create_template(body: TemplateIn, current: CurrentUser = Depends(require("offers.manage")), db: Session = Depends(get_db)):
    if db.scalar(select(OfferTemplate.id).where(OfferTemplate.name == body.name)):
        raise HTTPException(409, "Template name already exists")
    if body.is_default:
        for t in db.scalars(select(OfferTemplate)):
            t.is_default = False
    t = OfferTemplate(**body.model_dump())
    db.add(t)
    db.commit()
    return {"id": t.id}


@router.put("/offers/templates/{tid}")
def update_template(tid: int, body: TemplateIn, current: CurrentUser = Depends(require("offers.manage")),
                    db: Session = Depends(get_db)):
    t = get_or_404(db, OfferTemplate, tid, "Template")
    if body.is_default:
        for x in db.scalars(select(OfferTemplate)):
            x.is_default = False
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    audit(db, current.user, "offer_template.update", "offer_template", t.id, f"Updated template {t.name}")
    db.commit()
    return {"id": t.id}


# ------------------------------------------------------------------ offers

@router.get("/offers")
def list_offers(status: str | None = None, q: str | None = None, page: int = 1, page_size: int = 20,
                current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    stmt = select(OfferLetter).order_by(OfferLetter.created_at.desc())
    if status:
        stmt = stmt.where(OfferLetter.status == status)
    if q:
        stmt = stmt.where(OfferLetter.recipient_name.ilike(f"%{q}%") | OfferLetter.reference_no.ilike(f"%{q}%"))
    return paginate(db, stmt, page, page_size, lambda o: _offer(o, db))


@router.get("/offers/mine")
def my_offers(current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    if not current.employee_id:
        return []
    stmt = select(OfferLetter).where(OfferLetter.employee_id == current.employee_id,
                                     OfferLetter.status.in_(["approved", "sent", "accepted", "declined"]))
    return [_offer(o, db, True) for o in db.scalars(stmt)]


@router.post("/offers", status_code=201)
def create_offer(body: OfferIn, current: CurrentUser = Depends(require("offers.manage")), db: Session = Depends(get_db)):
    o = OfferLetter(reference_no=_ref(db), created_by_id=current.id, recipient_name="", recipient_email="",
                    designation=body.designation, joining_date=body.joining_date, annual_ctc=body.annual_ctc)
    _apply(db, o, body)
    db.add(o)
    db.flush()
    audit(db, current.user, "offer.create", "offer_letter", o.id, f"Drafted offer {o.reference_no} for {o.recipient_name}")
    db.commit()
    db.refresh(o)
    return _offer(o, db, True)


@router.get("/offers/{oid}")
def get_offer(oid: int, current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    o = get_or_404(db, OfferLetter, oid, "Offer letter")
    d = _offer(o, db, True)
    d["preview"] = _render_body(db, o)
    if o.status == "sent" and o.accept_token_hash:
        d["response_link_available"] = True
    return d


@router.put("/offers/{oid}")
def update_offer(oid: int, body: OfferIn, current: CurrentUser = Depends(require("offers.manage")), db: Session = Depends(get_db)):
    o = get_or_404(db, OfferLetter, oid, "Offer letter")
    if o.status not in EDITABLE:
        raise HTTPException(409, f"An offer that is {o.status.replace('_', ' ')} cannot be edited")
    _apply(db, o, body)
    if o.status == "rejected":
        o.status = "draft"
    audit(db, current.user, "offer.update", "offer_letter", o.id, f"Edited {o.reference_no}")
    db.commit()
    db.refresh(o)
    return _offer(o, db, True)


@router.post("/offers/{oid}/submit")
def submit_offer(oid: int, current: CurrentUser = Depends(require("offers.manage")), db: Session = Depends(get_db)):
    o = get_or_404(db, OfferLetter, oid, "Offer letter")
    if o.status not in EDITABLE:
        raise HTTPException(409, "Only drafts can be submitted for approval")
    _new_version(db, o, current.user, "Submitted for approval")
    o.status = "pending_approval"
    notify(db, set(user_ids_with_permission(db, "offers.approve")) - {current.id}, "Offer letter awaiting approval",
           f"{o.reference_no} · {o.recipient_name} · {o.designation}", f"/offers/{o.id}", "approval")
    audit(db, current.user, "offer.submit", "offer_letter", o.id, f"Submitted {o.reference_no}")
    db.commit()
    return _offer(o, db, True)


@router.post("/offers/{oid}/decision")
def decide_offer(oid: int, body: OfferDecisionIn, request: Request, current: CurrentUser = Depends(require("offers.approve")),
                 db: Session = Depends(get_db)):
    o = get_or_404(db, OfferLetter, oid, "Offer letter")
    if o.status != "pending_approval":
        raise HTTPException(409, "This offer is not awaiting approval")
    if o.created_by_id == current.id and current.role != "super_admin":
        raise HTTPException(403, "You cannot approve an offer you drafted")
    o.status = "approved" if body.approve else "rejected"
    o.approved_by_id, o.approved_at, o.approval_note = current.id, utcnow(), body.note
    if body.approve:
        v = db.scalar(select(OfferLetterVersion).where(OfferLetterVersion.offer_id == o.id,
                                                       OfferLetterVersion.version == o.current_version))
        _attach_to_employee(db, o, v, current.user)
    from app.models import User
    notify(db, [o.created_by_id] if db.get(User, o.created_by_id or 0) else [], f"Offer {o.status}",
           f"{o.reference_no} for {o.recipient_name}" + (f" — {body.note}" if body.note else ""), f"/offers/{o.id}", "approval")
    audit(db, current.user, f"offer.{o.status}", "offer_letter", o.id, f"{o.status.title()} {o.reference_no}", ip=client_ip(request))
    db.commit()
    return _offer(o, db, True)


@router.post("/offers/{oid}/send")
def send_offer(oid: int, account_id: int | None = None, current: CurrentUser = Depends(require("offers.manage")),
               db: Session = Depends(get_db)):
    """Issue a single-use response link. Optionally emails it through the sender's connected mailbox."""
    o = get_or_404(db, OfferLetter, oid, "Offer letter")
    if o.status not in ("approved", "sent"):
        raise HTTPException(409, "Only approved offers can be sent")
    token = new_opaque_token()
    o.accept_token_hash = sha256(token)
    o.status, o.sent_at = "sent", utcnow()
    link = f"{settings.FRONTEND_URL}/offer/respond/{token}"
    emailed = False
    if account_id:
        from app.services.email_sync import send_email
        acc = get_or_404(db, EmailAccount, account_id, "Mailbox")
        if acc.owner_user_id != current.id:
            raise HTTPException(403, "You can only send from your own connected mailbox")
        cs = get_company(db)
        send_email(db, acc, [o.recipient_email], f"Offer of employment — {cs.company_name}",
                   f"Dear {o.recipient_name},\n\nPlease find your offer from {cs.company_name} for the role of "
                   f"{o.designation}. You can review, download and respond to the offer here:\n\n{link}\n\n"
                   f"Warm regards,\nHuman Resources\n{cs.company_name}")
        emailed = True
    if o.candidate_id:
        c = db.get(Candidate, o.candidate_id)
        if c and c.status not in ("hired",):
            c.status = "offered"
    audit(db, current.user, "offer.send", "offer_letter", o.id, f"Sent {o.reference_no}", {"emailed": emailed})
    db.commit()
    return {"response_link": link, "emailed": emailed, "offer": _offer(o, db, True)}


@router.post("/offers/{oid}/withdraw")
def withdraw_offer(oid: int, current: CurrentUser = Depends(require("offers.manage")), db: Session = Depends(get_db)):
    o = get_or_404(db, OfferLetter, oid, "Offer letter")
    if o.status in ("accepted", "declined", "withdrawn"):
        raise HTTPException(409, f"Offer is already {o.status}")
    o.status, o.accept_token_hash = "withdrawn", None
    audit(db, current.user, "offer.withdraw", "offer_letter", o.id, f"Withdrew {o.reference_no}")
    db.commit()
    return _offer(o, db, True)


# ------------------------------------------------------------------ public response (no login)

def _by_token(db: Session, token: str) -> OfferLetter:
    o = db.scalar(select(OfferLetter).where(OfferLetter.accept_token_hash == sha256(token)))
    if not o:
        raise HTTPException(404, "This offer link is invalid or has been withdrawn")
    return o


@router.get("/public/offers/{token}")
@limiter.limit("30/minute")
def public_offer(request: Request, token: str, db: Session = Depends(get_db)):
    o = _by_token(db, token)
    cs = get_company(db)
    expired = bool(o.valid_until and o.valid_until < date.today() and o.status == "sent")
    return {"reference_no": o.reference_no, "recipient_name": o.recipient_name, "designation": o.designation,
            "department": o.department.name if o.department else None, "joining_date": o.joining_date,
            "annual_ctc": float(o.annual_ctc), "salary_breakup": o.salary_breakup or [], "valid_until": o.valid_until,
            "status": o.status, "expired": expired, "company_name": cs.company_name, "body": _render_body(db, o),
            "responded_at": o.responded_at}


@router.get("/public/offers/{token}/pdf")
@limiter.limit("30/minute")
def public_offer_pdf(request: Request, token: str, db: Session = Depends(get_db)):
    o = _by_token(db, token)
    v = db.scalar(select(OfferLetterVersion).where(OfferLetterVersion.offer_id == o.id)
                  .order_by(OfferLetterVersion.version.desc()))
    f = db.get(StoredFile, v.file_id)
    return Response(get_storage().load(f.storage_key), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{f.original_name}"'})


@router.post("/public/offers/{token}/respond")
@limiter.limit("10/minute")
def respond_offer(request: Request, token: str, body: OfferResponseIn, db: Session = Depends(get_db)):
    o = _by_token(db, token)
    if o.status != "sent":
        raise HTTPException(409, f"This offer has already been {o.status}")
    if o.valid_until and o.valid_until < date.today():
        raise HTTPException(409, "This offer has expired. Please contact HR.")
    if body.signature.strip().lower() != o.recipient_name.strip().lower():
        raise HTTPException(422, "Please type your full name exactly as it appears on the offer to sign")
    ip = client_ip(request)
    o.status = "accepted" if body.accept else "declined"
    o.responded_at, o.response_ip, o.response_signature, o.response_note = utcnow(), ip, body.signature.strip(), body.note
    if body.accept:
        stamp = (f"Digitally accepted by {o.response_signature} on {o.responded_at:%d %b %Y %H:%M} UTC "
                 f"from IP {ip}. Reference {o.reference_no}.")
        v = _new_version(db, o, None, "Accepted by recipient", acceptance=stamp)
        _attach_to_employee(db, o, v, None)
    else:
        if o.candidate_id:
            c = db.get(Candidate, o.candidate_id)
            if c and c.status == "offered":
                c.status = "withdrawn"
    notify(db, set(user_ids_with_permission(db, "offers.manage")), f"Offer {o.status}",
           f"{o.recipient_name} {o.status} offer {o.reference_no}", f"/offers/{o.id}", "recruitment")
    audit(db, None, f"offer.{o.status}", "offer_letter", o.id, f"Recipient {o.status} {o.reference_no}", ip=ip)
    db.commit()
    return {"status": o.status}
