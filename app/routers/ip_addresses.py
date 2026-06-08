from ipaddress import ip_address
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session
from starlette import status
from app.core.csrf import csrf_context, validate_csrf_token
from app.db.session import get_db
from app.models.models import IPAddress
from app.routers.auth import require_editor, require_user
from app.services.audit import write_audit

router = APIRouter(prefix="/ip-addresses")
templates = Jinja2Templates(directory="app/templates")
ASSIGNMENT_TYPES = {"Static", "Dynamic"}


def clean_ip(value: str) -> str:
    value = value.strip()
    try:
        return str(ip_address(value))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Enter a valid IP address.") from exc


def clean_assignment_type(value: str) -> str:
    return value if value in ASSIGNMENT_TYPES else "Static"


def ip_sort_key(row: IPAddress) -> tuple[int, int]:
    parsed = ip_address(row.address)
    return (parsed.version, int(parsed))


@router.get("")
def list_ip_addresses(request: Request, q: str = Query("", max_length=200), db: Session = Depends(get_db), user=Depends(require_user)):
    query = db.query(IPAddress)
    clean_q = q.strip()
    if clean_q:
        like = f"%{clean_q}%"
        query = query.filter(or_(IPAddress.address.ilike(like), IPAddress.name.ilike(like), IPAddress.description.ilike(like), IPAddress.assignment_type.ilike(like), IPAddress.notes.ilike(like)))
    rows = sorted(query.limit(500).all(), key=ip_sort_key)
    total = db.query(IPAddress).count()
    return templates.TemplateResponse(request, "ip_addresses.html", {"user": user, "rows": rows, "total": total, "q": clean_q, **csrf_context(request)})


@router.get("/new")
def new_ip_address(request: Request, user=Depends(require_editor)):
    return templates.TemplateResponse(request, "ip_address_form.html", {"user": user, "record": None, "assignment_types": sorted(ASSIGNMENT_TYPES), "error": None, **csrf_context(request)})


@router.post("/new")
def create_ip_address(request: Request, address: str = Form(..., max_length=80), name: str = Form("", max_length=255), description: str = Form("", max_length=5000), assignment_type: str = Form("Static"), notes: str = Form("", max_length=10000), csrf_token: str = Form(...), db: Session = Depends(get_db), user=Depends(require_editor)):
    validate_csrf_token(request, csrf_token)
    clean_address = clean_ip(address)
    if db.query(IPAddress).filter(IPAddress.address == clean_address).first():
        return templates.TemplateResponse(request, "ip_address_form.html", {"user": user, "record": None, "assignment_types": sorted(ASSIGNMENT_TYPES), "error": "That IP address already exists.", **csrf_context(request)}, status_code=400)
    row = IPAddress(address=clean_address, name=name.strip() or None, description=description.strip() or None, assignment_type=clean_assignment_type(assignment_type), notes=notes.strip() or None)
    db.add(row)
    db.commit()
    write_audit(db, user, "create", "ip_address", str(row.id), request.client.host if request.client else None, detail=clean_address)
    return RedirectResponse("/ip-addresses", status_code=303)


@router.get("/{record_id}")
def detail_ip_address(request: Request, record_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    row = db.get(IPAddress, record_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP address not found")
    return templates.TemplateResponse(request, "ip_address_detail.html", {"user": user, "record": row, **csrf_context(request)})


@router.get("/{record_id}/edit")
def edit_ip_address(request: Request, record_id: int, db: Session = Depends(get_db), user=Depends(require_editor)):
    row = db.get(IPAddress, record_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP address not found")
    return templates.TemplateResponse(request, "ip_address_form.html", {"user": user, "record": row, "assignment_types": sorted(ASSIGNMENT_TYPES), "error": None, **csrf_context(request)})


@router.post("/{record_id}/edit")
def update_ip_address(request: Request, record_id: int, address: str = Form(..., max_length=80), name: str = Form("", max_length=255), description: str = Form("", max_length=5000), assignment_type: str = Form("Static"), notes: str = Form("", max_length=10000), csrf_token: str = Form(...), db: Session = Depends(get_db), user=Depends(require_editor)):
    validate_csrf_token(request, csrf_token)
    row = db.get(IPAddress, record_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP address not found")
    clean_address = clean_ip(address)
    existing = db.query(IPAddress).filter(IPAddress.address == clean_address, IPAddress.id != row.id).first()
    if existing:
        return templates.TemplateResponse(request, "ip_address_form.html", {"user": user, "record": row, "assignment_types": sorted(ASSIGNMENT_TYPES), "error": "That IP address already exists.", **csrf_context(request)}, status_code=400)
    row.address = clean_address
    row.name = name.strip() or None
    row.description = description.strip() or None
    row.assignment_type = clean_assignment_type(assignment_type)
    row.notes = notes.strip() or None
    db.commit()
    write_audit(db, user, "update", "ip_address", str(row.id), request.client.host if request.client else None, detail=clean_address)
    return RedirectResponse(f"/ip-addresses/{row.id}", status_code=303)
