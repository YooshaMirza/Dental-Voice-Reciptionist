"""
Vertex AI / Google AI Studio WebSocket Client for Live Audio Streaming
Handles OAuth2 authentication and WebSocket connection to Gemini Live API.

Ported from voice_agent/vertex_ai_client.py unchanged, only swapping the
Django settings/config import for the FastAPI config loader.
"""

import json
import logging
import base64
import threading

from google.oauth2 import service_account
from google.auth.transport.requests import Request

from app.core.config import load_config

logger = logging.getLogger(__name__)

_credentials_cache = {"credentials": None, "lock": threading.Lock()}


def get_vertex_ai_credentials():
    with _credentials_cache["lock"]:
        cached_creds = _credentials_cache.get("credentials")
        if cached_creds and cached_creds.valid:
            logger.info(
                "Using cached Vertex AI token (expires at {})".format(
                    cached_creds.expiry.strftime("%H:%M:%S") if cached_creds.expiry else "unknown"
                )
            )
            return cached_creds.token

        if cached_creds:
            logger.info("Refreshing expired Vertex AI token...")
        else:
            logger.info("Creating new Vertex AI token (first call or server restart)...")

    try:
        cfg = load_config()
        creds_json = cfg.get("GOOGLE_CREDENTIALS_JSON", "")
        if not creds_json:
            raise ValueError("GOOGLE_CREDENTIALS_JSON not configured in config.properties")

        creds_dict = None
        try:
            creds_dict = json.loads(creds_json)
        except json.JSONDecodeError:
            pass

        if not creds_dict:
            try:
                decoded_json = base64.b64decode(creds_json).decode("utf-8")
                creds_dict = json.loads(decoded_json)
                logger.info("Successfully decoded GOOGLE_CREDENTIALS_JSON from Base64")
            except Exception:
                pass

        if not creds_dict:
            try:
                cleaned_json = creds_json.strip()
                if cleaned_json.startswith("'") and cleaned_json.endswith("'"):
                    cleaned_json = cleaned_json[1:-1]
                if cleaned_json.startswith('"') and cleaned_json.endswith('"'):
                    cleaned_json = cleaned_json[1:-1]
                cleaned_json = cleaned_json.replace("\\n", "\n").replace('\\"', '"')
                creds_dict = json.loads(cleaned_json)
                logger.info("Successfully parsed GOOGLE_CREDENTIALS_JSON after cleaning escape sequences")
            except json.JSONDecodeError:
                pass

        if not creds_dict:
            masked_preview = creds_json[:10] + "..." if creds_json else "Empty"
            raise ValueError(f"Failed to parse GOOGLE_CREDENTIALS_JSON. checked Raw, Base64, and Escaped formats. Preview: {masked_preview}")

        if "private_key" in creds_dict:
            private_key = creds_dict["private_key"]
            try:
                if "\\n" in private_key and "\n" not in private_key:
                    private_key = private_key.replace("\\n", "\n")
                creds_dict["private_key"] = private_key
            except Exception as e:
                logger.warning(f"Private key formatting issue: {e}")

        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)

        if not credentials.valid:
            credentials.refresh(Request())

        with _credentials_cache["lock"]:
            _credentials_cache["credentials"] = credentials
            logger.info(
                "Token cached successfully (expires at {})".format(
                    credentials.expiry.strftime("%H:%M:%S") if credentials.expiry else "unknown"
                )
            )

        return credentials.token

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse GOOGLE_CREDENTIALS_JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to get Vertex AI credentials: {e}")
        raise


def build_websocket_uri():
    cfg = load_config()
    provider = cfg.get("GEMINI_PROVIDER", "vertex")

    if provider == "ai_studio":
        api_key = cfg.get("GEMINI_API_KEY", "")
        if not api_key:
            logger.error("GEMINI_API_KEY is missing but GEMINI_PROVIDER is 'ai_studio'!")
            raise ValueError("GEMINI_API_KEY not configured")

        model_id = cfg.get("GEMINI_MODEL_ID", "gemini-1.5-flash")
        model_path = model_id if model_id.startswith("models/") else f"models/{model_id}"

        uri = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={api_key}"
        logger.info(f"Google AI Studio Live WebSocket URI: wss://generativelanguage.googleapis.com/... (Model path: {model_path})")
        return uri, model_path
    else:
        project_id = cfg.get("VERTEX_AI_PROJECT_ID", "")
        location = cfg.get("VERTEX_AI_LOCATION", "us-central1")
        model_id = cfg.get("GEMINI_MODEL_ID") or cfg.get("VERTEX_AI_MODEL_ID", "")

        logger.info(f"Checking Vertex AI Config - Project: '{project_id}', Location: '{location}', Model: '{model_id}'")

        if not project_id:
            logger.error("VERTEX_AI_PROJECT_ID is missing or empty! Please configure it in config.properties or Environment Variables.")
            raise ValueError("VERTEX_AI_PROJECT_ID not configured")

        host = f"{location}-aiplatform.googleapis.com"
        model_path = f"projects/{project_id}/locations/{location}/publishers/google/models/{model_id}"
        uri = f"wss://{host}/ws/google.cloud.aiplatform.v1beta1.LlmBidiService/BidiGenerateContent?alt=json"

        logger.info(f"Vertex AI WebSocket URI: {uri}")
        logger.info(f"Model path: {model_path}")
        return uri, model_path


