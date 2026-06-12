import requests
import logging
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
from api.db import config, save_outbound_context_sync, upsert_call_record_sync
from voice_agent.consumers import call_context_store
import json

logger = logging.getLogger(__name__)

def check_dnd_status(phone):
    """Checks if a number is on DND list (Bypassed for Twilio)."""
    return False


from twilio.rest import Client

def initiate_twilio_call(phone: str, context: dict):
    """
    Initiate an outbound Twilio call with a WebSocket stream.
    """
    try:
        from api.db import load_config
        cfg = load_config()
        account_sid = cfg.get("TWILIO_ACCOUNT_SID")
        auth_token = cfg.get("TWILIO_AUTH_TOKEN")
        twilio_number = cfg.get("TWILIO_PHONE_NUMBER")
        webhook_base_url = cfg.get("WEBHOOK_BASE_URL")
        
        client = Client(account_sid, auth_token)
        
        # TwiML that connects to our WebSocket
        # The TwiML will be served by our TwilioStreamView
        twiml_url = f"{webhook_base_url}/api/voice-agent/webhooks/twilio/stream/"
        
        # Add context as query params to the TwiML URL so we can recover it in the stream
        # Or just use call_context_store
        phone_digits = "".join(filter(str.isdigit, str(phone)))[-10:]
        call_context_store[phone_digits] = context
        save_outbound_context_sync(phone, context)
        
        call = client.calls.create(
            to=phone,
            from_=twilio_number,
            url=twiml_url,
            status_callback=f"{webhook_base_url}/api/voice-agent/webhooks/twilio/status/",
            status_callback_event=['completed', 'busy', 'no-answer', 'failed'],
            record=True,
            recording_status_callback=f"{webhook_base_url}/api/voice-agent/webhooks/twilio/recording/",
            recording_status_callback_event=['completed']
        )

        upsert_call_record_sync(
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
