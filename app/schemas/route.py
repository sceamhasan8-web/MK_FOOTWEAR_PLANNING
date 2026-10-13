from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field, model_validator
from app.models.route import SectionRouteStatus, OperationStatus, UnitType


class ProcessTemplateOut(BaseModel):
    id: int
    section_id: int
    name: str
    default_unit: UnitType
    display_order: int
    is_active: bool

    class Config:
        from_attributes = True


class SectionOut(BaseModel):
    id: int
    category_id: int
    name: str
    display_order: int
    planning_id: Optional[int] = None
    is_active: bool
    counting_unit: str = "Pairs"
    description: Optional[str] = None
    updated_at: Optional[datetime] = None
    templates: List[ProcessTemplateOut] = []

    class Config:
        from_attributes = True


class CategoryOut(BaseModel):
    id: int
    name: str
    display_order: int
    is_active: bool
    description: Optional[str] = None
    updated_at: Optional[datetime] = None
    sections: List[SectionOut] = []

    class Config:
        from_attributes = True


class OperationComponentCreate(BaseModel):
    component_name: str
    unit: UnitType = UnitType.PIECES
    pieces_per_pair: float = 1.0
    required_total_qty: Optional[float] = None  # If None, calculated from order pairs * pieces_per_pair


class OperationComponentOut(BaseModel):
    id: int
    operation_id: int
    component_name: str
    unit: UnitType
    pieces_per_pair: float
    required_total_qty: float
    accepted_total_qty: float
    rejected_total_qty: float
    balance_total_qty: float
    pair_equivalent_accepted: float = 0.0

    class Config:
        from_attributes = True


class OrderOperationCreate(BaseModel):
    operation_name: str
    sequence_order: int = 0
    unit: UnitType = UnitType.PAIRS
    required_quantity: Optional[float] = None
    components: List[OperationComponentCreate] = []
    notes: Optional[str] = None


class OrderOperationOut(BaseModel):
    id: int
    route_id: int
    operation_name: str
    sequence_order: int
    unit: UnitType
    required_quantity: float
    completed_quantity: float
    rejected_quantity: float
    balance_quantity: float
    completion_percentage: float = 0.0
    daily_target: float = 0.0
    today_actual: float = 0.0
    today_variance: float = 0.0
    is_overproduced: bool = False
    overproduction_quantity: float = 0.0
    start_date: Optional[date] = None
    expected_finish_date: Optional[date] = None
    status: OperationStatus
    notes: Optional[str] = None
    components: List[OperationComponentOut] = []

    class Config:
        from_attributes = True


class OrderRouteCreate(BaseModel):
    section_id: Optional[int] = None
    section_name: Optional[str] = None
    serial_no: Optional[int] = None
    sequence_order: int = 0
    transfer_rule: str = "IMMEDIATE"
    status: SectionRouteStatus = SectionRouteStatus.REQUIRED
    has_components: bool = False
    minimum_daily_target: Optional[int] = None
    notes: Optional[str] = None
    operations: List[OrderOperationCreate] = []


class OrderRouteOut(BaseModel):
    id: int
    order_id: int
    section_id: int
    section_name: Optional[str] = None
    category_name: Optional[str] = None
    serial_no: int = 1
    transfer_rule: str = "IMMEDIATE"
    status: SectionRouteStatus
    sequence_order: int
    has_components: bool
    minimum_daily_target: Optional[int] = None
    effective_minimum_target: Optional[int] = None
    notes: Optional[str] = None
    operations: List[OrderOperationOut] = []
    is_completed: bool = False

    class Config:
        from_attributes = True


class ProductionTargetSettingUpdate(BaseModel):
    section_id: Optional[int] = None
    minimum_daily_target: int = Field(ge=0, description="Minimum daily target in counting units (pairs/day)")
    maximum_daily_target: Optional[int] = Field(default=0, ge=0, description="Maximum daily target (0=unlimited)")
    calculation_mode: Optional[str] = "BALANCED"
    override_policy: Optional[str] = "ALLOWED"
    unit: str = "Pairs/day"
    is_active: bool = True
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_targets(self):
        if self.minimum_daily_target < 0:
            raise ValueError("Minimum daily target cannot be negative")
        if self.maximum_daily_target is not None and self.maximum_daily_target < 0:
            raise ValueError("Maximum daily target cannot be negative")
        if self.maximum_daily_target is not None and self.maximum_daily_target > 0:
            if self.minimum_daily_target > self.maximum_daily_target:
                raise ValueError("Minimum daily target cannot exceed maximum daily target")
        return self


class ProductionTargetSettingOut(BaseModel):
    id: Optional[int] = None
    section_id: int
    section_name: str
    category_id: int
    category_name: str
    minimum_daily_target: int
    maximum_daily_target: int = 0
    calculation_mode: str = "BALANCED"
    override_policy: str = "ALLOWED"
    unit: str
    is_active: bool
    notes: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by_id: Optional[int] = None
    updated_by_username: Optional[str] = None

    class Config:
        from_attributes = True

