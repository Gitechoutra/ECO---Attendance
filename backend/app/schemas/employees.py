from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

ROLE_CODES = {"super_admin", "hr_admin", "project_manager", "employee"}


class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=1, max_length=20)
    description: str | None = Field(None, max_length=500)
    head_id: int | None = None
    is_active: bool = True


class DesignationIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    department_id: int | None = None
    level: int = Field(1, ge=1, le=20)
    is_active: bool = True


class EmployeeBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field("", max_length=80)
    email: EmailStr
    personal_email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30, pattern=r"^[0-9+()\-\s]{6,30}$")
    date_of_birth: date | None = None
    gender: str | None = Field(None, max_length=20)
    marital_status: str | None = Field(None, max_length=20)
    blood_group: str | None = Field(None, max_length=5)
    address: str | None = Field(None, max_length=1000)
    city: str | None = Field(None, max_length=80)
    state: str | None = Field(None, max_length=80)
    country: str | None = Field("India", max_length=80)
    postal_code: str | None = Field(None, max_length=15)
    emergency_contact_name: str | None = Field(None, max_length=120)
    emergency_contact_phone: str | None = Field(None, max_length=30)
    department_id: int | None = None
    designation_id: int | None = None
    manager_id: int | None = None
    employment_type: str = Field("full_time", pattern="^(full_time|part_time|contract|intern|consultant)$")
    work_location: str | None = Field(None, max_length=120)
    joining_date: date
    probation_end_date: date | None = None
    bank_name: str | None = Field(None, max_length=120)
    bank_account: str | None = Field(None, max_length=40)
    bank_ifsc: str | None = Field(None, max_length=20)
    pan: str | None = Field(None, max_length=20)
    national_id: str | None = Field(None, max_length=30)

    @field_validator("email", "personal_email")
    @classmethod
    def lower(cls, v):
        return v.lower() if v else v

    @model_validator(mode="after")
    def check_dates(self):
        if self.date_of_birth and self.date_of_birth >= self.joining_date:
            raise ValueError("Date of birth must be before joining date")
        if self.date_of_birth and (self.joining_date.year - self.date_of_birth.year) < 14:
            raise ValueError("Employee must be at least 14 years old on joining date")
        if self.probation_end_date and self.probation_end_date < self.joining_date:
            raise ValueError("Probation end date cannot be before joining date")
        return self


class EmployeeCreate(EmployeeBase):
    create_login: bool = True
    role_code: str = "employee"

    @field_validator("role_code")
    @classmethod
    def role_ok(cls, v):
        if v not in ROLE_CODES:
            raise ValueError("Invalid role")
        return v


class EmployeeUpdate(EmployeeBase):
    pass


class EmployeeSelfUpdate(BaseModel):
    phone: str | None = Field(None, max_length=30, pattern=r"^[0-9+()\-\s]{6,30}$")
    personal_email: EmailStr | None = None
    address: str | None = Field(None, max_length=1000)
    city: str | None = Field(None, max_length=80)
    state: str | None = Field(None, max_length=80)
    postal_code: str | None = Field(None, max_length=15)
    marital_status: str | None = Field(None, max_length=20)
    blood_group: str | None = Field(None, max_length=5)
    emergency_contact_name: str | None = Field(None, max_length=120)
    emergency_contact_phone: str | None = Field(None, max_length=30)


class DeactivateIn(BaseModel):
    exit_date: date
    exit_reason: str = Field(min_length=3, max_length=500)
    status: str = Field("inactive", pattern="^(inactive|on_notice)$")


class AccountIn(BaseModel):
    role_code: str = "employee"

    @field_validator("role_code")
    @classmethod
    def role_ok(cls, v):
        if v not in ROLE_CODES:
            raise ValueError("Invalid role")
        return v
