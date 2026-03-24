class WhatsAppUI:
    """
    Layer 4 Presentation factory.
    Generates spec-compliant Meta WhatsApp Cloud API interactive message payloads.
    All character limits are enforced here so callers never exceed Meta constraints.
    """

    @staticmethod
    def build_button_message(
        to_number: str,
        text: str,
        buttons: list[dict],
    ) -> dict:
        """
        Builds a Quick Reply interactive message (up to 3 buttons).
        Each button dict requires 'id' and 'title' keys.
        """
        if len(buttons) > 3:
            raise ValueError("Meta allows a maximum of 3 buttons per message.")

        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": btn["id"],
                                "title": btn["title"][:20],  # Meta max 20 chars
                            },
                        }
                        for btn in buttons
                    ]
                },
            },
        }

    @staticmethod
    def build_list_message(
        to_number: str,
        text: str,
        menu_button_text: str,
        sections: list[dict],
    ) -> dict:
        """
        Builds an interactive list message (up to 10 rows total across all sections).
        Each section requires 'title' and 'rows'; each row requires 'id' and 'title',
        with an optional 'description'.
        """
        formatted_sections = []
        for section in sections:
            rows = []
            for row in section.get("rows", []):
                formatted_row: dict = {
                    "id": row["id"],
                    "title": row["title"][:24],  # Meta max 24 chars
                }
                if row.get("description"):
                    formatted_row["description"] = row["description"][:72]
                rows.append(formatted_row)
            formatted_sections.append({
                "title": section["title"][:24],
                "rows": rows,
            })

        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": text},
                "action": {
                    "button": menu_button_text[:20],
                    "sections": formatted_sections,
                },
            },
        }
