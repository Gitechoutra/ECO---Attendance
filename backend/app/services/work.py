from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.models import Project, ProjectMember, Task
from app.services.authz import accessible_project_ids
from app.services.common import today_local
from app.services.employees import employee_brief


def next_project_code(db: Session) -> str:
    n = db.scalar(select(func.max(Project.id))) or 0
    code = f"PRJ-{n + 1:04d}"
    while db.scalar(select(Project.id).where(Project.code == code)):
        n += 1
        code = f"PRJ-{n + 1:04d}"
    return code


def recompute_progress(db: Session, project_id: int | None) -> None:
    if not project_id:
        return
    p = db.get(Project, project_id)
    tasks = db.scalars(select(Task).where(Task.project_id == project_id)).unique().all()
    if not tasks:
        p.progress = 100.0 if p.status == "completed" else 0.0
        return
    total_w = sum((t.estimated_hours or 1) for t in tasks)
    done = sum((t.estimated_hours or 1) * (100 if t.status == "done" else t.progress) / 100 for t in tasks)
    p.progress = round(done / total_w * 100, 1)


def can_view_project(db: Session, current: CurrentUser, project_id: int) -> bool:
    ids = accessible_project_ids(db, current.user, current.perms)
    return ids is None or project_id in ids


def can_manage_project(current: CurrentUser, p: Project) -> bool:
    return current.has("projects.manage") or (current.employee_id is not None and p.manager_id == current.employee_id)


def require_project_view(db: Session, current: CurrentUser, p: Project) -> None:
    if not can_view_project(db, current, p.id):
        raise HTTPException(403, "You do not have access to this project")


def is_member(db: Session, project_id: int, employee_id: int | None) -> bool:
    if not employee_id:
        return False
    return bool(db.scalar(select(ProjectMember.id).where(ProjectMember.project_id == project_id,
                                                         ProjectMember.employee_id == employee_id)))


def serialize_project(db: Session, p: Project, detail: bool = False) -> dict:
    today = today_local(db)
    counts = dict(db.execute(select(Task.status, func.count()).where(Task.project_id == p.id).group_by(Task.status)).all())
    overdue = db.scalar(select(func.count()).select_from(Task).where(Task.project_id == p.id, Task.status != "done",
                                                                     Task.due_date < today)) or 0
    is_delayed = bool(p.end_date and p.end_date < today and p.status not in ("completed", "cancelled"))
    data = {
        "id": p.id, "code": p.code, "name": p.name, "status": p.status, "priority": p.priority,
        "start_date": p.start_date, "end_date": p.end_date, "progress": p.progress,
        "client": {"id": p.client.id, "name": p.client.name} if p.client else None, "client_id": p.client_id,
        "manager": employee_brief(p.manager), "manager_id": p.manager_id,
        "member_count": len(p.members), "task_counts": counts, "task_total": sum(counts.values()),
        "overdue_tasks": overdue, "is_delayed": is_delayed,
        "members": [{"id": m.id, "employee": employee_brief(m.employee), "role": m.role,
                     "allocation_percent": m.allocation_percent} for m in p.members] if detail else None,
    }
    if detail:
        data.update({"description": p.description, "budget": float(p.budget) if p.budget is not None else None,
                     "created_at": p.created_at})
    return data


def serialize_task(db: Session, t: Task) -> dict:
    today = today_local(db)
    return {
        "id": t.id, "title": t.title, "description": t.description, "status": t.status, "priority": t.priority,
        "due_date": t.due_date, "estimated_hours": t.estimated_hours, "progress": t.progress,
        "project": {"id": t.project.id, "name": t.project.name, "code": t.project.code} if t.project else None,
        "project_id": t.project_id, "milestone_id": t.milestone_id,
        "assignee": employee_brief(t.assignee), "assignee_id": t.assignee_id, "reporter": employee_brief(t.reporter),
        "is_overdue": bool(t.due_date and t.due_date < today and t.status != "done"),
        "completed_at": t.completed_at, "created_at": t.created_at, "updated_at": t.updated_at,
    }
