from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, utcnow


class BiometricConsent(Base, IdMixin):
    __tablename__ = "biometric_consents"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    consent_version: Mapped[str] = mapped_column(String(20))
    given_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class FaceProfile(Base, IdMixin, TimestampMixin):
    __tablename__ = "face_profiles"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), unique=True)
    embedding_enc: Mapped[bytes] = mapped_column(LargeBinary)  # Fernet-encrypted float32 mean embedding
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    consent_id: Mapped[int] = mapped_column(ForeignKey("biometric_consents.id"))
    enrolled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)


class LivenessChallenge(Base, IdMixin):
    __tablename__ = "liveness_challenges"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    nonce: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(20))  # check_in|check_out|enroll
    steps: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AttendanceRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("employee_id", "work_date"),)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime)
    check_in_method: Mapped[str | None] = mapped_column(String(20))  # face|manual|correction
    check_out_method: Mapped[str | None] = mapped_column(String(20))
    check_in_score: Mapped[float | None] = mapped_column(Float)
    check_out_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="present")  # present|late|half_day|absent|on_leave
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0)
    break_minutes: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(String(500))
    marked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    employee = relationship("Employee", lazy="joined")
    breaks: Mapped[list["AttendanceBreak"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="AttendanceBreak.start_at"
    )


class AttendanceBreak(Base, IdMixin):
    __tablename__ = "attendance_breaks"
    attendance_id: Mapped[int] = mapped_column(ForeignKey("attendance_records.id", ondelete="CASCADE"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str | None] = mapped_column(String(120))


class AttendanceCorrection(Base, IdMixin, TimestampMixin):
    """Correction requests AND manual check-in requests (kind='manual') awaiting approval."""

    __tablename__ = "attendance_corrections"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="correction")  # correction|manual
    work_date: Mapped[date] = mapped_column(Date)
    requested_check_in: Mapped[datetime | None] = mapped_column(DateTime)
    requested_check_out: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_note: Mapped[str | None] = mapped_column(String(500))
    employee = relationship("Employee", lazy="joined")
    reviewed_by = relationship("User", lazy="joined")


class LeaveType(Base, IdMixin, TimestampMixin):
    __tablename__ = "leave_types"
    name: Mapped[str] = mapped_column(String(80), unique=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    annual_quota: Mapped[float] = mapped_column(Float, default=0)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True)
    carry_forward: Mapped[bool] = mapped_column(Boolean, default=False)
    max_carry_forward: Mapped[float] = mapped_column(Float, default=0)
    color: Mapped[str] = mapped_column(String(10), default="#00BEA3")
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LeaveBalance(Base, IdMixin, TimestampMixin):
    __tablename__ = "leave_balances"
    __table_args__ = (UniqueConstraint("employee_id", "leave_type_id", "year"),)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer)
    allocated: Mapped[float] = mapped_column(Float, default=0)
    carried: Mapped[float] = mapped_column(Float, default=0)
    used: Mapped[float] = mapped_column(Float, default=0)
    leave_type: Mapped[LeaveType] = relationship(lazy="joined")

    @property
    def available(self) -> float:
        return round(self.allocated + self.carried - self.used, 2)


class LeaveRequest(Base, IdMixin, TimestampMixin):
    __tablename__ = "leave_requests"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    half_day: Mapped[bool] = mapped_column(Boolean, default=False)
    days: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|approved|rejected|cancelled
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_note: Mapped[str | None] = mapped_column(String(500))
    employee = relationship("Employee", foreign_keys=[employee_id], lazy="joined")
    leave_type: Mapped[LeaveType] = relationship(lazy="joined")
    reviewed_by = relationship("User", lazy="joined")


class Holiday(Base, IdMixin, TimestampMixin):
    __tablename__ = "holidays"
    date: Mapped[date] = mapped_column(Date, unique=True)
    name: Mapped[str] = mapped_column(String(120))
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text)
