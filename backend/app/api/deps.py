from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.services.authz import effective_permissions

bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user: User
    perms: set[str]

    @property
    def id(self) -> int:
        return self.user.id

    @property
    def employee_id(self) -> int | None:
        return self.user.employee_id

    @property
    def role(self) -> str:
        return self.user.role.code

    def has(self, *codes: str) -> bool:
        return all(c in self.perms for c in codes)

    def has_any(self, *codes: str) -> bool:
        return any(c in self.perms for c in codes)

    def require(self, *codes: str) -> None:
        if not self.has(*codes):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action")


def get_current(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or user.token_version != payload.get("tv"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is no longer valid")
    request.state.user_id = user.id
    return CurrentUser(user=user, perms=effective_permissions(user))


def require(*codes: str):
    def dep(current: CurrentUser = Depends(get_current)) -> CurrentUser:
        current.require(*codes)
        return current

    return dep


def require_any(*codes: str):
    def dep(current: CurrentUser = Depends(get_current)) -> CurrentUser:
        if not current.has_any(*codes):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action")
        return current

    return dep


def require_employee(current: CurrentUser = Depends(get_current)) -> CurrentUser:
    if not current.employee_id:
        raise HTTPException(400, "Your account is not linked to an employee profile")
    return current


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None
