import json
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from app.models.route import Category, Section, ProductionTargetSetting, OrderRoute, SectionRouteStatus
from app.models.settings import SystemSetting
from app.models.audit import AuditLog
from app.models.order import Order, OrderStatus
from app.models.entry import DailyProductionEntry
from app.models.calendar import FactoryCalendar, CalendarException
from app.models.user import User, UserRole

logger = logging.getLogger("erp.settings_service")

# Default factory section target benchmarks
DEFAULT_SECTION_TARGETS = {
    "Cutting": {"min": 2000, "max": 4000, "unit": "Pairs/day", "mode": "BALANCED"},
    "Printing": {"min": 1500, "max": 3500, "unit": "Pairs/day", "mode": "BALANCED"},
    "Emboss": {"min": 1000, "max": 3000, "unit": "Pairs/day", "mode": "BALANCED"},
    "Embosse": {"min": 1000, "max": 3000, "unit": "Pairs/day", "mode": "BALANCED"},
    "Sewing": {"min": 2000, "max": 5000, "unit": "Pairs/day", "mode": "BALANCED"},
    "Lasting": {"min": 2000, "max": 4500, "unit": "Pairs/day", "mode": "BALANCED"},
    "Lamination": {"min": 1500, "max": 3500, "unit": "Pairs/day", "mode": "BALANCED"},
    "Skiving": {"min": 1500, "max": 3500, "unit": "Pairs/day", "mode": "BALANCED"},
    "Dip": {"min": 1500, "max": 4000, "unit": "Pairs/day", "mode": "BALANCED"},
}

DEFAULT_SYSTEM_SETTINGS = {
    # General
    "general.company_name": ("Footwear Manufacturing Co.", "string", "Company display name"),
    "general.company_logo": ("", "string", "Company logo URL or base64 data"),
    "general.reporting_title": ("Footwear Production & WIP Flow Report", "string", "Default title for reports"),
    "general.company_address": ("Dhaka, Bangladesh", "string", "Factory address"),
    "general.company_contact": ("+880-1700-000000", "string", "Factory contact"),
    "general.timezone": ("Asia/Dhaka", "string", "Factory timezone"),
    "general.date_format": ("DD/MM/YYYY", "string", "Date display format"),
    "general.planning_cutoff_hour": ("18", "integer", "Daily planning cutoff hour"),
    "general.planning_cutoff_minute": ("0", "integer", "Daily planning cutoff minute"),
    "general.include_today_after_cutoff": ("false", "boolean", "Include today in plan after cutoff"),
    "general.default_unit": ("Pairs", "string", "Default production counting unit"),
    "general.component_units": ("Pieces, Sets", "string", "Allowed component counting units"),
    "general.thousand_separator": ("true", "boolean", "Display numbers with commas"),
    "general.decimal_places": ("0", "integer", "Decimal precision for counting units"),
    "general.theme_default": ("light", "string", "Default ERP interface theme"),
    "general.default_order_priority": ("MEDIUM", "string", "Default order priority"),
    "general.default_order_status": ("SCHEDULED", "string", "Default initial order status"),
    "general.default_target_calculation_mode": ("BALANCED", "string", "Default automatic target mode"),

    # WIP & Workflow
    "wip.transfer_timing": ("IMMEDIATE", "string", "WIP transfer timing (IMMEDIATE or NEXT_WORKING_DAY)"),
    "wip.transfer_source": ("ACCEPTED_ONLY", "string", "Transfer source (ACCEPTED_ONLY)"),
    "wip.enforce_wip_limit": ("true", "boolean", "Enforce WIP quantity limit"),
    "wip.allow_wip_override": ("true", "boolean", "Allow authorized WIP adjustments"),
    "wip.require_override_reason": ("true", "boolean", "Require mandatory reason for WIP override"),
    "wip.auto_recalculate_plans": ("true", "boolean", "Automatically recalculate future plans after WIP change"),

    # Production Entry
    "entry.default_production_unit": ("Pairs", "string", "Default production entry unit"),
    "entry.track_rejected_quantity": ("true", "boolean", "Track rejected quantity in entries"),
    "entry.separate_accepted_rejected": ("true", "boolean", "Separate accepted vs rejected quantities"),
    "entry.supervisor_approval_required": ("true", "boolean", "Require supervisor approval for entry correction"),
    "entry.overproduction_warnings": ("true", "boolean", "Display warnings when entry exceeds balance"),
    "entry.allow_authorized_override": ("true", "boolean", "Allow authorized override for overproduction"),
    "entry.roles_can_edit_history": ("admin,planning_manager", "string", "Roles permitted to edit historical entries"),
    "entry.reversal_reason_mandatory": ("true", "boolean", "Require reason when reversing an entry"),

    # Planning Validation
    "validation.warn_tg_exceeds_wip": ("true", "boolean", "Warn if planned T/G exceeds allocatable WIP"),
    "validation.warn_target_exceeds_max": ("true", "boolean", "Warn if target exceeds section maximum"),
    "validation.warn_min_conflicts_balance": ("true", "boolean", "Warn if minimum target conflicts with remaining quantity"),
    "validation.warn_shipment_infeasible": ("true", "boolean", "Warn if shipment deadline is infeasible under capacity"),
    "validation.warn_waiting_for_wip": ("true", "boolean", "Warn when downstream section is waiting for WIP"),
    "validation.warn_overproduction": ("true", "boolean", "Warn on cumulative overproduction"),
    "validation.require_override_reason": ("true", "boolean", "Require reason for planning target override"),
    "validation.require_supervisor_approval": ("true", "boolean", "Require supervisor approval for planning exceptions"),

    # Reports & Exports
    "export.default_xlsx_filename_format": ("Footwear_ERP_{report_type}_{date}", "string", "Default filename pattern for Excel exports"),
    "export.date_display_format": ("YYYY-MM-DD", "string", "Date format in exports"),
    "export.include_summary_rows": ("true", "boolean", "Include summary total rows in exports"),
    "export.include_inactive_sections": ("false", "boolean", "Include inactive sections in historical exports"),
    "export.default_date_range_days": ("14", "integer", "Default date range span in days for export"),
    "export.include_detailed_history": ("true", "boolean", "Include detailed daily history table in export"),
    "export.original_planning_title": ("Original Production Planning — T/G / ON HAND / O/T", "string", "Title for Sheet 1"),
    "export.wip_planning_title": ("WIP Flow Planning", "string", "Title for Sheet 2"),
}