def get_websocket_headers():
    provider = load_config().get("GEMINI_PROVIDER", "vertex")
    if provider == "ai_studio":
        return {}

    token = get_vertex_ai_credentials()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def build_setup_message(model_path: str, system_instruction: str, transfer_allowed: bool = False):
    master_protocol = """
### MANDATORY DENTAL ASSISTANT RULES
- **IDENTITY**: You are Alice (for inbound calls) or Dentina (for outbound calls) at Dental Care and Implants of Houston.
- **TONE**: Warm, helpful, professional, with Midwestern friendliness ("competent neighbor" vibe).
- **ZERO HALLUCINATION**: Do not make up any services, doctor names, or prices not specified in your instructions.
- **STRICT PROTOCOL FLOW**: Always confirm user details (spelling names letter-by-letter, phone numbers digit-by-digit) and follow the specific script pathways.
"""

    tools = []

    tools.append({
        "name": "query_knowledge_base",
        "description": "Queries the practice knowledge base for general questions about the dental clinic (address, location, hours, parking, accepted payment methods, dentist info, or what services are offered). Do NOT use this tool for pricing or cost questions.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"query": {"type": "STRING", "description": "The user's query or topic to search for in the knowledge base."}},
            "required": ["query"],
        },
    })

    tools.append({
        "name": "check_ghl_availability",
        "description": "Checks available slots/free calendar openings in GoHighLevel calendar.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "calendar_id": {"type": "STRING", "description": "The GHL calendar ID to check."},
                "preferred_day": {"type": "STRING", "description": "Preferred day or date (e.g., 'tomorrow', 'Tuesday', 'Friday')."},
                "time_preference": {"type": "STRING", "description": "Morning or afternoon preference."},
            },
            "required": ["calendar_id"],
        },
    })

    tools.append({
        "name": "create_ghl_appointment",
        "description": "Creates an appointment in the GoHighLevel calendar.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "calendar_id": {"type": "STRING", "description": "The calendar ID."},
                "contact_id": {"type": "STRING", "description": "The GHL contact ID of the patient."},
                "start_time": {"type": "STRING", "description": "The selected slot start time (ISO format)."},
                "appointment_type": {"type": "STRING", "description": "Type of appointment (e.g., 'NP Cleaning', 'EP Cleaning', 'NP Implant Consult', 'EP Treatment')."},
            },
            "required": ["calendar_id", "contact_id", "start_time", "appointment_type"],
        },
    })

    tools.append({
        "name": "send_to_ghl",
        "description": "Sends patient registration and call outcome data to GoHighLevel.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "first_name": {"type": "STRING", "description": "The patient's first name."},
                "last_name": {"type": "STRING", "description": "The patient's last name."},
                "phone": {"type": "STRING", "description": "The patient's phone number."},
                "email": {"type": "STRING", "description": "The patient's email address."},
                "appointment_type": {"type": "STRING", "description": "Type of appointment requested."},
                "call_outcome": {"type": "STRING", "description": "Outcome of the call (e.g. 'Booked', 'Message', 'Transfer', 'Duplicate')."},
                "patient_status": {"type": "STRING", "description": "new_patient or existing_patient."},
                "selected_slot": {"type": "STRING", "description": "The chosen slot time if booked."},
                "dob": {"type": "STRING", "description": "The patient's date of birth."},
                "zip_code": {"type": "STRING", "description": "The patient's residential ZIP code."},
                "support_person": {"type": "STRING", "description": "The support person or emergency contact name if provided."},
                "preferred_day": {"type": "STRING", "description": "The patient's preferred day of the week for appointment."},
                "time_preference": {"type": "STRING", "description": "The patient's preferred time of day (e.g. morning, afternoon)."},
                "message_notes": {"type": "STRING", "description": "Notes or messages to be saved alongside the registration."},
                "ghl_appointment_id": {"type": "STRING", "description": "The GHL appointment ID returned from create_ghl_appointment tool."},
            },
            "required": ["first_name", "last_name", "phone"],
        },
    })

    tools.append({
        "name": "save_job_application",
        "description": "Saves patient registration details (first name, last name, phone, email, dob, zip_code, etc.) to the local database.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "first_name": {"type": "STRING", "description": "The patient's first name."},
                "last_name": {"type": "STRING", "description": "The patient's last name."},
                "phone": {"type": "STRING", "description": "The patient's phone number."},
                "email": {"type": "STRING", "description": "The patient's email address."},
                "appointment_type": {"type": "STRING", "description": "Type of appointment requested."},
                "call_outcome": {"type": "STRING", "description": "Outcome of the call (e.g. 'Booked', 'Message', 'Transfer', 'Duplicate')."},
                "patient_status": {"type": "STRING", "description": "new_patient or existing_patient."},
                "selected_slot": {"type": "STRING", "description": "The chosen slot time if booked."},
                "dob": {"type": "STRING", "description": "The patient's date of birth."},
                "zip_code": {"type": "STRING", "description": "The patient's residential ZIP code."},
                "support_person": {"type": "STRING", "description": "The support person or emergency contact name if provided."},
                "preferred_day": {"type": "STRING", "description": "The patient's preferred day of the week for appointment."},
                "time_preference": {"type": "STRING", "description": "The patient's preferred time of day (e.g. morning, afternoon)."},
                "message_notes": {"type": "STRING", "description": "Notes or messages to be saved alongside the registration."},
                "ghl_appointment_id": {"type": "STRING", "description": "The GHL appointment ID returned from create_ghl_appointment tool."},
            },
            "required": ["first_name", "last_name", "phone"],
        },
    })

    tools.append({
        "name": "duplicate_booking_check",
        "description": "Checks if the patient already has an appointment within the next 24 hours.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"contact_id": {"type": "STRING", "description": "The GHL contact ID of the patient."}},
            "required": ["contact_id"],
        },
    })

    final_system_instruction = master_protocol + system_instruction

    provider = load_config().get("GEMINI_PROVIDER", "vertex")

    generation_config = {
        "response_modalities": ["AUDIO"],
        "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": "Zephyr"}}},
    }

    if provider != "ai_studio":
        generation_config["input_audio_transcription"] = {}
        generation_config["output_audio_transcription"] = {}

    setup = {
        "setup": {
            "model": model_path,
            "generation_config": generation_config,
            "system_instruction": {"parts": [{"text": final_system_instruction}]},
        }
    }

    if tools:
        setup["setup"]["tools"] = [{"functionDeclarations": tools}]

    logger.info(f"Gemini Setup: {len(tools)} tools active for dental flow.")
    return setup


