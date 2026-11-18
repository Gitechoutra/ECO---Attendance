"""Test harness. Uses a SEPARATE database (<DB_NAME>_test) that is rebuilt from migrations on every run.
The production database is never touched."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ENVIRONMENT"] = "test"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "echo_attend_test")
os.environ["LOCAL_STORAGE_PATH"] = str(ROOT / ".pytest_storage")
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["MICROSOFT_CLIENT_ID"] = ""

import itertools  # noqa: E402
from datetime import date  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402

assert settings.DB_NAME.endswith("_test"), "Refusing to run tests against a non-test database"

PASSWORD = "Passw0rd!Test"
_seq = itertools.count(1)


def _reset_database():
    server_url = settings.database_url.rsplit("/", 1)[0] + "/?charset=utf8mb4"
    eng = create_engine(server_url)
    with eng.begin() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS `{settings.DB_NAME}`"))
        c.execute(text(f"CREATE DATABASE `{settings.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    eng.dispose()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def client():
    _reset_database()
    from app.main import app
    from app.db.session import SessionLocal
    from app.services.bootstrap import seed_reference_data

    with SessionLocal() as db:
        seed_reference_data(db)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def db_session(client):
    from app.db.session import SessionLocal
    s = SessionLocal()
    yield s
    s.close()


def make_person(role: str, **emp_kwargs) -> dict:
    """Create an employee + login directly in the DB. Returns ids and credentials."""
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models import Employee, Role, User
    from app.services.employees import allocate_leave_balances, next_employee_code
    from sqlalchemy import select

    n = next(_seq)
    with SessionLocal() as db:
        emp = Employee(employee_code=next_employee_code(db), first_name=emp_kwargs.pop("first_name", f"{role.title()}"),
                       last_name=emp_kwargs.pop("last_name", f"User{n}"), email=f"{role}{n}@example.com",
                       joining_date=emp_kwargs.pop("joining_date", date(2025, 1, 1)), **emp_kwargs)
        db.add(emp)
        db.flush()
        r = db.scalar(select(Role).where(Role.code == role))
        u = User(email=emp.email, password_hash=hash_password(PASSWORD), role_id=r.id, employee_id=emp.id)
        db.add(u)
        allocate_leave_balances(db, emp, date.today().year)
        db.commit()
        return {"employee_id": emp.id, "user_id": u.id, "email": emp.email, "name": emp.full_name}


def login(client, email, password=PASSWORD) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class Actor:
    def __init__(self, client, role, **kw):
        self.info = make_person(role, **kw)
        self.client = client
        self.headers = login(client, self.info["email"])
        self.employee_id = self.info["employee_id"]
        self.user_id = self.info["user_id"]

    def get(self, url, **kw):
        return self.client.get("/api/v1" + url, headers=self.headers, **kw)

    def post(self, url, **kw):
        return self.client.post("/api/v1" + url, headers=self.headers, **kw)

    def put(self, url, **kw):
        return self.client.put("/api/v1" + url, headers=self.headers, **kw)

    def patch(self, url, **kw):
        return self.client.patch("/api/v1" + url, headers=self.headers, **kw)

    def delete(self, url, **kw):
        return self.client.delete("/api/v1" + url, headers=self.headers, **kw)


@pytest.fixture(scope="session")
def admin(client):
    return Actor(client, "super_admin")


@pytest.fixture(scope="session")
def hr(client):
    return Actor(client, "hr_admin")


@pytest.fixture(scope="session")
def pm(client):
    return Actor(client, "project_manager")


@pytest.fixture
def employee(client):
    """A fresh employee per test (so attendance/leave state never leaks between tests)."""
    return Actor(client, "employee")


@pytest.fixture(scope="session")
def set_face_required(admin):
    def _set(required: bool):
        s = admin.get("/admin/settings").json()
        body = {k: s[k] for k in ("company_name", "timezone", "currency", "employee_code_prefix", "work_start", "work_end",
                                  "grace_minutes", "half_day_minutes", "full_day_minutes", "weekly_offs",
                                  "biometric_retention_days", "session_timeout_minutes")}
        body["require_face_for_attendance"] = required
        body["weekly_offs"] = []  # every day is a working day so tests are date-independent
        r = admin.put("/admin/settings", json=body)
        assert r.status_code == 200, r.text
    return _set
