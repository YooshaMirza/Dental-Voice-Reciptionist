"""
Concurrency Tracker
Tracks concurrent operations across the application
"""
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ConcurrencyTracker:
    """Track concurrent operations across the application"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._active_calls = {}  # call_sid -> info
        self._active_gemini_sessions = {}  # call_sid -> start_time
        self._background_tasks = {}  # task_id -> task_type
        
    def register_call(self, call_sid, customer_name, phone):
        """Register a new active call"""
        with self._lock:
            self._active_calls[call_sid] = {
                'start_time': datetime.utcnow(),
                'customer': customer_name,
                'phone': phone
            }
            self._log_status()
    
    def unregister_call(self, call_sid):
        """Unregister a call"""
        with self._lock:
            if call_sid in self._active_calls:
                del self._active_calls[call_sid]
                self._log_status()
    
    def register_gemini_session(self, call_sid):
        """Register a new Gemini session"""
        with self._lock:
            self._active_gemini_sessions[call_sid] = datetime.utcnow()
            self._log_status()
    
    def unregister_gemini_session(self, call_sid):
        """Unregister a Gemini session"""
        with self._lock:
            if call_sid in self._active_gemini_sessions:
                del self._active_gemini_sessions[call_sid]
                self._log_status()
    
    def register_background_task(self, task_id, task_type):
        """Register a background task"""
        with self._lock:
            self._background_tasks[task_id] = task_type
            self._log_status()
    
    def unregister_background_task(self, task_id):
        """Unregister a background task"""
        with self._lock:
            if task_id in self._background_tasks:
                del self._background_tasks[task_id]
                self._log_status()
    
    def _log_status(self):
        """Log current concurrency status"""
        active_calls = len(self._active_calls)
        active_gemini = len(self._active_gemini_sessions)
        background = len(self._background_tasks)
        total = active_calls + background
        
        logger.info(
            f"📊 CONCURRENCY: Calls: {active_calls} | Gemini: {active_gemini} | "
            f"Background: {background} | Total: {total}"
        )
        
        # Warning if approaching limits
        if active_gemini >= 8:
            logger.warning(f"⚠️ HIGH GEMINI USAGE: {active_gemini}/10 sessions active!")
        if active_gemini >= 10:
            logger.error(f"🚨 GEMINI QUOTA LIMIT REACHED: {active_gemini} sessions!")
    
    def get_active_gemini_count(self):
        """Get current number of active Gemini sessions"""
        with self._lock:
            return len(self._active_gemini_sessions)
    
    def get_active_calls(self):
        """Get current number of active calls"""
        with self._lock:
            return len(self._active_calls)



# Global instance
concurrency_tracker = ConcurrencyTracker()
