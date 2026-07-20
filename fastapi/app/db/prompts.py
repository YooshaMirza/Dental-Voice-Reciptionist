"""
System prompt overrides + knowledge base storage. Ported from api/db.py.
"""
import logging
from datetime import datetime
from typing import List, Optional

from app.db.mongo import prompts_collection, knowledge_base_collection

logger = logging.getLogger(__name__)


def get_all_prompts() -> List[dict]:
    try:
        return list(prompts_collection.find({}, {"_id": 0}))
    except Exception as e:
        logger.error(f"Error getting all prompts: {e}")
        return []


def get_prompt_by_type(prompt_type: str) -> Optional[dict]:
    try:
        return prompts_collection.find_one({"prompt_type": prompt_type}, {"_id": 0})
    except Exception as e:
        logger.error(f"Error getting prompt by type: {e}")
        return None


def save_prompt(prompt_type: str, title: str, text: str, icon: Optional[str] = None) -> bool:
    try:
        update_data = {"title": title, "prompt_text": text, "updated_at": datetime.utcnow()}
        if icon:
            update_data["icon"] = icon
        prompts_collection.update_one({"prompt_type": prompt_type}, {"$set": update_data}, upsert=True)
        return True
    except Exception as e:
        logger.error(f"Error saving prompt: {e}")
        return False
