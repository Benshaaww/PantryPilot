import requests
import json

# Your local FastAPI server URL
URL = "http://127.0.0.1:8000/webhook"

# A perfect replica of Meta's "Button Click" JSON
mock_whatsapp_payload = {
    "object": "whatsapp_business_account",
    "entry": [{
        "id": "123456789",
        "changes": [{
            "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": "123", "phone_number_id": "456"},
                "contacts": [{"profile": {"name": "Ben"}, "wa_id": "1234567890"}],
                "messages": [{
                    "from": "1234567890",
                    "id": "wamid.HBg...",
                    "timestamp": "1700000000",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {
                            "id": "CMD_VIEW_PANTRY",
                            "title": "View Pantry"
                        }
                    }
                }]
            },
            "field": "messages"
        }]
    }]
}

print("🚀 Firing Fake WhatsApp Button Click to Local Server...")
try:
    response = requests.post(URL, json=mock_whatsapp_payload)
    print(f"✅ Server Status Code: {response.status_code}")
    print(f"✅ Server Response: {response.text}")
except Exception as e:
    print(f"❌ Connection Error: Is your uvicorn server running? ({e})")
