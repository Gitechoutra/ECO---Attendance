from fastapi import APIRouter

from app.api.routes import (
    admin, ai, attendance, auth, clients, communication, dashboard, email, employees, expenses, files, leave,
    notifications, offers, payroll, projects, recruitment, reports,
)

api_router = APIRouter()
for module in (auth, dashboard, employees, attendance, leave, projects, clients, email, recruitment, offers, payroll,
               expenses, communication, reports, ai, admin, files, notifications):
    api_router.include_router(module.router)
