import io
import csv
import json
import time
import openpyxl
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect

from app.database import get_db, engine
from app.config import settings as app_settings
from app.models.user import User, UserRole
from app.models.route import Category, Section, ProductionTargetSetting, OrderRoute
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.models.buyer import Buyer
from app.models.order import Order
from app.models.entry import DailyProductionEntry
from app.models.audit import AuditLog
from app.api.deps import get_current_user, require_roles
from app.services.settings_service import SettingsService
from app.services.calendar_service import CalendarService
from app.services.production_planning_service import ProductionPlanningService
from app.services.wip_planning_engine import WIPPlanningEngine
from app.schemas.route import (
    CategoryOut, SectionOut, ProductionTargetSettingOut, ProductionTargetSettingUpdate
)
from app.schemas.calendar import (
    CalendarExceptionCreate, CalendarExceptionOut, FactoryCalendarUpdate
)
from app.schemas.settings import (
    CategorySettingsUpdate, SectionSettingsUpdate, SectionDeactivateRequest, SectionReorderRequest,
    GeneralSettingsUpdate, WipSettingsUpdate, ProductionEntrySettingsUpdate,
    PlanningValidationSettingsUpdate, ReportExportSettingsUpdate, UserRoleUpdate,
    ImpactCheckRequest, ImpactCheckResponse, RecalculateRequest, RecalculateResponse
)

router = APIRouter(prefix="/settings", tags=["Settings & Configuration Module"])


