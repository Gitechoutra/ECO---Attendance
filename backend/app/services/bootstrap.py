"""Idempotent seeding of reference data required for the system to run (no fake business data)."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS, ROLES
from app.models import ExpenseCategory, LeaveType, OfferTemplate, Permission, Role, SalaryComponent
from app.services.common import get_company

DEFAULT_OFFER_TEMPLATE = """Dear {{candidate_name}},

We are delighted to offer you the position of {{designation}} in the {{department}} team at {{company_name}}. We were impressed by your experience and believe you will make a valuable contribution to our organisation.

Your employment will commence on {{joining_date}} and you will be based at {{work_location}}. Your total annual cost to company (CTC) will be {{annual_ctc}}, structured as detailed in the compensation annexure below.

This offer is subject to satisfactory verification of your documents and references. Please confirm your acceptance of this offer on or before {{valid_until}}.

{{additional_terms}}

We look forward to welcoming you to {{company_name}}.

Warm regards,

Human Resources
{{company_name}}"""


def seed_reference_data(db: Session) -> None:
    existing = {p.code: p for p in db.scalars(select(Permission))}
    for code, (module, desc) in PERMISSIONS.items():
        if code not in existing:
            p = Permission(code=code, module=module, description=desc)
            db.add(p)
            existing[code] = p
        else:
            existing[code].module, existing[code].description = module, desc
    db.flush()

    for code, (name, desc) in ROLES.items():
        role = db.scalar(select(Role).where(Role.code == code))
        if not role:
            role = Role(code=code, name=name, description=desc, is_system=True)
            role.permissions = [existing[c] for c in sorted(DEFAULT_ROLE_PERMISSIONS[code])]
            db.add(role)
        elif code == "super_admin":
            role.permissions = list(existing.values())

    get_company(db)

    if not db.scalar(select(LeaveType.id).limit(1)):
        db.add_all([
            LeaveType(name="Casual Leave", code="CL", annual_quota=12, color="#00BEA3"),
            LeaveType(name="Sick Leave", code="SL", annual_quota=8, color="#F59E0B"),
            LeaveType(name="Earned Leave", code="EL", annual_quota=15, carry_forward=True, max_carry_forward=30,
                      color="#1197A1"),
            LeaveType(name="Loss of Pay", code="LOP", annual_quota=0, is_paid=False, color="#94A3B8",
                      description="Unpaid leave; deducted in payroll."),
        ])
    if not db.scalar(select(ExpenseCategory.id).limit(1)):
        db.add_all([ExpenseCategory(name=n) for n in
                    ["Travel", "Food & Meals", "Accommodation", "Client Entertainment", "Software & Tools",
                     "Office Supplies", "Internet & Phone", "Training", "Other"]])
    if not db.scalar(select(SalaryComponent.id).limit(1)):
        # Configurable rule examples. Statutory rules (PF/ESI/PT/TDS) are intentionally NOT pre-configured —
        # HR must add verified rules for the applicable jurisdiction.
        db.add_all([
            SalaryComponent(name="House Rent Allowance", code="HRA", kind="earning", calc_type="percent_basic",
                            default_value=40),
            SalaryComponent(name="Special Allowance", code="SPA", kind="earning", calc_type="fixed", default_value=0),
            SalaryComponent(name="Conveyance Allowance", code="CONV", kind="earning", calc_type="fixed",
                            default_value=0),
        ])
    if not db.scalar(select(OfferTemplate.id).limit(1)):
        db.add(OfferTemplate(name="Standard Offer Letter", body=DEFAULT_OFFER_TEMPLATE, is_default=True))
    db.commit()


def current_year() -> int:
    return date.today().year
