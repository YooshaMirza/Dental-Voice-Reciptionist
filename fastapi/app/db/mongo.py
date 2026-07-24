"""
MongoDB connection and collection handles. Ported from the old api/db.py.
Kept synchronous (pymongo) intentionally — FastAPI runs sync `def` route
handlers in a threadpool automatically, so this is safe without an async
rewrite, and it's the exact same battle-tested access pattern as before.
"""
import logging
import pymongo

from app.core.config import settings

logger = logging.getLogger(__name__)

client = pymongo.MongoClient(settings.MONGO_URI, tlsAllowInvalidCertificates=True)
db = client[settings.DB_NAME]

# Collections (unchanged names — no data migration needed)
calls_collection = db["api_calls"]
context_memory_collection = db["context_memory"]
prompts_collection = db["prompts"]
feedback_collection = db["feedback"]
issues_collection = db["issues"]
candidates_collection = db["candidates"]
firoz_lalani_collection = db["firoz_lalani"]
knowledge_base_collection = db["knowledge_base"]
users_collection = db["api_customuser"]
web_users_collection = db["web_users"]
ghl_leads_collection = db["ghl_leads"]
app_settings_collection = db["app_settings"]

# In-memory store for active outbound call contexts (mirrors the old process-local store)
call_context_store: dict = {}


def _sanitize_mongo_uri(uri: str) -> str:
    try:
        if "//" in uri and "@" in uri:
            prefix, rest = uri.split("//", 1)
            creds_and_host = rest.split("@", 1)
            if len(creds_and_host) == 2:
                return f"{prefix}//***@{creds_and_host[1]}"
        return uri
    except Exception:
        return uri


try:
    logger.info(f"Connected to MongoDB: {_sanitize_mongo_uri(settings.MONGO_URI)} (DB: {settings.DB_NAME})")
except Exception as e:
    logger.error(f"MongoDB connection log failed: {e}")


def ensure_default_web_user():
    """Matches the old VoiceAgentConfig.ready() behavior: seed a default dashboard login."""
    try:
        user = web_users_collection.find_one({"username": "firoz"})
        if not user:
            web_users_collection.insert_one({"username": "firoz", "password": "firoz@123"})
            logger.info("Default MongoDB web user 'firoz' created.")
    except Exception as e:
        logger.warning(f"Failed to ensure default web user in MongoDB: {e}")
