from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.security import hash_password, require_roles

router = APIRouter(prefix="/api/users", tags=["users"])

manager = require_roles("developer", "admin")


def can_create(actor: User, role: str) -> bool:
    """Developer: admins and users. Admin: users, plus admins if a developer allowed it."""
    if role == "user":
        return actor.role in ("developer", "admin")
    if role == "admin":
        return actor.role == "developer" or (actor.role == "admin" and actor.can_create_admins)
    return False


def visible_users(db: Session, actor: User) -> list[User]:
    """Developers see everyone else. Admins see every account created below them in the
    hierarchy: the accounts they made, the accounts those admins made, and so on."""
    users = db.scalars(select(User).order_by(User.created_at, User.id)).all()
    if actor.role == "developer":
        return [u for u in users if u.id != actor.id]

    children: dict[int, list[User]] = defaultdict(list)
    for u in users:
        if u.created_by_id is not None:
            children[u.created_by_id].append(u)
    result, stack = [], [actor.id]
    while stack:
        for child in children[stack.pop()]:
            result.append(child)
            stack.append(child.id)
    return sorted(result, key=lambda u: (u.created_at, u.id))


@router.get("", response_model=list[UserOut])
def list_users(actor: User = Depends(manager), db: Session = Depends(get_db)):
    return [UserOut.of(u) for u in visible_users(db, actor)]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    if not can_create(actor, data.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"You aren't allowed to create {data.role} accounts")
    if data.can_create_admins and not (actor.role == "developer" and data.role == "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a developer can let an admin create admins")

    user = User(
        username=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=data.role,
        can_create_admins=data.can_create_admins,
        created_by_id=actor.id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"An account with {data.email} already exists")
    db.refresh(user)
    return UserOut.of(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, data: UserUpdate, actor: User = Depends(manager), db: Session = Depends(get_db)
):
    # Only accounts the actor can see can be changed, which also rules out changing yourself.
    target = next((u for u in visible_users(db, actor) if u.id == user_id), None)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if data.can_create_admins is not None:
        if actor.role != "developer" or target.role != "admin":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Only a developer can change an admin's permission to create admins",
            )
        target.can_create_admins = data.can_create_admins
    if data.is_active is not None:
        target.is_active = data.is_active

    db.commit()
    db.refresh(target)
    return UserOut.of(target)
