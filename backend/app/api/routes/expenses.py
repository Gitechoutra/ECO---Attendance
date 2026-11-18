from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current, require, require_employee
from app.db.base import utcnow
from app.db.session import get_db
from app.models import Expense, ExpenseCategory, Project, StoredFile
from app.services.common import (
    audit, get_or_404, notify, paginate, today_local, user_ids_for_employees, user_ids_with_permission,
)
from app.services.employees import employee_brief
from app.services.storage import delete_file, store_upload
from app.services.work import can_view_project

router = APIRouter(prefix="/expenses", tags=["Expenses"])
RECEIPT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    monthly_limit: float | None = Field(None, ge=0)
    requires_receipt: bool = True
    is_active: bool = True


class ReviewIn(BaseModel):
    approve: bool
    note: str | None = Field(None, max_length=500)


class ReimburseIn(BaseModel):
    reference: str | None = Field(None, max_length=120)


def _cat(c: ExpenseCategory) -> dict:
    return {"id": c.id, "name": c.name, "monthly_limit": float(c.monthly_limit) if c.monthly_limit is not None else None,
            "requires_receipt": c.requires_receipt, "is_active": c.is_active}


def _exp(e: Expense) -> dict:
    return {"id": e.id, "title": e.title, "amount": float(e.amount), "currency": e.currency, "expense_date": e.expense_date,
            "description": e.description, "status": e.status, "receipt_file_id": e.receipt_file_id,
            "category": {"id": e.category.id, "name": e.category.name}, "category_id": e.category_id,
            "project": {"id": e.project.id, "name": e.project.name} if e.project else None, "project_id": e.project_id,
            "employee": employee_brief(e.employee), "employee_id": e.employee_id, "review_note": e.review_note,
            "reviewed_at": e.reviewed_at, "reimbursed_at": e.reimbursed_at, "reimbursement_ref": e.reimbursement_ref,
            "created_at": e.created_at}


@router.get("/categories")
def categories(current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    return [_cat(c) for c in db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name))]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, current: CurrentUser = Depends(require("expenses.approve")), db: Session = Depends(get_db)):
    if db.scalar(select(ExpenseCategory.id).where(func.lower(ExpenseCategory.name) == body.name.lower())):
        raise HTTPException(409, "Category exists")
    c = ExpenseCategory(**body.model_dump())
    db.add(c)
    db.commit()
    return _cat(c)


@router.put("/categories/{cid}")
def update_category(cid: int, body: CategoryIn, current: CurrentUser = Depends(require("expenses.approve")),
                    db: Session = Depends(get_db)):
    c = get_or_404(db, ExpenseCategory, cid, "Category")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return _cat(c)


@router.get("")
def list_expenses(scope: str = "mine", status: str | None = None, category_id: int | None = None,
                  employee_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
                  page: int = 1, page_size: int = 20, current: CurrentUser = Depends(get_current),
                  db: Session = Depends(get_db)):
    stmt = select(Expense).order_by(Expense.created_at.desc())
    if scope == "all":
        if not current.has_any("expenses.view_all", "expenses.approve"):
            raise HTTPException(403, "Not allowed")
        if employee_id:
            stmt = stmt.where(Expense.employee_id == employee_id)
    else:
        stmt = stmt.where(Expense.employee_id == (current.employee_id or 0))
    if status:
        stmt = stmt.where(Expense.status == status)
    if category_id:
        stmt = stmt.where(Expense.category_id == category_id)
    if date_from:
        stmt = stmt.where(Expense.expense_date >= date_from)
    if date_to:
        stmt = stmt.where(Expense.expense_date <= date_to)
    out = paginate(db, stmt, page, page_size, _exp)
    total = db.scalar(select(func.coalesce(func.sum(Expense.amount), 0)).select_from(stmt.order_by(None).subquery()))
    out["sum_amount"] = float(total or 0)
    return out


