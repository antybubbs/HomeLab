from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.csrf import csrf_context
from app.db.session import get_db
from app.models.models import NetworkMonitor, NetworkMonitorCheck
from app.routers.auth import require_user
from app.services.network_monitor import monitor_label

router = APIRouter(prefix="/network-monitor")
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def network_monitor(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
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
    return templates.TemplateResponse(request, "network_monitor.html", {
        "user": user,
        "rows": rows,
        "total": len(monitors),
        "up_count": up_count,
        "down_count": down_count,
        **csrf_context(request),
    })