class SettingsService:

    @classmethod
    def initialize_defaults(cls, db: Session):
        """Seed default settings and missing target settings if not present."""
        try:
            for key, (val, dtype, desc) in DEFAULT_SYSTEM_SETTINGS.items():
                cat = key.split(".")[0]
                setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
                if not setting:
                    setting = SystemSetting(
                        category=cat,
                        key=key,
                        value=str(val),
                        data_type=dtype,
                        description=desc,
                        updated_at=datetime.utcnow()
                    )
                    db.add(setting)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Failed initializing default system settings: %s", e)

    # -------------------------------------------------------------------------
    # System Key-Value Store Helpers
    # -------------------------------------------------------------------------
    @classmethod
    def get_setting_value(cls, db: Session, key: str, default: Any = None) -> Any:
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not setting:
            fallback = DEFAULT_SYSTEM_SETTINGS.get(key)
            if fallback:
                raw_val, dtype, _ = fallback
            else:
                return default
        else:
            raw_val = setting.value
            dtype = setting.data_type

        if dtype == "boolean":
            return str(raw_val).strip().lower() in ("true", "1", "yes")
        elif dtype == "integer":
            try:
                return int(raw_val)
            except ValueError:
                return default
        elif dtype == "float":
            try:
                return float(raw_val)
            except ValueError:
                return default
        elif dtype == "json":
            try:
                return json.loads(raw_val)
            except Exception:
                return default
        return raw_val

    @classmethod
    def set_setting_value(cls, db: Session, key: str, value: Any, user_id: Optional[int] = None, reason: Optional[str] = None):
        cat = key.split(".")[0]
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        old_val = setting.value if setting else None
        new_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value).lower() if isinstance(value, bool) else str(value)

        if not setting:
            dtype = "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "json" if isinstance(value, (dict, list)) else "string"
            setting = SystemSetting(
                category=cat,
                key=key,
                value=new_str,
                data_type=dtype,
                updated_at=datetime.utcnow(),
                updated_by_id=user_id
            )
            db.add(setting)
        else:
            setting.value = new_str
            setting.updated_at = datetime.utcnow()
            setting.updated_by_id = user_id

        # Log audit if changed
        if old_val != new_str:
            cls.record_audit(
                db=db,
                entity_name="SystemSetting",
                entity_id=setting.id,
                action="UPDATE",
                setting_type=cat,
                user_id=user_id,
                details=json.dumps({"key": key, "old_value": old_val, "new_value": new_str}),
                reason=reason or f"Updated configuration {key}"
            )

        db.commit()
        db.refresh(setting)
        return setting

    # -------------------------------------------------------------------------
    # Audit History Helper
    # -------------------------------------------------------------------------
    @classmethod
    def record_audit(
        cls,
        db: Session,
        entity_name: str,
        entity_id: Optional[int],
        action: str,
        user_id: Optional[int] = None,
        setting_type: Optional[str] = None,
        details: Optional[str] = None,
        reason: Optional[str] = None,
        affected_order_count: int = 0,
        recalculation_status: Optional[str] = None
    ):
        try:
            log = AuditLog(
                entity_name=entity_name,
                entity_id=entity_id,
                action=action,
                setting_type=setting_type,
                user_id=user_id,
                timestamp=datetime.utcnow(),
                details=details,
                reason=reason,
                affected_order_count=affected_order_count,
                recalculation_status=recalculation_status
            )
            db.add(log)
            db.commit()
            return log
        except Exception as e:
            logger.error("Failed recording audit log: %s", e)
            return None

    # -------------------------------------------------------------------------
    # 2. Section & Category Management
    # -------------------------------------------------------------------------
    @classmethod
    def get_categories(cls, db: Session, include_inactive: bool = True) -> List[Category]:
        q = db.query(Category)
        if not include_inactive:
            q = q.filter(Category.is_active == True)
        return q.order_by(Category.display_order, Category.id).all()

    @classmethod
    def create_category(cls, db: Session, name: str, display_order: int = 0, is_active: bool = True, description: Optional[str] = None, user_id: Optional[int] = None) -> Category:
        existing = db.query(Category).filter(Category.name == name).first()
        if existing:
            raise ValueError(f"Category '{name}' already exists")

        cat = Category(
            name=name,
            display_order=display_order,
            is_active=is_active,
            description=description,
            updated_at=datetime.utcnow()
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)

        cls.record_audit(
            db=db,
            entity_name="Category",
            entity_id=cat.id,
            action="CREATE",
            setting_type="category",
            user_id=user_id,
            details=json.dumps({"name": cat.name, "display_order": cat.display_order}),
            reason="Added new production category"
        )
        return cat

    @classmethod
    def update_category(
        cls,
        db: Session,
        category_id: int,
        name: str,
        display_order: int = 0,
        is_active: bool = True,
        description: Optional[str] = None,
        user_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Category:
        cat = db.query(Category).filter(Category.id == category_id).first()
        if not cat:
            raise ValueError("Category not found")

        # Check duplicate name if renamed
        if cat.name != name:
            dup = db.query(Category).filter(Category.name == name, Category.id != category_id).first()
            if dup:
                raise ValueError(f"Category name '{name}' already in use")

        old_state = {"name": cat.name, "display_order": cat.display_order, "is_active": cat.is_active}
        cat.name = name
        cat.display_order = display_order
        cat.is_active = is_active
        if description is not None:
            cat.description = description
        cat.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(cat)

        cls.record_audit(
            db=db,
            entity_name="Category",
            entity_id=cat.id,
            action="UPDATE",
            setting_type="category",
            user_id=user_id,
            details=json.dumps({"old": old_state, "new": {"name": cat.name, "display_order": cat.display_order, "is_active": cat.is_active}}),
            reason=reason or f"Updated category {cat.name}"
        )
        return cat

    @classmethod
    def get_sections(cls, db: Session, category_id: Optional[int] = None, include_inactive: bool = True) -> List[Section]:
        q = db.query(Section)
        if category_id:
            q = q.filter(Section.category_id == category_id)
        if not include_inactive:
            q = q.filter(Section.is_active == True)
        return q.order_by(func.coalesce(Section.planning_id, Section.display_order, Section.id).asc(), Section.id.asc()).all()

    @classmethod
    def create_section(
        cls,
        db: Session,
        category_id: int,
        name: str,
        display_order: int = 0,
        planning_id: Optional[int] = None,
        is_active: bool = True,
        counting_unit: str = "Pairs",
        description: Optional[str] = None,
        min_target: Optional[int] = 0,
        max_target: Optional[int] = 0,
        calculation_mode: Optional[str] = "BALANCED",
        user_id: Optional[int] = None
    ) -> Section:
        cat = db.query(Category).filter(Category.id == category_id).first()
        if not cat:
            raise ValueError("Category not found")

        existing = db.query(Section).filter(Section.name == name, Section.category_id == category_id).first()
        if existing:
            raise ValueError(f"Section '{name}' already exists in this category")

        target_pid = planning_id if planning_id is not None else (display_order if display_order > 0 else None)
        if target_pid is None:
            max_pid = db.query(func.max(func.coalesce(Section.planning_id, Section.display_order, 0))).scalar() or 0
            target_pid = max_pid + 1
        else:
            if target_pid <= 0:
                raise ValueError("Planning ID must be a positive integer.")
            conflict = db.query(Section).filter(
                (Section.planning_id == target_pid) |
                ((Section.planning_id == None) & (Section.display_order == target_pid))
            ).first()
            if conflict:
                raise ValueError(f"Planning ID {target_pid} is already assigned to another section. Please choose a unique ID.")

        sec = Section(
            category_id=category_id,
            name=name,
            display_order=target_pid,
            planning_id=target_pid,
            is_active=is_active,
            counting_unit=counting_unit or "Pairs",
            description=description,
            updated_at=datetime.utcnow()
        )
        db.add(sec)
        db.commit()
        db.refresh(sec)

        # Initialize target setting for this section
        target_setting = ProductionTargetSetting(
            section_id=sec.id,
            minimum_daily_target=max(0, min_target or 0),
            maximum_daily_target=max(0, max_target or 0),
            calculation_mode=calculation_mode or "BALANCED",
            override_policy="ALLOWED",
            unit=f"{counting_unit}/day",
            is_active=True,
            notes="Default target initialized with section",
            updated_by_id=user_id,
            updated_at=datetime.utcnow()
        )
        db.add(target_setting)
        db.commit()

        cls.record_audit(
            db=db,
            entity_name="Section",
            entity_id=sec.id,
            action="CREATE",
            setting_type="section",
            user_id=user_id,
            details=json.dumps({"name": sec.name, "category_id": sec.category_id, "planning_id": sec.planning_id, "counting_unit": sec.counting_unit}),
            reason=f"Added section {sec.name}"
        )
        return sec

    @classmethod
    def update_section(
        cls,
        db: Session,
        section_id: int,
        name: str,
        category_id: int,
        display_order: int = 0,
        planning_id: Optional[int] = None,
        is_active: bool = True,
        counting_unit: str = "Pairs",
        description: Optional[str] = None,
        min_target: Optional[int] = None,
        max_target: Optional[int] = None,
        calculation_mode: Optional[str] = None,
        user_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Section:
        """
        Updates section while PRESERVING STABLE ID and HISTORICAL DATA INTEGRITY.
        Planning ID controls planning position and must be unique.
        """
        sec = db.query(Section).filter(Section.id == section_id).first()
        if not sec:
            raise ValueError("Section not found")

        # Determine target planning ID: prefer explicit planning_id, fallback to display_order, else keep existing
        target_pid = planning_id if planning_id is not None else (display_order if display_order > 0 else sec.effective_planning_id)
        if target_pid is not None:
            if target_pid <= 0:
                raise ValueError("Planning ID must be a positive integer.")
            conflict = db.query(Section).filter(
                Section.id != sec.id,
                (Section.planning_id == target_pid) |
                ((Section.planning_id == None) & (Section.display_order == target_pid))
            ).first()
            if conflict:
                raise ValueError(f"Planning ID {target_pid} is already assigned to another section. Please choose a unique ID.")

        old_state = {
            "name": sec.name,
            "category_id": sec.category_id,
            "display_order": sec.display_order,
            "planning_id": sec.planning_id or sec.display_order,
            "is_active": sec.is_active,
            "counting_unit": sec.counting_unit
        }

        sec.name = name
        sec.category_id = category_id
        if target_pid is not None:
            sec.planning_id = target_pid
            sec.display_order = target_pid
        sec.is_active = is_active
        sec.counting_unit = counting_unit or "Pairs"
        if description is not None:
            sec.description = description
        sec.updated_at = datetime.utcnow()

        # Update target setting if provided
        target_setting = db.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == section_id).first()
        if not target_setting:
            target_setting = ProductionTargetSetting(
                section_id=sec.id,
                minimum_daily_target=0,
                maximum_daily_target=0,
                unit=f"{sec.counting_unit}/day",
                is_active=is_active,
                updated_by_id=user_id,
                updated_at=datetime.utcnow()
            )
            db.add(target_setting)
        else:
            target_setting.is_active = is_active

        if min_target is not None:
            if min_target < 0:
                raise ValueError("Minimum daily target cannot be negative")
            target_setting.minimum_daily_target = min_target

        if max_target is not None:
            if max_target < 0:
                raise ValueError("Maximum daily target cannot be negative")
            target_setting.maximum_daily_target = max_target

        if calculation_mode is not None:
            target_setting.calculation_mode = calculation_mode

        # Target Validation: Minimum must not exceed Maximum if Maximum > 0
        if target_setting.maximum_daily_target > 0 and target_setting.minimum_daily_target > target_setting.maximum_daily_target:
            raise ValueError(
                f"Minimum daily target ({target_setting.minimum_daily_target}) cannot exceed maximum daily target ({target_setting.maximum_daily_target})"
            )

        target_setting.unit = f"{sec.counting_unit}/day"
        target_setting.updated_by_id = user_id
        target_setting.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(sec)

        # Count active orders affected
        affected_count = db.query(OrderRoute).join(Order).filter(
            OrderRoute.section_id == sec.id,
            Order.status.in_([OrderStatus.SCHEDULED, OrderStatus.IN_PRODUCTION, OrderStatus.AT_RISK, OrderStatus.OVERDUE])
        ).count()

        audit_action = "ACTIVATE" if (not old_state["is_active"] and is_active) else ("DEACTIVATE" if (old_state["is_active"] and not is_active) else "UPDATE")
        cls.record_audit(
            db=db,
            entity_name="Section",
            entity_id=sec.id,
            action=audit_action,
            setting_type="section",
            user_id=user_id,
            details=json.dumps({
                "stable_id": sec.id,
                "old": old_state,
                "new": {
                    "name": sec.name,
                    "category_id": sec.category_id,
                    "planning_id": sec.planning_id,
                    "display_order": sec.display_order,
                    "is_active": sec.is_active,
                    "min_target": target_setting.minimum_daily_target,
                    "max_target": target_setting.maximum_daily_target,
                    "calculation_mode": target_setting.calculation_mode,
                }
            }),
            reason=reason or f"Updated section {sec.name}",
            affected_order_count=affected_count
        )
        return sec

    @classmethod
    def reorder_sections(
        cls,
        db: Session,
        items: List[Dict[str, Any]],
        user_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> List[Section]:
        """
        Controlled batch reorder operation that updates all affected Planning IDs
        within one safe database transaction with rollback on failure.
        """
        if not items:
            return cls.get_sections(db)

        # 1. Validation: check positive integers
        for it in items:
            sec_id = it.get("section_id")
            pid = it.get("planning_id")
            if not sec_id:
                raise ValueError("Section ID is required for each reorder item.")
            if pid is None or pid <= 0:
                raise ValueError(f"Planning ID must be a positive integer (received {pid}).")

        # 2. Validation: check for duplicate IDs within the batch
        pids = [it["planning_id"] for it in items]
        if len(pids) != len(set(pids)):
            raise ValueError("Duplicate Planning IDs in reorder request. Please choose unique IDs.")

        sec_ids = [it["section_id"] for it in items]
        if len(sec_ids) != len(set(sec_ids)):
            raise ValueError("Duplicate Section IDs in reorder request.")

        # 3. Validation: all sections must exist
        sections = db.query(Section).filter(Section.id.in_(sec_ids)).all()
        if len(sections) != len(sec_ids):
            found_ids = {s.id for s in sections}
            missing = set(sec_ids) - found_ids
            raise ValueError(f"Sections not found: {missing}")

        sec_map = {s.id: s for s in sections}

        # 4. Validation: check conflicts with sections not included in the batch
        non_batch_conflicts = db.query(Section).filter(
            ~Section.id.in_(sec_ids),
            (Section.planning_id.in_(pids)) |
            ((Section.planning_id == None) & Section.display_order.in_(pids))
        ).first()
        if non_batch_conflicts:
            c_pid = non_batch_conflicts.planning_id or non_batch_conflicts.display_order
            raise ValueError(f"Planning ID {c_pid} is already assigned to another section. Please choose a unique ID.")

        # 5. Apply updates in safe transaction
        old_mapping = {}
        new_mapping = {}
        for it in items:
            s = sec_map[it["section_id"]]
            old_mapping[s.id] = {
                "name": s.name,
                "planning_id": s.planning_id or s.display_order
            }
            s.planning_id = it["planning_id"]
            s.display_order = it["planning_id"]
            s.updated_at = datetime.utcnow()
            new_mapping[s.id] = {
                "name": s.name,
                "planning_id": s.planning_id
            }

        db.commit()

        # 6. Audit log
        cls.record_audit(
            db=db,
            entity_name="Section",
            entity_id=0,
            action="REORDER",
            setting_type="section",
            user_id=user_id,
            details=json.dumps({"before": old_mapping, "after": new_mapping}),
            reason=reason or "Batch reordered sections planning IDs"
        )

        return cls.get_sections(db)

    @classmethod
    def deactivate_section(
        cls,
        db: Session,
        section_id: int,
        user_id: Optional[int] = None,
        reason: Optional[str] = None,
        force_confirm: bool = False,
        remove_from_active_workflows: bool = True
    ) -> Dict[str, Any]:
        """
        Safely deactivates a section without deleting historical production transactions.
        If section is part of active order workflows, requires explicit confirmation.
        When approved with remove_from_active_workflows=True, marks order route NOT_REQUIRED,
        re-sequences remaining active routes contiguously, and refreshes workflow plans.
        """
        sec = db.query(Section).filter(Section.id == section_id).first()
        if not sec:
            raise ValueError("Section not found")

        active_order_statuses = [
            OrderStatus.SCHEDULED,
            OrderStatus.IN_PRODUCTION,
            OrderStatus.AT_RISK,
            OrderStatus.OVERDUE,
        ]

        # Check existing orders and active workflows
        active_routes = (
            db.query(OrderRoute)
            .join(Order)
            .filter(
                OrderRoute.section_id == section_id,
                Order.status.in_(active_order_statuses),
                OrderRoute.status == SectionRouteStatus.REQUIRED
            )
            .all()
        )
        all_routes_count = db.query(OrderRoute).filter(OrderRoute.section_id == section_id).count()
        entries_count = (
            db.query(DailyProductionEntry)
            .join(OrderRoute)
            .filter(OrderRoute.section_id == section_id, DailyProductionEntry.is_reversed == False)
            .count()
        )

        affected_orders_summary = []
        for r in active_routes:
            ord_obj = r.order
            op_entries = (
                db.query(DailyProductionEntry)
                .filter(DailyProductionEntry.route_id == r.id, DailyProductionEntry.is_reversed == False)
                .all()
            )
            cum_acc = sum(e.accepted_quantity for e in op_entries)
            affected_orders_summary.append({
                "order_id": ord_obj.id,
                "order_code": ord_obj.order_code,
                "style_model": ord_obj.style_model,
                "status": ord_obj.status.value,
                "total_quantity": float(ord_obj.total_quantity),
                "recorded_quantity": float(cum_acc),
            })

        if (len(active_routes) > 0 or entries_count > 0) and not force_confirm:
            return {
                "requires_confirmation": True,
                "section_id": section_id,
                "section_name": sec.name,
                "active_orders_count": len(active_routes),
                "total_routes_count": all_routes_count,
                "production_entries_count": entries_count,
                "affected_orders": affected_orders_summary,
                "message": (
                    f"Section '{sec.name}' is used in {len(active_routes)} active order workflow(s) "
                    f"with {entries_count} production transactions. "
                    "Deactivating this section may affect active production workflows and outstanding WIP. "
                    "Please confirm whether to remove it from active order routes."
                ),
            }

        # Persist deactivation
        sec.is_active = False
        sec.updated_at = datetime.utcnow()

        target_setting = db.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == section_id).first()
        if target_setting:
            target_setting.is_active = False
            target_setting.updated_at = datetime.utcnow()

        orders_updated_count = 0
        if remove_from_active_workflows and active_routes:
            for r in active_routes:
                r.status = SectionRouteStatus.NOT_REQUIRED
                order = r.order
                # Re-sequence remaining required active routes contiguously (1, 2, 3...)
                remaining_required = [
                    rt for rt in order.routes
                    if rt.status == SectionRouteStatus.REQUIRED and rt.section and rt.section.is_active and rt.id != r.id
                ]
                remaining_required.sort(key=lambda rt: (
                    getattr(rt, "sequence_order", 0) or 0,
                    getattr(rt, "serial_no", 0) or 0,
                    rt.id
                ))
                for new_seq, rt in enumerate(remaining_required, start=1):
                    rt.serial_no = new_seq
                    rt.sequence_order = new_seq

                cls.record_audit(
                    db=db,
                    entity_name="Order",
                    entity_id=order.id,
                    action="UPDATE_WORKFLOW",
                    setting_type="workflow",
                    user_id=user_id,
                    details=json.dumps({
                        "deactivated_section_id": sec.id,
                        "deactivated_section_name": sec.name,
                        "status": "NOT_REQUIRED",
                        "remaining_active_sections": len(remaining_required),
                    }),
                    reason=reason or f"Section {sec.name} deactivated and removed from active production workflow",
                    affected_order_count=1
                )
                orders_updated_count += 1

        db.commit()

        cls.record_audit(
            db=db,
            entity_name="Section",
            entity_id=sec.id,
            action="DEACTIVATE",
            setting_type="section",
            user_id=user_id,
            details=json.dumps({
                "section_id": sec.id,
                "name": sec.name,
                "active_orders_affected": len(active_routes),
                "remove_from_active_workflows": remove_from_active_workflows,
                "orders_updated_count": orders_updated_count
            }),
            reason=reason or f"Deactivated section {sec.name}",
            affected_order_count=len(active_routes)
        )

        return {
            "requires_confirmation": False,
            "section_id": section_id,
            "section_name": sec.name,
            "is_active": False,
            "orders_updated_count": orders_updated_count,
            "message": f"Section '{sec.name}' deactivated successfully."
        }

    # -------------------------------------------------------------------------
    # 4. Automatic Target Settings
    # -------------------------------------------------------------------------
    @classmethod
    def get_section_target_settings(cls, db: Session) -> List[Dict[str, Any]]:
        sections = db.query(Section).order_by(Section.category_id, Section.display_order, Section.id).all()
        existing_map = {
            s.section_id: s for s in db.query(ProductionTargetSetting).all()
        }

        results = []
        for sec in sections:
            setting = existing_map.get(sec.id)
            if not setting:
                defaults = DEFAULT_SECTION_TARGETS.get(sec.name, {"min": 0, "max": 0, "unit": "Pairs/day", "mode": "BALANCED"})
                setting = ProductionTargetSetting(
                    section_id=sec.id,
                    minimum_daily_target=defaults.get("min", 0),
                    maximum_daily_target=defaults.get("max", 0),
                    calculation_mode=defaults.get("mode", "BALANCED"),
                    override_policy="ALLOWED",
                    unit=f"{sec.counting_unit}/day",
                    is_active=sec.is_active,
                    notes="Auto-initialized target setting",
                    updated_at=datetime.utcnow()
                )
                db.add(setting)
                db.commit()
                db.refresh(setting)
                existing_map[sec.id] = setting

            cat_name = sec.category.name if sec.category else "General"
            updater_name = setting.updated_by.full_name or setting.updated_by.username if setting.updated_by else "System"

            results.append({
                "id": setting.id,
                "section_id": sec.id,
                "section_name": sec.name,
                "category_id": sec.category_id,
                "category_name": cat_name,
                "minimum_daily_target": setting.minimum_daily_target,
                "maximum_daily_target": setting.maximum_daily_target or 0,
                "calculation_mode": setting.calculation_mode or "BALANCED",
                "override_policy": setting.override_policy or "ALLOWED",
                "unit": setting.unit or f"{sec.counting_unit}/day",
                "is_active": setting.is_active and sec.is_active,
                "notes": setting.notes,
                "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
                "updated_by_id": setting.updated_by_id,
                "updated_by_username": updater_name
            })
        return results

    @classmethod
    def update_section_target_setting(
        cls,
        db: Session,
        section_id: int,
        min_target: int,
        max_target: int = 0,
        unit: str = "Pairs/day",
        calculation_mode: str = "BALANCED",
        override_policy: str = "ALLOWED",
        is_active: bool = True,
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates and updates section target settings.
        Validations:
        - min_target >= 0
        - max_target >= 0
        - If max_target > 0, min_target <= max_target
        """
        if min_target < 0:
            raise ValueError("Minimum daily target cannot be negative")
        if max_target < 0:
            raise ValueError("Maximum daily target cannot be negative")
        if max_target > 0 and min_target > max_target:
            raise ValueError(
                f"Minimum daily target ({min_target:,}) cannot exceed Maximum daily target ({max_target:,})"
            )

        sec = db.query(Section).filter(Section.id == section_id).first()
        if not sec:
            raise ValueError("Section not found")

        setting = db.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == section_id).first()
        old_min = setting.minimum_daily_target if setting else 0
        old_max = setting.maximum_daily_target if setting else 0

        if not setting:
            setting = ProductionTargetSetting(
                section_id=section_id,
                minimum_daily_target=min_target,
                maximum_daily_target=max_target,
                unit=unit,
                calculation_mode=calculation_mode,
                override_policy=override_policy,
                is_active=is_active,
                notes=notes,
                updated_by_id=user_id,
                updated_at=datetime.utcnow()
            )
            db.add(setting)
        else:
            setting.minimum_daily_target = min_target
            setting.maximum_daily_target = max_target
            setting.unit = unit
            setting.calculation_mode = calculation_mode
            setting.override_policy = override_policy
            setting.is_active = is_active
            if notes is not None:
                setting.notes = notes
            setting.updated_by_id = user_id
            setting.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(setting)

        # Count active orders affected
        affected_count = db.query(OrderRoute).join(Order).filter(
            OrderRoute.section_id == sec.id,
            Order.status.in_([OrderStatus.SCHEDULED, OrderStatus.IN_PRODUCTION, OrderStatus.AT_RISK, OrderStatus.OVERDUE])
        ).count()

        cls.record_audit(
            db=db,
            entity_name="ProductionTargetSetting",
            entity_id=setting.id,
            action="UPDATE",
            setting_type="target",
            user_id=user_id,
            details=json.dumps({
                "section_id": sec.id,
                "section_name": sec.name,
                "old_min": old_min,
                "new_min": min_target,
                "old_max": old_max,
                "new_max": max_target,
                "calculation_mode": calculation_mode
            }),
            reason=reason or f"Updated target limits for {sec.name}",
            affected_order_count=affected_count
        )

        cat_name = sec.category.name if sec.category else "General"
        updater_name = setting.updated_by.username if setting.updated_by else "System"

        return {
            "id": setting.id,
            "section_id": sec.id,
            "section_name": sec.name,
            "category_id": sec.category_id,
            "category_name": cat_name,
            "minimum_daily_target": setting.minimum_daily_target,
            "maximum_daily_target": setting.maximum_daily_target,
            "calculation_mode": setting.calculation_mode,
            "override_policy": setting.override_policy,
            "unit": setting.unit,
            "is_active": setting.is_active,
            "notes": setting.notes,
            "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
            "updated_by_id": setting.updated_by_id,
            "updated_by_username": updater_name,
            "affected_orders": affected_count
        }

    # -------------------------------------------------------------------------
    # 10. Factory Calendar Settings
    # -------------------------------------------------------------------------
    @classmethod
    def get_factory_calendar(cls, db: Session) -> Dict[str, Any]:
        cal = db.query(FactoryCalendar).filter(FactoryCalendar.is_default == True).first()
        if not cal:
            cal = db.query(FactoryCalendar).first()
        if not cal:
            cal = FactoryCalendar(
                name="Standard Bangladesh Factory Calendar",
                is_default=True,
                work_monday=True,
                work_tuesday=True,
                work_wednesday=True,
                work_thursday=True,
                work_friday=False,  # Bangladesh weekend
                work_saturday=True,
                work_sunday=True,
                cutoff_hour=18,
                cutoff_minute=0,
                timezone="Asia/Dhaka",
                created_at=datetime.utcnow()
            )
            db.add(cal)
            db.commit()
            db.refresh(cal)

        exceptions = db.query(CalendarException).filter(
            CalendarException.calendar_id == cal.id
        ).order_by(CalendarException.exception_date.asc()).all()

        return {
            "id": cal.id,
            "name": cal.name,
            "is_default": cal.is_default,
            "work_monday": cal.work_monday,
            "work_tuesday": cal.work_tuesday,
            "work_wednesday": cal.work_wednesday,
            "work_thursday": cal.work_thursday,
            "work_friday": cal.work_friday,
            "work_saturday": cal.work_saturday,
            "work_sunday": cal.work_sunday,
            "cutoff_hour": cal.cutoff_hour,
            "cutoff_minute": cal.cutoff_minute,
            "timezone": cal.timezone,
            "exceptions": [
                {
                    "id": ex.id,
                    "exception_date": str(ex.exception_date),
                    "exception_type": ex.exception_type.value if hasattr(ex.exception_type, "value") else str(ex.exception_type),
                    "description": ex.description
                }
                for ex in exceptions
            ]
        }

    # -------------------------------------------------------------------------
    # 11-15. General, WIP, Entry, Validation, Reports Settings
    # -------------------------------------------------------------------------
    @classmethod
    def get_group_settings(cls, db: Session, group_prefix: str) -> Dict[str, Any]:
        cls.initialize_defaults(db)
        settings = db.query(SystemSetting).filter(SystemSetting.category == group_prefix).all()
        result = {}
        for s in settings:
            field_name = s.key.split(".", 1)[-1]
            if s.data_type == "boolean":
                val = s.value.strip().lower() in ("true", "1", "yes")
            elif s.data_type == "integer":
                try:
                    val = int(s.value)
                except ValueError:
                    val = 0
            elif s.data_type == "json":
                try:
                    val = json.loads(s.value)
                except Exception:
                    val = s.value
            else:
                val = s.value
            result[field_name] = val
        return result

    @classmethod
    def update_group_settings(cls, db: Session, group_prefix: str, data: Dict[str, Any], user_id: Optional[int] = None, reason: Optional[str] = None) -> Dict[str, Any]:
        for k, v in data.items():
            if k == "reason":
                continue
            key = f"{group_prefix}.{k}"
            cls.set_setting_value(db, key, v, user_id=user_id, reason=reason)
        return cls.get_group_settings(db, group_prefix)

    # -------------------------------------------------------------------------
    # 16. User & Permissions Management
    # -------------------------------------------------------------------------
    @classmethod
    def get_users_with_roles(cls, db: Session) -> List[Dict[str, Any]]:
        users = db.query(User).order_by(User.id).all()
        return [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "email": u.email,
                "role": u.role.value if hasattr(u.role, "value") else str(u.role),
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "updated_at": u.updated_at.isoformat() if u.updated_at else None
            }
            for u in users
        ]

    @classmethod
    def update_user_role(cls, db: Session, target_user_id: int, new_role: UserRole, is_active: Optional[bool] = None, user_id: Optional[int] = None, reason: Optional[str] = None):
        user = db.query(User).filter(User.id == target_user_id).first()
        if not user:
            raise ValueError("User not found")

        old_role = user.role.value if hasattr(user.role, "value") else str(user.role)
        user.role = new_role
        if is_active is not None:
            user.is_active = is_active
        user.updated_at = datetime.utcnow()
        db.commit()

        cls.record_audit(
            db=db,
            entity_name="User",
            entity_id=user.id,
            action="ROLE_CHANGE",
            setting_type="permissions",
            user_id=user_id,
            details=json.dumps({"username": user.username, "old_role": old_role, "new_role": new_role.value}),
            reason=reason or f"Changed role of user {user.username} to {new_role.value}"
        )
        return user

    # -------------------------------------------------------------------------
    # 18. Impact Check & Recalculation
    # -------------------------------------------------------------------------
    @classmethod
    def check_impact(cls, db: Session, setting_type: str, entity_id: Optional[int] = None, new_value: Optional[Any] = None) -> Dict[str, Any]:
        """
        Calculates the number and list of active orders that may be affected by a setting change.
        """
        active_statuses = [OrderStatus.SCHEDULED, OrderStatus.IN_PRODUCTION, OrderStatus.AT_RISK, OrderStatus.OVERDUE]
        query = db.query(Order).filter(Order.status.in_(active_statuses))

        if setting_type in ("section", "target") and entity_id:
            query = query.join(OrderRoute).filter(OrderRoute.section_id == entity_id)

        orders = query.all()
        affected_count = len(orders)
        order_list = [{"id": o.id, "order_code": o.order_code, "customer_ref": o.customer_ref, "quantity": o.total_quantity} for o in orders[:20]]

        msg = f"Changing this setting affects {affected_count} active orders in production."
        return {
            "setting_type": setting_type,
            "entity_id": entity_id,
            "affected_order_count": affected_count,
            "affected_orders": order_list,
            "message": msg
        }

    @classmethod
    def recalculate_affected_plans(cls, db: Session, setting_type: str, entity_id: Optional[int] = None, user_id: Optional[int] = None, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Recalculates affected active orders in a controlled, auditable manner.
        """
        active_statuses = [OrderStatus.SCHEDULED, OrderStatus.IN_PRODUCTION, OrderStatus.AT_RISK, OrderStatus.OVERDUE]
        query = db.query(Order).filter(Order.status.in_(active_statuses))

        if setting_type in ("section", "target") and entity_id:
            query = query.join(OrderRoute).filter(OrderRoute.section_id == entity_id)

        orders = query.all()
        recalculated_count = 0

        # Touch/refresh order updated timestamps to invalidate caches and trigger recalculation
        for o in orders:
            o.updated_at = datetime.utcnow()
            recalculated_count += 1
        db.commit()

        cls.record_audit(
            db=db,
            entity_name="PlanningEngine",
            entity_id=entity_id,
            action="RECALCULATE",
            setting_type=setting_type,
            user_id=user_id,
            details=json.dumps({"recalculated_count": recalculated_count, "setting_type": setting_type}),
            reason=reason or f"Triggered plan recalculation due to {setting_type} setting update",
            affected_order_count=recalculated_count,
            recalculation_status="SUCCESS"
        )

        return {
            "status": "SUCCESS",
            "recalculated_order_count": recalculated_count,
            "message": f"Successfully recalculated planning schedules for {recalculated_count} active orders.",
            "timestamp": datetime.utcnow()
        }
