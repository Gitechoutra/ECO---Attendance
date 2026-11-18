from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current
from app.db.base import utcnow
from app.db.session import get_db
from app.models import (
    Announcement, AttendanceCorrection, AttendanceRecord, AuditLog, Candidate, Client, Department, Employee, Expense,
    Holiday, JobOpening, LeaveBalance, LeaveRequest, Meeting, MeetingAttendee, OfferLetter, PayrollRun, Project,
    ProjectMember, Task,
)
from app.services.attendance import is_working_day, serialize_record
from app.services.authz import accessible_client_ids, accessible_project_ids
from app.services.common import company_tz, today_local
from app.services.employees import employee_brief
from app.services.work import serialize_project, serialize_task

router = APIRouter(tags=["Dashboard"])


def _personal(db: Session, current: CurrentUser, today) -> dict:
    eid = current.employee_id
    tz = company_tz(db)
    rec = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == eid, AttendanceRecord.work_date == today))
    month_start = today.replace(day=1)
    month_recs = db.scalars(select(AttendanceRecord).where(AttendanceRecord.employee_id == eid,
                                                           AttendanceRecord.work_date >= month_start)).unique().all()
    open_tasks = select(Task).where(Task.assignee_id == eid, Task.status != "done")
    tasks = db.scalars(open_tasks.order_by(Task.due_date.is_(None), Task.due_date).limit(6)).unique().all()
    task_counts = {
        "open": db.scalar(select(func.count()).select_from(open_tasks.subquery())),
        "overdue": db.scalar(select(func.count()).select_from(Task).where(Task.assignee_id == eid, Task.status != "done",
                                                                          Task.due_date < today)),
        "due_this_week": db.scalar(select(func.count()).select_from(Task).where(
            Task.assignee_id == eid, Task.status != "done", Task.due_date.between(today, today + timedelta(days=7)))),
    }
    balances = db.scalars(select(LeaveBalance).where(LeaveBalance.employee_id == eid, LeaveBalance.year == today.year)).all()
    attending = select(MeetingAttendee.meeting_id).where(MeetingAttendee.employee_id == eid)
    meetings = db.scalars(select(Meeting).where(Meeting.id.in_(attending), Meeting.status != "cancelled",
                                                Meeting.end_at >= utcnow()).order_by(Meeting.start_at).limit(4)).unique().all()
    return {
        "attendance_today": serialize_record(rec, tz) if rec else None,
        "is_working_day": is_working_day(db, today),
        "month_attendance": {"present": sum(1 for r in month_recs if r.check_in_at),
                             "late": sum(1 for r in month_recs if r.late_minutes),
                             "hours": round(sum(r.worked_minutes for r in month_recs) / 60, 1)},
        "tasks": [serialize_task(db, t) for t in tasks], "task_counts": task_counts,
        "leave_balances": [{"name": b.leave_type.name, "code": b.leave_type.code, "color": b.leave_type.color,
                            "available": b.available, "allocated": b.allocated + b.carried}
                           for b in balances if b.leave_type.is_paid],
        "pending_leave": db.scalar(select(func.count()).select_from(LeaveRequest).where(
            LeaveRequest.employee_id == eid, LeaveRequest.status == "pending")),
        "meetings": [{"id": m.id, "title": m.title, "start_at": m.start_at, "end_at": m.end_at,
                      "meeting_link": m.meeting_link, "location": m.location} for m in meetings],
    }


