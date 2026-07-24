"""
Dashboard-editable app settings — stored in MongoDB rather than env vars,
since these are meant to be flipped by office staff from the dashboard UI
without needing a file edit + server restart.
"""
import logging

from app.core.config import load_config
from app.db.mongo import app_settings_collection

logger = logging.getLogger(__name__)

_AUTO_CALL_SETTING_KEY = "ghl_auto_call_on_lead"


def get_auto_call_enabled() -> bool:
    """Whether an incoming GHL lead should immediately trigger an outbound call.
    Seeded once from GHL_AUTO_CALL_ON_LEAD in .env if no DB value exists yet;
    after that, the DB value (editable from the dashboard) is authoritative."""
    doc = app_settings_collection.find_one({"key": _AUTO_CALL_SETTING_KEY})
    if doc is not None:
        return bool(doc.get("enabled", False))

    default_enabled = load_config().get("GHL_AUTO_CALL_ON_LEAD", "false").strip().lower() == "true"
    try:
        app_settings_collection.update_one(
            {"key": _AUTO_CALL_SETTING_KEY},
            {"$set": {"enabled": default_enabled}},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"Failed to seed auto-call setting in DB: {e}")
    return default_enabled


def set_auto_call_enabled(enabled: bool) -> None:
    app_settings_collection.update_one(
        {"key": _AUTO_CALL_SETTING_KEY},
        {"$set": {"enabled": bool(enabled)}},
        upsert=True,
    )
