from datetime import date

from pydantic import BaseModel, Field, model_validator


class ChallengeIn(BaseModel):
    purpose: str = Field(pattern="^(check_in|check_out|enroll)$")
    employee_id: int | None = None  # enrollment by HR


class FaceSubmitIn(BaseModel):
    nonce: str = Field(min_length=10, max_length=64)
    frames: list[str] = Field(min_length=6, max_length=24)
    timestamps: list[float] = Field(min_length=6, max_length=24)

    @model_validator(mode="after")
    def same_len(self):
        if len(self.frames) != len(self.timestamps):
            raise ValueError("frames and timestamps must have equal length")
        return self


class EnrollIn(FaceSubmitIn):
    employee_id: int
    consent_confirmed: bool

    @model_validator(mode="after")
    def consent(self):
        if not self.consent_confirmed:
            raise ValueError("Recorded employee consent is required for biometric enrollment")
        return self


class BreakIn(BaseModel):
    action: str = Field(pattern="^(start|end)$")
    reason: str | None = Field(None, max_length=120)


class CorrectionIn(BaseModel):
    kind: str = Field("correction", pattern="^(correction|manual)$")
    work_date: date
    check_in: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    check_out: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    reason: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def any_time(self):
        if not self.check_in and not self.check_out:
            raise ValueError("Provide a check-in or check-out time")
        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValueError("Check-out must be after check-in")
        return self


class ReviewIn(BaseModel):
    approve: bool
    note: str | None = Field(None, max_length=500)


class ManualMarkIn(BaseModel):
    employee_id: int
    work_date: date
    check_in: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    check_out: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    status: str | None = Field(None, pattern="^(present|absent|half_day|on_leave)$")
    reason: str = Field(min_length=3, max_length=500)


class LeaveTypeIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    code: str = Field(min_length=1, max_length=10)
    annual_quota: float = Field(0, ge=0, le=365)
    is_paid: bool = True
    carry_forward: bool = False
    max_carry_forward: float = Field(0, ge=0, le=365)
    color: str = Field("#00BEA3", pattern=r"^#[0-9A-Fa-f]{6}$")
    description: str | None = Field(None, max_length=255)
    is_active: bool = True


class LeaveApplyIn(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    half_day: bool = False
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        if self.half_day and self.start_date != self.end_date:
            raise ValueError("Half-day leave must be a single date")
        if (self.end_date - self.start_date).days > 90:
            raise ValueError("Leave cannot exceed 90 days in one request")
        return self


class BalanceAdjustIn(BaseModel):
    employee_id: int
    leave_type_id: int
    year: int = Field(ge=2000, le=2100)
    allocated: float = Field(ge=0, le=365)
    carried: float = Field(0, ge=0, le=365)


class HolidayIn(BaseModel):
    date: date
    name: str = Field(min_length=2, max_length=120)
    is_optional: bool = False
    description: str | None = Field(None, max_length=1000)
