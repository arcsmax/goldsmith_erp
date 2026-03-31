"""Pydantic schemas for Order Comments (Digitale Post-its)."""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class OrderCommentBase(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class OrderCommentCreate(OrderCommentBase):
    pass


class OrderCommentUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=5000)


class OrderCommentRead(OrderCommentBase):
    id: int
    order_id: int
    user_id: int
    user_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
