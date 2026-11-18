import calendar
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current
from app.db.session import get_db
from app.models import (
    Candidate, Client, ClientCommunication, ClientFeedback, Employee, Expense, LeaveRequest, PayrollRun, Payslip,
    Project, Task,
)
from app.services.attendance import range_summary
from app.services.authz import accessible_client_ids, accessible_project_ids
from app.services.common import audit, get_company, today_local
from app.services.pdf import table_report_pdf

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORTS = {
    "attendance": ("Attendance summary", ["reports.hr"]),
    "employees": ("Employee register", ["reports.hr"]),
    "leave": ("Leave report", ["reports.hr"]),
    "recruitment": ("Recruitment pipeline", ["reports.hr"]),
    "projects": ("Project status", ["reports.view"]),
    "tasks": ("Task report", ["reports.view"]),
    "clients": ("Client report", ["reports.view", "clients.view"]),
    "payroll": ("Payroll register", ["reports.finance"]),
    "expenses": ("Expense report", ["reports.finance"]),
}


@router.get("")
def available(current: CurrentUser = Depends(get_current)):
    return [{"key": k, "title": t} for k, (t, perms) in REPORTS.items() if current.has(*perms)]


def _build(db: Session, current: CurrentUser, kind: str, start: date, end: date, department_id: int | None,
           status: str | None) -> dict:
    today = today_local(db)
    if kind == "attendance":
        ids = list(db.scalars(select(Employee.id).where(Employee.department_id == department_id))) if department_id else None
        rows = range_summary(db, ids, start, end)
        cols = ["Employee", "Code", "Department", "Working days", "Present", "Half days", "Late", "Early exits",
                "Leave", "Absent", "Hours", "Avg hrs/day"]
        data = [[r["employee"]["full_name"], r["employee"]["employee_code"], r["employee"]["department"] or "—",
                 r["working_days"], r["present"], r["half_days"], r["late"], r["early_departures"], r["leave_days"],
                 r["absent"], r["worked_hours"], r["avg_hours"]] for r in rows]
        tot_wd = sum(r["working_days"] for r in rows) or 1
        summary = [("Employees", len(rows)), ("Attendance rate", f"{sum(r['present'] + r['half_days'] for r in rows) / tot_wd * 100:.1f}%"),
                   ("Late arrivals", sum(r["late"] for r in rows)), ("Absences", sum(r["absent"] for r in rows))]
        chart = [{"label": r["employee"]["full_name"], "value": r["present"]} for r in rows[:20]]
    elif kind == "employees":
        stmt = select(Employee).order_by(Employee.employee_code)
        if department_id:
            stmt = stmt.where(Employee.department_id == department_id)
        if status:
            stmt = stmt.where(Employee.status == status)
        emps = db.scalars(stmt).unique().all()
        cols = ["Code", "Name", "Email", "Department", "Designation", "Type", "Joined", "Status", "Exit date"]
        data = [[e.employee_code, e.full_name, e.email, e.department.name if e.department else "—",
                 e.designation.title if e.designation else "—", e.employment_type.replace("_", " "), str(e.joining_date),
                 e.status.replace("_", " "), str(e.exit_date or "—")] for e in emps]
        joined = sum(1 for e in emps if start <= e.joining_date <= end)
        left = sum(1 for e in emps if e.exit_date and start <= e.exit_date <= end)
        summary = [("Employees", len(emps)), ("Active", sum(1 for e in emps if e.status == "active")),
                   ("Joined in period", joined), ("Exited in period", left)]
        by_dept = {}
        for e in emps:
            k = e.department.name if e.department else "Unassigned"
            by_dept[k] = by_dept.get(k, 0) + 1
        chart = [{"label": k, "value": v} for k, v in by_dept.items()]
    elif kind == "leave":
        stmt = select(LeaveRequest).where(LeaveRequest.start_date <= end, LeaveRequest.end_date >= start).order_by(LeaveRequest.start_date)
        if status:
            stmt = stmt.where(LeaveRequest.status == status)
        if department_id:
            stmt = stmt.join(Employee, Employee.id == LeaveRequest.employee_id).where(Employee.department_id == department_id)
        rows = db.scalars(stmt).unique().all()
        cols = ["Employee", "Leave type", "From", "To", "Days", "Status", "Reason"]
        data = [[r.employee.full_name, r.leave_type.name, str(r.start_date), str(r.end_date), r.days, r.status, r.reason[:80]] for r in rows]
        by_type = {}
        for r in rows:
            if r.status == "approved":
                by_type[r.leave_type.name] = by_type.get(r.leave_type.name, 0) + r.days
        summary = [("Requests", len(rows)), ("Approved days", sum(by_type.values())),
                   ("Pending", sum(1 for r in rows if r.status == "pending")), ("Rejected", sum(1 for r in rows if r.status == "rejected"))]
        chart = [{"label": k, "value": v} for k, v in by_type.items()]
    elif kind == "recruitment":
        stmt = select(Candidate).where(func.date(Candidate.created_at).between(start, end)).order_by(Candidate.created_at)
        if status:
            stmt = stmt.where(Candidate.status == status)
        rows = db.scalars(stmt).unique().all()
        cols = ["Candidate", "Email", "Opening", "Source", "Experience", "Status", "Added"]
        data = [[c.full_name, c.email, c.job.title if c.job else "—", c.source or "—", c.experience_years or "—", c.status,
                 str(c.created_at.date())] for c in rows]
        by = {}
        for c in rows:
            by[c.status] = by.get(c.status, 0) + 1
        summary = [("Candidates", len(rows)), ("Interviewing", by.get("interview", 0)), ("Offered", by.get("offered", 0)),
                   ("Hired", by.get("hired", 0))]
        chart = [{"label": k, "value": v} for k, v in by.items()]
    elif kind == "projects":
        stmt = select(Project).order_by(Project.name)
        pids = accessible_project_ids(db, current.user, current.perms)
        if pids is not None:
            stmt = stmt.where(Project.id.in_(pids or [0]))
        stmt = stmt.where(or_(Project.start_date.is_(None), Project.start_date <= end),
                          or_(Project.end_date.is_(None), Project.end_date >= start))
        if status:
            stmt = stmt.where(Project.status == status)
        rows = db.scalars(stmt).unique().all()
        cols = ["Code", "Project", "Client", "Manager", "Start", "End", "Status", "Progress", "Open tasks", "Delayed"]
        data = []
        for p in rows:
            open_t = db.scalar(select(func.count()).select_from(Task).where(Task.project_id == p.id, Task.status != "done"))
            delayed = bool(p.end_date and p.end_date < today and p.status not in ("completed", "cancelled"))
            data.append([p.code, p.name, p.client.name if p.client else "Internal", p.manager.full_name if p.manager else "—",
                         str(p.start_date or "—"), str(p.end_date or "—"), p.status.replace("_", " "), f"{p.progress:.0f}%",
                         open_t, "Yes" if delayed else "No"])
        summary = [("Projects", len(rows)), ("Active", sum(1 for p in rows if p.status == "active")),
                   ("Completed", sum(1 for p in rows if p.status == "completed")), ("Delayed", sum(1 for r in data if r[-1] == "Yes"))]
        chart = [{"label": p.name, "value": round(p.progress)} for p in rows[:20]]
    elif kind == "tasks":
        stmt = select(Task).where(or_(Task.due_date.between(start, end), func.date(Task.created_at).between(start, end)))
        if not current.has("tasks.manage_all"):
            pids = accessible_project_ids(db, current.user, current.perms)
            if pids is not None:
                stmt = stmt.where(or_(Task.project_id.in_(pids or [0]), Task.assignee_id == current.employee_id))
        if status:
            stmt = stmt.where(Task.status == status)
        rows = db.scalars(stmt.order_by(Task.due_date)).unique().all()
        cols = ["Task", "Project", "Assignee", "Priority", "Status", "Due", "Overdue"]
        data = [[t.title, t.project.name if t.project else "Personal", t.assignee.full_name if t.assignee else "—", t.priority,
                 t.status.replace("_", " "), str(t.due_date or "—"),
                 "Yes" if t.due_date and t.due_date < today and t.status != "done" else "No"] for t in rows]
        by = {}
        for t in rows:
            by[t.status] = by.get(t.status, 0) + 1
        summary = [("Tasks", len(rows)), ("Completed", by.get("done", 0)), ("In progress", by.get("in_progress", 0)),
                   ("Overdue", sum(1 for r in data if r[-1] == "Yes"))]
        chart = [{"label": k.replace("_", " "), "value": v} for k, v in by.items()]
    elif kind == "clients":
        stmt = select(Client).order_by(Client.name)
        cids = accessible_client_ids(db, current.user, current.perms)
        if cids is not None:
            stmt = stmt.where(Client.id.in_(cids or [0]))
        if status:
            stmt = stmt.where(Client.status == status)
        rows = db.scalars(stmt).unique().all()
        cols = ["Client", "Industry", "Status", "Account manager", "Projects", "Active projects", "Interactions", "Avg rating"]
        data = []
        for c in rows:
            pc = db.scalar(select(func.count()).select_from(Project).where(Project.client_id == c.id))
            ac = db.scalar(select(func.count()).select_from(Project).where(Project.client_id == c.id, Project.status == "active"))
            comms = db.scalar(select(func.count()).select_from(ClientCommunication).where(
                ClientCommunication.client_id == c.id, func.date(ClientCommunication.occurred_at).between(start, end)))
            avg = db.scalar(select(func.avg(ClientFeedback.rating)).where(ClientFeedback.client_id == c.id))
            data.append([c.name, c.industry or "—", c.status, c.account_manager.full_name if c.account_manager else "—",
                         pc, ac, comms, f"{float(avg):.1f}" if avg else "—"])
        summary = [("Clients", len(rows)), ("Active", sum(1 for c in rows if c.status == "active")),
                   ("Leads", sum(1 for c in rows if c.status == "lead")), ("Interactions", sum(r[6] for r in data))]
        chart = [{"label": r[0], "value": r[6]} for r in data[:20]]
    elif kind == "payroll":
        months = []
        d = start.replace(day=1)
        while d <= end:
            months.append((d.year, d.month))
            d = (d + timedelta(days=32)).replace(day=1)
        runs = [r for r in db.scalars(select(PayrollRun)) if (r.year, r.month) in months and r.status != "draft"]
        cols = ["Period", "Employee", "Code", "Paid days", "LOP", "Gross", "Bonus", "Deductions", "Net pay", "Payment"]
        data = []
        for r in sorted(runs, key=lambda x: (x.year, x.month)):
            for p in db.scalars(select(Payslip).where(Payslip.run_id == r.id)).unique():
                data.append([f"{calendar.month_abbr[r.month]} {r.year}", p.employee.full_name, p.employee.employee_code,
                             p.paid_days, p.lop_days, float(p.gross_earnings), float(p.bonus), float(p.total_deductions),
                             float(p.net_pay), p.payment_status])
        summary = [("Payslips", len(data)), ("Gross", f"{sum(r[5] + r[6] for r in data):,.2f}"),
                   ("Deductions", f"{sum(r[7] for r in data):,.2f}"), ("Net pay", f"{sum(r[8] for r in data):,.2f}")]
        chart = [{"label": f"{calendar.month_abbr[r.month]} {r.year}", "value": float(r.total_net)} for r in sorted(runs, key=lambda x: (x.year, x.month))]
    elif kind == "expenses":
        stmt = select(Expense).where(Expense.expense_date.between(start, end)).order_by(Expense.expense_date)
        if status:
            stmt = stmt.where(Expense.status == status)
        if department_id:
            stmt = stmt.join(Employee, Employee.id == Expense.employee_id).where(Employee.department_id == department_id)
        rows = db.scalars(stmt).unique().all()
        cols = ["Date", "Employee", "Category", "Title", "Project", "Amount", "Status"]
        data = [[str(e.expense_date), e.employee.full_name, e.category.name, e.title, e.project.name if e.project else "—",
                 float(e.amount), e.status] for e in rows]
        by = {}
        for e in rows:
            if e.status in ("approved", "reimbursed"):
                by[e.category.name] = by.get(e.category.name, 0) + float(e.amount)
        summary = [("Claims", len(rows)), ("Approved total", f"{sum(by.values()):,.2f}"),
                   ("Pending", sum(1 for e in rows if e.status == "submitted")),
                   ("Reimbursed", sum(1 for e in rows if e.status == "reimbursed"))]
        chart = [{"label": k, "value": round(v, 2)} for k, v in by.items()]
    else:
        raise HTTPException(404, "Unknown report")
    return {"title": REPORTS[kind][0], "columns": cols, "rows": data, "summary": summary, "chart": chart,
            "period": {"from": start, "to": end}}


