"""Email, recruitment, offer letters, payroll, expenses, communication and AI."""
from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, utcnow

LongText = Text().with_variant(MEDIUMTEXT(), "mysql")

# ---------------------------------------------------------------- Email


class EmailAccount(Base, IdMixin, TimestampMixin):
    __tablename__ = "email_accounts"
    __table_args__ = (UniqueConstraint("provider", "email_address"),)
    provider: Mapped[str] = mapped_column(String(20))  # gmail|outlook
    email_address: Mapped[str] = mapped_column(String(190))
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)  # company mailbox visible to email.view_shared
    access_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    sync_status: Mapped[str] = mapped_column(String(20), default="connected")  # connected|error|disconnected
    sync_error: Mapped[str | None] = mapped_column(String(500))
    owner = relationship("User", lazy="joined")


class EmailMessage(Base, IdMixin):
    __tablename__ = "email_messages"
    __table_args__ = (UniqueConstraint("account_id", "provider_message_id"),)
    account_id: Mapped[int] = mapped_column(ForeignKey("email_accounts.id", ondelete="CASCADE"), index=True)
    provider_message_id: Mapped[str] = mapped_column(String(190))
    thread_id: Mapped[str | None] = mapped_column(String(190), index=True)
    direction: Mapped[str] = mapped_column(String(5))  # in|out
    subject: Mapped[str | None] = mapped_column(String(500))
    from_address: Mapped[str | None] = mapped_column(String(255), index=True)
    to_addresses: Mapped[str | None] = mapped_column(Text)
    cc_addresses: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(String(500))
    body_text: Mapped[str | None] = mapped_column(LongText)
    sent_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    account: Mapped[EmailAccount] = relationship(lazy="joined")
    client = relationship("Client", lazy="joined")
    project = relationship("Project", lazy="joined")


