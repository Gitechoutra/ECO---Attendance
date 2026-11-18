from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, get_current, require, require_employee
from app.core.ratelimit import limiter
from app.core.security import encrypt_bytes
from app.db.base import utcnow
from app.db.session import get_db
from app.models import AttendanceCorrection, AttendanceRecord, BiometricConsent, Employee, FaceProfile
from app.schemas.attendance import (
    BreakIn, ChallengeIn, CorrectionIn, EnrollIn, FaceSubmitIn, ManualMarkIn, ReviewIn,
)
from app.services import attendance as svc
from app.services import face
from app.services.common import (
    audit, company_tz, get_company, get_or_404, notify, paginate, user_ids_for_employees, user_ids_with_permission,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])
CONSENT_VERSION = "2026-1"

INSTRUCTIONS = {
    "center": "Look straight at the camera",
    "left": "Slowly turn your head to your left",
    "right": "Slowly turn your head to your right",
}


def _emp(db: Session, current: CurrentUser) -> Employee:
    return db.get(Employee, current.employee_id)


@router.get("/today")
def today(current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    tz = company_tz(db)
    rec = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == current.employee_id,
                                                   AttendanceRecord.work_date == svc.local_today(db)))
    cs = get_company(db)
    profile = db.scalar(select(FaceProfile).where(FaceProfile.employee_id == current.employee_id))
    pending = db.scalar(select(AttendanceCorrection).where(
        AttendanceCorrection.employee_id == current.employee_id, AttendanceCorrection.status == "pending",
        AttendanceCorrection.work_date == svc.local_today(db)))
    return {
        "date": svc.local_today(db), "record": svc.serialize_record(rec, tz) if rec else None,
        "face_enrolled": bool(profile), "face_required": cs.require_face_for_attendance,
        "is_working_day": svc.is_working_day(db, svc.local_today(db)),
        "shift": {"start": cs.work_start.strftime("%H:%M"), "end": cs.work_end.strftime("%H:%M"),
                  "grace_minutes": cs.grace_minutes},
        "pending_request": bool(pending),
    }


@router.post("/challenge")
@limiter.limit("20/minute")
def challenge(request: Request, body: ChallengeIn, current: CurrentUser = Depends(get_current),
              db: Session = Depends(get_db)):
    if body.purpose == "enroll":
        emp_id = body.employee_id or current.employee_id
        if not emp_id:
            raise HTTPException(422, "employee_id is required for enrollment")
        if emp_id != current.employee_id:
            current.require("attendance.enroll_face")  # enrolling someone else is an HR action
        get_or_404(db, Employee, emp_id, "Employee")
    else:
        if not current.employee_id:
            raise HTTPException(400, "Your account is not linked to an employee profile")
        emp_id = current.employee_id
    ch = svc.issue_challenge(db, emp_id, body.purpose)
    db.commit()
    return {"nonce": ch.nonce, "steps": ch.steps, "instructions": [INSTRUCTIONS[s] for s in ch.steps],
            "expires_in": 90}


@router.post("/check-in/face")
@limiter.limit("10/minute")
def check_in_face(request: Request, body: FaceSubmitIn, current: CurrentUser = Depends(require_employee),
                  db: Session = Depends(get_db)):
    result = svc.verify_face(db, current.employee_id, body.nonce, "check_in", body.frames, body.timestamps)
    rec = svc.do_check_in(db, _emp(db, current), "face", result["score"])
    audit(db, current.user, "attendance.check_in", "attendance", rec.id, "Face-verified check-in",
          {"score": result["score"], "liveness": result}, ip=client_ip(request))
    db.commit()
    return {"record": svc.serialize_record(rec, company_tz(db)), "verification": result}


@router.post("/check-out/face")
@limiter.limit("10/minute")
def check_out_face(request: Request, body: FaceSubmitIn, current: CurrentUser = Depends(require_employee),
                   db: Session = Depends(get_db)):
    result = svc.verify_face(db, current.employee_id, body.nonce, "check_out", body.frames, body.timestamps)
    rec = svc.do_check_out(db, _emp(db, current), "face", result["score"])
    audit(db, current.user, "attendance.check_out", "attendance", rec.id, "Face-verified check-out",
          {"score": result["score"]}, ip=client_ip(request))
    db.commit()
    return {"record": svc.serialize_record(rec, company_tz(db)), "verification": result}


