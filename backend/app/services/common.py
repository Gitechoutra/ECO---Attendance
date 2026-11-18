"""Cross-cutting helpers: audit logging, notifications, pagination, company settings, time."""
from datetime import date, datetime, timezone
from math import ceil
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, CompanySettings, Notification, User


def audit(db: Session, user: User | None, action: str, entity_type: str | None = None,
          entity_id: int | None = None, summary: str | None = None, details: dict | None = None,
          ip: str | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type,
                    entity_id=entity_id, summary=(summary or "")[:500], details=details, ip_address=ip))


def notify(db: Session, user_ids, title: str, body: str | None = None, link: str | None = None,
           category: str = "general") -> None:
    for uid in {u for u in user_ids if u}:
        db.add(Notification(user_id=uid, title=title[:200], body=(body or "")[:1000] or None, link=link,
                            category=category))


def user_ids_for_employees(db: Session, employee_ids) -> list[int]:
    ids = [e for e in employee_ids if e]
    if not ids:
        return []
    return list(db.scalars(select(User.id).where(User.employee_id.in_(ids), User.is_active.is_(True))))


def user_ids_with_permission(db: Session, code: str) -> list[int]:
    from app.services.authz import effective_permissions  # local import avoids cycle

    users = db.scalars(select(User).where(User.is_active.is_(True))).all()
    return [u.id for u in users if code in effective_permissions(u)]


def paginate(db: Session, stmt, page: int = 1, page_size: int = 20, transform=None) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).unique().all()
    items = [transform(r) for r in rows] if transform else rows
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": ceil(total / page_size) if total else 0}


def get_company(db: Session) -> CompanySettings:
    cs = db.get(CompanySettings, 1)
    if not cs:
        cs = CompanySettings(id=1)
        db.add(cs)
        db.flush()
    return cs


def company_tz(db: Session) -> ZoneInfo:
    return ZoneInfo(get_company(db).timezone or "Asia/Kolkata")


def utc_to_local(dt: datetime | None, tz: ZoneInfo) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(tz)


def local_to_utc(dt: datetime, tz: ZoneInfo) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def today_local(db: Session) -> date:
    return datetime.now(company_tz(db)).date()


def get_or_404(db: Session, model, obj_id: int, label: str | None = None):
    obj = db.get(model, obj_id)
    if not obj:
        raise HTTPException(404, f"{label or model.__name__} not found")
    return obj


def apply_updates(obj, data: dict) -> dict:
    """Set attributes and return {field: [old, new]} for those that changed."""
    changes = {}
    for k, v in data.items():
        old = getattr(obj, k)
        if old != v:
            changes[k] = [str(old) if old is not None else None, str(v) if v is not None else None]
            setattr(obj, k, v)
    return changes
