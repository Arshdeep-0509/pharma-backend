from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Medicine
from app.schemas import MedicineIn, MedicineOut

router = APIRouter(prefix="/api/medicines", tags=["medicines"])


def _get_or_404(db: Session, medicine_id: int) -> Medicine:
    medicine = db.get(Medicine, medicine_id)
    if medicine is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medicine not found")
    return medicine


def _commit(db: Session, data: MedicineIn) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Batch {data.batch_no} of {data.name} already exists",
        )


@router.get("", response_model=list[MedicineOut])
def list_medicines(db: Session = Depends(get_db)):
    return db.scalars(select(Medicine).order_by(Medicine.name, Medicine.expiry_date)).all()


@router.get("/{medicine_id}", response_model=MedicineOut)
def get_medicine(medicine_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, medicine_id)


@router.post("", response_model=MedicineOut, status_code=status.HTTP_201_CREATED)
def create_medicine(data: MedicineIn, db: Session = Depends(get_db)):
    medicine = Medicine(**data.model_dump())
    db.add(medicine)
    _commit(db, data)
    db.refresh(medicine)
    return medicine


@router.put("/{medicine_id}", response_model=MedicineOut)
def update_medicine(medicine_id: int, data: MedicineIn, db: Session = Depends(get_db)):
    medicine = _get_or_404(db, medicine_id)
    for field, value in data.model_dump().items():
        setattr(medicine, field, value)
    _commit(db, data)
    db.refresh(medicine)
    return medicine


@router.delete("/{medicine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medicine(medicine_id: int, db: Session = Depends(get_db)):
    db.delete(_get_or_404(db, medicine_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
