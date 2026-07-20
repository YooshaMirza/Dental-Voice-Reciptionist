"""
Generic GHL lead webhook receiver.

Field mapping below is based on real payloads from the client's "ai voice
agent" GHL workflow (a Facebook Instant Form -> bot-survey flow with ~60
possible fields, most blank for any given lead since each lead only answers
whichever questions their path through the bot asked). Contact fields
(first_name/last_name/phone/email/contact_id/date_of_birth/postal_code) come
through clean and consistent.

The survey questions come in BOTH English and Spanish field names (the same
question asked twice, once per language variant of the bot flow) — which one
is non-empty depends on which language path that particular lead went through.
Real traffic has shown both happen regularly (e.g. a lead answering entirely
in the Spanish-labeled fields with the English ones all blank), so every
concept below checks both language's field name and translates common Spanish
answer values to English before they go into the spoken summary (the AI
persona speaks English).
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Request

from app.core.config import load_config
from app.db.mongo import ghl_leads_collection
from app.calls.outbound import initiate_twilio_call

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ghl", tags=["ghl"])

_PHONE_KEYS = ("phone", "Phone", "phone_number", "phoneNumber", "contact_phone")
_FIRST_NAME_KEYS = ("first_name", "firstName", "First Name")
_LAST_NAME_KEYS = ("last_name", "lastName", "Last Name")
_FULL_NAME_KEYS = ("full_name", "fullName", "name", "Full Name")
_DOB_KEYS = ("date_of_birth", "dob", "DOB")
_ZIP_KEYS = ("postal_code", "zip_code", "zip", "Zip Code")

# Common Spanish answer values seen in real payloads -> English. Extend this as
# more real traffic surfaces new values; anything not found here is passed
# through untranslated rather than dropped.
_SPANISH_VALUE_TRANSLATIONS = {
    "más de un año": "more than a year",
    "menos de un año": "less than a year",
    "todos": "all of them",
    "sí": "yes",
    "no": "no",
    "puente, corona": "a bridge and a crown",
    "puente": "a bridge",
    "corona": "a crown",
    "dentadura completa o parcial": "a full or partial denture",
}


def _translate_value(value: str) -> str:
    translated = _SPANISH_VALUE_TRANSLATIONS.get(value.strip().lower())
    return translated if translated else value


# Each concept lists every field-name variant seen in real traffic (English
# first, then Spanish) — first non-empty one wins. Ordered: the first one
# found drives the personalized opening line; the rest, if present, get
# folded in as supporting detail.
_SURVEY_FIELD_TEMPLATES = [
    (
        ("How Long Have You Been Missing Your Teeth?", "¿Cuánto tiempo llevas sin tus dientes?"),
        "they've been missing their teeth for {value}",
    ),
    (
        ("How Many Missing Or Broken Teeth Do You Have?", "¿Cuántos dientes faltantes o dañados tienes?"),
        "they have {value} missing or broken teeth",
    ),
    (
        ("What Best Describes Your Condition?", "¿Qué describe mejor tu condición?"),
        "they describe their condition as \"{value}\"",
    ),
    (("Current Issue With Teeth",), "their current issue is \"{value}\""),
    (
        (
            "Are You Currently Unable To Eat Certain Foods Or Have To Modify The Way You Chew?",
            "¿Actualmente no puedes comer ciertos alimentos o tienes que modificar la forma en que masticas?",
        ),
        "they've had to modify how they eat: \"{value}\"",
    ),
    (
        (
            "Are You Currently Experiencing A Lack Of Confidence In Social Situations or Find Yourself Hiding Your Smile?",
            "¿Actualmente experimentas falta de confianza en situaciones sociales o tiendes a ocultar tu sonrisa?",
        ),
        "they mentioned feeling self-conscious about their smile: \"{value}\"",
    ),
    (
        ("Do you currently have any of these dental solutions?", "¿Actualmente tienes alguna de estas soluciones dentales?"),
        "they currently have {value}",
    ),
    (
        ("Anything That You Would Like For Us to Know Regarding Your Smile?", "¿Hay algo que te gustaría que supiéramos respecto a tu sonrisa?"),
        "they shared: \"{value}\"",
    ),
]


def _first_present(payload: dict, keys):
    for key in keys:
        value = payload.get(key)
        if value:
            return value
    return None


def _build_lead_context_summary(payload: dict) -> str:
    """Natural-language summary of whichever dental-relevant survey questions
    this lead actually answered (in either language), so the outbound opening
    line can reference it (e.g. "I see you've been missing your teeth for
    more than a year...") instead of asking from scratch. Empty/unanswered
    fields are skipped."""
    facts = []
    for field_variants, template in _SURVEY_FIELD_TEMPLATES:
        value = _first_present(payload, field_variants)
        if value:
            facts.append(template.format(value=_translate_value(value)))

    if not facts:
        return ""

    return "Before the call: according to their intake form, " + "; and ".join(facts) + "."


@router.post("/webhook/lead/")
async def ghl_lead_webhook(request: Request):
    payload = await request.json()
    logger.info(f"GHL lead webhook received: {payload}")

    ghl_leads_collection.insert_one({"raw_payload": payload, "received_at": datetime.utcnow()})

    # Controlled by GHL_AUTO_CALL_ON_LEAD in config.properties — off by default while
    # the real payload shape is still being mapped out. Storage above always happens
    # regardless, so leads are never lost even with auto-calling disabled.
    auto_call_enabled = load_config().get("GHL_AUTO_CALL_ON_LEAD", "false").strip().lower() == "true"
    if not auto_call_enabled:
        logger.info("GHL lead webhook: GHL_AUTO_CALL_ON_LEAD is disabled — payload stored, no call triggered.")
        return {"status": "stored", "call_triggered": False, "reason": "auto_call_disabled"}

    phone = _first_present(payload, _PHONE_KEYS)
    first_name = _first_present(payload, _FIRST_NAME_KEYS)
    last_name = _first_present(payload, _LAST_NAME_KEYS)
    full_name = _first_present(payload, _FULL_NAME_KEYS)
    customer_name = full_name or " ".join(filter(None, [first_name, last_name])) or "Patient"
    dob = _first_present(payload, _DOB_KEYS)
    zip_code = _first_present(payload, _ZIP_KEYS)

    if not phone:
        logger.warning("GHL lead webhook: no recognizable phone field in payload — call not triggered. Raw payload stored for inspection.")
        return {"status": "stored", "call_triggered": False, "reason": "no_phone_found"}

    lead_context_summary = _build_lead_context_summary(payload)

    context = {
        "customerName": customer_name,
        "first_name": first_name,
        "last_name": last_name,
        "dob": dob,
        "zip_code": zip_code,
        "lead_context_summary": lead_context_summary,
        **payload,
    }

    result = initiate_twilio_call(phone, context)
    return {"status": "stored", "call_triggered": result.get("status") == "success", "call_result": result}
