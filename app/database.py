from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_connect_args = {}
if settings.database_url.startswith("postgresql+psycopg"):
    _connect_args = {
        # Supabase's transaction pooler (port 6543) can't handle server-side prepared statements.
        "prepare_threshold": None,
        # Fail fast with a clear error instead of hanging when the database is unreachable.
        "connect_timeout": 15,
    }

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db
