"""
Twilio Media Streams WebSocket endpoint — replaces the old Django Channels
`VoiceAgentConsumer` (voice_agent/consumers.py). No Redis/Channels layer is
used here: nothing in the old code ever did cross-consumer group messaging
(grepped the whole repo — zero `group_send`/`group_add` calls), so a plain
FastAPI WebSocket route is a full behavioral match.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.voice.sessions import VoiceAgentSession
from app.voice.concurrency import concurrency_tracker
from app.db.calls import get_call_by_sid, upsert_call_record
from app.db.candidates import get_candidate_by_phone, get_outbound_context

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
@router.websocket("/ws/")
@router.websocket("/ws/twilio")
@router.websocket("/ws/twilio/")
async def voice_agent_websocket(websocket: WebSocket):
    await websocket.accept()

    query_params = dict(websocket.query_params)
    url_to = query_params.get("to")
    url_from = query_params.get("from")
    url_direction = query_params.get("direction")
    url_name = query_params.get("name")
    url_job = query_params.get("job")
    url_location = query_params.get("location")

    logger.info(f"WebSocket Connected: to={url_to}, from={url_from}, direction={url_direction}")

    session: VoiceAgentSession | None = None

    async def connect_gemini_async(sess: VoiceAgentSession):
        try:
            await asyncio.wait_for(sess.connect_to_gemini(), timeout=15.0)
            await asyncio.sleep(1.2)
            await sess.send_initial_greeting()
        except Exception as e:
            logger.error(f"Gemini connection error: {e}")
            await websocket.close()

    async def handle_start_event(data: dict):
        nonlocal session
        start = data.get("start", {})
        stream_sid = start.get("streamSid")
        db_call_sid = start.get("callSid") or start.get("call_sid") or stream_sid
        custom_params = start.get("customParameters", {})

        logger.info(f"Session start event received. SID: {stream_sid}")
        logger.info(f"Custom Parameters: {custom_params}")

        direction_from_params = custom_params.get("direction") or url_direction
        if not direction_from_params:
            existing_record = get_call_by_sid(db_call_sid) if db_call_sid else None
            direction_from_params = (existing_record or {}).get("direction") or "inbound"

        if direction_from_params == "outbound":
            phone = custom_params.get("to") or custom_params.get("from") or url_from or "WebDialer"
        else:
            phone = custom_params.get("from") or url_from or "WebDialer"

        is_returning = False
        candidate = None

        search_phone = phone
        if search_phone and search_phone.startswith("+"):
            search_phone = search_phone[-10:]

        if search_phone and search_phone not in ("WebDialer", "None", "unknown"):
            candidate = get_candidate_by_phone(search_phone)
            if candidate:
                is_returning = True
                cand_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip() or candidate.get("name", "Patient")
                logger.info(f"Returning user detected: {cand_name} ({search_phone})")

        # For outbound calls, pull in whatever lead context was saved when the call was
        # triggered (e.g. from a GHL lead webhook) — this is where lead_context_summary
        # and other GHL fields (missing tooth, survey answers, etc.) come from, so the
        # outbound opening line can reference them via call_prompts' placeholder passthrough.
        outbound_context = {}
        if direction_from_params == "outbound" and search_phone:
            outbound_context = get_outbound_context(search_phone) or {}

        final_data = {**outbound_context, **(candidate or {})}

        if candidate:
            cand_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip() or candidate.get("name")
            if cand_name:
                final_data["customerName"] = cand_name

        final_data.setdefault("customerName", custom_params.get("name") or url_name or "Candidate")
        final_data["job_interest"] = custom_params.get("job") or url_job or final_data.get("job_interest", "")
        final_data["location"] = custom_params.get("location") or url_location or final_data.get("location", "")
        final_data["direction"] = direction_from_params
        final_data["is_returning"] = is_returning
        final_data["phone_number"] = phone
        final_data["db_call_sid"] = db_call_sid

        media_format = start.get("mediaFormat", {})
        encoding = media_format.get("encoding", "ulaw")

        call_direction = final_data["direction"]
        call_type = "dashboard_outbound" if call_direction == "outbound" else "dashboard_inbound"

        twilio_number = custom_params.get("to") if call_direction == "inbound" else custom_params.get("from")

        upsert_call_record(
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

        session = VoiceAgentSession(
            call_sid=stream_sid or "unknown",
            websocket=websocket,
            customer_data=final_data,
            media_format={"encoding": encoding, "sample_rate": 8000},
        )

        logger.info(f"Session initialized: SID={stream_sid}, Encoding={encoding}, Name={final_data['customerName']}")
        concurrency_tracker.register_call(stream_sid, final_data["customerName"], phone)
        asyncio.create_task(connect_gemini_async(session))

    try:
        while True:
            text_data = await websocket.receive_text()
            try:
                data = json.loads(text_data)
                event = data.get("event")

                if event == "connected":
                    logger.info("Twilio stream 'connected' - waiting for 'start' event for session init.")
                elif event == "start":
                    await handle_start_event(data)
                elif event == "media":
                    media_payload = data.get("media", {}).get("payload")
                    if media_payload and session:
                        asyncio.create_task(session.process_incoming_audio(media_payload))
                elif event == "stop":
                    break
            except Exception as e:
                logger.error(f"Error in receive: {e}")
    except WebSocketDisconnect:
        pass
    finally:
        if session:
            concurrency_tracker.unregister_call(session.call_sid)
            await session.close()
        logger.info("WebSocket Disconnected")
