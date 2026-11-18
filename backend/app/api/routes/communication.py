from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current, require
from app.db.base import utcnow
from app.db.session import get_db
from app.models import Announcement, Employee, Holiday, Meeting, MeetingAttendee, Project, User
from app.services.common import audit, get_or_404, notify, paginate, today_local, user_ids_for_employees
from app.services.employees import employee_brief

router = APIRouter(tags=["Communication"])


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=20000)
    category: str = Field("general", pattern="^(general|policy|event|update|urgent)$")
    audience: str = Field("all", pattern="^(all|department|role)$")
    department_id: int | None = None
    role_code: str | None = Field(None, pattern="^(super_admin|hr_admin|project_manager|employee)$")
    is_pinned: bool = False
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def aud(self):
        if self.audience == "department" and not self.department_id:
            raise ValueError("Select a department")
        if self.audience == "role" and not self.role_code:
            raise ValueError("Select a role")
        return self


class MeetingIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(None, max_length=5000)
    start_at: datetime
    end_at: datetime
    location: str | None = Field(None, max_length=255)
    meeting_link: str | None = Field(None, max_length=500, pattern=r"^https?://")
    project_id: int | None = None
    attendee_ids: list[int] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def times(self):
        if self.end_at <= self.start_at:
            raise ValueError("Meeting must end after it starts")
        return self


class RsvpIn(BaseModel):
    response: str = Field(pattern="^(accepted|declined)$")


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _ann(a: Announcement) -> dict:
    author = a.created_by
    return {"id": a.id, "title": a.title, "body": a.body, "category": a.category, "audience": a.audience,
            "department": a.department.name if a.department else None, "department_id": a.department_id,
            "role_code": a.role_code, "is_pinned": a.is_pinned, "published_at": a.published_at, "expires_at": a.expires_at,
            "author": (author.employee.full_name if author and author.employee else author.email if author else None)}


def _audience_filter(current: CurrentUser):
    emp = current.user.employee
    conds = [Announcement.audience == "all", and_(Announcement.audience == "role", Announcement.role_code == current.role)]
    if emp and emp.department_id:
        conds.append(and_(Announcement.audience == "department", Announcement.department_id == emp.department_id))
    return or_(*conds)


