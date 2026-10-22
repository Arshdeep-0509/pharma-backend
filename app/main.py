from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import Base, engine
from app.routers import auth, bills, medicines, users
from app.security import get_current_user


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Creates missing tables on startup. Swap for Alembic migrations once the schema evolves.
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    yield


def _add_missing_columns() -> None:
    """create_all() never alters existing tables, so add columns introduced after first deploy."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE bills"
            " ADD COLUMN IF NOT EXISTS patient_age INTEGER,"
            " ADD COLUMN IF NOT EXISTS patient_gender VARCHAR(10),"
            " ADD COLUMN IF NOT EXISTS doctor_name VARCHAR(200),"
            " ADD COLUMN IF NOT EXISTS payment_mode VARCHAR(20) NOT NULL DEFAULT 'Cash'"
        ))
        conn.execute(text("ALTER TABLE bill_items ADD COLUMN IF NOT EXISTS expiry_date DATE"))
        # Login identifiers became emails (up to 254 chars) after the table was first created.
        conn.execute(text("ALTER TABLE users ALTER COLUMN username TYPE VARCHAR(254)"))


app = FastAPI(title="PharmaStock API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,  # the session cookie travels with API calls
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
# Inventory and billing need a logged-in account (any role).
_login_required = [Depends(get_current_user)]
app.include_router(medicines.router, dependencies=_login_required)
app.include_router(bills.router, dependencies=_login_required)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
