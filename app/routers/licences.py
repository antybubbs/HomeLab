from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session
from starlette import status
from app.core.csrf import csrf_context, validate_csrf_token
from app.core.security import decrypt_secret, encrypt_secret, mask_key
from app.db.session import get_db
from app.models.models import Licence
from app.routers.auth import require_editor, require_user
from app.services.audit import write_audit

router = APIRouter(prefix="/licences")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_licences(request: Request, q: str = Query("", max_length=200), db: Session = Depends(get_db), user=Depends(require_user)):
    query = db.query(Licence)
    clean_q = q.strip()
    if clean_q:
        like = f"%{clean_q}%"
        query = query.filter(or_(Licence.product.ilike(like), Licence.organisation.ilike(like), Licence.licence_type.ilike(like), Licence.licence_id.ilike(like)))
    rows = query.order_by(Licence.product.asc()).limit(500).all()
    return templates.TemplateResponse(request, "licences.html", {"user": user, "rows": rows, "q": clean_q, "mask_key": lambda encrypted: mask_key(decrypt_secret(encrypted)), **csrf_context(request)})


@router.get("/new")
def new_licence(request: Request, user=Depends(require_editor)):
    return templates.TemplateResponse(request, "licence_form.html", {"user": user, "licence": None, **csrf_context(request)})


@router.post("/new")
def create_licence(request: Request, product: str = Form(..., max_length=500), product_key: str = Form(..., max_length=500), organisation: str = Form("", max_length=255), licence_type: str = Form("", max_length=120), seats: int = Form(0, ge=0, le=1000000), notes: str = Form("", max_length=10000), csrf_token: str = Form(...), db: Session = Depends(get_db), user=Depends(require_editor)):
    validate_csrf_token(request, csrf_token)
    product = product.strip()
    product_key = product_key.strip()
    if not product or not product_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product and product key are required")
    row = Licence(product=product, encrypted_product_key=encrypt_secret(product_key), organisation=organisation.strip() or None, licence_type=licence_type.strip() or None, seats=seats, notes=notes.strip() or None)
    db.add(row)
    db.commit()
    write_audit(db, user, "create", "licence", str(row.id), request.client.host if request.client else None)
    return RedirectResponse("/licences", status_code=303)


@router.get("/{licence_id}")
def detail(request: Request, licence_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    row = db.get(Licence, licence_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Licence not found")
    return templates.TemplateResponse(request, "licence_detail.html", {"user": user, "licence": row, "display_key": mask_key(decrypt_secret(row.encrypted_product_key)), "revealed": False, **csrf_context(request)})


@router.post("/{licence_id}/reveal")
def reveal(request: Request, licence_id: int, csrf_token: str = Form(...), db: Session = Depends(get_db), user=Depends(require_editor)):
    validate_csrf_token(request, csrf_token)
    row = db.get(Licence, licence_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Licence not found")
    write_audit(db, user, "reveal", "licence", str(row.id), request.client.host if request.client else None)
    return templates.TemplateResponse(request, "licence_detail.html", {"user": user, "licence": row, "display_key": decrypt_secret(row.encrypted_product_key), "revealed": True, **csrf_context(request)})