def _xlsx(report: dict, company: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = report["title"][:30]
    ws["A1"] = f"{company} — {report['title']}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Period: {report['period']['from']} to {report['period']['to']}"
    ws["A2"].font = Font(color="62707A")
    r = 4
    for k, v in report["summary"]:
        ws.cell(r, 1, k).font = Font(color="62707A")
        ws.cell(r, 2, v).font = Font(bold=True)
        r += 1
    r += 1
    fill = PatternFill("solid", fgColor="050B0F")
    for i, c in enumerate(report["columns"], 1):
        cell = ws.cell(r, i, c)
        cell.font, cell.fill, cell.alignment = Font(bold=True, color="FFFFFF"), fill, Alignment(vertical="center")
    for row in report["rows"]:
        r += 1
        for i, v in enumerate(row, 1):
            ws.cell(r, i, v)
    for i, c in enumerate(report["columns"], 1):
        width = max([len(str(c))] + [len(str(row[i - 1])) for row in report["rows"][:500]]) + 2
        ws.column_dimensions[get_column_letter(i)].width = min(width, 45)
    ws.freeze_panes = ws.cell(r - len(report["rows"]) + 1, 1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/{kind}")
def run_report(kind: str, date_from: date | None = None, date_to: date | None = None, department_id: int | None = None,
               status: str | None = None, format: str = "json", current: CurrentUser = Depends(get_current),
               db: Session = Depends(get_db)):
    if kind not in REPORTS:
        raise HTTPException(404, "Unknown report")
    current.require(*REPORTS[kind][1])
    end = date_to or today_local(db)
    start = date_from or end.replace(day=1)
    if start > end:
        raise HTTPException(422, "Start date must be before end date")
    if (end - start).days > 731:
        raise HTTPException(422, "Date range cannot exceed two years")
    report = _build(db, current, kind, start, end, department_id, status)
    if format == "json":
        return report
    cs = get_company(db)
    fname = f"{kind}-report-{start}-to-{end}"
    audit(db, current.user, "report.export", "report", None, f"Exported {kind} report ({format})",
          {"from": str(start), "to": str(end)})
    db.commit()
    if format == "xlsx":
        return Response(_xlsx(report, cs.company_name),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.xlsx"'})
    if format == "pdf":
        pdf = table_report_pdf({"company_name": cs.company_name, "legal_name": cs.legal_name, "email": cs.email,
                                "phone": cs.phone, "website": cs.website, "address": cs.address},
                               report["title"], f"{start:%d %b %Y} – {end:%d %b %Y}", report["columns"],
                               [[str(c) for c in row] for row in report["rows"]],
                               [(k, str(v)) for k, v in report["summary"]])
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'})
    raise HTTPException(422, "format must be json, xlsx or pdf")
