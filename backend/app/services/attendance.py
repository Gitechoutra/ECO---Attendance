import calendar
import secrets
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.security import decrypt_bytes
from app.db.base import utcnow
from app.models import (
    AttendanceBreak, AttendanceRecord, Employee, FaceProfile, Holiday, LeaveRequest, LivenessChallenge,
)
from app.services import face
from app.services.common import company_tz, get_company, local_to_utc, utc_to_local

STEP_POOL = [["left", "center"], ["right", "center"], ["left", "right"], ["right", "left"]]


def issue_challenge(db: Session, employee_id: int, purpose: str) -> LivenessChallenge:
    steps = ["center"] + secrets.choice(STEP_POOL)
    ch = LivenessChallenge(employee_id=employee_id, nonce=secrets.token_urlsafe(24), purpose=purpose, steps=steps,
                           expires_at=utcnow() + timedelta(seconds=90))
    db.add(ch)
    db.flush()
    return ch


def consume_challenge(db: Session, nonce: str, employee_id: int, purpose: str) -> LivenessChallenge:
    ch = db.scalar(select(LivenessChallenge).where(LivenessChallenge.nonce == nonce).with_for_update())
    if not ch or ch.employee_id != employee_id or ch.purpose != purpose:
        raise HTTPException(400, "Invalid liveness challenge")
    if ch.used_at:
        raise HTTPException(400, "This liveness challenge was already used")
    if ch.expires_at < utcnow():
        raise HTTPException(400, "Liveness challenge expired. Please start again.")
    ch.used_at = utcnow()
    return ch


def verify_face(db: Session, employee_id: int, nonce: str, purpose: str, frames: list[str],
                timestamps: list[float]) -> dict:
    ch = consume_challenge(db, nonce, employee_id, purpose)
    db.commit()  # burn the nonce even if verification fails
    profile = db.scalar(select(FaceProfile).where(FaceProfile.employee_id == employee_id))
    if not profile:
        raise HTTPException(400, "No face profile is enrolled for you. Ask HR to enroll you or request manual attendance.")
    try:
        analyses = face.analyze_frames(frames)
        live = face.check_liveness(analyses, ch.steps, timestamps)
        enrolled = face.bytes_to_embedding(decrypt_bytes(profile.embedding_enc, biometric=True))
        median, minimum = face.match_score(analyses, enrolled)
    except face.FaceError as e:
        raise HTTPException(422, str(e))
    threshold = get_company(db).face_match_threshold or face.settings.FACE_MATCH_THRESHOLD
    if median < threshold or minimum < threshold - 0.1:
        raise HTTPException(422, "Face did not match your enrolled profile. Retry in good lighting, "
                                 "or submit a manual attendance request.")
    profile.last_verified_at = utcnow()
    return {"score": round(median, 4), **live}


# ------------------------------------------------------------------ status helpers

def is_working_day(db: Session, d: date) -> bool:
    cs = get_company(db)
    if d.weekday() in (cs.weekly_offs or []):
        return False
    return not db.scalar(select(Holiday.id).where(Holiday.date == d, Holiday.is_optional.is_(False)))


def working_days_in_range(db: Session, start: date, end: date) -> list[date]:
    cs = get_company(db)
    hols = set(db.scalars(select(Holiday.date).where(Holiday.date.between(start, end), Holiday.is_optional.is_(False))))
    out, d = [], start
    while d <= end:
        if d.weekday() not in (cs.weekly_offs or []) and d not in hols:
            out.append(d)
        d += timedelta(days=1)
    return out


