"""Customer/Client Pydantic Models for CRM"""
from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Optional, List
from datetime import datetime
import re


class CustomerBase(BaseModel):
    """Base Customer schema with common fields"""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    email: EmailStr = Field(..., description="Customer email address")
    phone: Optional[str] = Field(None, max_length=50)
    mobile: Optional[str] = Field(None, max_length=50)
    street: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: str = Field("Deutschland", max_length=100)
    customer_type: str = Field("private", description="private or business")
    source: Optional[str] = Field(None, max_length=100, description="How customer found us")
    notes: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name contains only allowed characters"""
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        v = v.strip()
        # Allow letters, spaces, hyphens, apostrophes, and common diacritics
        if not re.match(r"^[a-zA-ZäöüÄÖÜßàáâãèéêìíîòóôõùúûçñ\s'\-]+$", v):
            raise ValueError("Name contains invalid characters")
        return v

    @field_validator('company_name')
    @classmethod
    def validate_company_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate company name if provided"""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # Allow alphanumeric, spaces, and common business characters
        if not re.match(r"^[a-zA-Z0-9äöüÄÖÜß\s&.,\-()]+$", v):
            raise ValueError("Company name contains invalid characters")
        return v

    @field_validator('customer_type')
    @classmethod
    def validate_customer_type(cls, v: str) -> str:
        """Validate customer type"""
        allowed_types = ['private', 'business']
        if v not in allowed_types:
            raise ValueError(f"Customer type must be one of: {', '.join(allowed_types)}")
        return v

    @field_validator('phone', 'mobile')
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format"""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # Allow numbers, spaces, +, -, (), /
        if not re.match(r"^[\d\s+\-()\/]+$", v):
            raise ValueError("Phone number contains invalid characters")
        return v

    @field_validator('postal_code')
    @classmethod
    def validate_postal_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate postal code format"""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        # For Germany: 5 digits, but allow international formats
        if not re.match(r"^[\d\s\-A-Z]{3,10}$", v):
            raise ValueError("Invalid postal code format")
        return v

    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> List[str]:
        """Validate tags list"""
        if v is None:
            return []
        # Remove empty tags and duplicates
        tags = [tag.strip() for tag in v if tag and tag.strip()]
        return list(set(tags))  # Remove duplicates


class CustomerCreate(CustomerBase):
    """Schema for creating a new customer"""
    pass


class CustomerUpdate(BaseModel):
    """Schema for updating a customer (all fields optional)"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    mobile: Optional[str] = Field(None, max_length=50)
    street: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    customer_type: Optional[str] = None
    source: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate name if provided"""
        if v is None:
            return v
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        v = v.strip()
        if not re.match(r"^[a-zA-ZäöüÄÖÜßàáâãèéêìíîòóôõùúûçñ\s'\-]+$", v):
            raise ValueError("Name contains invalid characters")
        return v


class CustomerRead(CustomerBase):
    """Schema for reading a customer (includes DB fields)"""
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CustomerListItem(BaseModel):
    """Lightweight schema for customer lists"""
    id: int
    first_name: str
    last_name: str
    company_name: Optional[str]
    email: str
    phone: Optional[str]
    customer_type: str
    tags: List[str]
    is_active: bool

    class Config:
        from_attributes = True


class CustomerWithOrders(CustomerRead):
    """Customer schema with order count"""
    order_count: int = 0
    total_spent: float = 0.0
    last_order_date: Optional[datetime] = None

    class Config:
        from_attributes = True
