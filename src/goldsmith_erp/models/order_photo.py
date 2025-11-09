# src/goldsmith_erp/models/order_photo.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class OrderPhotoBase(BaseModel):
    """Basis-Schema für OrderPhoto."""
    order_id: int
    notes: Optional[str] = None

class OrderPhotoCreate(OrderPhotoBase):
    """Schema für OrderPhoto-Erstellung."""
    time_entry_id: Optional[str] = None  # UUID, optional
    taken_by: int
    file_path: str

class OrderPhotoRead(OrderPhotoBase):
    """Schema für OrderPhoto-Anzeige."""
    id: str  # UUID
    time_entry_id: Optional[str] = None
    file_path: str
    timestamp: datetime
    taken_by: int
    user_name: Optional[str] = None  # Für erweiterte Anzeige

    model_config = ConfigDict(from_attributes=True)

class OrderPhotoUpload(BaseModel):
    """Schema für Photo-Upload mit Base64."""
    order_id: int
    time_entry_id: Optional[str] = None
    notes: Optional[str] = None
    image_base64: str  # Base64-codiertes Bild
