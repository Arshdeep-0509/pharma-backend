from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

COOKIE_NAME = "access_token"
ALGORITHM = "HS256"

password_hash = PasswordHash.recommended()  # Argon2id
# Also accept "Authorization: Bearer <token>" so the API docs and scripts can authenticate.
_bearer = HTTPBearer(auto_error=False)

# Hash of a throwaway password, verified on unknown usernames so login takes the same time
# whether or not the account exists (no username probing by timing).
_DUMMY_HASH = password_hash.hash("timing-equaliser")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if hashed is None:
        password_hash.verify(password, _DUMMY_HASH)
        return False
    return password_hash.verify(password, hashed)


def create_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(hours=settings.session_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def set_session_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_token(user),
        max_age=settings.session_hours * 3600,
        httponly=True,  # not readable from JavaScript, so XSS can't steal the session
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax", secure=settings.cookie_secure)


_unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in to continue")


def get_current_user(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    token = bearer.credentials if bearer else request.cookies.get(COOKIE_NAME)
    if not token:
        raise _unauthorized
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized
    # Looked up on every request so deactivation and role changes apply immediately.
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to do this")
        return user

    return dependency
