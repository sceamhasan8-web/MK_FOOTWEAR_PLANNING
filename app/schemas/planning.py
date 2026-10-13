from typing import List, Optional
from datetime import date
from pydantic import BaseModel


class CategoryFlowItemOut(BaseModel):
    category_id: int
    category_name: str
    display_order: int
    required_quantity: float
    opening_on_hand: float
    incoming_wip: float
    available_on_hand: float
    actual_production: float
    completed_output: float
    closing_on_hand: float
    current_on_hand: float
    balance: float
    status: str
    wip_status: str


class OrderCategoryFlowOut(BaseModel):
    order_id: int
    order_code: str
    buyer_name: Optional[str] = None
    order_quantity: float
    shipment_date: date
    final_completed_quantity: float
    final_balance: float
    categories: List[CategoryFlowItemOut] = []


class PlanningSheetRowOut(BaseModel):
    date: date
    buyer_id: Optional[int] = None
    buyer_name: Optional[str] = None
    order_id: int
    order_code: str
    order_quantity: float
    category_id: Optional[int] = None
    category_name: str
    section_id: Optional[int] = None
    section_name: str
    operation_id: Optional[int] = None
    operation_name: str
    opening_on_hand: float
    incoming_wip: float
    available_on_hand: float
    daily_target: float
    executable_target: float
    actual_production: Optional[float] = None
    completed_output: float
    closing_on_hand: float
    balance: float
    variance: Optional[float] = None
    wip_status: str
    production_status: str
    shipment_date: date


class SectionCellData(BaseModel):
    tg: float
    on_hand: float
    ot: float
    closing_on_hand: float
    balance: float
    status: str
    status_code: str
    is_required: bool = True


class MatrixDateRowOut(BaseModel):
    date: date
    is_workday: bool
    day_name: str
    remaining_working_days: int
    section_data: dict[str, SectionCellData]


class SectionSummaryOut(BaseModel):
    section_name: str
    section_id: Optional[int] = None
    planning_id: Optional[int] = None
    total_tg: float
    final_on_hand: float
    total_ot: float
    balance: float
    status: str
    status_code: str
    target_matches_balance: Optional[bool] = None
    future_target_total: Optional[float] = None
    daily_target: Optional[float] = None
    required_daily_rate: Optional[float] = None
    executable_daily_target: Optional[float] = None
    executable_tg: Optional[float] = None
    allocatable_wip: Optional[float] = None
    effective_minimum_target: Optional[int] = None
    maximum_daily_target: Optional[int] = None
    calculation_mode: Optional[str] = None
    feasibility: Optional[dict] = None


class OrderMatrixPlanningOut(BaseModel):
    order_id: int
    order_code: str
    buyer_id: Optional[int] = None
    buyer_name: str
    style_model: Optional[str] = None
    total_quantity: float
    order_quantity: Optional[float] = None
    completed_quantity: Optional[float] = 0.0
    current_balance: Optional[float] = None
    production_start_date: date
    shipment_date: date
    running_date: Optional[date] = None
    planning_date: Optional[str] = None
    original_delivery_date: date
    remaining_working_days: int
    working_days: Optional[int] = None
    working_dates: List[date] = []
    final_balance: float
    total_planned_target: Optional[float] = None
    validation: Optional[dict] = None
    overall_status: str
    sections: list[dict] = []
    rows: list[MatrixDateRowOut] = []
    summary: dict[str, SectionSummaryOut] = {}
    category_flow_summary: list[CategoryFlowItemOut] = []
    order_completion_summary: dict = {}


class WipAdjustmentCreate(BaseModel):
    workflow_id: int
    date: date
    quantity: float
    reason: str


class WipAdjustmentOut(BaseModel):
    id: int
    order_id: int
    workflow_id: int
    date: date
    quantity: float
    reason: str
    user_id: int
    status: str

    class Config:
        from_attributes = True


class WipFlowDailyRow(BaseModel):
    date: date
    date_str: str
    date_display: str
    is_workday: bool
    is_working_day: Optional[bool] = None
    day_name: str
    serial_no: int
    route_id: int
    section_id: int
    section_name: str
    target: float
    tg: Optional[float] = None
    opening_on_hand: float
    incoming_wip: float
    available_wip: float
    actual_production: Optional[float] = None
    actual: float
    complete: float
    closing_on_hand: float
    balance: float
    remaining_working_days: int
    remaining_days: Optional[int] = None
    status: str
    status_code: str
    transfer_rule: str


class WipWorkflowSummaryItem(BaseModel):
    serial_no: int
    route_id: int
    section_id: int
    section_name: str
    required_quantity: float
    required_qty: Optional[float] = None
    total_target: float
    total_tg: float
    complete: float
    final_on_hand: float
    closing_on_hand: float
    balance: float
    status: str
    status_code: str
    transfer_rule: str


class WipFlowDateGroup(BaseModel):
    date: date
    date_str: str
    date_display: str
    day_name: str
    is_workday: bool
    remaining_working_days: int
    sections: List[WipFlowDailyRow] = []


class WipOrderCompletionSummary(BaseModel):
    order_quantity: float
    completed_quantity: float
    final_balance: float
    remaining_balance: Optional[float] = None
    remaining_working_days: int
    days_remaining: Optional[int] = None
    current_bottleneck: str
    bottleneck_section: Optional[str] = None
    wip_waiting: float
    wip_waiting_quantity: Optional[float] = None
    wip_waiting_display: str
    overall_status: str


class WipFlowPlanResponse(BaseModel):
    order_id: int
    order_code: str
    buyer_id: Optional[int] = None
    buyer_name: str
    customer_ref: Optional[str] = None
    style_model: str
    order_quantity: float
    total_quantity: Optional[float] = None
    planning_start_date: date
    shipment_date: date
    running_date: date
    remaining_working_days: int
    final_balance: float
    overall_status: str
    current_bottleneck: str
    bottleneck: Optional[str] = None
    bottleneck_process: Optional[str] = None
    wip_waiting: float
    wip_waiting_quantity: Optional[float] = None
    sections: List[dict] = []
    workflow: List[WipWorkflowSummaryItem] = []
    workflow_summary: List[WipWorkflowSummaryItem] = []
    summary: List[WipWorkflowSummaryItem] = []
    rows: List[WipFlowDailyRow] = []
    daily_plan_rows: List[WipFlowDailyRow] = []
    dates_grouped: List[WipFlowDateGroup] = []
    matrix_rows: List[dict] = []
    completion_summary: WipOrderCompletionSummary


