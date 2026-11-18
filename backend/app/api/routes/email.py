from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current, require
from app.core.config import settings
from app.db.base import utcnow
from app.db.session import get_db
from app.models import Client, EmailAccount, EmailFollowUp, EmailMessage, Project
from app.services import email_sync as svc
from app.services.common import audit, get_or_404, paginate

router = APIRouter(prefix="/email", tags=["Email"])


class ConnectIn(BaseModel):
    provider: str = Field(pattern="^(gmail|outlook)$")
    shared: bool = False


class LinkIn(BaseModel):
    client_id: int | None = None
    project_id: int | None = None


class FollowUpIn(BaseModel):
    due_at: datetime
    note: str | None = Field(None, max_length=500)


class SendIn(BaseModel):
    account_id: int
    to: list[EmailStr] = Field(min_length=1, max_length=20)
    cc: list[EmailStr] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=100000)
    reply_to_message_id: int | None = None
    client_id: int | None = None
    project_id: int | None = None


def _acc(a: EmailAccount) -> dict:
    return {"id": a.id, "provider": a.provider, "email_address": a.email_address, "is_shared": a.is_shared,
            "owner": a.owner.email, "last_synced_at": a.last_synced_at, "sync_status": a.sync_status,
            "sync_error": a.sync_error}


def _msg(m: EmailMessage, full=False) -> dict:
    d = {"id": m.id, "account_id": m.account_id, "account": m.account.email_address, "thread_id": m.thread_id,
         "direction": m.direction, "subject": m.subject, "from_address": m.from_address, "to_addresses": m.to_addresses,
         "snippet": m.snippet, "sent_at": m.sent_at, "is_read": m.is_read,
         "client": {"id": m.client.id, "name": m.client.name} if m.client else None,
         "project": {"id": m.project.id, "name": m.project.name} if m.project else None}
    if full:
        d.update({"cc_addresses": m.cc_addresses, "body_text": m.body_text})
    return d


def _visible_acc(db: Session, current: CurrentUser, acc_id: int) -> EmailAccount:
    a = get_or_404(db, EmailAccount, acc_id, "Mailbox")
    if a.owner_user_id != current.id and not (a.is_shared and current.has("email.view_shared")):
        raise HTTPException(403, "You do not have access to this mailbox")
    return a


def _visible_msg(db: Session, current: CurrentUser, mid: int) -> EmailMessage:
    m = get_or_404(db, EmailMessage, mid, "Email")
    _visible_acc(db, current, m.account_id)
    return m


@router.get("/status")
def integration_status(current: CurrentUser = Depends(require("email.use"))):
    return {"gmail": svc.provider_configured("gmail"), "outlook": svc.provider_configured("outlook"),
            "redirect_uris": {"gmail": svc.redirect_uri("gmail"), "outlook": svc.redirect_uri("outlook")}}


@router.get("/accounts")
def accounts(current: CurrentUser = Depends(require("email.use")), db: Session = Depends(get_db)):
    stmt = select(EmailAccount).where(or_(EmailAccount.owner_user_id == current.id,
                                          EmailAccount.is_shared.is_(True) & current.has("email.view_shared")))
    return [_acc(a) for a in db.scalars(stmt).unique()]


@router.post("/connect")
def connect(body: ConnectIn, current: CurrentUser = Depends(require("email.use"))):
    if body.shared and not current.has("email.view_shared"):
        raise HTTPException(403, "Only administrators can connect shared company mailboxes")
    return {"auth_url": svc.build_auth_url(body.provider, current.id, body.shared)}


@router.get("/oauth/{provider}/callback", include_in_schema=False)
def oauth_callback(provider: str, code: str | None = None, state: str | None = None, error: str | None = None,
                   db: Session = Depends(get_db)):
    target = f"{settings.FRONTEND_URL}/email"
    if error or not code or not state:
        return RedirectResponse(f"{target}?connected=0&error={error or 'cancelled'}")
    st = svc.decode_state(state)
    if st.get("p") != provider:
        return RedirectResponse(f"{target}?connected=0&error=state_mismatch")
    try:
        acc = svc.exchange_code(db, provider, code, int(st["uid"]), bool(st.get("shared")))
        from app.models import User
        audit(db, db.get(User, int(st["uid"])), "email.connect", "email_account", acc.id, f"Connected {acc.email_address}")
        db.commit()
    except HTTPException as e:
        db.rollback()
        return RedirectResponse(f"{target}?connected=0&error={e.detail[:120]}")
    return RedirectResponse(f"{target}?connected=1")


@router.post("/accounts/{aid}/sync")
def sync_now(aid: int, current: CurrentUser = Depends(require("email.use")), db: Session = Depends(get_db)):
    acc = _visible_acc(db, current, aid)
    n = svc.sync_account(db, acc)
    return {"new_messages": n, "account": _acc(acc)}


@router.delete("/accounts/{aid}")
def disconnect(aid: int, purge: bool = False, current: CurrentUser = Depends(require("email.use")),
               db: Session = Depends(get_db)):
    acc = get_or_404(db, EmailAccount, aid, "Mailbox")
    if acc.owner_user_id != current.id and not current.has("admin.settings"):
        raise HTTPException(403, "Only the owner can disconnect this mailbox")
    audit(db, current.user, "email.disconnect", "email_account", acc.id, f"Disconnected {acc.email_address}",
          {"purged": purge})
    if purge:
        db.delete(acc)
    else:
        acc.access_token_enc = acc.refresh_token_enc = None
        acc.sync_status = "disconnected"
    db.commit()
    return {"ok": True}


