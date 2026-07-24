"""
Generic GHL lead webhook receiver + pending-leads review/trigger API.

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

Whether a lead auto-triggers a call or waits for manual review is controlled
by a DB-backed setting (see app/db/settings.py) editable from the dashboard —
not a static env var, since flipping that requires a file edit + restart,
which isn't realistic for office staff day-to-day.
"""
import logging
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from app.db.mongo import ghl_leads_collection
from app.db.settings import get_auto_call_enabled
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


def _extract_lead_fields(payload: dict) -> dict:
    """Everything derived from a raw GHL payload that either drives the call
    context or is shown to staff reviewing the lead before triggering it."""
    phone = _first_present(payload, _PHONE_KEYS)
    first_name = _first_present(payload, _FIRST_NAME_KEYS)
    last_name = _first_present(payload, _LAST_NAME_KEYS)
    full_name = _first_present(payload, _FULL_NAME_KEYS)
    customer_name = full_name or " ".join(filter(None, [first_name, last_name])) or "Patient"

    answered_questions = []
    for field_variants, _template in _SURVEY_FIELD_TEMPLATES:
        value = _first_present(payload, field_variants)
        if value:
            answered_questions.append({"question": field_variants[0], "answer": _translate_value(value)})

    return {
        "phone": phone,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "customer_name": customer_name,
        "email": payload.get("email"),
        "dob": _first_present(payload, _DOB_KEYS),
        "zip_code": _first_present(payload, _ZIP_KEYS),
        "contact_id": payload.get("contact_id"),
        "location_name": (payload.get("location") or {}).get("name") if isinstance(payload.get("location"), dict) else None,
        "answered_questions": answered_questions,
        "lead_context_summary": _build_lead_context_summary(payload),
    }


def _call_context_from_fields(fields: dict, payload: dict) -> dict:
    return {
        "customerName": fields["customer_name"],
        "first_name": fields["first_name"],
        "last_name": fields["last_name"],
        "dob": fields["dob"],
        "zip_code": fields["zip_code"],
        "lead_context_summary": fields["lead_context_summary"],
        **payload,
    }


_TEST_LEAD_SAMPLE_ANSWERS = {
    "How Long Have You Been Missing Your Teeth?": "more than a year",
    "How Many Missing Or Broken Teeth Do You Have?": "2 to 4",
    "What Best Describes Your Condition?": "missing back teeth",
    "Anything That You Would Like For Us to Know Regarding Your Smile?": "I'm nervous about the cost",
}


@router.post("/leads/simulate-test/")
async def simulate_test_lead(request: Request):
    """Dashboard-only test helper. Injects a fake lead through the exact same
    extraction/storage path a real GHL webhook uses, so staff can verify the
    Pending Leads flow (list, detail modal, Call Now) without waiting for a
    real lead or needing GHL's workflow pointed at whatever the current ngrok
    URL happens to be. Always lands as "pending" regardless of the auto-call
    setting — this is for reviewing the pipeline, not for testing auto-dial."""
    data = await request.json()
    phone = (data.get("phone") or "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number required for the test lead")

    name = (data.get("name") or "Test Patient").strip()
    name_parts = name.split(" ", 1)
    payload = {
        "first_name": name_parts[0],
        "last_name": name_parts[1] if len(name_parts) > 1 else "Lead",
        "phone": phone,
        "email": "test-lead@example.com",
        "contact_id": f"test_{ObjectId()}",
        **_TEST_LEAD_SAMPLE_ANSWERS,
    }

    fields = _extract_lead_fields(payload)
    lead_doc = {
        "raw_payload": payload,
        "received_at": datetime.utcnow(),
        "status": "pending",
        "is_test": True,
        **{k: v for k, v in fields.items() if k not in ("answered_questions", "customer_name")},
        "customer_name": f"[TEST] {fields['customer_name']}",
        "answered_questions": fields["answered_questions"],
    }
    inserted = ghl_leads_collection.insert_one(lead_doc)
    logger.info(f"Simulated test lead {inserted.inserted_id} inserted for dashboard testing.")
    return {"success": True, "lead_id": str(inserted.inserted_id)}


