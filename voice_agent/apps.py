from django.apps import AppConfig
import logging
import os
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


class VoiceAgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'voice_agent'
    
    def ready(self):
        """Initialize MongoDB connection and warm up token cache when Django starts"""
        # Database connection will be established on first use
        # This avoids blocking Django startup
        logger.info("✅ Voice Agent app ready - MongoDB will connect on first use")

        # Ensure default web user in MongoDB web_users collection
        try:
            from api.db import db
            web_users = db['web_users']
            user = web_users.find_one({"username": "firoz"})
            if not user:
                web_users.insert_one({
                    "username": "firoz",
                    "password": "firoz@123"
                })
                logger.info("✅ Default MongoDB web user 'firoz' created.")
            else:
                web_users.update_one(
                    {"username": "firoz"},
                    {"$set": {"password": "firoz@123"}}
                )
        except Exception as e:
            logger.warning(f"Failed to ensure default web user in MongoDB: {e}")

        def async_recording_backfill():
            try:
                import asyncio
                from api.db import get_calls_missing_recordings_sync
                from voice_agent.batch_processor import batch_processor

                missing_calls = get_calls_missing_recordings_sync(limit=100)
                if not missing_calls:
                    logger.info("🎧 No completed calls missing recordings at startup.")
                    return

                queued = 0
                for call in missing_calls:
                    call_sid = call.get("call_sid")
                    if not call_sid:
                        continue

                    call_end_time = call.get("call_end_at") or call.get("call_created_at")
                    if not call_end_time:
                        call_end_time = datetime.utcnow()

                    batch_processor.add_to_queue(
                        call_sid=call_sid,
                        call_end_time=call_end_time
                    )
                    queued += 1

                logger.info(f"🎧 Startup recording backfill queued {queued} call(s) missing recordings.")
                if queued > 0:
                    asyncio.run(batch_processor._process_batch())
            except Exception as e:
                logger.warning(f"Startup recording backfill failed: {e}")

        if os.environ.get("VOICE_AGENT_STARTUP_BACKFILL_RAN") != "1":
            os.environ["VOICE_AGENT_STARTUP_BACKFILL_RAN"] = "1"
            backfill_thread = threading.Thread(target=async_recording_backfill, daemon=True)
            backfill_thread.start()
            logger.info("🎧 Startup recording backfill started in background...")
        
        # Pre-create the Vertex token only when Vertex is actually selected.
        # This runs in background to avoid blocking Django startup.
        from django.conf import settings
        from voice_agent.vertex_ai_client import warm_up_token_cache

        if getattr(settings, 'GEMINI_PROVIDER', 'vertex') == 'ai_studio':
            logger.info("🔥 GEMINI_PROVIDER is 'ai_studio' - token cache warm-up skipped.")
            return
        
        def async_token_warmup():
            try:
                warm_up_token_cache()
            except Exception as e:
                logger.warning(f"Token warm-up failed (will retry on first call): {e}")
        
        warmup_thread = threading.Thread(target=async_token_warmup, daemon=True)
        warmup_thread.start()
        logger.info("🔄 Token cache warm-up started in background...")

