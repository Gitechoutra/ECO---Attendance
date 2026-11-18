from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, require
from app.db.session import get_db
from app.models import (
    Candidate, Department, Designation, Employee, Interview, JobOpening, OfferLetter, OfferLetterVersion, StoredFile,
)
from app.schemas.people import (
    CandidateIn, CandidateStatusIn, ConvertIn, InterviewFeedbackIn, InterviewIn, JobIn,
)
from app.services.common import audit, get_or_404, notify, paginate, user_ids_for_employees
from app.services.employees import (
    add_history, allocate_leave_balances, create_login, employee_brief, next_employee_code, serialize_employee,
)
from app.services.storage import delete_file, get_storage, store_bytes, store_upload

router = APIRouter(prefix="/recruitment", tags=["Recruitment"])
view = require("recruitment.view")
manage = require("recruitment.manage")


def _job(db: Session, j: JobOpening) -> dict:
    counts = dict(db.execute(select(Candidate.status, func.count()).where(Candidate.job_id == j.id)
                             .group_by(Candidate.status)).all())
    return {"id": j.id, "title": j.title, "department": j.department.name if j.department else None,
            "department_id": j.department_id, "designation_id": j.designation_id,
            "designation": j.designation.title if j.designation else None, "description": j.description,
            "requirements": j.requirements, "location": j.location, "employment_type": j.employment_type,
            "experience_min": j.experience_min, "experience_max": j.experience_max, "positions": j.positions,
            "status": j.status, "closes_on": j.closes_on, "hiring_manager": employee_brief(j.hiring_manager),
            "hiring_manager_id": j.hiring_manager_id, "candidate_count": sum(counts.values()), "pipeline": counts,
            "hired": counts.get("hired", 0), "created_at": j.created_at}


def _cand(c: Candidate) -> dict:
    return {"id": c.id, "full_name": c.full_name, "first_name": c.first_name, "last_name": c.last_name,
            "email": c.email, "phone": c.phone, "source": c.source, "current_company": c.current_company,
            "experience_years": c.experience_years, "current_ctc": float(c.current_ctc) if c.current_ctc is not None else None,
            "expected_ctc": float(c.expected_ctc) if c.expected_ctc is not None else None,
            "notice_period_days": c.notice_period_days, "skills": c.skills, "status": c.status, "rating": c.rating,
            "notes": c.notes, "resume_file_id": c.resume_file_id, "employee_id": c.employee_id,
            "job": {"id": c.job.id, "title": c.job.title} if c.job else None, "job_id": c.job_id,
            "created_at": c.created_at, "updated_at": c.updated_at}


def _iv(i: Interview) -> dict:
    return {"id": i.id, "candidate_id": i.candidate_id, "candidate": i.candidate.full_name, "round_name": i.round_name,
            "scheduled_at": i.scheduled_at, "duration_minutes": i.duration_minutes, "mode": i.mode,
            "location": i.location, "interviewer": employee_brief(i.interviewer), "interviewer_id": i.interviewer_id,
            "status": i.status, "rating": i.rating, "recommendation": i.recommendation, "feedback": i.feedback,
            "job": i.candidate.job.title if i.candidate.job else None}


# ------------------------------------------------------------------ jobs

@router.get("/jobs")
def list_jobs(status: str | None = None, q: str | None = None, current: CurrentUser = Depends(view),
              db: Session = Depends(get_db)):
    stmt = select(JobOpening).order_by(JobOpening.status == "closed", JobOpening.created_at.desc())
    if status:
        stmt = stmt.where(JobOpening.status == status)
    if q:
        stmt = stmt.where(JobOpening.title.ilike(f"%{q}%"))
    return [_job(db, j) for j in db.scalars(stmt).unique()]


