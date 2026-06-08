from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from app.core.csrf import csrf_context
from app.routers.auth import require_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard")
def dashboard(request: Request, user=Depends(require_user)):
    return templates.TemplateResponse(request, "dashboard.html", {"user": user, **csrf_context(request)})
