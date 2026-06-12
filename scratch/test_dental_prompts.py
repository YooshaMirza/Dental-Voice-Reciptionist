import sys
from unittest.mock import MagicMock

# 1. Mock Django settings before importing the call prompts
mock_django = MagicMock()
mock_settings = MagicMock()
mock_settings.GEMINI_PROVIDER = 'vertex'
mock_settings.VERTEX_AI_MODEL_ID = 'gemini-live-2.5-flash-native-audio'
mock_django.conf.settings = mock_settings

sys.modules['django'] = mock_django
sys.modules['django.conf'] = mock_django.conf

# 2. Import the prompt getter
from voice_agent.call_prompts import get_system_prompt

# Test 1: Inbound call prompt
inbound_data = {
    "direction": "inbound",
    "customerName": "Yoosha Mirza",
    "first_name": "Yoosha",
    "last_name": "Mirza",
    "preferred_day": "Tuesday",
    "selected_time": "2:30 PM",
    "phone_number": "8325551234",
    "appointment_date": "May 26th"
}

inbound_prompt = get_system_prompt(inbound_data)
print("=== INBOUND PROMPT TEST ===")
print("Prompt length:", len(inbound_prompt))

# Check some replacements and assertions
assert "Alice" in inbound_prompt
assert "Dental Care and Implants of Houston" in inbound_prompt
assert "165 Greens Rd" in inbound_prompt
assert "May 26th" in inbound_prompt  # replaced from {{selected_date}} / {{appointment_date}}
print("[OK] Inbound prompt replacement verified successfully!")

# Test 2: Outbound call prompt
outbound_data = {
    "direction": "outbound",
    "contact_first_name": "Yoosha",
    "contact_last_name": "Mirza",
    "appointment_day": "Friday",
    "appointment_date": "May 29th",
    "appointment_time": "11:00 AM",
    "phone": "+18325551234"
}

outbound_prompt = get_system_prompt(outbound_data)
print("\n=== OUTBOUND PROMPT TEST ===")
print("Prompt length:", len(outbound_prompt))
assert "Dentina" in outbound_prompt
assert "Mirza" in outbound_prompt
assert "Friday" in outbound_prompt
assert "May 29th" in outbound_prompt
assert "11:00 AM" in outbound_prompt
# check last 4 phone
assert "1234" in outbound_prompt
print("[OK] Outbound prompt replacement verified successfully!")

print("\nALL TESTS PASSED SUCCESSFULLY!")
