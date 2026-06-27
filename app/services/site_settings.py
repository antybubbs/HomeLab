from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.branding import APP_BRAND_NAME
from app.models.models import RemoteManagerSetting


DEFAULT_SITE_SETTINGS = {
    "app_name": APP_BRAND_NAME,
    "base_url": "http://localhost:8080",
    "github_repo": "antybubbs/HomeLab",
    "version_check_interval_seconds": "1800",
    "guacd_host": "",
    "guacd_port": "",
    "max_upload_mb": "25",
}


def get_site_setting(db: Session, key: str) -> str:
    row = (
        db.query(RemoteManagerSetting)
        .filter(RemoteManagerSetting.key == key)
        .first()
    )

    if row and row.value is not None:
        return row.value

    if key in DEFAULT_SITE_SETTINGS:
        return DEFAULT_SITE_SETTINGS[key]

    return str(getattr(get_settings(), key, ""))