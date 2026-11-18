from fastapi import APIRouter

from app.api.routes import attendance, auth, employees, files, leave, notifications

api_router = APIRouter()
for module in (auth, employees, attendance, leave, files, notifications):
    api_router.include_router(module.router)
