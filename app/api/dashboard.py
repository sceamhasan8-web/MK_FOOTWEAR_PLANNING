from typing import List
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.route import Section, Category, OrderRoute, SectionRouteStatus
from app.models.entry import DailyProductionEntry
from app.models.user import User
from app.schemas.dashboard import DashboardSummaryOut, SectionPerformance
from app.api.deps import get_current_user
from app.services.order_service import OrderService
from app.services.production_planning_service import ProductionPlanningService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    today = ProductionPlanningService.get_running_date()
    planning_display = ProductionPlanningService.get_planning_date_display(today)
    next_7_days = today + timedelta(days=7)

    # Active buyers
    active_buyers_count = db.query(Buyer).filter(Buyer.is_active == True).count()

    # Orders query
    all_orders = db.query(Order).all()
    active_orders = [
        o for o in all_orders
        if not getattr(o, "is_archived", False)
        and o.status not in [OrderStatus.CLOSED, OrderStatus.PRODUCTION_COMPLETE, OrderStatus.ARCHIVED, OrderStatus.CANCELLED]
    ]

    total_ordered_pairs = sum(o.total_quantity for o in active_orders)
    total_completed_pairs = 0.0
    total_outstanding_pairs = 0.0
    due_today_count = 0
    due_7_days_count = 0
    overdue_count = 0
    at_risk_count = 0

    order_details_cache = []
    for o in active_orders:
        det = OrderService.get_order_calculated_details(db, o, as_of_date=today)
        order_details_cache.append(det)

        total_completed_pairs += det["completed_pairs"]
        total_outstanding_pairs += det["outstanding_pairs"]

        if o.current_delivery_date == today:
            due_today_count += 1
        if today <= o.current_delivery_date <= next_7_days:
            due_7_days_count += 1
        if det["is_overdue"]:
            overdue_count += 1
        elif det["is_at_risk"]:
            at_risk_count += 1

    wip_waiting_qty = 0.0
    wip_waiting_count = 0
    for det in order_details_cache:
        for cat in det.get("categories", []):
            if cat.get("wip_status") in ["WAITING FOR WIP", "PARTIALLY AVAILABLE"]:
                shortage = max(0.0, cat.get("balance", 0.0) - cat.get("available_on_hand", 0.0))
                wip_waiting_qty += shortage
                wip_waiting_count += 1

    # Section-wise performance for today
    sections = db.query(Section).filter(Section.is_active == True).all()
    section_perfs: List[SectionPerformance] = []
    sections_behind_count = 0
    today_total_planned = 0.0
    today_total_actual = 0.0

    today_entries = db.query(DailyProductionEntry).filter(
        DailyProductionEntry.entry_date == today,
        DailyProductionEntry.is_reversed == False
    ).all()

    for s in sections:
        # Calculate today's planned target for this section across active orders
        s_planned = 0.0
        for det in order_details_cache:
            for r in det["routes"]:
                if r["section_id"] == s.id and r["status"] == "REQUIRED":
                    # Section daily target is max daily target among its operations
                    op_targets = [op["daily_target"] for op in r["operations"]]
                    if op_targets:
                        s_planned += max(op_targets)

        # Calculate actual today's production for this section
        s_actual_entries = [
            e for e in today_entries if e.route and e.route.section_id == s.id
        ]
        s_actual = sum(e.accepted_quantity for e in s_actual_entries)

        variance = s_actual - s_planned
        is_behind = (s_actual < s_planned) and (s_planned > 0)
        if is_behind:
            sections_behind_count += 1

        today_total_planned += s_planned
        today_total_actual += s_actual

        cat_name = s.category.name if s.category else "General"
        section_perfs.append(
            SectionPerformance(
                section_id=s.id,
                section_name=s.name,
                category_name=cat_name,
                total_planned_today=s_planned,
                total_actual_today=s_actual,
                variance=variance,
                is_behind=is_behind,
            )
        )

    return DashboardSummaryOut(
        total_active_buyers=active_buyers_count,
        active_orders_count=len(active_orders),
        total_ordered_pairs=total_ordered_pairs,
        completed_pairs=total_completed_pairs,
        outstanding_production_pairs=total_outstanding_pairs,
        total_balance=total_outstanding_pairs,
        running_date=today,
        planning_date_display=planning_display,
        orders_due_today=due_today_count,
        orders_due_7_days=due_7_days_count,
        overdue_orders_count=overdue_count,
        at_risk_orders_count=at_risk_count,
        sections_behind_count=sections_behind_count,
        today_total_planned=today_total_planned,
        today_total_actual=today_total_actual,
        wip_waiting_qty=wip_waiting_qty,
        wip_waiting_count=wip_waiting_count,
        section_performances=section_perfs,
    )