class EmailFollowUp(Base, IdMixin, TimestampMixin):
    __tablename__ = "email_followups"
    message_id: Mapped[int] = mapped_column(ForeignKey("email_messages.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    note: Mapped[str | None] = mapped_column(String(500))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime)
    message: Mapped[EmailMessage] = relationship(lazy="joined")


# ---------------------------------------------------------------- Recruitment


class JobOpening(Base, IdMixin, TimestampMixin):
    __tablename__ = "job_openings"
    title: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    designation_id: Mapped[int | None] = mapped_column(ForeignKey("designations.id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(120))
    employment_type: Mapped[str] = mapped_column(String(30), default="full_time")
    experience_min: Mapped[float | None] = mapped_column(Float)
    experience_max: Mapped[float | None] = mapped_column(Float)
    positions: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # draft|open|on_hold|closed
    closes_on: Mapped[date | None] = mapped_column(Date)
    hiring_manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    department = relationship("Department", lazy="joined")
    designation = relationship("Designation", lazy="joined")
    hiring_manager = relationship("Employee", lazy="joined")


class Candidate(Base, IdMixin, TimestampMixin):
    __tablename__ = "candidates"
    job_id: Mapped[int | None] = mapped_column(ForeignKey("job_openings.id", ondelete="SET NULL"), index=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80), default="")
    email: Mapped[str] = mapped_column(String(190), index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    source: Mapped[str | None] = mapped_column(String(60))
    current_company: Mapped[str | None] = mapped_column(String(160))
    experience_years: Mapped[float | None] = mapped_column(Float)
    current_ctc: Mapped[float | None] = mapped_column(Numeric(14, 2))
    expected_ctc: Mapped[float | None] = mapped_column(Numeric(14, 2))
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    skills: Mapped[str | None] = mapped_column(String(500))
    resume_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="applied", index=True)
    rating: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    job: Mapped[JobOpening | None] = relationship(lazy="joined")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Interview(Base, IdMixin, TimestampMixin):
    __tablename__ = "interviews"
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    round_name: Mapped[str] = mapped_column(String(80))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    mode: Mapped[str] = mapped_column(String(20), default="video")  # video|in_person|phone
    location: Mapped[str | None] = mapped_column(String(255))
    interviewer_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled|completed|cancelled|no_show
    rating: Mapped[int | None] = mapped_column(Integer)
    recommendation: Mapped[str | None] = mapped_column(String(10))  # hire|no_hire|hold
    feedback: Mapped[str | None] = mapped_column(Text)
    candidate: Mapped[Candidate] = relationship(lazy="joined")
    interviewer = relationship("Employee", lazy="joined")


# ---------------------------------------------------------------- Offer letters


class OfferTemplate(Base, IdMixin, TimestampMixin):
    __tablename__ = "offer_templates"
    name: Mapped[str] = mapped_column(String(120), unique=True)
    body: Mapped[str] = mapped_column(LongText)  # placeholders: {{candidate_name}}, {{designation}}, ...
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class OfferLetter(Base, IdMixin, TimestampMixin):
    __tablename__ = "offer_letters"
    reference_no: Mapped[str] = mapped_column(String(30), unique=True)
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("offer_templates.id", ondelete="SET NULL"))
    recipient_name: Mapped[str] = mapped_column(String(160))
    recipient_email: Mapped[str] = mapped_column(String(190))
    designation: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    joining_date: Mapped[date] = mapped_column(Date)
    annual_ctc: Mapped[float] = mapped_column(Numeric(14, 2))
    salary_breakup: Mapped[list | None] = mapped_column(JSON)  # [{label, monthly, annual}]
    work_location: Mapped[str | None] = mapped_column(String(120))
    valid_until: Mapped[date | None] = mapped_column(Date)
    additional_terms: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # draft|pending_approval|approved|rejected|sent|accepted|declined|withdrawn
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approval_note: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    accept_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)
    response_ip: Mapped[str | None] = mapped_column(String(64))
    response_signature: Mapped[str | None] = mapped_column(String(160))
    response_note: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    candidate: Mapped[Candidate | None] = relationship(lazy="joined")
    department = relationship("Department", lazy="joined")
    approved_by = relationship("User", foreign_keys=[approved_by_id], lazy="joined")


class OfferLetterVersion(Base, IdMixin):
    __tablename__ = "offer_letter_versions"
    __table_args__ = (UniqueConstraint("offer_id", "version"),)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offer_letters.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    change_note: Mapped[str | None] = mapped_column(String(255))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by = relationship("User", lazy="joined")


# ---------------------------------------------------------------- Payroll


class SalaryComponent(Base, IdMixin, TimestampMixin):
    """Configurable salary rule. calc_type: fixed (amount) | percent_basic | percent_gross."""

    __tablename__ = "salary_components"
    name: Mapped[str] = mapped_column(String(80), unique=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    kind: Mapped[str] = mapped_column(String(10))  # earning|deduction
    calc_type: Mapped[str] = mapped_column(String(20), default="fixed")
    default_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    prorate_with_attendance: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(String(255))


class SalaryStructure(Base, IdMixin, TimestampMixin):
    __tablename__ = "salary_structures"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    monthly_basic: Mapped[float] = mapped_column(Numeric(14, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(String(255))
    items: Mapped[list["SalaryStructureItem"]] = relationship(lazy="selectin", cascade="all, delete-orphan")
    employee = relationship("Employee", lazy="joined")


class SalaryStructureItem(Base, IdMixin):
    __tablename__ = "salary_structure_items"
    __table_args__ = (UniqueConstraint("structure_id", "component_id"),)
    structure_id: Mapped[int] = mapped_column(ForeignKey("salary_structures.id", ondelete="CASCADE"))
    component_id: Mapped[int] = mapped_column(ForeignKey("salary_components.id", ondelete="CASCADE"))
    value: Mapped[float] = mapped_column(Numeric(14, 2))  # amount or percent depending on component calc_type
    component: Mapped[SalaryComponent] = relationship(lazy="joined")


class PayrollAdjustment(Base, IdMixin, TimestampMixin):
    __tablename__ = "payroll_adjustments"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10))  # bonus|deduction
    label: Mapped[str] = mapped_column(String(120))
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    employee = relationship("Employee", lazy="joined")


class PayrollRun(Base, IdMixin, TimestampMixin):
    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("year", "month"),)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|finalized|paid
    working_days: Mapped[int] = mapped_column(Integer, default=0)
    total_gross: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    total_deductions: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    total_net: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    processed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime)
    payslips: Mapped[list["Payslip"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class Payslip(Base, IdMixin, TimestampMixin):
    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("run_id", "employee_id"),)
    run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    working_days: Mapped[float] = mapped_column(Float)
    paid_days: Mapped[float] = mapped_column(Float)
    lop_days: Mapped[float] = mapped_column(Float, default=0)
    monthly_basic: Mapped[float] = mapped_column(Numeric(14, 2))
    gross_earnings: Mapped[float] = mapped_column(Numeric(14, 2))
    total_deductions: Mapped[float] = mapped_column(Numeric(14, 2))
    bonus: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    net_pay: Mapped[float] = mapped_column(Numeric(14, 2))
    breakdown: Mapped[dict] = mapped_column(JSON)  # {earnings:[{code,name,amount}], deductions:[...]}
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid")  # unpaid|paid
    employee = relationship("Employee", lazy="joined")


class SalaryPayment(Base, IdMixin):
    __tablename__ = "salary_payments"
    payslip_id: Mapped[int] = mapped_column(ForeignKey("payslips.id", ondelete="CASCADE"), index=True)
    paid_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    mode: Mapped[str] = mapped_column(String(30))  # bank_transfer|cheque|cash|upi
    reference: Mapped[str | None] = mapped_column(String(120))
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- Expenses


class ExpenseCategory(Base, IdMixin, TimestampMixin):
    __tablename__ = "expense_categories"
    name: Mapped[str] = mapped_column(String(80), unique=True)
    monthly_limit: Mapped[float | None] = mapped_column(Numeric(14, 2))
    requires_receipt: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Expense(Base, IdMixin, TimestampMixin):
    __tablename__ = "expenses"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("expense_categories.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    receipt_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True)
    # submitted|approved|rejected|reimbursed
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_note: Mapped[str | None] = mapped_column(String(500))
    reimbursed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reimbursement_ref: Mapped[str | None] = mapped_column(String(120))
    employee = relationship("Employee", lazy="joined")
    category: Mapped[ExpenseCategory] = relationship(lazy="joined")
    project = relationship("Project", lazy="joined")


# ---------------------------------------------------------------- Communication


class Announcement(Base, IdMixin, TimestampMixin):
    __tablename__ = "announcements"
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default="general")  # general|policy|event|update|urgent
    audience: Mapped[str] = mapped_column(String(20), default="all")  # all|department|role
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    role_code: Mapped[str | None] = mapped_column(String(40))
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by = relationship("User", lazy="joined")
    department = relationship("Department", lazy="joined")


class Meeting(Base, IdMixin, TimestampMixin):
    __tablename__ = "meetings"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str | None] = mapped_column(String(255))
    meeting_link: Mapped[str | None] = mapped_column(String(500))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    organizer_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    organizer = relationship("Employee", lazy="joined")
    attendees: Mapped[list["MeetingAttendee"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class MeetingAttendee(Base, IdMixin):
    __tablename__ = "meeting_attendees"
    __table_args__ = (UniqueConstraint("meeting_id", "employee_id"),)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    response: Mapped[str] = mapped_column(String(10), default="pending")  # pending|accepted|declined
    employee = relationship("Employee", lazy="joined")


# ---------------------------------------------------------------- AI


class AIConversation(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_conversations"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))


class AIMessage(Base, IdMixin):
    __tablename__ = "ai_messages"
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user|model
    content: Mapped[str] = mapped_column(LongText)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
