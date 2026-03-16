import requests
import time
import uuid

WEBHOOK_URL = "http://127.0.0.1:8000/api/webhook"
SENDER = "1234567890"

def build_text_payload(text: str):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "123", "phone_number_id": "123"},
                    "messages": [{
                        "from": SENDER,
                        "id": f"wamid.{uuid.uuid4()}",
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": text}
                    }]
                },
                "field": "messages"
            }]
        }]
    }

def test_race_condition():
    item_name = f"item_{uuid.uuid4().hex[:6]}"
    print(f"Adding item: {item_name}")
    resp1 = requests.post(WEBHOOK_URL, json=build_text_payload(f"Add {item_name}"))
    print(f"Add Response: {resp1.status_code}")
    
    # Wait a tiny bit to ensure the background task starts but not enough for the LLM to necessarily finish if it was slow
    # However, since we await DB write, the READ_LIST should see it if it fires after
    print("Requesting list immediately...")
    resp2 = requests.post(WEBHOOK_URL, json=build_text_payload("View my list"))
    print(f"View Response: {resp2.status_code}")
    
    print("\nCheck the bot's logs or WhatsApp messages to confirm if the item appears in the list.")

if __name__ == "__main__":
    test_race_condition()
