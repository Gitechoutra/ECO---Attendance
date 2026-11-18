from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, get_current, require, require_employee
from app.db.base import utcnow
from app.db.session import get_db
from app.models import Employee, Holiday, LeaveBalance, LeaveRequest, LeaveType
from app.schemas.attendance import BalanceAdjustIn, HolidayIn, LeaveApplyIn, LeaveTypeIn, ReviewIn
from app.services.attendance import working_days_in_range
from app.services.common import (
    audit, get_or_404, notify, paginate, today_local, user_ids_for_employees, user_ids_with_permission,
)
from app.services.employees import allocate_leave_balances

router = APIRouter(tags=["Leave"])


def _lt(t: LeaveType) -> dict:
    return {k: getattr(t, k) for k in ("id", "name", "code", "annual_quota", "is_paid", "carry_forward",
                                         "max_carry_forward", "color", "description", "is_active")}


def _bal(b: LeaveBalance) -> dict:
    return {"id": b.id, "employee_id": b.employee_id, "year": b.year, "leave_type": _lt(b.leave_type),
            "allocated": b.allocated, "carried": b.carried, "used": b.used, "available": b.available}


def _req(r: LeaveRequest) -> dict:
    return {"id": r.id, "employee": {"id": r.employee.id, "full_name": r.employee.full_name,
                                     "employee_code": r.employee.employee_code, "photo_file_id": r.employee.photo_file_id,
                                     "department": r.employee.department.name if r.employee.department else None},
            "leave_type": {"id": r.leave_type.id, "name": r.leave_type.name, "code": r.leave_type.code,
                           "color": r.leave_type.color},
            "start_date": r.start_date, "end_date": r.end_date, "half_day": r.half_day, "days": r.days,
            "reason": r.reason, "status": r.status, "review_note": r.review_note, "reviewed_at": r.reviewed_at,
            "reviewed_by": r.reviewed_by.email if r.reviewed_by else None, "created_at": r.created_at}


# ------------------------------------------------------------------ leave types

