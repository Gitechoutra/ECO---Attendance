"""Create the initial Super Admin (CEO) account and its employee profile.

Usage (from backend/):
    .venv\\Scripts\\python -m scripts.create_superadmin --email ceo@company.com --first-name Name --last-name Surname
The password is prompted interactively (never passed on the command line or stored in source).
"""
import argparse
import getpass
import sys
from datetime import date

from sqlalchemy import func, select

from app.core.security import hash_password, validate_password_strength
from app.db.session import SessionLocal
from app.models import Employee, Role, User
from app.services.bootstrap import seed_reference_data
from app.services.common import audit
from app.services.employees import allocate_leave_balances, next_employee_code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--first-name", required=True)
    ap.add_argument("--last-name", default="")
    ap.add_argument("--joining-date", default=date.today().isoformat())
    ap.add_argument("--password-env", help="Read password from this environment variable (for automation)")
    args = ap.parse_args()

    if args.password_env:
        import os
        pw = os.environ.get(args.password_env, "")
    else:
        pw = getpass.getpass("Password for super admin: ")
        if pw != getpass.getpass("Confirm password: "):
            print("Passwords do not match")
            return 1
    if err := validate_password_strength(pw):
        print(err)
        return 1

    with SessionLocal() as db:
        seed_reference_data(db)
        email = args.email.strip().lower()
        if db.scalar(select(User.id).where(func.lower(User.email) == email)):
            print("A user with this email already exists.")
            return 1
        role = db.scalar(select(Role).where(Role.code == "super_admin"))
        emp = db.scalar(select(Employee).where(func.lower(Employee.email) == email))
        if not emp:
            emp = Employee(employee_code=next_employee_code(db), first_name=args.first_name, last_name=args.last_name,
                           email=email, joining_date=date.fromisoformat(args.joining_date))
            db.add(emp)
            db.flush()
            allocate_leave_balances(db, emp)
        user = User(email=email, password_hash=hash_password(pw), role_id=role.id, employee_id=emp.id)
        db.add(user)
        db.flush()
        audit(db, user, "user.bootstrap_superadmin", "user", user.id, "Initial super admin created")
        db.commit()
        print(f"Super admin created: {email} (employee {emp.employee_code})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
