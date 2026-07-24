"""
Doctor dashboard UI, call details API, booking update, knowledge base API,
system prompts API, and the session-based dashboard login/logout. Ported
from voice_agent/views.py (DoctorDashboardUI, CallDetailsAPI, UpdateBookingAPI,
CustomLoginUI, CustomLogoutUI, KnowledgeBaseAPI, KnowledgeBaseDetailAPI,
SystemPromptsAPI, WebDialerUI).
"""
import json
import logging
import datetime

import pytz
from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import load_config
from app.db.mongo import (
    calls_collection,
    firoz_lalani_collection,
    knowledge_base_collection,
    prompts_collection,
    web_users_collection,
)
from app.db.calls import call_sid_lookup_filter
from app.db.settings import get_auto_call_enabled, set_auto_call_enabled
from app.ghl.calendar import create_appointment, sync_appointment_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice-agent", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


def _djdate(value, fmt: str) -> str:
    """Minimal Django-date-format-string -> Python strftime translator, just
    covering the format codes this template actually uses ("d M Y, h:i a")."""
    if not value:
        return ""
    code_map = {
        "d": "%d", "m": "%m", "Y": "%Y", "y": "%y",
        "M": "%b", "N": "%b", "F": "%B",
        "H": "%H", "i": "%M", "s": "%S",
    }
    out = []
    i = 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == "h":  # 12-hour, no leading zero
            out.append(str(int(value.strftime("%I"))))
        elif ch == "a":  # am/pm
            out.append(value.strftime("%p").lower())
        elif ch in code_map:
            out.append(value.strftime(code_map[ch]))
        else:
            out.append(ch)
        i += 1
    return "".join(out)


templates.env.filters["djdate"] = _djdate


def _is_logged_in(request: Request) -> bool:
    return bool(request.session.get("web_user"))


