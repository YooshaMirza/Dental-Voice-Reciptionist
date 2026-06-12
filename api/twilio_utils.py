from twilio.rest import Client
from django.conf import settings
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

def initiate_twilio_call(to_number, customer_name="Job Seeker", direction="outbound", extra_params=None):
    """
    Initiates an outbound call using Twilio.
    The call will hit our /api/twilio/outbound/ webhook to connect the media stream.
    """
    try:
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        from_number = settings.TWILIO_PHONE_NUMBER
        
        if not account_sid or not auth_token or not from_number:
            logger.error("❌ Twilio credentials missing in settings.")
            return None
            
        client = Client(account_sid, auth_token)
        
        # Build the webhook URL with parameters
        # In a real scenario, this should be a public URL
        # For now, we assume the server's public URL is configured or accessible
        # You might need to use a tool like ngrok for local testing
        base_url = "https://your-public-domain.com" # This should ideally come from settings
        
        params = {
            'customerName': customer_name,
            'direction': direction
        }
        if extra_params:
            params.update(extra_params)
            
        url = f"{base_url}/api/twilio/outbound/?{urlencode(params)}"
        
        logger.info(f"🚀 Initiating Twilio call to {to_number} from {from_number}")
        
        call = client.calls.create(
            to=to_number,
            from_=from_number,
            url=url
        )
        
        logger.info(f"✅ Twilio call initiated. SID: {call.sid}")
        return call.sid
        
    except Exception as e:
        logger.error(f"❌ Failed to initiate Twilio call: {e}")
        return None