@router.get("/announcements")
def announcements(include_expired: bool = False, page: int = 1, page_size: int = 20,
                  current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    stmt = select(Announcement).order_by(Announcement.is_pinned.desc(), Announcement.published_at.desc())
    if not current.has("announcements.manage"):
        stmt = stmt.where(_audience_filter(current))
    if not include_expired:
        stmt = stmt.where(or_(Announcement.expires_at.is_(None), Announcement.expires_at > utcnow()))
    return paginate(db, stmt, page, page_size, _ann)


def _recipients(db: Session, a: Announcement) -> list[int]:
    q = select(User.id).where(User.is_active.is_(True))
    if a.audience == "department":
        q = q.join(Employee, Employee.id == User.employee_id).where(Employee.department_id == a.department_id)
    elif a.audience == "role":
        from app.models import Role
        q = q.join(Role, Role.id == User.role_id).where(Role.code == a.role_code)
    return list(db.scalars(q))


@router.post("/announcements", status_code=201)
def create_announcement(body: AnnouncementIn, current: CurrentUser = Depends(require("announcements.manage")),
                        db: Session = Depends(get_db)):
    data = body.model_dump()
    data["expires_at"] = _utc(data["expires_at"])
    a = Announcement(created_by_id=current.id, **data)
    db.add(a)
    db.flush()
    notify(db, set(_recipients(db, a)) - {current.id}, f"📢 {a.title}", a.body[:200], "/communication", "announcement")
    audit(db, current.user, "announcement.publish", "announcement", a.id, a.title)
    db.commit()
    db.refresh(a)
    return _ann(a)


@router.put("/announcements/{aid}")
def update_announcement(aid: int, body: AnnouncementIn, current: CurrentUser = Depends(require("announcements.manage")),
                        db: Session = Depends(get_db)):
    a = get_or_404(db, Announcement, aid, "Announcement")
    data = body.model_dump()
    data["expires_at"] = _utc(data["expires_at"])
    for k, v in data.items():
        setattr(a, k, v)
    audit(db, current.user, "announcement.update", "announcement", a.id, a.title)
    db.commit()
    return _ann(a)


@router.delete("/announcements/{aid}")
def delete_announcement(aid: int, current: CurrentUser = Depends(require("announcements.manage")), db: Session = Depends(get_db)):
    a = get_or_404(db, Announcement, aid, "Announcement")
    db.delete(a)
    audit(db, current.user, "announcement.delete", "announcement", aid, a.title)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ meetings

def _mtg(m: Meeting, me: int | None = None) -> dict:
    mine = next((a for a in m.attendees if a.employee_id == me), None)
    return {"id": m.id, "title": m.title, "description": m.description, "start_at": m.start_at, "end_at": m.end_at,
            "location": m.location, "meeting_link": m.meeting_link, "project_id": m.project_id, "status": m.status,
            "organizer": employee_brief(m.organizer), "organizer_id": m.organizer_id,
            "attendees": [{"employee": employee_brief(a.employee), "response": a.response} for a in m.attendees],
            "my_response": mine.response if mine else None}


@router.get("/meetings")
def meetings(date_from: date | None = None, date_to: date | None = None, scope: str = "mine",
             current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    start = datetime.combine(date_from or today_local(db) - timedelta(days=7), datetime.min.time())
    end = datetime.combine(date_to or today_local(db) + timedelta(days=60), datetime.max.time())
    stmt = select(Meeting).where(Meeting.start_at.between(start - timedelta(hours=14), end + timedelta(hours=14)),
                                 Meeting.status != "cancelled").order_by(Meeting.start_at)
    if scope != "all" or not current.has("meetings.manage"):
        attending = select(MeetingAttendee.meeting_id).where(MeetingAttendee.employee_id == (current.employee_id or 0))
        stmt = stmt.where(or_(Meeting.organizer_id == current.employee_id, Meeting.id.in_(attending)))
    return [_mtg(m, current.employee_id) for m in db.scalars(stmt).unique()]


@router.post("/meetings", status_code=201)
def create_meeting(body: MeetingIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    if not current.employee_id:
        raise HTTPException(400, "Your account is not linked to an employee profile")
    if body.project_id:
        p = get_or_404(db, Project, body.project_id, "Project")
        if not (current.has("meetings.manage") or p.manager_id == current.employee_id):
            raise HTTPException(403, "Only the project manager can schedule project meetings")
    elif not current.has("meetings.manage"):
        raise HTTPException(403, "You do not have permission to schedule company meetings")
    data = body.model_dump(exclude={"attendee_ids"})
    data["start_at"], data["end_at"] = _utc(data["start_at"]), _utc(data["end_at"])
    m = Meeting(organizer_id=current.employee_id, **data)
    ids = set(body.attendee_ids) - {current.employee_id}
    valid = set(db.scalars(select(Employee.id).where(Employee.id.in_(ids or [0]), Employee.status != "inactive")))
    if ids - valid:
        raise HTTPException(422, "Some attendees were not found or are inactive")
    m.attendees = [MeetingAttendee(employee_id=i) for i in valid] + [MeetingAttendee(employee_id=current.employee_id,
                                                                                       response="accepted")]
    db.add(m)
    db.flush()
    notify(db, user_ids_for_employees(db, list(valid)), "Meeting invitation",
           f"{m.title} — {m.start_at:%d %b %Y %H:%M} UTC", "/communication?tab=meetings", "meeting")
    audit(db, current.user, "meeting.create", "meeting", m.id, m.title)
    db.commit()
    db.refresh(m)
    return _mtg(m, current.employee_id)


@router.put("/meetings/{mid}")
def update_meeting(mid: int, body: MeetingIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    m = get_or_404(db, Meeting, mid, "Meeting")
    if m.organizer_id != current.employee_id and not current.has("meetings.manage"):
        raise HTTPException(403, "Only the organizer can edit this meeting")
    data = body.model_dump(exclude={"attendee_ids"})
    data["start_at"], data["end_at"] = _utc(data["start_at"]), _utc(data["end_at"])
    for k, v in data.items():
        setattr(m, k, v)
    keep = {a.employee_id: a for a in m.attendees}
    want = set(body.attendee_ids) | {m.organizer_id}
    m.attendees = [keep.get(i) or MeetingAttendee(employee_id=i) for i in want if i]
    new = want - set(keep)
    notify(db, user_ids_for_employees(db, list(want - {current.employee_id})), "Meeting updated",
           f"{m.title} — {m.start_at:%d %b %Y %H:%M} UTC", "/communication?tab=meetings", "meeting")
    db.commit()
    db.refresh(m)
    _ = new
    return _mtg(m, current.employee_id)


@router.post("/meetings/{mid}/cancel")
def cancel_meeting(mid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    m = get_or_404(db, Meeting, mid, "Meeting")
    if m.organizer_id != current.employee_id and not current.has("meetings.manage"):
        raise HTTPException(403, "Only the organizer can cancel this meeting")
    m.status = "cancelled"
    notify(db, user_ids_for_employees(db, [a.employee_id for a in m.attendees if a.employee_id != current.employee_id]),
           "Meeting cancelled", m.title, "/communication?tab=meetings", "meeting")
    db.commit()
    return {"ok": True}


@router.post("/meetings/{mid}/rsvp")
def rsvp(mid: int, body: RsvpIn, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    m = get_or_404(db, Meeting, mid, "Meeting")
    a = next((x for x in m.attendees if x.employee_id == current.employee_id), None)
    if not a:
        raise HTTPException(403, "You are not invited to this meeting")
    a.response = body.response
    db.commit()
    return _mtg(m, current.employee_id)


# ------------------------------------------------------------------ calendar / celebrations

@router.get("/calendar/events")
def calendar_events(date_from: date, date_to: date, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    if (date_to - date_from).days > 120:
        raise HTTPException(422, "Range too large")
    events = []
    for h in db.scalars(select(Holiday).where(Holiday.date.between(date_from, date_to))):
        events.append({"type": "holiday", "date": h.date, "title": h.name, "optional": h.is_optional})
    emps = db.scalars(select(Employee).where(Employee.status != "inactive")).unique().all()
    d = date_from
    while d <= date_to:
        for e in emps:
            if e.date_of_birth and (e.date_of_birth.month, e.date_of_birth.day) == (d.month, d.day):
                events.append({"type": "birthday", "date": d, "title": f"{e.full_name}'s birthday",
                               "employee": employee_brief(e)})
            if e.joining_date and e.joining_date.year < d.year and (e.joining_date.month, e.joining_date.day) == (d.month, d.day):
                events.append({"type": "anniversary", "date": d, "title": f"{e.full_name} · {d.year - e.joining_date.year} yr",
                               "employee": employee_brief(e)})
        d += timedelta(days=1)
    for m in meetings(date_from, date_to, "mine", current, db):
        events.append({"type": "meeting", "date": m["start_at"].date(), "title": m["title"], "start_at": m["start_at"],
                       "end_at": m["end_at"], "id": m["id"]})
    from app.models import LeaveRequest
    for lr in db.scalars(select(LeaveRequest).where(LeaveRequest.status == "approved", LeaveRequest.start_date <= date_to,
                                                    LeaveRequest.end_date >= date_from)):
        events.append({"type": "leave", "date": max(lr.start_date, date_from), "end_date": lr.end_date,
                       "title": f"{lr.employee.full_name} on leave", "employee": employee_brief(lr.employee)})
    return sorted(events, key=lambda e: (str(e["date"]), e["type"]))


@router.get("/celebrations")
def celebrations(days: int = 30, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    today = today_local(db)
    out = []
    for e in db.scalars(select(Employee).where(Employee.status != "inactive")).unique():
        for kind, base in (("birthday", e.date_of_birth), ("anniversary", e.joining_date)):
            if not base:
                continue
            try:
                nxt = base.replace(year=today.year)
            except ValueError:  # 29 Feb
                nxt = date(today.year, 3, 1)
            if nxt < today:
                try:
                    nxt = base.replace(year=today.year + 1)
                except ValueError:
                    nxt = date(today.year + 1, 3, 1)
            delta = (nxt - today).days
            if delta <= days and not (kind == "anniversary" and nxt.year - base.year < 1):
                out.append({"type": kind, "date": nxt, "in_days": delta, "employee": employee_brief(e),
                            "years": nxt.year - base.year if kind == "anniversary" else None})
    return sorted(out, key=lambda x: x["in_days"])
