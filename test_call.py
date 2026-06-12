import requests

# ---------------------------------------------------------
# 🛠️ TEST CONFIGURATION
# ---------------------------------------------------------

# 1. Paste your current NGROK URL here (No trailing slash)
NGROK_URL = "https://66eb-2405-201-6837-e05e-d593-221e-4c9d-51d0.ngrok-free.app" 

# 2. Paste your REAL phone number (with country code, e.g., +91...)
MY_PHONE = "+919528114494" 

# ---------------------------------------------------------

url = f"{NGROK_URL}/api/voice-agent/twilio/make-call/"
payload = {
    "phone": MY_PHONE,
    "customerName": "Yoosha",
    "job_interest": "Software Engineer",
    "location": "India"
}

print(f"🚀 Triggering outbound call to {MY_PHONE} via {NGROK_URL}...")

try:
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("✅ SUCCESS! Your phone should be ringing in a few seconds.")
        print(f"Call Details: {response.json()}")
    else:
        print(f"❌ FAILED! Server returned error: {response.text}")
except Exception as e:
    print(f"❌ Error connecting to your server: {e}")
