"""
Auth user storage — raw pymongo against the `api_customuser` collection
(same collection name the old Django/Djongo app used, so no data migration
is needed). Djongo's ORM is gone; this replaces it with the same direct
pymongo pattern api/db.py and api/jwt_auth.py already fell back to for
reliable ObjectId lookups.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from app.db.mongo import users_collection

logger = logging.getLogger(__name__)


def get_user_by_email(email: str) -> Optional[dict]:
    return users_collection.find_one({"email": email.strip().lower()})


def get_user_by_id(user_id: str) -> Optional[dict]:
    try:
        return users_collection.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def get_user_by_phone(phone: str) -> Optional[dict]:
    return users_collection.find_one({"phone": phone})


def create_user(*, email: str, password_hash: str, first_name: str, phone: str, role: str = "admin") -> dict:
    email = email.strip().lower()
    doc = {
        "email": email,
        "username": email[:150],
        "first_name": first_name,
        "phone": phone,
        "role": role,
        "agent_name": "Lindiwe",
        "voicelink_did": None,
        "is_active": True,
        "password": password_hash,
        "date_joined": datetime.now(timezone.utc),
    }
    result = users_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def update_user_password(user_id: str, password_hash: str) -> bool:
    try:
        result = users_collection.update_one(
            {"_id": ObjectId(user_id)}, {"$set": {"password": password_hash}}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Error updating user password: {e}")
        return False
