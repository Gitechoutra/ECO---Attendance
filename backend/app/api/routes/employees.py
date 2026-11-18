from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, get_current, require, require_employee
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Department, Designation, Employee, EmployeeHistory, Role, StoredFile, User
from app.schemas.employees import (
    AccountIn, DeactivateIn, DepartmentIn, DesignationIn, EmployeeCreate, EmployeeSelfUpdate, EmployeeUpdate,
)
from app.services.auth import revoke_all
from app.services.common import audit, get_or_404, paginate
from app.services.employees import (
    add_history, allocate_leave_balances, apply_employee_fields, create_login, next_employee_code,
    serialize_employee, temp_password, validate_refs,
)
from app.services.storage import IMAGE_TYPES, delete_file, store_upload

router = APIRouter(tags=["Employees"])


# ------------------------------------------------------------------ Departments

def _dept(d: Department, count: int = 0) -> dict:
    return {"id": d.id, "name": d.name, "code": d.code, "description": d.description, "is_active": d.is_active,
            "head": {"id": d.head.id, "full_name": d.head.full_name} if d.head else None, "head_id": d.head_id,
            "employee_count": count}


@router.get("/departments")
def list_departments(current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Employee.department_id, func.count()).where(Employee.status != "inactive")
                             .group_by(Employee.department_id)).all())
    return [_dept(d, counts.get(d.id, 0)) for d in db.scalars(select(Department).order_by(Department.name))]


@router.post("/departments", status_code=201)
def create_department(body: DepartmentIn, request: Request, current: CurrentUser = Depends(require("departments.manage")),
                      db: Session = Depends(get_db)):
    if db.scalar(select(Department.id).where(or_(func.lower(Department.name) == body.name.lower(),
                                                 func.lower(Department.code) == body.code.lower()))):
        raise HTTPException(409, "A department with this name or code already exists")
    d = Department(**body.model_dump())
    d.code = d.code.upper()
    db.add(d)
    db.flush()
    audit(db, current.user, "department.create", "department", d.id, f"Created department {d.name}", ip=client_ip(request))
    db.commit()
    return _dept(d)


@router.put("/departments/{dept_id}")
def update_department(dept_id: int, body: DepartmentIn, request: Request,
                      current: CurrentUser = Depends(require("departments.manage")), db: Session = Depends(get_db)):
    d = get_or_404(db, Department, dept_id, "Department")
    dup = db.scalar(select(Department.id).where(Department.id != dept_id, or_(
        func.lower(Department.name) == body.name.lower(), func.lower(Department.code) == body.code.lower())))
    if dup:
        raise HTTPException(409, "A department with this name or code already exists")
    if body.head_id and not db.get(Employee, body.head_id):
        raise HTTPException(422, "Department head not found")
    for k, v in body.model_dump().items():
        setattr(d, k, v)
    d.code = d.code.upper()
    audit(db, current.user, "department.update", "department", d.id, f"Updated department {d.name}", ip=client_ip(request))
    db.commit()
    return _dept(d)


@router.delete("/departments/{dept_id}")
def delete_department(dept_id: int, request: Request, current: CurrentUser = Depends(require("departments.manage")),
                      db: Session = Depends(get_db)):
    d = get_or_404(db, Department, dept_id, "Department")
    if db.scalar(select(func.count()).select_from(Employee).where(Employee.department_id == dept_id)):
        raise HTTPException(409, "Department has employees. Reassign them or mark the department inactive instead.")
    audit(db, current.user, "department.delete", "department", d.id, f"Deleted department {d.name}", ip=client_ip(request))
    db.delete(d)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ Designations

def _desig(d: Designation) -> dict:
    return {"id": d.id, "title": d.title, "level": d.level, "is_active": d.is_active, "department_id": d.department_id,
            "department": d.department.name if d.department else None}


