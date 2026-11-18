"""Payroll calculation from configurable rules.

No statutory rule (PF, ESI, professional tax, TDS) is assumed. HR configures every component explicitly as
fixed amount, % of basic, or % of gross. Attendance drives paid days:
  LOP days = absent working days + approved unpaid (non-paid leave type) days + 0.5 × half days
  proration = paid_days / working_days
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord, Employee, LeaveRequest, PayrollAdjustment, PayrollRun, Payslip, SalaryStructure,
)
from app.services.attendance import month_bounds, working_days_in_range
from app.services.common import today_local


def r2(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def active_structure(db: Session, employee_id: int, on: date) -> SalaryStructure | None:
    return db.scalar(select(SalaryStructure).where(SalaryStructure.employee_id == employee_id,
                                                   SalaryStructure.effective_from <= on)
                     .order_by(SalaryStructure.effective_from.desc(), SalaryStructure.id.desc()).limit(1))


def attendance_days(db: Session, emp: Employee, start: date, end: date) -> dict:
    eff_start = max(start, emp.joining_date)
    eff_end = min(end, emp.exit_date) if emp.exit_date else end
    wdays = working_days_in_range(db, eff_start, eff_end) if eff_end >= eff_start else []
    cutoff = min(eff_end, today_local(db) - timedelta(days=1))  # future days are presumed present
    recs = {r.work_date: r for r in db.scalars(select(AttendanceRecord).where(
        AttendanceRecord.employee_id == emp.id, AttendanceRecord.work_date.between(start, end))).unique()}
    leaves = db.scalars(select(LeaveRequest).where(
        LeaveRequest.employee_id == emp.id, LeaveRequest.status == "approved",
        and_(LeaveRequest.start_date <= end, LeaveRequest.end_date >= start))).all()
    paid_leave, unpaid_leave = {}, {}
    for lr in leaves:
        d = max(lr.start_date, start)
        while d <= min(lr.end_date, end):
            (paid_leave if lr.leave_type.is_paid else unpaid_leave)[d] = 0.5 if lr.half_day else 1.0
            d += timedelta(days=1)
    absent = half = unpaid = 0.0
    for d in wdays:
        if d in unpaid_leave:
            unpaid += unpaid_leave[d]
            continue
        if d in paid_leave:
            continue
        r = recs.get(d)
        if d > cutoff:
            continue
        if not r or (not r.check_in_at and r.status != "on_leave"):
            absent += 1
        elif r.status == "half_day":
            half += 1
    lop = absent + unpaid + 0.5 * half
    total_month_days = len(working_days_in_range(db, start, end))
    return {"working_days": float(total_month_days), "employed_days": float(len(wdays)),
            "lop_days": round(lop, 2), "absent": absent, "unpaid_leave": unpaid, "half_days": half}


def compute_payslip(db: Session, emp: Employee, year: int, month: int) -> dict | None:
    start, end = month_bounds(year, month)
    st = active_structure(db, emp.id, end)
    if not st:
        return None
    att = attendance_days(db, emp, start, end)
    wd = att["working_days"] or 1
    paid_days = max(att["employed_days"] - att["lop_days"], 0)
    factor = Decimal(str(paid_days / wd))
    basic_full = Decimal(str(st.monthly_basic))
    basic = r2(basic_full * factor)
    earnings = [{"code": "BASIC", "name": "Basic salary", "amount": float(basic)}]
    deductions = []
    pct_gross = []
    for item in st.items:
        c = item.component
        if not c.is_active:
            continue
        val = Decimal(str(item.value))
        if c.calc_type == "percent_gross":
            pct_gross.append((c, val))
            continue
        amount = basic_full * val / 100 if c.calc_type == "percent_basic" else val
        if c.prorate_with_attendance:
            amount *= factor
        row = {"code": c.code, "name": c.name, "amount": float(r2(amount))}
        (earnings if c.kind == "earning" else deductions).append(row)
    gross = r2(sum(Decimal(str(e["amount"])) for e in earnings))
    for c, val in pct_gross:
        row = {"code": c.code, "name": c.name, "amount": float(r2(gross * val / 100))}
        (earnings if c.kind == "earning" else deductions).append(row)
    gross = r2(sum(Decimal(str(e["amount"])) for e in earnings))
    adjs = db.scalars(select(PayrollAdjustment).where(PayrollAdjustment.employee_id == emp.id,
                                                      PayrollAdjustment.year == year, PayrollAdjustment.month == month)).all()
    bonus = r2(sum(Decimal(str(a.amount)) for a in adjs if a.kind == "bonus"))
    for a in adjs:
        if a.kind == "deduction":
            deductions.append({"code": "ADJ", "name": a.label, "amount": float(r2(a.amount))})
    bonuses = [{"code": "BONUS", "name": a.label, "amount": float(r2(a.amount))} for a in adjs if a.kind == "bonus"]
    total_ded = r2(sum(Decimal(str(d["amount"])) for d in deductions))
    net = r2(gross + bonus - total_ded)
    if net < 0:
        net = Decimal("0.00")
    return {"working_days": wd, "paid_days": round(paid_days, 2), "lop_days": att["lop_days"],
            "monthly_basic": basic_full, "gross_earnings": gross, "total_deductions": total_ded, "bonus": bonus,
            "net_pay": net, "breakdown": {"earnings": earnings + bonuses, "deductions": deductions, "attendance": att}}


def process_run(db: Session, run: PayrollRun) -> dict:
    if run.status != "draft":
        raise HTTPException(409, "Only draft payroll runs can be recalculated")
    start, end = month_bounds(run.year, run.month)
    emps = db.scalars(select(Employee).where(Employee.joining_date <= end)).unique().all()
    emps = [e for e in emps if not (e.exit_date and e.exit_date < start) and not (e.status == "inactive" and not e.exit_date)]
    existing = {p.employee_id: p for p in run.payslips}
    skipped = []
    seen = set()
    for e in emps:
        calc = compute_payslip(db, e, run.year, run.month)
        if not calc:
            skipped.append({"id": e.id, "full_name": e.full_name, "employee_code": e.employee_code,
                            "reason": "No salary structure"})
            continue
        seen.add(e.id)
        p = existing.get(e.id) or Payslip(run_id=run.id, employee_id=e.id)
        for k, v in calc.items():
            setattr(p, k, v)
        if p.id is None:
            run.payslips.append(p)
    for eid, p in existing.items():
        if eid not in seen:
            run.payslips.remove(p)
    db.flush()
    run.working_days = len(working_days_in_range(db, start, end))
    run.total_gross = sum((Decimal(str(p.gross_earnings)) + Decimal(str(p.bonus)) for p in run.payslips), Decimal(0))
    run.total_deductions = sum((Decimal(str(p.total_deductions)) for p in run.payslips), Decimal(0))
    run.total_net = sum((Decimal(str(p.net_pay)) for p in run.payslips), Decimal(0))
    return {"skipped": skipped}
