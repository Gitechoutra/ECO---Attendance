"""Clients, projects, milestones and tasks."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, utcnow


class Client(Base, IdMixin, TimestampMixin):
    __tablename__ = "clients"
    name: Mapped[str] = mapped_column(String(160), index=True)
    company_name: Mapped[str | None] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(190))
    email: Mapped[str | None] = mapped_column(String(190), index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80))
    country: Mapped[str | None] = mapped_column(String(80))
    tax_id: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # lead|active|inactive
    account_manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    account_manager = relationship("Employee", lazy="joined")
    contacts: Mapped[list["ClientContact"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class ClientContact(Base, IdMixin, TimestampMixin):
    __tablename__ = "client_contacts"
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    designation: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(190), index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    is_primary: Mapped[bool] = mapped_column(default=False)


class ClientRequirement(Base, IdMixin, TimestampMixin):
    __tablename__ = "client_requirements"
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|in_progress|delivered|dropped
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ClientMeeting(Base, IdMixin, TimestampMixin):
    __tablename__ = "client_meetings"
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    location: Mapped[str | None] = mapped_column(String(255))
    agenda: Mapped[str | None] = mapped_column(Text)
    minutes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled|completed|cancelled
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ClientCommunication(Base, IdMixin):
    __tablename__ = "client_communications"
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20))  # call|email|meeting|note|chat
    subject: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    email_message_id: Mapped[int | None] = mapped_column(ForeignKey("email_messages.id", ondelete="SET NULL"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user = relationship("User", lazy="joined")


class ClientFeedback(Base, IdMixin):
    __tablename__ = "client_feedback"
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    rating: Mapped[int] = mapped_column(Integer)  # 1..5
    comments: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[date] = mapped_column(Date)
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ClientContract(Base, IdMixin, TimestampMixin):
    __tablename__ = "client_contracts"
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    value: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|active|expired|terminated
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))


class Project(Base, IdMixin, TimestampMixin):
    __tablename__ = "projects"
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="planning", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    budget: Mapped[float | None] = mapped_column(Numeric(14, 2))
    progress: Mapped[float] = mapped_column(Float, default=0)  # 0-100, derived from tasks
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    client: Mapped[Client | None] = relationship(lazy="joined")
    manager = relationship("Employee", lazy="joined")
    members: Mapped[list["ProjectMember"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class ProjectMember(Base, IdMixin):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "employee_id"),)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    role: Mapped[str | None] = mapped_column(String(80))
    allocation_percent: Mapped[int] = mapped_column(Integer, default=100)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    employee = relationship("Employee", lazy="joined")


class Milestone(Base, IdMixin, TimestampMixin):
    __tablename__ = "milestones"
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|in_progress|completed
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Task(Base, IdMixin, TimestampMixin):
    __tablename__ = "tasks"
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    milestone_id: Mapped[int | None] = mapped_column(ForeignKey("milestones.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    priority: Mapped[str] = mapped_column(String(10), default="medium")  # low|medium|high|urgent
    status: Mapped[str] = mapped_column(String(20), default="todo", index=True)  # todo|in_progress|review|blocked|done
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    estimated_hours: Mapped[float | None] = mapped_column(Float)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_overdue_reminder: Mapped[date | None] = mapped_column(Date)
    project: Mapped[Project | None] = relationship(lazy="joined")
    assignee = relationship("Employee", foreign_keys=[assignee_id], lazy="joined")
    reporter = relationship("Employee", foreign_keys=[reporter_id], lazy="joined")


class TaskComment(Base, IdMixin):
    __tablename__ = "task_comments"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    author = relationship("User", lazy="joined")


class TaskUpdate(Base, IdMixin):
    """Daily progress update posted by the assignee."""

    __tablename__ = "task_updates"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    update_date: Mapped[date] = mapped_column(Date)
    progress: Mapped[int] = mapped_column(Integer)
    hours_spent: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    employee = relationship("Employee", lazy="joined")


class TaskHistory(Base, IdMixin):
    __tablename__ = "task_history"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    field: Mapped[str] = mapped_column(String(40))
    old_value: Mapped[str | None] = mapped_column(String(500))
    new_value: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user = relationship("User", lazy="joined")
