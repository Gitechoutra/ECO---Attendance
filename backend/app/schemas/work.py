from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

PRIORITY = "^(low|medium|high|urgent)$"


class ProjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(None, max_length=10000)
    client_id: int | None = None
    manager_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str = Field("planning", pattern="^(planning|active|on_hold|completed|cancelled)$")
    priority: str = Field("medium", pattern=PRIORITY)
    budget: float | None = Field(None, ge=0)

    @model_validator(mode="after")
    def dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        return self


class MemberIn(BaseModel):
    employee_id: int
    role: str | None = Field(None, max_length=80)
    allocation_percent: int = Field(100, ge=1, le=100)


class MilestoneIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(None, max_length=5000)
    due_date: date | None = None
    status: str = Field("pending", pattern="^(pending|in_progress|completed)$")


class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(None, max_length=20000)
    project_id: int | None = None
    milestone_id: int | None = None
    assignee_id: int | None = None
    priority: str = Field("medium", pattern=PRIORITY)
    status: str = Field("todo", pattern="^(todo|in_progress|review|blocked|done)$")
    due_date: date | None = None
    estimated_hours: float | None = Field(None, ge=0, le=1000)


class TaskStatusIn(BaseModel):
    status: str = Field(pattern="^(todo|in_progress|review|blocked|done)$")


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class TaskUpdateIn(BaseModel):
    progress: int = Field(ge=0, le=100)
    hours_spent: float = Field(0, ge=0, le=24)
    note: str = Field(min_length=3, max_length=5000)
    update_date: date | None = None


class ClientIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    company_name: str | None = Field(None, max_length=200)
    industry: str | None = Field(None, max_length=100)
    website: str | None = Field(None, max_length=190)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40)
    address: str | None = Field(None, max_length=2000)
    city: str | None = Field(None, max_length=80)
    country: str | None = Field(None, max_length=80)
    tax_id: str | None = Field(None, max_length=60)
    status: str = Field("active", pattern="^(lead|active|inactive)$")
    account_manager_id: int | None = None
    notes: str | None = Field(None, max_length=10000)


class ContactIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    designation: str | None = Field(None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40)
    is_primary: bool = False


class RequirementIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(None, max_length=10000)
    priority: str = Field("medium", pattern=PRIORITY)
    status: str = Field("open", pattern="^(open|in_progress|delivered|dropped)$")
    project_id: int | None = None


class ClientMeetingIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    scheduled_at: datetime
    duration_minutes: int = Field(60, ge=5, le=600)
    location: str | None = Field(None, max_length=255)
    agenda: str | None = Field(None, max_length=5000)
    minutes: str | None = Field(None, max_length=20000)
    status: str = Field("scheduled", pattern="^(scheduled|completed|cancelled)$")
    project_id: int | None = None


class CommunicationIn(BaseModel):
    channel: str = Field(pattern="^(call|email|meeting|note|chat)$")
    subject: str = Field(min_length=2, max_length=255)
    summary: str | None = Field(None, max_length=10000)
    occurred_at: datetime | None = None


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comments: str | None = Field(None, max_length=5000)
    received_at: date
    project_id: int | None = None


class ContractIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    value: float | None = Field(None, ge=0)
    currency: str = Field("INR", max_length=8)
    start_date: date | None = None
    end_date: date | None = None
    status: str = Field("draft", pattern="^(draft|active|expired|terminated)$")
    project_id: int | None = None
