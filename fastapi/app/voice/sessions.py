"""
VoiceAgentSession — manages a single live call's Gemini connection, audio
pipeline, and tool calls. Ported from voice_agent/sessions.py.

Changes vs. the old version:
- Channels' `self.consumer.send(text_data=...)` replaced with the native
  FastAPI/Starlette WebSocket's `self.websocket.send_text(...)`.
- `check_ghl_availability`/`create_ghl_appointment` now call the real GHL
  Calendar API (app/ghl/calendar.py) instead of only building a URL and
  never using it.
"""
import asyncio
import json
import logging
import base64
import difflib
from datetime import datetime, date

import websockets

from app.voice.vertex_ai_client import (
    get_websocket_headers,
    build_websocket_uri,
    build_setup_message,
    build_audio_message,
    build_text_message,
    parse_audio_response,
    build_tool_response,
)
from app.voice.audio_processor import WebRTCExotelProcessor
from app.voice.call_prompts import get_system_prompt
from app.core.config import load_config
from app.db.calls import update_call_status, update_call_transcript
from app.db.candidates import save_firoz_lalani_data
from app.db.mongo import knowledge_base_collection
from app.ghl import calendar as ghl_calendar

logger = logging.getLogger(__name__)


class VoiceAgentSession:
    """Manages a single dental call session (inbound or outbound)."""

    def __init__(self, call_sid: str, websocket, customer_data: dict, media_format: dict = None):
        self.call_sid = call_sid
        self.db_call_sid = customer_data.get("db_call_sid") or call_sid
        self.session_id = f"call_{call_sid[:8]}"
        self.websocket = websocket
        self.customer_data = customer_data
        self.media_format = media_format or {"encoding": "alaw", "sample_rate": "8000"}

        self.gemini_ws = None
        self.provider = load_config().get("GEMINI_PROVIDER", "vertex")
        encoding = self.media_format.get("encoding", "alaw")
        self.audio_processor = WebRTCExotelProcessor(self.session_id, encoding=encoding)
        self.conversation_text = []
        self.conversation_turns = []
        self._is_active = True
        self._ai_is_generating = False
        self._is_tool_calling = False
        self._greeting_done = False
        # Holds calendar_id/contact_id/start_time/appointment_type from
        # create_ghl_appointment when GHL_DEFER_BOOKING_TO_APPROVAL is on, so
        # send_to_ghl/save_job_application can persist them for the real GHL
        # write to happen later, at dashboard-approval time (see handle_tool_call).
        self._pending_booking = {}

    async def connect_to_gemini(self):
        """Connect to the Gemini Live API (Vertex AI or AI Studio)."""
        try:
            uri, model_path = build_websocket_uri()
            headers = get_websocket_headers()

            self.gemini_ws = await websockets.connect(uri, additional_headers=headers)
            logger.info(f"[{self.session_id}] Connected to Gemini Live API ({self.provider})")

            system_prompt = get_system_prompt(self.customer_data)
            setup_msg = build_setup_message(model_path, system_prompt)
            await self.gemini_ws.send(json.dumps(setup_msg))

            asyncio.create_task(self.process_gemini_responses())
            return True
        except Exception as e:
            logger.error(f"[{self.session_id}] Gemini connection failed: {e}")
            return False

    async def send_initial_greeting(self):
        if self.gemini_ws:
            direction = self.customer_data.get("direction", "inbound").lower()
            if direction == "outbound":
                trigger_text = "[Call connected. Start by introducing yourself and asking for the patient according to your outbound script.]"
            else:
                trigger_text = "[Call connected. Greet the patient immediately according to your inbound greeting script.]"

            greeting_msg = build_text_message(trigger_text)
            await self.gemini_ws.send(json.dumps(greeting_msg))

    async def process_incoming_audio(self, payload_b64: str):
        if not self.gemini_ws or not self._is_active:
            return

        if not self._greeting_done:
            return

        audio_data = base64.b64decode(payload_b64)
        processed_audio = self.audio_processor.process_inbound(audio_data)

        if processed_audio:
            rate = self.audio_processor.gemini_in_rate
            msg = build_audio_message(processed_audio, mime_type=f"audio/pcm;rate={rate}")
            await self.gemini_ws.send(json.dumps(msg))

    async def process_gemini_responses(self):
        try:
            async for message in self.gemini_ws:
                if not self._is_active:
                    break

                response_data = json.loads(message)

                if "error" in response_data:
                    logger.error(f"[{self.session_id}] Gemini Server Error: {response_data['error']}")
                    continue

                audio_bytes, is_turn_complete, is_interrupted, text_content, user_text, tool_calls = parse_audio_response(response_data)

                if user_text:
                    logger.info(f"[{self.session_id}] Human: {user_text}")
                    self.conversation_text.append(f"Candidate: {user_text}")
                    self.conversation_turns.append({"speaker": "candidate", "text": user_text})

                if text_content:
                    logger.info(f"[{self.session_id}] AI: {text_content}")
                    self.conversation_text.append(f"Agent: {text_content}")
                    self.conversation_turns.append({"speaker": "agent", "text": text_content})

                if is_interrupted:
                    logger.warning(f"[{self.session_id}] Interrupted!")
                    await self.websocket.send_text(json.dumps({"event": "clear", "streamSid": self.call_sid}))

                if is_turn_complete:
                    if not self._greeting_done:
                        logger.info(f"[{self.session_id}] Greeting complete. Unmuting user microphone.")
                        self._greeting_done = True
                    else:
                        logger.info(f"[{self.session_id}] Turn complete")
                    self._ai_is_generating = False

                if audio_bytes:
                    outbound_audio = self.audio_processor.process_outbound(audio_bytes)
                    if outbound_audio:
                        payload = base64.b64encode(outbound_audio).decode("utf-8")
                        await self.websocket.send_text(json.dumps({
                            "event": "media",
                            "streamSid": self.call_sid,
                            "media": {"payload": payload},
                        }))

                if tool_calls:
                    for call in tool_calls:
                        await self.handle_tool_call(call)

        except Exception as e:
            logger.error(f"[{self.session_id}] Gemini response handler error: {e}")

    def _make_json_safe(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: self._make_json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._make_json_safe(i) for i in obj]
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    async def handle_tool_call(self, call):
        """Execute tool calls from Gemini."""
        fn_name = call.get("name")
        args = call.get("args", {})
        call_id = call.get("id")

        logger.info(f"[{self.session_id}] Tool Call: {fn_name}({args})")

        result = {"status": "error", "message": "Unknown function"}
        ghl_api_key = load_config().get("GHL_API_KEY", "")

        if fn_name == "check_ghl_availability":
            calendar_id = args.get("calendar_id")
            time_pref = args.get("time_preference", "morning")
            slots_result = await asyncio.to_thread(
                ghl_calendar.get_free_slots, calendar_id, ghl_api_key, time_pref
            )
            result = {"status": "success", "slots": slots_result["slots"]}

        elif fn_name == "create_ghl_appointment":
            calendar_id = args.get("calendar_id")
            # The AI is only ever given an opaque contact_id in the system prompt
            # placeholders — trust the value we already have server-side (from the
            # GHL lead webhook) over whatever the model echoes back, in case it
            # garbles or omits it mid-conversation.
            contact_id = self.customer_data.get("contact_id") or args.get("contact_id")
            start_time = args.get("start_time")
            appt_type = args.get("appointment_type", "NP Cleaning")

            defer_booking = load_config().get("GHL_DEFER_BOOKING_TO_APPROVAL", "true").strip().lower() == "true"

            if defer_booking:
                # Do NOT touch the real GHL calendar during the call. The AI still
                # confirms this time with the patient and the call proceeds
                # normally — the real appointment only gets created once staff
                # approves this lead's booking on the dashboard.
                self._pending_booking = {
                    "ghl_calendar_id": calendar_id,
                    "ghl_contact_id": contact_id,
                    "selected_slot_iso": start_time,
                    "appointment_type": appt_type,
                }
                result = {
                    "status": "success",
                    "appointment_id": "pending_approval",
                    "calendar_id": calendar_id,
                    "selected_time": start_time,
                }
                logger.info(f"[{self.session_id}] GHL booking deferred to dashboard approval (calendar={calendar_id}, time={start_time})")
            else:
                result = await asyncio.to_thread(
                    ghl_calendar.create_appointment, calendar_id, contact_id, start_time, appt_type, ghl_api_key
                )

        elif fn_name == "send_to_ghl":
            defer_booking = load_config().get("GHL_DEFER_BOOKING_TO_APPROVAL", "true").strip().lower() == "true"

            patient_data = {
                "first_name": args.get("first_name"),
                "last_name": args.get("last_name"),
                "email": args.get("email"),
                "appointment_type": args.get("appointment_type"),
                "call_outcome": args.get("call_outcome"),
                "patient_status": args.get("patient_status"),
                "selected_slot": args.get("selected_slot"),
                "dob": args.get("dob"),
                "zip_code": args.get("zip_code"),
                "support_person": args.get("support_person"),
                "preferred_day": args.get("preferred_day"),
                "time_preference": args.get("time_preference"),
                "message_notes": args.get("message_notes"),
                # Never a real GHL appointment id while deferred — dashboard approval
                # creates the real one and overwrites this.
                "ghl_appointment_id": None if defer_booking else (args.get("ghl_appointment_id") or args.get("appointment_id")),
                **self._pending_booking,
            }
            phone = args.get("phone")
            await asyncio.to_thread(save_firoz_lalani_data, phone, patient_data)

            if defer_booking:
                # Don't create/update the real GHL contact either — nothing about
                # this lead touches GHL until staff approves it on the dashboard.
                result = {"status": "success", "message": "Saved locally, pending dashboard approval before syncing to GHL."}
            else:
                result = await asyncio.to_thread(
                    ghl_calendar.send_contact,
                    args.get("first_name"),
                    args.get("last_name"),
                    phone,
                    args.get("email"),
                    {
                        "appointment_type": args.get("appointment_type"),
                        "call_outcome": args.get("call_outcome"),
                        "patient_status": args.get("patient_status"),
                        "selected_slot": args.get("selected_slot"),
                    },
                    ghl_api_key,
                )

        elif fn_name == "save_job_application":
            defer_booking = load_config().get("GHL_DEFER_BOOKING_TO_APPROVAL", "true").strip().lower() == "true"
            patient_data = {
                "first_name": args.get("first_name"),
                "last_name": args.get("last_name"),
                "email": args.get("email"),
                "appointment_type": args.get("appointment_type"),
                "call_outcome": args.get("call_outcome"),
                "patient_status": args.get("patient_status"),
                "selected_slot": args.get("selected_slot"),
                "dob": args.get("dob"),
                "zip_code": args.get("zip_code"),
                "support_person": args.get("support_person"),
                "preferred_day": args.get("preferred_day"),
                "time_preference": args.get("time_preference"),
                "message_notes": args.get("message_notes"),
                "ghl_appointment_id": None if defer_booking else (args.get("ghl_appointment_id") or args.get("appointment_id")),
                **self._pending_booking,
            }
            success = await asyncio.to_thread(save_firoz_lalani_data, args.get("phone"), patient_data)
            result = {
                "status": "success" if success else "error",
                "message": "Patient profile details saved to firoz_lalani collection successfully" if success else "Failed to save details",
            }

        elif fn_name == "duplicate_booking_check":
            result = {"status": "success", "has_duplicate": False, "existing_appointment_id": None}

        elif fn_name == "query_knowledge_base":
            result = await asyncio.to_thread(self._query_knowledge_base, args.get("query", ""))

        result = self._make_json_safe(result)
        logger.info(f"[{self.session_id}] Tool Result: {fn_name} -> {str(result)[:120]}")

        if self.gemini_ws:
            resp = build_tool_response(call_id, fn_name, result)
            await self.gemini_ws.send(json.dumps(resp))

    def _query_knowledge_base(self, query: str) -> dict:
        query_lower = query.lower()

        if any(w in query_lower for w in ["price", "cost", "charge", "fee", "rate", "dollar", "how much", "amount", "$"]):
            return {
                "status": "deflect",
                "error_code": "pricing_query_detected",
                "message": "Pricing information is patient-specific and case-dependent. You MUST NOT answer pricing questions from the knowledge base. Instead, use the 2-step price deflection flow: Deflection 1 (offer the $60 consultation special or free implant consult) and Deflection 2 (starting price + rollover perk if pressed again).",
            }

        matched_answer = None
        try:
            entries = list(knowledge_base_collection.find({}))
            best_match = None
            highest_score = 0.0

            for entry in entries:
                q_text = entry.get("question", "").lower()
                keywords = entry.get("keywords", [])

                q_ratio = difflib.SequenceMatcher(None, query_lower, q_text).ratio()
                sub_matches = sum(1.0 for kw in keywords if kw in query_lower)
                sub_ratio = sub_matches / len(keywords) if keywords else 0.0

                max_kw_ratio = 0.0
                for kw in keywords:
                    kw_ratio = difflib.SequenceMatcher(None, query_lower, kw).ratio()
                    if kw in query_lower:
                        kw_ratio = max(kw_ratio, 0.8)
                    if kw_ratio > max_kw_ratio:
                        max_kw_ratio = kw_ratio

                combined_score = (0.4 * q_ratio) + (0.6 * max(sub_ratio, max_kw_ratio))

                if combined_score > highest_score:
                    highest_score = combined_score
                    best_match = entry

            if best_match and highest_score >= 0.35:
                matched_answer = best_match.get("answer")
                logger.info(f"KB Fuzzy Match found (score {highest_score:.2f}): {best_match.get('question')} -> {matched_answer}")
        except Exception as db_err:
            logger.error(f"Error querying KB from DB: {db_err}")

        if matched_answer:
            return {"status": "success", "answer": matched_answer}

        return {
            "status": "success",
            "answer": "We are Dental Care and Implants of Houston, located at 165 Greens Road, Houston, TX. We offer general, cosmetic, and implant dentistry. For specific questions about your treatment or visit, we recommend booking a consultation with our doctor.",
        }

    async def close(self):
        """Close the session and save data."""
        self._is_active = False
        if self.gemini_ws:
            await self.gemini_ws.close()

        full_transcript = "\n".join(self.conversation_text)
        await asyncio.to_thread(update_call_transcript, self.db_call_sid, full_transcript, self.conversation_turns)
        await asyncio.to_thread(update_call_status, self.db_call_sid, "completed")

        logger.info(f"[{self.session_id}] Session closed")

        if full_transcript.strip():
            from app.voice.ai_analysis import process_transcript_analysis_only
            customer_number = self.customer_data.get("phone_number") or self.customer_data.get("customer_number")
            asyncio.create_task(process_transcript_analysis_only(self.db_call_sid, full_transcript, customer_number))
            logger.info(f"[{self.session_id}] AI analysis triggered from session transcript.")
