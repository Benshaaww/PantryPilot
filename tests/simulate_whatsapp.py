import requests
import json
import time

# Target local webhook URL
WEBHOOK_URL = "http://127.0.0.1:8000/api/webhook"

def build_text_payload(message_body: str, sender_phone: str = "1234567890") -> dict:
    """Constructs a Meta incoming webhook payload for a text message."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "16505551111",
                        "phone_number_id": "123456123456"
                    },
                    "contacts": [{
                        "profile": {"name": "Test User"},
                        "wa_id": sender_phone
                    }],
                    "messages": [{
                        "from": sender_phone,
                        "id": f"wamid.{int(time.time())}",
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": message_body}
                    }]
                },
                "field": "messages"
            }]
        }]
    }

def build_audio_payload(audio_id: str = "sample_audio_123", sender_phone: str = "1234567890") -> dict:
    """Constructs a Meta incoming webhook payload for an audio/voice message."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "16505551111",
                        "phone_number_id": "123456123456"
                    },
                    "contacts": [{
                        "profile": {"name": "Test User"},
                        "wa_id": sender_phone
                    }],
                    "messages": [{
                        "from": sender_phone,
                        "id": f"wamid.{int(time.time())}",
                        "timestamp": str(int(time.time())),
                        "type": "audio",
                        "audio": {
                            "mime_type": "audio/ogg; codecs=opus",
                            "sha256": "hash_here",
                            "id": audio_id,
                            "voice": True
                        }
                    }]
                },
                "field": "messages"
            }]
        }]
    }

def simulate_message():
    """Sends the mock payload to the FastAPI server."""
    
    # 1. Simulate a standard text request
    text_message = "Hey, we are out of milk and need 2 loaves of bread for tomorrow."
    print(f"Sending Text Payload: '{text_message}'")
    
    payload = build_text_payload(text_message)
    
    # 2. To simulate audio, uncomment the lines below:
    # print("Sending Audio Payload")
    # payload = build_audio_payload()

    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        print(f"Server responded with status code: {response.status_code}")
        print(f"Response Body: {response.json()}")
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Could not connect to {WEBHOOK_URL}.")
        print("Is the FastAPI server running? (python -m uvicorn main:app --reload)")

if __name__ == "__main__":
    simulate_message()
