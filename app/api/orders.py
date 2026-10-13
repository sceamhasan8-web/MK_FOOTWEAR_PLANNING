from typing import List, Optional
from datetime import date
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus, OrderPriority, DeliveryDateRevision
from app.models.route import OrderRoute, OrderOperation, SectionRouteStatus
from app.models.user import UserRole, User
from app.schemas.order import (
    OrderCreate,
    OrderUpdate,
    OrderOut,
    OrderDetailOut,
    DeliveryRevisionCreate,
    DeliveryRevisionOut,
    OrderDependencyCheckOut,
    OrderArchiveRequest,
)
from app.schemas.dashboard import DailySchedulePlanOut, DailyScheduleRow
from app.api.deps import get_current_user, require_roles
from app.services.order_service import OrderService
from app.services.calendar_service import CalendarService
from app.services.calculation_engine import CalculationEngine
from app.services.production_planning_service import ProductionPlanningService
from app.models.entry import DailyProductionEntry
from app.models.wip_adjustment import WipAdjustment
from app.models.audit import AuditLog
from app.services.wip_planning_engine import WIPPlanningEngine
from app.schemas.planning import (
    PlanningSheetRowOut,
    OrderCategoryFlowOut,
    CategoryFlowItemOut,
    OrderMatrixPlanningOut,
    WipFlowPlanResponse,
    WipAdjustmentCreate,
    WipAdjustmentOut,
)


router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("", response_model=List[OrderOut])
def get_orders(
    buyer_id: Optional[int] = None,
    order_status: Optional[OrderStatus] = None,
    priority: Optional[OrderPriority] = None,
    search: Optional[str] = None,
    start_date: Optional[date] = None,
    delivery_date: Optional[date] = None,
    include_archived: bool = Query(False),
    limit: Optional[int] = Query(None, ge=1, le=1000),
    offset: Optional[int] = Query(None, ge=0),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Order)
    if buyer_id:
        query = query.filter(Order.buyer_id == buyer_id)
    if order_status:
        query = query.filter(Order.status == order_status)
    elif not include_archived:
        query = query.filter(
            Order.is_archived == False,
            Order.status.notin_([OrderStatus.ARCHIVED, OrderStatus.CANCELLED])
        )
    if priority:
        query = query.filter(Order.priority == priority)
    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Order.order_code.ilike(search_term),
                Order.customer_ref.ilike(search_term),
                Order.style_model.ilike(search_term),
                Order.po_number.ilike(search_term),
                Order.description.ilike(search_term),
                Order.buyer.has(
                    or_(
                        Buyer.name.ilike(search_term),
                        Buyer.buyer_code.ilike(search_term)
                    )
                ),
            )
        )
    if start_date:
        query = query.filter(Order.production_start_date >= start_date)
    if delivery_date:
        query = query.filter(Order.current_delivery_date <= delivery_date)

    # Ordering: shipment date ascending, then ID descending
    query = query.order_by(Order.current_delivery_date.asc(), Order.id.desc())

    if page is not None and page_size is not None:
        offset = (page - 1) * page_size
        limit = page_size

    if offset is not None:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    orders = query.all()
    results = []
    for o in orders:
        details = OrderService.get_order_calculated_details(db, o)
        # Exclude detailed route structures for summary list
        results.append(OrderOut(**details))
    return results


