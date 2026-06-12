from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
def twilio_inbound_handler(request):
    """
    Handles inbound calls from Twilio.
    Returns TwiML to connect the call to our WebSocket Media Stream.
    """
    response = VoiceResponse()
    
    # Get the host from the request (needed for the WebSocket URL)
    host = request.get_host()
    scheme = "wss" if request.is_secure() else "ws"
    
    # Create the WebSocket URL for Twilio Media Stream
    # We pass the direction as inbound so the consumer knows how to handle it
    ws_url = f"{scheme}://{host}/ws/twilio/?direction=inbound"
    
    logger.info(f"📞 Twilio Inbound Call received. Connecting to Stream: {ws_url}")
    
    connect = Connect()
    connect.stream(url=ws_url)
    response.append(connect)
    
    return HttpResponse(str(response), content_type='application/xml')

@csrf_exempt
def twilio_outbound_handler(request):
    """
    Handles outbound calls from Twilio (when Twilio executes the URL provided in the API call).
    Returns TwiML to connect the call to our WebSocket Media Stream.
    """
    response = VoiceResponse()
    
    # Extract parameters passed in the URL (e.g. customer name, etc.)
    customer_name = request.GET.get('customerName', 'Job Seeker')
    direction = request.GET.get('direction', 'outbound')
    
    host = request.get_host()
    scheme = "wss" if request.is_secure() else "ws"
    
    # Construct query params for the WebSocket connection
    query_params = f"direction={direction}&customerName={customer_name}"
    ws_url = f"{scheme}://{host}/ws/twilio/?{query_params}"
    
    logger.info(f"📞 Twilio Outbound Call established. Connecting to Stream: {ws_url}")
    
    connect = Connect()
    connect.stream(url=ws_url)
    response.append(connect)
    
    return HttpResponse(str(response), content_type='application/xml')
