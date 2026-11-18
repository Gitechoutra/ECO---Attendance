from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

CAND_STATUS = "^(applied|screening|interview|offered|hired|rejected|withdrawn)$"


class JobIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    department_id: int | None = None
    designation_id: int | None = None
    description: str | None = Field(None, max_length=20000)
    requirements: str | None = Field(None, max_length=20000)
    location: str | None = Field(None, max_length=120)
    employment_type: str = Field("full_time", pattern="^(full_time|part_time|contract|intern|consultant)$")
    experience_min: float | None = Field(None, ge=0, le=50)
    experience_max: float | None = Field(None, ge=0, le=50)
    positions: int = Field(1, ge=1, le=500)
    status: str = Field("open", pattern="^(draft|open|on_hold|closed)$")
    closes_on: date | None = None
    hiring_manager_id: int | None = None

    @model_validator(mode="after")
    def exp(self):
        if self.experience_min is not None and self.experience_max is not None and self.experience_max < self.experience_min:
            raise ValueError("Maximum experience must be ≥ minimum experience")
        return self


class CandidateIn(BaseModel):
    job_id: int | None = None
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field("", max_length=80)
    email: EmailStr
    phone: str | None = Field(None, max_length=30)
    source: str | None = Field(None, max_length=60)
    current_company: str | None = Field(None, max_length=160)
    experience_years: float | None = Field(None, ge=0, le=60)
    current_ctc: float | None = Field(None, ge=0)
    expected_ctc: float | None = Field(None, ge=0)
    notice_period_days: int | None = Field(None, ge=0, le=365)
    skills: str | None = Field(None, max_length=500)
    status: str = Field("applied", pattern=CAND_STATUS)
    rating: int | None = Field(None, ge=1, le=5)
    notes: str | None = Field(None, max_length=10000)


class CandidateStatusIn(BaseModel):
    status: str = Field(pattern=CAND_STATUS)
    note: str | None = Field(None, max_length=1000)


class InterviewIn(BaseModel):
    round_name: str = Field(min_length=2, max_length=80)
    scheduled_at: datetime
    duration_minutes: int = Field(60, ge=10, le=480)
    mode: str = Field("video", pattern="^(video|in_person|phone)$")
    location: str | None = Field(None, max_length=255)
    interviewer_id: int | None = None


class InterviewFeedbackIn(BaseModel):
    status: str = Field("completed", pattern="^(scheduled|completed|cancelled|no_show)$")
    rating: int | None = Field(None, ge=1, le=5)
    recommendation: str | None = Field(None, pattern="^(hire|no_hire|hold)$")
    feedback: str | None = Field(None, max_length=10000)


class ConvertIn(BaseModel):
    joining_date: date | None = None
    department_id: int | None = None
    designation_id: int | None = None
    manager_id: int | None = None
    create_login: bool = True
    role_code: str = Field("employee", pattern="^(employee|project_manager|hr_admin)$")


class SalaryLine(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    monthly: float = Field(ge=0)
    annual: float = Field(ge=0)


class OfferIn(BaseModel):
    candidate_id: int | None = None
    employee_id: int | None = None
    template_id: int | None = None
    recipient_name: str | None = Field(None, max_length=160)
    recipient_email: EmailStr | None = None
    designation: str = Field(min_length=2, max_length=120)
    department_id: int | None = None
    joining_date: date
    annual_ctc: float = Field(gt=0)
    salary_breakup: list[SalaryLine] = Field(default_factory=list)
    work_location: str | None = Field(None, max_length=120)
    valid_until: date | None = None
    additional_terms: str | None = Field(None, max_length=10000)

    @model_validator(mode="after")
    def target(self):
        if not self.candidate_id and not self.employee_id and not (self.recipient_name and self.recipient_email):
            raise ValueError("Select a candidate or employee, or enter the recipient's name and email")
        if self.salary_breakup:
            total = round(sum(x.annual for x in self.salary_breakup), 2)
            if abs(total - self.annual_ctc) > 1:
                raise ValueError(f"Salary breakup totals {total:,.2f} but annual CTC is {self.annual_ctc:,.2f}")
        return self


class OfferDecisionIn(BaseModel):
    approve: bool
    note: str | None = Field(None, max_length=500)


class OfferResponseIn(BaseModel):
    accept: bool
    signature: str = Field(min_length=2, max_length=160)
    note: str | None = Field(None, max_length=500)


class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=20, max_length=50000)
    is_default: bool = False
    is_active: bool = True
