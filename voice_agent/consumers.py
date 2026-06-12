import json
import asyncio
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from .sessions import VoiceAgentSession
from .concurrency import concurrency_tracker
from api.db import get_candidate_by_phone, call_context_store, upsert_call_record_sync, get_call_by_sid_sync

logger = logging.getLogger(__name__)

class VoiceAgentConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self._url_to = None
        self._url_from = None
        self._url_direction = None
        self._url_name = None
        self._url_job = None
        self._url_location = None

    async def connect(self):
        await self.accept()
        
        # Parse query parameters (e.g. ?from=...&to=...)
        query_bytes = self.scope.get("query_string", b"")
        query = query_bytes.decode("utf-8")
        logger.info(f"🔌 [DEBUG] WebSocket Query String: {query}")
        
        params = {}
        if query:
            params = dict(p.split("=") for p in query.split("&") if "=" in p)
            
        self._url_to = params.get("to")
        self._url_from = params.get("from")
        self._url_direction = params.get("direction")
        self._url_name = params.get("name")
        self._url_job = params.get("job")
        self._url_location = params.get("location")
        
        logger.info(f"🔌 WebSocket Connected: to={self._url_to}, from={self._url_from}, direction={self._url_direction}")

    async def disconnect(self, close_code):
        if self.session:
            concurrency_tracker.unregister_call(self.session.call_sid)
            await self.session.close()
        logger.info(f"🔌 WebSocket Disconnected (code: {close_code})")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            event = data.get("event")
            
            if event == "connected":
                logger.info("🔗 Twilio stream 'connected' — waiting for 'start' event for session init.")
            elif event == "start":
                await self.handle_start_event(data)
            elif event == "media":
                await self.handle_media_event(data)
            elif event == "stop":
                await self.close()
                
        except Exception as e:
            logger.error(f"❌ Error in receive: {e}")

    async def handle_start_event(self, data):
        start = data.get("start", {})
        stream_sid = start.get("streamSid")
        db_call_sid = start.get("callSid") or start.get("call_sid") or stream_sid
        custom_params = start.get("customParameters", {})
        
        logger.info(f"🚀 Session start event received. SID: {stream_sid}")
        logger.info(f"📦 Custom Parameters: {custom_params}")
        
        # 1. Identity Resolution (Parameter priority)
        # Determine direction first to resolve the correct customer phone number
        direction_from_params = custom_params.get("direction") or self._url_direction
        if not direction_from_params:
            # Check DB for an existing direction set by call_utils.py (outbound calls)
            existing_record = get_call_by_sid_sync(db_call_sid) if db_call_sid else None
            direction_from_params = (existing_record or {}).get("direction") or "inbound"

        if direction_from_params == 'outbound':
            phone = custom_params.get("to") or custom_params.get("from") or self._url_from or "WebDialer"
        else:
            phone = custom_params.get("from") or self._url_from or "WebDialer"

        is_returning = False
        candidate = None
        
        # Strip leading + for lookup if needed, but standard is 10 digits
        search_phone = phone
        if search_phone and search_phone.startswith('+'):
            search_phone = search_phone[-10:]

        if search_phone and search_phone not in ("WebDialer", "None", "unknown"):
            candidate = get_candidate_by_phone(search_phone)
            if candidate:
                is_returning = True
                cand_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip() or candidate.get('name', 'Patient')
                logger.info(f"✅ Returning user detected: {cand_name} ({search_phone})")

        # 2. Context Preparation
        final_data = candidate.copy() if candidate else {}
        
        # Priority: Database name field > Parameter name field
        if candidate:
            cand_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip() or candidate.get('name')
            if cand_name:
                final_data["customerName"] = cand_name
            
        final_data.setdefault("customerName", custom_params.get("name") or self._url_name or "Candidate")
        final_data["job_interest"] = custom_params.get("job") or self._url_job or final_data.get("job_interest", "")
        final_data["location"] = custom_params.get("location") or self._url_location or final_data.get("location", "")
        final_data["direction"] = direction_from_params
        final_data["is_returning"] = is_returning
        final_data["phone_number"] = phone
        final_data["db_call_sid"] = db_call_sid
        
        # Detect encoding
        media_format = start.get("mediaFormat", {})
        encoding = media_format.get("encoding", "ulaw")

        call_direction = final_data["direction"]
        call_type = "dashboard_outbound" if call_direction == "outbound" else "dashboard_inbound"

        twilio_number = custom_params.get("to") if call_direction == "inbound" else custom_params.get("from")

        upsert_call_record_sync(
            db_call_sid,
            direction=call_direction,
            call_type=call_type,
            call_status="in-progress",
            phone_number=phone,
            from_number=phone if call_direction == "inbound" else twilio_number,
            to_number=twilio_number if call_direction == "inbound" else phone,
            customer_name=final_data.get("customerName"),
            call_notes=f"Triggered from the dashboard {call_direction} call.",
        )

        
        # Initialize session
        self.session = VoiceAgentSession(
            call_sid=stream_sid or "unknown",
            consumer=self,
            customer_data=final_data,
            media_format={"encoding": encoding, "sample_rate": 8000}
        )
        
        logger.info(f"🚀 Session initialized: SID={stream_sid}, Encoding={encoding}, Name={final_data['customerName']}")
        concurrency_tracker.register_call(stream_sid, final_data["customerName"], phone)
        asyncio.create_task(self._connect_gemini_async())

    async def _connect_gemini_async(self):
        try:
            await asyncio.wait_for(self.session.connect_to_gemini(), timeout=15.0)
            # Add a small delay to ensure the phone line is fully connected and stable
            # before the AI starts speaking its first words.
            await asyncio.sleep(1.2)
            await self.session.send_initial_greeting()
        except Exception as e:
            logger.error(f"❌ Gemini connection error: {e}")
            await self.close()

    async def handle_media_event(self, data):
        media_payload = data.get("media", {}).get("payload")
        if media_payload and self.session:
            # Monitor energy (debug)
            if not hasattr(self, '_media_chunk_count'): self._media_chunk_count = 0
            self._media_chunk_count += 1
            
            if self._media_chunk_count % 50 == 0:
                energy = self.session.audio_processor._last_energy
                logger.info(f"🎤 [AUDIO_DEBUG] Inbound Energy: {energy}")

            asyncio.create_task(self.session.process_incoming_audio(media_payload))