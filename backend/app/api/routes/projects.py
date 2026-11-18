from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, get_current
from app.db.base import utcnow
from app.db.session import get_db
from app.models import (
    Client, Employee, Milestone, Project, ProjectMember, StoredFile, Task, TaskComment, TaskHistory, TaskUpdate,
)
from app.schemas.work import CommentIn, MemberIn, MilestoneIn, ProjectIn, TaskIn, TaskStatusIn, TaskUpdateIn
from app.services.authz import accessible_project_ids
from app.services.common import audit, get_or_404, notify, paginate, today_local, user_ids_for_employees
from app.services.storage import delete_file, store_upload
from app.services.work import (
    can_manage_project, is_member, next_project_code, recompute_progress, require_project_view, serialize_project,
    serialize_task,
)

router = APIRouter(tags=["Projects & Tasks"])


def _check_refs(db: Session, body: ProjectIn):
    if body.client_id and not db.get(Client, body.client_id):
        raise HTTPException(422, "Client not found")
    if body.manager_id:
        m = db.get(Employee, body.manager_id)
        if not m or m.status == "inactive":
            raise HTTPException(422, "Project manager not found or inactive")


# ------------------------------------------------------------------ projects

@router.get("/projects")
def list_projects(q: str | None = None, status: str | None = None, client_id: int | None = None,
                  manager_id: int | None = None, delayed: bool = False, page: int = 1, page_size: int = 20,
                  current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    stmt = select(Project).order_by(Project.updated_at.desc())
    ids = accessible_project_ids(db, current.user, current.perms)
    if ids is not None:
        stmt = stmt.where(Project.id.in_(ids or [0]))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Project.name.ilike(like), Project.code.ilike(like)))
    if status:
        stmt = stmt.where(Project.status == status)
    if client_id:
        stmt = stmt.where(Project.client_id == client_id)
    if manager_id:
        stmt = stmt.where(Project.manager_id == manager_id)
    if delayed:
        stmt = stmt.where(Project.end_date < today_local(db), Project.status.not_in(["completed", "cancelled"]))
    return paginate(db, stmt, page, page_size, lambda p: serialize_project(db, p))


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, request: Request, current: CurrentUser = Depends(get_current),
                   db: Session = Depends(get_db)):
    current.require("projects.manage")
    _check_refs(db, body)
    p = Project(code=next_project_code(db), created_by_id=current.id, **body.model_dump())
    db.add(p)
    db.flush()
    if p.manager_id:
        db.add(ProjectMember(project_id=p.id, employee_id=p.manager_id, role="Project Manager"))
        notify(db, user_ids_for_employees(db, [p.manager_id]), "You are managing a new project",
               f"{p.name} ({p.code})", f"/projects/{p.id}", "project")
    audit(db, current.user, "project.create", "project", p.id, f"Created project {p.name}", ip=client_ip(request))
    db.commit()
    db.refresh(p)
    return serialize_project(db, p, detail=True)


