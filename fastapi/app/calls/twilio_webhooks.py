"""
Twilio HTTP webhooks (TwiML + status/recording callbacks) and call
initiation/token endpoints. Ported from voice_agent/views.py — only the live
"Twilio (new platform)" paths were carried forward; the legacy/dead Exotel
views and the unused api/twilio_views.py duplicate path were dropped.

Routes are kept under the same `/api/voice-agent/...` prefix as the old app
so existing Twilio console phone-number configuration doesn't need to change.
"""
import asyncio
import logging
import threading
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

from app.core.config import load_config, get_twilio_config
from app.db.mongo import calls_collection
from app.db.calls import call_sid_lookup_filter
from app.calls.outbound import initiate_twilio_call

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice-agent", tags=["twilio"])


@router.post("/webhooks/twilio/stream/")
async def twilio_stream(request: Request):
    """Returns TwiML to start a WebSocket media stream for a Twilio call."""
    cfg = load_config()
    webhook_base_url = cfg.get("WEBHOOK_BASE_URL", "http://localhost:8000")
    ws_url = webhook_base_url.replace("https://", "wss://").replace("http://", "ws://")

    form = await request.form()
    to_phone = request.query_params.get("To") or form.get("To", "Unknown")
    from_phone = request.query_params.get("From") or form.get("From", "Unknown")
    twilio_direction = (form.get("Direction") or "").lower()
    direction = "outbound" if twilio_direction.startswith("outbound") else "inbound"

    # Outbound calls are already recorded at creation time (record=True passed to
    # calls.create() in app/calls/outbound.py). Inbound calls are answered purely
    # through this TwiML webhook with no recording of their own — without this,
    # they never get a recording or the full audio-based AI analysis pipeline,
    # only the lighter live-transcript fallback. Start one explicitly here so
    # inbound calls get full parity with outbound (recording + Gemini analysis).
    recording_block = ""
    if direction == "inbound":
        recording_block = f"""
    <Start>
        <Recording recordingStatusCallback="{webhook_base_url}/api/voice-agent/webhooks/twilio/recording/" recordingStatusCallbackEvent="completed" />
    </Start>"""

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>{recording_block}
    <Connect>
        <Stream url="{ws_url}/ws/">
            <Parameter name="to" value="{to_phone}" />
            <Parameter name="from" value="{from_phone}" />
            <Parameter name="direction" value="{direction}" />
        </Stream>
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="text/xml")


