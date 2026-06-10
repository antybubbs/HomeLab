from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette import status

from app.core.csrf import csrf_context, validate_csrf_token
from app.db.session import get_db
from app.models.models import NetworkMonitor, NetworkMonitorCheck
from app.routers.auth import require_user
from app.services.network_monitor import monitor_label, run_monitor_check_by_id

router = APIRouter(prefix="/network-monitor")
templates = Jinja2Templates(directory="app/templates")


def monitor_rows(db: Session) -> tuple[list[dict], int, int, int]:
    monitors = db.query(NetworkMonitor).filter(
        NetworkMonitor.is_enabled == True
    ).order_by(NetworkMonitor.display_name.asc(), NetworkMonitor.id.asc()).all()
    since = datetime.utcnow() - timedelta(hours=24)
    rows = []
    up_count = 0
    down_count = 0
    for monitor in monitors:
        checks = db.query(NetworkMonitorCheck).filter(
            NetworkMonitorCheck.monitor_id == monitor.id,
            NetworkMonitorCheck.checked_at >= since,
        ).order_by(NetworkMonitorCheck.checked_at.asc()).all()
        recent = checks[-36:]
        total_checks = len(checks)
        total_up = len([check for check in checks if check.status == "up"])
        if monitor.last_status == "up":
            up_count += 1
        if monitor.last_status == "down":
            down_count += 1
        rows.append({
            "monitor": monitor,
            "label": monitor_label(monitor),
            "history": recent,
            "uptime": round((total_up / total_checks) * 100, 1) if total_checks else None,
        })
    return rows, len(monitors), up_count, down_count


@router.get("")
def network_monitor(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    rows, total, up_count, down_count = monitor_rows(db)
    return templates.TemplateResponse(request, "network_monitor.html", {
        "user": user,
        "rows": rows,
        "total": total,
        "up_count": up_count,
        "down_count": down_count,
        **csrf_context(request),
    })


@router.get("/cards")
def network_monitor_cards(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    rows, total, up_count, down_count = monitor_rows(db)
    return templates.TemplateResponse(request, "_network_monitor_cards.html", {
        "user": user,
        "rows": rows,
        "total": total,
        "up_count": up_count,
        "down_count": down_count,
        **csrf_context(request),
    })


@router.post("/{monitor_id}/refresh")
def refresh_monitor(request: Request, monitor_id: int, csrf_token: str = Form(...), db: Session = Depends(get_db), user=Depends(require_user)):
    validate_csrf_token(request, csrf_token)
    monitor = db.get(NetworkMonitor, monitor_id)
    if not monitor or not monitor.is_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    run_monitor_check_by_id(monitor.id)
    return JSONResponse({"ok": True})
