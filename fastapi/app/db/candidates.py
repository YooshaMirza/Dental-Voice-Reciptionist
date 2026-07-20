"""
Patient/lead lookups against the firoz_lalani collection, and outbound call
context storage. Ported from api/db.py.
"""
import logging
from datetime import datetime
from typing import Optional

from app.db.mongo import firoz_lalani_collection, context_memory_collection

logger = logging.getLogger(__name__)


def _last_10_digits(phone_number: str) -> str:
    return "".join(filter(str.isdigit, str(phone_number)))[-10:]


def get_candidate_by_phone(phone_number: str) -> Optional[dict]:
    """Lookup patient profile by phone. Matches last 10 digits for robustness."""
    try:
        digits = "".join(filter(str.isdigit, str(phone_number)))
        if len(digits) < 10:
            return None
        last_10 = digits[-10:]

        candidate = firoz_lalani_collection.find_one({"phone": last_10})
        if candidate:
            return candidate
        return firoz_lalani_collection.find_one({"phone": {"$regex": f"{last_10}$"}})
    except Exception as e:
        logger.error(f"Error getting candidate: {e}")
        return None


def save_firoz_lalani_data(phone_number: str, data: dict) -> bool:
    try:
        normalized_phone = _last_10_digits(phone_number)
        update_data = data.copy()
        update_data["updated_at"] = datetime.utcnow()
        update_data["phone"] = normalized_phone

        firoz_lalani_collection.update_one(
            {"phone": normalized_phone},
            {"$set": update_data, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
        )
        return True
    except Exception as e:
        logger.error(f"Error saving firoz_lalani data: {e}")
        return False


def get_outbound_context(phone_number: str) -> Optional[dict]:
    try:
        normalized_phone = _last_10_digits(phone_number)
        doc = context_memory_collection.find_one({"phone_number": normalized_phone})
        return doc.get("context") if doc else None
    except Exception as e:
        logger.error(f"Error getting outbound context: {e}")
        return None


def save_outbound_context(phone_number: str, context: dict) -> bool:
    try:
        normalized_phone = _last_10_digits(phone_number)
        context_memory_collection.update_one(
            {"phone_number": normalized_phone},
            {"$set": {"context": context, "updated_at": datetime.utcnow()}},
            upsert=True,
        )
        return True
    except Exception as e:
        logger.error(f"Error saving outbound context: {e}")
        return False
