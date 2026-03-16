import requests
import json
import time

# Target local webhook URL
WEBHOOK_URL = "http://127.0.0.1:8000/webhook"

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

def build_interactive_payload(button_id: str, button_title: str, sender_phone: str = "1234567890") -> dict:
    """Constructs a Meta incoming webhook payload for an interactive button reply."""
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
                        "type": "interactive",
                        "interactive": {
                            "type": "button_reply",
                            "button_reply": {
                                "id": button_id,
                                "title": button_title
                            }
                        }
                    }]
                },
                "field": "messages"
            }]
        }]
    }

def send_request(payload: dict):
    """Helper to send the request and print the response."""
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        print(f"API responded with status code: {response.status_code}")
        print(f"Response Body: {response.json()}\n")
        # Give the background tasks a moment to execute
        time.sleep(3)
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Could not connect to {WEBHOOK_URL}.")
        print("Is the FastAPI server running? (python -m uvicorn main:app --reload)")
        exit(1)

def simulate_message():
    """Simulates the new multi-user Family OS flow."""
    print("=== STARTING FAMILY OS SIMULATION ===")
    
    phone_buyer = "9998887776"
    phone_req = "5554443332"
    
    # --- Scenario 1: Onboarding Flow ---
    print("\n--- 1. Buyer Onboarding (Interactive) ---")
    print("> Sending first message from unrecognized number (Triggers Step 1)...")
    send_request(build_text_payload("Hi there!", sender_phone=phone_buyer))
    
    print("> Replying with Family Account button (Triggers Step 2)...")
    send_request(build_interactive_payload("onboard_family", "Family Account", sender_phone=phone_buyer))
    
    print("> Replying with Parent (Buyer) button...")
    send_request(build_interactive_payload("role_parent", "Parent (Buyer)", sender_phone=phone_buyer))
    
    print("\n--- 2. Requester Onboarding (Interactive) ---")
    print("> Sending first message from unrecognized number (Triggers Step 1)...")
    send_request(build_text_payload("Hello", sender_phone=phone_req))
    
    print("> Replying with Family Account button (Triggers Step 2)...")
    send_request(build_interactive_payload("onboard_family", "Family Account", sender_phone=phone_req))
    
    print("> Replying with Child (Requester) button...")
    send_request(build_interactive_payload("role_child", "Child (Requester)", sender_phone=phone_req))
    
    # --- Scenario 2: Adding Items ---
    print("\n--- 3. Requester Adds Items ---")
    print(f"> {phone_req} (Child) requesting groceries...")
    send_request(build_text_payload("We are totally out of milk and need 2 loaves of bread.", sender_phone=phone_req))
    
    print("\n--- 4. Buyer Adds Items ---")
    print(f"> {phone_buyer} (Parent) requesting groceries...")
    send_request(build_text_payload("Add some bananas and a 6-pack of coke.", sender_phone=phone_buyer))
    
    # --- Scenario 3: Role-Base Checkout Guard ---
    print("\n--- 5. Requester Tries to Checkout (Should Block) ---")
    print(f"> {phone_req} (Child) attempting to order...")
    send_request(build_text_payload("Can you order everything on Sixty60?", sender_phone=phone_req))
    
    # --- Scenario 4: Buyer Grouped Checkout ---
    print("\n--- 6. Buyer Tries to Checkout (Should Succeed) ---")
    print(f"> {phone_buyer} (Parent) attempting to order...")
    send_request(build_text_payload("Checkout on Sixty60, let's buy these.", sender_phone=phone_buyer))

if __name__ == "__main__":
    simulate_message()
