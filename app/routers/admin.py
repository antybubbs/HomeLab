from pathlib import Path
import tempfile
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.csrf import csrf_context, validate_csrf_token
from app.db.session import get_db
from app.models.models import AuditLog
from app.routers.auth import require_admin
from app.services.importer import ImportCSVError, import_csv

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


@router.get("/import")
def import_page(request: Request, user=Depends(require_admin)):
    return templates.TemplateResponse("import.html", {"request": request, "user": user, "message": None, "error": None, **csrf_context(request)})


@router.post("/import")
async def import_upload(request: Request, file: UploadFile = File(...), csrf_token: str = Form(...), db: Session = Depends(get_db), user=Depends(require_admin)):
    validate_csrf_token(request, csrf_token)
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        return templates.TemplateResponse("import.html", {"request": request, "user": user, "message": None, "error": "Only CSV files are currently supported.", **csrf_context(request)}, status_code=400)
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    contents = await file.read(max_bytes + 1)
    if len(contents) > max_bytes:
        return templates.TemplateResponse("import.html", {"request": request, "user": user, "message": None, "error": f"CSV file is larger than {get_settings().max_upload_mb} MB.", **csrf_context(request)}, status_code=413)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    try:
        count = import_csv(db, user, tmp_path, request.client.host if request.client else None)
    except ImportCSVError as exc:
        return templates.TemplateResponse("import.html", {"request": request, "user": user, "message": None, "error": str(exc), **csrf_context(request)}, status_code=400)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return templates.TemplateResponse("import.html", {"request": request, "user": user, "message": f"Imported {count} licence records.", "error": None, **csrf_context(request)})


@router.get("/audit")
def audit(request: Request, db: Session = Depends(get_db), user=Depends(require_admin)):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return templates.TemplateResponse("audit.html", {"request": request, "user": user, "logs": logs, **csrf_context(request)})
