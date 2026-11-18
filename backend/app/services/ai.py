"""Permission-scoped AI company assistant (Google Gemini with function calling).

The model never receives a data dump. It can only call the tool functions below, and every tool enforces the
signed-in user's permissions exactly like the REST API does. Tools return {"error": ...} when access is denied.
"""
import json
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.config import settings
from app.models import (
    Client, ClientCommunication, Department, EmailMessage, Employee, Expense, ExpenseCategory, Holiday, LeaveBalance,
    LeaveRequest, LeaveType, PayrollRun, Project, Task,
)
from app.services.attendance import range_summary
from app.services.authz import accessible_client_ids, accessible_project_ids
from app.services.common import get_company, today_local
from app.services.work import serialize_project

DENIED = {"error": "The current user is not authorized to access this information."}


def _d(s: str | None, default: date) -> date:
    try:
        return date.fromisoformat(s) if s else default
    except ValueError:
        return default


def build_tools(db: Session, current: CurrentUser) -> list:
    today = today_local(db)

    def get_today_and_company_info() -> dict:
        """Get today's date, company name, working hours, leave types and upcoming holidays."""
        cs = get_company(db)
        return {"today": str(today), "company": cs.company_name, "work_start": cs.work_start.strftime("%H:%M"),
                "work_end": cs.work_end.strftime("%H:%M"), "grace_minutes": cs.grace_minutes,
                "leave_types": [{"name": t.name, "annual_quota": t.annual_quota, "paid": t.is_paid}
                                for t in db.scalars(select(LeaveType).where(LeaveType.is_active.is_(True)))],
                "upcoming_holidays": [{"date": str(h.date), "name": h.name} for h in db.scalars(
                    select(Holiday).where(Holiday.date >= today).order_by(Holiday.date).limit(8))]}

    def get_my_summary() -> dict:
        """Get the current user's own profile, leave balances, pending leave and open tasks."""
        if not current.employee_id:
            return {"error": "User has no employee profile"}
        e = db.get(Employee, current.employee_id)
        bals = db.scalars(select(LeaveBalance).where(LeaveBalance.employee_id == e.id, LeaveBalance.year == today.year)).all()
        tasks = db.scalars(select(Task).where(Task.assignee_id == e.id, Task.status != "done")
                           .order_by(Task.due_date).limit(20)).unique().all()
        return {"name": e.full_name, "designation": e.designation.title if e.designation else None,
                "department": e.department.name if e.department else None, "joining_date": str(e.joining_date),
                "leave_balances": [{"type": b.leave_type.name, "available": b.available} for b in bals],
                "pending_leave_requests": db.scalar(select(func.count()).select_from(LeaveRequest).where(
                    LeaveRequest.employee_id == e.id, LeaveRequest.status == "pending")),
                "open_tasks": [{"title": t.title, "project": t.project.name if t.project else None, "status": t.status,
                                "due": str(t.due_date) if t.due_date else None,
                                "overdue": bool(t.due_date and t.due_date < today)} for t in tasks]}

    def get_attendance_summary(start_date: str = "", end_date: str = "", employee_name: str = "",
                               department: str = "") -> dict:
        """Attendance summary (present, late, absent, leave, hours) per employee for a date range (YYYY-MM-DD).
        Without the attendance.view_all permission only the user's own attendance is returned."""
        end = _d(end_date, today)
        start = _d(start_date, end.replace(day=1))
        if (end - start).days > 366:
            return {"error": "Range too large; use at most one year"}
        if current.has("attendance.view_all"):
            stmt = select(Employee.id)
            if employee_name:
                like = f"%{employee_name}%"
                stmt = stmt.where(or_(Employee.first_name.ilike(like), Employee.last_name.ilike(like),
                                      func.concat(Employee.first_name, " ", Employee.last_name).ilike(like)))
            if department:
                stmt = stmt.join(Department, Department.id == Employee.department_id).where(Department.name.ilike(f"%{department}%"))
            ids = list(db.scalars(stmt)) if (employee_name or department) else None
        else:
            if not current.employee_id:
                return DENIED
            ids = [current.employee_id]
        rows = range_summary(db, ids, start, end)
        return {"from": str(start), "to": str(end), "employees": [
            {k: v for k, v in r.items() if k != "employee"} | {"name": r["employee"]["full_name"],
                                                              "department": r["employee"]["department"]} for r in rows[:60]]}

    def get_todays_attendance() -> dict:
        """Company-wide attendance status for today (who is in, late, on leave, not checked in)."""
        if not current.has("attendance.view_all"):
            return DENIED
        from app.api.routes.attendance import live_board
        board = live_board(current, db)
        return {"date": str(board["date"]), "counts": board["counts"], "people": [
            {"name": r["employee"]["full_name"], "state": r["state"],
             "check_in": r["record"]["check_in_local"] if r["record"] else None,
             "late_minutes": r["record"]["late_minutes"] if r["record"] else 0} for r in board["rows"]]}

    def list_projects(status: str = "", delayed_only: bool = False) -> dict:
        """List projects the user can access with status, progress, dates, manager and task counts.
        status may be planning, active, on_hold, completed or cancelled."""
        stmt = select(Project)
        ids = accessible_project_ids(db, current.user, current.perms)
        if ids is not None:
            stmt = stmt.where(Project.id.in_(ids or [0]))
        if status:
            stmt = stmt.where(Project.status == status)
        out = [serialize_project(db, p) for p in db.scalars(stmt.limit(100)).unique()]
        if delayed_only:
            out = [p for p in out if p["is_delayed"] or p["overdue_tasks"]]
        return {"projects": [{"name": p["name"], "code": p["code"], "status": p["status"], "progress": p["progress"],
                              "start": str(p["start_date"]), "end": str(p["end_date"]), "is_delayed": p["is_delayed"],
                              "overdue_tasks": p["overdue_tasks"], "open_tasks": p["task_total"] - p["task_counts"].get("done", 0),
                              "client": p["client"]["name"] if p["client"] else None,
                              "manager": p["manager"]["full_name"] if p["manager"] else None} for p in out]}

    def get_project_details(project: str) -> dict:
        """Detailed progress of one project (by name or code): milestones, task breakdown, overdue tasks, team."""
        ids = accessible_project_ids(db, current.user, current.perms)
        stmt = select(Project).where(or_(Project.name.ilike(f"%{project}%"), Project.code.ilike(f"%{project}%")))
        if ids is not None:
            stmt = stmt.where(Project.id.in_(ids or [0]))
        p = db.scalars(stmt.limit(1)).first()
        if not p:
            return {"error": "No accessible project matches that name"}
        from app.models import Milestone
        tasks = db.scalars(select(Task).where(Task.project_id == p.id)).unique().all()
        return {"project": serialize_project(db, p, detail=True) | {"members": [m.employee.full_name for m in p.members]},
                "milestones": [{"title": m.title, "due": str(m.due_date), "status": m.status}
                               for m in db.scalars(select(Milestone).where(Milestone.project_id == p.id))],
                "overdue_tasks": [{"title": t.title, "assignee": t.assignee.full_name if t.assignee else None,
                                   "due": str(t.due_date)} for t in tasks if t.due_date and t.due_date < today and t.status != "done"],
                "blocked_tasks": [t.title for t in tasks if t.status == "blocked"]}

    def get_client_communications(client: str, days: int = 30) -> dict:
        """Recent communication history (calls, meetings, notes, linked emails) with a client the user may access."""
        cids = accessible_client_ids(db, current.user, current.perms)
        if cids is not None and not cids:
            return DENIED
        stmt = select(Client).where(or_(Client.name.ilike(f"%{client}%"), Client.company_name.ilike(f"%{client}%")))
        if cids is not None:
            stmt = stmt.where(Client.id.in_(cids))
        c = db.scalars(stmt.limit(1)).first()
        if not c:
            return {"error": "No accessible client matches that name"}
        since = today - timedelta(days=min(max(days, 1), 365))
        comms = db.scalars(select(ClientCommunication).where(ClientCommunication.client_id == c.id,
                                                             func.date(ClientCommunication.occurred_at) >= since)
                           .order_by(ClientCommunication.occurred_at.desc()).limit(40)).unique().all()
        from app.services.email_sync import visible_accounts_filter
        emails = db.scalars(select(EmailMessage).where(EmailMessage.client_id == c.id, visible_accounts_filter(db, current),
                                                       func.date(EmailMessage.sent_at) >= since)
                            .order_by(EmailMessage.sent_at.desc()).limit(25)).unique().all()
        return {"client": c.name, "status": c.status,
                "interactions": [{"date": str(x.occurred_at.date()), "channel": x.channel, "subject": x.subject,
                                  "summary": (x.summary or "")[:500]} for x in comms if not x.email_message_id],
                "emails": [{"date": str(m.sent_at.date()), "direction": m.direction, "subject": m.subject,
                            "from": m.from_address, "excerpt": (m.body_text or m.snippet or "")[:800]} for m in emails]}

    def get_workforce_overview() -> dict:
        """Headcount by department and status, recent joiners and exits."""
        if not current.has("employees.view_all"):
            return DENIED
        rows = db.execute(select(Department.name, Employee.status, func.count()).select_from(Employee)
                          .outerjoin(Department, Department.id == Employee.department_id)
                          .group_by(Department.name, Employee.status)).all()
        since = today - timedelta(days=90)
        return {"by_department": [{"department": d or "Unassigned", "status": s, "count": n} for d, s, n in rows],
                "joined_last_90_days": [e.full_name for e in db.scalars(select(Employee).where(Employee.joining_date >= since)).unique()],
                "exited_last_90_days": [e.full_name for e in db.scalars(select(Employee).where(Employee.exit_date >= since)).unique()]}

    def get_leave_overview(start_date: str = "", end_date: str = "") -> dict:
        """Approved and pending leave across the company for a date range (HR permission required)."""
        if not current.has("leave.view_all"):
            return DENIED
        end = _d(end_date, today + timedelta(days=30))
        start = _d(start_date, today)
        rows = db.scalars(select(LeaveRequest).where(LeaveRequest.start_date <= end, LeaveRequest.end_date >= start,
                                                     LeaveRequest.status.in_(["approved", "pending"]))).unique().all()
        return {"from": str(start), "to": str(end), "leave": [
            {"employee": r.employee.full_name, "type": r.leave_type.name, "from": str(r.start_date), "to": str(r.end_date),
             "days": r.days, "status": r.status} for r in rows]}

    def get_payroll_summary(year: int = 0) -> dict:
        """Monthly payroll totals (gross, deductions, net) for a year. Requires payroll permission."""
        if not current.has("payroll.view"):
            return DENIED
        y = year or today.year
        return {"year": y, "months": [{"month": r.month, "status": r.status, "gross": float(r.total_gross),
                                       "deductions": float(r.total_deductions), "net": float(r.total_net),
                                       "employees": len(r.payslips)}
                                      for r in db.scalars(select(PayrollRun).where(PayrollRun.year == y).order_by(PayrollRun.month))]}

    def get_expense_summary(year: int = 0) -> dict:
        """Company expense totals by category and status for a year. Requires expense permission."""
        if not current.has("expenses.view_all"):
            return DENIED
        y = year or today.year
        rows = db.execute(select(ExpenseCategory.name, Expense.status, func.sum(Expense.amount), func.count())
                          .join(Expense).where(func.year(Expense.expense_date) == y)
                          .group_by(ExpenseCategory.name, Expense.status)).all()
        return {"year": y, "rows": [{"category": c, "status": s, "amount": float(a), "count": n} for c, s, a, n in rows]}

    return [get_today_and_company_info, get_my_summary, get_attendance_summary, get_todays_attendance, list_projects,
            get_project_details, get_client_communications, get_workforce_overview, get_leave_overview,
            get_payroll_summary, get_expense_summary]