@router.get("/projects/{pid}")
def get_project(pid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    require_project_view(db, current, p)
    data = serialize_project(db, p, detail=True)
    data["can_manage"] = can_manage_project(current, p)
    return data


@router.put("/projects/{pid}")
def update_project(pid: int, body: ProjectIn, request: Request, current: CurrentUser = Depends(get_current),
                   db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    if not can_manage_project(current, p):
        raise HTTPException(403, "Only the project manager or administrators can edit this project")
    if body.manager_id != p.manager_id and not current.has("projects.manage"):
        raise HTTPException(403, "Only administrators can reassign the project manager")
    _check_refs(db, body)
    old_mgr = p.manager_id
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    if p.manager_id and p.manager_id != old_mgr:
        if not is_member(db, p.id, p.manager_id):
            db.add(ProjectMember(project_id=p.id, employee_id=p.manager_id, role="Project Manager"))
        notify(db, user_ids_for_employees(db, [p.manager_id]), "You are now managing a project", p.name,
               f"/projects/{p.id}", "project")
    recompute_progress(db, p.id)
    audit(db, current.user, "project.update", "project", p.id, f"Updated project {p.name}", ip=client_ip(request))
    db.commit()
    db.refresh(p)
    return serialize_project(db, p, detail=True)


@router.delete("/projects/{pid}")
def delete_project(pid: int, request: Request, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    current.require("projects.manage")
    p = get_or_404(db, Project, pid, "Project")
    if db.scalar(select(func.count()).select_from(Task).where(Task.project_id == pid)):
        raise HTTPException(409, "Project has tasks. Mark it cancelled or completed instead of deleting.")
    audit(db, current.user, "project.delete", "project", p.id, f"Deleted project {p.name}", ip=client_ip(request))
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/projects/{pid}/members", status_code=201)
def add_member(pid: int, body: MemberIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    if not can_manage_project(current, p):
        raise HTTPException(403, "Not allowed")
    emp = get_or_404(db, Employee, body.employee_id, "Employee")
    if emp.status == "inactive":
        raise HTTPException(422, "Employee is inactive")
    if is_member(db, pid, emp.id):
        raise HTTPException(409, f"{emp.full_name} is already on this project")
    db.add(ProjectMember(project_id=pid, **body.model_dump()))
    notify(db, user_ids_for_employees(db, [emp.id]), "Added to a project", f"You were added to {p.name}",
           f"/projects/{p.id}", "project")
    audit(db, current.user, "project.member_add", "project", pid, f"Added {emp.full_name}")
    db.commit()
    db.refresh(p)
    return serialize_project(db, p, detail=True)


@router.delete("/projects/{pid}/members/{mid}")
def remove_member(pid: int, mid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    if not can_manage_project(current, p):
        raise HTTPException(403, "Not allowed")
    m = get_or_404(db, ProjectMember, mid, "Member")
    if m.project_id != pid:
        raise HTTPException(404, "Member not found")
    if m.employee_id == p.manager_id:
        raise HTTPException(409, "Reassign the project manager before removing them")
    audit(db, current.user, "project.member_remove", "project", pid, f"Removed {m.employee.full_name}")
    db.delete(m)
    db.commit()
    db.refresh(p)
    return serialize_project(db, p, detail=True)


# ------------------------------------------------------------------ milestones

def _ms(m: Milestone, db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(Task).where(Task.milestone_id == m.id)) or 0
    done = db.scalar(select(func.count()).select_from(Task).where(Task.milestone_id == m.id, Task.status == "done")) or 0
    return {"id": m.id, "title": m.title, "description": m.description, "due_date": m.due_date, "status": m.status,
            "completed_at": m.completed_at, "task_total": total, "task_done": done,
            "is_overdue": bool(m.due_date and m.due_date < today_local(db) and m.status != "completed")}


@router.get("/projects/{pid}/milestones")
def list_milestones(pid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    require_project_view(db, current, p)
    return [_ms(m, db) for m in db.scalars(select(Milestone).where(Milestone.project_id == pid)
                                           .order_by(Milestone.due_date.is_(None), Milestone.due_date))]


@router.post("/projects/{pid}/milestones", status_code=201)
def create_milestone(pid: int, body: MilestoneIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    if not can_manage_project(current, p):
        raise HTTPException(403, "Not allowed")
    m = Milestone(project_id=pid, **body.model_dump())
    if m.status == "completed":
        m.completed_at = utcnow()
    db.add(m)
    db.flush()
    audit(db, current.user, "milestone.create", "project", pid, f"Milestone {m.title}")
    db.commit()
    return _ms(m, db)


@router.put("/projects/{pid}/milestones/{mid}")
def update_milestone(pid: int, mid: int, body: MilestoneIn, current: CurrentUser = Depends(get_current),
                     db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    if not can_manage_project(current, p):
        raise HTTPException(403, "Not allowed")
    m = get_or_404(db, Milestone, mid, "Milestone")
    if m.project_id != pid:
        raise HTTPException(404, "Milestone not found")
    was = m.status
    for k, v in body.model_dump().items():
        setattr(m, k, v)
    if m.status == "completed" and was != "completed":
        m.completed_at = utcnow()
    elif m.status != "completed":
        m.completed_at = None
    audit(db, current.user, "milestone.update", "project", pid, f"Milestone {m.title} → {m.status}")
    db.commit()
    return _ms(m, db)


@router.delete("/projects/{pid}/milestones/{mid}")
def delete_milestone(pid: int, mid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    if not can_manage_project(current, p):
        raise HTTPException(403, "Not allowed")
    m = get_or_404(db, Milestone, mid, "Milestone")
    if m.project_id != pid:
        raise HTTPException(404, "Milestone not found")
    db.delete(m)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ project files

@router.get("/projects/{pid}/files")
def project_files(pid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    require_project_view(db, current, p)
    rows = db.scalars(select(StoredFile).where(StoredFile.entity_type == "project", StoredFile.entity_id == pid)
                      .order_by(StoredFile.created_at.desc()))
    return [{"id": f.id, "name": f.original_name, "size": f.size_bytes, "content_type": f.content_type,
             "category": f.category, "description": f.description, "created_at": f.created_at,
             "uploaded_by": f.uploaded_by.email if f.uploaded_by else None} for f in rows]


@router.post("/projects/{pid}/files", status_code=201)
async def upload_project_file(pid: int, file: UploadFile = File(...), description: str | None = Form(None),
                              current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    require_project_view(db, current, p)
    f = await store_upload(db, file, current.user, "project", pid, "project_file", description)
    audit(db, current.user, "project.file_upload", "project", pid, f"Uploaded {f.original_name}")
    db.commit()
    return {"id": f.id, "name": f.original_name}


@router.delete("/projects/{pid}/files/{fid}")
def delete_project_file(pid: int, fid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    f = get_or_404(db, StoredFile, fid, "File")
    if f.entity_type != "project" or f.entity_id != pid:
        raise HTTPException(404, "File not found")
    if not (can_manage_project(current, p) or f.uploaded_by_id == current.id):
        raise HTTPException(403, "Not allowed")
    delete_file(db, f)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ tasks

def _task_scope(db: Session, current: CurrentUser):
    if current.has("tasks.manage_all"):
        return None
    ids = accessible_project_ids(db, current.user, current.perms)
    conds = [Task.assignee_id == current.employee_id, Task.reporter_id == current.employee_id]
    if ids is None:
        return None
    if ids:
        conds.append(Task.project_id.in_(ids))
    return or_(*conds)


def _can_view_task(db: Session, current: CurrentUser, t: Task) -> bool:
    if current.has("tasks.manage_all") or t.assignee_id == current.employee_id or t.reporter_id == current.employee_id:
        return True
    if t.project_id:
        ids = accessible_project_ids(db, current.user, current.perms)
        return ids is None or t.project_id in ids
    return False


def _can_edit_task(db: Session, current: CurrentUser, t: Task) -> bool:
    if current.has("tasks.manage_all") or (t.reporter_id and t.reporter_id == current.employee_id):
        return True
    if t.project_id:
        return can_manage_project(current, t.project)
    return t.assignee_id == current.employee_id


def _validate_task(db: Session, current: CurrentUser, body: TaskIn) -> None:
    if body.project_id:
        p = get_or_404(db, Project, body.project_id, "Project")
        if not (can_manage_project(current, p) or current.has("tasks.manage_all") or is_member(db, p.id, current.employee_id)):
            raise HTTPException(403, "You cannot create tasks in this project")
        if body.assignee_id and not (is_member(db, p.id, body.assignee_id) or p.manager_id == body.assignee_id):
            raise HTTPException(422, "Assignee must be a member of the project")
        if body.milestone_id:
            m = db.get(Milestone, body.milestone_id)
            if not m or m.project_id != p.id:
                raise HTTPException(422, "Milestone does not belong to this project")
    else:
        if body.milestone_id:
            raise HTTPException(422, "Milestones require a project")
        if body.assignee_id and body.assignee_id != current.employee_id and not current.has("tasks.manage_all"):
            raise HTTPException(403, "Personal tasks can only be assigned to yourself")
    if body.assignee_id:
        a = db.get(Employee, body.assignee_id)
        if not a or a.status == "inactive":
            raise HTTPException(422, "Assignee not found or inactive")


@router.get("/tasks")
def list_tasks(scope: str = "mine", q: str | None = None, status: str | None = None, priority: str | None = None,
               project_id: int | None = None, assignee_id: int | None = None, overdue: bool = False,
               page: int = 1, page_size: int = 50, current: CurrentUser = Depends(get_current),
               db: Session = Depends(get_db)):
    """scope: mine (assigned to me) | created (reported by me) | all (everything I can see)."""
    stmt = select(Task)
    if scope == "mine":
        stmt = stmt.where(Task.assignee_id == (current.employee_id or 0))
    elif scope == "created":
        stmt = stmt.where(Task.reporter_id == (current.employee_id or 0))
    else:
        cond = _task_scope(db, current)
        if cond is not None:
            stmt = stmt.where(cond)
    if q:
        stmt = stmt.where(Task.title.ilike(f"%{q.strip()}%"))
    if status:
        stmt = stmt.where(Task.status.in_(status.split(",")))
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if project_id:
        p = get_or_404(db, Project, project_id, "Project")
        require_project_view(db, current, p)
        stmt = stmt.where(Task.project_id == project_id)
    if assignee_id:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if overdue:
        stmt = stmt.where(Task.due_date < today_local(db), Task.status != "done")
    stmt = stmt.order_by(Task.status == "done", Task.due_date.is_(None), Task.due_date, Task.id.desc())
    return paginate(db, stmt, page, page_size, lambda t: serialize_task(db, t))


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    if not current.employee_id:
        raise HTTPException(400, "Your account is not linked to an employee profile")
    _validate_task(db, current, body)
    t = Task(reporter_id=current.employee_id, **body.model_dump())
    if t.status == "done":
        t.completed_at, t.progress = utcnow(), 100
    db.add(t)
    db.flush()
    db.add(TaskHistory(task_id=t.id, user_id=current.id, field="created", new_value=t.title))
    if t.assignee_id and t.assignee_id != current.employee_id:
        notify(db, user_ids_for_employees(db, [t.assignee_id]), "New task assigned", t.title, f"/tasks/{t.id}", "task")
    recompute_progress(db, t.project_id)
    audit(db, current.user, "task.create", "task", t.id, f"Created task {t.title}")
    db.commit()
    db.refresh(t)
    return serialize_task(db, t)


@router.get("/tasks/{tid}")
def get_task(tid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    t = get_or_404(db, Task, tid, "Task")
    if not _can_view_task(db, current, t):
        raise HTTPException(403, "You do not have access to this task")
    data = serialize_task(db, t)
    data["can_edit"] = _can_edit_task(db, current, t)
    data["can_update_status"] = data["can_edit"] or t.assignee_id == current.employee_id
    data["comments"] = [{"id": c.id, "body": c.body, "created_at": c.created_at,
                         "author": {"id": c.author.id, "email": c.author.email,
                                    "name": c.author.employee.full_name if c.author and c.author.employee else None,
                                    "photo_file_id": c.author.employee.photo_file_id if c.author and c.author.employee else None}
                         if c.author else None}
                        for c in db.scalars(select(TaskComment).where(TaskComment.task_id == tid).order_by(TaskComment.created_at))]
    data["updates"] = [{"id": u.id, "update_date": u.update_date, "progress": u.progress, "hours_spent": u.hours_spent,
                        "note": u.note, "employee": {"id": u.employee.id, "full_name": u.employee.full_name}, "created_at": u.created_at}
                       for u in db.scalars(select(TaskUpdate).where(TaskUpdate.task_id == tid).order_by(TaskUpdate.created_at.desc()))]
    data["history"] = [{"field": h.field, "old_value": h.old_value, "new_value": h.new_value, "created_at": h.created_at,
                        "user": h.user.email if h.user else None}
                       for h in db.scalars(select(TaskHistory).where(TaskHistory.task_id == tid).order_by(TaskHistory.created_at.desc()))]
    return data


def _log_changes(db: Session, t: Task, user_id: int, before: dict) -> None:
    for k, old in before.items():
        new = getattr(t, k)
        if old != new:
            db.add(TaskHistory(task_id=t.id, user_id=user_id, field=k, old_value=str(old) if old is not None else None,
                               new_value=str(new) if new is not None else None))


def _apply_status(t: Task, status: str) -> None:
    t.status = status
    if status == "done":
        t.completed_at, t.progress = t.completed_at or utcnow(), 100
    else:
        t.completed_at = None
        if t.progress == 100:
            t.progress = 90


@router.put("/tasks/{tid}")
def update_task(tid: int, body: TaskIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    t = get_or_404(db, Task, tid, "Task")
    if not _can_edit_task(db, current, t):
        raise HTTPException(403, "You cannot edit this task")
    _validate_task(db, current, body)
    fields = body.model_dump()
    before = {k: getattr(t, k) for k in fields}
    old_project, old_assignee = t.project_id, t.assignee_id
    status = fields.pop("status")
    for k, v in fields.items():
        setattr(t, k, v)
    if status != t.status:
        _apply_status(t, status)
    _log_changes(db, t, current.id, before)
    if t.assignee_id and t.assignee_id != old_assignee and t.assignee_id != current.employee_id:
        notify(db, user_ids_for_employees(db, [t.assignee_id]), "Task assigned to you", t.title, f"/tasks/{t.id}", "task")
    recompute_progress(db, t.project_id)
    if old_project != t.project_id:
        recompute_progress(db, old_project)
    db.commit()
    db.refresh(t)
    return serialize_task(db, t)


@router.patch("/tasks/{tid}/status")
def update_task_status(tid: int, body: TaskStatusIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    t = get_or_404(db, Task, tid, "Task")
    if not (_can_edit_task(db, current, t) or t.assignee_id == current.employee_id):
        raise HTTPException(403, "You cannot update this task")
    before = {"status": t.status, "progress": t.progress}
    _apply_status(t, body.status)
    _log_changes(db, t, current.id, before)
    if body.status in ("done", "review", "blocked") and t.reporter_id and t.reporter_id != current.employee_id:
        notify(db, user_ids_for_employees(db, [t.reporter_id]), f"Task moved to {body.status.replace('_', ' ')}",
               t.title, f"/tasks/{t.id}", "task")
    recompute_progress(db, t.project_id)
    db.commit()
    db.refresh(t)
    return serialize_task(db, t)


@router.delete("/tasks/{tid}")
def delete_task(tid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    t = get_or_404(db, Task, tid, "Task")
    if not _can_edit_task(db, current, t):
        raise HTTPException(403, "You cannot delete this task")
    pid = t.project_id
    audit(db, current.user, "task.delete", "task", t.id, f"Deleted task {t.title}")
    db.delete(t)
    db.flush()
    recompute_progress(db, pid)
    db.commit()
    return {"ok": True}


@router.post("/tasks/{tid}/comments", status_code=201)
def add_comment(tid: int, body: CommentIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    t = get_or_404(db, Task, tid, "Task")
    if not _can_view_task(db, current, t):
        raise HTTPException(403, "Not allowed")
    db.add(TaskComment(task_id=tid, author_id=current.id, body=body.body.strip()))
    recipients = {t.assignee_id, t.reporter_id} - {current.employee_id}
    name = current.user.employee.full_name if current.user.employee else current.user.email
    notify(db, user_ids_for_employees(db, list(recipients)), f"{name} commented on a task", t.title, f"/tasks/{t.id}", "task")
    db.commit()
    return {"ok": True}


@router.post("/tasks/{tid}/updates", status_code=201)
def add_progress_update(tid: int, body: TaskUpdateIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    t = get_or_404(db, Task, tid, "Task")
    if t.assignee_id != current.employee_id and not _can_edit_task(db, current, t):
        raise HTTPException(403, "Only the assignee can post progress updates")
    d = body.update_date or today_local(db)
    if d > today_local(db):
        raise HTTPException(422, "Update date cannot be in the future")
    db.add(TaskUpdate(task_id=tid, employee_id=current.employee_id, update_date=d, progress=body.progress,
                      hours_spent=body.hours_spent, note=body.note))
    before = {"progress": t.progress, "status": t.status}
    t.progress = body.progress
    if body.progress == 100 and t.status != "done":
        _apply_status(t, "review" if t.reporter_id and t.reporter_id != current.employee_id else "done")
    elif t.status == "todo" and body.progress > 0:
        t.status = "in_progress"
    _log_changes(db, t, current.id, before)
    recompute_progress(db, t.project_id)
    db.commit()
    return {"ok": True}


@router.get("/projects/{pid}/report")
def project_report(pid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Project, pid, "Project")
    require_project_view(db, current, p)
    tasks = db.scalars(select(Task).where(Task.project_id == pid)).unique().all()
    today = today_local(db)
    by_member = {}
    for t in tasks:
        key = t.assignee.full_name if t.assignee else "Unassigned"
        row = by_member.setdefault(key, {"name": key, "total": 0, "done": 0, "overdue": 0, "hours": 0.0})
        row["total"] += 1
        row["done"] += t.status == "done"
        row["overdue"] += bool(t.due_date and t.due_date < today and t.status != "done")
    hours = dict(db.execute(select(TaskUpdate.employee_id, func.sum(TaskUpdate.hours_spent))
                            .join(Task, Task.id == TaskUpdate.task_id).where(Task.project_id == pid)
                            .group_by(TaskUpdate.employee_id)).all())
    for t in tasks:
        if t.assignee and t.assignee_id in hours:
            by_member[t.assignee.full_name]["hours"] = float(hours[t.assignee_id] or 0)
    return {
        "project": serialize_project(db, p),
        "status_breakdown": [{"status": s, "count": sum(1 for t in tasks if t.status == s)}
                             for s in ("todo", "in_progress", "review", "blocked", "done")],
        "priority_breakdown": [{"priority": s, "count": sum(1 for t in tasks if t.priority == s)}
                               for s in ("low", "medium", "high", "urgent")],
        "members": sorted(by_member.values(), key=lambda r: -r["total"]),
        "days_remaining": (p.end_date - today).days if p.end_date else None,
        "generated_on": date.today(),
    }