@router.post("/check-in")
def check_in_web(request: Request, current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    """Check-in without biometrics — only when the company has disabled the face requirement."""
    if get_company(db).require_face_for_attendance:
        raise HTTPException(403, "Face verification is required. Use the camera check-in or request manual attendance.")
    rec = svc.do_check_in(db, _emp(db, current), "web")
    audit(db, current.user, "attendance.check_in", "attendance", rec.id, "Web check-in", ip=client_ip(request))
    db.commit()
    return {"record": svc.serialize_record(rec, company_tz(db))}


@router.post("/check-out")
def check_out_web(request: Request, current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    if get_company(db).require_face_for_attendance:
        raise HTTPException(403, "Face verification is required. Use the camera check-out or request manual attendance.")
    rec = svc.do_check_out(db, _emp(db, current), "web")
    audit(db, current.user, "attendance.check_out", "attendance", rec.id, "Web check-out", ip=client_ip(request))
    db.commit()
    return {"record": svc.serialize_record(rec, company_tz(db))}


@router.post("/break")
def take_break(body: BreakIn, current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    rec = svc.toggle_break(db, _emp(db, current), body.action, body.reason)
    db.commit()
    return {"record": svc.serialize_record(rec, company_tz(db))}


@router.get("/my")
def my_attendance(year: int, month: int, current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    start, end = svc.month_bounds(year, month)
    tz = company_tz(db)
    rows = db.scalars(select(AttendanceRecord).where(AttendanceRecord.employee_id == current.employee_id,
                                                     AttendanceRecord.work_date.between(start, end))
                      .order_by(AttendanceRecord.work_date)).unique().all()
    summary = svc.monthly_summary(db, [current.employee_id], year, month)
    return {"records": [svc.serialize_record(r, tz) for r in rows], "summary": summary[0] if summary else None,
            "working_days": [d.isoformat() for d in svc.working_days_in_range(db, start, end)]}


@router.get("/records")
def list_records(date_from: date | None = None, date_to: date | None = None, employee_id: int | None = None,
                 department_id: int | None = None, status: str | None = None, page: int = 1, page_size: int = 25,
                 current: CurrentUser = Depends(require("attendance.view_all")), db: Session = Depends(get_db)):
    tz = company_tz(db)
    date_to = date_to or svc.local_today(db)
    date_from = date_from or date_to
    stmt = select(AttendanceRecord).join(Employee).where(AttendanceRecord.work_date.between(date_from, date_to))
    if employee_id:
        stmt = stmt.where(AttendanceRecord.employee_id == employee_id)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if status:
        stmt = stmt.where(AttendanceRecord.status == status)
    stmt = stmt.order_by(AttendanceRecord.work_date.desc(), AttendanceRecord.check_in_at)
    return paginate(db, stmt, page, page_size, lambda r: svc.serialize_record(r, tz))


@router.get("/live")
def live_board(current: CurrentUser = Depends(require("attendance.view_all")), db: Session = Depends(get_db)):
    """Today's status for every active employee (including those not yet checked in)."""
    tz = company_tz(db)
    today_d = svc.local_today(db)
    emps = db.scalars(select(Employee).where(Employee.status != "inactive").order_by(Employee.first_name)).unique().all()
    recs = {r.employee_id: r for r in db.scalars(select(AttendanceRecord).where(AttendanceRecord.work_date == today_d)).unique()}
    from app.models import LeaveRequest
    on_leave = set(db.scalars(select(LeaveRequest.employee_id).where(
        LeaveRequest.status == "approved", LeaveRequest.start_date <= today_d, LeaveRequest.end_date >= today_d)))
    rows = []
    for e in emps:
        r = recs.get(e.id)
        state = ("on_leave" if e.id in on_leave and not (r and r.check_in_at) else
                 "not_checked_in" if not r or not r.check_in_at else
                 "checked_out" if r.check_out_at else "on_break" if any(b.end_at is None for b in r.breaks) else "working")
        rows.append({"employee": {"id": e.id, "full_name": e.full_name, "employee_code": e.employee_code,
                                  "photo_file_id": e.photo_file_id,
                                  "department": e.department.name if e.department else None},
                     "state": state, "record": svc.serialize_record(r, tz) if r else None})
    counts = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return {"date": today_d, "is_working_day": svc.is_working_day(db, today_d), "counts": counts, "rows": rows}


@router.get("/summary")
def summary(year: int, month: int, department_id: int | None = None,
            current: CurrentUser = Depends(require("attendance.view_all")), db: Session = Depends(get_db)):
    ids = None
    if department_id:
        ids = list(db.scalars(select(Employee.id).where(Employee.department_id == department_id)))
    return svc.monthly_summary(db, ids, year, month)


@router.post("/manual")
def manual_mark(body: ManualMarkIn, request: Request, current: CurrentUser = Depends(require("attendance.manage")),
                db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, body.employee_id, "Employee")
    if body.work_date > svc.local_today(db):
        raise HTTPException(422, "Cannot mark attendance for a future date")
    if body.status in ("absent", "on_leave"):
        rec = svc.get_or_create_record(db, emp.id, body.work_date)
        rec.check_in_at = rec.check_out_at = None
        rec.breaks.clear()
        rec.status = body.status
        rec.worked_minutes = rec.late_minutes = rec.early_leave_minutes = 0
    else:
        rec = svc.apply_correction(db, emp.id, body.work_date, svc.parse_local(db, body.work_date, body.check_in),
                                   svc.parse_local(db, body.work_date, body.check_out), current.id, "manual")
        if body.status == "half_day":
            rec.status = "half_day"
    rec.notes = f"Manual: {body.reason}"
    rec.marked_by_id = current.id
    audit(db, current.user, "attendance.manual", "attendance", rec.id,
          f"Manual attendance for {emp.full_name} on {body.work_date}", body.model_dump(mode="json"), ip=client_ip(request))
    notify(db, user_ids_for_employees(db, [emp.id]), "Attendance updated by HR",
           f"Your attendance for {body.work_date} was updated: {body.reason}", "/attendance", "attendance")
    db.commit()
    return svc.serialize_record(rec, company_tz(db))


# ------------------------------------------------------------------ corrections & manual requests

def _corr(c: AttendanceCorrection, tz) -> dict:
    from app.services.common import utc_to_local
    return {"id": c.id, "kind": c.kind, "work_date": c.work_date, "reason": c.reason, "status": c.status,
            "employee": {"id": c.employee.id, "full_name": c.employee.full_name, "employee_code": c.employee.employee_code},
            "requested_check_in": utc_to_local(c.requested_check_in, tz).strftime("%H:%M") if c.requested_check_in else None,
            "requested_check_out": utc_to_local(c.requested_check_out, tz).strftime("%H:%M") if c.requested_check_out else None,
            "reviewed_by": c.reviewed_by.email if c.reviewed_by else None, "reviewed_at": c.reviewed_at,
            "review_note": c.review_note, "created_at": c.created_at}


@router.post("/corrections", status_code=201)
def request_correction(body: CorrectionIn, current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    today_d = svc.local_today(db)
    if body.work_date > today_d:
        raise HTTPException(422, "Cannot request attendance for a future date")
    if body.work_date < today_d - timedelta(days=45):
        raise HTTPException(422, "Corrections are allowed only for the last 45 days")
    if db.scalar(select(AttendanceCorrection.id).where(
            AttendanceCorrection.employee_id == current.employee_id, AttendanceCorrection.work_date == body.work_date,
            AttendanceCorrection.status == "pending")):
        raise HTTPException(409, "A request for this date is already pending")
    c = AttendanceCorrection(employee_id=current.employee_id, kind=body.kind, work_date=body.work_date,
                             requested_check_in=svc.parse_local(db, body.work_date, body.check_in),
                             requested_check_out=svc.parse_local(db, body.work_date, body.check_out),
                             reason=body.reason)
    db.add(c)
    db.flush()
    emp = _emp(db, current)
    approvers = set(user_ids_with_permission(db, "attendance.manage"))
    if emp.manager_id:
        approvers |= set(user_ids_for_employees(db, [emp.manager_id]))
    notify(db, approvers, f"Attendance {body.kind} request", f"{emp.full_name} requested a {body.kind} for {body.work_date}",
           "/attendance?tab=requests", "approval")
    audit(db, current.user, "attendance.correction_request", "attendance_correction", c.id, f"{body.kind} request for {body.work_date}")
    db.commit()
    return _corr(c, company_tz(db))


@router.get("/corrections")
def list_corrections(status: str | None = None, mine: bool = False, page: int = 1, page_size: int = 20,
                     current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    stmt = select(AttendanceCorrection).order_by(AttendanceCorrection.created_at.desc())
    if mine or not current.has("attendance.manage"):
        if not current.employee_id:
            return {"items": [], "total": 0, "page": 1, "page_size": page_size, "pages": 0}
        stmt = stmt.where(AttendanceCorrection.employee_id == current.employee_id)
    if status:
        stmt = stmt.where(AttendanceCorrection.status == status)
    tz = company_tz(db)
    return paginate(db, stmt, page, page_size, lambda c: _corr(c, tz))


@router.post("/corrections/{cid}/review")
def review_correction(cid: int, body: ReviewIn, request: Request,
                      current: CurrentUser = Depends(require("attendance.manage")), db: Session = Depends(get_db)):
    c = get_or_404(db, AttendanceCorrection, cid, "Request")
    if c.status != "pending":
        raise HTTPException(409, "Request already reviewed")
    if c.employee_id == current.employee_id:
        raise HTTPException(403, "You cannot approve your own request")
    c.status = "approved" if body.approve else "rejected"
    c.reviewed_by_id, c.reviewed_at, c.review_note = current.id, utcnow(), body.note
    if body.approve:
        svc.apply_correction(db, c.employee_id, c.work_date, c.requested_check_in, c.requested_check_out, current.id,
                             "manual" if c.kind == "manual" else "correction")
    notify(db, user_ids_for_employees(db, [c.employee_id]), f"Attendance request {c.status}",
           f"Your {c.kind} request for {c.work_date} was {c.status}." + (f" Note: {body.note}" if body.note else ""),
           "/attendance", "attendance")
    audit(db, current.user, f"attendance.correction_{c.status}", "attendance_correction", c.id,
          f"{c.status.title()} {c.kind} for {c.employee.full_name} on {c.work_date}", ip=client_ip(request))
    db.commit()
    return _corr(c, company_tz(db))


# ------------------------------------------------------------------ face enrollment

@router.get("/face/status/{employee_id}")
def face_status(employee_id: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    if employee_id != current.employee_id and not current.has("attendance.enroll_face"):
        raise HTTPException(403, "Not allowed")
    p = db.scalar(select(FaceProfile).where(FaceProfile.employee_id == employee_id))
    consent = db.scalar(select(BiometricConsent).where(BiometricConsent.employee_id == employee_id)
                        .order_by(BiometricConsent.given_at.desc()))
    return {"enrolled": bool(p), "enrolled_at": p.created_at if p else None, "samples": p.sample_count if p else 0,
            "last_verified_at": p.last_verified_at if p else None,
            "consent": None if not consent else {"version": consent.consent_version, "given_at": consent.given_at,
                                                 "revoked_at": consent.revoked_at}}


@router.post("/face/enroll")
@limiter.limit("10/minute")
def enroll_face(request: Request, body: EnrollIn, current: CurrentUser = Depends(get_current),
                db: Session = Depends(get_db)):
    """HR enrolls any employee; an employee may enroll themselves (live capture + their own consent)."""
    self_enroll = body.employee_id == current.employee_id
    if not self_enroll:
        current.require("attendance.enroll_face")
    emp = get_or_404(db, Employee, body.employee_id, "Employee")
    if emp.status == "inactive":
        raise HTTPException(400, "Cannot enroll an inactive employee")
    ch = svc.consume_challenge(db, body.nonce, emp.id, "enroll")
    db.commit()
    try:
        analyses = face.analyze_frames(body.frames)
        live = face.check_liveness(analyses, ch.steps, body.timestamps)
    except face.FaceError as e:
        raise HTTPException(422, str(e))
    frontal = [a for a in analyses if abs(a.yaw) < 0.12] or analyses
    vec = face.mean_embedding(frontal)
    consent = BiometricConsent(employee_id=emp.id, consent_version=CONSENT_VERSION, ip_address=client_ip(request),
                               recorded_by_id=current.id)
    db.add(consent)
    db.flush()
    profile = db.scalar(select(FaceProfile).where(FaceProfile.employee_id == emp.id))
    blob = encrypt_bytes(face.embedding_to_bytes(vec), biometric=True)
    if profile:
        profile.embedding_enc, profile.sample_count, profile.consent_id = blob, len(frontal), consent.id
        profile.enrolled_by_id = current.id
    else:
        db.add(FaceProfile(employee_id=emp.id, embedding_enc=blob, sample_count=len(frontal), consent_id=consent.id,
                           enrolled_by_id=current.id))
    audit(db, current.user, "biometric.enroll", "employee", emp.id,
          f"Face profile {'self-' if self_enroll else ''}enrolled for {emp.full_name}",
          {"frames": live["frames"], "self": self_enroll}, ip=client_ip(request))
    if self_enroll:
        notify(db, set(user_ids_with_permission(db, "attendance.enroll_face")) - {current.id},
               "Employee enrolled face check-in", f"{emp.full_name} set up face verification with a live capture.",
               f"/employees/{emp.id}", "attendance")
    else:
        notify(db, user_ids_for_employees(db, [emp.id]), "Face profile enrolled",
               "Your face profile for attendance was enrolled. You can revoke consent anytime from your profile.",
               "/profile", "attendance")
    db.commit()
    return {"enrolled": True, **live}


@router.delete("/face/{employee_id}")
def remove_face(employee_id: int, request: Request, current: CurrentUser = Depends(get_current),
                db: Session = Depends(get_db)):
    """Employees may revoke their own consent; HR may remove profiles. Template is deleted immediately."""
    if employee_id != current.employee_id and not current.has("attendance.enroll_face"):
        raise HTTPException(403, "Not allowed")
    p = db.scalar(select(FaceProfile).where(FaceProfile.employee_id == employee_id))
    if not p:
        raise HTTPException(404, "No face profile enrolled")
    for c in db.scalars(select(BiometricConsent).where(BiometricConsent.employee_id == employee_id,
                                                       BiometricConsent.revoked_at.is_(None))):
        c.revoked_at = utcnow()
    db.delete(p)
    audit(db, current.user, "biometric.delete", "employee", employee_id, "Face profile deleted / consent revoked",
          ip=client_ip(request))
    db.commit()
    return {"ok": True}
