"""
Loads .env with env-var override, and dynamic reload on file change so
runtime tool calls (Twilio, Gemini, GHL) always see the latest key without a
restart. In production (Railway/Fly.io/etc.), there usually is no .env file
on disk at all — real environment variables set on the platform are what's
read here instead, which is exactly what os.environ already provides.
"""
import os
import logging
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # fastapi/
ENV_PATH = BASE_DIR / ".env"

_config_cache = {"data": {}, "last_mtime": 0}


def load_config() -> dict:
    """Read .env (reloading on change) then overlay real environment variables."""
    file_config = {}
    if ENV_PATH.exists():
        try:
            current_mtime = ENV_PATH.stat().st_mtime
            if current_mtime == _config_cache["last_mtime"]:
                file_config = _config_cache["data"]
            else:
                new_config = {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}
                _config_cache["data"] = new_config
                _config_cache["last_mtime"] = current_mtime
                file_config = new_config
        except Exception as e:
            logger.error(f"Error loading .env: {e}")
            file_config = _config_cache["data"] or {}

    merged = dict(file_config)
    merged.update(os.environ)
    return merged


class Settings:
    """Snapshot of config values read once at process start, for things that don't need hot-reload."""

    def __init__(self):
        cfg = load_config()
        self.MONGO_URI = cfg.get("MONGO_URI", "mongodb://localhost:27017/")
        self.DB_NAME = cfg.get("DB_NAME", "instabus_db")
        self.WEBHOOK_BASE_URL = cfg.get("WEBHOOK_BASE_URL", "http://localhost:8000")
        self.SECRET_KEY = cfg.get("SECRET_KEY", "insecure-dev-key-change-me")
        self.ACCESS_TOKEN_LIFETIME_MINUTES = int(cfg.get("ACCESS_TOKEN_LIFETIME_MINUTES", str(24 * 60)))
        self.REFRESH_TOKEN_LIFETIME_DAYS = int(cfg.get("REFRESH_TOKEN_LIFETIME_DAYS", "7"))


settings = Settings()


def get_twilio_config() -> dict:
    cfg = load_config()
    return {
        "account_sid": cfg.get("TWILIO_ACCOUNT_SID", ""),
        "auth_token": cfg.get("TWILIO_AUTH_TOKEN", ""),
        "phone_number": cfg.get("TWILIO_PHONE_NUMBER", ""),
        "api_key": cfg.get("TWILIO_API_KEY", ""),
        "api_secret": cfg.get("TWILIO_API_SECRET", ""),
        "app_sid": cfg.get("TWILIO_APP_SID", ""),
    }
