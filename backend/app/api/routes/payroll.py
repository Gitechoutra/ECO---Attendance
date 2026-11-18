import calendar
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, client_ip, get_current, require, require_employee
from app.core.security import decrypt_str
from app.db.base import utcnow
from app.db.session import get_db
from app.models import (
    Employee, PayrollAdjustment, PayrollRun, Payslip, SalaryComponent, SalaryPayment, SalaryStructure,
    SalaryStructureItem,
)
from app.services.common import audit, get_company, get_or_404, notify, user_ids_for_employees
from app.services.employees import employee_brief, mask
from app.services.payroll import active_structure, compute_payslip, process_run
from app.services.pdf import payslip_pdf

router = APIRouter(prefix="/payroll", tags=["Payroll"])
view = require("payroll.view")
manage = require("payroll.manage")


class ComponentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_]+$")
    kind: str = Field(pattern="^(earning|deduction)$")
    calc_type: str = Field(pattern="^(fixed|percent_basic|percent_gross)$")
    default_value: float = Field(0, ge=0)
    prorate_with_attendance: bool = True
    is_active: bool = True
    description: str | None = Field(None, max_length=255)


class StructureItemIn(BaseModel):
    component_id: int
    value: float = Field(ge=0)


class StructureIn(BaseModel):
    employee_id: int
    effective_from: date
    monthly_basic: float = Field(gt=0)
    items: list[StructureItemIn] = Field(default_factory=list)
    notes: str | None = Field(None, max_length=255)


class AdjustmentIn(BaseModel):
    employee_id: int
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    kind: str = Field(pattern="^(bonus|deduction)$")
    label: str = Field(min_length=2, max_length=120)
    amount: float = Field(gt=0)


class RunIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class PayIn(BaseModel):
    paid_on: date
    mode: str = Field(pattern="^(bank_transfer|cheque|cash|upi)$")
    reference: str | None = Field(None, max_length=120)
    payslip_ids: list[int] | None = None


def _comp(c: SalaryComponent) -> dict:
    return {"id": c.id, "name": c.name, "code": c.code, "kind": c.kind, "calc_type": c.calc_type,
            "default_value": float(c.default_value), "prorate_with_attendance": c.prorate_with_attendance,
            "is_active": c.is_active, "description": c.description}


def _struct(s: SalaryStructure) -> dict:
    return {"id": s.id, "employee": employee_brief(s.employee), "employee_id": s.employee_id,
            "effective_from": s.effective_from, "monthly_basic": float(s.monthly_basic), "notes": s.notes,
            "items": [{"component_id": i.component_id, "code": i.component.code, "name": i.component.name,
                       "kind": i.component.kind, "calc_type": i.component.calc_type, "value": float(i.value)} for i in s.items]}


def _slip(p: Payslip, run: PayrollRun | None = None) -> dict:
    run = run or p.__dict__.get("_run")
    return {"id": p.id, "run_id": p.run_id, "employee": employee_brief(p.employee), "employee_id": p.employee_id,
            "working_days": p.working_days, "paid_days": p.paid_days, "lop_days": p.lop_days,
            "monthly_basic": float(p.monthly_basic), "gross_earnings": float(p.gross_earnings),
            "total_deductions": float(p.total_deductions), "bonus": float(p.bonus), "net_pay": float(p.net_pay),
            "breakdown": p.breakdown, "payment_status": p.payment_status}


def _run(r: PayrollRun, with_slips=False) -> dict:
    d = {"id": r.id, "year": r.year, "month": r.month, "period": f"{calendar.month_name[r.month]} {r.year}",
         "status": r.status, "working_days": r.working_days, "total_gross": float(r.total_gross),
         "total_deductions": float(r.total_deductions), "total_net": float(r.total_net),
         "employee_count": len(r.payslips), "paid_count": sum(1 for p in r.payslips if p.payment_status == "paid"),
         "finalized_at": r.finalized_at, "created_at": r.created_at}
    if with_slips:
        d["payslips"] = sorted([_slip(p) for p in r.payslips], key=lambda x: x["employee"]["full_name"])
    return d


# ------------------------------------------------------------------ components