def _company(db: Session, today) -> dict:
    active = select(Employee).where(Employee.status != "inactive")
    headcount = db.scalar(select(func.count()).select_from(active.subquery()))
    month_start = today.replace(day=1)
    joiners = db.scalar(select(func.count()).select_from(Employee).where(Employee.joining_date >= month_start,
                                                                         Employee.joining_date <= today))
    exits = db.scalar(select(func.count()).select_from(Employee).where(Employee.exit_date >= month_start,
                                                                       Employee.exit_date <= today))
    recs = db.scalars(select(AttendanceRecord).where(AttendanceRecord.work_date == today)).unique().all()
    on_leave = db.scalar(select(func.count(func.distinct(LeaveRequest.employee_id))).where(
        LeaveRequest.status == "approved", LeaveRequest.start_date <= today, LeaveRequest.end_date >= today))
    checked_in = sum(1 for r in recs if r.check_in_at)
    trend_start = today - timedelta(days=13)
    trend_rows = dict(db.execute(select(AttendanceRecord.work_date, func.count()).where(
        AttendanceRecord.work_date >= trend_start, AttendanceRecord.check_in_at.is_not(None))
        .group_by(AttendanceRecord.work_date)).all())
    late_rows = dict(db.execute(select(AttendanceRecord.work_date, func.count()).where(
        AttendanceRecord.work_date >= trend_start, AttendanceRecord.late_minutes > 0)
        .group_by(AttendanceRecord.work_date)).all())
    trend = []
    for i in range(14):
        d = trend_start + timedelta(days=i)
        if is_working_day(db, d):
            trend.append({"date": d, "present": trend_rows.get(d, 0), "late": late_rows.get(d, 0)})
    depts = db.execute(select(Department.name, func.count(Employee.id)).join(Employee, Employee.department_id == Department.id)
                       .where(Employee.status != "inactive").group_by(Department.name).order_by(func.count(Employee.id).desc())).all()
    unassigned = db.scalar(select(func.count()).select_from(Employee).where(Employee.status != "inactive",
                                                                            Employee.department_id.is_(None)))
    proj_status = dict(db.execute(select(Project.status, func.count()).group_by(Project.status)).all())
    delayed = db.scalars(select(Project).where(Project.end_date < today, Project.status.not_in(["completed", "cancelled"]))
                         .order_by(Project.end_date).limit(5)).unique().all()
    activity = db.scalars(select(AuditLog).where(AuditLog.action.not_in(["auth.login", "payroll.payslip_download"]))
                          .order_by(AuditLog.created_at.desc()).limit(10)).unique().all()
    return {
        "headcount": headcount, "new_joiners": joiners, "exits": exits,
        "today": {"checked_in": checked_in, "late": sum(1 for r in recs if r.late_minutes), "on_leave": on_leave,
                  "not_checked_in": max(headcount - checked_in - on_leave, 0) if is_working_day(db, today) else 0,
                  "is_working_day": is_working_day(db, today)},
        "attendance_trend": trend,
        "departments": [{"name": n, "count": c} for n, c in depts] + ([{"name": "Unassigned", "count": unassigned}] if unassigned else []),
        "projects": {"by_status": proj_status, "total": sum(proj_status.values()),
                     "delayed": [serialize_project(db, p) for p in delayed]},
        "clients": {"active": db.scalar(select(func.count()).select_from(Client).where(Client.status == "active")),
                    "leads": db.scalar(select(func.count()).select_from(Client).where(Client.status == "lead"))},
        "recruitment": {"open_jobs": db.scalar(select(func.count()).select_from(JobOpening).where(JobOpening.status == "open")),
                        "active_candidates": db.scalar(select(func.count()).select_from(Candidate).where(
                            Candidate.status.in_(["applied", "screening", "interview", "offered"])))},
        "activity": [{"id": a.id, "action": a.action, "summary": a.summary, "created_at": a.created_at,
                      "user": (a.user.employee.full_name if a.user and a.user.employee else a.user.email if a.user else "System")}
                     for a in activity],
    }


def _approvals(db: Session, current: CurrentUser) -> dict:
    out = {}
    if current.has("leave.approve"):
        out["leave"] = db.scalar(select(func.count()).select_from(LeaveRequest).where(
            LeaveRequest.status == "pending", LeaveRequest.employee_id != (current.employee_id or 0)))
    elif current.employee_id:
        reports = select(Employee.id).where(Employee.manager_id == current.employee_id)
        n = db.scalar(select(func.count()).select_from(LeaveRequest).where(LeaveRequest.status == "pending",
                                                                           LeaveRequest.employee_id.in_(reports)))
        if n:
            out["leave"] = n
    if current.has("attendance.manage"):
        out["attendance"] = db.scalar(select(func.count()).select_from(AttendanceCorrection).where(
            AttendanceCorrection.status == "pending"))
    if current.has("expenses.approve"):
        out["expenses"] = db.scalar(select(func.count()).select_from(Expense).where(Expense.status == "submitted"))
    if current.has("expenses.reimburse"):
        out["reimbursements"] = db.scalar(select(func.count()).select_from(Expense).where(Expense.status == "approved"))
    if current.has("offers.approve"):
        out["offers"] = db.scalar(select(func.count()).select_from(OfferLetter).where(OfferLetter.status == "pending_approval"))
    return out