@router.get("/designations")
def list_designations(current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    return [_desig(d) for d in db.scalars(select(Designation).order_by(Designation.level, Designation.title))]


@router.post("/designations", status_code=201)
def create_designation(body: DesignationIn, current: CurrentUser = Depends(require("departments.manage")),
                       db: Session = Depends(get_db)):
    if db.scalar(select(Designation.id).where(func.lower(Designation.title) == body.title.lower())):
        raise HTTPException(409, "Designation already exists")
    d = Designation(**body.model_dump())
    db.add(d)
    db.flush()
    audit(db, current.user, "designation.create", "designation", d.id, f"Created designation {d.title}")
    db.commit()
    return _desig(d)


@router.put("/designations/{des_id}")
def update_designation(des_id: int, body: DesignationIn, current: CurrentUser = Depends(require("departments.manage")),
                       db: Session = Depends(get_db)):
    d = get_or_404(db, Designation, des_id, "Designation")
    if db.scalar(select(Designation.id).where(Designation.id != des_id,
                                              func.lower(Designation.title) == body.title.lower())):
        raise HTTPException(409, "Designation already exists")
    for k, v in body.model_dump().items():
        setattr(d, k, v)
    audit(db, current.user, "designation.update", "designation", d.id, f"Updated designation {d.title}")
    db.commit()
    return _desig(d)


@router.delete("/designations/{des_id}")
def delete_designation(des_id: int, current: CurrentUser = Depends(require("departments.manage")),
                       db: Session = Depends(get_db)):
    d = get_or_404(db, Designation, des_id, "Designation")
    if db.scalar(select(func.count()).select_from(Employee).where(Employee.designation_id == des_id)):
        raise HTTPException(409, "Designation is assigned to employees. Mark it inactive instead.")
    db.delete(d)
    audit(db, current.user, "designation.delete", "designation", des_id, f"Deleted designation {d.title}")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ Employees

def _can_view_employee(current: CurrentUser, emp: Employee) -> bool:
    return current.has("employees.view_all") or current.employee_id == emp.id


@router.get("/employees/directory")
def directory(q: str | None = None, department_id: int | None = None, include_inactive: bool = False,
              current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    """Lightweight list for pickers and the people directory (no private data)."""
    stmt = select(Employee).order_by(Employee.first_name, Employee.last_name)
    if not include_inactive:
        stmt = stmt.where(Employee.status != "inactive")
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Employee.first_name.ilike(like), Employee.last_name.ilike(like),
                              Employee.employee_code.ilike(like), Employee.email.ilike(like)))
    return [serialize_employee(e, include_private=False) for e in db.scalars(stmt).unique()]


@router.get("/employees")
def list_employees(q: str | None = None, department_id: int | None = None, designation_id: int | None = None,
                   status: str | None = None, employment_type: str | None = None, page: int = 1,
                   page_size: int = 20, sort: str = "name",
                   current: CurrentUser = Depends(require("employees.view_all")), db: Session = Depends(get_db)):
    stmt = select(Employee)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Employee.first_name.ilike(like), Employee.last_name.ilike(like),
                              Employee.employee_code.ilike(like), Employee.email.ilike(like),
                              Employee.phone.ilike(like)))
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if designation_id:
        stmt = stmt.where(Employee.designation_id == designation_id)
    if status:
        stmt = stmt.where(Employee.status == status)
    if employment_type:
        stmt = stmt.where(Employee.employment_type == employment_type)
    order = {"name": (Employee.first_name, Employee.last_name), "code": (Employee.employee_code,),
             "joining": (Employee.joining_date.desc(),), "recent": (Employee.id.desc(),)}.get(sort, (Employee.first_name,))
    stmt = stmt.order_by(*order)
    return paginate(db, stmt, page, page_size, lambda e: serialize_employee(e, include_private=False))


@router.get("/employees/next-code")
def employee_next_code(current: CurrentUser = Depends(require("employees.manage")), db: Session = Depends(get_db)):
    return {"employee_code": next_employee_code(db)}


