"""
Views for Voice Agent - Webhooks and Call Initiation
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
import json
import logging
import redis
import asyncio
from datetime import datetime, timedelta
import requests
from requests.auth import HTTPBasicAuth
from api.call_utils import check_dnd_status
from .consumers import call_context_store
from bson import ObjectId
from api.db import save_outbound_context_sync, calls_collection, firoz_lalani_collection, call_sid_lookup_filter
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Dial, Client, Connect, Stream, Parameter

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class ExotelStatusWebhookView(APIView):
    """Handle Exotel status callback webhook"""
    
    def post(self, request):
        try:
            data = request.data if hasattr(request, 'data') else json.loads(request.body)
            logger.info(f"📞 Exotel webhook received: {json.dumps(data, indent=2)}")
            
            call_sid = data.get("CallSid") or data.get("call_sid") or data.get("Sid")
            status_value = data.get("Status") or data.get("status")
            duration = data.get("Duration") or data.get("duration")
            phone_number = None
            
            logger.info(f"📞 Call Status Update: {call_sid} - {status_value} (Duration: {duration}s)")
            
            if call_sid:
                # Update only api_calls (db_call) collection.
                call_record = calls_collection.find_one({"call_sid": call_sid})
                
                if call_record:
                    if call_record.get('direction') == 'outbound':
                        phone_number = data.get("To") or data.get("to")
                    else:
                        phone_number = data.get("From") or data.get("from")
                
                # Fallback phone extraction if record not found yet
                if not phone_number:
                    phone_number = data.get("To") or data.get("to") or data.get("From") or data.get("from")

                # Map Exotel status to db_call status field.
                status_map = {
                    "in-progress": "in-progress",
                    "completed": "completed",
                    "busy": "busy",
                    "no-answer": "no_answer",
                    "chanunavail": "chan_unavail",
                    "chan-unavail": "chan_unavail",
                    "failed": "failed",
                    "canceled": "cancelled",
                }
                normalized_status = (status_value or "unknown").strip().lower()
                mapped_status = status_map.get(normalized_status, normalized_status)

                update_data = {
                    "call_status": mapped_status,
                    "call_end_at": datetime.utcnow(),
                }
                if phone_number:
                    update_data["phone_number"] = phone_number
                if duration:
                    try:
                        update_data["call_duration"] = int(duration)
                    except (TypeError, ValueError):
                        logger.warning(f"⚠️ Invalid duration received for {call_sid}: {duration}")

                # Optional DND enrichment for failed calls, stored on same call record.
                if mapped_status == "failed" and phone_number:
                    try:
                        is_dnd = check_dnd_status(phone_number)
                        update_data["dnd_status"] = bool(is_dnd)
                        if is_dnd:
                            update_data["error_reason"] = "DND Blocked (Post-Call Check)"
                            update_data["call_status"] = "dnd_blocked"
                    except Exception as dnd_err:
                        logger.warning(f"⚠️ DND check failed for {phone_number}: {dnd_err}")

                # $set only touches listed fields; booking_id and other insert-time fields stay.
                try:
                    result = calls_collection.update_one(
                        {"call_sid": call_sid},
                        {"$set": update_data}
                    )
                    if result.modified_count > 0:
                        logger.info(f"✅ Updated call {call_sid} status to '{status_value}'")
                    else:
                        logger.warning(f"⚠️ Call {call_sid} not found in calls collection")
                except Exception as call_err:
                    logger.error(f"⚠️ Failed to update call status: {call_err}")
            
            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"❌ Error handling Exotel webhook: {e}")
            return Response({"status": "error", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# @method_decorator(csrf_exempt, name='dispatch')
# class ExotelStatusWebhookView(APIView):
#     """Handle Exotel status callback webhook"""
    
#     def post(self, request):
#         try:
#             data = request.data if hasattr(request, 'data') else json.loads(request.body)
#             logger.info(f"📞 Exotel webhook received: {json.dumps(data, indent=2)}")
            
#             call_sid = data.get("CallSid") or data.get("call_sid") or data.get("Sid")
#             status_value = data.get("Status") or data.get("status")
#             duration = data.get("Duration") or data.get("duration")
#             phone_number = None
            
#             logger.info(f"📞 Call Status Update: {call_sid} - {status_value} (Duration: {duration}s)")
            
#             if call_sid:
#                 # Use synchronous pymongo update (api.db.calls_collection)
#                 from api.db import calls_collection, bookings_collection
#                 from datetime import datetime, timedelta
                
#                 # Get call record to determine direction for phone number extraction AND call_type
#                 call_record = calls_collection.find_one({"call_sid": call_sid})
#                 call_type = "feedback"  # Default for backward compatibility
                
#                 if call_record:
#                     # Extract call_type from call record (NEW)
#                     call_type = call_record.get('call_type', 'feedback')
                    
#                     if call_record.get('direction') == 'outbound':
#                         phone_number = data.get("To") or data.get("to")
#                     else:
#                         phone_number = data.get("From") or data.get("from")
                
#                 # Fallback phone extraction if record not found yet
#                 if not phone_number:
#                     phone_number = data.get("To") or data.get("to") or data.get("From") or data.get("from")

#                 # Update calls collection
#                 try:
#                     update_data = {
#                         "status": status_value.lower() if status_value else "unknown",
#                         "end_time": datetime.utcnow()
#                     }
#                     if duration:
#                         update_data["duration"] = int(duration)
                    
#                     result = calls_collection.update_one(
#                         {"call_sid": call_sid},
#                         {"$set": update_data}
#                     )
#                     if result.modified_count > 0:
#                         logger.info(f"✅ Updated call {call_sid} status to '{status_value}'")
#                     else:
#                         logger.warning(f"⚠️ Call {call_sid} not found in calls collection")
#                 except Exception as call_err:
#                     logger.error(f"⚠️ Failed to update call status: {call_err}")
                
#                 # Also update bookings collection to reflect call completion
#                 if phone_number and status_value:
#                     try:
#                         # Categorize failures: retryable (system) vs non-retryable (user)
#                         RETRYABLE_STATUSES = ['failed']  # System errors
#                         NON_RETRYABLE_STATUSES = ['busy', 'no-answer']  # User errors
                        
#                         # Map Exotel status to booking call_status
#                         status_map = {
#                             "completed": "completed",
#                             "busy": "busy",
#                             "no-answer": "no_answer",
#                             "in-progress": "in_progress"
#                         }
                        
#                         # HYBRID DND DETECTION: Check DND only for "failed" status
#                         if status_value.lower() == "failed":
#                             # Import DND check function
#                             from api.call_utils import check_dnd_status
                            
#                             # Check if failure is due to DND
#                             logger.info(f"🔍 Call failed - checking if DND for {phone_number}")
#                             is_dnd = check_dnd_status(phone_number)
                            
#                             if is_dnd:
#                                 booking_status = "dnd_blocked"
#                                 logger.warning(f"📵 Failure confirmed as DND for {phone_number}")
                                
#                                 # Log DND block to calls collection for reporting
#                                 try:
#                                     calls_collection.insert_one({
#                                         "phone_number": phone_number,
#                                         "status": "dnd_blocked",
#                                         "dnd_status": True,
#                                         "created_at": datetime.utcnow(),
#                                         "error_reason": "DND Blocked (Post-Call Check)"
#                                     })
#                                 except Exception as log_err:
#                                     logger.error(f"Failed to log DND block: {log_err}")
#                             else:
#                                 booking_status = "failed"
#                                 logger.warning(f"❌ Failure due to network/invalid number for {phone_number}")
#                         else:
#                             booking_status = status_map.get(status_value.lower(), status_value.lower())
                        
#                         # Use dynamic field names based on call_type (NEW)
#                         status_field = f"call_status_{call_type}"  # e.g., "call_status_post_booking"
#                         completed_field = f"call_completed_at_{call_type}"  # e.g., "call_completed_at_post_booking"
#                         retry_field = f"retry_count_{call_type}"  # e.g., "retry_count_post_booking"
                        
#                         # Get current booking to check retry_count (using dynamic field)
#                         booking = bookings_collection.find_one({
#                             "passenger_phone": phone_number,
#                             status_field: "called"
#                         })
                        
#                         if booking:
#                             retry_count = booking.get(retry_field, 0)
                            
#                             # Check if this is a retryable failure
#                             if status_value.lower() in RETRYABLE_STATUSES and retry_count < 2:
#                                 # Mark for retry
#                                 retry_count += 1
#                                 retry_after = None
                                
#                                 # Add 2-minute delay only for 2nd retry
#                                 if retry_count >= 2:
#                                     retry_after = datetime.utcnow() + timedelta(minutes=2)
                                
#                                 # Use dynamic field names (NEW)
#                                 update_data = {
#                                     status_field: "retry_needed",
#                                     f"retry_reason_{call_type}": f"Exotel status: {status_value}",
#                                     retry_field: retry_count,
#                                     f"last_retry_at_{call_type}": datetime.utcnow()
#                                 }
                                
#                                 if retry_after:
#                                     update_data[f"retry_after_{call_type}"] = retry_after
                                
#                                 bookings_collection.update_one(
#                                     {"_id": booking["_id"]},
#                                     {"$set": update_data}
#                                 )
#                                 logger.info(f"📝 Marked {phone_number} for {call_type} retry (attempt {retry_count}/2)")
                            
#                             elif status_value.lower() in RETRYABLE_STATUSES and retry_count >= 2:
#                                 # Max retries exceeded (NEW: use dynamic fields)
#                                 bookings_collection.update_one(
#                                     {"_id": booking["_id"]},
#                                     {"$set": {
#                                         status_field: "failed_permanent",
#                                         f"final_status_{call_type}": "max_retries_exceeded",
#                                         completed_field: datetime.utcnow()
#                                     }}
#                                 )
#                                 logger.warning(f"⚠️ Max {call_type} retries (2) exceeded for {phone_number}")
                            
#                             else:
#                                 # Non-retryable or completed (NEW: use dynamic fields)
#                                 bookings_collection.update_one(
#                                     {"_id": booking["_id"]},
#                                     {"$set": {
#                                         status_field: booking_status,
#                                         completed_field: datetime.utcnow()
#                                     }}
#                                 )
#                                 logger.info(f"✅ Updated {call_type} booking status to '{booking_status}'")
#                         else:
#                             logger.warning(f"⚠️ No active {call_type} booking found with {status_field}='called' for {phone_number}")
                        
#                     except Exception as booking_err:
#                         logger.error(f"⚠️ Failed to update booking status: {booking_err}")

                
#                 # --- TRIGGER NEXT CALL (Sequential Processing with Retry Logic) ---
#                 # NEW: Only process next call of the SAME call_type
#                 if status_value.lower() in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
#                     try:
#                         # Build dynamic query for THIS call_type only (NEW)
#                         status_field = f"call_status_{call_type}"
#                         retry_field = f"retry_count_{call_type}"
#                         retry_after_field = f"retry_after_{call_type}"
#                         queued_at_field = f"queued_at_{call_type}"
                        
#                         # Find next call of the SAME call_type: prioritize retries, then queued
#                         next_passenger = bookings_collection.find_one(
#                             {
#                                 "$or": [
#                                     {status_field: "retry_needed", retry_field: 1},
#                                     {status_field: "retry_needed", retry_field: 2, retry_after_field: {"$lte": datetime.utcnow()}},
#                                     {status_field: "queued"}
#                                 ]
#                             },
#                             sort=[(retry_field, 1), (queued_at_field, 1)]
#                         )
                        
#                         # Loop until we successfully start a call or run out of queued items
#                         while next_passenger:
#                             logger.info(f"🔄 Chain Reaction ({call_type}): Triggering next call for {next_passenger.get('passenger_phone')} (status: {next_passenger.get(status_field)}, retry: {next_passenger.get(retry_field, 0)})...")
#                             result = initiate_call_for_booking(next_passenger, call_type)  # Pass call_type (NEW)
                            
#                             if result.get('status') == 'success':
#                                 break  # One active call launched
                            
#                             # If skipped (DND) or failed, try next immediately
#                             next_passenger = bookings_collection.find_one(
#                                 {
#                                     "$or": [
#                                         {status_field: "retry_needed", retry_field: 1},
#                                         {status_field: "retry_needed", retry_field: 2, retry_after_field: {"$lte": datetime.utcnow()}},
#                                         {status_field: "queued"}
#                                     ]
#                                 },
#                                 sort=[(retry_field, 1), (queued_at_field, 1)]
#                             )
                        
#                         # ✅ CRITICAL: If no more calls to trigger, try to start batch processing
#                         if not next_passenger:
#                             logger.info("✅ No more calls queued - checking if batch can start")
#                             try:
#                                 from voice_agent.batch_processor import batch_processor
#                                 import asyncio
#                                 import threading
                                
#                                 # Get the running event loop from the main thread
#                                 try:
#                                     loop = asyncio.get_running_loop()
#                                 except RuntimeError:
#                                     # No loop running, try to get the default loop
#                                     loop = asyncio.get_event_loop()
                                
#                                 # Schedule the coroutine in the event loop
#                                 asyncio.run_coroutine_threadsafe(
#                                     batch_processor.try_start_batch(),
#                                     loop
#                                 )
#                             except Exception as e:
#                                 # Silently ignore - batch will be triggered from session end anyway
#                                 logger.debug(f"Could not trigger batch from webhook: {e}")
#                     except Exception as chain_err:
#                         logger.error(f"❌ Chain Reaction Error: {chain_err}")
            
#             return Response({"status": "success"}, status=status.HTTP_200_OK)
            
#         except Exception as e:
#             logger.error(f"❌ Error handling Exotel webhook: {e}")
#             return Response({"status": "error", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
#         # Absolute fallback return
#         return Response({"status": "fallback_success"}, status=status.HTTP_200_OK)




@method_decorator(csrf_exempt, name='dispatch')
class InitiateExotelCallView(APIView):
    """
    Django view to initiate Exotel call
    Replaces FastAPI /make-call endpoint
    """
    
    def post(self, request):
        try:
            data = request.data if hasattr(request, 'data') else json.loads(request.body)
            phone_number = data.get('phone')
            customer_name = data.get('customerName', 'Customer')
            trip_route = data.get('tripRoute', 'Unknown')
            bus_agency_name = data.get('busAgencyName', 'Your Bus Operator')
            
            if not phone_number:
                return Response({"success": False, "error": "Phone required"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Save context (same as FastAPI)
            normalized_phone = phone_number[-10:]
            context = {
                "customerName": customer_name,
                "tripRoute": trip_route,
                "busAgencyName": bus_agency_name,
                "agent_name": data.get("agent_name", "Puja"),
                "discount": data.get("discount", 10),
                "full_phone": phone_number,
                "booking_id": data.get('booking_id') or data.get('bookingId'),
                "route_id": data.get('route_id') or data.get('routeId'),
                "passenger_id": data.get('passenger_id') or data.get('passengerId') or data.get('passanger_id'),
            }
            
            # Save to memory
            call_context_store[normalized_phone] = context
            
            # Save to database
            save_outbound_context_sync(phone_number, context)
            
            logger.info(f"💾 Context saved for {normalized_phone}")
            
            # --- DND CHECK ---
            if check_dnd_status(phone_number):
                # Log to DB
                from datetime import datetime
                calls_collection.insert_one({
                    "phone_number": phone_number,
                    "customer_name": customer_name,
                    "trip_route": trip_route,
                    "status": "dnd_blocked",
                    "dnd_status": True,
                    "created_at": datetime.utcnow(),
                    "error_reason": "DND Blocked (Manual Call)"
                })
                
                return Response({
                    "success": False, 
                    "error": "Call blocked: Number is on DND list"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Exotel API call
            sid = settings.EXOTEL_SID
            key = settings.EXOTEL_API_KEY
            token = settings.EXOTEL_API_TOKEN
            caller_id = settings.EXOTEL_CALLER_ID
            app_id = settings.EXOTEL_APP_ID
            
            exotel_flow_url = f"http://my.exotel.com/{sid}/exoml/start_voice/{app_id}"
            api_url = f"https://api.exotel.com/v1/Accounts/{sid}/Calls/connect.json"
            
            # IMPORTANT: Update this to your Django deployment URL
            webhook_base_url = settings.WEBHOOK_BASE_URL
            
            payload = {
                'From': phone_number,
                'CallerId': caller_id,
                'Url': exotel_flow_url,
                'CallType': 'trans',
                'StatusCallback': f'{webhook_base_url}/api/voice-agent/webhooks/exotel/status/',
                'StatusCallbackEvents': 'completed,busy,no-answer,failed',
                'Record': 'true'
            }
            
            response = requests.post(
                api_url,
                auth=HTTPBasicAuth(key, token),
                data=payload
            )
            
            if response.status_code == 200:
                call_sid = response.json().get('Call', {}).get('Sid')
                return Response({"success": True, "callSid": call_sid})
            else:
                return Response({"success": False, "error": response.text}, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Error initiating call: {e}")
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# LOCAL RECORDINGS SERVER
# =============================================================================
@method_decorator(csrf_exempt, name='dispatch')
class CallRecordingAPI(APIView):
    """
    Serves the call recording binary audio data from MongoDB calls_collection.
    """
    def get(self, request, call_sid):
        try:
            # Find the call directly in MongoDB calls_collection
            call_data = calls_collection.find_one({"call_sid": call_sid})
            if not call_data or "recording_file_data" not in call_data:
                # Try fallback matching
                call_data = calls_collection.find_one(call_sid_lookup_filter(call_sid))
                
            if not call_data or "recording_file_data" not in call_data:
                return Response({"error": "Recording binary file not found in MongoDB"}, status=status.HTTP_404_NOT_FOUND)
                
            binary_data = call_data["recording_file_data"]
            # Return binary data as audio response
            response = HttpResponse(binary_data, content_type="audio/mpeg")
            response["Content-Disposition"] = f'inline; filename="recording_{call_sid}.mp3"'
            return response
        except Exception as e:
            logger.error(f"Error serving local call recording: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class TwilioStreamView(APIView):
    """
    Returns TwiML to start a WebSocket stream for Twilio calls.
    """
    def post(self, request):
        webhook_base_url = settings.WEBHOOK_BASE_URL
        # Normalize https to wss
        ws_url = webhook_base_url.replace("https://", "wss://").replace("http://", "ws://")
        
        # Get metadata from request (passed as query params or body)
        data = request.data if hasattr(request, 'data') else request.POST
        to_phone = request.GET.get('To') or data.get('To', 'Unknown')
        from_phone = request.GET.get('From') or data.get('From', 'Unknown')
        # Twilio sends 'outbound-api' or 'outbound-dial' for outbound calls, NOT just 'outbound'
        twilio_direction = (data.get('Direction') or '').lower()
        direction = "outbound" if twilio_direction.startswith('outbound') else "inbound"

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}/ws/">
            <Parameter name="to" value="{to_phone}" />
            <Parameter name="from" value="{from_phone}" />
            <Parameter name="direction" value="{direction}" />
        </Stream>
    </Connect>
</Response>"""
        return HttpResponse(twiml, content_type="text/xml")