@router.post("", response_model=OrderDetailOut)
def create_order(
    order_in: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    order = OrderService.create_order(db, order_in, current_user.id)
    details = OrderService.get_order_calculated_details(db, order)
    return OrderDetailOut(**details)


@router.get("/wip-flow-plan", response_model=Optional[WipFlowPlanResponse])
def get_active_order_wip_flow_plan(
    order_id: Optional[int] = None,
    buyer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns the dynamic Serial WIP Flow Planning Sheet for an order.
    If order_id is not provided, selects the first active order.
    """
    target_order_id = order_id
    if not target_order_id:
        query = db.query(Order).filter(
            Order.is_archived == False,
            Order.status.notin_([OrderStatus.CLOSED, OrderStatus.PRODUCTION_COMPLETE, OrderStatus.ARCHIVED, OrderStatus.CANCELLED])
        )
        if buyer_id:
            query = query.filter(Order.buyer_id == buyer_id)
        first_order = query.order_by(Order.current_delivery_date.asc(), Order.id.asc()).first()
        if not first_order:
            return None
        target_order = first_order
    else:
        target_order = db.query(Order).filter(Order.id == target_order_id).first()
        if not target_order:
            raise HTTPException(status_code=404, detail=f"Order {target_order_id} not found")

    plan = WIPPlanningEngine.calculate_order_wip_flow(db, target_order)
    return WipFlowPlanResponse(**plan)


@router.get("/{order_id}/wip-flow-plan", response_model=WipFlowPlanResponse)
def get_order_wip_flow_plan(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns the dynamic Serial WIP Flow Planning Sheet for a specific order.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    if order.is_archived or order.status in [OrderStatus.ARCHIVED, OrderStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Archived or cancelled orders cannot generate active WIP flow plans.")

    plan = WIPPlanningEngine.calculate_order_wip_flow(db, order)
    return WipFlowPlanResponse(**plan)


@router.post("/{order_id}/wip-adjustments", response_model=WipAdjustmentOut)
def record_wip_adjustment(
    order_id: int,
    adj_in: WipAdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    """
    Controlled stock adjustment function (Section 42 & 46).
    Normal users cannot manually edit On Hand.
    All stock adjustments require quantity, section/workflow, date, reason, user, and audit trail.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    route = db.query(OrderRoute).filter(OrderRoute.id == adj_in.workflow_id, OrderRoute.order_id == order_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Workflow route not found on this order")

    adj = WipAdjustment(
        order_id=order_id,
        workflow_id=adj_in.workflow_id,
        date=adj_in.date,
        quantity=adj_in.quantity,
        reason=adj_in.reason,
        user_id=current_user.id,
        status="APPROVED"
    )
    db.add(adj)
    db.flush()

    sec_name = route.section.name if route.section else f"Section {route.section_id}"
    audit = AuditLog(
        entity_name="WipAdjustment",
        entity_id=adj.id,
        action="CREATE",
        user_id=current_user.id,
        details=f"WIP Adjustment: {adj.quantity:+,.0f} pairs in {sec_name} on {adj.date}. Reason: {adj.reason}",
        reason=adj.reason
    )
    db.add(audit)
    db.commit()
    db.refresh(adj)
    return adj


@router.get("/{order_id}/wip-adjustments", response_model=List[WipAdjustmentOut])
def get_wip_adjustments(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns all controlled WIP adjustments for an order.
    """
    return db.query(WipAdjustment).filter(WipAdjustment.order_id == order_id).order_by(WipAdjustment.date.desc()).all()


@router.get("/matrix-planning", response_model=Optional[OrderMatrixPlanningOut])
def get_active_order_matrix_planning(
    order_id: Optional[int] = None,
    buyer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns the Date-Wise TG / ON HAND / O/T Planning Matrix for an order.
    If order_id is not provided, automatically selects the first active order.
    """
    target_order_id = order_id
    if not target_order_id:
        query = db.query(Order).filter(
            Order.is_archived == False,
            Order.status.notin_([OrderStatus.CLOSED, OrderStatus.PRODUCTION_COMPLETE, OrderStatus.ARCHIVED, OrderStatus.CANCELLED])
        )
        if buyer_id:
            query = query.filter(Order.buyer_id == buyer_id)
        first_order = query.order_by(Order.current_delivery_date.asc(), Order.id.asc()).first()
        if not first_order:
            return None
        target_order_id = first_order.id

    try:
        matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, target_order_id)
        return OrderMatrixPlanningOut(**matrix)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{order_id}/matrix-planning", response_model=OrderMatrixPlanningOut)
def get_order_matrix_planning(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns the Date-Wise TG / ON HAND / O/T Planning Matrix for a specific order.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.is_archived or order.status in [OrderStatus.ARCHIVED, OrderStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Archived or cancelled orders cannot generate active production planning matrices.")

    try:
        matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order_id)
        return OrderMatrixPlanningOut(**matrix)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{order_id}/recalculate-plan", response_model=OrderMatrixPlanningOut)
def recalculate_order_plan(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    """
    Controlled plan rebuild (Section 30):
    Recalculates all future planning rows from authoritative order data,
    entries, process route, and factory calendar without modifying historical production.
    """
    try:
        matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order_id)
        return OrderMatrixPlanningOut(**matrix)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/planning-sheet", response_model=List[PlanningSheetRowOut])
def get_planning_sheet(
    order_id: Optional[int] = None,
    buyer_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = ProductionPlanningService.generate_category_flow_planning_sheet(
        db=db,
        order_id=order_id,
        buyer_id=buyer_id,
        start_date=start_date,
        end_date=end_date
    )
    return [PlanningSheetRowOut(**r) for r in rows]


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order_detail(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    details = OrderService.get_order_calculated_details(db, order)
    return OrderDetailOut(**details)


@router.put("/{order_id}", response_model=OrderDetailOut)
def update_order(
    order_id: int,
    order_update: OrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    order = OrderService.update_order(db, order_id, order_update, current_user.id)
    details = OrderService.get_order_calculated_details(db, order)
    return OrderDetailOut(**details)


@router.post("/{order_id}/revise-delivery-date", response_model=OrderDetailOut)
def revise_order_delivery_date(
    order_id: int,
    rev_in: DeliveryRevisionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    order = OrderService.revise_delivery_date(db, order_id, rev_in, current_user.id)
    details = OrderService.get_order_calculated_details(db, order)
    return OrderDetailOut(**details)


@router.get("/{order_id}/revisions", response_model=List[DeliveryRevisionOut])
def get_order_revisions(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    revisions = db.query(DeliveryDateRevision).filter(
        DeliveryDateRevision.order_id == order_id
    ).order_by(DeliveryDateRevision.created_at.desc()).all()
    results = []
    for r in revisions:
        results.append(DeliveryRevisionOut(
            id=r.id,
            order_id=r.order_id,
            previous_delivery_date=r.previous_delivery_date,
            revised_delivery_date=r.revised_delivery_date,
            reason=r.reason,
            revised_by_id=r.revised_by_id,
            revised_by_name=r.revised_by_user.full_name if r.revised_by_user else None,
            created_at=r.created_at,
        ))
    return results


@router.get("/{order_id}/dependency-check", response_model=OrderDependencyCheckOut)
def check_order_dependencies(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Checks order dependencies (production entries, WIP records)
    to determine if permanent deletion or archival is required.
    """
    return OrderService.check_order_dependencies(db, order_id)


@router.delete("/{order_id}")
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Safely deletes an eligible order with 0 production dependencies.
    If production history exists, rejects permanent deletion and directs to archival.
    """
    return OrderService.delete_order(db, order_id, current_user.id)


@router.post("/{order_id}/archive", response_model=OrderDetailOut)
def archive_order(
    order_id: int,
    archive_in: Optional[OrderArchiveRequest] = None,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    """
    Archives/cancels an order with production history, preserving historical records
    while excluding it from active planning and selectors.
    """
    archive_reason = (archive_in.reason if archive_in and archive_in.reason else reason) or "Archived by user"
    order = OrderService.archive_order(db, order_id, current_user.id, reason=archive_reason)
    details = OrderService.get_order_calculated_details(db, order)
    return OrderDetailOut(**details)


@router.post("/{order_id}/restore", response_model=OrderDetailOut)
def restore_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    """
    Restores an archived order back to active operational planning status.
    """
    order = OrderService.restore_order(db, order_id, current_user.id)
    details = OrderService.get_order_calculated_details(db, order)
    return OrderDetailOut(**details)


@router.put("/{order_id}/routes/{route_id}/toggle-status")
def toggle_route_status(
    order_id: int,
    route_id: int,
    status_value: SectionRouteStatus,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    route = db.query(OrderRoute).filter(
        OrderRoute.id == route_id,
        OrderRoute.order_id == order_id
    ).first()
    if not route:
        raise HTTPException(status_code=404, detail="Order route not found")

    route.status = status_value
    db.commit()
    return {"detail": f"Route status updated to {status_value}"}


@router.get("/{order_id}/operations/{operation_id}/daily-schedule", response_model=DailySchedulePlanOut)
def get_operation_daily_schedule(
    order_id: int,
    operation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    op = db.query(OrderOperation).filter(
        OrderOperation.id == operation_id,
        OrderOperation.route.has(order_id=order_id)
    ).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")

    entries = db.query(DailyProductionEntry).filter(
        DailyProductionEntry.operation_id == op.id,
        DailyProductionEntry.is_reversed == False
    ).order_by(DailyProductionEntry.entry_date.asc()).all()

    rem_days, working_dates = ProductionPlanningService.calculate_remaining_days(
        db, order.production_start_date, order.current_delivery_date
    )

    cum_accepted = sum(e.accepted_quantity for e in entries)
    bal = ProductionPlanningService.calculate_balance(op.required_quantity, cum_accepted)
    daily_tgt = ProductionPlanningService.calculate_daily_target(bal, rem_days)

    future_plan = ProductionPlanningService.generate_future_daily_plan(db, order, op)

    rows: List[DailyScheduleRow] = []
    cum_acc = 0.0

    for r in future_plan:
        act = r.get("actual") or 0.0
        rej = r.get("rejected") or 0.0
        cum_acc += act
        pct = 100.0 if op.required_quantity <= 0 else min(100.0, round((cum_acc / op.required_quantity) * 100.0, 2))
        var = r.get("variance")
        if var is None:
            var = 0.0

        rows.append(
            DailyScheduleRow(
                date=r["date"],
                is_workday=True,
                day_name=r["day_name"],
                opening_balance=float(r["opening_balance"]),
                planned_quantity=float(r.get("auto_target_numeric", 0.0)),
                actual_accepted_quantity=float(act),
                rejected_quantity=float(rej),
                closing_balance=float(r["closing_balance"]),
                cumulative_accepted_quantity=float(cum_acc),
                completion_percentage=float(pct),
                variance=float(var),
                remarks=r.get("remarks")
            )
        )

    return DailySchedulePlanOut(
        order_id=order.id,
        operation_id=op.id,
        operation_name=op.operation_name,
        required_quantity=op.required_quantity,
        remaining_balance=bal,
        remaining_working_days=rem_days,
        daily_target=daily_tgt,
        rows=rows,
    )


@router.get("/{order_id}/category-flow", response_model=OrderCategoryFlowOut)
def get_order_category_flow(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    flow = ProductionPlanningService.calculate_category_flow(db, order)
    final_output = flow[-1]["completed_output"] if flow else 0.0
    final_bal = max(0.0, order.total_quantity - final_output)

    return OrderCategoryFlowOut(
        order_id=order.id,
        order_code=order.order_code,
        buyer_name=order.buyer.name if order.buyer else None,
        order_quantity=order.total_quantity,
        shipment_date=order.current_delivery_date,
        final_completed_quantity=final_output,
        final_balance=final_bal,
        categories=[CategoryFlowItemOut(**item) for item in flow]
    )


class RouteTargetOverride(BaseModel):
    minimum_daily_target: Optional[int] = None


@router.put("/{order_id}/routes/{route_id}/target-override")
def override_order_route_target(
    order_id: int,
    route_id: int,
    override_in: RouteTargetOverride,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    """Allows an authorized planning manager to override the section minimum daily target for a specific order."""
    route = db.query(OrderRoute).filter(OrderRoute.id == route_id, OrderRoute.order_id == order_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Order route not found")
    if override_in.minimum_daily_target is not None and override_in.minimum_daily_target < 0:
        raise HTTPException(status_code=400, detail="Minimum daily target cannot be negative")
    route.minimum_daily_target = override_in.minimum_daily_target
    db.commit()
    db.refresh(route)
    return {
        "order_id": order_id,
        "route_id": route_id,
        "minimum_daily_target": route.minimum_daily_target,
        "message": "Route target override updated successfully"
    }


