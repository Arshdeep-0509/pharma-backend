from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Medicine(Base):
    __tablename__ = "medicines"
    __table_args__ = (
        UniqueConstraint("name", "batch_no", name="uq_medicine_name_batch"),
        CheckConstraint("price >= 0", name="ck_medicine_price_non_negative"),
        CheckConstraint("quantity >= 0", name="ck_medicine_quantity_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    batch_no: Mapped[str] = mapped_column(String(50), index=True)
    expiry_date: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_name: Mapped[str | None] = mapped_column(String(200))
    patient_age: Mapped[int | None] = mapped_column(Integer)
    patient_gender: Mapped[str | None] = mapped_column(String(10))
    doctor_name: Mapped[str | None] = mapped_column(String(200))
    payment_mode: Mapped[str] = mapped_column(String(20), default="Cash")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    items: Mapped[list["BillItem"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", lazy="selectin", order_by="BillItem.id"
    )


class BillItem(Base):
    __tablename__ = "bill_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_bill_item_quantity_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    # Nullable so a bill survives the medicine being deleted later; name/batch/price are
    # snapshotted at sale time for the same reason.
    medicine_id: Mapped[int | None] = mapped_column(ForeignKey("medicines.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200))
    batch_no: Mapped[str] = mapped_column(String(50))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int] = mapped_column(Integer)

    bill: Mapped[Bill] = relationship(back_populates="items")


class User(Base):
    """App account. Roles: developer > admin > user. `created_by_id` forms the hierarchy that
    decides which accounts an admin can see (everything created below them)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('developer', 'admin', 'user')", name="ck_user_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Login identifier: mobile number for developers, email for admins and users.
    username: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    # Granted by a developer; lets an admin create other admins.
    can_create_admins: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped["User | None"] = relationship(remote_side=[id], lazy="joined")
