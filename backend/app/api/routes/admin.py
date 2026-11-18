import os
import shutil
import subprocess
from datetime import date, datetime, time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, get_current, require
from app.core.config import BASE_DIR, settings
from app.core.permissions import PERMISSIONS, SUPER_ADMIN
from app.db.session import get_db
from app.models import AuditLog, Employee, Permission, Role, User, UserPermissionOverride
from app.services.auth import revoke_all
from app.services.authz import effective_permissions
from app.services.common import audit, get_company, get_or_404, paginate

router = APIRouter(prefix="/admin", tags=["Administration"])
BACKUP_DIR = BASE_DIR / "backups"


class UserUpdateIn(BaseModel):
    role_code: str
    is_active: bool


class OverrideIn(BaseModel):
    code: str
    granted: bool | None  # None removes the override


class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(None, max_length=255)
    permissions: list[str] = Field(default_factory=list)


class SettingsIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=160)
    legal_name: str | None = Field(None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40)
    website: str | None = Field(None, max_length=190)
    address: str | None = Field(None, max_length=2000)
    tax_id: str | None = Field(None, max_length=60)
    timezone: str = Field("Asia/Kolkata", max_length=64)
    currency: str = Field("INR", min_length=3, max_length=3)
    employee_code_prefix: str = Field("ECH", min_length=1, max_length=10, pattern=r"^[A-Za-z]+$")
    work_start: time
    work_end: time
    grace_minutes: int = Field(15, ge=0, le=180)
    half_day_minutes: int = Field(240, ge=30, le=720)
    full_day_minutes: int = Field(480, ge=60, le=900)
    weekly_offs: list[int] = Field(default_factory=lambda: [5, 6])
    face_match_threshold: float | None = Field(None, ge=0.3, le=0.8)
    biometric_retention_days: int = Field(30, ge=0, le=3650)
    require_face_for_attendance: bool = True
    session_timeout_minutes: int = Field(480, ge=15, le=10080)


def _user(u: User) -> dict:
    return {"id": u.id, "email": u.email, "is_active": u.is_active, "role": {"code": u.role.code, "name": u.role.name},
            "employee": {"id": u.employee.id, "full_name": u.employee.full_name, "employee_code": u.employee.employee_code,
                         "photo_file_id": u.employee.photo_file_id} if u.employee else None,
            "last_login_at": u.last_login_at, "locked": bool(u.locked_until and u.locked_until > datetime.utcnow()),
            "must_change_password": u.must_change_password,
            "overrides": [{"code": o.permission.code, "granted": o.granted} for o in u.overrides]}


# ------------------------------------------------------------------ users

@router.get("/users")
def users(q: str | None = None, role: str | None = None, page: int = 1, page_size: int = 25,
          current: CurrentUser = Depends(require("admin.users")), db: Session = Depends(get_db)):
    stmt = select(User).outerjoin(Employee, Employee.id == User.employee_id).order_by(User.email)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.email.ilike(like), Employee.first_name.ilike(like), Employee.last_name.ilike(like)))
    if role:
        stmt = stmt.join(Role, Role.id == User.role_id).where(Role.code == role)
    return paginate(db, stmt, page, page_size, _user)


@router.put("/users/{uid}")
def update_user(uid: int, body: UserUpdateIn, request: Request, current: CurrentUser = Depends(require("admin.users")),
                db: Session = Depends(get_db)):
    u = get_or_404(db, User, uid, "User")
    role = db.scalar(select(Role).where(Role.code == body.role_code))
    if not role:
        raise HTTPException(422, "Role not found")
    touching_super = SUPER_ADMIN in (role.code, u.role.code)
    if touching_super and current.role != SUPER_ADMIN:
        raise HTTPException(403, "Only a Super Admin can grant or remove the Super Admin role")
    if u.id == current.id and (not body.is_active or role.code != u.role.code):
        raise HTTPException(400, "You cannot change your own role or deactivate yourself")
    if u.role.code == SUPER_ADMIN and (role.code != SUPER_ADMIN or not body.is_active):
        others = db.scalar(select(func.count()).select_from(User).join(Role).where(
            Role.code == SUPER_ADMIN, User.is_active.is_(True), User.id != u.id))
        if not others:
            raise HTTPException(409, "At least one active Super Admin must remain")
    changed = role.id != u.role_id or body.is_active != u.is_active
    u.role_id, u.is_active = role.id, body.is_active
    if changed:
        revoke_all(db, u)
    if body.is_active:
        u.locked_until, u.failed_logins = None, 0
    audit(db, current.user, "user.update", "user", u.id, f"{u.email}: role={role.code}, active={body.is_active}",
          ip=client_ip(request))
    db.commit()
    db.refresh(u)
    return _user(u)


