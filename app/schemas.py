from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints
from pydantic.alias_generators import to_camel

from app.identity import normalize_email, normalize_phone

# JSON uses camelCase (batchNo, expiryDate) to match the frontend; Python uses snake_case.
_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

Price = Annotated[
    Decimal,
    Field(ge=0, max_digits=10, decimal_places=2),
    PlainSerializer(float, return_type=float, when_used="json"),
]


class MedicineIn(BaseModel):
    model_config = _config

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    batch_no: Annotated[
        str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=50)
    ]
    expiry_date: date
    price: Price
    quantity: Annotated[int, Field(ge=0)]


class MedicineOut(MedicineIn):
    id: int


Amount = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class BillItemIn(BaseModel):
    model_config = _config

    medicine_id: int
    quantity: Annotated[int, Field(ge=1)]


class BillIn(BaseModel):
    model_config = _config

    customer_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    patient_age: Annotated[int, Field(ge=0, le=150)] | None = None
    patient_gender: Literal["M", "F", "O"] | None = None
    doctor_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    payment_mode: Literal["Cash", "UPI", "Card"] = "Cash"
    items: Annotated[list[BillItemIn], Field(min_length=1)]


class BillItemOut(BaseModel):
    model_config = _config

    medicine_id: int | None
    name: str
    batch_no: str
    expiry_date: date | None
    price: Amount
    quantity: int


class BillOut(BaseModel):
    model_config = _config

    id: int
    customer_name: str | None
    patient_age: int | None
    patient_gender: str | None
    doctor_name: str | None
    payment_mode: str
    total: Amount
    created_at: datetime
    items: list[BillItemOut]



class BillDeleteOut(BaseModel):
    model_config = _config

    id: int
    restocked_units: int
    # Lines whose medicine batch no longer exists, so their units couldn't be returned.
    skipped_lines: int


Role = Literal["developer", "admin", "user"]
Phone = Annotated[str, AfterValidator(normalize_phone)]
Email = Annotated[str, StringConstraints(max_length=254), AfterValidator(normalize_email)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class LoginIn(BaseModel):
    model_config = _config

    # Developers: mobile number. Admins and users: email.
    identifier: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]
    password: Annotated[str, StringConstraints(max_length=128)]


class RegisterIn(BaseModel):
    """One-time developer setup — developers sign in with their mobile number."""

    model_config = _config

    phone: Phone
    full_name: FullName
    password: Password


class UserCreate(BaseModel):
    """Admins and users sign in with their email."""

    model_config = _config

    email: Email
    full_name: FullName
    password: Password
    role: Literal["admin", "user"]
    can_create_admins: bool = False


class UserUpdate(BaseModel):
    model_config = _config

    is_active: bool | None = None
    can_create_admins: bool | None = None


class UserOut(BaseModel):
    model_config = _config

    id: int
    full_name: str
    role: Role
    email: str | None = None
    phone: str | None = None
    can_create_admins: bool
    is_active: bool
    created_by_id: int | None
    created_by_name: str | None = None
    created_at: datetime

    @classmethod
    def of(cls, user) -> "UserOut":
        out = cls.model_validate(user)
        # One stored identifier, exposed under the name that matches the role.
        if user.role == "developer":
            out.phone = user.username
        else:
            out.email = user.username
        out.created_by_name = user.created_by.full_name if user.created_by else None
        return out


class SetupStatus(BaseModel):
    model_config = _config

    needs_setup: bool
