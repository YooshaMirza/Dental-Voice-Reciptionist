import requests
try:
    resp = requests.get("http://127.0.0.1:8001/voice-agent/", timeout=3)
    print("Server responded! Status code:", resp.status_code)
except Exception as e:
    print("Could not connect to server:", e)
