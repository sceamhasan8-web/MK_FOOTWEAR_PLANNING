from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field


class DailyProductionEntryCreate(BaseModel):
    entry_date: date
    order_id: int
    route_id: int
    operation_id: int
    component_id: Optional[int] = None
    quantity: float = Field(..., gt=0)
    accepted_quantity: float = Field(..., ge=0)
    rejected_quantity: float = Field(0.0, ge=0)
    unit: str = "PAIRS"
    remarks: Optional[str] = None
    is_override: bool = False  # Set to True when supervisor authorizes override of remaining target


class ProductionBulkItem(BaseModel):
    operation_id: int
    component_id: Optional[int] = None
    quantity: float = Field(..., gt=0)
    accepted_quantity: float = Field(..., ge=0)
    rejected_quantity: float = Field(0.0, ge=0)
    unit: str = "PAIRS"
    remarks: Optional[str] = None
    is_override: bool = False


class ProductionBulkCreate(BaseModel):
    entry_date: date
    order_id: int
    route_id: int
    items: List[ProductionBulkItem]


class ProductionCorrectionCreate(BaseModel):
    new_accepted_quantity: float = Field(..., ge=0)
    new_rejected_quantity: float = Field(0.0, ge=0)
    reason: str = Field(..., min_length=2)


class ProductionEntryReversalCreate(BaseModel):
    reason: str = Field(..., min_length=2)


class ProductionCorrectionOut(BaseModel):
    id: int
    entry_id: int
    original_accepted_qty: float
    new_accepted_qty: float
    original_rejected_qty: float
    new_rejected_qty: float
    action_type: str
    reason: str
    authorized_by_id: int
    authorized_by_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DailyProductionEntryOut(BaseModel):
    id: int
    entry_date: date
    order_id: int
    order_code: Optional[str] = None
    customer_ref: Optional[str] = None
    buyer_name: Optional[str] = None
    route_id: int
    section_name: Optional[str] = None
    operation_id: int
    operation_name: Optional[str] = None
    component_id: Optional[int] = None
    component_name: Optional[str] = None
    quantity: float
    accepted_quantity: float
    rejected_quantity: float
    unit: str
    remarks: Optional[str] = None
    entered_by_id: int
    entered_by_name: Optional[str] = None
    created_at: datetime
    is_reversed: bool
    is_override: bool
    updated_balance: Optional[float] = None
    updated_daily_target: Optional[float] = None
    remaining_days: Optional[int] = None
    available_on_hand: Optional[float] = None
    executable_target: Optional[float] = None
    corrections: List[ProductionCorrectionOut] = []

    class Config:
        from_attributes = True