def recompute(db: Session, rec: AttendanceRecord) -> None:
    cs = get_company(db)
    tz = company_tz(db)
    rec.late_minutes = rec.early_leave_minutes = 0
    if rec.check_in_at:
        local_in = utc_to_local(rec.check_in_at, tz)
        start = datetime.combine(rec.work_date, cs.work_start, tzinfo=tz)
        late = int((local_in - start).total_seconds() // 60)
        rec.late_minutes = late if late > cs.grace_minutes else 0
    rec.break_minutes = sum(
        int(((b.end_at or rec.check_out_at or utcnow()) - b.start_at).total_seconds() // 60) for b in rec.breaks
    ) if rec.breaks else 0
    if rec.check_in_at and rec.check_out_at:
        total = int((rec.check_out_at - rec.check_in_at).total_seconds() // 60)
        rec.worked_minutes = max(total - rec.break_minutes, 0)
        local_out = utc_to_local(rec.check_out_at, tz)
        end = datetime.combine(rec.work_date, cs.work_end, tzinfo=tz)
        early = int((end - local_out).total_seconds() // 60)
        rec.early_leave_minutes = max(early, 0)
    else:
        rec.worked_minutes = 0
    if rec.status in ("on_leave", "absent") and not rec.check_in_at:
        return
    # After check-out, a day shorter than the midpoint between the half-day and full-day thresholds
    # (defaults 240/480 min -> 6 h) counts as a half day.
    half_day_cutoff = (cs.half_day_minutes + cs.full_day_minutes) / 2
    if rec.check_out_at and rec.worked_minutes < half_day_cutoff:
        rec.status = "half_day"
    else:
        rec.status = "late" if rec.late_minutes else "present"


def get_or_create_record(db: Session, employee_id: int, work_date: date) -> AttendanceRecord:
    rec = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == employee_id,
                                                   AttendanceRecord.work_date == work_date))
    if not rec:
        rec = AttendanceRecord(employee_id=employee_id, work_date=work_date, status="present")
        db.add(rec)
        db.flush()
    return rec


def local_today(db: Session) -> date:
    return datetime.now(company_tz(db)).date()


def do_check_in(db: Session, employee: Employee, method: str, score: float | None = None,
                at: datetime | None = None, notes: str | None = None, marked_by: int | None = None) -> AttendanceRecord:
    if employee.status == "inactive":
        raise HTTPException(400, "Inactive employees cannot mark attendance")
    now = (at or utcnow()).replace(microsecond=0)  # MySQL DATETIME has second precision
    work_date = utc_to_local(now, company_tz(db)).date()
    rec = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == employee.id,
                                                   AttendanceRecord.work_date == work_date).with_for_update())
    if rec and rec.check_in_at:
        raise HTTPException(409, "You have already checked in today")
    if not rec:
        rec = AttendanceRecord(employee_id=employee.id, work_date=work_date)
        db.add(rec)
    rec.check_in_at, rec.check_in_method, rec.check_in_score = now, method, score
    rec.status = "present"
    rec.marked_by_id = marked_by
    if notes:
        rec.notes = notes
    db.flush()
    recompute(db, rec)
    return rec


def do_check_out(db: Session, employee: Employee, method: str, score: float | None = None,
                 at: datetime | None = None) -> AttendanceRecord:
    now = (at or utcnow()).replace(microsecond=0)  # MySQL DATETIME has second precision
    tz = company_tz(db)
    work_date = utc_to_local(now, tz).date()
    rec = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == employee.id,
                                                   AttendanceRecord.work_date == work_date).with_for_update())
    if not rec:  # overnight shift: allow checkout for yesterday's open record
        rec = db.scalar(select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee.id, AttendanceRecord.work_date == work_date - timedelta(days=1),
            AttendanceRecord.check_out_at.is_(None), AttendanceRecord.check_in_at.is_not(None)))
    if not rec or not rec.check_in_at:
        raise HTTPException(409, "You have not checked in today")
    if rec.check_out_at:
        raise HTTPException(409, "You have already checked out today")
    if now < rec.check_in_at:
        raise HTTPException(400, "Check-out time must be after check-in time")
    for b in rec.breaks:
        if b.end_at is None:
            b.end_at = now
    rec.check_out_at, rec.check_out_method, rec.check_out_score = now, method, score
    recompute(db, rec)
    return rec


def toggle_break(db: Session, employee: Employee, action: str, reason: str | None) -> AttendanceRecord:
    rec = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == employee.id,
                                                   AttendanceRecord.work_date == local_today(db)))
    if not rec or not rec.check_in_at or rec.check_out_at:
        raise HTTPException(409, "You must be checked in to take a break")
    open_b = next((b for b in rec.breaks if b.end_at is None), None)
    if action == "start":
        if open_b:
            raise HTTPException(409, "A break is already in progress")
        rec.breaks.append(AttendanceBreak(start_at=utcnow(), reason=reason))
    else:
        if not open_b:
            raise HTTPException(409, "No break in progress")
        open_b.end_at = utcnow()
    db.flush()
    recompute(db, rec)
    return rec


def apply_correction(db: Session, employee_id: int, work_date: date, check_in: datetime | None,
                     check_out: datetime | None, marked_by: int, method: str = "correction") -> AttendanceRecord:
    rec = get_or_create_record(db, employee_id, work_date)
    if check_in:
        rec.check_in_at, rec.check_in_method = check_in, method
    if check_out:
        rec.check_out_at, rec.check_out_method = check_out, method
    if rec.check_in_at and rec.check_out_at and rec.check_out_at <= rec.check_in_at:
        raise HTTPException(422, "Check-out must be after check-in")
    rec.marked_by_id = marked_by
    rec.status = "present"
    recompute(db, rec)
    return rec