@router.put("/users/{uid}/permissions")
def set_override(uid: int, body: OverrideIn, current: CurrentUser = Depends(require("admin.roles")), db: Session = Depends(get_db)):
    u = get_or_404(db, User, uid, "User")
    p = db.scalar(select(Permission).where(Permission.code == body.code))
    if not p:
        raise HTTPException(422, "Unknown permission")
    if u.role.code == SUPER_ADMIN:
        raise HTTPException(409, "Super Admins always have every permission")
    o = db.scalar(select(UserPermissionOverride).where(UserPermissionOverride.user_id == uid,
                                                       UserPermissionOverride.permission_id == p.id))
    if body.granted is None:
        if o:
            db.delete(o)
    elif o:
        o.granted = body.granted
    else:
        db.add(UserPermissionOverride(user_id=uid, permission_id=p.id, granted=body.granted))
    audit(db, current.user, "user.permission_override", "user", uid, f"{body.code} → {body.granted}")
    db.commit()
    db.refresh(u)
    return {**_user(u), "effective": sorted(effective_permissions(u))}


# ------------------------------------------------------------------ roles

@router.get("/permissions")
def permissions(current: CurrentUser = Depends(require("admin.roles"))):
    return [{"code": c, "module": m, "description": d} for c, (m, d) in PERMISSIONS.items()]


@router.get("/roles")
def roles(current: CurrentUser = Depends(require("admin.roles")), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(User.role_id, func.count()).group_by(User.role_id)).all())
    return [{"id": r.id, "code": r.code, "name": r.name, "description": r.description, "is_system": r.is_system,
             "user_count": counts.get(r.id, 0), "permissions": sorted(p.code for p in r.permissions)}
            for r in db.scalars(select(Role).order_by(Role.id))]


@router.post("/roles", status_code=201)
def create_role(body: RoleIn, current: CurrentUser = Depends(require("admin.roles")), db: Session = Depends(get_db)):
    code = "custom_" + "".join(c if c.isalnum() else "_" for c in body.name.lower())[:30]
    if db.scalar(select(Role.id).where(or_(Role.code == code, Role.name == body.name))):
        raise HTTPException(409, "A role with this name exists")
    perms = db.scalars(select(Permission).where(Permission.code.in_(body.permissions))).all()
    r = Role(code=code, name=body.name, description=body.description, is_system=False, permissions=list(perms))
    db.add(r)
    audit(db, current.user, "role.create", "role", None, f"Created role {body.name}")
    db.commit()
    return {"id": r.id, "code": r.code}


@router.put("/roles/{rid}")
def update_role(rid: int, body: RoleIn, request: Request, current: CurrentUser = Depends(require("admin.roles")),
                db: Session = Depends(get_db)):
    r = get_or_404(db, Role, rid, "Role")
    if r.code == SUPER_ADMIN:
        raise HTTPException(409, "The Super Admin role always has every permission")
    unknown = set(body.permissions) - set(PERMISSIONS)
    if unknown:
        raise HTTPException(422, f"Unknown permissions: {', '.join(sorted(unknown))}")
    before = {p.code for p in r.permissions}
    r.permissions = list(db.scalars(select(Permission).where(Permission.code.in_(body.permissions))))
    r.description = body.description
    if not r.is_system:
        r.name = body.name
    after = set(body.permissions)
    audit(db, current.user, "role.update", "role", r.id, f"Updated permissions of {r.name}",
          {"added": sorted(after - before), "removed": sorted(before - after)}, ip=client_ip(request))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ settings

