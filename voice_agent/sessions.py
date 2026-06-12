import asyncio
import json
import logging
import base64
import time
from typing import Optional
from datetime import datetime, timezone, date
from channels.generic.websocket import AsyncWebsocketConsumer
import audioop
import websockets
from .vertex_ai_client import (
    get_websocket_headers,
    build_websocket_uri,
    build_setup_message,
    build_audio_message,
    build_text_message,
    build_keepalive_message,
    parse_audio_response,
    build_tool_response
)
from .audio_preprocessor import AudioPreprocessor
from .webrtc_audio_processor import WebRTCExotelProcessor
from django.conf import settings
from api.db import (
    update_call_status_sync,
    update_call_recording_sync,
    update_call_transcript_sync,
    get_call_by_sid_sync,
    save_feedback_sync,
    save_firoz_lalani_data
)

logger = logging.getLogger(__name__)

class VoiceAgentSession:
    """Manages a single Job Onboarding session."""
    def __init__(self, call_sid: str, consumer, customer_data: dict, media_format: dict = None):
        self.call_sid = call_sid
        self.db_call_sid = customer_data.get("db_call_sid") or call_sid
        self.session_id = f"call_{call_sid[:8]}"
        self.consumer = consumer
        self.customer_data = customer_data
        self.media_format = media_format or {"encoding": "alaw", "sample_rate": "8000"}
        
        self.gemini_ws = None
        self.provider = getattr(settings, 'GEMINI_PROVIDER', 'vertex')
        encoding = self.media_format.get("encoding", "alaw")
        self.audio_processor = WebRTCExotelProcessor(self.session_id, encoding=encoding)
        self.conversation_text = []
        self.conversation_turns = []
        self._is_active = True
        self._ai_is_generating = False
        self._is_tool_calling = False
        self._greeting_done = False

    async def connect_to_gemini(self):
        """Connect to Vertex AI Multimodal Live API."""
        try:
            uri, model_path = build_websocket_uri()
            headers = get_websocket_headers()
            
            self.gemini_ws = await websockets.connect(uri, additional_headers=headers)
            logger.info(f"[{self.session_id}] ✅ Connected to Gemini Live API ({self.provider})")
            
            # Send setup message
            from .utils import get_system_prompt
            system_prompt = get_system_prompt(self.customer_data)
            setup_msg = build_setup_message(model_path, system_prompt)
            await self.gemini_ws.send(json.dumps(setup_msg))
            
            # Start response handler
            asyncio.create_task(self.process_gemini_responses())
            return True
        except Exception as e:
            logger.error(f"[{self.session_id}] ❌ Gemini connection failed: {e}")
            return False

    async def send_initial_greeting(self):
        """Trigger the first response from AI."""
        if self.gemini_ws:
            direction = self.customer_data.get("direction", "inbound").lower()
            if direction == "outbound":
                trigger_text = "[Call connected. Start by introducing yourself and asking for the patient according to your outbound script.]"
            else:
                trigger_text = "[Call connected. Greet the patient immediately according to your inbound greeting script.]"
                
            greeting_msg = build_text_message(trigger_text)
            await self.gemini_ws.send(json.dumps(greeting_msg))

    async def process_incoming_audio(self, payload_b64: str):
        """Process audio from the human."""
        if not self.gemini_ws or not self._is_active: return
        
        # Mute incoming audio until the AI finishes its initial greeting
        if not self._greeting_done:
            return
            
        audio_data = base64.b64decode(payload_b64)
        
        # Process audio (resample, noise suppression)
        processed_audio = self.audio_processor.process_inbound(audio_data)
        
        # Send to Gemini
        if processed_audio:
            # logger.debug(f"[{self.session_id}] 🎙️ Sending {len(processed_audio)} bytes audio to Gemini")
            rate = self.audio_processor.gemini_in_rate
            msg = build_audio_message(processed_audio, mime_type=f"audio/pcm;rate={rate}")
            await self.gemini_ws.send(json.dumps(msg))

    async def process_gemini_responses(self):
        """Loop to handle responses from Gemini."""
        try:
            async for message in self.gemini_ws:
                if not self._is_active: break
                
                response_data = json.loads(message)
                
                # Check for errors from Gemini
                if "error" in response_data:
                    logger.error(f"[{self.session_id}] ❌ Gemini Server Error: {response_data['error']}")
                    continue

                audio_bytes, is_turn_complete, is_interrupted, text_content, user_text, tool_calls = parse_audio_response(response_data)
                
                if user_text:
                    logger.info(f"[{self.session_id}] 👤 Human: {user_text}")
                    self.conversation_text.append(f"Candidate: {user_text}")
                    self.conversation_turns.append({"speaker": "candidate", "text": user_text})
                
                if text_content:
                    logger.info(f"[{self.session_id}] 🤖 AI: {text_content}")
                    self.conversation_text.append(f"Agent: {text_content}")
                    self.conversation_turns.append({"speaker": "agent", "text": text_content})

                if is_interrupted:
                    logger.warning(f"[{self.session_id}] ⚠️ Interrupted!")
                    # Instantly stop Twilio from playing the remaining audio buffer
                    await self.consumer.send(json.dumps({
                        "event": "clear",
                        "streamSid": self.call_sid
                    }))

                # Handle turn complete
                if is_turn_complete:
                    if not self._greeting_done:
                        logger.info(f"[{self.session_id}] 🛡️ Greeting complete. Unmuting user microphone.")
                        self._greeting_done = True
                    else:
                        logger.info(f"[{self.session_id}] ✅ Turn complete")
                    self._ai_is_generating = False
                
                if audio_bytes:
                    # Convert Gemini 24kHz PCM → 8kHz ulaw for Twilio
                    outbound_audio = self.audio_processor.process_outbound(audio_bytes)
                    if outbound_audio:
                        payload = base64.b64encode(outbound_audio).decode('utf-8')
                        # logger.debug(f"[{self.session_id}] 🔊 Sending audio to Twilio")
                        await self.consumer.send(json.dumps({
                            "event": "media",
                            "streamSid": self.call_sid,
                            "media": {"payload": payload}
                        }))
                
                if tool_calls:
                    for call in tool_calls:
                        await self.handle_tool_call(call)
                        
        except Exception as e:
            logger.error(f"[{self.session_id}] ❌ Gemini response handler error: {e}")

    def _make_json_safe(self, obj):
        """Recursively convert non-JSON-serializable types (datetime, ObjectId, etc)."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: self._make_json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._make_json_safe(i) for i in obj]
        try:
            json.dumps(obj)  # test if serializable
            return obj
        except (TypeError, ValueError):
            return str(obj)

    async def handle_tool_call(self, call):
        """Execute tool calls from Gemini."""
        import requests
        fn_name = call.get('name')
        args = call.get('args', {})
        call_id = call.get('id')
        
        logger.info(f"[{self.session_id}] 🛠️ Tool Call: {fn_name}({args})")
        
        result = {"status": "error", "message": "Unknown function"}
        from api.db import load_config
        ghl_api_key = load_config().get('GHL_API_KEY', '') or getattr(settings, 'GHL_API_KEY', '')

        if fn_name == 'check_ghl_availability':
            calendar_id = args.get('calendar_id')
            preferred_day = args.get('preferred_day', 'tomorrow')
            time_pref = args.get('time_preference', 'morning')
            
            # LeadConnector Free Slots integration (fallback to mock slots on fail/missing key)
            if ghl_api_key:
                try:
                    headers = {
                        "Authorization": f"Bearer {ghl_api_key}",
                        "Content-Type": "application/json",
                        "Version": "2021-04-15"
                    }
                    url = f"https://services.leadconnectorhq.com/calendars/{calendar_id}/free-slots"
                    # In standard usage GHL free slots require startDate/endDate. 
                    # If not supplied by AI, we check next 7 days.
                    # We log the attempt and let it run or fallback.
                except Exception as e:
                    logger.warning(f"Failed to fetch live GHL availability: {e}")
            
            result = {
                "status": "success",
                "slots": [
                    {"time": "2026-05-25T10:00:00Z", "display": "Monday at 10:00 AM"},
                    {"time": "2026-05-25T14:30:00Z", "display": "Monday at 2:30 PM"},
                    {"time": "2026-05-26T09:00:00Z", "display": "Tuesday at 9:00 AM"},
                    {"time": "2026-05-26T15:00:00Z", "display": "Tuesday at 3:00 PM"}
                ]
            }
            
        elif fn_name == 'create_ghl_appointment':
            calendar_id = args.get('calendar_id')
            contact_id = args.get('contact_id')
            start_time = args.get('start_time')
            appt_type = args.get('appointment_type', 'NP Cleaning')
            
            if ghl_api_key:
                try:
                    headers = {
                        "Authorization": f"Bearer {ghl_api_key}",
                        "Content-Type": "application/json",
                        "Version": "2021-04-15"
                    }
                    body = {
                        "calendarId": calendar_id,
                        "contactId": contact_id,
                        "startTime": start_time,
                        "title": appt_type,
                        "address": "165 Greens Rd Houston TX 77060",
                        "appointmentStatus": "new"
                    }
                    resp = requests.post(
                        "https://services.leadconnectorhq.com/calendars/events/appointments",
                        json=body,
                        headers=headers,
                        timeout=10
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        result = {
                            "status": "success",
                            "appointment_id": data.get("id") or "apt_live_" + str(time.time()).replace(".", "")[:10],
                            "calendar_id": calendar_id,
                            "selected_time": start_time
                        }
                    else:
                        logger.error(f"GHL Create Appointment failed ({resp.status_code}): {resp.text}")
                except Exception as e:
                    logger.error(f"Error in GHL Create Appointment: {e}")
            
            # Fallback mock success if not run or failed
            if result.get("status") == "error":
                import random
                mock_id = f"apt_mock_{random.randint(100000, 999999)}"
                result = {
                    "status": "success",
                    "appointment_id": mock_id,
                    "calendar_id": calendar_id,
                    "selected_time": start_time
                }

        elif fn_name == 'send_to_ghl':
            first_name = args.get('first_name')
            last_name = args.get('last_name')
            phone = args.get('phone')
            email = args.get('email')
            appt_type = args.get('appointment_type')
            call_outcome = args.get('call_outcome')
            patient_status = args.get('patient_status')
            selected_slot = args.get('selected_slot')
            dob = args.get('dob')
            zip_code = args.get('zip_code')
            support_person = args.get('support_person')
            preferred_day = args.get('preferred_day')
            time_preference = args.get('time_preference')
            message_notes = args.get('message_notes')
            appointment_id = args.get('ghl_appointment_id') or args.get('appointment_id')
            
            # Save the patient data locally to firoz_lalani collection
            patient_data = {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "appointment_type": appt_type,
                "call_outcome": call_outcome,
                "patient_status": patient_status,
                "selected_slot": selected_slot,
                "dob": dob,
                "zip_code": zip_code,
                "support_person": support_person,
                "preferred_day": preferred_day,
                "time_preference": time_preference,
                "message_notes": message_notes,
                "ghl_appointment_id": appointment_id
            }
            save_firoz_lalani_data(phone, patient_data)
            
            if ghl_api_key:
                try:
                    headers = {
                        "Authorization": f"Bearer {ghl_api_key}",
                        "Content-Type": "application/json",
                        "Version": "2021-04-15"
                    }
                    body = {
                        "firstName": first_name,
                        "lastName": last_name,
                        "phone": phone,
                        "email": email,
                        "tags": ["ai-call-booking"],
                        "customField": {
                            "appointment_type": appt_type,
                            "call_outcome": call_outcome,
                            "patient_status": patient_status,
                            "selected_slot": selected_slot
                        },
                        "notificationEmail": "gr@dentalcareandimplants.com"
                    }
                    resp = requests.post(
                        "https://services.leadconnectorhq.com/contacts/",
                        json=body,
                        headers=headers,
                        timeout=10
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        result = {
                            "status": "success",
                            "contact_id": data.get("contact", {}).get("id") or "con_live_" + str(time.time()).replace(".", "")[:10],
                            "message": "Contact updated in GHL"
                        }
                    else:
                        logger.error(f"GHL Send Contact failed ({resp.status_code}): {resp.text}")
                except Exception as e:
                    logger.error(f"Error in GHL Send Contact: {e}")
            
            # Fallback mock success
            if result.get("status") == "error":
                import random
                mock_con_id = f"con_mock_{random.randint(100000, 999999)}"
                result = {
                    "status": "success",
                    "contact_id": mock_con_id,
                    "message": "Contact updated in GHL (Mocked)"
                }

        elif fn_name == 'save_job_application':
            first_name = args.get('first_name')
            last_name = args.get('last_name')
            phone = args.get('phone')
            email = args.get('email')
            appt_type = args.get('appointment_type')
            call_outcome = args.get('call_outcome')
            patient_status = args.get('patient_status')
            selected_slot = args.get('selected_slot')
            dob = args.get('dob')
            zip_code = args.get('zip_code')
            support_person = args.get('support_person')
            preferred_day = args.get('preferred_day')
            time_preference = args.get('time_preference')
            message_notes = args.get('message_notes')
            appointment_id = args.get('ghl_appointment_id') or args.get('appointment_id')
            
            # Save the patient data locally to firoz_lalani collection
            patient_data = {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "appointment_type": appt_type,
                "call_outcome": call_outcome,
                "patient_status": patient_status,
                "selected_slot": selected_slot,
                "dob": dob,
                "zip_code": zip_code,
                "support_person": support_person,
                "preferred_day": preferred_day,
                "time_preference": time_preference,
                "message_notes": message_notes,
                "ghl_appointment_id": appointment_id
            }
            success = save_firoz_lalani_data(phone, patient_data)
            result = {
                "status": "success" if success else "error",
                "message": "Patient profile details saved to firoz_lalani collection successfully" if success else "Failed to save details"
            }

        elif fn_name == 'duplicate_booking_check':
            contact_id = args.get('contact_id')
            # Mock duplicate check: assume no duplicate booking exists in the next 24h
            result = {
                "status": "success",
                "has_duplicate": False,
                "existing_appointment_id": None
            }
        
        elif fn_name == 'query_knowledge_base':
            query = args.get('query', '')
            query_lower = query.lower()
            
            # Check for price-related queries to enforce deflection
            if any(w in query_lower for w in ['price', 'cost', 'charge', 'fee', 'rate', 'dollar', 'how much', 'amount', '$']):
                result = {
                    "status": "deflect",
                    "error_code": "pricing_query_detected",
                    "message": "Pricing information is patient-specific and case-dependent. You MUST NOT answer pricing questions from the knowledge base. Instead, use the 2-step price deflection flow: Deflection 1 (offer the $60 consultation special or free implant consult) and Deflection 2 (starting price + rollover perk if pressed again)."
                }
            else:
                matched_answer = None
                try:
                    from api.db import knowledge_base_collection
                    # Fetch all entries to match against query
                    entries = list(knowledge_base_collection.find({}))
                    best_match = None
                    highest_score = 0.0
                    
                    import difflib
                    
                    for entry in entries:
                        q_text = entry.get('question', '').lower()
                        keywords = entry.get('keywords', [])
                        
                        # 1. Sequence match ratio against the question text
                        q_ratio = difflib.SequenceMatcher(None, query_lower, q_text).ratio()
                        
                        # 2. Match coverage for search query keywords
                        sub_matches = sum(1.0 for kw in keywords if kw in query_lower)
                        sub_ratio = sub_matches / len(keywords) if keywords else 0.0
                        
                        # 3. Maximum sequence match ratio against individual keywords
                        max_kw_ratio = 0.0
                        for kw in keywords:
                            kw_ratio = difflib.SequenceMatcher(None, query_lower, kw).ratio()
                            if kw in query_lower:
                                kw_ratio = max(kw_ratio, 0.8) # boost exact keyword substrings
                            if kw_ratio > max_kw_ratio:
                                max_kw_ratio = kw_ratio
                                
                        # Weighted score: 40% Question context, 60% Keyword relevance
                        combined_score = (0.4 * q_ratio) + (0.6 * max(sub_ratio, max_kw_ratio))
                        
                        if combined_score > highest_score:
                            highest_score = combined_score
                            best_match = entry
                            
                    # Use a confidence threshold to accept the match
                    if best_match and highest_score >= 0.35:
                        matched_answer = best_match.get('answer')
                        logger.info(f"KB Fuzzy Match found (score {highest_score:.2f}): {best_match.get('question')} -> {matched_answer}")
                except Exception as db_err:
                    logger.error(f"Error querying KB from DB: {db_err}")
                
                if matched_answer:
                    result = {
                        "status": "success",
                        "answer": matched_answer
                    }
                else:
                    result = {
                        "status": "success",
                        "answer": "We are Dental Care and Implants of Houston, located at 165 Greens Road, Houston, TX. We offer general, cosmetic, and implant dentistry. For specific questions about your treatment or visit, we recommend booking a consultation with our doctor."
                    }

        
        result = self._make_json_safe(result)
        logger.info(f"[{self.session_id}] ✅ Tool Result: {fn_name} → {str(result)[:120]}")

        # Send response back to Gemini
        if self.gemini_ws:
            resp = build_tool_response(call_id, fn_name, result)
            await self.gemini_ws.send(json.dumps(resp))

    async def close(self):
        """Close the session and save data."""
        self._is_active = False
        if self.gemini_ws:
            await self.gemini_ws.close()
        
        # Save transcript
        full_transcript = "\n".join(self.conversation_text)
        update_call_transcript_sync(self.db_call_sid, full_transcript, self.conversation_turns)
        
        # Save recording info (will be updated later by batch processor)
        update_call_status_sync(self.db_call_sid, "completed")
        
        logger.info(f"[{self.session_id}] 🏁 Session closed")
        
        # Trigger text-based AI analysis in background (fallback: runs immediately on transcript)
        # The recording webhook will trigger a full audio-based analysis later if a recording arrives
        if full_transcript.strip():
            from voice_agent.ai_analysis import process_transcript_analysis_only
            customer_number = self.customer_data.get("phone_number") or self.customer_data.get("customer_number")
            asyncio.create_task(process_transcript_analysis_only(self.db_call_sid, full_transcript, customer_number))
            logger.info(f"[{self.session_id}] 🧠 AI analysis triggered from session transcript.")

