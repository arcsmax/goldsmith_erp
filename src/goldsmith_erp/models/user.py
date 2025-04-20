from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

class UserBase(BaseModel):
    """Basis-Schema für User."""
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserCreate(UserBase):
    """Schema für User-Erstellung."""
    password: str

class UserUpdate(BaseModel):
    """Schema für User-Updates."""
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

class User(UserBase):
    """Schema für User-Anzeige."""
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        orm_mode = True

class UserInDB(User):
    """Internes Schema mit Hash-Passwort."""
    hashed_password: str