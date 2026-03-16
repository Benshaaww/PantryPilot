import requests
import time
import uuid

WEBHOOK_URL = "http://127.0.0.1:8000/api/webhook"

def build_payload(wamid: str):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "123", "phone_number_id": "123"},
                    "messages": [{
                        "from": "1234567890",
                        "id": wamid,
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": "test message"}
                    }]
                },
                "field": "messages"
            }]
        }]
    }

def test_deduplication():
    wamid = f"wamid.{uuid.uuid4()}"
    payload = build_payload(wamid)
    
    print(f"Sending first request with wamid: {wamid}")
    resp1 = requests.post(WEBHOOK_URL, json=payload)
    print(f"Response 1: {resp1.status_code} - {resp1.json()}")
    
    print(f"Sending duplicate request with wamid: {wamid}")
    resp2 = requests.post(WEBHOOK_URL, json=payload)
    print(f"Response 2: {resp2.status_code} - {resp2.json()}")
    
    if resp2.json().get("detail") == "duplicate":
        print("SUCCESS: Duplicate detected and handled.")
    else:
        print("FAILURE: Duplicate not detected.")

if __name__ == "__main__":
    test_deduplication()