def serialize_record(r: AttendanceRecord, tz) -> dict:
    open_break = next((b for b in r.breaks if b.end_at is None), None)
    return {
        "id": r.id, "employee_id": r.employee_id, "work_date": r.work_date,
        "employee": {"id": r.employee.id, "full_name": r.employee.full_name, "employee_code": r.employee.employee_code,
                     "photo_file_id": r.employee.photo_file_id,
                     "department": r.employee.department.name if r.employee.department else None},
        "check_in_at": _iso(r.check_in_at), "check_out_at": _iso(r.check_out_at),
        "check_in_local": utc_to_local(r.check_in_at, tz).strftime("%H:%M") if r.check_in_at else None,
        "check_out_local": utc_to_local(r.check_out_at, tz).strftime("%H:%M") if r.check_out_at else None,
        "check_in_method": r.check_in_method, "check_out_method": r.check_out_method,
        "check_in_score": r.check_in_score, "status": r.status, "late_minutes": r.late_minutes,
        "early_leave_minutes": r.early_leave_minutes, "worked_minutes": r.worked_minutes,
        "break_minutes": r.break_minutes, "notes": r.notes, "on_break": bool(open_break),
        "breaks": [{"start_at": _iso(b.start_at), "end_at": _iso(b.end_at), "reason": b.reason} for b in r.breaks],
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def monthly_summary(db: Session, employee_ids: list[int] | None, year: int, month: int) -> list[dict]:
    start, end = month_bounds(year, month)
    return range_summary(db, employee_ids, start, end)


def range_summary(db: Session, employee_ids: list[int] | None, start: date, end: date) -> list[dict]:
    today = local_today(db)
    eff_end = min(end, today)
    wdays = working_days_in_range(db, start, eff_end) if eff_end >= start else []
    emp_q = select(Employee).where(Employee.joining_date <= end).order_by(Employee.first_name)
    if employee_ids is not None:
        emp_q = emp_q.where(Employee.id.in_(employee_ids))
    emps = db.scalars(emp_q).unique().all()
    recs = db.scalars(select(AttendanceRecord).where(AttendanceRecord.work_date.between(start, end))).unique().all()
    by_emp: dict[int, dict[date, AttendanceRecord]] = {}
    for r in recs:
        by_emp.setdefault(r.employee_id, {})[r.work_date] = r
    leaves = db.scalars(select(LeaveRequest).where(LeaveRequest.status == "approved",
                                                   and_(LeaveRequest.start_date <= end, LeaveRequest.end_date >= start))).all()
    leave_days: dict[int, dict[date, float]] = {}
    for lr in leaves:
        d = max(lr.start_date, start)
        while d <= min(lr.end_date, end):
            leave_days.setdefault(lr.employee_id, {})[d] = 0.5 if lr.half_day else 1.0
            d += timedelta(days=1)
    out = []
    for e in emps:
        if e.exit_date and e.exit_date < start:
            continue
        days = by_emp.get(e.id, {})
        ldays = leave_days.get(e.id, {})
        emp_wdays = [d for d in wdays if d >= e.joining_date and (not e.exit_date or d <= e.exit_date)]
        present = sum(1 for d, r in days.items() if r.check_in_at and r.status in ("present", "late"))
        half = sum(1 for r in days.values() if r.status == "half_day")
        late = sum(1 for r in days.values() if r.late_minutes > 0)
        early = sum(1 for r in days.values() if r.early_leave_minutes > 0 and r.check_out_at)
        leave = sum(v for d, v in ldays.items() if d in emp_wdays)
        absent = sum(1 for d in emp_wdays if d < today and d not in ldays and not (days.get(d) and days[d].check_in_at))
        minutes = sum(r.worked_minutes for r in days.values())
        out.append({
            "employee": {"id": e.id, "full_name": e.full_name, "employee_code": e.employee_code,
                         "department": e.department.name if e.department else None},
            "working_days": len(emp_wdays), "present": present, "half_days": half, "late": late,
            "early_departures": early, "leave_days": leave, "absent": absent,
            "worked_hours": round(minutes / 60, 1),
            "avg_hours": round(minutes / 60 / max(present + half, 1), 1),
        })
    return out


def parse_local(db: Session, d: date, hhmm: str | None) -> datetime | None:
    if not hhmm:
        return None
    try:
        h, m = [int(x) for x in hhmm.split(":")[:2]]
        return local_to_utc(datetime(d.year, d.month, d.day, h, m), company_tz(db))
    except (ValueError, TypeError):
        raise HTTPException(422, "Time must be HH:MM")
