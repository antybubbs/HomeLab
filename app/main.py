from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import get_settings, trusted_hosts
from app.core.security import hash_password
from app.db.session import Base, engine, SessionLocal
from app.models.models import User, VLAN
from app.routers import auth, dashboard, licences, admin, ip_addresses

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    docs_url=None if settings.app_env == "production" else "/docs",
    root_path=settings.root_path,
)

if settings.app_env == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=trusted_hosts(settings),
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=settings.session_cookie_secure,
    same_site="strict",
    max_age=60 * 60 * 8,
)

@app.exception_handler(PermissionError)
async def permission_handler(request: Request, exc: PermissionError):
    if request.session.get("user_id"):
        return PlainTextResponse("Forbidden", status_code=403)
    return RedirectResponse("/login", status_code=303)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    response.headers["Cache-Control"] = "no-store"
    if settings.session_cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

Path("/app/uploads").mkdir(parents=True, exist_ok=True)
Path("/app/data").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def bootstrap():
    Base.metadata.create_all(bind=engine)
    migrate_existing_database()
    db: Session = SessionLocal()
    try:
        admin_email = settings.admin_email.strip().lower()
        admin = db.query(User).filter(User.email == admin_email).first()
        if not admin:
            db.add(User(email=admin_email, password_hash=hash_password(settings.admin_password), role="admin"))
            db.commit()
        default_vlan = db.query(VLAN).filter(VLAN.name == "VLAN 1").first()
        if not default_vlan:
            db.add(VLAN(name="VLAN 1"))
            db.commit()
    finally:
        db.close()


def migrate_existing_database():
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
        if "totp_secret" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN totp_secret TEXT"))
        if "totp_enabled" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT 0 NOT NULL"))
        vlan_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(vlans)"))}
        if not vlan_columns:
            conn.execute(text("CREATE TABLE vlans (id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(120) NOT NULL UNIQUE, description TEXT, created_at DATETIME, updated_at DATETIME)"))
            conn.execute(text("CREATE INDEX ix_vlans_name ON vlans (name)"))
        ip_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(ip_addresses)"))}
        if ip_columns and "vlan_id" not in ip_columns:
            conn.execute(text("ALTER TABLE ip_addresses ADD COLUMN vlan_id INTEGER REFERENCES vlans(id)"))
            conn.execute(text("CREATE INDEX ix_ip_addresses_vlan_id ON ip_addresses (vlan_id)"))
        conn.execute(text("INSERT OR IGNORE INTO vlans (name, created_at, updated_at) VALUES ('VLAN 1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        conn.execute(text("UPDATE ip_addresses SET vlan_id = (SELECT id FROM vlans WHERE name = 'VLAN 1') WHERE vlan_id IS NULL"))


@app.on_event("startup")
async def on_startup():
    bootstrap()


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(licences.router)
app.include_router(ip_addresses.router)
app.include_router(admin.router)

@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}

@app.get("/")
def root(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard")
    return RedirectResponse("/login")