@router.get("/settings")
def get_settings(current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    cs = get_company(db)
    base = {"company_name": cs.company_name, "timezone": cs.timezone, "currency": cs.currency,
            "work_start": cs.work_start.strftime("%H:%M"), "work_end": cs.work_end.strftime("%H:%M"),
            "weekly_offs": cs.weekly_offs, "require_face_for_attendance": cs.require_face_for_attendance}
    if not current.has("admin.settings"):
        return base
    from app.services.ai import ai_configured
    from app.services.email_sync import provider_configured
    return base | {
        "legal_name": cs.legal_name, "email": cs.email, "phone": cs.phone, "website": cs.website, "address": cs.address,
        "tax_id": cs.tax_id, "employee_code_prefix": cs.employee_code_prefix, "grace_minutes": cs.grace_minutes,
        "half_day_minutes": cs.half_day_minutes, "full_day_minutes": cs.full_day_minutes,
        "face_match_threshold": cs.face_match_threshold, "biometric_retention_days": cs.biometric_retention_days,
        "session_timeout_minutes": cs.session_timeout_minutes,
        "integrations": {"gemini": ai_configured(), "gmail": provider_configured("gmail"),
                         "outlook": provider_configured("outlook"),
                         "s3": settings.STORAGE_BACKEND == "s3" and bool(settings.AWS_S3_BUCKET),
                         "redis": bool(settings.REDIS_URL), "storage_backend": settings.STORAGE_BACKEND},
        "security": {"access_token_minutes": settings.ACCESS_TOKEN_MINUTES, "refresh_token_days": settings.REFRESH_TOKEN_DAYS,
                     "max_login_attempts": settings.MAX_LOGIN_ATTEMPTS, "lockout_minutes": settings.LOCKOUT_MINUTES}}


@router.put("/settings")
def update_settings(body: SettingsIn, request: Request, current: CurrentUser = Depends(require("admin.settings")),
                    db: Session = Depends(get_db)):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(422, "Unknown timezone")
    if body.work_end <= body.work_start:
        raise HTTPException(422, "Work end must be after work start")
    if body.half_day_minutes >= body.full_day_minutes:
        raise HTTPException(422, "Half-day threshold must be less than the full-day threshold")
    if any(d < 0 or d > 6 for d in body.weekly_offs):
        raise HTTPException(422, "Weekly offs must be weekday numbers 0 (Mon) – 6 (Sun)")
    cs = get_company(db)
    changes = {}
    for k, v in body.model_dump().items():
        if getattr(cs, k) != v:
            changes[k] = str(v)
            setattr(cs, k, v)
    cs.currency = cs.currency.upper()
    cs.employee_code_prefix = cs.employee_code_prefix.upper()
    audit(db, current.user, "settings.update", "company_settings", 1, "Updated company settings", changes, ip=client_ip(request))
    db.commit()
    return get_settings(current, db)


# ------------------------------------------------------------------ audit

@router.get("/audit")
def audit_log(q: str | None = None, action: str | None = None, user_id: int | None = None, entity_type: str | None = None,
              date_from: date | None = None, date_to: date | None = None, page: int = 1, page_size: int = 50,
              current: CurrentUser = Depends(require("admin.audit")), db: Session = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if q:
        stmt = stmt.where(or_(AuditLog.summary.ilike(f"%{q}%"), AuditLog.action.ilike(f"%{q}%")))
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(date_to, time.max))
    return paginate(db, stmt, page, page_size, lambda a: {
        "id": a.id, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id, "summary": a.summary,
        "details": a.details, "ip_address": a.ip_address, "created_at": a.created_at,
        "user": (a.user.employee.full_name if a.user and a.user.employee else a.user.email) if a.user else "System"})


# ------------------------------------------------------------------ backups

def _mysqldump() -> str | None:
    found = shutil.which("mysqldump")
    if found:
        return found
    for p in [r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe", "/usr/bin/mysqldump", "/usr/local/bin/mysqldump"]:
        if Path(p).exists():
            return p
    return None


@router.get("/backups")
def list_backups(current: CurrentUser = Depends(require("admin.backup"))):
    BACKUP_DIR.mkdir(exist_ok=True)
    return {"tool_available": bool(_mysqldump()), "backups": sorted([
        {"name": f.name, "size": f.stat().st_size, "created_at": datetime.fromtimestamp(f.stat().st_mtime)}
        for f in BACKUP_DIR.glob("*.sql")], key=lambda x: x["created_at"], reverse=True)}


@router.post("/backups", status_code=201)
def create_backup(request: Request, current: CurrentUser = Depends(require("admin.backup")), db: Session = Depends(get_db)):
    tool = _mysqldump()
    if not tool:
        raise HTTPException(503, "mysqldump was not found on the server. See docs/DEPLOYMENT.md for backup setup.")
    BACKUP_DIR.mkdir(exist_ok=True)
    name = f"echo_attend-{datetime.now():%Y%m%d-%H%M%S}.sql"
    target = BACKUP_DIR / name
    env = {**os.environ, "MYSQL_PWD": settings.DB_PASSWORD}  # never on the command line
    cmd = [tool, "-h", settings.DB_HOST, "-P", str(settings.DB_PORT), "-u", settings.DB_USER, "--single-transaction",
           "--routines", "--triggers", "--set-gtid-purged=OFF", f"--result-file={target}", settings.DB_NAME]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        target.unlink(missing_ok=True)
        raise HTTPException(500, f"Backup failed: {proc.stderr.strip()[:300]}")
    audit(db, current.user, "admin.backup", "backup", None, f"Created backup {name}", ip=client_ip(request))
    db.commit()
    return {"name": name, "size": target.stat().st_size}


@router.get("/backups/{name}")
def download_backup(name: str, current: CurrentUser = Depends(require("admin.backup")), db: Session = Depends(get_db)):
    path = (BACKUP_DIR / name).resolve()
    if path.parent != BACKUP_DIR.resolve() or not path.exists() or path.suffix != ".sql":
        raise HTTPException(404, "Backup not found")
    audit(db, current.user, "admin.backup_download", "backup", None, f"Downloaded backup {name}")
    db.commit()
    return FileResponse(path, media_type="application/sql", filename=name)
