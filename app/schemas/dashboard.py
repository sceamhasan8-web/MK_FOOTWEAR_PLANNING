from typing import List, Optional
from datetime import date
from pydantic import BaseModel


class DailyScheduleRow(BaseModel):
    date: date
    is_workday: bool
    day_name: str
    opening_balance: float
    planned_quantity: float
    actual_accepted_quantity: float
    rejected_quantity: float
    closing_balance: float
    cumulative_accepted_quantity: float
    completion_percentage: float
    variance: float
    remarks: Optional[str] = None


class DailySchedulePlanOut(BaseModel):
    order_id: int
    operation_id: int
    operation_name: str
    required_quantity: float
    remaining_balance: float
    remaining_working_days: int
    daily_target: float
    rows: List[DailyScheduleRow] = []


class SectionPerformance(BaseModel):
    section_id: int
    section_name: str
    category_name: str
    total_planned_today: float
    total_actual_today: float
    variance: float
    is_behind: bool


class DashboardSummaryOut(BaseModel):
    total_active_buyers: int
    active_orders_count: int
    total_ordered_pairs: float
    completed_pairs: float
    outstanding_production_pairs: float
    total_balance: Optional[float] = 0.0
    running_date: Optional[date] = None
    planning_date_display: Optional[str] = None
    orders_due_today: int
    orders_due_7_days: int
    overdue_orders_count: int
    at_risk_orders_count: int
    sections_behind_count: int
    today_total_planned: float
    today_total_actual: float
    wip_waiting_qty: Optional[float] = 0.0
    wip_waiting_count: Optional[int] = 0
    section_performances: List[SectionPerformance] = []