SYSTEM = """You are the ECHOUTRA ONE assistant for {company}, helping {name} ({role}).
Today is {today}.
Rules:
- Answer ONLY from data returned by the provided tools. Call tools whenever the question needs company data.
- If a tool returns an "error" about authorization, tell the user they don't have access to that information.
  Never guess, infer or reveal confidential data (salaries, personal details, other people's records) that tools did not return.
- Be concise and professional. Use short paragraphs, bullet points and small markdown tables when helpful.
- When summarising, highlight risks (delays, overdue work, absences) and suggest practical next steps.
- Dates are in the company's local time zone. Format money in INR unless stated otherwise."""


def ai_configured() -> bool:
    return bool(settings.GEMINI_API_KEY)


def chat(db: Session, current: CurrentUser, history: list[dict], message: str) -> str:
    if not ai_configured():
        raise HTTPException(503, "The AI assistant is not configured. Add GEMINI_API_KEY to backend/.env.")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    emp = current.user.employee
    system = SYSTEM.format(company=get_company(db).company_name, name=emp.full_name if emp else current.user.email,
                           role=current.user.role.name, today=today_local(db).isoformat())
    contents = [types.Content(role=h["role"], parts=[types.Part(text=h["content"])]) for h in history[-12:]]
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    try:
        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system, tools=build_tools(db, current), temperature=0.3,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=8)),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI service error: {str(exc)[:200]}")
    return (resp.text or "I couldn't generate an answer for that. Please rephrase your question.").strip()


def tool_preview(db: Session, current: CurrentUser, name: str, **kwargs) -> str:
    """Run one tool directly (used for deterministic insight cards & tests)."""
    tools = {f.__name__: f for f in build_tools(db, current)}
    return json.dumps(tools[name](**kwargs), default=str)