@router.post("/webhooks/twilio/status/")
async def twilio_status_webhook(request: Request):
    """Handle Twilio call status updates."""
    try:
        form = await request.form()
        call_sid = form.get("CallSid")
        status_value = form.get("CallStatus")
        duration = form.get("CallDuration")

        logger.info(f"Twilio status received: {call_sid} -> {status_value}")

        if call_sid:
            calls_collection.update_one(
                {"call_sid": call_sid},
                {"$set": {
                    "call_status": status_value,
                    "call_duration": int(duration) if duration else 0,
                    "call_end_at": datetime.utcnow(),
                }},
            )
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in twilio_status_webhook: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/webhooks/twilio/recording/")
async def twilio_recording_webhook(request: Request):
    """Handle Twilio recording status updates and trigger AI analysis."""
    try:
        form = await request.form()
        call_sid = form.get("CallSid")
        recording_url = form.get("RecordingUrl") or form.get("RecordingURL")
        recording_sid = form.get("RecordingSid")
        duration = form.get("RecordingDuration")

        logger.info(f"Twilio recording received: call={call_sid} recording={recording_sid}")

        if call_sid and recording_url:
            calls_collection.update_one(
                {"call_sid": call_sid},
                {"$set": {
                    "recording_url": recording_url,
                    "call_recording_url": recording_url,
                    "recording_sid": recording_sid,
                    "recording_duration": int(duration) if duration else None,
                    "recording_fetched_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }},
            )
            logger.info(f"Recording URL saved for {call_sid}. Triggering AI analysis...")

            from app.voice.ai_analysis import process_recording_analysis

            def _run_analysis():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(process_recording_analysis(call_sid, recording_url))
                except Exception as e:
                    logger.error(f"[{call_sid}] AI analysis error: {e}")
                finally:
                    loop.close()

            threading.Thread(target=_run_analysis, daemon=True).start()

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in twilio_recording_webhook: {e}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/api/calls/{call_sid}/recording/")
async def call_recording(call_sid: str):
    """Serves the call recording binary audio data stored directly in MongoDB."""
    call_data = calls_collection.find_one({"call_sid": call_sid})
    if not call_data or "recording_file_data" not in call_data:
        call_data = calls_collection.find_one(call_sid_lookup_filter(call_sid))

    if not call_data or "recording_file_data" not in call_data:
        return JSONResponse({"error": "Recording binary file not found in MongoDB"}, status_code=404)

    binary_data = call_data["recording_file_data"]
    return Response(
        content=binary_data,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f'inline; filename="recording_{call_sid}.mp3"'},
    )


@router.post("/twilio/make-call/")
async def make_call(request: Request):
    """Trigger an outbound Twilio call via API — used by the dashboard's
    "Trigger Outbound Advocate" form (manual test dial, no GHL lead behind it)."""
    data = await request.json()
    phone = data.get("phone")
    if not phone:
        return JSONResponse({"success": False, "error": "Phone number required"}, status_code=400)

    context = {
        "customerName": data.get("customerName") or "Patient",
        "appointment_type": data.get("appointment_type") or "Cleaning",
    }

    res = initiate_twilio_call(phone, context)
    if res["status"] == "success":
        return {"success": True, "call_sid": res["call_sid"]}
    return JSONResponse({"success": False, "error": res.get("error")}, status_code=500)


@router.get("/twilio/token/")
async def twilio_token():
    """Generate a Twilio Access Token for the browser dialer."""
    tw_config = get_twilio_config()
    account_sid = tw_config["account_sid"]
    api_key = tw_config["api_key"]
    api_secret = tw_config["api_secret"]
    app_sid = tw_config["app_sid"]

    identity = "test_user_" + str(ObjectId())[:8]

    if not account_sid or not api_key or not api_secret or not app_sid:
        return JSONResponse({
            "success": False,
            "error": "Twilio configuration is incomplete (requires TWILIO_ACCOUNT_SID, TWILIO_API_KEY, TWILIO_API_SECRET, and TWILIO_APP_SID in config.properties).",
        }, status_code=400)

    try:
        token = AccessToken(account_sid, api_key, api_secret, identity=identity)
        voice_grant = VoiceGrant(outgoing_application_sid=app_sid, incoming_allow=True)
        token.add_grant(voice_grant)
        return {"success": True, "token": token.to_jwt(), "identity": identity}
    except Exception as e:
        logger.error(f"Error generating Twilio capability token: {e}")
        return JSONResponse({
            "success": False,
            "error": f"Failed to generate token: {str(e)}. Make sure your API credentials are correct in config.properties.",
        }, status_code=400)


@router.post("/webhooks/twilio/dialer-twiml/")
async def web_dialer_twiml(request: Request):
    """Handles the call signal from the browser dialer and connects to AI."""
    from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

    cfg = load_config()
    webhook_base_url = cfg.get("WEBHOOK_BASE_URL", "http://localhost:8000")
    ws_url = webhook_base_url.replace("https://", "wss://").replace("http://", "ws://")

    form = await request.form()
    name = form.get("name") or "Candidate"
    job = form.get("job") or ""
    location = form.get("location") or ""
    caller_id = form.get("from") or form.get("From") or "WebDialer"
    call_direction = form.get("direction") or "inbound"

    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=f"{ws_url}/ws/")
    stream.parameter(name="direction", value=call_direction)
    stream.parameter(name="name", value=name)
    stream.parameter(name="job", value=job)
    stream.parameter(name="location", value=location)
    stream.parameter(name="from", value=caller_id)
    connect.append(stream)
    response.append(connect)

    twiml_str = str(response)
    logger.info(f"Generated TwiML: {twiml_str}")
    return Response(content=twiml_str, media_type="text/xml")
