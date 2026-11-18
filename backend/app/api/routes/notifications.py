from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current
from app.db.session import get_db
from app.models import Notification
from app.services.common import paginate

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _n(n: Notification) -> dict:
    return {"id": n.id, "title": n.title, "body": n.body, "link": n.link, "category": n.category,
            "is_read": n.is_read, "created_at": n.created_at}


@router.get("")
def list_notifications(unread: bool = False, page: int = 1, page_size: int = 20,
                       current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == current.id).order_by(Notification.created_at.desc())
    if unread:
        stmt = stmt.where(Notification.is_read.is_(False))
    out = paginate(db, stmt, page, page_size, _n)
    out["unread_count"] = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == current.id, Notification.is_read.is_(False)))
    return out


@router.post("/{nid}/read")
def mark_read(nid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.id == nid, Notification.user_id == current.id)
               .values(is_read=True))
    db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == current.id, Notification.is_read.is_(False))
               .values(is_read=True))
    db.commit()
    return {"ok": True}
