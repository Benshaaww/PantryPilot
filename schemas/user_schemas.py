from enum import Enum
from pydantic import BaseModel
from typing import Optional

class UserRole(str, Enum):
    BUYER = "buyer"
    REQUESTER = "requester"

class User(BaseModel):
    phone_number: str
    name: str
    role: UserRole
    family_id: Optional[str] = None
    reminder_day: Optional[str] = None
    notification_enabled: bool = False
