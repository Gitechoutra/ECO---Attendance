"""Authorization helpers: effective permissions and row-level scoping."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.permissions import SUPER_ADMIN
from app.models import Project, ProjectMember, User


def effective_permissions(user: User) -> set[str]:
    perms = {p.code for p in user.role.permissions}
    if user.role.code == SUPER_ADMIN:
        from app.core.permissions import ALL
        perms |= ALL
    for o in user.overrides:
        if o.granted:
            perms.add(o.permission.code)
        else:
            perms.discard(o.permission.code)
    return perms


def accessible_project_ids(db: Session, user: User, perms: set[str]) -> list[int] | None:
    """None means unrestricted. Otherwise projects the user manages or is a member of."""
    if "projects.view_all" in perms:
        return None
    emp_id = user.employee_id
    if not emp_id:
        return []
    managed = select(Project.id).where(Project.manager_id == emp_id)
    member = select(ProjectMember.project_id).where(ProjectMember.employee_id == emp_id)
    return list(db.scalars(select(Project.id).where(or_(Project.id.in_(managed), Project.id.in_(member)))))


def managed_project_ids(db: Session, user: User) -> list[int]:
    if not user.employee_id:
        return []
    return list(db.scalars(select(Project.id).where(Project.manager_id == user.employee_id)))


def accessible_client_ids(db: Session, user: User, perms: set[str]) -> list[int] | None:
    """None = all clients. Project managers / members see clients of their projects."""
    if "clients.manage" in perms or ("clients.view" in perms and "projects.view_all" in perms):
        return None
    pids = accessible_project_ids(db, user, perms)
    ids = set()
    if pids:
        ids |= {c for c in db.scalars(select(Project.client_id).where(Project.id.in_(pids))) if c}
    if user.employee_id:
        from app.models import Client
        ids |= set(db.scalars(select(Client.id).where(Client.account_manager_id == user.employee_id)))
    return list(ids) if "clients.view" in perms else []
