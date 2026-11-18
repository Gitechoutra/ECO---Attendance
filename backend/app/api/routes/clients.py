from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, get_current, require_any
from app.db.base import utcnow
from app.db.session import get_db
from app.models import (
    Client, ClientCommunication, ClientContact, ClientContract, ClientFeedback, ClientMeeting, ClientRequirement,
    EmailMessage, Employee, Project, StoredFile,
)
from app.schemas.work import (
    ClientIn, ClientMeetingIn, CommunicationIn, ContactIn, ContractIn, FeedbackIn, RequirementIn,
)
from app.services.authz import accessible_client_ids
from app.services.common import audit, get_or_404, paginate
from app.services.employees import employee_brief
from app.services.storage import delete_file, store_upload
from app.services.work import serialize_project

router = APIRouter(prefix="/clients", tags=["Clients"])
viewer = require_any("clients.view", "clients.manage")


def _client_or_403(db: Session, current: CurrentUser, cid: int) -> Client:
    c = get_or_404(db, Client, cid, "Client")
    ids = accessible_client_ids(db, current.user, current.perms)
    if ids is not None and c.id not in ids:
        raise HTTPException(403, "You do not have access to this client")
    return c


def _manage(current: CurrentUser, c: Client | None = None) -> None:
    if current.has("clients.manage"):
        return
    if c and current.employee_id and c.account_manager_id == current.employee_id:
        return
    raise HTTPException(403, "You do not have permission to modify client records")


def _contact(c: ClientContact) -> dict:
    return {"id": c.id, "name": c.name, "designation": c.designation, "email": c.email, "phone": c.phone,
            "is_primary": c.is_primary}


def _client(db: Session, c: Client, detail=False) -> dict:
    projects = db.scalar(select(func.count()).select_from(Project).where(Project.client_id == c.id)) or 0
    active = db.scalar(select(func.count()).select_from(Project).where(Project.client_id == c.id,
                                                                       Project.status == "active")) or 0
    primary = next((x for x in c.contacts if x.is_primary), c.contacts[0] if c.contacts else None)
    data = {"id": c.id, "name": c.name, "company_name": c.company_name, "industry": c.industry, "email": c.email,
            "phone": c.phone, "status": c.status, "city": c.city, "country": c.country,
            "account_manager": employee_brief(c.account_manager), "account_manager_id": c.account_manager_id,
            "project_count": projects, "active_projects": active,
            "primary_contact": _contact(primary) if primary else None, "created_at": c.created_at}
    if detail:
        data.update({"website": c.website, "address": c.address, "tax_id": c.tax_id, "notes": c.notes,
                     "contacts": [_contact(x) for x in c.contacts]})
        avg = db.scalar(select(func.avg(ClientFeedback.rating)).where(ClientFeedback.client_id == c.id))
        data["avg_rating"] = round(float(avg), 1) if avg else None
    return data


@router.get("")
def list_clients(q: str | None = None, status: str | None = None, page: int = 1, page_size: int = 20,
                 current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    stmt = select(Client).order_by(Client.name)
    ids = accessible_client_ids(db, current.user, current.perms)
    if ids is not None:
        stmt = stmt.where(Client.id.in_(ids or [0]))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Client.name.ilike(like), Client.company_name.ilike(like), Client.email.ilike(like)))
    if status:
        stmt = stmt.where(Client.status == status)
    return paginate(db, stmt, page, page_size, lambda c: _client(db, c))