@router.post("/jobs", status_code=201)
def create_job(body: JobIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    if body.department_id and not db.get(Department, body.department_id):
        raise HTTPException(422, "Department not found")
    j = JobOpening(created_by_id=current.id, **body.model_dump())
    db.add(j)
    db.flush()
    audit(db, current.user, "job.create", "job_opening", j.id, f"Opened {j.title}")
    db.commit()
    db.refresh(j)
    return _job(db, j)


@router.put("/jobs/{jid}")
def update_job(jid: int, body: JobIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    j = get_or_404(db, JobOpening, jid, "Job opening")
    for k, v in body.model_dump().items():
        setattr(j, k, v)
    audit(db, current.user, "job.update", "job_opening", j.id, f"Updated {j.title}")
    db.commit()
    db.refresh(j)
    return _job(db, j)


@router.delete("/jobs/{jid}")
def delete_job(jid: int, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    j = get_or_404(db, JobOpening, jid, "Job opening")
    if db.scalar(select(func.count()).select_from(Candidate).where(Candidate.job_id == jid)):
        raise HTTPException(409, "This opening has candidates. Close it instead of deleting.")
    db.delete(j)
    audit(db, current.user, "job.delete", "job_opening", jid, f"Deleted {j.title}")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ candidates

@router.get("/candidates")
def list_candidates(job_id: int | None = None, status: str | None = None, q: str | None = None, page: int = 1,
                    page_size: int = 100, current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    stmt = select(Candidate).order_by(Candidate.updated_at.desc())
    if job_id:
        stmt = stmt.where(Candidate.job_id == job_id)
    if status:
        stmt = stmt.where(Candidate.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Candidate.first_name.ilike(like), Candidate.last_name.ilike(like),
                              Candidate.email.ilike(like), Candidate.skills.ilike(like)))
    return paginate(db, stmt, page, page_size, _cand)


@router.post("/candidates", status_code=201)
def create_candidate(body: CandidateIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    if body.job_id and not db.get(JobOpening, body.job_id):
        raise HTTPException(422, "Job opening not found")
    dup = select(Candidate.id).where(func.lower(Candidate.email) == body.email.lower(),
                                     Candidate.status.not_in(["rejected", "withdrawn"]))
    if body.job_id:
        dup = dup.where(Candidate.job_id == body.job_id)
    if db.scalar(dup):
        raise HTTPException(409, "This candidate is already active for this opening")
    c = Candidate(**body.model_dump())
    c.email = c.email.lower()
    db.add(c)
    db.flush()
    audit(db, current.user, "candidate.create", "candidate", c.id, f"Added candidate {c.full_name}")
    db.commit()
    db.refresh(c)
    return _cand(c)


@router.get("/candidates/{cid}")
def get_candidate(cid: int, current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    c = get_or_404(db, Candidate, cid, "Candidate")
    data = _cand(c)
    data["interviews"] = [_iv(i) for i in db.scalars(select(Interview).where(Interview.candidate_id == cid)
                                                     .order_by(Interview.scheduled_at))]
    data["offers"] = [{"id": o.id, "reference_no": o.reference_no, "status": o.status, "designation": o.designation,
                       "annual_ctc": float(o.annual_ctc), "created_at": o.created_at}
                      for o in db.scalars(select(OfferLetter).where(OfferLetter.candidate_id == cid))]
    return data


@router.put("/candidates/{cid}")
def update_candidate(cid: int, body: CandidateIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    c = get_or_404(db, Candidate, cid, "Candidate")
    if c.status == "hired" and body.status != "hired":
        raise HTTPException(409, "A hired candidate's status cannot be changed")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    c.email = c.email.lower()
    audit(db, current.user, "candidate.update", "candidate", c.id, f"Updated {c.full_name}")
    db.commit()
    return _cand(c)


@router.patch("/candidates/{cid}/status")
def candidate_status(cid: int, body: CandidateStatusIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    c = get_or_404(db, Candidate, cid, "Candidate")
    if c.status == "hired":
        raise HTTPException(409, "Candidate is already hired")
    if body.status == "hired":
        raise HTTPException(422, "Use 'Convert to employee' to mark a candidate as hired")
    old = c.status
    c.status = body.status
    if body.note:
        c.notes = ((c.notes or "") + f"\n[{old} → {body.status}] {body.note}").strip()
    audit(db, current.user, "candidate.status", "candidate", c.id, f"{c.full_name}: {old} → {body.status}")
    db.commit()
    return _cand(c)


@router.delete("/candidates/{cid}")
def delete_candidate(cid: int, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    c = get_or_404(db, Candidate, cid, "Candidate")
    if c.employee_id:
        raise HTTPException(409, "Converted candidates cannot be deleted")
    if db.scalar(select(OfferLetter.id).where(OfferLetter.candidate_id == cid)):
        raise HTTPException(409, "Candidate has offer letters. Mark them withdrawn instead.")
    if c.resume_file_id:
        f = db.get(StoredFile, c.resume_file_id)
        c.resume_file_id = None
        db.flush()
        if f:
            delete_file(db, f)
    audit(db, current.user, "candidate.delete", "candidate", cid, f"Deleted {c.full_name}")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/candidates/{cid}/resume")
async def upload_resume(cid: int, file: UploadFile = File(...), current: CurrentUser = Depends(manage),
                        db: Session = Depends(get_db)):
    c = get_or_404(db, Candidate, cid, "Candidate")
    f = await store_upload(db, file, current.user, "candidate", cid, "resume", allowed={
        "application/pdf", "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"})
    old = db.get(StoredFile, c.resume_file_id) if c.resume_file_id else None
    c.resume_file_id = f.id
    if old:
        db.flush()
        delete_file(db, old)
    db.commit()
    return {"resume_file_id": f.id}


@router.post("/candidates/{cid}/convert", status_code=201)
def convert_to_employee(cid: int, body: ConvertIn, request: Request,
                        current: CurrentUser = Depends(require("recruitment.manage", "employees.manage")),
                        db: Session = Depends(get_db)):
    """Create the employee record from a selected candidate (single profile, no duplicates)."""
    c = get_or_404(db, Candidate, cid, "Candidate")
    if c.employee_id:
        raise HTTPException(409, "Candidate was already converted")
    if db.scalar(select(Employee.id).where(func.lower(Employee.email) == c.email.lower())):
        raise HTTPException(409, "An employee with this email already exists")
    offer = db.scalar(select(OfferLetter).where(OfferLetter.candidate_id == cid, OfferLetter.status == "accepted")
                      .order_by(OfferLetter.id.desc()))
    joining = body.joining_date or (offer.joining_date if offer else None)
    if not joining:
        raise HTTPException(422, "Joining date is required (no accepted offer found)")
    desig_id = body.designation_id
    if not desig_id and offer:
        desig_id = db.scalar(select(Designation.id).where(func.lower(Designation.title) == offer.designation.lower()))
    dept_id = body.department_id or (offer.department_id if offer else None) or (c.job.department_id if c.job else None)
    emp = Employee(employee_code=next_employee_code(db), first_name=c.first_name, last_name=c.last_name or "",
                   email=c.email, phone=c.phone, joining_date=joining, department_id=dept_id,
                   designation_id=desig_id or (c.job.designation_id if c.job else None), manager_id=body.manager_id,
                   employment_type=c.job.employment_type if c.job else "full_time",
                   work_location=offer.work_location if offer else None)
    db.add(emp)
    db.flush()
    temp_pw = None
    if body.create_login:
        _, temp_pw = create_login(db, emp, body.role_code)
    allocate_leave_balances(db, emp, joining.year)
    c.employee_id, c.status = emp.id, "hired"
    # Carry offer letters (all versions) and resume into the employee's document records
    storage = get_storage()
    for o in db.scalars(select(OfferLetter).where(OfferLetter.candidate_id == cid)):
        o.employee_id = emp.id
        if o.status == "accepted":
            for v in db.scalars(select(OfferLetterVersion).where(OfferLetterVersion.offer_id == o.id)):
                src = db.get(StoredFile, v.file_id)
                store_bytes(db, storage.load(src.storage_key), f"Offer-{o.reference_no}-v{v.version}.pdf",
                            "application/pdf", current.user, "employee", emp.id, "offer_letter", f"Offer letter v{v.version}")
    if c.resume_file_id:
        src = db.get(StoredFile, c.resume_file_id)
        store_bytes(db, storage.load(src.storage_key), src.original_name, src.content_type, current.user, "employee",
                    emp.id, "resume", "Resume from recruitment")
    add_history(db, emp.id, "created", f"Hired from recruitment (candidate #{c.id})", None, current.user)
    audit(db, current.user, "candidate.convert", "employee", emp.id, f"Converted {c.full_name} to {emp.employee_code}",
          ip=client_ip(request))
    db.commit()
    db.refresh(emp)
    out = serialize_employee(emp)
    out["temporary_password"] = temp_pw
    return out


# ------------------------------------------------------------------ interviews

@router.get("/interviews")
def list_interviews(upcoming: bool = False, mine: bool = False, current: CurrentUser = Depends(view),
                    db: Session = Depends(get_db)):
    from app.db.base import utcnow
    stmt = select(Interview).order_by(Interview.scheduled_at)
    if upcoming:
        stmt = stmt.where(Interview.scheduled_at >= utcnow(), Interview.status == "scheduled")
    if mine:
        stmt = stmt.where(Interview.interviewer_id == current.employee_id)
    return [_iv(i) for i in db.scalars(stmt.limit(200)).unique()]


@router.post("/candidates/{cid}/interviews", status_code=201)
def schedule_interview(cid: int, body: InterviewIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    c = get_or_404(db, Candidate, cid, "Candidate")
    if c.status in ("hired", "rejected", "withdrawn"):
        raise HTTPException(409, f"Cannot schedule interviews for a {c.status} candidate")
    data = body.model_dump()
    if data["scheduled_at"].tzinfo:
        from datetime import timezone
        data["scheduled_at"] = data["scheduled_at"].astimezone(timezone.utc).replace(tzinfo=None)
    i = Interview(candidate_id=cid, **data)
    db.add(i)
    if c.status in ("applied", "screening"):
        c.status = "interview"
    db.flush()
    if i.interviewer_id:
        notify(db, user_ids_for_employees(db, [i.interviewer_id]), "Interview scheduled",
               f"{body.round_name} with {c.full_name}", f"/recruitment/candidates/{cid}", "recruitment")
    audit(db, current.user, "interview.schedule", "candidate", cid, f"{body.round_name} scheduled")
    db.commit()
    db.refresh(i)
    return _iv(i)


@router.put("/interviews/{iid}")
def update_interview(iid: int, body: InterviewIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    i = get_or_404(db, Interview, iid, "Interview")
    data = body.model_dump()
    if data["scheduled_at"].tzinfo:
        from datetime import timezone
        data["scheduled_at"] = data["scheduled_at"].astimezone(timezone.utc).replace(tzinfo=None)
    for k, v in data.items():
        setattr(i, k, v)
    db.commit()
    return _iv(i)


@router.post("/interviews/{iid}/feedback")
def interview_feedback(iid: int, body: InterviewFeedbackIn, current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    i = get_or_404(db, Interview, iid, "Interview")
    if not (current.has("recruitment.manage") or (current.employee_id and i.interviewer_id == current.employee_id)):
        raise HTTPException(403, "Only the interviewer or recruiters can submit feedback")
    for k, v in body.model_dump().items():
        setattr(i, k, v)
    audit(db, current.user, "interview.feedback", "candidate", i.candidate_id, f"Feedback for {i.round_name}")
    db.commit()
    return _iv(i)


@router.delete("/interviews/{iid}")
def delete_interview(iid: int, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    i = get_or_404(db, Interview, iid, "Interview")
    db.delete(i)
    db.commit()
    return {"ok": True}
