from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.user import UserRole


class CategorySettingsUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    display_order: int = 0
    is_active: bool = True
    description: Optional[str] = None
    reason: Optional[str] = None


class SectionSettingsUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category_id: int
    display_order: int = 0
    planning_id: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True
    counting_unit: str = "Pairs"
    description: Optional[str] = None
    minimum_daily_target: Optional[int] = Field(default=None, ge=0)
    maximum_daily_target: Optional[int] = Field(default=None, ge=0)
    calculation_mode: Optional[str] = "BALANCED"
    reason: Optional[str] = None


class SectionReorderItem(BaseModel):
    section_id: int
    planning_id: int = Field(gt=0)


class SectionReorderRequest(BaseModel):
    items: List[SectionReorderItem]
    reason: Optional[str] = None


class SectionDeactivateRequest(BaseModel):
    reason: Optional[str] = None
    force_confirm: bool = False
    remove_from_active_workflows: bool = True


class GeneralSettingsUpdate(BaseModel):
    company_name: str = "Footwear Manufacturing Co."
    company_logo: Optional[str] = ""
    reporting_title: str = "Footwear Production & WIP Flow Report"
    company_address: Optional[str] = "Dhaka, Bangladesh"
    company_contact: Optional[str] = "+880-1700-000000"
    timezone: str = "Asia/Dhaka"
    date_format: str = "DD/MM/YYYY"
    planning_cutoff_hour: int = Field(default=18, ge=0, le=23)
    planning_cutoff_minute: int = Field(default=0, ge=0, le=59)
    include_today_after_cutoff: bool = False
    default_unit: str = "Pairs"
    component_units: str = "Pieces, Sets"
    thousand_separator: bool = True
    decimal_places: int = Field(default=0, ge=0, le=4)
    theme_default: str = "light"
    default_order_priority: str = "MEDIUM"
    default_order_status: str = "SCHEDULED"
    default_target_calculation_mode: str = "BALANCED"
    reason: Optional[str] = None


class WipSettingsUpdate(BaseModel):
    wip_transfer_timing: str = "IMMEDIATE"  # "IMMEDIATE" or "NEXT_WORKING_DAY"
    wip_transfer_source: str = "ACCEPTED_ONLY"
    enforce_wip_limit: bool = True
    allow_wip_override: bool = True
    require_override_reason: bool = True
    auto_recalculate_plans: bool = True
    reason: Optional[str] = None


class ProductionEntrySettingsUpdate(BaseModel):
    default_production_unit: str = "Pairs"
    track_rejected_quantity: bool = True
    separate_accepted_rejected: bool = True
    supervisor_approval_required: bool = True
    overproduction_warnings: bool = True
    allow_authorized_override: bool = True
    roles_can_edit_history: str = "admin,planning_manager"
    reversal_reason_mandatory: bool = True
    reason: Optional[str] = None


class PlanningValidationSettingsUpdate(BaseModel):
    warn_tg_exceeds_wip: bool = True
    warn_target_exceeds_max: bool = True
    warn_min_conflicts_balance: bool = True
    warn_shipment_infeasible: bool = True
    warn_waiting_for_wip: bool = True
    warn_overproduction: bool = True
    require_override_reason: bool = True
    require_supervisor_approval: bool = True
    reason: Optional[str] = None


class ReportExportSettingsUpdate(BaseModel):
    default_xlsx_filename_format: str = "Footwear_ERP_{report_type}_{date}"
    date_display_format: str = "YYYY-MM-DD"
    include_summary_rows: bool = True
    include_inactive_sections: bool = False
    default_date_range_days: int = Field(default=14, ge=1, le=180)
    include_detailed_history: bool = True
    original_planning_title: str = "Original Production Planning — T/G / ON HAND / O/T"
    wip_planning_title: str = "WIP Flow Planning"
    reason: Optional[str] = None


class UserRoleUpdate(BaseModel):
    role: UserRole
    is_active: Optional[bool] = None
    reason: Optional[str] = None


class ImpactCheckRequest(BaseModel):
    setting_type: str  # section, section_target, calendar, general, wip
    entity_id: Optional[int] = None
    new_value: Optional[Any] = None


class ImpactCheckResponse(BaseModel):
    setting_type: str
    entity_id: Optional[int] = None
    affected_order_count: int
    affected_orders: List[Dict[str, Any]] = []
    message: str


class RecalculateRequest(BaseModel):
    setting_type: str
    entity_id: Optional[int] = None
    reason: Optional[str] = None


class RecalculateResponse(BaseModel):
    status: str
    recalculated_order_count: int
    message: str
    timestamp: datetime
