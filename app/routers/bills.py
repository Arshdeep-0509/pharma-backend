from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bill, BillItem, Medicine
from app.schemas import BillDeleteOut, BillIn, BillOut
from app.security import require_roles

router = APIRouter(prefix="/api/bills", tags=["bills"])


@router.get("", response_model=list[BillOut])
def list_bills(limit: int = 20, db: Session = Depends(get_db)):
    return db.scalars(select(Bill).order_by(Bill.id.desc()).limit(min(limit, 100))).all()


@router.get("/{bill_id}", response_model=BillOut)
def get_bill(bill_id: int, db: Session = Depends(get_db)):
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill not found")
    return bill


@router.post("", response_model=BillOut, status_code=status.HTTP_201_CREATED)
def create_bill(data: BillIn, db: Session = Depends(get_db)):
    """Create a bill and deduct the sold quantities from stock in one transaction."""
    wanted = Counter()
    for item in data.items:
        wanted[item.medicine_id] += item.quantity

    # Row locks stop two simultaneous bills from overselling the same batch.
    medicines = {
        m.id: m
        for m in db.scalars(
            select(Medicine).where(Medicine.id.in_(wanted)).with_for_update()
        )
    }

    today = date.today()
    errors = []
    for medicine_id, qty in wanted.items():
        m = medicines.get(medicine_id)
        if m is None:
            errors.append(f"Medicine #{medicine_id} no longer exists")
        elif m.expiry_date < today:
            errors.append(f"{m.name} (batch {m.batch_no}) is expired and cannot be sold")
        elif m.quantity < qty:
            errors.append(f"Only {m.quantity} units of {m.name} (batch {m.batch_no}) in stock")
    if errors:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "; ".join(errors))

    bill = Bill(
        customer_name=data.customer_name or None,
        patient_age=data.patient_age,
        patient_gender=data.patient_gender,
        doctor_name=data.doctor_name or None,
        payment_mode=data.payment_mode,
        total=0,
    )
    for medicine_id, qty in wanted.items():
        m = medicines[medicine_id]
        m.quantity -= qty
        bill.items.append(
            BillItem(
                medicine_id=m.id,
                name=m.name,
                batch_no=m.batch_no,
                expiry_date=m.expiry_date,
                price=m.price,
                quantity=qty,
            )
        )
    bill.total = sum(i.price * i.quantity for i in bill.items)

    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill


@router.delete(
    "/{bill_id}",
    response_model=BillDeleteOut,
    dependencies=[Depends(require_roles("developer", "admin"))],
)
def delete_bill(bill_id: int, restock: bool = True, db: Session = Depends(get_db)):
    """Delete a bill (admins and developers only). With restock=true (the default) the sold
    quantities go back into stock, undoing what create_bill deducted, in the same transaction."""
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill not found")

    restocked = skipped = 0
    if restock:
        returned = Counter()
        for item in bill.items:
            if item.medicine_id is None:
                skipped += 1  # the medicine batch was deleted after the sale
            else:
                returned[item.medicine_id] += item.quantity
        medicines = {
            m.id: m
            for m in db.scalars(select(Medicine).where(Medicine.id.in_(returned)).with_for_update())
        }
        for medicine_id, qty in returned.items():
            medicines[medicine_id].quantity += qty
            restocked += qty

    db.delete(bill)
    db.commit()
    return BillDeleteOut(id=bill_id, restocked_units=restocked, skipped_lines=skipped)
