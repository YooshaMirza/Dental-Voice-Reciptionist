"""
Outbound Twilio call initiation — ported from api/call_utils.py. This is the
one live outbound path (the old api/twilio_views.py/api/twilio_utils.py dead
code was not carried forward — it had zero callers and a hardcoded placeholder
domain).
"""
import logging

from twilio.rest import Client

from app.core.config import load_config
from app.db.mongo import call_context_store
from app.db.calls import upsert_call_record
from app.db.candidates import save_outbound_context

logger = logging.getLogger(__name__)


def check_dnd_status(phone: str) -> bool:
    """Bypassed for Twilio (ported as-is — Exotel-era DND check, always False now)."""
    return False


def initiate_twilio_call(phone: str, context: dict) -> dict:
    """Initiate an outbound Twilio call with a WebSocket media stream."""
    try:
        cfg = load_config()
        account_sid = cfg.get("TWILIO_ACCOUNT_SID")
        auth_token = cfg.get("TWILIO_AUTH_TOKEN")
        twilio_number = cfg.get("TWILIO_PHONE_NUMBER")
        webhook_base_url = cfg.get("WEBHOOK_BASE_URL")

        client = Client(account_sid, auth_token)

        # NOTE: path kept identical to the old Django app (/api/voice-agent/...) so
        # existing Twilio console phone-number webhook configuration doesn't need
        # to change as part of this migration.
        twiml_url = f"{webhook_base_url}/api/voice-agent/webhooks/twilio/stream/"

        phone_digits = "".join(filter(str.isdigit, str(phone)))[-10:]
        call_context_store[phone_digits] = context
        save_outbound_context(phone, context)

        call = client.calls.create(
            to=phone,
            from_=twilio_number,
            url=twiml_url,
            status_callback=f"{webhook_base_url}/api/voice-agent/webhooks/twilio/status/",
            status_callback_event=["completed", "busy", "no-answer", "failed"],
            record=True,
            recording_status_callback=f"{webhook_base_url}/api/voice-agent/webhooks/twilio/recording/",
            recording_status_callback_event=["completed"],
        )

        upsert_call_record(
            call.sid,
            direction="outbound",
            call_type="dashboard_outbound",
            call_status="queued",
            phone_number=phone_digits,
            from_number=twilio_number,
            to_number=phone,
            customer_name=context.get("customerName"),
            call_notes="Triggered from the dashboard outbound form.",
        )

        return {"status": "success", "call_sid": call.sid}
    except Exception as e:
        logger.error(f"Error in initiate_twilio_call: {e}")
        return {"status": "error", "error": str(e)}
