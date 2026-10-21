"""Request and response contracts, including merged-record validation."""

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Name = Annotated[str, Field(min_length=2, max_length=100)]
Phone = Annotated[str, Field(min_length=7, max_length=25)]
Course = Annotated[str, Field(min_length=1, max_length=100)]
Address = Annotated[str, Field(min_length=1, max_length=300)]


class StudentFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("email", "phone", "course", "address", mode="before", check_fields=False)
    @classmethod
    def normalize_optional(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("email", check_fields=False)
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower() if value is not None else None

    @field_validator("phone", check_fields=False)
    @classmethod
    def valid_phone(cls, value):
        if value is not None:
            if not re.fullmatch(r"\+?[0-9 ()-]+", value) or not 7 <= len(re.sub(r"\D", "", value)) <= 15:
                raise ValueError("phone must contain 7 to 15 digits, with an optional +, spaces, hyphens or parentheses")
        return value

    @field_validator("date_of_birth", check_fields=False)
    @classmethod
    def birth_not_in_future(cls, value):
        if value is not None and value > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return value


class StudentCreate(StudentFields):
    name: Name
    date_of_birth: date
    email: EmailStr | None = None
    phone: Phone | None = None
    course: Course | None = None
    address: Address | None = None
    enrollment_date: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def validate_record(self):
        if self.email is None and self.phone is None:
            raise ValueError("at least one contact method (email or phone) is required")
        if self.enrollment_date < self.date_of_birth:
            raise ValueError("enrollment_date cannot precede date_of_birth")
        return self


class StudentPatch(StudentFields):
    name: Name | None = None
    date_of_birth: date | None = None
    email: EmailStr | None = None
    phone: Phone | None = None
    course: Course | None = None
    address: Address | None = None
    enrollment_date: date | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("provide at least one field to update")
        for key in ("name", "date_of_birth", "enrollment_date"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class StudentOut(BaseModel):
    student_id: int
    name: str
    date_of_birth: date
    email: str | None
    phone: str | None
    course: str | None
    address: str | None
    enrollment_date: date
    created_at: datetime
    updated_at: datetime


class StudentPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[StudentOut]


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=300)
    use_ai: bool = False


class EvidenceStudent(BaseModel):
    student_id: int
    name: str
    date_of_birth: date
    course: str | None


class AskResponse(BaseModel):
    answer: str
    total_matches: int
    shown: int
    truncated: bool
    filters: dict[str, str]
    records: list[EvidenceStudent]
    source: Literal["sqlite", "sqlite+ollama"]
    ai_explanation: str | None = None
