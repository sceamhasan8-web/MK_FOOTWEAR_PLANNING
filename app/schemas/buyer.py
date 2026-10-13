from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class BuyerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    buyer_code: str = Field(..., min_length=1, max_length=50)
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


class BuyerCreate(BuyerBase):
    pass


class BuyerUpdate(BaseModel):
    name: Optional[str] = None
    buyer_code: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class BuyerOut(BuyerBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BuyerSummaryOut(BuyerOut):
    active_orders_count: int = 0
    completed_orders_count: int = 0
    total_ordered_pairs: float = 0.0
    outstanding_production_pairs: float = 0.0
