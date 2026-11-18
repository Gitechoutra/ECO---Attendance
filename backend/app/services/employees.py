import re
import secrets
import string
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import decrypt_str, encrypt_str, hash_password
from app.models import Employee, EmployeeHistory, LeaveBalance, LeaveType, Role, User
from app.services.common import get_company

SENSITIVE_FIELDS = {"bank_account": "bank_account_enc", "pan": "pan_enc", "national_id": "national_id_enc"}


def next_employee_code(db: Session) -> str:
    prefix = get_company(db).employee_code_prefix or "ECH"
    codes = db.scalars(select(Employee.employee_code).where(Employee.employee_code.like(f"{prefix}%"))).all()
    nums = [int(m.group(1)) for c in codes if (m := re.match(rf"^{re.escape(prefix)}(\d+)$", c))]
    return f"{prefix}{(max(nums) + 1 if nums else 1):04d}"


def temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(10)) + secrets.choice("!@#$%") + "9a"
        if any(c.isupper() for c in pw) and any(c.islower() for c in pw):
            return pw


def mask(value: str | None) -> str | None:
    if not value:
        return value
    return "•" * max(len(value) - 4, 2) + value[-4:]


def employee_brief(e: Employee | None) -> dict | None:
    if not e:
        return None
    return {"id": e.id, "employee_code": e.employee_code, "full_name": e.full_name,
            "designation": e.designation.title if e.designation else None, "photo_file_id": e.photo_file_id,
            "email": e.email}


def serialize_employee(e: Employee, sensitive: bool = False, include_private: bool = True) -> dict:
    data = {
        "id": e.id, "employee_code": e.employee_code, "first_name": e.first_name, "last_name": e.last_name,
        "full_name": e.full_name, "email": e.email, "phone": e.phone,
        "department": {"id": e.department.id, "name": e.department.name} if e.department else None,
        "designation": {"id": e.designation.id, "title": e.designation.title} if e.designation else None,
        "department_id": e.department_id, "designation_id": e.designation_id,
        "manager": employee_brief(e.manager) if e.manager_id else None, "manager_id": e.manager_id,
        "employment_type": e.employment_type, "work_location": e.work_location,
        "joining_date": e.joining_date, "status": e.status, "photo_file_id": e.photo_file_id,
        "exit_date": e.exit_date,
    }
    if include_private:
        data.update({
            "personal_email": e.personal_email, "date_of_birth": e.date_of_birth, "gender": e.gender,
            "marital_status": e.marital_status, "blood_group": e.blood_group, "address": e.address,
            "city": e.city, "state": e.state, "country": e.country, "postal_code": e.postal_code,
            "emergency_contact_name": e.emergency_contact_name,
            "emergency_contact_phone": e.emergency_contact_phone,
            "probation_end_date": e.probation_end_date, "exit_reason": e.exit_reason,
            "bank_name": e.bank_name, "bank_ifsc": e.bank_ifsc,
        })
        for plain, enc in SENSITIVE_FIELDS.items():
            raw = decrypt_str(getattr(e, enc))
            data[plain] = raw if sensitive else mask(raw)
        user = e.user
        data["account"] = None if not user else {
            "user_id": user.id, "role": user.role.code, "role_name": user.role.name, "is_active": user.is_active,
            "last_login_at": user.last_login_at,
        }
    return data


def apply_employee_fields(e: Employee, data: dict) -> dict:
    changes = {}
    for plain, enc in SENSITIVE_FIELDS.items():
        if plain in data:
            val = data.pop(plain)
            if val is not None and "•" in val:  # masked value echoed back — ignore
                continue
            new = encrypt_str(val.strip()) if val else None
            if decrypt_str(getattr(e, enc)) != (val.strip() if val else None):
                changes[plain] = ["(hidden)", "(updated)"]
                setattr(e, enc, new)
    for k, v in data.items():
        old = getattr(e, k)
        if old != v:
            changes[k] = [str(old) if old is not None else None, str(v) if v is not None else None]
            setattr(e, k, v)
    return changes


def validate_refs(db: Session, data: dict, employee_id: int | None = None) -> None:
    from app.models import Department, Designation

    if data.get("department_id") and not db.get(Department, data["department_id"]):
        raise HTTPException(422, "Department not found")
    if data.get("designation_id") and not db.get(Designation, data["designation_id"]):
        raise HTTPException(422, "Designation not found")
    if data.get("manager_id"):
        if employee_id and data["manager_id"] == employee_id:
            raise HTTPException(422, "An employee cannot report to themselves")
        mgr = db.get(Employee, data["manager_id"])
        if not mgr or mgr.status == "inactive":
            raise HTTPException(422, "Reporting manager not found or inactive")
    q = select(Employee.id).where(func.lower(Employee.email) == data["email"].lower())
    if employee_id:
        q = q.where(Employee.id != employee_id)
    if db.scalar(q):
        raise HTTPException(409, "An employee with this email already exists")


def create_login(db: Session, emp: Employee, role_code: str) -> tuple[User, str]:
    if db.scalar(select(User.id).where(func.lower(User.email) == emp.email.lower())):
        raise HTTPException(409, "A user account with this email already exists")
    role = db.scalar(select(Role).where(Role.code == role_code))
    if not role:
        raise HTTPException(422, "Role not found")
    pw = temp_password()
    user = User(email=emp.email, password_hash=hash_password(pw), role_id=role.id, employee_id=emp.id,
                must_change_password=True)
    db.add(user)
    db.flush()
    return user, pw


def allocate_leave_balances(db: Session, emp: Employee, year: int | None = None) -> None:
    year = year or date.today().year
    types = db.scalars(select(LeaveType).where(LeaveType.is_active.is_(True))).all()
    for lt in types:
        exists = db.scalar(select(LeaveBalance.id).where(LeaveBalance.employee_id == emp.id,
                                                         LeaveBalance.leave_type_id == lt.id,
                                                         LeaveBalance.year == year))
        if exists:
            continue
        quota = lt.annual_quota or 0
        if emp.joining_date and emp.joining_date.year == year:
            months_left = 12 - emp.joining_date.month + 1
            quota = round(quota * months_left / 12 * 2) / 2  # nearest half day
        db.add(LeaveBalance(employee_id=emp.id, leave_type_id=lt.id, year=year, allocated=quota))
    db.flush()


def add_history(db: Session, emp_id: int, event: str, description: str, changes: dict | None, user: User | None):
    db.add(EmployeeHistory(employee_id=emp_id, event_type=event, description=description[:500], changes=changes,
                           changed_by_id=user.id if user else None))
