import json

class WhatsAppUI:
    """
    Factory class for generating Meta WhatsApp Cloud API exact JSON payloads
    for Interactive Messages (Buttons and Lists). Layer 4 Presentation layer.
    """

    @staticmethod
    def build_button_message(to_number: str, text: str, buttons: list[dict]) -> dict:
        """
        Builds a Quick Reply 'button' interactive message payload.
        Meta allows a maximum of 3 buttons.
        Each button dict should have 'id' and 'title'.
        """
        if len(buttons) > 3:
            raise ValueError("Meta WhatsApp API allows a maximum of 3 buttons per message.")

        action_buttons = []
        for btn in buttons:
            action_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"][:20]  # Meta enforces max 20 chars
                }
            })

        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": text
                },
                "action": {
                    "buttons": action_buttons
                }
            }
        }

    @staticmethod
    def build_list_message(to_number: str, text: str, menu_button_text: str, sections: list[dict]) -> dict:
        """
        Builds a 'list' interactive message payload.
        Meta allows up to 10 rows across all sections.
        Each section dict should have a 'title' and a 'rows' list.
        Each row is a dict expecting at minimum an 'id' and 'title', and optionally a 'description'.
        """
        # Ensure deep compliance mapping for sections
        formatted_sections = []
        for section in sections:
            formatted_rows = []
            for row in section.get("rows", []):
                formatted_row = {
                    "id": row["id"],
                    "title": row["title"][:24]  # Meta enforces max 24 chars for list titles
                }
                if "description" in row and row["description"]:
                    formatted_row["description"] = row["description"][:72]  # Max 72 chars
                formatted_rows.append(formatted_row)
            
            formatted_sections.append({
                "title": section["title"][:24],
                "rows": formatted_rows
            })

        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {
                    "text": text
                },
                "action": {
                    "button": menu_button_text[:20],  # Max 20 chars
                    "sections": formatted_sections
                }
            }
        }


if __name__ == "__main__":
    # --- Dummy Usage Example ---
    ui = WhatsAppUI()

    print("\n--- Testing Single Button Message Component ---")
    mock_buttons = [
        {"id": "CMD_VIEW_PANTRY", "title": "View Pantry"},
        {"id": "CMD_MAIN_MENU", "title": "Main Menu"}
    ]
    
    button_payload = WhatsAppUI.build_button_message(
        to_number="1234567890",
        text="What's next? You can check your pantry or return to the main menu.",
        buttons=mock_buttons
    )
    print(json.dumps(button_payload, indent=2))

    print("\n--- Testing List Message Component ---")
    mock_sections = [
        {
            "title": "Inventory Actions",
            "rows": [
                {"id": "CMD_VIEW_PANTRY", "title": "View Pantry", "description": "See your current grocery list"},
                {"id": "CMD_ADD_ITEM", "title": "Add Item", "description": "Add new items to your pantry"}
            ]
        },
        {
            "title": "Settings",
            "rows": [
                {"id": "CMD_HELP", "title": "Help"},
            ]
        }
    ]

    list_payload = WhatsAppUI.build_list_message(
        to_number="1234567890",
        text="Please select an option from the menu below:",
        menu_button_text="Main Menu",
        sections=mock_sections
    )
    print(json.dumps(list_payload, indent=2))
