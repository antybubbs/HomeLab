from pathlib import Path
import tempfile
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import AuditLog
from app.routers.auth import require_admin
from app.services.importer import ImportCSVError, import_csv

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


@router.get("/import")
def import_page(request: Request, user=Depends(require_admin)):
    return templates.TemplateResponse("import.html", {"request": request, "user": user, "message": None, "error": None})


@router.post("/import")
async def import_upload(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(require_admin)):
    if not file.filename.lower().endswith(".csv"):
        return templates.TemplateResponse("import.html", {"request": request, "user": user, "message": None, "error": "Only CSV files are currently supported."}, status_code=400)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        count = import_csv(db, user, tmp_path, request.client.host if request.client else None)
    except ImportCSVError as exc:
        return templates.TemplateResponse("import.html", {"request": request, "user": user, "message": None, "error": str(exc)}, status_code=400)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return templates.TemplateResponse("import.html", {"request": request, "user": user, "message": f"Imported {count} licence records.", "error": None})


@router.get("/audit")
def audit(request: Request, db: Session = Depends(get_db), user=Depends(require_admin)):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return templates.TemplateResponse("audit.html", {"request": request, "user": user, "logs": logs})
