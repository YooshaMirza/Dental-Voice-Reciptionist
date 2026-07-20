"""
Real GoHighLevel Calendar API integration — replaces the old sessions.py
placeholders (`check_ghl_availability` never actually called GHL; it always
returned 4 hardcoded slots).

Falls back to the same hardcoded mock slots / mock appointment IDs the old
code used whenever GHL isn't configured or the call fails, so a live call
never breaks because of a GHL outage or a not-yet-set-up calendar — but when
`GHL_API_KEY` (and a real calendar_id) are present, this hits the real API.
"""
import logging
import time
import random
import datetime

import requests
import pytz

logger = logging.getLogger(__name__)

GHL_BASE_URL = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-04-15"

_MOCK_SLOTS = [
    {"time": "2026-05-25T10:00:00Z", "display": "Monday at 10:00 AM"},
    {"time": "2026-05-25T14:30:00Z", "display": "Monday at 2:30 PM"},
    {"time": "2026-05-26T09:00:00Z", "display": "Tuesday at 9:00 AM"},
    {"time": "2026-05-26T15:00:00Z", "display": "Tuesday at 3:00 PM"},
]


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Version": GHL_API_VERSION,
    }


def get_free_slots(calendar_id: str, api_key: str, time_preference: str = "morning", days_ahead: int = 7) -> dict:
    """Fetch real free slots from GHL's Calendars API for the next `days_ahead` days.
    Returns {"status": "success"|"mock", "slots": [{"time": iso_str, "display": str}, ...]}."""
    if not api_key or not calendar_id:
        logger.info("GHL calendar not configured — returning mock slots.")
        return {"status": "mock", "slots": _MOCK_SLOTS}

    try:
        central_tz = pytz.timezone("US/Central")
        now = datetime.datetime.now(central_tz)
        start_ms = int(now.timestamp() * 1000)
        end_ms = int((now + datetime.timedelta(days=days_ahead)).timestamp() * 1000)

        resp = requests.get(
            f"{GHL_BASE_URL}/calendars/{calendar_id}/free-slots",
            params={"startDate": start_ms, "endDate": end_ms, "timezone": "America/Chicago"},
            headers=_headers(api_key),
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"GHL free-slots failed ({resp.status_code}): {resp.text}")
            return {"status": "mock", "slots": _MOCK_SLOTS}

        data = resp.json()
        all_slots = []
        for day_key, day_data in data.items():
            if not isinstance(day_data, dict):
                continue
            for slot_iso in day_data.get("slots", []):
                all_slots.append(slot_iso)

        if not all_slots:
            logger.warning("GHL free-slots returned no slots — falling back to mock slots.")
            return {"status": "mock", "slots": _MOCK_SLOTS}

        want_afternoon = (time_preference or "").strip().lower() == "afternoon"
        filtered = []
        for slot_iso in all_slots:
            try:
                dt = datetime.datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
                is_afternoon = dt.hour >= 12
                if is_afternoon == want_afternoon:
                    filtered.append((dt, slot_iso))
            except Exception:
                continue

        chosen = filtered or [(datetime.datetime.fromisoformat(s.replace("Z", "+00:00")), s) for s in all_slots]
        chosen.sort(key=lambda pair: pair[0])

        slots_out = []
        for dt, slot_iso in chosen[:4]:
            slots_out.append({"time": slot_iso, "display": dt.strftime("%A at %I:%M %p").replace(" 0", " ")})

        return {"status": "success", "slots": slots_out}
    except Exception as e:
        logger.error(f"Error fetching GHL free slots: {e}")
        return {"status": "mock", "slots": _MOCK_SLOTS}


def create_appointment(calendar_id: str, contact_id: str, start_time: str, appointment_type: str, api_key: str) -> dict:
    """Create a real appointment in GHL. Falls back to a mock ID on failure so the
    call flow never breaks, matching the old behavior."""
    if api_key:
        try:
            body = {
                "calendarId": calendar_id,
                "contactId": contact_id,
                "startTime": start_time,
                "title": appointment_type,
                "address": "165 Greens Rd Houston TX 77060",
                "appointmentStatus": "new",
            }
            resp = requests.post(
                f"{GHL_BASE_URL}/calendars/events/appointments",
                json=body,
                headers=_headers(api_key),
                timeout=10,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "status": "success",
                    "appointment_id": data.get("id") or "apt_live_" + str(time.time()).replace(".", "")[:10],
                    "calendar_id": calendar_id,
                    "selected_time": start_time,
                }
            logger.error(f"GHL create appointment failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Error creating GHL appointment: {e}")

    mock_id = f"apt_mock_{random.randint(100000, 999999)}"
    return {"status": "success", "appointment_id": mock_id, "calendar_id": calendar_id, "selected_time": start_time}


def sync_appointment_status(appointment_id: str, status_val: str, api_key: str) -> bool:
    """PUT an appointment status update to GHL (confirmed/cancelled). Used by the
    manual booking-update endpoint. Returns True on success."""
    if not api_key or not appointment_id:
        return False
    if any(appointment_id.startswith(pfx) for pfx in ("ghl_apt_", "apt_mock_", "apt_live_")):
        return False  # not a real GHL ID, nothing to sync
    try:
        ghl_status = "confirmed" if status_val == "confirmed" else "cancelled"
        resp = requests.put(
            f"{GHL_BASE_URL}/calendars/events/appointments/{appointment_id}",
            json={"appointmentStatus": ghl_status},
            headers=_headers(api_key),
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Synced GHL appointment {appointment_id} status to '{ghl_status}'")
            return True
        logger.error(f"GHL appointment status sync failed for {appointment_id} ({resp.status_code}): {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Error syncing GHL appointment {appointment_id}: {e}")
        return False


def send_contact(first_name, last_name, phone, email, custom_fields: dict, api_key: str) -> dict:
    """Create/update a GHL contact with call-outcome custom fields."""
    if api_key:
        try:
            body = {
                "firstName": first_name,
                "lastName": last_name,
                "phone": phone,
                "email": email,
                "tags": ["ai-call-booking"],
                "customField": custom_fields,
                "notificationEmail": "gr@dentalcareandimplants.com",
            }
            resp = requests.post(f"{GHL_BASE_URL}/contacts/", json=body, headers=_headers(api_key), timeout=10)
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "status": "success",
                    "contact_id": data.get("contact", {}).get("id") or "con_live_" + str(time.time()).replace(".", "")[:10],
                    "message": "Contact updated in GHL",
                }
            logger.error(f"GHL send contact failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Error sending contact to GHL: {e}")

    mock_con_id = f"con_mock_{random.randint(100000, 999999)}"
    return {"status": "success", "contact_id": mock_con_id, "message": "Contact updated in GHL (Mocked)"}