@router.get("/employees/me")
def my_profile(current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    return serialize_employee(db.get(Employee, current.employee_id), sensitive=False)


@router.put("/employees/me")
def update_my_profile(body: EmployeeSelfUpdate, current: CurrentUser = Depends(require_employee),
                      db: Session = Depends(get_db)):
    emp = db.get(Employee, current.employee_id)
    changes = apply_employee_fields(emp, body.model_dump(exclude_unset=True))
    if changes:
        add_history(db, emp.id, "self_update", "Employee updated personal details", changes, current.user)
        audit(db, current.user, "employee.self_update", "employee", emp.id, "Updated own profile", {"fields": list(changes)})
    db.commit()
    return serialize_employee(emp)


@router.get("/employees/{emp_id}")
def get_employee(emp_id: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    if not _can_view_employee(current, emp):
        # Allow basic profile for colleagues
        return serialize_employee(emp, include_private=False)
    return serialize_employee(emp, sensitive=current.has("employees.view_sensitive"))


@router.post("/employees", status_code=201)
def create_employee(body: EmployeeCreate, request: Request, current: CurrentUser = Depends(require("employees.manage")),
                    db: Session = Depends(get_db)):
    data = body.model_dump(exclude={"create_login", "role_code"})
    validate_refs(db, data)
    if body.role_code == "super_admin" and current.role != "super_admin":
        raise HTTPException(403, "Only a Super Admin can grant the Super Admin role")
    emp = Employee(employee_code=next_employee_code(db), joining_date=body.joining_date, first_name=body.first_name,
                   email=body.email)
    apply_employee_fields(emp, data)
    db.add(emp)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Duplicate employee code or email — please retry")
    temp_pw = None
    if body.create_login:
        _, temp_pw = create_login(db, emp, body.role_code)
    allocate_leave_balances(db, emp)
    add_history(db, emp.id, "created", f"Employee profile created ({emp.employee_code})", None, current.user)
    audit(db, current.user, "employee.create", "employee", emp.id, f"Created employee {emp.full_name} ({emp.employee_code})",
          ip=client_ip(request))
    db.commit()
    db.refresh(emp)
    out = serialize_employee(emp, sensitive=current.has("employees.view_sensitive"))
    out["temporary_password"] = temp_pw  # shown once to HR; user must change at first login
    return out


@router.put("/employees/{emp_id}")
def update_employee(emp_id: int, body: EmployeeUpdate, request: Request,
                    current: CurrentUser = Depends(require("employees.manage")), db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    data = body.model_dump()
    validate_refs(db, data, emp_id)
    old_desig, old_dept = emp.designation_id, emp.department_id
    old_email = emp.email
    changes = apply_employee_fields(emp, data)
    if not changes:
        return serialize_employee(emp, sensitive=current.has("employees.view_sensitive"))
    event = "updated"
    if emp.designation_id != old_desig:
        event = "designation_changed"
    elif emp.department_id != old_dept:
        event = "transferred"
    if emp.email != old_email and emp.user:
        if db.scalar(select(User.id).where(func.lower(User.email) == emp.email, User.id != emp.user.id)):
            raise HTTPException(409, "Another user account already uses this email")
        emp.user.email = emp.email
    add_history(db, emp.id, event, f"Profile updated: {', '.join(changes)}", changes, current.user)
    audit(db, current.user, "employee.update", "employee", emp.id, f"Updated employee {emp.full_name}",
          {"fields": list(changes)}, ip=client_ip(request))
    db.commit()
    return serialize_employee(emp, sensitive=current.has("employees.view_sensitive"))


@router.post("/employees/{emp_id}/deactivate")
def deactivate_employee(emp_id: int, body: DeactivateIn, request: Request,
                        current: CurrentUser = Depends(require("employees.manage")), db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    if emp.id == current.employee_id:
        raise HTTPException(400, "You cannot deactivate your own profile")
    if body.exit_date < emp.joining_date:
        raise HTTPException(422, "Exit date cannot be before joining date")
    emp.status, emp.exit_date, emp.exit_reason = body.status, body.exit_date, body.exit_reason
    if body.status == "inactive" and emp.user:
        emp.user.is_active = False
        revoke_all(db, emp.user)
    add_history(db, emp.id, "deactivated" if body.status == "inactive" else "notice",
                f"Status set to {body.status}. Exit date {body.exit_date}. Reason: {body.exit_reason}", None, current.user)
    audit(db, current.user, "employee.deactivate", "employee", emp.id, f"{emp.full_name} → {body.status}",
          ip=client_ip(request))
    db.commit()
    return serialize_employee(emp)


@router.post("/employees/{emp_id}/reactivate")
def reactivate_employee(emp_id: int, request: Request, current: CurrentUser = Depends(require("employees.manage")),
                        db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    emp.status, emp.exit_date, emp.exit_reason = "active", None, None
    if emp.user:
        emp.user.is_active = True
    add_history(db, emp.id, "reactivated", "Employee reactivated", None, current.user)
    audit(db, current.user, "employee.reactivate", "employee", emp.id, f"Reactivated {emp.full_name}", ip=client_ip(request))
    db.commit()
    return serialize_employee(emp)


@router.post("/employees/{emp_id}/account", status_code=201)
def create_account(emp_id: int, body: AccountIn,
                   current: CurrentUser = Depends(require("employees.manage", "admin.users")), db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    if emp.user:
        raise HTTPException(409, "Employee already has a login account")
    if body.role_code == "super_admin" and current.role != "super_admin":
        raise HTTPException(403, "Only a Super Admin can grant the Super Admin role")
    user, pw = create_login(db, emp, body.role_code)
    audit(db, current.user, "user.create", "user", user.id, f"Login created for {emp.full_name}")
    db.commit()
    return {"user_id": user.id, "email": user.email, "temporary_password": pw}


@router.post("/employees/{emp_id}/reset-password")
def reset_password(emp_id: int, request: Request, current: CurrentUser = Depends(require("admin.users")),
                   db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    user = emp.user
    if not user:
        raise HTTPException(404, "Employee has no login account")
    if user.role.code == "super_admin" and current.role != "super_admin":
        raise HTTPException(403, "Only a Super Admin can reset a Super Admin password")
    pw = temp_password()
    user.password_hash = hash_password(pw)
    user.must_change_password = True
    user.failed_logins, user.locked_until = 0, None
    revoke_all(db, user)
    audit(db, current.user, "user.reset_password", "user", user.id, f"Password reset for {emp.full_name}",
          ip=client_ip(request))
    db.commit()
    return {"temporary_password": pw}


@router.post("/employees/{emp_id}/photo")
async def upload_photo(emp_id: int, file: UploadFile = File(...), current: CurrentUser = Depends(get_current),
                       db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    if not (current.has("employees.manage") or current.employee_id == emp.id):
        raise HTTPException(403, "Not allowed")
    f = await store_upload(db, file, current.user, "employee_photo", emp.id, "photo", allowed=IMAGE_TYPES)
    old = db.get(StoredFile, emp.photo_file_id) if emp.photo_file_id else None
    emp.photo_file_id = f.id
    if old:
        db.flush()
        delete_file(db, old)
    db.commit()
    return {"photo_file_id": f.id}


@router.get("/employees/{emp_id}/documents")
def list_documents(emp_id: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    if not _can_view_employee(current, emp):
        raise HTTPException(403, "Not allowed")
    rows = db.scalars(select(StoredFile).where(StoredFile.entity_type == "employee", StoredFile.entity_id == emp_id)
                      .order_by(StoredFile.created_at.desc()))
    return [_file(f) for f in rows]


def _file(f: StoredFile) -> dict:
    return {"id": f.id, "name": f.original_name, "content_type": f.content_type, "size": f.size_bytes,
            "category": f.category, "description": f.description, "created_at": f.created_at,
            "uploaded_by": f.uploaded_by.email if f.uploaded_by else None}


@router.post("/employees/{emp_id}/documents", status_code=201)
async def upload_document(emp_id: int, file: UploadFile = File(...), category: str = Form("other"),
                          description: str | None = Form(None), current: CurrentUser = Depends(get_current),
                          db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    if not (current.has("employees.manage") or current.employee_id == emp.id):
        raise HTTPException(403, "Not allowed")
    f = await store_upload(db, file, current.user, "employee", emp.id, category[:60], description)
    add_history(db, emp.id, "document", f"Document uploaded: {f.original_name} ({category})", None, current.user)
    audit(db, current.user, "employee.document_upload", "employee", emp.id, f"Uploaded {f.original_name}")
    db.commit()
    return _file(f)


@router.delete("/employees/{emp_id}/documents/{file_id}")
def delete_document(emp_id: int, file_id: int, current: CurrentUser = Depends(require("employees.manage")),
                    db: Session = Depends(get_db)):
    f = get_or_404(db, StoredFile, file_id, "Document")
    if f.entity_type != "employee" or f.entity_id != emp_id:
        raise HTTPException(404, "Document not found")
    add_history(db, emp_id, "document", f"Document removed: {f.original_name}", None, current.user)
    audit(db, current.user, "employee.document_delete", "employee", emp_id, f"Deleted {f.original_name}")
    delete_file(db, f)
    db.commit()
    return {"ok": True}


@router.get("/employees/{emp_id}/history")
def employee_history(emp_id: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    emp = get_or_404(db, Employee, emp_id, "Employee")
    if not _can_view_employee(current, emp):
        raise HTTPException(403, "Not allowed")
    rows = db.scalars(select(EmployeeHistory).where(EmployeeHistory.employee_id == emp_id)
                      .order_by(EmployeeHistory.created_at.desc()))
    return [{"id": h.id, "event_type": h.event_type, "description": h.description, "changes": h.changes,
             "changed_by": h.changed_by.email if h.changed_by else None, "created_at": h.created_at} for h in rows]


@router.get("/roles/options")
def role_options(current: CurrentUser = Depends(require("employees.manage")), db: Session = Depends(get_db)):
    return [{"code": r.code, "name": r.name} for r in db.scalars(select(Role).order_by(Role.id))]
