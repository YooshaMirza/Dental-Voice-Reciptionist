import pymongo
import os
import re
from django.conf import settings
from datetime import datetime
from typing import Any, Optional, List, Dict
import logging
from bson import ObjectId

logger = logging.getLogger(__name__)

_config_cache = {
    'data': {},
    'last_mtime': 0
}

# Helper to read config.properties dynamically on change
def load_config():
    config_path = os.path.join(settings.BASE_DIR, 'config.properties')
    if not os.path.exists(config_path):
        return {}
    try:
        current_mtime = os.path.getmtime(config_path)
        if current_mtime == _config_cache['last_mtime']:
            return _config_cache['data']
            
        new_config = {}
        with open(config_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        new_config[key.strip()] = value.strip()
                        
        _config_cache['data'] = new_config
        _config_cache['last_mtime'] = current_mtime
        logger.info(f"🔄 Config reloaded dynamically (mtime: {current_mtime})")
        return new_config
    except Exception as e:
        logger.error(f"Error loading config dynamically: {e}")
        return _config_cache['data'] or {}

def get_twilio_config():
    cfg = load_config()
    return {
        'account_sid': cfg.get('TWILIO_ACCOUNT_SID') or getattr(settings, 'TWILIO_ACCOUNT_SID', ''),
        'auth_token': cfg.get('TWILIO_AUTH_TOKEN') or getattr(settings, 'TWILIO_AUTH_TOKEN', ''),
        'phone_number': cfg.get('TWILIO_PHONE_NUMBER') or getattr(settings, 'TWILIO_PHONE_NUMBER', ''),
        'api_key': cfg.get('TWILIO_API_KEY') or getattr(settings, 'TWILIO_API_KEY', ''),
        'api_secret': cfg.get('TWILIO_API_SECRET') or getattr(settings, 'TWILIO_API_SECRET', ''),
        'app_sid': cfg.get('TWILIO_APP_SID') or getattr(settings, 'TWILIO_APP_SID', ''),
    }

config = load_config()

# MongoDB Connection Details
MONGO_URI = config.get('MONGO_URI', "mongodb://localhost:27017/")
DB_NAME = config.get('DB_NAME', "job_agent")

client = pymongo.MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
db = client[DB_NAME]

# Collections
calls_collection = db['api_calls']
call_records_collection = db['call_records']
context_memory_collection = db['context_memory']
prompts_collection = db['prompts']
feedback_collection = db['feedback']
issues_collection = db['issues']
candidates_collection = db['candidates']
firoz_lalani_collection = db['firoz_lalani']
jobs_collection = db['jobs']
job_applications_collection = db['job_applications']
knowledge_base_collection = db['knowledge_base']

# In-memory store for active call contexts
call_context_store = {}

def get_outbound_context_sync(phone_number: str) -> Optional[dict]:
    """Retrieve call context from DB."""
    try:
        normalized_phone = "".join(filter(str.isdigit, str(phone_number)))[-10:]
        doc = context_memory_collection.find_one({"phone_number": normalized_phone})
        return doc.get("context") if doc else None
    except Exception as e:
        logger.error(f"Error getting outbound context: {e}")
        return None

def get_candidate_by_phone(phone_number: str) -> Optional[dict]:
    """Lookup candidate profile by phone. Matches last 10 digits for robustness."""
    try:
        # Extract last 10 digits for normalization
        digits = "".join(filter(str.isdigit, str(phone_number)))
        if len(digits) < 10:
            return None
        last_10 = digits[-10:]
        
        # Try exact match first (standard)
        candidate = firoz_lalani_collection.find_one({"phone": last_10})
        if candidate:
            return candidate
            
        # Try matching as suffix (handles +1 or other prefixes in DB)
        return firoz_lalani_collection.find_one({"phone": {"$regex": f"{last_10}$"}})
    except Exception as e:
        logger.error(f"Error getting candidate: {e}")
        return None

def get_available_jobs(location: str = None, job_interest: str = None) -> list:
    """Fetch available jobs from DB, with flexible matching for location and interest."""
    try:
        query = {}
        
        # Handle "All over South Africa" or broad location requests
        is_broad_location = False
        if location:
            loc_lower = location.lower()
            broad_keywords = ["all over", "anywhere", "everywhere", "country", "south africa", "nationwide", "any"]
            if any(kw in loc_lower for kw in broad_keywords):
                is_broad_location = True
                logger.info(f"Broad location detected ('{location}'). Skipping city filter.")
        
        if location and not is_broad_location:
            # Handle complex locations like "Cape Town and Johannesburg"
            loc_words = [w.strip() for w in re.split(r'\band\b|\bor\b|,', location) if len(w.strip()) > 2]
            if len(loc_words) > 1:
                query["$or"] = [{"location_city": {"$regex": lw, "$options": "i"}} for lw in loc_words]
            else:
                query["location_city"] = {"$regex": location, "$options": "i"}
            
        # Handle "any" job interest
        is_broad_interest = False
        if job_interest:
            int_lower = job_interest.lower()
            if int_lower in ["any", "all", "anything", "whatever", "open"]:
                is_broad_interest = True
                
        if job_interest and not is_broad_interest:
            # Split interest into words for more flexible regex matching
            words = job_interest.strip().split()
            if words:
                # Create a regex that matches if words appear in any order
                regex_pattern = ".*".join([re.escape(w) for w in words])
                # Search in BOTH title and category
                
                interest_query = [
                    {"title": {"$regex": regex_pattern, "$options": "i"}},
                    {"category": {"$regex": regex_pattern, "$options": "i"}}
                ]
                
                # If query already has an $or (from location), we need to use $and
                if "$or" in query:
                    query["$and"] = [{"$or": query.pop("$or")}, {"$or": interest_query}]
                else:
                    query["$or"] = interest_query
        
        # Initial attempt
        jobs = list(jobs_collection.find(query).limit(5))
        
        # If no results, try an even broader search (individual words)
        if not jobs and job_interest and not is_broad_interest:
            words = job_interest.strip().split()
            if len(words) > 1:
                or_queries = []
                for w in words:
                    if len(w) > 3:
                        or_queries.append({"title": {"$regex": w, "$options": "i"}})
                        or_queries.append({"category": {"$regex": w, "$options": "i"}})
                
                if or_queries:
                    search_query = {"$or": or_queries}
                    # Try dropping the location filter for this broad search
                    jobs = list(jobs_collection.find(search_query).limit(5))

        # FINAL FALLBACK: If still no jobs, just return ANY 5 active jobs
        # so the AI can say "I don't have exactly that, but I have..."
        if not jobs:
            logger.info("No exact jobs found. Falling back to ALL active jobs.")
            jobs = list(jobs_collection.find({}).limit(5))

        for j in jobs: j["_id"] = str(j["_id"])
        return jobs
    except Exception as e:
        logger.error(f"Error getting jobs: {e}")
        return []

def save_job_application(phone_number: str, job_id: str) -> bool:
    """Record a job application."""
    try:
        normalized_phone = "".join(filter(str.isdigit, str(phone_number)))[-10:]
        job_applications_collection.insert_one({
            "phone": normalized_phone,
            "job_id": job_id,
            "status": "applied",
            "applied_at": datetime.utcnow()
        })
        return True
    except Exception as e:
        logger.error(f"Error saving job application: {e}")
        return False

def _sanitize_mongo_uri(uri: str) -> str:
    try:
        if '//' in uri and '@' in uri:
            prefix, rest = uri.split('//', 1)
            creds_and_host = rest.split('@', 1)
            if len(creds_and_host) == 2:
                return f"{prefix}//***@{creds_and_host[1]}"
        return uri
    except Exception:
        return uri

try:
    sanitized = _sanitize_mongo_uri(MONGO_URI)
    logger.info(f"🔌 Connected to MongoDB: {sanitized} (DB: {DB_NAME})")
except Exception as e:
    logger.error(f"❌ MongoDB connection log failed: {e}")

# --- Helper Functions ---

def save_outbound_context_sync(phone_number: str, context: dict):
    """Save call context for outbound calls."""
    try:
        normalized_phone = "".join(filter(str.isdigit, str(phone_number)))[-10:]
        context_memory_collection.update_one(
            {"phone_number": normalized_phone},
            {"$set": {
                "context": context,
                "updated_at": datetime.utcnow()
            }},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error saving outbound context: {e}")
        return False

def upsert_call_record_sync(
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
):
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

def update_call_status_sync(call_sid: str, status: str, duration: Optional[int] = None, error_reason: Optional[str] = None):
    """Update call status in DB."""
    try:
        update_data = {
            "call_status": status,
            "updated_at": datetime.utcnow()
        }
        if duration is not None:
            update_data["call_duration"] = duration
        if error_reason:
            update_data["error_reason"] = error_reason
            
        calls_collection.update_one(
            {"call_sid": call_sid},
            {"$set": update_data},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error updating call status: {e}")
        return False

def update_call_recording_sync(call_sid: str, recording_url: str, recording_duration: Optional[int] = None):
    """Update call record with recording info."""
    try:
        update_data = {
            "call_recording_url": recording_url,
            "updated_at": datetime.utcnow()
        }
        if recording_duration is not None:
            update_data["call_duration"] = recording_duration
            
        calls_collection.update_one(
            {"call_sid": call_sid},
            {"$set": update_data}
        )
        return True
    except Exception as e:
        logger.error(f"Error updating call recording: {e}")
        return False

def update_call_transcript_sync(call_sid: str, transcript_text: str, transcript_turns: Optional[list] = None):
    """Update call with transcript."""
    try:
        update_data = {
            "transcript": {
                "text": transcript_text,
                "turns": transcript_turns or []
            },
            "updated_at": datetime.utcnow()
        }
        calls_collection.update_one(
            {"call_sid": call_sid},
            {"$set": update_data}
        )
        return True
    except Exception as e:
        logger.error(f"Error updating call transcript: {e}")
        return False

def update_call_ai_status_sync(call_sid: str, status: str, error_message: str = None, sentiment: str = None, conversation_summary: str = None):
    """Update AI analysis status and optional sentiment/summary fields."""
    try:
        update_data = {
            "ai_analysis_status": status,
            "ai_analysis_updated_at": datetime.utcnow()
        }
        if error_message:
            update_data["ai_analysis_error"] = error_message
        if sentiment:
            update_data["sentiment"] = sentiment
        if conversation_summary:
            update_data["conversation_summary"] = conversation_summary
            
        calls_collection.update_one(
            {"call_sid": call_sid},
            {"$set": update_data}
        )
        return True
    except Exception as e:
        logger.error(f"Error updating AI status: {e}")
        return False

def get_call_by_sid_sync(call_sid: str) -> Optional[dict]:
    """Get call data by SID."""
    try:
        return calls_collection.find_one({"call_sid": call_sid})
    except Exception as e:
        logger.error(f"Error getting call by SID: {e}")
        return None

def get_calls_missing_recordings_sync(limit: int = 100) -> List[dict]:
    """Return completed calls that do not yet have a saved recording in MongoDB."""
    try:
        query = {
            "call_status": "completed",
            "$or": [
                {"recording_file_data": {"$exists": False}},
                {"recording_file_data": None},
                {"recording_file_data": ""},
            ]
        }
        return list(
            calls_collection.find(query).sort([
                ("call_end_at", -1),
                ("call_created_at", -1),
            ]).limit(limit)
        )
    except Exception as e:
        logger.error(f"Error getting calls missing recordings: {e}")
        return []

def save_feedback_sync(call_sid: str, sentiment: str, comment: str, **kwargs):
    """Save call feedback."""
    try:
        feedback_data = {
            "call_sid": call_sid,
            "sentiment": sentiment,
            "comment": comment,
            "created_at": datetime.utcnow()
        }
        feedback_data.update(kwargs)
        feedback_collection.insert_one(feedback_data)
        return True
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        return False

def save_issue_sync(call_sid: str, category: str, description: str, severity: str = "medium"):
    """Save call issue."""
    try:
        issue_data = {
            "call_sid": call_sid,
            "category": category,
            "description": description,
            "severity": severity,
            "created_at": datetime.utcnow()
        }
        issues_collection.insert_one(issue_data)
        return True
    except Exception as e:
        logger.error(f"Error saving issue: {e}")
        return False

def save_candidate_data(phone_number: str, data: dict) -> bool:
    """Save candidate profile data."""
    try:
        normalized_phone = "".join(filter(str.isdigit, str(phone_number)))[-10:]
        update_data = data.copy()
        update_data["updated_at"] = datetime.utcnow()
        update_data["phone"] = normalized_phone
        
        candidates_collection.update_one(
            {"phone": normalized_phone},
            {"$set": update_data},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error saving candidate data: {e}")
        return False

def save_firoz_lalani_data(phone_number: str, data: dict) -> bool:
    """Save firoz_lalani profile data."""
    try:
        normalized_phone = "".join(filter(str.isdigit, str(phone_number)))[-10:]
        update_data = data.copy()
        update_data["updated_at"] = datetime.utcnow()
        update_data["phone"] = normalized_phone
        
        firoz_lalani_collection.update_one(
            {"phone": normalized_phone},
            {
                "$set": update_data,
                "$setOnInsert": {
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error saving firoz_lalani data: {e}")
        return False

def get_all_prompts_sync() -> List[dict]:
    """Get all prompts."""
    try:
        return list(prompts_collection.find({}, {"_id": 0}))
    except Exception as e:
        logger.error(f"Error getting all prompts: {e}")
        return []

def get_prompt_by_type_sync(prompt_type: str) -> Optional[dict]:
    """Get prompt by type."""
    try:
        return prompts_collection.find_one({"prompt_type": prompt_type}, {"_id": 0})
    except Exception as e:
        logger.error(f"Error getting prompt by type: {e}")
        return None

def save_prompt_sync(prompt_type: str, title: str, text: str, icon: str = None) -> bool:
    """Save or update a prompt."""
    try:
        update_data = {
            "title": title,
            "prompt_text": text,
            "updated_at": datetime.utcnow()
        }
        if icon:
            update_data["icon"] = icon
            
        prompts_collection.update_one(
            {"prompt_type": prompt_type},
            {"$set": update_data},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error saving prompt: {e}")
        return False

def call_sid_lookup_filter(sid_input: Any) -> dict:
    """Filter for looking up calls by various SID formats."""
    sid_str = str(sid_input).strip()
    return {"$or": [
        {"call_sid": sid_str},
        {"voicelink_uid": sid_str},
        {"lead_id": sid_str}
    ]}