@router.post("/webhook/lead/")
async def ghl_lead_webhook(request: Request):
    payload = await request.json()
    logger.info(f"GHL lead webhook received: {payload}")

    fields = _extract_lead_fields(payload)
    auto_call_enabled = get_auto_call_enabled()

    lead_doc = {
        "raw_payload": payload,
        "received_at": datetime.utcnow(),
        "status": "pending",
        **{k: v for k, v in fields.items() if k != "answered_questions"},
        "answered_questions": fields["answered_questions"],
    }
    inserted = ghl_leads_collection.insert_one(lead_doc)

    if not auto_call_enabled:
        logger.info(f"GHL lead {inserted.inserted_id} stored — auto-call is off, awaiting manual trigger from the dashboard.")
        return {"status": "stored", "call_triggered": False, "reason": "auto_call_disabled", "lead_id": str(inserted.inserted_id)}

    if not fields["phone"]:
        logger.warning(f"GHL lead {inserted.inserted_id}: no recognizable phone field — call not triggered.")
        ghl_leads_collection.update_one({"_id": inserted.inserted_id}, {"$set": {"status": "no_phone"}})
        return {"status": "stored", "call_triggered": False, "reason": "no_phone_found", "lead_id": str(inserted.inserted_id)}

    context = _call_context_from_fields(fields, payload)
    result = initiate_twilio_call(fields["phone"], context)
    ghl_leads_collection.update_one(
        {"_id": inserted.inserted_id},
        {"$set": {"status": "called" if result.get("status") == "success" else "call_failed", "call_result": result}},
    )
    return {"status": "stored", "call_triggered": result.get("status") == "success", "call_result": result, "lead_id": str(inserted.inserted_id)}


@router.get("/leads/pending/")
async def list_pending_leads():
    """Leads awaiting manual review/trigger — shown on the dashboard's Pending Leads tab."""
    leads = list(ghl_leads_collection.find({"status": "pending"}).sort("received_at", -1))
    return {
        "success": True,
        "leads": [
            {
                "id": str(lead["_id"]),
                "customer_name": lead.get("customer_name"),
                "phone": lead.get("phone"),
                "email": lead.get("email"),
                "received_at": lead["received_at"].isoformat() if lead.get("received_at") else None,
                "lead_context_summary": lead.get("lead_context_summary") or "",
                "answered_count": len(lead.get("answered_questions") or []),
                "is_test": bool(lead.get("is_test")),
            }
            for lead in leads
        ],
    }


@router.get("/leads/{lead_id}/")
async def get_lead_detail(lead_id: str):
    """Full detail for the review modal — every field that will be handed to the AI as context."""
    try:
        lead = ghl_leads_collection.find_one({"_id": ObjectId(lead_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead id")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {
        "success": True,
        "lead": {
            "id": str(lead["_id"]),
            "status": lead.get("status"),
            "customer_name": lead.get("customer_name"),
            "first_name": lead.get("first_name"),
            "last_name": lead.get("last_name"),
            "phone": lead.get("phone"),
            "email": lead.get("email"),
            "dob": lead.get("dob"),
            "zip_code": lead.get("zip_code"),
            "contact_id": lead.get("contact_id"),
            "location_name": lead.get("location_name"),
            "received_at": lead["received_at"].isoformat() if lead.get("received_at") else None,
            "lead_context_summary": lead.get("lead_context_summary") or "",
            "answered_questions": lead.get("answered_questions") or [],
        },
    }


@router.post("/leads/{lead_id}/call/")
async def trigger_lead_call(lead_id: str):
    """Manually trigger the outbound call for one specific pending lead."""
    try:
        lead = ghl_leads_collection.find_one({"_id": ObjectId(lead_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead id")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.get("phone"):
        raise HTTPException(status_code=400, detail="This lead has no phone number on file")

    fields = {
        "customer_name": lead.get("customer_name"),
        "first_name": lead.get("first_name"),
        "last_name": lead.get("last_name"),
        "dob": lead.get("dob"),
        "zip_code": lead.get("zip_code"),
        "lead_context_summary": lead.get("lead_context_summary") or "",
    }
    context = _call_context_from_fields(fields, lead.get("raw_payload") or {})
    result = initiate_twilio_call(lead["phone"], context)

    ghl_leads_collection.update_one(
        {"_id": lead["_id"]},
        {"$set": {"status": "called" if result.get("status") == "success" else "call_failed", "call_result": result}},
    )
    return {"success": result.get("status") == "success", "call_result": result}