@router.get("/options")
def client_options(current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    """Minimal list for pickers (e.g. project creation)."""
    stmt = select(Client.id, Client.name).where(Client.status != "inactive").order_by(Client.name)
    ids = accessible_client_ids(db, current.user, current.perms) if not current.has("projects.manage") else None
    if ids is not None:
        stmt = stmt.where(Client.id.in_(ids or [0]))
    return [{"id": i, "name": n} for i, n in db.execute(stmt).all()]


@router.post("", status_code=201)
def create_client(body: ClientIn, request: Request, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    _manage(current)
    if db.scalar(select(Client.id).where(func.lower(Client.name) == body.name.lower())):
        raise HTTPException(409, "A client with this name already exists")
    if body.account_manager_id and not db.get(Employee, body.account_manager_id):
        raise HTTPException(422, "Account manager not found")
    c = Client(**body.model_dump())
    db.add(c)
    db.flush()
    audit(db, current.user, "client.create", "client", c.id, f"Created client {c.name}", ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return _client(db, c, True)


@router.get("/{cid}")
def get_client(cid: int, current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    c = _client_or_403(db, current, cid)
    data = _client(db, c, True)
    data["can_manage"] = current.has("clients.manage") or (current.employee_id and c.account_manager_id == current.employee_id)
    return data


@router.put("/{cid}")
def update_client(cid: int, body: ClientIn, request: Request, current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    c = _client_or_403(db, current, cid)
    _manage(current, c)
    if db.scalar(select(Client.id).where(func.lower(Client.name) == body.name.lower(), Client.id != cid)):
        raise HTTPException(409, "A client with this name already exists")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, current.user, "client.update", "client", c.id, f"Updated client {c.name}", ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return _client(db, c, True)


@router.delete("/{cid}")
def delete_client(cid: int, request: Request, current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    c = _client_or_403(db, current, cid)
    current.require("clients.manage")
    if db.scalar(select(func.count()).select_from(Project).where(Project.client_id == cid)):
        raise HTTPException(409, "Client has projects. Mark the client inactive instead.")
    audit(db, current.user, "client.delete", "client", c.id, f"Deleted client {c.name}", ip=client_ip(request))
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/{cid}/projects")
def client_projects(cid: int, current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    _client_or_403(db, current, cid)
    return [serialize_project(db, p) for p in db.scalars(select(Project).where(Project.client_id == cid)
                                                          .order_by(Project.start_date.desc())).unique()]


# ------------------------------------------------------------------ generic sub-resources

SUB = {
    "contacts": (ClientContact, ContactIn, _contact),
    "requirements": (ClientRequirement, RequirementIn, lambda r: {
        "id": r.id, "title": r.title, "description": r.description, "priority": r.priority, "status": r.status,
        "project_id": r.project_id, "created_at": r.created_at}),
    "meetings": (ClientMeeting, ClientMeetingIn, lambda m: {
        "id": m.id, "title": m.title, "scheduled_at": m.scheduled_at, "duration_minutes": m.duration_minutes,
        "location": m.location, "agenda": m.agenda, "minutes": m.minutes, "status": m.status, "project_id": m.project_id}),
    "communications": (ClientCommunication, CommunicationIn, lambda c: {
        "id": c.id, "channel": c.channel, "subject": c.subject, "summary": c.summary, "occurred_at": c.occurred_at,
        "email_message_id": c.email_message_id, "user": c.user.email if c.user else None}),
    "feedback": (ClientFeedback, FeedbackIn, lambda f: {
        "id": f.id, "rating": f.rating, "comments": f.comments, "received_at": f.received_at, "project_id": f.project_id}),
    "contracts": (ClientContract, ContractIn, lambda k: {
        "id": k.id, "title": k.title, "value": float(k.value) if k.value is not None else None, "currency": k.currency,
        "start_date": k.start_date, "end_date": k.end_date, "status": k.status, "file_id": k.file_id,
        "project_id": k.project_id}),
}

ORDER = {"meetings": ClientMeeting.scheduled_at.desc(), "communications": ClientCommunication.occurred_at.desc(),
         "feedback": ClientFeedback.received_at.desc()}


async def _parse(request: Request, schema) -> dict:
    try:
        return schema.model_validate(await request.json()).model_dump()
    except ValidationError as e:
        raise RequestValidationError(e.errors())
    except ValueError:
        raise HTTPException(400, "Invalid JSON body")


def _sub(kind: str):
    if kind not in SUB:
        raise HTTPException(404, "Unknown resource")
    return SUB[kind]


@router.get("/{cid}/{kind}")
def list_sub(cid: int, kind: str, current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    _client_or_403(db, current, cid)
    model, _, ser = _sub(kind)
    order = ORDER.get(kind, model.id.desc())
    return [ser(x) for x in db.scalars(select(model).where(model.client_id == cid).order_by(order))]


def _validate_project(db: Session, cid: int, data: dict):
    if data.get("project_id"):
        p = db.get(Project, data["project_id"])
        if not p or p.client_id != cid:
            raise HTTPException(422, "Project does not belong to this client")


@router.post("/{cid}/{kind}", status_code=201)
async def create_sub(cid: int, kind: str, request: Request, current: CurrentUser = Depends(viewer),
                     db: Session = Depends(get_db)):
    c = _client_or_403(db, current, cid)
    model, schema, ser = _sub(kind)
    if kind not in ("communications", "meetings"):
        _manage(current, c)
    data = await _parse(request, schema)
    _validate_project(db, cid, data)
    if kind == "communications":
        data["occurred_at"] = data.get("occurred_at") or utcnow()
        data["user_id"] = current.id
    if kind in ("requirements", "meetings"):
        data["created_by_id"] = current.id
    if kind == "feedback":
        data["recorded_by_id"] = current.id
    if kind == "contacts" and data.get("is_primary"):
        for x in c.contacts:
            x.is_primary = False
    obj = model(client_id=cid, **data)
    db.add(obj)
    db.flush()
    if kind == "meetings":
        db.add(ClientCommunication(client_id=cid, channel="meeting", subject=f"Meeting scheduled: {obj.title}",
                                   summary=obj.agenda, occurred_at=obj.scheduled_at, user_id=current.id))
    audit(db, current.user, f"client.{kind}_create", "client", cid, f"{kind[:-1] if kind.endswith('s') else kind} added")
    db.commit()
    return ser(obj)


@router.put("/{cid}/{kind}/{oid}")
async def update_sub(cid: int, kind: str, oid: int, request: Request, current: CurrentUser = Depends(viewer),
                     db: Session = Depends(get_db)):
    c = _client_or_403(db, current, cid)
    model, schema, ser = _sub(kind)
    obj = get_or_404(db, model, oid)
    if obj.client_id != cid:
        raise HTTPException(404, "Record not found")
    if kind not in ("meetings",) or (getattr(obj, "created_by_id", None) != current.id):
        _manage(current, c)
    data = await _parse(request, schema)
    _validate_project(db, cid, data)
    if kind == "communications":
        data["occurred_at"] = data.get("occurred_at") or obj.occurred_at
    if kind == "contacts" and data.get("is_primary"):
        for x in c.contacts:
            x.is_primary = False
    for k, v in data.items():
        setattr(obj, k, v)
    audit(db, current.user, f"client.{kind}_update", "client", cid, f"Updated {kind} #{oid}")
    db.commit()
    return ser(obj)


@router.delete("/{cid}/{kind}/{oid}")
def delete_sub(cid: int, kind: str, oid: int, current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    c = _client_or_403(db, current, cid)
    _manage(current, c)
    model, _, _ = _sub(kind)
    obj = get_or_404(db, model, oid)
    if obj.client_id != cid:
        raise HTTPException(404, "Record not found")
    if kind == "contracts" and obj.file_id:
        f = db.get(StoredFile, obj.file_id)
        obj.file_id = None
        db.flush()
        if f:
            delete_file(db, f)
    db.delete(obj)
    audit(db, current.user, f"client.{kind}_delete", "client", cid, f"Deleted {kind} #{oid}")
    db.commit()
    return {"ok": True}


@router.post("/{cid}/contracts/{oid}/file")
async def upload_contract_file(cid: int, oid: int, file: UploadFile = File(...), current: CurrentUser = Depends(viewer),
                               db: Session = Depends(get_db)):
    c = _client_or_403(db, current, cid)
    _manage(current, c)
    k = get_or_404(db, ClientContract, oid, "Contract")
    if k.client_id != cid:
        raise HTTPException(404, "Contract not found")
    f = await store_upload(db, file, current.user, "client_contract", k.id, "contract")
    old = db.get(StoredFile, k.file_id) if k.file_id else None
    k.file_id = f.id
    if old:
        db.flush()
        delete_file(db, old)
    audit(db, current.user, "client.contract_file", "client", cid, f"Uploaded contract document {f.original_name}")
    db.commit()
    return {"file_id": f.id}


@router.get("/{cid}/documents/list")
def client_documents(cid: int, current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    _client_or_403(db, current, cid)
    rows = db.scalars(select(StoredFile).where(StoredFile.entity_type == "client", StoredFile.entity_id == cid)
                      .order_by(StoredFile.created_at.desc()))
    return [{"id": f.id, "name": f.original_name, "size": f.size_bytes, "category": f.category,
             "description": f.description, "created_at": f.created_at} for f in rows]


@router.post("/{cid}/documents/upload", status_code=201)
async def upload_client_document(cid: int, file: UploadFile = File(...), category: str = Form("document"),
                                 description: str | None = Form(None), current: CurrentUser = Depends(viewer),
                                 db: Session = Depends(get_db)):
    c = _client_or_403(db, current, cid)
    _manage(current, c)
    f = await store_upload(db, file, current.user, "client", cid, category[:60], description)
    audit(db, current.user, "client.document_upload", "client", cid, f"Uploaded {f.original_name}")
    db.commit()
    return {"id": f.id, "name": f.original_name}


@router.get("/{cid}/emails/list")
def client_emails(cid: int, current: CurrentUser = Depends(viewer), db: Session = Depends(get_db)):
    """Emails linked to this client from mailboxes the user is authorized to read."""
    from app.services.email_sync import visible_accounts_filter

    _client_or_403(db, current, cid)
    stmt = (select(EmailMessage).where(EmailMessage.client_id == cid, visible_accounts_filter(db, current))
            .order_by(EmailMessage.sent_at.desc()).limit(100))
    return [{"id": m.id, "subject": m.subject, "from_address": m.from_address, "snippet": m.snippet,
             "sent_at": m.sent_at, "direction": m.direction} for m in db.scalars(stmt).unique()]