@router.get("/messages")
def messages(q: str | None = None, account_id: int | None = None, client_id: int | None = None,
             project_id: int | None = None, direction: str | None = None, unlinked: bool = False,
             date_from: datetime | None = None, date_to: datetime | None = None, page: int = 1, page_size: int = 30,
             current: CurrentUser = Depends(require("email.use")), db: Session = Depends(get_db)):
    stmt = select(EmailMessage).where(svc.visible_accounts_filter(db, current)).order_by(EmailMessage.sent_at.desc())
    if account_id:
        stmt = stmt.where(EmailMessage.account_id == account_id)
    if client_id:
        stmt = stmt.where(EmailMessage.client_id == client_id)
    if project_id:
        stmt = stmt.where(EmailMessage.project_id == project_id)
    if direction:
        stmt = stmt.where(EmailMessage.direction == direction)
    if unlinked:
        stmt = stmt.where(EmailMessage.client_id.is_(None))
    if date_from:
        stmt = stmt.where(EmailMessage.sent_at >= date_from)
    if date_to:
        stmt = stmt.where(EmailMessage.sent_at <= date_to)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(EmailMessage.subject.ilike(like), EmailMessage.from_address.ilike(like),
                              EmailMessage.to_addresses.ilike(like), EmailMessage.snippet.ilike(like)))
    return paginate(db, stmt, page, page_size, _msg)


@router.get("/messages/{mid}")
def message(mid: int, current: CurrentUser = Depends(require("email.use")), db: Session = Depends(get_db)):
    m = _visible_msg(db, current, mid)
    m.is_read = True
    db.commit()
    thread = []
    if m.thread_id:
        thread = [_msg(x) for x in db.scalars(select(EmailMessage).where(
            EmailMessage.thread_id == m.thread_id, EmailMessage.account_id == m.account_id, EmailMessage.id != m.id)
            .order_by(EmailMessage.sent_at))]
    fu = db.scalars(select(EmailFollowUp).where(EmailFollowUp.message_id == mid, EmailFollowUp.user_id == current.id)).all()
    return {**_msg(m, True), "thread": thread,
            "followups": [{"id": f.id, "due_at": f.due_at, "note": f.note, "is_done": f.is_done} for f in fu]}


@router.post("/messages/{mid}/link")
def link(mid: int, body: LinkIn, current: CurrentUser = Depends(require("email.use")), db: Session = Depends(get_db)):
    m = _visible_msg(db, current, mid)
    if body.client_id and not db.get(Client, body.client_id):
        raise HTTPException(422, "Client not found")
    if body.project_id:
        p = db.get(Project, body.project_id)
        if not p:
            raise HTTPException(422, "Project not found")
        if body.client_id and p.client_id != body.client_id:
            raise HTTPException(422, "Project does not belong to the selected client")
        body.client_id = body.client_id or p.client_id
    m.client_id, m.project_id = body.client_id, body.project_id
    if m.client_id:
        svc._log_client_comm(db, m)
    db.commit()
    return _msg(m)


@router.get("/followups")
def followups(include_done: bool = False, current: CurrentUser = Depends(require("email.use")), db: Session = Depends(get_db)):
    stmt = select(EmailFollowUp).where(EmailFollowUp.user_id == current.id).order_by(EmailFollowUp.due_at)
    if not include_done:
        stmt = stmt.where(EmailFollowUp.is_done.is_(False))
    return [{"id": f.id, "due_at": f.due_at, "note": f.note, "is_done": f.is_done, "is_overdue": f.due_at < utcnow(),
             "message": _msg(f.message)} for f in db.scalars(stmt).unique()]


@router.post("/messages/{mid}/followups", status_code=201)
def add_followup(mid: int, body: FollowUpIn, current: CurrentUser = Depends(require("email.use")), db: Session = Depends(get_db)):
    _visible_msg(db, current, mid)
    due = body.due_at.astimezone(timezone.utc).replace(tzinfo=None) if body.due_at.tzinfo else body.due_at
    f = EmailFollowUp(message_id=mid, user_id=current.id, due_at=due, note=body.note)
    db.add(f)
    db.commit()
    return {"id": f.id}


@router.post("/followups/{fid}/done")
def followup_done(fid: int, current: CurrentUser = Depends(require("email.use")), db: Session = Depends(get_db)):
    f = get_or_404(db, EmailFollowUp, fid, "Follow-up")
    if f.user_id != current.id:
        raise HTTPException(403, "Not allowed")
    f.is_done = True
    db.commit()
    return {"ok": True}


@router.post("/send")
def send(body: SendIn, current: CurrentUser = Depends(require("email.use")), db: Session = Depends(get_db)):
    acc = get_or_404(db, EmailAccount, body.account_id, "Mailbox")
    if acc.owner_user_id != current.id:
        raise HTTPException(403, "You can only send from mailboxes you connected")
    thread = None
    if body.reply_to_message_id:
        orig = _visible_msg(db, current, body.reply_to_message_id)
        thread = orig.thread_id if acc.provider == "gmail" else None
    svc.send_email(db, acc, [str(x) for x in body.to], body.subject, body.body, [str(x) for x in body.cc], thread)
    audit(db, current.user, "email.send", "email_account", acc.id, f"Sent email: {body.subject[:120]}",
          {"to": [str(x) for x in body.to]})
    db.commit()
    try:
        svc.sync_account(db, acc)  # pull the sent message into history
    except HTTPException:
        pass
    return {"ok": True}
