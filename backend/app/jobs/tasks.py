import logging
from datetime import timedelta

from sqlalchemy import delete, extract, or_, select

from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models import (
    BiometricConsent, EmailAccount, EmailFollowUp, Employee, FaceProfile, LivenessChallenge, RefreshToken, Task, User,
)
from app.services.common import audit, get_company, notify, today_local, user_ids_for_employees

log = logging.getLogger("echoutra.jobs")


def _safe(fn):
    def wrapper():
        try:
            fn()
        except Exception:  # noqa: BLE001
            log.exception("Job %s failed", fn.__name__)
    wrapper.__name__ = fn.__name__
    return wrapper


@_safe
def overdue_task_reminders():
    with SessionLocal() as db:
        today = today_local(db)
        tasks = db.scalars(select(Task).where(Task.due_date < today, Task.status != "done",
                                              or_(Task.last_overdue_reminder.is_(None),
                                                  Task.last_overdue_reminder < today))).unique().all()
        for t in tasks:
            recipients = user_ids_for_employees(db, [t.assignee_id, t.project.manager_id if t.project else None])
            days = (today - t.due_date).days
            notify(db, recipients, "Task overdue", f"“{t.title}” is {days} day(s) overdue.", f"/tasks/{t.id}", "task")
            t.last_overdue_reminder = today
        db.commit()
        log.info("Overdue reminders sent for %d tasks", len(tasks))


@_safe
def email_followup_reminders():
    with SessionLocal() as db:
        due = db.scalars(select(EmailFollowUp).where(EmailFollowUp.is_done.is_(False), EmailFollowUp.due_at <= utcnow(),
                                                     EmailFollowUp.reminded_at.is_(None))).all()
        for f in due:
            notify(db, [f.user_id], "Email follow-up due", f"Follow up: {f.message.subject or '(no subject)'}"
                   + (f" — {f.note}" if f.note else ""), f"/email?message={f.message_id}", "email")
            f.reminded_at = utcnow()
        db.commit()


@_safe
def sync_email_accounts():
    from app.services.email_sync import sync_account

    with SessionLocal() as db:
        ids = list(db.scalars(select(EmailAccount.id).where(EmailAccount.sync_status != "disconnected")))
    for aid in ids:
        with SessionLocal() as db:
            acc = db.get(EmailAccount, aid)
            try:
                sync_account(db, acc)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                acc = db.get(EmailAccount, aid)
                acc.sync_status, acc.sync_error = "error", str(exc)[:500]
                db.commit()


@_safe
def purge_biometrics():
    """Delete face templates of employees who left more than `biometric_retention_days` ago."""
    with SessionLocal() as db:
        days = get_company(db).biometric_retention_days
        cutoff = today_local(db) - timedelta(days=days)
        emps = db.scalars(select(Employee.id).where(Employee.status == "inactive", Employee.exit_date <= cutoff)).all()
        n = 0
        for p in db.scalars(select(FaceProfile).where(FaceProfile.employee_id.in_(emps))).all():
            for c in db.scalars(select(BiometricConsent).where(BiometricConsent.employee_id == p.employee_id,
                                                               BiometricConsent.revoked_at.is_(None))):
                c.revoked_at = utcnow()
            audit(db, None, "biometric.retention_purge", "employee", p.employee_id, "Face template purged (retention)")
            db.delete(p)
            n += 1
        db.execute(delete(LivenessChallenge).where(LivenessChallenge.expires_at < utcnow() - timedelta(days=1)))
        db.commit()
        log.info("Biometric retention purge removed %d templates", n)


@_safe
def purge_expired_tokens():
    with SessionLocal() as db:
        db.execute(delete(RefreshToken).where(RefreshToken.expires_at < utcnow() - timedelta(days=1)))
        db.commit()


@_safe
def celebration_notifications():
    with SessionLocal() as db:
        today = today_local(db)
        everyone = list(db.scalars(select(User.id).where(User.is_active.is_(True))))
        emps = db.scalars(select(Employee).where(Employee.status != "inactive")).unique().all()
        for e in emps:
            if e.date_of_birth and (e.date_of_birth.month, e.date_of_birth.day) == (today.month, today.day):
                notify(db, everyone, f"🎂 Happy birthday, {e.first_name}!", f"Wish {e.full_name} a great year ahead.",
                       "/communication", "celebration")
            if (e.joining_date and e.joining_date.year < today.year
                    and (e.joining_date.month, e.joining_date.day) == (today.month, today.day)):
                yrs = today.year - e.joining_date.year
                notify(db, everyone, f"🎉 {e.full_name} completes {yrs} year(s)",
                       "Congratulate them on their work anniversary.", "/communication", "celebration")
        db.commit()


_ = extract
