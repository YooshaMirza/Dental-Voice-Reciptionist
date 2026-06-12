"""
Create per-service Prompt rows when a provider signs up.

Uses built-in opening scripts from default_prompt_texts (same placeholders as
voice_agent.call_prompts.get_system_prompt).
"""
import logging
from typing import Any

from bson import ObjectId

from api.models import Prompt
from api.services.default_prompt_texts import DEFAULT_PROMPT_TEXTS

logger = logging.getLogger(__name__)

# DB keys match voice_agent.call_prompts (underscore → hyphen).
CANONICAL_PROMPTS = (
    ("onboarding", "Onboarding"),
    ("knowledge_base", "Knowledge base"),
)


def seed_default_prompts_for_user(user: Any, overwrite: bool = False) -> dict:
    """
    Insert default Prompt documents for this provider (service_id = user.pk).

    Idempotent by default: skips types that already exist for this service_id.
    If overwrite=True, updates existing rows with current default prompt text.
    """
    service_id = user.pk
    if service_id is None:
        logger.warning("seed_default_prompts_for_user: user has no pk; skipping")
        return {"inserted": 0, "updated": 0, "skipped": 0}

    sid = service_id if isinstance(service_id, ObjectId) else ObjectId(str(service_id))
    inserted = 0
    updated = 0
    skipped = 0

    for prompt_type, default_title in CANONICAL_PROMPTS:
        prompt_text = (DEFAULT_PROMPT_TEXTS.get(prompt_type) or "").strip()
        existing = Prompt.objects.filter(service_id=sid, prompt_type=prompt_type).first()

        if existing:
            if overwrite:
                existing.title = default_title
                existing.prompt_text = prompt_text
                existing.save(update_fields=["title", "prompt_text"])
                updated += 1
                logger.info(
                    "Updated prompt service_id=%s prompt_type=%s (chars=%s)",
                    sid,
                    prompt_type,
                    len(prompt_text),
                )
            else:
                skipped += 1
            continue

        Prompt.objects.create(
            service_id=sid,
            prompt_type=prompt_type,
            title=default_title,
            icon=None,
            prompt_text=prompt_text,
        )
        inserted += 1
        logger.info(
            "Seeded prompt service_id=%s prompt_type=%s (chars=%s)",
            sid,
            prompt_type,
            len(prompt_text),
        )

    return {"inserted": inserted, "updated": updated, "skipped": skipped}
