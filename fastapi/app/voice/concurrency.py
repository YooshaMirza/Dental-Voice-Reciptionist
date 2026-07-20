import logging

logger = logging.getLogger(__name__)


class ConcurrencyTracker:
    def __init__(self):
        self.active_calls = {}

    def register_call(self, call_sid, customer_name, phone):
        self.active_calls[call_sid] = {"name": customer_name, "phone": phone}
        self._log_stats()

    def unregister_call(self, call_sid):
        if call_sid in self.active_calls:
            del self.active_calls[call_sid]
        self._log_stats()

    def _log_stats(self):
        count = len(self.active_calls)
        logger.info(f"CONCURRENCY: Calls: {count} | Total: {count}")


concurrency_tracker = ConcurrencyTracker()
