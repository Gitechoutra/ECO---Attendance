from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, utcnow


class Department(Base, IdMixin, TimestampMixin):
    __tablename__ = "departments"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    head_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL", use_alter=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    head = relationship("Employee", foreign_keys=[head_id], lazy="joined")


class Designation(Base, IdMixin, TimestampMixin):
    __tablename__ = "designations"
    title: Mapped[str] = mapped_column(String(120), unique=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    level: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    department: Mapped[Department | None] = relationship(lazy="joined")


class Employee(Base, IdMixin, TimestampMixin):
    __tablename__ = "employees"
    employee_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80), default="")
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    personal_email: Mapped[str | None] = mapped_column(String(190))
    phone: Mapped[str | None] = mapped_column(String(30))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    marital_status: Mapped[str | None] = mapped_column(String(20))
    blood_group: Mapped[str | None] = mapped_column(String(5))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(80))
    country: Mapped[str | None] = mapped_column(String(80), default="India")
    postal_code: Mapped[str | None] = mapped_column(String(15))
    emergency_contact_name: Mapped[str | None] = mapped_column(String(120))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30))

    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), index=True)
    designation_id: Mapped[int | None] = mapped_column(ForeignKey("designations.id", ondelete="SET NULL"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    employment_type: Mapped[str] = mapped_column(String(30), default="full_time")
    work_location: Mapped[str | None] = mapped_column(String(120))
    joining_date: Mapped[date] = mapped_column(Date)
    probation_end_date: Mapped[date | None] = mapped_column(Date)
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_reason: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|on_notice|inactive

    photo_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL", use_alter=True))
    # Encrypted at rest (Fernet) — see services/employees.py
    bank_name: Mapped[str | None] = mapped_column(String(120))
    bank_account_enc: Mapped[str | None] = mapped_column(String(500))
    bank_ifsc: Mapped[str | None] = mapped_column(String(20))
    pan_enc: Mapped[str | None] = mapped_column(String(500))
    national_id_enc: Mapped[str | None] = mapped_column(String(500))

    department: Mapped[Department | None] = relationship(foreign_keys=[department_id], lazy="joined")
    designation: Mapped["Designation | None"] = relationship(lazy="joined")
    manager: Mapped["Employee | None"] = relationship(remote_side="Employee.id", lazy="select")
    user = relationship("User", primaryjoin="User.employee_id == Employee.id", uselist=False, viewonly=True, lazy="select")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class EmployeeHistory(Base, IdMixin):
    __tablename__ = "employee_history"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))  # created|updated|promoted|transferred|deactivated|...
    description: Mapped[str] = mapped_column(String(500))
    changes: Mapped[dict | None] = mapped_column(JSON)
    changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    changed_by = relationship("User", lazy="joined")
