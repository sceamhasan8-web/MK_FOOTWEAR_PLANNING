from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.entry import DailyProductionEntry
from app.models.user import UserRole, User
from app.schemas.entry import (
    DailyProductionEntryCreate,
    DailyProductionEntryOut,
    ProductionBulkCreate,
    ProductionCorrectionCreate,
    ProductionEntryReversalCreate,
    ProductionCorrectionOut,
)
from app.api.deps import get_current_user, require_roles
from app.services.production_service import ProductionService
from app.services.production_planning_service import ProductionPlanningService

router = APIRouter(prefix="/production", tags=["Daily Production"])


@router.post("/entry", response_model=DailyProductionEntryOut)
def record_daily_production(
    entry_in: DailyProductionEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER, UserRole.SUPERVISOR]))
):
    entry = ProductionService.record_production_entry(db, entry_in, current_user.id)
    return _serialize_entry(entry, db)


@router.post("/bulk", response_model=List[DailyProductionEntryOut])
def record_bulk_production(
    bulk_in: ProductionBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER, UserRole.SUPERVISOR]))
):
    entries = ProductionService.record_bulk_production(db, bulk_in, current_user.id)
    return [_serialize_entry(e, db) for e in entries]


@router.put("/entries/{entry_id}/correct", response_model=DailyProductionEntryOut)
def correct_production_entry(
    entry_id: int,
    correction_in: ProductionCorrectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER, UserRole.SUPERVISOR]))
):
    entry = ProductionService.correct_production_entry(db, entry_id, correction_in, current_user.id)
    return _serialize_entry(entry, db)


@router.post("/entries/{entry_id}/reverse", response_model=DailyProductionEntryOut)
def reverse_production_entry(
    entry_id: int,
    reversal_in: ProductionEntryReversalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER, UserRole.SUPERVISOR]))
):
    entry = ProductionService.reverse_production_entry(db, entry_id, reversal_in, current_user.id)
    return _serialize_entry(entry, db)


@router.delete("/entries/{entry_id}", response_model=DailyProductionEntryOut)
def delete_production_entry(
    entry_id: int,
    reason: Optional[str] = Query("Cancelled by user"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER, UserRole.SUPERVISOR]))
):
    entry = ProductionService.cancel_production_entry(db, entry_id, current_user.id, reason=reason)
    return _serialize_entry(entry, db)


@router.post("/entries/{entry_id}/cancel", response_model=DailyProductionEntryOut)
def cancel_production_entry_post(
    entry_id: int,
    reversal_in: Optional[ProductionEntryReversalCreate] = None,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER, UserRole.SUPERVISOR]))
):
    cancel_reason = (reversal_in.reason if reversal_in and reversal_in.reason else reason) or "Cancelled by user"
    entry = ProductionService.cancel_production_entry(db, entry_id, current_user.id, reason=cancel_reason)
    return _serialize_entry(entry, db)


@router.get("/entries/{entry_id}", response_model=DailyProductionEntryOut)
def get_production_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    entry = db.query(DailyProductionEntry).filter(DailyProductionEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Production entry not found")
    return _serialize_entry(entry, db)


@router.get("/entries", response_model=List[DailyProductionEntryOut])
def get_production_entries(
    order_id: Optional[int] = None,
    operation_id: Optional[int] = None,
    entry_date: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    include_reversed: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(DailyProductionEntry)
    if order_id:
        query = query.filter(DailyProductionEntry.order_id == order_id)
    if operation_id:
        query = query.filter(DailyProductionEntry.operation_id == operation_id)
    if entry_date:
        query = query.filter(DailyProductionEntry.entry_date == entry_date)
    if start_date:
        query = query.filter(DailyProductionEntry.entry_date >= start_date)
    if end_date:
        query = query.filter(DailyProductionEntry.entry_date <= end_date)
    if not include_reversed:
        query = query.filter(DailyProductionEntry.is_reversed == False)

    entries = query.order_by(DailyProductionEntry.entry_date.desc(), DailyProductionEntry.id.desc()).all()
    return [_serialize_entry(e, db) for e in entries]


def _serialize_entry(e: DailyProductionEntry, db: Optional[Session] = None) -> DailyProductionEntryOut:
    corrections_data = [
        ProductionCorrectionOut(
            id=c.id,
            entry_id=c.entry_id,
            original_accepted_qty=c.original_accepted_qty,
            new_accepted_qty=c.new_accepted_qty,
            original_rejected_qty=c.original_rejected_qty,
            new_rejected_qty=c.new_rejected_qty,
            action_type=c.action_type,
            reason=c.reason,
            authorized_by_id=c.authorized_by_id,
            authorized_by_name=c.authorized_by_user.full_name if c.authorized_by_user else None,
            created_at=c.created_at,
        )
        for c in e.corrections
    ]

    updated_bal = None
    updated_tgt = None
    rem_days = None
    avail_oh = None
    exec_tgt = None

    if db and e.operation and e.order:
        rem_days, _ = ProductionPlanningService.calculate_remaining_days(
            db, e.order.production_start_date, e.order.current_delivery_date
        )
        valid_entries = db.query(DailyProductionEntry).filter(
            DailyProductionEntry.operation_id == e.operation_id,
            DailyProductionEntry.is_reversed == False
        ).all()
        cum_acc = sum(x.accepted_quantity for x in valid_entries)
        updated_bal = ProductionPlanningService.calculate_balance(e.operation.required_quantity, cum_acc)
        updated_tgt = ProductionPlanningService.calculate_daily_target(updated_bal, rem_days)
        avail_oh = ProductionPlanningService.get_available_on_hand_for_operation(db, e.operation)
        exec_tgt = min(updated_tgt, avail_oh)

    return DailyProductionEntryOut(
        id=e.id,
        entry_date=e.entry_date,
        order_id=e.order_id,
        order_code=e.order.order_code if e.order else None,
        customer_ref=e.order.customer_ref if e.order else None,
        buyer_name=e.order.buyer.name if (e.order and e.order.buyer) else None,
        route_id=e.route_id,
        section_name=e.route.section.name if (e.route and e.route.section) else None,
        operation_id=e.operation_id,
        operation_name=e.operation.operation_name if e.operation else None,
        component_id=e.component_id,
        component_name=e.component.component_name if e.component else None,
        quantity=e.quantity,
        accepted_quantity=e.accepted_quantity,
        rejected_quantity=e.rejected_quantity,
        unit=e.unit,
        remarks=e.remarks,
        entered_by_id=e.entered_by_id,
        entered_by_name=e.entered_by_user.full_name if e.entered_by_user else None,
        created_at=e.created_at,
        is_reversed=e.is_reversed,
        is_override=e.is_override,
        updated_balance=updated_bal,
        updated_daily_target=updated_tgt,
        remaining_days=rem_days,
        available_on_hand=avail_oh,
        executable_target=exec_tgt,
        corrections=corrections_data,
    )
