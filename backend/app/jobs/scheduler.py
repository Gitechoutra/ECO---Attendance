"""In-process background jobs (APScheduler). Run a single API worker with jobs enabled, or set
SCHEDULER_ENABLED=false on extra workers to avoid duplicate runs."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.jobs import tasks

log = logging.getLogger("echoutra.jobs")


def start_scheduler() -> BackgroundScheduler:
    s = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1})
    s.add_job(tasks.overdue_task_reminders, "cron", hour=3, minute=30, id="overdue_tasks")  # 09:00 IST
    s.add_job(tasks.email_followup_reminders, "interval", minutes=15, id="email_followups")
    s.add_job(tasks.sync_email_accounts, "interval", minutes=10, id="email_sync")
    s.add_job(tasks.purge_biometrics, "cron", hour=20, minute=0, id="biometric_retention")
    s.add_job(tasks.purge_expired_tokens, "cron", hour=21, minute=0, id="token_cleanup")
    s.add_job(tasks.celebration_notifications, "cron", hour=2, minute=30, id="celebrations")
    s.start()
    log.info("Background scheduler started with %d jobs", len(s.get_jobs()))
    return s
