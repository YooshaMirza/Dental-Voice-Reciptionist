"""
Error Tracker
Track and log detailed error information
"""
import logging
from enum import Enum
from datetime import datetime
from .logger_formatter import format_error_box

logger = logging.getLogger(__name__)


class CallFailureReason(Enum):
    """Enumeration of all possible call failure reasons"""
    QUOTA_EXCEEDED = "quota_exceeded"
    GEMINI_CONNECTION_FAILED = "gemini_connection_failed"
    EXOTEL_API_ERROR = "exotel_api_error"
    DND_BLOCKED = "dnd_blocked"
    INVALID_NUMBER = "invalid_number"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    USER_BUSY = "user_busy"
    NO_ANSWER = "no_answer"
    UNKNOWN = "unknown"


class ErrorTracker:
    """Track and log detailed error information"""
    
    # Emoji mapping for different error types
    EMOJI_MAP = {
        CallFailureReason.QUOTA_EXCEEDED: "🚨",
        CallFailureReason.GEMINI_CONNECTION_FAILED: "❌",
        CallFailureReason.EXOTEL_API_ERROR: "⚠️",
        CallFailureReason.DND_BLOCKED: "📵",
        CallFailureReason.INVALID_NUMBER: "🔢",
        CallFailureReason.NETWORK_ERROR: "🌐",
        CallFailureReason.TIMEOUT: "⏱️",
        CallFailureReason.USER_BUSY: "📵",
        CallFailureReason.NO_ANSWER: "📵",
        CallFailureReason.UNKNOWN: "❓"
    }
    
    @staticmethod
    def log_call_failure(call_sid, phone, reason: CallFailureReason, details: str, calls_collection=None):
        """Log detailed call failure information"""
        
        emoji = ErrorTracker.EMOJI_MAP.get(reason, "❌")
        
        # Create error box
        error_details = {
            "Call ID": call_sid[:20] + "..." if len(call_sid) > 20 else call_sid,
            "Phone": phone,
            "Reason": reason.value.upper(),
            "Details": details[:40] + "..." if len(details) > 40 else details,
            "Time": datetime.utcnow().strftime('%H:%M:%S')
        }
        
        title = f"{emoji} CALL FAILED"
        error_box = format_error_box(title, error_details)
        
        logger.error(error_box)
        
        # Save to database if collection provided
        if calls_collection:
            try:
                calls_collection.update_one(
                    {"call_sid": call_sid},
                    {"$set": {
                        "failure_reason": reason.value,
                        "failure_details": details,
                        "failed_at": datetime.utcnow()
                    }},
                    upsert=True
                )
            except Exception as e:
                logger.error(f"Failed to save error to database: {e}")


# Global instance
error_tracker = ErrorTracker()