@router.get("/leave/types")
def leave_types(current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    return [_lt(t) for t in db.scalars(select(LeaveType).order_by(LeaveType.id))]


@router.post("/leave/types", status_code=201)
def create_type(body: LeaveTypeIn, current: CurrentUser = Depends(require("leave.configure")), db: Session = Depends(get_db)):
    if db.scalar(select(LeaveType.id).where((func.lower(LeaveType.name) == body.name.lower()) |
                                            (func.lower(LeaveType.code) == body.code.lower()))):
        raise HTTPException(409, "Leave type with this name or code exists")
    t = LeaveType(**body.model_dump())
    t.code = t.code.upper()
    db.add(t)
    db.flush()
    audit(db, current.user, "leave_type.create", "leave_type", t.id, f"Created leave type {t.name}")
    db.commit()
    return _lt(t)


@router.put("/leave/types/{tid}")
def update_type(tid: int, body: LeaveTypeIn, current: CurrentUser = Depends(require("leave.configure")),
                db: Session = Depends(get_db)):
    t = get_or_404(db, LeaveType, tid, "Leave type")
    if db.scalar(select(LeaveType.id).where(LeaveType.id != tid, (func.lower(LeaveType.name) == body.name.lower()) |
                                            (func.lower(LeaveType.code) == body.code.lower()))):
        raise HTTPException(409, "Leave type with this name or code exists")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    t.code = t.code.upper()
    audit(db, current.user, "leave_type.update", "leave_type", t.id, f"Updated leave type {t.name}")
    db.commit()
    return _lt(t)


# ------------------------------------------------------------------ balances

@router.get("/leave/balances/me")
def my_balances(year: int | None = None, current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    year = year or today_local(db).year
    emp = db.get(Employee, current.employee_id)
    allocate_leave_balances(db, emp, year)
    db.commit()
    return [_bal(b) for b in db.scalars(select(LeaveBalance).where(LeaveBalance.employee_id == emp.id,
                                                                   LeaveBalance.year == year))]


@router.get("/leave/balances")
def balances(year: int | None = None, employee_id: int | None = None,
             current: CurrentUser = Depends(require("leave.view_all")), db: Session = Depends(get_db)):
    year = year or today_local(db).year
    emps = db.scalars(select(Employee).where(Employee.status != "inactive") if not employee_id
                      else select(Employee).where(Employee.id == employee_id)).unique().all()
    for e in emps:
        allocate_leave_balances(db, e, year)
    db.commit()
    rows = db.scalars(select(LeaveBalance).where(LeaveBalance.year == year,
                                                 LeaveBalance.employee_id.in_([e.id for e in emps]))).all()
    by_emp = {}
    for b in rows:
        by_emp.setdefault(b.employee_id, []).append(_bal(b))
    return [{"employee": {"id": e.id, "full_name": e.full_name, "employee_code": e.employee_code},
             "balances": by_emp.get(e.id, [])} for e in emps]


@router.put("/leave/balances")
def adjust_balance(body: BalanceAdjustIn, current: CurrentUser = Depends(require("leave.configure")),
                   db: Session = Depends(get_db)):
    get_or_404(db, Employee, body.employee_id, "Employee")
    get_or_404(db, LeaveType, body.leave_type_id, "Leave type")
    b = db.scalar(select(LeaveBalance).where(LeaveBalance.employee_id == body.employee_id,
                                             LeaveBalance.leave_type_id == body.leave_type_id,
                                             LeaveBalance.year == body.year))
    if not b:
        b = LeaveBalance(employee_id=body.employee_id, leave_type_id=body.leave_type_id, year=body.year, used=0)
        db.add(b)
    old = (b.allocated, b.carried)
    b.allocated, b.carried = body.allocated, body.carried
    db.flush()
    db.refresh(b)
    audit(db, current.user, "leave_balance.adjust", "employee", body.employee_id,
          f"Leave balance adjusted {old} → {(body.allocated, body.carried)}", body.model_dump())
    db.commit()
    return _bal(b)


# ------------------------------------------------------------------ requests

def _count_days(db: Session, body: LeaveApplyIn) -> float:
    if body.half_day:
        return 0.5
    return float(len(working_days_in_range(db, body.start_date, body.end_date)))


@router.post("/leave/requests", status_code=201)
def apply_leave(body: LeaveApplyIn, current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    emp = db.get(Employee, current.employee_id)
    lt = get_or_404(db, LeaveType, body.leave_type_id, "Leave type")
    if not lt.is_active:
        raise HTTPException(422, "This leave type is not active")
    if body.start_date < emp.joining_date:
        raise HTTPException(422, "Leave cannot start before your joining date")
    days = _count_days(db, body)
    if days <= 0:
        raise HTTPException(422, "Selected dates contain no working days")
    overlap = db.scalar(select(LeaveRequest.id).where(
        LeaveRequest.employee_id == emp.id, LeaveRequest.status.in_(["pending", "approved"]),
        and_(LeaveRequest.start_date <= body.end_date, LeaveRequest.end_date >= body.start_date)))
    if overlap:
        raise HTTPException(409, "You already have a leave request overlapping these dates")
    if lt.is_paid:
        if body.start_date.year != body.end_date.year:
            raise HTTPException(422, "Please split leave that spans two calendar years")
        allocate_leave_balances(db, emp, body.start_date.year)
        db.flush()
        bal = db.scalar(select(LeaveBalance).where(LeaveBalance.employee_id == emp.id, LeaveBalance.leave_type_id == lt.id,
                                                   LeaveBalance.year == body.start_date.year))
        pending = db.scalar(select(func.coalesce(func.sum(LeaveRequest.days), 0)).where(
            LeaveRequest.employee_id == emp.id, LeaveRequest.leave_type_id == lt.id, LeaveRequest.status == "pending",
            func.year(LeaveRequest.start_date) == body.start_date.year)) or 0
        available = (bal.available if bal else 0) - float(pending)
        if days > available:
            raise HTTPException(422, f"Insufficient {lt.name} balance: {available:g} day(s) available "
                                     f"(including pending requests), {days:g} requested")
    r = LeaveRequest(employee_id=emp.id, leave_type_id=lt.id, start_date=body.start_date, end_date=body.end_date,
                     half_day=body.half_day, days=days, reason=body.reason, approver_id=emp.manager_id)
    db.add(r)
    db.flush()
    approvers = set(user_ids_with_permission(db, "leave.approve"))
    if emp.manager_id:
        approvers |= set(user_ids_for_employees(db, [emp.manager_id]))
    approvers.discard(current.id)
    notify(db, approvers, "New leave request",
           f"{emp.full_name} applied for {days:g} day(s) of {lt.name} ({body.start_date} → {body.end_date})",
           "/leave?tab=approvals", "approval")
    audit(db, current.user, "leave.apply", "leave_request", r.id, f"Applied {lt.code} {days:g} day(s)")
    db.commit()
    db.refresh(r)
    return _req(r)


def _can_review(db: Session, current: CurrentUser, r: LeaveRequest) -> bool:
    if r.employee_id == current.employee_id:
        return False
    if current.has("leave.approve"):
        return True
    return bool(current.employee_id and r.employee.manager_id == current.employee_id)


@router.get("/leave/requests")
def list_requests(scope: str = "mine", status: str | None = None, employee_id: int | None = None,
                  date_from: date | None = None, date_to: date | None = None, page: int = 1, page_size: int = 20,
                  current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    """scope: mine | approvals (requests I can act on) | all (leave.view_all)."""
    stmt = select(LeaveRequest).order_by(LeaveRequest.created_at.desc())
    if scope == "all":
        current.require("leave.view_all")
        if employee_id:
            stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    elif scope == "approvals":
        if not current.has("leave.approve"):
            if not current.employee_id:
                return {"items": [], "total": 0, "page": 1, "page_size": page_size, "pages": 0}
            reports = select(Employee.id).where(Employee.manager_id == current.employee_id)
            stmt = stmt.where(LeaveRequest.employee_id.in_(reports))
        if current.employee_id:
            stmt = stmt.where(LeaveRequest.employee_id != current.employee_id)
    else:
        if not current.employee_id:
            return {"items": [], "total": 0, "page": 1, "page_size": page_size, "pages": 0}
        stmt = stmt.where(LeaveRequest.employee_id == current.employee_id)
    if status:
        stmt = stmt.where(LeaveRequest.status == status)
    if date_from:
        stmt = stmt.where(LeaveRequest.end_date >= date_from)
    if date_to:
        stmt = stmt.where(LeaveRequest.start_date <= date_to)
    return paginate(db, stmt, page, page_size, _req)


@router.post("/leave/requests/{rid}/review")
def review_request(rid: int, body: ReviewIn, request: Request, current: CurrentUser = Depends(get_current),
                   db: Session = Depends(get_db)):
    r = db.scalar(select(LeaveRequest).where(LeaveRequest.id == rid).with_for_update())
    if not r:
        raise HTTPException(404, "Leave request not found")
    if not _can_review(db, current, r):
        raise HTTPException(403, "You cannot review this request")
    if r.status != "pending":
        raise HTTPException(409, f"Request is already {r.status}")
    if body.approve and r.leave_type.is_paid:
        bal = db.scalar(select(LeaveBalance).where(LeaveBalance.employee_id == r.employee_id,
                                                   LeaveBalance.leave_type_id == r.leave_type_id,
                                                   LeaveBalance.year == r.start_date.year).with_for_update())
        if not bal or bal.available < r.days:
            raise HTTPException(422, "Insufficient leave balance to approve this request")
        bal.used += r.days
    r.status = "approved" if body.approve else "rejected"
    r.reviewed_by_id, r.reviewed_at, r.review_note = current.id, utcnow(), body.note
    notify(db, user_ids_for_employees(db, [r.employee_id]), f"Leave {r.status}",
           f"Your {r.leave_type.name} ({r.start_date} → {r.end_date}) was {r.status}."
           + (f" Note: {body.note}" if body.note else ""), "/leave", "leave")
    audit(db, current.user, f"leave.{r.status}", "leave_request", r.id,
          f"{r.status.title()} leave of {r.employee.full_name}", ip=client_ip(request))
    db.commit()
    return _req(r)


@router.post("/leave/requests/{rid}/cancel")
def cancel_request(rid: int, current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    r = get_or_404(db, LeaveRequest, rid, "Leave request")
    if r.employee_id != current.employee_id:
        raise HTTPException(403, "You can only cancel your own requests")
    if r.status not in ("pending", "approved"):
        raise HTTPException(409, f"Cannot cancel a {r.status} request")
    if r.status == "approved":
        if r.start_date <= today_local(db):
            raise HTTPException(409, "Approved leave that has started cannot be cancelled. Contact HR.")
        if r.leave_type.is_paid:
            bal = db.scalar(select(LeaveBalance).where(LeaveBalance.employee_id == r.employee_id,
                                                       LeaveBalance.leave_type_id == r.leave_type_id,
                                                       LeaveBalance.year == r.start_date.year))
            if bal:
                bal.used = max(bal.used - r.days, 0)
    r.status = "cancelled"
    audit(db, current.user, "leave.cancel", "leave_request", r.id, "Cancelled leave request")
    db.commit()
    return _req(r)


@router.get("/leave/calendar")
def leave_calendar(date_from: date, date_to: date, current: CurrentUser = Depends(get_current),
                   db: Session = Depends(get_db)):
    """Approved leave in a range — team-wide view shows names only (no reasons)."""
    rows = db.scalars(select(LeaveRequest).where(LeaveRequest.status == "approved", LeaveRequest.start_date <= date_to,
                                                 LeaveRequest.end_date >= date_from)).all()
    full = current.has("leave.view_all")
    return [{"id": r.id, "employee": {"id": r.employee.id, "full_name": r.employee.full_name},
             "leave_type": {"name": r.leave_type.name, "color": r.leave_type.color},
             "start_date": r.start_date, "end_date": r.end_date, "half_day": r.half_day,
             "reason": r.reason if full or r.employee_id == current.employee_id else None} for r in rows]


# ------------------------------------------------------------------ holidays

def _hol(h: Holiday) -> dict:
    return {"id": h.id, "date": h.date, "name": h.name, "is_optional": h.is_optional, "description": h.description}


@router.get("/holidays")
def list_holidays(year: int | None = None, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    year = year or today_local(db).year
    return [_hol(h) for h in db.scalars(select(Holiday).where(func.year(Holiday.date) == year).order_by(Holiday.date))]


@router.post("/holidays", status_code=201)
def create_holiday(body: HolidayIn, current: CurrentUser = Depends(require("leave.configure")), db: Session = Depends(get_db)):
    if db.scalar(select(Holiday.id).where(Holiday.date == body.date)):
        raise HTTPException(409, "A holiday already exists on this date")
    h = Holiday(**body.model_dump())
    db.add(h)
    db.flush()
    audit(db, current.user, "holiday.create", "holiday", h.id, f"Holiday {h.name} on {h.date}")
    db.commit()
    return _hol(h)


@router.put("/holidays/{hid}")
def update_holiday(hid: int, body: HolidayIn, current: CurrentUser = Depends(require("leave.configure")),
                   db: Session = Depends(get_db)):
    h = get_or_404(db, Holiday, hid, "Holiday")
    if db.scalar(select(Holiday.id).where(Holiday.date == body.date, Holiday.id != hid)):
        raise HTTPException(409, "A holiday already exists on this date")
    for k, v in body.model_dump().items():
        setattr(h, k, v)
    audit(db, current.user, "holiday.update", "holiday", h.id, f"Updated holiday {h.name}")
    db.commit()
    return _hol(h)


@router.delete("/holidays/{hid}")
def delete_holiday(hid: int, current: CurrentUser = Depends(require("leave.configure")), db: Session = Depends(get_db)):
    h = get_or_404(db, Holiday, hid, "Holiday")
    audit(db, current.user, "holiday.delete", "holiday", h.id, f"Deleted holiday {h.name}")
    db.delete(h)
    db.commit()
    return {"ok": True}
