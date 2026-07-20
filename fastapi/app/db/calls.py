"""
Call record CRUD — ported from api/db.py.

BUGFIX (vs. the old Django app): `update_call_status` now includes
`call_created_at`/`call_date` in `$setOnInsert`, same as `upsert_call_record`
already did. In the old code, `update_call_status_sync` upserted WITHOUT those
fields — if the call-start upsert ever failed silently, the end-of-call update
became the row's first insert with no `call_created_at`, making it permanently
invisible to the dashboard's date-range filter even though it still received
full AI analysis. Every upsert-capable write here now stamps those fields on
insert so a "headless" call row can never happen again.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.db.mongo import calls_collection

logger = logging.getLogger(__name__)


def upsert_call_record(
    call_sid: str,
    *,
    direction: Optional[str] = None,
    call_type: Optional[str] = None,
    call_status: Optional[str] = None,
    phone_number: Optional[str] = None,
    from_number: Optional[str] = None,
    to_number: Optional[str] = None,
    customer_name: Optional[str] = None,
    call_notes: Optional[str] = None,
) -> bool:
    """Create or update the canonical call record used by the dashboard."""
    try:
        update_data = {"updated_at": datetime.utcnow()}
        if direction is not None:
            update_data["direction"] = direction
        if call_type is not None:
            update_data["call_type"] = call_type
        if call_status is not None:
            update_data["call_status"] = call_status
        if phone_number is not None:
            update_data["phone_number"] = phone_number
        if from_number is not None:
            update_data["from_number"] = from_number
        if to_number is not None:
            update_data["to_number"] = to_number
        if customer_name is not None:
            update_data["customer_name"] = customer_name
        if call_notes is not None:
            update_data["call_notes"] = call_notes

        calls_collection.update_one(
            {"call_sid": call_sid},
            {
                "$set": update_data,
                "$setOnInsert": {
                    "call_sid": call_sid,
                    "call_created_at": datetime.utcnow(),
                    "call_date": datetime.utcnow(),
                },
            },
            upsert=True,
        )
        return True
    except Exception as e:
        logger.error(f"Error upserting call record: {e}")
        return False


def update_call_status(
    call_sid: str,
    status: str,
    duration: Optional[int] = None,
    error_reason: Optional[str] = None,
) -> bool:
    """Update call status in DB. Upserts safely: a never-before-seen call_sid still
    gets call_created_at/call_date stamped, so it can never go missing from the
    dashboard's date-filtered call log (see module docstring)."""
    try:
        update_data = {"call_status": status, "updated_at": datetime.utcnow()}
        if duration is not None:
            update_data["call_duration"] = duration
        if error_reason:
            update_data["error_reason"] = error_reason

        now = datetime.utcnow()
        calls_collection.update_one(
            {"call_sid": call_sid},
            {
                "$set": update_data,
                "$setOnInsert": {
                    "call_sid": call_sid,
                    "call_created_at": now,
                    "call_date": now,
                },
            },
            upsert=True,
        )
        return True
    except Exception as e:
        logger.error(f"Error updating call status: {e}")
        return False


def update_call_recording(call_sid: str, recording_url: str, recording_duration: Optional[int] = None) -> bool:
    try:
        update_data = {"call_recording_url": recording_url, "updated_at": datetime.utcnow()}
        if recording_duration is not None:
            update_data["call_duration"] = recording_duration
        calls_collection.update_one({"call_sid": call_sid}, {"$set": update_data})
        return True
    except Exception as e:
        logger.error(f"Error updating call recording: {e}")
        return False


def update_call_transcript(call_sid: str, transcript_text: str, transcript_turns: Optional[list] = None) -> bool:
    try:
        update_data = {
            "transcript": {"text": transcript_text, "turns": transcript_turns or []},
            "updated_at": datetime.utcnow(),
        }
        calls_collection.update_one({"call_sid": call_sid}, {"$set": update_data})
        return True
    except Exception as e:
        logger.error(f"Error updating call transcript: {e}")
        return False


def update_call_ai_status(
    call_sid: str,
    status: str,
    error_message: Optional[str] = None,
    sentiment: Optional[str] = None,
    conversation_summary: Optional[str] = None,
) -> bool:
    try:
        update_data = {"ai_analysis_status": status, "ai_analysis_updated_at": datetime.utcnow()}
        if error_message:
            update_data["ai_analysis_error"] = error_message
        if sentiment:
            update_data["sentiment"] = sentiment
        if conversation_summary:
            update_data["conversation_summary"] = conversation_summary
        calls_collection.update_one({"call_sid": call_sid}, {"$set": update_data})
        return True
    except Exception as e:
        logger.error(f"Error updating AI status: {e}")
        return False


def get_call_by_sid(call_sid: str) -> Optional[dict]:
    try:
        return calls_collection.find_one({"call_sid": call_sid})
    except Exception as e:
        logger.error(f"Error getting call by SID: {e}")
        return None


def call_sid_lookup_filter(sid_input: Any) -> dict:
    sid_str = str(sid_input).strip()
    return {"$or": [{"call_sid": sid_str}, {"voicelink_uid": sid_str}, {"lead_id": sid_str}]}


def get_calls_missing_recordings(limit: int = 100) -> List[dict]:
    try:
        query = {
            "call_status": "completed",
            "$or": [
                {"recording_file_data": {"$exists": False}},
                {"recording_file_data": None},
                {"recording_file_data": ""},
            ],
        }
        return list(
            calls_collection.find(query)
            .sort([("call_end_at", -1), ("call_created_at", -1)])
            .limit(limit)
        )
    except Exception as e:
        logger.error(f"Error getting calls missing recordings: {e}")
        return []


def save_feedback(call_sid: str, sentiment: str, comment: str, **kwargs) -> bool:
    from app.db.mongo import feedback_collection

    try:
        feedback_data = {
            "call_sid": call_sid,
            "sentiment": sentiment,
            "comment": comment,
            "created_at": datetime.utcnow(),
        }
        feedback_data.update(kwargs)
        feedback_collection.insert_one(feedback_data)
        return True
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        return False