@router.post("", status_code=201)
async def submit_expense(title: str = Form(..., min_length=2, max_length=200), amount: float = Form(..., gt=0, le=10_000_000),
                         expense_date: date = Form(...), category_id: int = Form(...),
                         project_id: int | None = Form(None), description: str | None = Form(None, max_length=5000),
                         receipt: UploadFile | None = File(None), current: CurrentUser = Depends(require_employee),
                         db: Session = Depends(get_db)):
    cat = get_or_404(db, ExpenseCategory, category_id, "Category")
    if not cat.is_active:
        raise HTTPException(422, "Category is not active")
    if expense_date > today_local(db):
        raise HTTPException(422, "Expense date cannot be in the future")
    if cat.requires_receipt and not receipt:
        raise HTTPException(422, f"A receipt is required for {cat.name} expenses")
    if project_id:
        get_or_404(db, Project, project_id, "Project")
        if not can_view_project(db, current, project_id):
            raise HTTPException(403, "You are not part of that project")
    e = Expense(employee_id=current.employee_id, category_id=cat.id, project_id=project_id, title=title.strip(),
                amount=amount, expense_date=expense_date, description=description)
    db.add(e)
    db.flush()
    if receipt:
        f = await store_upload(db, receipt, current.user, "expense", e.id, "receipt", allowed=RECEIPT_TYPES)
        e.receipt_file_id = f.id
    warning = None
    if cat.monthly_limit:
        spent = db.scalar(select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.employee_id == current.employee_id, Expense.category_id == cat.id,
            Expense.status.not_in(["rejected"]), func.year(Expense.expense_date) == expense_date.year,
            func.month(Expense.expense_date) == expense_date.month))
        if float(spent) > float(cat.monthly_limit):
            warning = f"Monthly {cat.name} limit of {float(cat.monthly_limit):,.0f} exceeded"
    approvers = set(user_ids_with_permission(db, "expenses.approve")) - {current.id}
    notify(db, approvers, "Expense claim submitted", f"{current.user.employee.full_name}: {title} — {amount:,.2f}"
           + (f" ({warning})" if warning else ""), "/expenses?tab=approvals", "approval")
    audit(db, current.user, "expense.submit", "expense", e.id, f"Submitted {title} {amount}")
    db.commit()
    db.refresh(e)
    return {**_exp(e), "warning": warning}


@router.delete("/{eid}")
def delete_expense(eid: int, current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    e = get_or_404(db, Expense, eid, "Expense")
    if e.employee_id != current.employee_id:
        raise HTTPException(403, "Not allowed")
    if e.status != "submitted":
        raise HTTPException(409, "Only pending claims can be withdrawn")
    if e.receipt_file_id:
        f = db.get(StoredFile, e.receipt_file_id)
        e.receipt_file_id = None
        db.flush()
        if f:
            delete_file(db, f)
    db.delete(e)
    audit(db, current.user, "expense.withdraw", "expense", eid, "Withdrew claim")
    db.commit()
    return {"ok": True}


@router.post("/{eid}/review")
def review(eid: int, body: ReviewIn, current: CurrentUser = Depends(require("expenses.approve")), db: Session = Depends(get_db)):
    e = get_or_404(db, Expense, eid, "Expense")
    if e.status != "submitted":
        raise HTTPException(409, f"Claim is already {e.status}")
    if e.employee_id == current.employee_id:
        raise HTTPException(403, "You cannot approve your own claim")
    if not body.approve and not body.note:
        raise HTTPException(422, "Please give a reason for rejection")
    e.status = "approved" if body.approve else "rejected"
    e.reviewed_by_id, e.reviewed_at, e.review_note = current.id, utcnow(), body.note
    notify(db, user_ids_for_employees(db, [e.employee_id]), f"Expense {e.status}", f"{e.title} — {float(e.amount):,.2f}"
           + (f". {body.note}" if body.note else ""), "/expenses", "expense")
    audit(db, current.user, f"expense.{e.status}", "expense", e.id, f"{e.status.title()} {e.title}")
    db.commit()
    return _exp(e)


@router.post("/{eid}/reimburse")
def reimburse(eid: int, body: ReimburseIn, current: CurrentUser = Depends(require("expenses.reimburse")),
              db: Session = Depends(get_db)):
    e = get_or_404(db, Expense, eid, "Expense")
    if e.status != "approved":
        raise HTTPException(409, "Only approved claims can be reimbursed")
    e.status, e.reimbursed_at, e.reimbursement_ref = "reimbursed", utcnow(), body.reference
    notify(db, user_ids_for_employees(db, [e.employee_id]), "Expense reimbursed", f"{e.title} — {float(e.amount):,.2f}",
           "/expenses", "expense")
    audit(db, current.user, "expense.reimburse", "expense", e.id, f"Reimbursed {e.title}")
    db.commit()
    return _exp(e)


@router.get("/stats")
def stats(year: int | None = None, current: CurrentUser = Depends(require("expenses.view_all")), db: Session = Depends(get_db)):
    year = year or today_local(db).year
    by_cat = db.execute(select(ExpenseCategory.name, func.sum(Expense.amount)).join(Expense)
                        .where(func.year(Expense.expense_date) == year, Expense.status.in_(["approved", "reimbursed"]))
                        .group_by(ExpenseCategory.name)).all()
    by_month = db.execute(select(func.month(Expense.expense_date), func.sum(Expense.amount))
                          .where(func.year(Expense.expense_date) == year, Expense.status.in_(["approved", "reimbursed"]))
                          .group_by(func.month(Expense.expense_date))).all()
    pending = db.scalar(select(func.count()).select_from(Expense).where(Expense.status == "submitted"))
    to_reimburse = db.scalar(select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.status == "approved"))
    return {"by_category": [{"name": n, "amount": float(a)} for n, a in by_cat],
            "by_month": [{"month": int(m), "amount": float(a)} for m, a in by_month],
            "pending_count": pending, "awaiting_reimbursement": float(to_reimburse or 0)}
