from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, get_current
from app.core.config import settings
from app.core.ratelimit import limiter
from app.core.security import hash_password, validate_password_strength, verify_password
from app.db.base import utcnow
from app.db.session import get_db
from app.models import User
from app.schemas.auth import ChangePasswordIn, LoginIn, RefreshIn
from app.services.auth import issue_tokens, revoke_all, revoke_refresh, rotate_refresh, user_profile
from app.services.common import audit

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Constant-time-ish dummy verification to avoid user enumeration through timing
_DUMMY_HASH = hash_password("dummy-password-For-timing-1")


def _strip(tokens: dict) -> dict:
    tokens.pop("_rt", None)
    return tokens


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, body: LoginIn, db: Session = Depends(get_db)):
    ip = client_ip(request)
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    now = utcnow()
    if not user:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(401, "Invalid email or password")
    if user.locked_until and user.locked_until > now:
        mins = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(423, f"Account temporarily locked. Try again in {mins} minute(s).")
    if not verify_password(body.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
            user.failed_logins = 0
            audit(db, user, "auth.locked", "user", user.id, "Account locked after failed logins", ip=ip)
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Your account has been deactivated. Contact HR.")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    tokens = issue_tokens(db, user, ua=request.headers.get("user-agent"), ip=ip)
    audit(db, user, "auth.login", "user", user.id, f"{user.email} signed in", ip=ip)
    db.commit()
    return {**_strip(tokens), "user": user_profile(user)}


@router.post("/refresh")
@limiter.limit("30/minute")
def refresh(request: Request, body: RefreshIn, db: Session = Depends(get_db)):
    tokens = rotate_refresh(db, body.refresh_token, request.headers.get("user-agent"), client_ip(request))
    db.commit()
    return _strip(tokens)


@router.post("/logout")
def logout(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    revoke_refresh(db, body.refresh_token)
    db.commit()
    return {"ok": True}


@router.post("/logout-all")
def logout_all(request: Request, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    revoke_all(db, current.user)
    audit(db, current.user, "auth.logout_all", "user", current.id, "Signed out of all sessions", ip=client_ip(request))
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(current: CurrentUser = Depends(get_current)):
    return user_profile(current.user)


@router.post("/change-password")
@limiter.limit("5/minute")
def change_password(request: Request, body: ChangePasswordIn, current: CurrentUser = Depends(get_current),
                    db: Session = Depends(get_db)):
    user = current.user
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if err := validate_password_strength(body.new_password):
        raise HTTPException(422, err)
    if verify_password(body.new_password, user.password_hash):
        raise HTTPException(422, "New password must differ from the current password")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    revoke_all(db, user)  # invalidate other sessions
    tokens = issue_tokens(db, user, ua=request.headers.get("user-agent"), ip=client_ip(request))
    audit(db, user, "auth.password_changed", "user", user.id, "Password changed", ip=client_ip(request))
    db.commit()
    return {**_strip(tokens), "user": user_profile(user)}