# =============================================================================
# 1. CATEGORY & SECTION SETTINGS
# =============================================================================
@router.get("/categories")
def list_categories(
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cats = SettingsService.get_categories(db, include_inactive=include_inactive)
    return [
        {
            "id": c.id,
            "name": c.name,
            "display_order": c.display_order,
            "is_active": c.is_active,
            "description": c.description,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "section_count": len(c.sections)
        }
        for c in cats
    ]


@router.post("/categories")
def create_category(
    cat_in: CategorySettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    try:
        cat = SettingsService.create_category(
            db=db,
            name=cat_in.name,
            display_order=cat_in.display_order,
            is_active=cat_in.is_active,
            description=cat_in.description,
            user_id=current_user.id
        )
        return {
            "id": cat.id,
            "name": cat.name,
            "display_order": cat.display_order,
            "is_active": cat.is_active,
            "description": cat.description,
            "updated_at": cat.updated_at.isoformat() if cat.updated_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/categories/{category_id}")
def update_category(
    category_id: int,
    cat_in: CategorySettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    try:
        cat = SettingsService.update_category(
            db=db,
            category_id=category_id,
            name=cat_in.name,
            display_order=cat_in.display_order,
            is_active=cat_in.is_active,
            description=cat_in.description,
            user_id=current_user.id,
            reason=cat_in.reason
        )
        return {
            "id": cat.id,
            "name": cat.name,
            "display_order": cat.display_order,
            "is_active": cat.is_active,
            "description": cat.description,
            "updated_at": cat.updated_at.isoformat() if cat.updated_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sections")
def list_sections(
    category_id: Optional[int] = None,
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    secs = SettingsService.get_sections(db, category_id=category_id, include_inactive=include_inactive)
    target_settings = {s.section_id: s for s in db.query(ProductionTargetSetting).all()}

    results = []
    for s in secs:
        ts = target_settings.get(s.id)
        pid = s.planning_id or s.display_order or s.id
        results.append({
            "id": s.id,
            "category_id": s.category_id,
            "category_name": s.category.name if s.category else "General",
            "name": s.name,
            "display_order": s.display_order,
            "planning_id": pid,
            "is_active": s.is_active,
            "counting_unit": s.counting_unit or "Pairs",
            "description": s.description,
            "minimum_daily_target": ts.minimum_daily_target if ts else 0,
            "maximum_daily_target": ts.maximum_daily_target if ts else 0,
            "calculation_mode": ts.calculation_mode if ts else "BALANCED",
            "updated_at": s.updated_at.isoformat() if s.updated_at else None
        })
    return results


@router.post("/sections")
def create_section(
    sec_in: SectionSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    try:
        sec = SettingsService.create_section(
            db=db,
            category_id=sec_in.category_id,
            name=sec_in.name,
            display_order=sec_in.display_order,
            planning_id=sec_in.planning_id,
            is_active=sec_in.is_active,
            counting_unit=sec_in.counting_unit,
            description=sec_in.description,
            min_target=sec_in.minimum_daily_target,
            max_target=sec_in.maximum_daily_target,
            calculation_mode=sec_in.calculation_mode,
            user_id=current_user.id
        )
        return {
            "id": sec.id,
            "category_id": sec.category_id,
            "name": sec.name,
            "display_order": sec.display_order,
            "planning_id": sec.planning_id or sec.display_order,
            "is_active": sec.is_active,
            "counting_unit": sec.counting_unit,
            "description": sec.description,
            "updated_at": sec.updated_at.isoformat() if sec.updated_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/sections/reorder")
def reorder_sections(
    req: SectionReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    try:
        updated_secs = SettingsService.reorder_sections(
            db=db,
            items=[item.model_dump() for item in req.items],
            user_id=current_user.id,
            reason=req.reason
        )
        target_settings = {s.section_id: s for s in db.query(ProductionTargetSetting).all()}
        return [
            {
                "id": s.id,
                "category_id": s.category_id,
                "category_name": s.category.name if s.category else "General",
                "name": s.name,
                "display_order": s.display_order,
                "planning_id": s.planning_id or s.display_order,
                "is_active": s.is_active,
                "counting_unit": s.counting_unit or "Pairs",
                "description": s.description,
                "minimum_daily_target": target_settings.get(s.id).minimum_daily_target if target_settings.get(s.id) else 0,
                "maximum_daily_target": target_settings.get(s.id).maximum_daily_target if target_settings.get(s.id) else 0,
                "calculation_mode": target_settings.get(s.id).calculation_mode if target_settings.get(s.id) else "BALANCED",
                "updated_at": s.updated_at.isoformat() if s.updated_at else None
            }
            for s in updated_secs
        ]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/sections/{section_id}")
def update_section(
    section_id: int,
    sec_in: SectionSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    try:
        sec = SettingsService.update_section(
            db=db,
            section_id=section_id,
            name=sec_in.name,
            category_id=sec_in.category_id,
            display_order=sec_in.display_order,
            planning_id=sec_in.planning_id,
            is_active=sec_in.is_active,
            counting_unit=sec_in.counting_unit,
            description=sec_in.description,
            min_target=sec_in.minimum_daily_target,
            max_target=sec_in.maximum_daily_target,
            calculation_mode=sec_in.calculation_mode,
            user_id=current_user.id,
            reason=sec_in.reason
        )
        ts = db.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == section_id).first()
        return {
            "id": sec.id,
            "category_id": sec.category_id,
            "category_name": sec.category.name if sec.category else "General",
            "name": sec.name,
            "display_order": sec.display_order,
            "planning_id": sec.planning_id or sec.display_order,
            "is_active": sec.is_active,
            "counting_unit": sec.counting_unit,
            "description": sec.description,
            "minimum_daily_target": ts.minimum_daily_target if ts else 0,
            "maximum_daily_target": ts.maximum_daily_target if ts else 0,
            "calculation_mode": ts.calculation_mode if ts else "BALANCED",
            "updated_at": sec.updated_at.isoformat() if sec.updated_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sections/{section_id}/deactivate")
def deactivate_section(
    section_id: int,
    req: SectionDeactivateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    try:
        res = SettingsService.deactivate_section(
            db=db,
            section_id=section_id,
            user_id=current_user.id,
            reason=req.reason,
            force_confirm=req.force_confirm,
            remove_from_active_workflows=req.remove_from_active_workflows
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# 2. AUTOMATIC TARGET SETTINGS
# =============================================================================
@router.get("/target-settings")
def get_target_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return SettingsService.get_section_target_settings(db)


@router.put("/target-settings/{section_id}")
def update_target_setting(
    section_id: int,
    setting_in: ProductionTargetSettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    try:
        sec_id = section_id or setting_in.section_id
        if not sec_id:
            raise HTTPException(status_code=400, detail="Section ID is required")
        res = SettingsService.update_section_target_setting(
            db=db,
            section_id=sec_id,
            min_target=setting_in.minimum_daily_target,
            max_target=setting_in.maximum_daily_target or 0,
            unit=setting_in.unit or "Pairs/day",
            calculation_mode=setting_in.calculation_mode or "BALANCED",
            override_policy=setting_in.override_policy or "ALLOWED",
            is_active=setting_in.is_active,
            notes=setting_in.notes,
            user_id=current_user.id,
            reason="Updated target limits"
        )
        res["saved"] = True
        return res
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# 3. FACTORY CALENDAR
# =============================================================================
@router.get("/calendar")
def get_factory_calendar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return SettingsService.get_factory_calendar(db)


@router.put("/calendar")
def update_factory_calendar(
    cal_in: FactoryCalendarUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    cal = CalendarService.get_active_calendar(db)
    for field, val in cal_in.model_dump(exclude_unset=True).items():
        setattr(cal, field, val)
    cal.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cal)

    SettingsService.record_audit(
        db=db,
        entity_name="FactoryCalendar",
        entity_id=cal.id,
        action="UPDATE",
        setting_type="calendar",
        user_id=current_user.id,
        details=json.dumps({"name": cal.name, "work_friday": cal.work_friday, "cutoff": f"{cal.cutoff_hour}:{cal.cutoff_minute}"}),
        reason="Updated factory working-day rules"
    )
    return SettingsService.get_factory_calendar(db)


@router.post("/calendar/exceptions", response_model=CalendarExceptionOut)
def add_calendar_exception(
    ex_in: CalendarExceptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    cal = CalendarService.get_active_calendar(db)
    existing = db.query(CalendarException).filter(
        CalendarException.calendar_id == cal.id,
        CalendarException.exception_date == ex_in.exception_date
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="An exception on this date already exists")

    ex = CalendarException(calendar_id=cal.id, **ex_in.model_dump())
    db.add(ex)
    db.commit()
    db.refresh(ex)

    SettingsService.record_audit(
        db=db,
        entity_name="CalendarException",
        entity_id=ex.id,
        action="CREATE",
        setting_type="calendar",
        user_id=current_user.id,
        details=json.dumps({"date": str(ex.exception_date), "type": str(ex.exception_type), "description": ex.description}),
        reason=f"Added calendar exception for {ex.exception_date}"
    )
    return ex


@router.put("/calendar/exceptions/{exception_id}", response_model=CalendarExceptionOut)
def update_calendar_exception(
    exception_id: int,
    ex_in: CalendarExceptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    ex = db.query(CalendarException).filter(CalendarException.id == exception_id).first()
    if not ex:
        raise HTTPException(status_code=404, detail="Exception not found")

    ex.exception_date = ex_in.exception_date
    ex.exception_type = ex_in.exception_type
    ex.description = ex_in.description
    db.commit()
    db.refresh(ex)

    SettingsService.record_audit(
        db=db,
        entity_name="CalendarException",
        entity_id=ex.id,
        action="UPDATE",
        setting_type="calendar",
        user_id=current_user.id,
        details=json.dumps({"date": str(ex.exception_date), "type": str(ex.exception_type), "description": ex.description}),
        reason=f"Updated calendar exception on {ex.exception_date}"
    )
    return ex


@router.delete("/calendar/exceptions/{exception_id}")
def delete_calendar_exception(
    exception_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    ex = db.query(CalendarException).filter(CalendarException.id == exception_id).first()
    if not ex:
        raise HTTPException(status_code=404, detail="Exception not found")

    db.delete(ex)
    db.commit()

    SettingsService.record_audit(
        db=db,
        entity_name="CalendarException",
        entity_id=exception_id,
        action="DELETE",
        setting_type="calendar",
        user_id=current_user.id,
        details=json.dumps({"date": str(ex.exception_date)}),
        reason="Removed factory holiday / exception"
    )
    return {"detail": "Calendar exception removed successfully"}


# =============================================================================
# 4. WIP & WORKFLOW SETTINGS
# =============================================================================
@router.get("/wip")
def get_wip_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return SettingsService.get_group_settings(db, "wip")


@router.put("/wip")
def update_wip_settings(
    wip_in: WipSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    data = wip_in.model_dump()
    reason = data.pop("reason", None)
    return SettingsService.update_group_settings(db, "wip", data, user_id=current_user.id, reason=reason)


# =============================================================================
# 5. PRODUCTION ENTRY SETTINGS
# =============================================================================
@router.get("/production-entry")
def get_production_entry_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return SettingsService.get_group_settings(db, "entry")


@router.put("/production-entry")
def update_production_entry_settings(
    entry_in: ProductionEntrySettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    data = entry_in.model_dump()
    reason = data.pop("reason", None)
    return SettingsService.update_group_settings(db, "entry", data, user_id=current_user.id, reason=reason)


# =============================================================================
# 6. GENERAL ERP SETTINGS
# =============================================================================
@router.get("/general")
def get_general_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return SettingsService.get_group_settings(db, "general")


@router.put("/general")
def update_general_settings(
    gen_in: GeneralSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    data = gen_in.model_dump()
    reason = data.pop("reason", None)
    return SettingsService.update_group_settings(db, "general", data, user_id=current_user.id, reason=reason)


# =============================================================================
# 7. PLANNING VALIDATION SETTINGS
# =============================================================================
@router.get("/planning-validation")
def get_planning_validation_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return SettingsService.get_group_settings(db, "validation")


@router.put("/planning-validation")
def update_planning_validation_settings(
    val_in: PlanningValidationSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    data = val_in.model_dump()
    reason = data.pop("reason", None)
    return SettingsService.update_group_settings(db, "validation", data, user_id=current_user.id, reason=reason)


# =============================================================================
# 8. REPORTS & EXPORT SETTINGS
# =============================================================================
@router.get("/reports")
def get_report_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return SettingsService.get_group_settings(db, "export")


@router.put("/reports")
def update_report_settings(
    rep_in: ReportExportSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    data = rep_in.model_dump()
    reason = data.pop("reason", None)
    return SettingsService.update_group_settings(db, "export", data, user_id=current_user.id, reason=reason)


# =============================================================================
# 9. USER ROLES & SETTINGS PERMISSIONS
# =============================================================================
@router.get("/permissions/users")
def get_users_and_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    return SettingsService.get_users_with_roles(db)


@router.put("/permissions/users/{target_user_id}")
def update_user_role(
    target_user_id: int,
    role_in: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    try:
        user = SettingsService.update_user_role(
            db=db,
            target_user_id=target_user_id,
            new_role=role_in.role,
            is_active=role_in.is_active,
            user_id=current_user.id,
            reason=role_in.reason
        )
        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "is_active": user.is_active,
            "message": "User permissions updated successfully."
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# 10. AUDIT HISTORY
# =============================================================================
@router.get("/audit")
def get_audit_history(
    setting_type: Optional[str] = None,
    entity_name: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    query = db.query(AuditLog)
    if setting_type:
        query = query.filter(AuditLog.setting_type == setting_type)
    if entity_name:
        query = query.filter(AuditLog.entity_name == entity_name)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "entity_name": l.entity_name,
            "entity_id": l.entity_id,
            "action": l.action,
            "setting_type": l.setting_type or "general",
            "user_id": l.user_id,
            "user_name": l.user.full_name if l.user else (l.user.username if l.user else "System"),
            "timestamp": l.timestamp.isoformat(),
            "details": l.details,
            "reason": l.reason,
            "affected_order_count": l.affected_order_count or 0,
            "recalculation_status": l.recalculation_status
        }
        for l in logs
    ]


# =============================================================================
# 11. SYSTEM DIAGNOSTICS (Comprehensive 10-Subsystem Health Probe)
# =============================================================================
@router.get("/diagnostics")
@router.post("/diagnostics/run")
def run_diagnostics(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    diagnostics = []
    overall_status = "PASS"

    def probe(name: str, check_fn):
        nonlocal overall_status
        t0 = time.time()
        try:
            msg = check_fn()
            latency = round((time.time() - t0) * 1000, 2)
            diagnostics.append({
                "subsystem": name,
                "status": "PASS",
                "connected": True,
                "last_checked": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                "details": msg or "Connected & Healthy",
                "latency_ms": latency,
                "error": None
            })
        except Exception as exc:
            overall_status = "FAIL"
            latency = round((time.time() - t0) * 1000, 2)
            diagnostics.append({
                "subsystem": name,
                "status": "FAIL",
                "connected": False,
                "last_checked": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                "details": "Subsystem failure detected",
                "latency_ms": latency,
                "error": str(exc)
            })

    # 1. Backend API
    probe("Backend API", lambda: f"FastAPI Server operational (v{app_settings.VERSION})")

    # 2. Database connection
    def check_db():
        db.execute(text("SELECT 1"))
        insp = inspect(engine)
        table_count = len(insp.get_table_names())
        return f"Connected ({engine.dialect.name}), {table_count} tables verified"
    probe("Database Connection", check_db)

    # 3. Buyer API
    def check_buyers():
        c = db.query(Buyer).count()
        return f"Operational — {c} registered buyers"
    probe("Buyer API", check_buyers)

    # 4. Order API
    def check_orders():
        c = db.query(Order).count()
        return f"Operational — {c} active orders managed"
    probe("Order API", check_orders)

    # 5. Original Production Planning API
    def check_planning_matrix():
        first_order = db.query(Order).first()
        if first_order:
            ProductionPlanningService.generate_order_matrix_planning_sheet(db, first_order.id)
            return "Planning matrix engine verified and functioning"
        return "Operational — no test orders in database"
    probe("Original Production Planning API", check_planning_matrix)

    # 6. WIP Flow Planning API
    def check_wip_flow():
        first_order = db.query(Order).first()
        if first_order:
            WIPPlanningEngine.calculate_order_wip_flow(db, first_order.id)
            return "WIP serial flow simulation engine operational"
        return "Operational — no test orders in database"
    probe("WIP Flow Planning API", check_wip_flow)

    # 7. Factory Calendar API
    def check_calendar():
        cal = CalendarService.get_active_calendar(db)
        is_today_work = CalendarService.is_working_day(date.today(), cal, cal.exceptions)
        return f"Active calendar: {cal.name} ({cal.timezone}). Today workday: {is_today_work}"
    probe("Factory Calendar API", check_calendar)

    # 8. Production Entry API
    def check_production():
        c = db.query(DailyProductionEntry).count()
        return f"Daily entry service verified ({c} entries logged)"
    probe("Production Entry API", check_production)

    # 9. XLSX export
    def check_xlsx():
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Test"
        ws["A1"] = "Footwear ERP Export Diagnostic"
        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        assert len(out.getvalue()) > 0
        return "openpyxl XLSX generator operational"
    probe("XLSX Export", check_xlsx)

    # 10. CSV export
    def check_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Section", "Minimum", "Maximum", "Unit"])
        writer.writerow(["Cutting", 2000, 4000, "Pairs/day"])
        assert len(buf.getvalue()) > 0
        return "CSV stream generator operational"
    probe("CSV Export", check_csv)

    return {
        "overall_status": overall_status,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "subsystems": diagnostics
    }


# =============================================================================
# 12. IMPACT CHECK & CONTROLLED RECALCULATION
# =============================================================================
@router.post("/impact-check", response_model=ImpactCheckResponse)
def check_settings_impact(
    req: ImpactCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    res = SettingsService.check_impact(
        db=db,
        setting_type=req.setting_type,
        entity_id=req.entity_id,
        new_value=req.new_value
    )
    return ImpactCheckResponse(**res)


@router.post("/recalculate", response_model=RecalculateResponse)
def trigger_plan_recalculation(
    req: RecalculateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    res = SettingsService.recalculate_affected_plans(
        db=db,
        setting_type=req.setting_type,
        entity_id=req.entity_id,
        user_id=current_user.id,
        reason=req.reason
    )
    return RecalculateResponse(**res)
