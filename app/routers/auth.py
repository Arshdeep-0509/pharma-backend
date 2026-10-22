from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.identity import is_phone_identifier, normalize_email, normalize_phone
from app.models import User
from app.schemas import LoginIn, RegisterIn, SetupStatus, UserOut
from app.security import (
    clear_session_cookie,
    get_current_user,
    hash_password,
    set_session_cookie,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


@router.get("/setup-status", response_model=SetupStatus)
def setup_status(db: Session = Depends(get_db)):
    """True until the first account exists; the frontend then offers the register form."""
    return SetupStatus(needs_setup=_user_count(db) == 0)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, response: Response, db: Session = Depends(get_db)):
    """One-time setup: the first account becomes the developer. Afterwards accounts are
    created by admins/developers from the Users page, so open sign-up is closed."""
    if db.bind.dialect.name == "postgresql":
        # Serialise concurrent first-time registrations so only one developer is created.
        db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
    if _user_count(db) > 0:
        db.rollback()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Registration is closed. Ask an admin or developer to create your account.",
        )
    user = User(
        username=data.phone,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role="developer",
        can_create_admins=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That phone number is already registered")
    db.refresh(user)
    set_session_cookie(response, user)
    return UserOut.of(user)


@router.post("/login", response_model=UserOut)
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    # Developers sign in with their mobile number; admins and users with their email.
    try:
        if is_phone_identifier(data.identifier):
            identifier, allowed_roles = normalize_phone(data.identifier), {"developer"}
        else:
            identifier, allowed_roles = normalize_email(data.identifier), {"admin", "user"}
    except ValueError:
        identifier, allowed_roles = None, set()

    user = db.scalar(select(User).where(User.username == identifier)) if identifier else None
    if user is not None and user.role not in allowed_roles:
        user = None  # e.g. an email typed for the developer account
    if not verify_password(data.password, user.password_hash if user else None) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email/phone number or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
    set_session_cookie(response, user)
    return UserOut.of(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    clear_session_cookie(response)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.of(user)