def build_audio_message(audio_data: bytes, mime_type: str = "audio/pcm;rate=16000"):
    audio_b64 = base64.b64encode(audio_data).decode("utf-8")
    return {"realtimeInput": {"audio": {"data": audio_b64, "mimeType": mime_type}}}


def build_text_message(text: str):
    return {"clientContent": {"turns": [{"role": "user", "parts": [{"text": text}]}], "turnComplete": True}}


def build_tool_response(call_id: str, function_name: str, response_data: dict):
    return {
        "toolResponse": {
            "functionResponses": [{"id": call_id, "name": function_name, "response": {"result": response_data}}]
        }
    }


def build_keepalive_message():
    return {"clientContent": {"turns": [{"role": "user", "parts": [{"text": ""}]}], "turnComplete": False}}


def parse_audio_response(response_data: dict):
    audio_bytes = None
    is_turn_complete = False
    is_interrupted = False
    text_content = None
    user_text = None
    tool_calls = None

    server_content = response_data.get("serverContent", {})

    if server_content.get("interrupted"):
        is_interrupted = True

    if server_content.get("turnComplete"):
        is_turn_complete = True

    tool_call_data = response_data.get("toolCall") or server_content.get("toolCall", {})
    if tool_call_data.get("functionCalls"):
        tool_calls = tool_call_data["functionCalls"]

    input_transcription = server_content.get("inputTranscription", {})
    if input_transcription.get("text"):
        user_text = input_transcription["text"]

    output_transcription = server_content.get("outputTranscription", {})
    if output_transcription.get("text"):
        text_content = output_transcription["text"]

    model_turn = server_content.get("modelTurn", {})
    parts = model_turn.get("parts", [])

    for part in parts:
        inline_data = part.get("inlineData", {})
        if inline_data.get("data"):
            audio_bytes = base64.b64decode(inline_data["data"])

        if part.get("text") and not text_content:
            text_content = part["text"]

    return audio_bytes, is_turn_complete, is_interrupted, text_content, user_text, tool_calls


def warm_up_token_cache():
    provider = load_config().get("GEMINI_PROVIDER", "vertex")
    if provider == "ai_studio":
        logger.info("GEMINI_PROVIDER is 'ai_studio' - token cache warm-up skipped.")
        return

    try:
        logger.info("Warming up token cache...")
        token = get_vertex_ai_credentials()
        if token:
            logger.info("Token cache warm-up successful - first call will be instant!")
        else:
            logger.warning("Token cache warm-up returned empty token")
    except Exception as e:
        logger.error(f"Token cache warm-up failed: {e}")
        logger.info("Token will be created on first call instead (6-7s delay)")
        raise


def clear_token_cache():
    with _credentials_cache["lock"]:
        _credentials_cache["credentials"] = None
        logger.info("Token cache cleared - next call will create fresh token")