@method_decorator(csrf_exempt, name='dispatch')
class TwilioStatusWebhookView(APIView):
    """
    Handle Twilio call status updates.
    """
    def post(self, request):
        try:
            data = request.data if hasattr(request, 'data') else json.loads(request.body)
            call_sid = data.get('CallSid')
            status_value = data.get('CallStatus')
            duration = data.get('CallDuration')
            
            logger.info(f"📞 Twilio status received: {call_sid} -> {status_value}")
            
            if call_sid:
                calls_collection.update_one(
                    {"call_sid": call_sid},
                    {"$set": {
                        "call_status": status_value,
                        "call_duration": int(duration) if duration else 0,
                        "call_end_at": datetime.utcnow()
                    }}
                )
            return Response({"status": "success"})
        except Exception as e:
            logger.error(f"Error in TwilioStatusWebhookView: {e}")
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class TwilioRecordingWebhookView(APIView):
    """
    Handle Twilio recording status updates and persist the recording URL.
    """
    def post(self, request):
        try:
            data = request.data if hasattr(request, 'data') else json.loads(request.body)
            call_sid = data.get('CallSid')
            recording_url = data.get('RecordingUrl') or data.get('RecordingURL')
            recording_sid = data.get('RecordingSid')
            duration = data.get('RecordingDuration')

            logger.info(f"🎙️ Twilio recording received: call={call_sid} recording={recording_sid}")

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
                    }}
                )
                logger.info(f"📥 Recording URL saved for {call_sid}. Triggering AI analysis...")
                # Trigger AI analysis in a background thread so we return 200 fast
                import threading
                from voice_agent.ai_analysis import process_recording_analysis
                def _run_analysis():
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(process_recording_analysis(call_sid, recording_url))
                    except Exception as e:
                        logger.error(f"[{call_sid}] AI analysis error: {e}")
                    finally:
                        loop.close()
                threading.Thread(target=_run_analysis, daemon=True).start()

            return Response({"status": "success"})
        except Exception as e:
            logger.error(f"Error in TwilioRecordingWebhookView: {e}")
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class InitiateTwilioCallView(APIView):
    """
    Trigger an outbound Twilio call via API.
    """
    def post(self, request):
        try:
            data = request.data if hasattr(request, 'data') else json.loads(request.body)
            phone = data.get('phone')
            if not phone:
                return Response({"success": False, "error": "Phone number required"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Prepare context
            context = {
                "customerName": data.get('customerName', 'Candidate'),
                "job_interest": data.get('job_interest'),
                "location": data.get('location'),
                "agent_name": data.get('agent_name', 'Career Assistant'),
                "agency": data.get('agency', 'South African Job Portal')
            }
            
            from api.call_utils import initiate_twilio_call
            res = initiate_twilio_call(phone, context)
            
            if res["status"] == "success":
                return Response({"success": True, "call_sid": res["call_sid"]})
            else:
                return Response({"success": False, "error": res.get("error")}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Error in InitiateTwilioCallView: {e}")
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TwilioTokenView(APIView):
    """
    Generate a Twilio Access Token for the browser dialer.
    """
    def get(self, request):
        from api.db import get_twilio_config
        
        tw_config = get_twilio_config()
        
        # Use trial credentials if matching to avoid Account SID / API Key mismatch
        from api.db import config as db_config
        trial_account_sid = db_config.get('TRIAL_TWILIO_ACCOUNT_SID')
        trial_api_key = db_config.get('TRIAL_TWILIO_API_KEY')
        
        if trial_account_sid and tw_config['api_key'] == trial_api_key:
            account_sid = trial_account_sid
            api_key = trial_api_key
            api_secret = db_config.get('TRIAL_TWILIO_API_SECRET')
            app_sid = db_config.get('TRIAL_TWILIO_APP_SID')
            logger.info("🔑 Twilio token generated using Trial Account SID credentials.")
        else:
            account_sid = tw_config['account_sid']
            api_key = tw_config['api_key']
            api_secret = tw_config['api_secret']
            app_sid = tw_config['app_sid']
            logger.info("🔑 Twilio token generated using Primary Account SID credentials.")
        
        # Identity for this user
        identity = 'test_user_' + str(ObjectId())[:8]
        
        if not account_sid or not api_key or not api_secret or not app_sid:
            return JsonResponse({
                'success': False,
                'error': 'Twilio configuration is incomplete (requires TWILIO_ACCOUNT_SID, TWILIO_API_KEY, TWILIO_API_SECRET, and TWILIO_APP_SID in config.properties).'
            }, status=400)
            
        try:
            token = AccessToken(account_sid, api_key, api_secret, identity=identity)
            
            voice_grant = VoiceGrant(
                outgoing_application_sid=app_sid,
                incoming_allow=True,
            )
            token.add_grant(voice_grant)
            
            return JsonResponse({'success': True, 'token': token.to_jwt(), 'identity': identity})
        except Exception as e:
            logger.error(f"Error generating Twilio capability token: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Failed to generate token: {str(e)}. Make sure your API credentials are correct in config.properties.'
            }, status=400)

class WebDialerUI(APIView):
    """
    Renders the custom Web Dialer HTML.
    """
    def get(self, request):
        if not request.session.get('web_user'):
            return redirect('voice_agent:login')
        return render(request, 'voice_agent/dialer.html')

@method_decorator(csrf_exempt, name='dispatch')
class WebDialerTwiMLView(APIView):
    """
    Handles the call signal from the browser dialer and connects to AI.
    Receives caller context (name, job, location) from the dialer form and
    passes them to the WebSocket session as query params.
    """
    def post(self, request):
        response = VoiceResponse()
        webhook_base_url = settings.WEBHOOK_BASE_URL
        ws_url = webhook_base_url.replace("https://", "wss://").replace("http://", "ws://")

        # Read caller context forwarded from the browser Twilio SDK custom params
        name = request.data.get("name") or request.POST.get("name") or "Candidate"
        job = request.data.get("job") or request.POST.get("job") or ""
        location = request.data.get("location") or request.POST.get("location") or ""
        caller_id = request.data.get("from") or request.POST.get("From") or "WebDialer"

        # Read direction from request (browser dialer passes it as custom param)
        call_direction = request.data.get("direction") or request.POST.get("direction") or "inbound"

        # Generate TwiML with Stream Parameters (more reliable than query strings)
        connect = Connect()
        stream = Stream(url=f"{ws_url}/ws/")
        stream.parameter(name='direction', value=call_direction)
        stream.parameter(name='name', value=name)
        stream.parameter(name='job', value=job)
        stream.parameter(name='location', value=location)
        stream.parameter(name='from', value=caller_id)
        
        connect.append(stream)
        response.append(connect)

        twiml_str = str(response)
        logger.info(f"📡 [DEBUG] Generated TwiML: {twiml_str}")
        return HttpResponse(twiml_str, content_type='text/xml')


from api.models import Call, FirozLalani

class DoctorDashboardUI(APIView):
    """
    Renders the doctor dashboard UI with statistics, patient records, and testing suite.
    """
    def get(self, request):
        if not request.session.get('web_user'):
            return redirect('voice_agent:login')

        import pytz
        import datetime
        from django.utils import timezone
        
        central_tz = pytz.timezone('US/Central')
        
        # 1. Parse or fallback selected_date
        date_str = request.GET.get('date')
        selected_date = None
        if date_str:
            try:
                selected_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
                
        if not selected_date:
            # Fallback to the latest call's local date
            latest_call = Call.objects.all().order_by('-call_created_at').first()
            if latest_call and latest_call.call_created_at:
                selected_date = latest_call.call_created_at.astimezone(central_tz).date()
            elif latest_call and latest_call.call_date:
                selected_date = latest_call.call_date.astimezone(central_tz).date()
            else:
                selected_date = datetime.datetime.now(central_tz).date()
                
        # 2. Get local day start and end, and convert to UTC timezone-aware datetimes
        start_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.min))
        end_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.max))
        
        start_utc = start_local.astimezone(pytz.UTC)
        end_utc = end_local.astimezone(pytz.UTC)
        
        # 3. Apply the timezone filter
        calls_on_date = Call.objects.filter(call_created_at__gte=start_utc, call_created_at__lte=end_utc)
        patients_on_date = FirozLalani.objects.filter(created_at__gte=start_utc, created_at__lte=end_utc)
        appointments_on_date = patients_on_date.exclude(selected_slot__isnull=True).exclude(selected_slot="")
        
        # Fetch statistics for the selected date
        total_calls = calls_on_date.count()
        total_appointments = appointments_on_date.count()
        total_new_patients = patients_on_date.filter(patient_status="new_patient").count()
        
        # Sentiment ratios for the selected date
        positive_sentiment = calls_on_date.filter(sentiment="positive").count()
        neutral_sentiment = calls_on_date.filter(sentiment="neutral").count()
        negative_sentiment = calls_on_date.filter(sentiment="negative").count()
        
        # Retrieve call logs for the selected date (recent 100)
        call_logs = calls_on_date.order_by('-call_created_at' if 'call_created_at' in [f.name for f in Call._meta.get_fields()] else '-_id')[:100]
        
        # Retrieve patient list for the selected date (recent 100)
        patients = patients_on_date.order_by('-created_at')[:100]
        
        # Retrieve all appointments for the selected date
        appointment_list = appointments_on_date.order_by('-created_at')[:100]
        
        # 4. Compute next/prev date strings
        prev_date_str = (selected_date - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        next_date_str = (selected_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        selected_date_str = selected_date.strftime('%Y-%m-%d')
        
        day = selected_date.day
        month_year = selected_date.strftime('%B %Y')
        selected_date_display = f"{day} {month_year}"

        context = {
            'total_calls': total_calls,
            'total_appointments': total_appointments,
            'total_new_patients': total_new_patients,
            'sentiment': {
                'positive': positive_sentiment,
                'neutral': neutral_sentiment,
                'negative': negative_sentiment,
            },
            'call_logs': call_logs,
            'patients': patients,
            'appointments': appointment_list,
            'twilio_configured': bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_API_KEY),
            'prev_date_str': prev_date_str,
            'next_date_str': next_date_str,
            'selected_date_str': selected_date_str,
            'selected_date_display': selected_date_display,
        }
        return render(request, 'voice_agent/dashboard.html', context)


class CallDetailsAPI(APIView):
    """
    Returns call details (transcript, sentiment, summary) in JSON format.
    """
    def get(self, request, call_sid):
        try:
            call = Call.objects.get(call_sid=call_sid)
            transcript_data = call.transcript or {}
            analysis_profile = None
            if call.phone_number:
                digits = "".join(filter(str.isdigit, str(call.phone_number)))
                if len(digits) >= 10:
                    analysis_profile = firoz_lalani_collection.find_one({"phone": digits[-10:]})
            
            # Determine the call recording URL.
            # If we have saved the binary recording file in MongoDB calls_collection, we serve it locally.
            local_recording_url = ""
            call_raw = calls_collection.find_one({"call_sid": call_sid})
            if not call_raw:
                call_raw = calls_collection.find_one(call_sid_lookup_filter(call_sid))
                
            if call_raw and "recording_file_data" in call_raw:
                local_recording_url = f"/api/voice-agent/api/calls/{call_sid}/recording/"
            
            recording_url = local_recording_url or call.call_recording_url or ""
            
            # Formulate the response
            data = {
                'call_sid': call.call_sid,
                'direction': call.direction,
                'phone_number': call.phone_number or call.from_number or "",
                'customer_name': call.customer_name or "",
                'call_date': call.call_date.isoformat() if call.call_date else (call.call_created_at.isoformat() if call.call_created_at else None),
                'call_duration': call.call_duration or 0,
                'call_status': call.call_status or "completed",
                'call_type': call.call_type or "unknown",
                'call_notes': call.call_notes or "",
                'call_created_at': call.call_created_at.isoformat() if call.call_created_at else None,
                'call_end_at': call.call_end_at.isoformat() if call.call_end_at else None,
                'sentiment': call.sentiment or "neutral",
                'conversation_summary': call.conversation_summary or "",
                'call_feedback': call.call_feedback or "",
                'call_rating': call.call_rating,
                'transcript': transcript_data.get('text', ''),
                'turns': transcript_data.get('turns', []),
                'call_recording_url': recording_url,
                'recording_status': 'available' if recording_url else 'pending',
                'analysis_profile': {
                    'first_name': analysis_profile.get('first_name') if analysis_profile else None,
                    'last_name': analysis_profile.get('last_name') if analysis_profile else None,
                    'dob': analysis_profile.get('dob') if analysis_profile else None,
                    'zip_code': analysis_profile.get('zip_code') if analysis_profile else None,
                    'support_person': analysis_profile.get('support_person') if analysis_profile else None,
                    'appointment_type': analysis_profile.get('appointment_type') if analysis_profile else None,
                    'preferred_day': analysis_profile.get('preferred_day') if analysis_profile else None,
                    'time_preference': analysis_profile.get('time_preference') if analysis_profile else None,
                    'selected_slot': analysis_profile.get('selected_slot') if analysis_profile else None,
                    'call_outcome': analysis_profile.get('call_outcome') if analysis_profile else None,
                    'patient_status': analysis_profile.get('patient_status') if analysis_profile else None,
                    'message_notes': analysis_profile.get('message_notes') if analysis_profile else None,
                    'last_call_sentiment': analysis_profile.get('last_call_sentiment') if analysis_profile else None,
                }
            }
            return JsonResponse({'success': True, 'call': data})
        except Call.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Call details not found'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
class UpdateBookingAPI(APIView):
    def post(self, request):
        try:
            patient_id = request.data.get('patient_id')
            status_val = request.data.get('status')
            
            if not patient_id or status_val not in ['confirmed', 'declined']:
                return JsonResponse({'success': False, 'error': 'Invalid parameters'}, status=400)
            
            patient = FirozLalani.objects.get(_id=ObjectId(patient_id))
            patient.booking_status = status_val
            
            from api.db import load_config
            ghl_api_key = load_config().get('GHL_API_KEY', '') or getattr(settings, 'GHL_API_KEY', '')
            
            # Sync to GHL API if we have an API Key and a real appointment ID
            if ghl_api_key and patient.ghl_appointment_id:
                app_id = patient.ghl_appointment_id
                # Check that it's a real GHL ID, not a mock/fallback string
                if not any(app_id.startswith(pfx) for pfx in ['ghl_apt_', 'apt_mock_', 'apt_live_']):
                    try:
                        headers = {
                            "Authorization": f"Bearer {ghl_api_key}",
                            "Content-Type": "application/json",
                            "Version": "2021-04-15"
                        }
                        ghl_status = "confirmed" if status_val == "confirmed" else "cancelled"
                        body = {
                            "appointmentStatus": ghl_status
                        }
                        import requests
                        resp = requests.put(
                            f"https://services.leadconnectorhq.com/calendars/events/appointments/{app_id}",
                            json=body,
                            headers=headers,
                            timeout=10
                        )
                        if resp.status_code == 200:
                            logger.info(f"Sync: Updated GHL appointment {app_id} status to '{ghl_status}'")
                        else:
                            logger.error(f"Sync: GHL update failed for {app_id} ({resp.status_code}): {resp.text}")
                    except Exception as e:
                        logger.error(f"Sync: Error updating GHL appointment {app_id}: {e}")

            if status_val == 'confirmed' and not patient.ghl_appointment_id:
                # Mock fallback if not already set by call booking
                import time
                patient.ghl_appointment_id = 'ghl_apt_' + str(time.time()).replace('.', '')[:10]
            
            patient.save()
            return JsonResponse({'success': True, 'booking_status': patient.booking_status})
            
        except FirozLalani.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Patient not found'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class CustomLoginUI(APIView):
    """
    Renders the secure login portal and authenticates against MongoDB.
    """
    def get(self, request):
        if request.session.get('web_user'):
            return redirect('voice_agent:dashboard')
        return render(request, 'voice_agent/login.html')

    def post(self, request):
        username = request.data.get('username') or request.POST.get('username')
        password = request.data.get('password') or request.POST.get('password')
        
        # Check against MongoDB web_users collection
        from api.db import db
        web_users = db['web_users']
        user = web_users.find_one({"username": username, "password": password})
        
        if user:
            request.session['web_user'] = username
            return redirect('voice_agent:dashboard')
        else:
            return render(request, 'voice_agent/login.html', {'error': 'Invalid username or password.'})


class CustomLogoutUI(APIView):
    """
    Signs out the current user session.
    """
    def get(self, request):
        request.session.pop('web_user', None)
        return redirect('voice_agent:login')


@method_decorator(csrf_exempt, name='dispatch')
class KnowledgeBaseAPI(APIView):
    """
    API for listing, creating, and updating Knowledge Base entries.
    """
    def get(self, request):
        try:
            from api.db import knowledge_base_collection
            entries = list(knowledge_base_collection.find({}))
            serialized = []
            for entry in entries:
                entry['_id'] = str(entry['_id'])
                serialized.append(entry)
            return JsonResponse({'success': True, 'data': serialized})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def post(self, request):
        try:
            from api.db import knowledge_base_collection
            data = json.loads(request.body) if request.body else {}
            
            kb_id = data.get('id') or data.get('_id')
            category = data.get('category', 'general')
            question = data.get('question', '')
            answer = data.get('answer', '')
            keywords_raw = data.get('keywords', '')
            
            # Parse keywords
            if isinstance(keywords_raw, str):
                keywords = [k.strip().lower() for k in keywords_raw.split(',') if k.strip()]
            elif isinstance(keywords_raw, list):
                keywords = [str(k).strip().lower() for k in keywords_raw if str(k).strip()]
            else:
                keywords = []
                
            doc = {
                'category': category,
                'question': question,
                'answer': answer,
                'keywords': keywords
            }
            
            if category == 'pricing':
                doc['procedure_name'] = data.get('procedure_name', '')
                doc['starting_price'] = data.get('starting_price', '')
                doc['notes'] = data.get('notes', '')
                
            if kb_id:
                knowledge_base_collection.update_one({'_id': ObjectId(kb_id)}, {'$set': doc})
                doc['_id'] = str(kb_id)
                message = "Knowledge Base rule updated successfully."
            else:
                result = knowledge_base_collection.insert_one(doc)
                doc['_id'] = str(result.inserted_id)
                message = "Knowledge Base rule added successfully."
                
            return JsonResponse({'success': True, 'message': message, 'data': doc})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class KnowledgeBaseDetailAPI(APIView):
    """
    API for deleting specific Knowledge Base entries.
    """
    def delete(self, request, kb_id):
        try:
            from api.db import knowledge_base_collection
            result = knowledge_base_collection.delete_one({'_id': ObjectId(kb_id)})
            if result.deleted_count > 0:
                return JsonResponse({'success': True, 'message': 'Rule deleted successfully.'})
            return JsonResponse({'success': False, 'error': 'Rule not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class SystemPromptsAPI(APIView):
    """
    API for retrieving and live-saving system prompts to MongoDB.
    """
    def get(self, request):
        try:
            from api.db import prompts_collection
            from voice_agent.call_prompts import INBOUND_SYSTEM_PROMPT, OUTBOUND_SYSTEM_PROMPT
            
            inbound = prompts_collection.find_one({"prompt_type": "inbound"})
            if not inbound:
                inbound = {
                    "prompt_type": "inbound",
                    "title": "Inbound Assistant (Alice)",
                    "prompt_text": INBOUND_SYSTEM_PROMPT
                }
                prompts_collection.insert_one(inbound.copy())
                
            outbound = prompts_collection.find_one({"prompt_type": "outbound"})
            if not outbound:
                outbound = {
                    "prompt_type": "outbound",
                    "title": "Outbound Patient Advocate (Dentina)",
                    "prompt_text": OUTBOUND_SYSTEM_PROMPT
                }
                prompts_collection.insert_one(outbound.copy())
                
            return JsonResponse({
                'success': True,
                'prompts': {
                    'inbound': inbound.get('prompt_text', ''),
                    'outbound': outbound.get('prompt_text', '')
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def post(self, request):
        try:
            from api.db import prompts_collection
            data = json.loads(request.body) if request.body else {}
            prompt_type = data.get('prompt_type')
            prompt_text = data.get('prompt_text')
            
            if prompt_type not in ['inbound', 'outbound']:
                return JsonResponse({'success': False, 'error': 'Invalid prompt type.'}, status=400)
                
            prompts_collection.update_one(
                {"prompt_type": prompt_type},
                {"$set": {
                    "prompt_text": prompt_text,
                    "updated_at": datetime.utcnow()
                }},
                upsert=True
            )
            return JsonResponse({'success': True, 'message': f'{prompt_type.capitalize()} prompt updated successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


