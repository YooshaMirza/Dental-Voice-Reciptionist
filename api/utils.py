from api.models import Call, CustomUser
from api.db import db as mongo_db


def get_last_five_calls(voicelinkdid=None, user_mobile=None):
    """Get the last 5 completed calls for a user/candidate."""
    user = None
    if voicelinkdid:
        user = CustomUser.objects.filter(voicelink_did=str(voicelinkdid).strip()).first()
        if not user:
            return []

    normalized_mobile = "".join(ch for ch in str(user_mobile or "") if ch.isdigit())[-10:]
    if not normalized_mobile:
        return []

    # If no specific user, we can't filter by service_id (provider_id)
    # But in JobOnboardingAgent, we usually have a provider/admin user associated with the DID.
    
    call_query = {"phone_number": {"$regex": normalized_mobile + "$"}, "call_status": "completed"}
    
    if user:
        provider_id = getattr(user, "_id", None) or user.pk
        call_query["service_id"] = provider_id

    call_docs = list(
        mongo_db["api_calls"]
        .find(call_query)
        .sort([("call_date", -1), ("call_created_at", -1)])
        .limit(5)
    )

    calls_out = []
    for doc in call_docs:
        cid = doc.get("_id")
        
        calls_out.append(
            {
                "call_id": str(cid),
                "call_sid": doc.get("call_sid"),
                "call_type": doc.get("call_type"),
                "direction": doc.get("direction"),
                "call_status": doc.get("call_status"),
                "transcript": doc.get("transcript"),
                "call_date": doc.get("call_date").isoformat() if hasattr(doc.get("call_date"), "isoformat") else str(doc.get("call_date")),
                "call_duration": doc.get("call_duration"),
                "ai_analysis": doc.get("ai_analysis"),
                "phone_number": doc.get("phone_number"),
            }
        )
    return calls_out
