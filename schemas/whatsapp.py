from pydantic import BaseModel, Field
from typing import List, Optional

class TextMessage(BaseModel):
    """Represents the text payload in a WhatsApp message."""
    body: str

class ImageMessage(BaseModel):
    """Represents the image payload in a WhatsApp message."""
    mime_type: str
    sha256: str
    id: str

class AudioMessage(BaseModel):
    """Represents the audio payload in a WhatsApp message."""
    mime_type: str
    sha256: str
    id: str
    voice: Optional[bool] = False

class ButtonReply(BaseModel):
    """Represents the payload of an interactive button click."""
    id: str
    title: str

class ListReply(BaseModel):
    """Represents the payload of an interactive list selection."""
    id: str
    title: str
    description: Optional[str] = None

class InteractiveMessage(BaseModel):
    """Represents an interactive message payload."""
    type: str  # e.g., 'button_reply', 'list_reply'
    button_reply: Optional[ButtonReply] = None
    list_reply: Optional[ListReply] = None

class Message(BaseModel):
    """Represents a single WhatsApp message from a user."""
    from_: str = Field(alias="from", description="The sender's WhatsApp ID/phone number")
    id: str
    timestamp: str
    type: str  # Enum could be used here: 'text', 'image', 'audio', 'interactive'
    text: Optional[TextMessage] = None
    image: Optional[ImageMessage] = None
    audio: Optional[AudioMessage] = None
    interactive: Optional[InteractiveMessage] = None

class Profile(BaseModel):
    """Represents the profile information of the sender."""
    name: str

class Contact(BaseModel):
    """Represents the contact information of the sender."""
    profile: Profile
    wa_id: str

class Metadata(BaseModel):
    """Represents metadata of the phone number receiving the message."""
    display_phone_number: str
    phone_number_id: str

class ChangeValue(BaseModel):
    """Represents the value block inside a WhatsApp webhook change."""
    messaging_product: str
    metadata: Metadata
    contacts: Optional[List[Contact]] = None
    messages: Optional[List[Message]] = None

class Change(BaseModel):
    """Represents a change block describing an event."""
    value: ChangeValue
    field: str

class Entry(BaseModel):
    """Represents an entry in the WhatsApp webhook payload."""
    id: str
    changes: List[Change]

class WhatsAppWebhookPayload(BaseModel):
    """Root model for parsing the incoming Meta WhatsApp Webhook payload."""
    object: str
    entry: List[Entry]
