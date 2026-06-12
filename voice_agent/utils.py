from voice_agent.call_prompts import get_system_prompt as get_prompt_by_type
import logging

logger = logging.getLogger(__name__)

def get_system_prompt(customer_data: dict, call_type: str = "onboarding", direction: str | None = None, current_time: str | None = None) -> str:
    """
    Generate system prompt for Gemini AI voice assistant based on onboarding logic.
    """
    logger.info(
        "Getting onboarding system prompt call_type=%s customer=%s",
        call_type,
        (customer_data or {}).get("customerName"),
    )
    return get_prompt_by_type(customer_data, call_type, current_time=current_time)