@router.get("/components")
def components(current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    return [_comp(c) for c in db.scalars(select(SalaryComponent).order_by(SalaryComponent.kind.desc(), SalaryComponent.name))]


@router.post("/components", status_code=201)
def create_component(body: ComponentIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    if db.scalar(select(SalaryComponent.id).where((SalaryComponent.code == body.code.upper()) | (SalaryComponent.name == body.name))):
        raise HTTPException(409, "A component with this name or code exists")
    if body.calc_type != "fixed" and body.default_value > 100:
        raise HTTPException(422, "Percentage cannot exceed 100")
    c = SalaryComponent(**body.model_dump())
    c.code = c.code.upper()
    db.add(c)
    db.flush()
    audit(db, current.user, "payroll.component_create", "salary_component", c.id, f"Component {c.name}")
    db.commit()
    return _comp(c)


@router.put("/components/{cid}")
def update_component(cid: int, body: ComponentIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    c = get_or_404(db, SalaryComponent, cid, "Component")
    if db.scalar(select(SalaryComponent.id).where(SalaryComponent.id != cid, (SalaryComponent.code == body.code.upper()) |
                                                  (SalaryComponent.name == body.name))):
        raise HTTPException(409, "A component with this name or code exists")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    c.code = c.code.upper()
    audit(db, current.user, "payroll.component_update", "salary_component", c.id, f"Component {c.name}")
    db.commit()
    return _comp(c)


# ------------------------------------------------------------------ structures

@router.get("/structures")
def structures(current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    """Current structure (or none) for each non-inactive employee."""
    emps = db.scalars(select(Employee).where(Employee.status != "inactive").order_by(Employee.first_name)).unique().all()
    today = date.today()
    out = []
    for e in emps:
        s = active_structure(db, e.id, today) or db.scalar(select(SalaryStructure).where(SalaryStructure.employee_id == e.id)
                                                            .order_by(SalaryStructure.effective_from.desc()).limit(1))
        calc = None
        if s:
            gross = float(s.monthly_basic)
            for i in s.items:
                if i.component.kind == "earning":
                    gross += float(s.monthly_basic) * float(i.value) / 100 if i.component.calc_type == "percent_basic" else (
                        float(i.value) if i.component.calc_type == "fixed" else 0)
            calc = round(gross, 2)
        out.append({"employee": employee_brief(e), "structure": _struct(s) if s else None, "monthly_gross_estimate": calc})
    return out


@router.get("/structures/{employee_id}")
def employee_structures(employee_id: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    if employee_id != current.employee_id and not current.has("payroll.view"):
        raise HTTPException(403, "Not allowed")
    return [_struct(s) for s in db.scalars(select(SalaryStructure).where(SalaryStructure.employee_id == employee_id)
                                           .order_by(SalaryStructure.effective_from.desc()))]


@router.post("/structures", status_code=201)
def create_structure(body: StructureIn, request: Request, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    e = get_or_404(db, Employee, body.employee_id, "Employee")
    if db.scalar(select(SalaryStructure.id).where(SalaryStructure.employee_id == e.id,
                                                  SalaryStructure.effective_from == body.effective_from)):
        raise HTTPException(409, "A structure already exists for this effective date. Edit it or choose another date.")
    finalized = db.scalar(select(PayrollRun.id).where(PayrollRun.status != "draft",
                                                      (PayrollRun.year * 100 + PayrollRun.month) >= body.effective_from.year * 100 + body.effective_from.month))
    if finalized:
        raise HTTPException(409, "Payroll is already finalized for that period. Choose a later effective date.")
    ids = [i.component_id for i in body.items]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Each component can appear only once")
    s = SalaryStructure(employee_id=e.id, effective_from=body.effective_from, monthly_basic=body.monthly_basic, notes=body.notes)
    for i in body.items:
        c = get_or_404(db, SalaryComponent, i.component_id, "Component")
        if c.calc_type != "fixed" and i.value > 100:
            raise HTTPException(422, f"{c.name}: percentage cannot exceed 100")
        s.items.append(SalaryStructureItem(component_id=c.id, value=i.value))
    db.add(s)
    db.flush()
    audit(db, current.user, "payroll.structure_create", "employee", e.id,
          f"Salary structure for {e.full_name} effective {body.effective_from}", ip=client_ip(request))
    db.commit()
    db.refresh(s)
    return _struct(s)


@router.delete("/structures/{sid}")
def delete_structure(sid: int, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    s = get_or_404(db, SalaryStructure, sid, "Structure")
    if db.scalar(select(PayrollRun.id).where(PayrollRun.status != "draft",
                                             (PayrollRun.year * 100 + PayrollRun.month) >= s.effective_from.year * 100 + s.effective_from.month)):
        raise HTTPException(409, "This structure was used in finalized payroll and cannot be deleted")
    audit(db, current.user, "payroll.structure_delete", "employee", s.employee_id, f"Deleted structure from {s.effective_from}")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/preview/{employee_id}")
def preview(employee_id: int, year: int, month: int, current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    e = get_or_404(db, Employee, employee_id, "Employee")
    calc = compute_payslip(db, e, year, month)
    if not calc:
        raise HTTPException(404, "No salary structure for this employee")
    return {k: (float(v) if hasattr(v, "quantize") else v) for k, v in calc.items()}


# ------------------------------------------------------------------ adjustments

@router.get("/adjustments")
def adjustments(year: int, month: int, current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    rows = db.scalars(select(PayrollAdjustment).where(PayrollAdjustment.year == year, PayrollAdjustment.month == month))
    return [{"id": a.id, "employee": employee_brief(a.employee), "kind": a.kind, "label": a.label,
             "amount": float(a.amount)} for a in rows]


def _assert_open(db: Session, year: int, month: int):
    r = db.scalar(select(PayrollRun).where(PayrollRun.year == year, PayrollRun.month == month))
    if r and r.status != "draft":
        raise HTTPException(409, "Payroll for this month is finalized")


@router.post("/adjustments", status_code=201)
def add_adjustment(body: AdjustmentIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    get_or_404(db, Employee, body.employee_id, "Employee")
    _assert_open(db, body.year, body.month)
    a = PayrollAdjustment(created_by_id=current.id, **body.model_dump())
    db.add(a)
    db.flush()
    audit(db, current.user, f"payroll.{body.kind}", "employee", body.employee_id, f"{body.label}: {body.amount}")
    db.commit()
    return {"id": a.id}


@router.delete("/adjustments/{aid}")
def delete_adjustment(aid: int, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    a = get_or_404(db, PayrollAdjustment, aid, "Adjustment")
    _assert_open(db, a.year, a.month)
    db.delete(a)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ runs

@router.get("/runs")
def runs(current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    return [_run(r) for r in db.scalars(select(PayrollRun).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()))]


@router.post("/runs", status_code=201)
def process(body: RunIn, request: Request, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    if date(body.year, body.month, 1) > date.today().replace(day=1):
        raise HTTPException(422, "Cannot process payroll for a future month")
    r = db.scalar(select(PayrollRun).where(PayrollRun.year == body.year, PayrollRun.month == body.month))
    if not r:
        r = PayrollRun(year=body.year, month=body.month, processed_by_id=current.id)
        db.add(r)
        db.flush()
    result = process_run(db, r)
    r.processed_by_id = current.id
    audit(db, current.user, "payroll.process", "payroll_run", r.id, f"Processed payroll {body.month}/{body.year}",
          {"employees": len(r.payslips), "skipped": len(result["skipped"])}, ip=client_ip(request))
    db.commit()
    db.refresh(r)
    return {**_run(r, True), **result}


@router.get("/runs/{rid}")
def get_run(rid: int, current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    return _run(get_or_404(db, PayrollRun, rid, "Payroll run"), True)


@router.post("/runs/{rid}/finalize")
def finalize(rid: int, request: Request, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    r = get_or_404(db, PayrollRun, rid, "Payroll run")
    if r.status != "draft":
        raise HTTPException(409, "Payroll run is already finalized")
    if not r.payslips:
        raise HTTPException(422, "No payslips to finalize")
    r.status, r.finalized_at = "finalized", utcnow()
    period = f"{calendar.month_name[r.month]} {r.year}"
    notify(db, user_ids_for_employees(db, [p.employee_id for p in r.payslips]), f"Payslip for {period} is available",
           "View or download it from Payroll.", "/payroll", "payroll")
    audit(db, current.user, "payroll.finalize", "payroll_run", r.id, f"Finalized payroll {period}", ip=client_ip(request))
    db.commit()
    return _run(r, True)


@router.post("/runs/{rid}/pay")
def mark_paid(rid: int, body: PayIn, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    r = get_or_404(db, PayrollRun, rid, "Payroll run")
    if r.status == "draft":
        raise HTTPException(409, "Finalize payroll before recording payments")
    targets = [p for p in r.payslips if p.payment_status != "paid" and (not body.payslip_ids or p.id in body.payslip_ids)]
    for p in targets:
        db.add(SalaryPayment(payslip_id=p.id, paid_on=body.paid_on, amount=p.net_pay, mode=body.mode,
                             reference=body.reference, recorded_by_id=current.id))
        p.payment_status = "paid"
    if all(p.payment_status == "paid" for p in r.payslips):
        r.status = "paid"
    audit(db, current.user, "payroll.payment", "payroll_run", r.id, f"Recorded payment for {len(targets)} payslip(s)",
          body.model_dump(mode="json"))
    db.commit()
    return _run(r, True)


@router.delete("/runs/{rid}")
def delete_run(rid: int, current: CurrentUser = Depends(manage), db: Session = Depends(get_db)):
    r = get_or_404(db, PayrollRun, rid, "Payroll run")
    if r.status != "draft":
        raise HTTPException(409, "Finalized payroll cannot be deleted")
    db.delete(r)
    audit(db, current.user, "payroll.delete_draft", "payroll_run", rid, f"Deleted draft {r.month}/{r.year}")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ payslips

@router.get("/my-payslips")
def my_payslips(current: CurrentUser = Depends(require_employee), db: Session = Depends(get_db)):
    rows = db.execute(select(Payslip, PayrollRun).join(PayrollRun, PayrollRun.id == Payslip.run_id)
                      .where(Payslip.employee_id == current.employee_id, PayrollRun.status != "draft")
                      .order_by(PayrollRun.year.desc(), PayrollRun.month.desc())).all()
    return [{**_slip(p), "period": f"{calendar.month_name[r.month]} {r.year}", "year": r.year, "month": r.month}
            for p, r in rows]


@router.get("/payslips/{pid}/pdf")
def payslip_download(pid: int, current: CurrentUser = Depends(get_current), db: Session = Depends(get_db)):
    p = get_or_404(db, Payslip, pid, "Payslip")
    r = db.get(PayrollRun, p.run_id)
    own = p.employee_id == current.employee_id
    if not (current.has("payroll.view") or (own and r.status != "draft")):
        raise HTTPException(403, "Not allowed")
    e = p.employee
    cs = get_company(db)
    period = f"{calendar.month_name[r.month]} {r.year}"
    data = {**_slip(p), "period": period,
            "employee": {"full_name": e.full_name, "employee_code": e.employee_code,
                         "designation": e.designation.title if e.designation else None,
                         "department": e.department.name if e.department else None,
                         "bank_account": mask(decrypt_str(e.bank_account_enc))}}
    pdf = payslip_pdf({"company_name": cs.company_name, "legal_name": cs.legal_name, "email": cs.email,
                       "phone": cs.phone, "website": cs.website, "address": cs.address}, data)
    audit(db, current.user, "payroll.payslip_download", "payslip", p.id, f"Downloaded payslip {period} for {e.full_name}")
    db.commit()
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Payslip-{e.employee_code}-{r.year}-{r.month:02d}.pdf"'})


@router.get("/summary")
def payroll_summary(year: int | None = None, current: CurrentUser = Depends(view), db: Session = Depends(get_db)):
    year = year or date.today().year
    rows = db.execute(select(PayrollRun.month, PayrollRun.total_gross, PayrollRun.total_deductions, PayrollRun.total_net,
                             PayrollRun.status).where(PayrollRun.year == year).order_by(PayrollRun.month)).all()
    return [{"month": m, "label": calendar.month_abbr[m], "gross": float(g), "deductions": float(d), "net": float(n),
             "status": s} for m, g, d, n, s in rows]


_ = func
