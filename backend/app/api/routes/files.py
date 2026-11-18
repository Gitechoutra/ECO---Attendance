"""Authorized file download. Every file is checked against the entity it belongs to."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current
from app.db.session import get_db
from app.models import (
    Candidate, ClientContract, EmailMessage, Expense, OfferLetter, OfferLetterVersion, Project, StoredFile,
)
from app.services.authz import accessible_client_ids, accessible_project_ids
from app.services.common import get_or_404
from app.services.storage import get_storage

router = APIRouter(prefix="/files", tags=["Files"])


def can_access(db: Session, current: CurrentUser, f: StoredFile) -> bool:
    et, eid, p = f.entity_type, f.entity_id, current.perms
    if f.uploaded_by_id == current.id:
        return True
    if et == "employee_photo":
        return True  # profile photos are visible to colleagues
    if et == "employee":
        return "employees.view_all" in p or eid == current.employee_id
    if et == "project":
        ids = accessible_project_ids(db, current.user, p)
        return ids is None or eid in ids
    if et == "client":
        ids = accessible_client_ids(db, current.user, p)
        return ids is None or eid in ids
    if et == "client_contract":
        c = db.get(ClientContract, eid)
        ids = accessible_client_ids(db, current.user, p)
        return bool(c) and (ids is None or c.client_id in ids)
    if et == "candidate":
        return "recruitment.view" in p
    if et == "offer_letter":
        ver = db.scalar(select(OfferLetterVersion).where(OfferLetterVersion.file_id == f.id))
        offer = db.get(OfferLetter, ver.offer_id) if ver else db.get(OfferLetter, eid)
        if "offers.manage" in p or "offers.approve" in p:
            return True
        return bool(offer and offer.employee_id and offer.employee_id == current.employee_id
                    and offer.status in ("sent", "accepted", "declined"))
    if et == "expense":
        e = db.get(Expense, eid)
        return bool(e) and (e.employee_id == current.employee_id or "expenses.view_all" in p
                            or "expenses.approve" in p)
    if et == "payslip":
        from app.models import Payslip
        ps = db.get(Payslip, eid)
        return bool(ps) and (ps.employee_id == current.employee_id or "payroll.view" in p)
    if et == "email":
        msg = db.get(EmailMessage, eid)
        return bool(msg) and (msg.account.owner_user_id == current.id or
                              (msg.account.is_shared and "email.view_shared" in p))
    return "admin.settings" in p


@router.get("/{file_id}")
def download(file_id: int, inline: bool = True, current: CurrentUser = Depends(get_current),
             db: Session = Depends(get_db)):
    f = get_or_404(db, StoredFile, file_id, "File")
    if not can_access(db, current, f):
        raise HTTPException(403, "You do not have access to this file")
    data = get_storage().load(f.storage_key)
    disp = "inline" if inline and (f.content_type.startswith("image/") or f.content_type == "application/pdf") else "attachment"
    return Response(content=data, media_type=f.content_type, headers={
        "Content-Disposition": f"{disp}; filename*=UTF-8''{quote(f.original_name)}",
        "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/{file_id}/meta")
def meta(file_id: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    f = get_or_404(db, StoredFile, file_id, "File")
    if not can_access(db, current, f):
        raise HTTPException(403, "You do not have access to this file")
    return {"id": f.id, "name": f.original_name, "content_type": f.content_type, "size": f.size_bytes,
            "created_at": f.created_at}


_ = Project, Candidate  # imported for clarity of entity types