@router.get("/dashboard/", response_class=HTMLResponse)
async def dashboard(request: Request, date: str | None = None):
    if not _is_logged_in(request):
        return RedirectResponse(url="/api/voice-agent/login/")

    central_tz = pytz.timezone("US/Central")

    selected_date = None
    if date:
        try:
            selected_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            pass

    if not selected_date:
        latest_call = calls_collection.find_one(sort=[("call_created_at", -1)])
        if latest_call and latest_call.get("call_created_at"):
            call_created_at = latest_call["call_created_at"]
            if call_created_at.tzinfo is None:
                call_created_at = pytz.UTC.localize(call_created_at)
            selected_date = call_created_at.astimezone(central_tz).date()
        else:
            selected_date = datetime.datetime.now(central_tz).date()

    start_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.min))
    end_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.max))
    start_utc = start_local.astimezone(pytz.UTC)
    end_utc = end_local.astimezone(pytz.UTC)

    date_filter = {"call_created_at": {"$gte": start_utc.replace(tzinfo=None), "$lte": end_utc.replace(tzinfo=None)}}
    patient_date_filter = {"created_at": {"$gte": start_utc.replace(tzinfo=None), "$lte": end_utc.replace(tzinfo=None)}}

    total_calls = calls_collection.count_documents(date_filter)
    total_new_patients = firoz_lalani_collection.count_documents({**patient_date_filter, "patient_status": "new_patient"})

    positive_sentiment = calls_collection.count_documents({**date_filter, "sentiment": "positive"})
    neutral_sentiment = calls_collection.count_documents({**date_filter, "sentiment": "neutral"})
    negative_sentiment = calls_collection.count_documents({**date_filter, "sentiment": "negative"})

    call_logs = list(calls_collection.find(date_filter).sort("call_created_at", -1).limit(100))
    patients = list(firoz_lalani_collection.find(patient_date_filter).sort("created_at", -1).limit(100))
    appointment_list = list(
        firoz_lalani_collection.find({
            **patient_date_filter,
            "selected_slot": {"$nin": [None, ""]},
        }).sort("created_at", -1).limit(100)
    )
    total_appointments = len(appointment_list)

    prev_date_str = (selected_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    next_date_str = (selected_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    selected_date_str = selected_date.strftime("%Y-%m-%d")
    selected_date_display = f"{selected_date.day} {selected_date.strftime('%B %Y')}"

    cfg = load_config()
    context = {
        "request": request,
        "total_calls": total_calls,
        "total_appointments": total_appointments,
        "total_new_patients": total_new_patients,
        "sentiment": {"positive": positive_sentiment, "neutral": neutral_sentiment, "negative": negative_sentiment},
        "call_logs": call_logs,
        "patients": patients,
        "appointments": appointment_list,
        "twilio_configured": bool(cfg.get("TWILIO_ACCOUNT_SID") and cfg.get("TWILIO_API_KEY")),
        "prev_date_str": prev_date_str,
        "next_date_str": next_date_str,
        "selected_date_str": selected_date_str,
        "selected_date_display": selected_date_display,
    }
    return templates.TemplateResponse("dashboard.html", context)


@router.get("/login/", response_class=HTMLResponse)
async def login_page(request: Request):
    if _is_logged_in(request):
        return RedirectResponse(url="/api/voice-agent/dashboard/")
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login/", response_class=HTMLResponse)
async def login_submit(request: Request):
    form = await request.form()
    username = form.get("username")
    password = form.get("password")

    user = web_users_collection.find_one({"username": username, "password": password})
    if user:
        request.session["web_user"] = username
        return RedirectResponse(url="/api/voice-agent/dashboard/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password."})


@router.get("/logout/")
async def logout(request: Request):
    request.session.pop("web_user", None)
    return RedirectResponse(url="/api/voice-agent/login/")


@router.get("/test-dialer/", response_class=HTMLResponse)
async def web_dialer_ui(request: Request):
    if not _is_logged_in(request):
        return RedirectResponse(url="/api/voice-agent/login/")
    return templates.TemplateResponse("dialer.html", {"request": request})


@router.get("/api/calls/{call_sid}/")
async def call_details(call_sid: str):
    call = calls_collection.find_one({"call_sid": call_sid})
    if not call:
        return JSONResponse({"success": False, "error": "Call details not found"}, status_code=404)

    transcript_data = call.get("transcript") or {}
    analysis_profile = None
    phone_number = call.get("phone_number") or call.get("from_number")
    if phone_number:
        digits = "".join(filter(str.isdigit, str(phone_number)))
        if len(digits) >= 10:
            analysis_profile = firoz_lalani_collection.find_one({"phone": digits[-10:]})

    local_recording_url = ""
    if "recording_file_data" in call:
        local_recording_url = f"/api/voice-agent/api/calls/{call_sid}/recording/"

    recording_url = local_recording_url or call.get("call_recording_url") or ""

    def _iso(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    data = {
        "call_sid": call.get("call_sid"),
        "direction": call.get("direction"),
        "phone_number": phone_number or "",
        "customer_name": call.get("customer_name") or "",
        "call_date": _iso(call.get("call_date")) or _iso(call.get("call_created_at")),
        "call_duration": call.get("call_duration") or 0,
        "call_status": call.get("call_status") or "completed",
        "call_type": call.get("call_type") or "unknown",
        "call_notes": call.get("call_notes") or "",
        "call_created_at": _iso(call.get("call_created_at")),
        "call_end_at": _iso(call.get("call_end_at")),
        "sentiment": call.get("sentiment") or "neutral",
        "ai_analysis_status": call.get("ai_analysis_status") or "",
        "conversation_summary": call.get("conversation_summary") or "",
        "call_feedback": call.get("call_feedback") or "",
        "call_rating": call.get("call_rating"),
        "transcript": transcript_data.get("text", ""),
        "turns": transcript_data.get("turns", []),
        "call_recording_url": recording_url,
        "recording_status": "available" if recording_url else "pending",
        "analysis_profile": {
            "first_name": analysis_profile.get("first_name") if analysis_profile else None,
            "last_name": analysis_profile.get("last_name") if analysis_profile else None,
            "dob": analysis_profile.get("dob") if analysis_profile else None,
            "zip_code": analysis_profile.get("zip_code") if analysis_profile else None,
            "support_person": analysis_profile.get("support_person") if analysis_profile else None,
            "appointment_type": analysis_profile.get("appointment_type") if analysis_profile else None,
            "preferred_day": analysis_profile.get("preferred_day") if analysis_profile else None,
            "time_preference": analysis_profile.get("time_preference") if analysis_profile else None,
            "selected_slot": analysis_profile.get("selected_slot") if analysis_profile else None,
            "call_outcome": analysis_profile.get("call_outcome") if analysis_profile else None,
            "patient_status": analysis_profile.get("patient_status") if analysis_profile else None,
            "message_notes": analysis_profile.get("message_notes") if analysis_profile else None,
            "last_call_sentiment": analysis_profile.get("last_call_sentiment") if analysis_profile else None,
        },
    }
    return {"success": True, "call": data}


_UNREAL_APPOINTMENT_ID_PREFIXES = ("ghl_apt_", "apt_mock_", "apt_live_", "pending_")


def _is_real_ghl_appointment_id(appointment_id) -> bool:
    return bool(appointment_id) and not any(str(appointment_id).startswith(p) for p in _UNREAL_APPOINTMENT_ID_PREFIXES)


@router.post("/api/booking/update/")
async def update_booking(request: Request):
    data = await request.json()
    patient_id = data.get("patient_id")
    status_val = data.get("status")

    if not patient_id or status_val not in ["confirmed", "declined"]:
        return JSONResponse({"success": False, "error": "Invalid parameters"}, status_code=400)

    patient = firoz_lalani_collection.find_one({"_id": ObjectId(patient_id)})
    if not patient:
        return JSONResponse({"success": False, "error": "Patient not found"}, status_code=404)

    ghl_api_key = load_config().get("GHL_API_KEY", "")
    ghl_appointment_id = patient.get("ghl_appointment_id")
    update_fields = {"booking_status": status_val}

    if status_val == "confirmed" and not _is_real_ghl_appointment_id(ghl_appointment_id):
        # Booking was deferred during the call (GHL_DEFER_BOOKING_TO_APPROVAL) — this
        # is the moment it actually gets written to the real GHL calendar, using
        # whatever calendar_id/contact_id/slot the call captured.
        calendar_id = patient.get("ghl_calendar_id")
        contact_id = patient.get("ghl_contact_id")
        start_time = patient.get("selected_slot_iso")
        appt_type = patient.get("appointment_type") or "NP Cleaning"

        if ghl_api_key and calendar_id and contact_id and start_time:
            from app.ghl.calendar import create_appointment

            result = await run_in_threadpool(create_appointment, calendar_id, contact_id, start_time, appt_type, ghl_api_key)
            if result.get("status") == "success" and _is_real_ghl_appointment_id(result.get("appointment_id")):
                update_fields["ghl_appointment_id"] = result["appointment_id"]
                logger.info(f"Created real GHL appointment {result['appointment_id']} for patient {patient_id} on approval")
            else:
                logger.warning(f"GHL appointment creation on approval did not return a real ID for patient {patient_id}: {result}")
        else:
            logger.warning(
                f"Cannot create real GHL appointment for patient {patient_id} on approval — "
                f"missing GHL_API_KEY, calendar_id, contact_id, or selected_slot_iso."
            )
    elif _is_real_ghl_appointment_id(ghl_appointment_id) and ghl_api_key:
        # Already a real appointment (non-deferred flow, or previously approved) — just sync status.
        sync_appointment_status(ghl_appointment_id, status_val, ghl_api_key)

    firoz_lalani_collection.update_one({"_id": ObjectId(patient_id)}, {"$set": update_fields})
    return {"success": True, "booking_status": status_val}


@router.get("/api/settings/auto-call/")
async def get_auto_call_setting():
    return {"success": True, "enabled": get_auto_call_enabled()}


@router.post("/api/settings/auto-call/")
async def update_auto_call_setting(request: Request):
    data = await request.json()
    enabled = bool(data.get("enabled"))
    set_auto_call_enabled(enabled)
    return {"success": True, "enabled": enabled}


@router.get("/api/kb/")
async def kb_list():
    entries = list(knowledge_base_collection.find({}))
    for entry in entries:
        entry["_id"] = str(entry["_id"])
    return {"success": True, "data": entries}


@router.post("/api/kb/")
async def kb_create_or_update(request: Request):
    data = await request.json()
    kb_id = data.get("id") or data.get("_id")
    category = data.get("category", "general")
    question = data.get("question", "")
    answer = data.get("answer", "")
    keywords_raw = data.get("keywords", "")

    if isinstance(keywords_raw, str):
        keywords = [k.strip().lower() for k in keywords_raw.split(",") if k.strip()]
    elif isinstance(keywords_raw, list):
        keywords = [str(k).strip().lower() for k in keywords_raw if str(k).strip()]
    else:
        keywords = []

    doc = {"category": category, "question": question, "answer": answer, "keywords": keywords}
    if category == "pricing":
        doc["procedure_name"] = data.get("procedure_name", "")
        doc["starting_price"] = data.get("starting_price", "")
        doc["notes"] = data.get("notes", "")

    if kb_id:
        knowledge_base_collection.update_one({"_id": ObjectId(kb_id)}, {"$set": doc})
        doc["_id"] = str(kb_id)
        message = "Knowledge Base rule updated successfully."
    else:
        result = knowledge_base_collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        message = "Knowledge Base rule added successfully."

    return {"success": True, "message": message, "data": doc}


@router.delete("/api/kb/{kb_id}/")
async def kb_delete(kb_id: str):
    result = knowledge_base_collection.delete_one({"_id": ObjectId(kb_id)})
    if result.deleted_count > 0:
        return {"success": True, "message": "Rule deleted successfully."}
    return JSONResponse({"success": False, "error": "Rule not found."}, status_code=404)


@router.get("/api/prompts/")
async def prompts_get():
    from app.voice.call_prompts import INBOUND_SYSTEM_PROMPT, OUTBOUND_SYSTEM_PROMPT

    inbound = prompts_collection.find_one({"prompt_type": "inbound"})
    if not inbound:
        inbound = {"prompt_type": "inbound", "title": "Inbound Assistant (Alice)", "prompt_text": INBOUND_SYSTEM_PROMPT}
        prompts_collection.insert_one(inbound.copy())

    outbound = prompts_collection.find_one({"prompt_type": "outbound"})
    if not outbound:
        outbound = {"prompt_type": "outbound", "title": "Outbound Patient Advocate (Dentina)", "prompt_text": OUTBOUND_SYSTEM_PROMPT}
        prompts_collection.insert_one(outbound.copy())

    return {
        "success": True,
        "prompts": {"inbound": inbound.get("prompt_text", ""), "outbound": outbound.get("prompt_text", "")},
    }


@router.post("/api/prompts/")
async def prompts_update(request: Request):
    data = await request.json()
    prompt_type = data.get("prompt_type")
    prompt_text = data.get("prompt_text")

    if prompt_type not in ["inbound", "outbound"]:
        return JSONResponse({"success": False, "error": "Invalid prompt type."}, status_code=400)

    prompts_collection.update_one(
        {"prompt_type": prompt_type},
        {"$set": {"prompt_text": prompt_text, "updated_at": datetime.datetime.utcnow()}},
        upsert=True,
    )
    return {"success": True, "message": f"{prompt_type.capitalize()} prompt updated successfully."}