def _manager(db: Session, current: CurrentUser, today) -> dict | None:
    if not current.employee_id:
        return None
    projects = db.scalars(select(Project).where(Project.manager_id == current.employee_id,
                                                Project.status.not_in(["completed", "cancelled"]))).unique().all()
    if not projects:
        return None
    pids = [p.id for p in projects]
    overdue = db.scalars(select(Task).where(Task.project_id.in_(pids), Task.status != "done", Task.due_date < today)
                         .order_by(Task.due_date).limit(8)).unique().all()
    load = db.execute(select(Task.assignee_id, func.count()).where(Task.project_id.in_(pids), Task.status != "done",
                                                                   Task.assignee_id.is_not(None)).group_by(Task.assignee_id)).all()
    members = {m.employee_id: m.employee for p in projects for m in p.members}
    return {"projects": [serialize_project(db, p) for p in projects],
            "overdue_tasks": [serialize_task(db, t) for t in overdue],
            "workload": sorted([{"employee": employee_brief(members.get(a) or db.get(Employee, a)), "open_tasks": n}
                                for a, n in load], key=lambda x: -x["open_tasks"])}


@router.get("/dashboard")
def dashboard(current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    today = today_local(db)
    data = {"date": today, "role": current.role, "sections": []}
    if current.employee_id:
        data["personal"] = _personal(db, current, today)
    if current.has("dashboard.company"):
        data["company"] = _company(db, today)
        if current.has("payroll.view"):
            last = db.scalar(select(PayrollRun).where(PayrollRun.status != "draft")
                             .order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).limit(1))
            data["company"]["last_payroll"] = None if not last else {
                "year": last.year, "month": last.month, "total_net": float(last.total_net), "status": last.status}
    data["approvals"] = _approvals(db, current)
    mgr = _manager(db, current, today)
    if mgr:
        data["manager"] = mgr
    ann_filter = or_(Announcement.expires_at.is_(None), Announcement.expires_at > utcnow())
    from app.api.routes.communication import _ann, _audience_filter
    stmt = select(Announcement).where(ann_filter).order_by(Announcement.is_pinned.desc(), Announcement.published_at.desc()).limit(4)
    if not current.has("announcements.manage"):
        stmt = stmt.where(_audience_filter(current))
    data["announcements"] = [_ann(a) for a in db.scalars(stmt).unique()]
    data["holidays"] = [{"date": h.date, "name": h.name} for h in db.scalars(
        select(Holiday).where(Holiday.date >= today, Holiday.is_optional.is_(False)).order_by(Holiday.date).limit(4))]
    return data


@router.get("/search")
def search(q: str, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    q = q.strip()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    out = []
    for e in db.scalars(select(Employee).where(Employee.status != "inactive", or_(
            Employee.first_name.ilike(like), Employee.last_name.ilike(like), Employee.employee_code.ilike(like),
            func.concat(Employee.first_name, " ", Employee.last_name).ilike(like))).limit(6)).unique():
        out.append({"type": "employee", "id": e.id, "title": e.full_name,
                    "subtitle": " · ".join(x for x in [e.employee_code, e.designation.title if e.designation else None] if x),
                    "link": f"/employees/{e.id}"})
    pids = accessible_project_ids(db, current.user, current.perms)
    ps = select(Project).where(or_(Project.name.ilike(like), Project.code.ilike(like)))
    if pids is not None:
        ps = ps.where(Project.id.in_(pids or [0]))
    for p in db.scalars(ps.limit(5)).unique():
        out.append({"type": "project", "id": p.id, "title": p.name, "subtitle": f"{p.code} · {p.status.replace('_', ' ')}",
                    "link": f"/projects/{p.id}"})
    if current.has_any("clients.view", "clients.manage"):
        cids = accessible_client_ids(db, current.user, current.perms)
        cs = select(Client).where(or_(Client.name.ilike(like), Client.company_name.ilike(like)))
        if cids is not None:
            cs = cs.where(Client.id.in_(cids or [0]))
        for c in db.scalars(cs.limit(5)).unique():
            out.append({"type": "client", "id": c.id, "title": c.name, "subtitle": c.company_name or c.industry,
                        "link": f"/clients/{c.id}"})
    ts = select(Task).where(Task.title.ilike(like))
    if not current.has("tasks.manage_all"):
        conds = [Task.assignee_id == current.employee_id, Task.reporter_id == current.employee_id]
        if pids is None:
            conds = []
        elif pids:
            conds.append(Task.project_id.in_(pids))
        if conds:
            ts = ts.where(or_(*conds))
    for t in db.scalars(ts.limit(5)).unique():
        out.append({"type": "task", "id": t.id, "title": t.title, "subtitle": t.project.name if t.project else "Personal task",
                    "link": f"/tasks/{t.id}"})
    return out


_ = ProjectMember
