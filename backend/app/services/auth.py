import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, new_opaque_token, sha256
from app.db.base import utcnow
from app.models import RefreshToken, User
from app.services.authz import effective_permissions
from app.services.common import audit


def issue_tokens(db: Session, user: User, family_id: str | None = None, ua: str | None = None,
                 ip: str | None = None) -> dict:
    raw = new_opaque_token()
    rt = RefreshToken(user_id=user.id, token_hash=sha256(raw), family_id=family_id or secrets.token_hex(16),
                      expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_DAYS),
                      user_agent=(ua or "")[:255], ip_address=ip)
    db.add(rt)
    db.flush()
    return {
        "access_token": create_access_token(user.id, user.role.code, user.token_version),
        "refresh_token": raw,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_MINUTES * 60,
        "_rt": rt,
    }


def rotate_refresh(db: Session, raw: str, ua: str | None, ip: str | None) -> dict:
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(raw)))
    if not rt:
        raise HTTPException(401, "Invalid refresh token")
    now = utcnow()
    if rt.revoked_at is not None:
        # Reuse of a rotated token => likely theft. Revoke the whole family.
        db.execute(update(RefreshToken).where(RefreshToken.family_id == rt.family_id,
                                              RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
        user = db.get(User, rt.user_id)
        audit(db, user, "auth.refresh_reuse_detected", "user", rt.user_id, "Refresh token reuse — sessions revoked",
              ip=ip)
        db.commit()
        raise HTTPException(401, "Session revoked for security reasons. Please sign in again.")
    if rt.expires_at < now:
        raise HTTPException(401, "Session expired")
    user = db.get(User, rt.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Account disabled")
    tokens = issue_tokens(db, user, family_id=rt.family_id, ua=ua, ip=ip)
    rt.revoked_at = now
    rt.replaced_by_id = tokens["_rt"].id
    return tokens


def revoke_refresh(db: Session, raw: str) -> None:
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(raw)))
    if rt and rt.revoked_at is None:
        rt.revoked_at = utcnow()


def revoke_all(db: Session, user: User) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=utcnow()))
    user.token_version += 1


def user_profile(user: User) -> dict:
    emp = user.employee
    return {
        "id": user.id,
        "email": user.email,
        "role": {"code": user.role.code, "name": user.role.name},
        "permissions": sorted(effective_permissions(user)),
        "must_change_password": user.must_change_password,
        "last_login_at": user.last_login_at,
        "employee": None if not emp else {
            "id": emp.id,
            "employee_code": emp.employee_code,
            "full_name": emp.full_name,
            "first_name": emp.first_name,
            "designation": emp.designation.title if emp.designation else None,
            "department": emp.department.name if emp.department else None,
            "photo_file_id": emp.photo_file_id,
        },
    }
