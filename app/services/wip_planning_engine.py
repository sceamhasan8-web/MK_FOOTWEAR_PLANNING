import math
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.config import settings
from app.models.order import Order, OrderStatus
from app.models.route import OrderRoute, SectionRouteStatus
from app.models.entry import DailyProductionEntry
from app.models.calendar import FactoryCalendar
from app.models.wip_adjustment import WipAdjustment
from app.services.calendar_service import CalendarService
from app.services.production_planning_service import ProductionPlanningService


class WIPPlanningEngine:
    """
    Centralized Authoritative WIP Planning Engine for Footwear Manufacturing ERP.
    Single source of truth for:
    - User-defined Serial Production Workflow (Section 1 -> Section 2 -> Section 3...)
    - Dynamic Target Calculation: CEILING(Remaining Required / Remaining Working Days)
    - Bangladesh Factory Calendar filtering (Friday weekly off, holidays, special workdays)
    - Real-Time Live WIP On Hand tracking:
        * Section 1: On Hand = Order Quantity - Section 1 Cumulative Complete
        * Section N: On Hand = Section (N-1) Cumulative Complete - Section N Cumulative Complete
    - Target NEVER moves WIP forward. ONLY actual completed quantity transfers WIP.
    - Day-by-Day Serial Flow Sheet & Matrix View
    - Bottleneck Process & WIP Waiting identification
    - Order Completion based on the final serial workflow section
    """

    @classmethod
    def get_order_workflow_routes(cls, order: Order) -> List[OrderRoute]:
        """
        Returns all workflow routes for the order sorted by serial_no (or sequence_order).
        The serial_no is the authoritative production sequence.
        """
        routes = list(order.routes)
        routes.sort(key=lambda r: (
            getattr(r, "serial_no", None) or getattr(r, "sequence_order", 0) or 0,
            r.id or 0
        ))
        return routes

    @classmethod
    def calculate_order_wip_flow(
        cls,
        db: Session,
        order: Order,
        as_of_date: Optional[date] = None,
        calendar_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Authoritative calculation of the entire WIP Flow Planning Sheet for an order.
        Receives: Order, Workflow, Production Entries, Factory Calendar, Planning Date, Shipment Date.
        Returns:
        - Order meta & completion status
        - Bottleneck section & WIP waiting
        - Workflow serial sequence
        - Date-wise serial plan rows (Date -> Section 1, Section 2, Section 3...)
        - Date-by-date matrix view
        - Workflow summary table
        """
        running_date = as_of_date or date.today()
        cal = CalendarService.get_active_calendar(db, calendar_id)
        order_qty = float(order.total_quantity)

        # 1. Extract Workflow in serial order
        routes = cls.get_order_workflow_routes(order)
        required_routes = [
            r for r in routes
            if r.status == SectionRouteStatus.REQUIRED and r.section and r.section.is_active
        ]
        active_routes = required_routes if required_routes else [
            r for r in routes if r.section and r.section.is_active
        ]

        # 2. Planning Date Range
        plan_start = order.production_start_date or running_date
        plan_end = order.current_delivery_date

        all_entries = db.query(DailyProductionEntry).filter(
            DailyProductionEntry.order_id == order.id,
            DailyProductionEntry.is_reversed == False
        ).order_by(DailyProductionEntry.entry_date.asc(), DailyProductionEntry.id.asc()).all()

        if all_entries:
            min_ent_date = min(e.entry_date for e in all_entries)
            if min_ent_date < plan_start:
                plan_start = min_ent_date
            max_ent_date = max(e.entry_date for e in all_entries)
            if max_ent_date > plan_end:
                plan_end = max_ent_date

        num_days = max(1, (plan_end - plan_start).days + 1) if plan_end >= plan_start else 1
        planning_dates = [plan_start + timedelta(days=i) for i in range(num_days)]

        # Fetch adjustments
        adjustments = db.query(WipAdjustment).filter(
            WipAdjustment.order_id == order.id
        ).all()
        adj_map: Dict[Tuple[int, date], float] = {}
        for a in adjustments:
            key = (a.workflow_id, a.date)
            adj_map[key] = adj_map.get(key, 0.0) + float(a.quantity)

        # Aggregate actual production entries by (route_id, entry_date)
        entries_by_route_date: Dict[Tuple[int, date], float] = {}
        entries_by_route: Dict[int, float] = {r.id: 0.0 for r in routes}
        for e in all_entries:
            r_id = e.route_id
            entries_by_route_date[(r_id, e.entry_date)] = (
                entries_by_route_date.get((r_id, e.entry_date), 0.0) + float(e.accepted_quantity)
            )
            entries_by_route[r_id] = entries_by_route.get(r_id, 0.0) + float(e.accepted_quantity)

        # Precompute factory calendar working day flags and remaining working days
        cal_exceptions = list(cal.exceptions)
        working_day_flag: Dict[date, bool] = {}
        rem_working_days_map: Dict[date, int] = {}
        for d in planning_dates:
            is_workday = CalendarService.is_working_day(d, cal, cal_exceptions)
            working_day_flag[d] = is_workday
            rem_days, _ = CalendarService.get_remaining_working_days(
                db=db,
                start_date=d,
                delivery_date=order.current_delivery_date,
                calendar_id=cal.id,
                as_of_date=d
            )
            rem_working_days_map[d] = rem_days

        # 3. Precompute section-wise targets using intelligent planning engine
        future_workdays_from_running = [
            d for d in planning_dates
            if d >= running_date and d <= order.current_delivery_date and working_day_flag[d]
        ]
        future_workdays_strictly_after_running = [
            d for d in planning_dates
            if d > running_date and d <= order.current_delivery_date and working_day_flag[d]
        ]

        route_targets_map: Dict[int, Dict[date, int]] = {}
        eff_min_by_route: Dict[int, int] = {}

        for s_idx, r in enumerate(active_routes):
            eff_rules = ProductionPlanningService.get_effective_target_rules(db, r.section_id, r)
            eff_min = eff_rules["minimum_daily_target"]
            eff_max = eff_rules["maximum_daily_target"]
            eff_mode = eff_rules["calculation_mode"]
            eff_min_by_route[r.id] = eff_min

            past_accepted = sum(entries_by_route_date.get((r.id, d), 0.0) for d in planning_dates if d < running_date)
            today_accepted = entries_by_route_date.get((r.id, running_date), 0.0)
            total_accepted_to_date = past_accepted + today_accepted
            curr_balance = max(0, int(round(order_qty)) - int(round(total_accepted_to_date)))

            if s_idx == 0:
                allocatable_wip = curr_balance
            else:
                prev_r = active_routes[s_idx - 1]
                prev_accepted = sum(entries_by_route_date.get((prev_r.id, d), 0.0) for d in planning_dates if d <= running_date)
                allocatable_wip = max(0, int(round(prev_accepted)) - int(round(total_accepted_to_date)))

            r_sched: Dict[date, int] = {}
            has_today_entry = (r.id, running_date) in entries_by_route_date

            if has_today_entry:
                today_oh = allocatable_wip + int(round(today_accepted))
                today_dist = ProductionPlanningService.allocate_section_targets(
                    order_qty, past_accepted, today_oh, future_workdays_from_running,
                    effective_min=eff_min, effective_max=eff_max, calculation_mode=eff_mode
                )
                r_sched[running_date] = today_dist.get(running_date, 0)
                if future_workdays_strictly_after_running and curr_balance > 0 and allocatable_wip > 0:
                    future_dist = ProductionPlanningService.allocate_section_targets(
                        order_qty, total_accepted_to_date, allocatable_wip, future_workdays_strictly_after_running,
                        effective_min=eff_min, effective_max=eff_max, calculation_mode=eff_mode
                    )
                    r_sched.update(future_dist)
            else:
                if future_workdays_from_running and curr_balance > 0 and allocatable_wip > 0:
                    future_dist = ProductionPlanningService.allocate_section_targets(
                        order_qty, total_accepted_to_date, allocatable_wip, future_workdays_from_running,
                        effective_min=eff_min, effective_max=eff_max, calculation_mode=eff_mode
                    )
                    r_sched.update(future_dist)

            for d in planning_dates:
                if d < running_date:
                    if (r.id, d) in entries_by_route_date:
                        r_sched[d] = int(round(entries_by_route_date[(r.id, d)]))
                    else:
                        r_sched[d] = 0

            route_targets_map[r.id] = r_sched

        # 4. Simulate day-by-day serial flow
        closing_on_hand: Dict[int, float] = {}
        cum_complete: Dict[int, float] = {r.id: 0.0 for r in routes}
        prev_day_actual: Dict[int, float] = {r.id: 0.0 for r in routes}

        for idx, r in enumerate(active_routes):
            if idx == 0:
                closing_on_hand[r.id] = order_qty
            else:
                closing_on_hand[r.id] = 0.0

        daily_flow_rows: List[Dict[str, Any]] = []
        matrix_rows: List[Dict[str, Any]] = []

        total_tg_by_route: Dict[int, float] = {r.id: 0.0 for r in routes}

        for d_idx, d in enumerate(planning_dates):
            is_workday = working_day_flag[d]
            day_name = d.strftime("%A")
            rem_work_days = rem_working_days_map[d]

            # Storage for today's actuals across sections for immediate transfer
            today_actual_by_route: Dict[int, float] = {}
            matrix_section_data: Dict[str, Any] = {}

            # First pass for today: gather actual entered for today if any
            for r in active_routes:
                today_actual_by_route[r.id] = entries_by_route_date.get((r.id, d), 0.0)

            for s_idx, r in enumerate(active_routes):
                serial = s_idx + 1
                sec_name = r.section.name if r.section else f"Section {r.section_id}"
                transfer_rule = getattr(r, "transfer_rule", "IMMEDIATE") or "IMMEDIATE"

                # 1. Opening On Hand
                if d_idx == 0:
                    if s_idx == 0:
                        opening_oh = order_qty
                    else:
                        opening_oh = 0.0
                else:
                    opening_oh = closing_on_hand[r.id]

                # 2. Incoming WIP (Transfer only actual completed quantity, NEVER target)
                if s_idx == 0:
                    incoming_wip = 0.0
                else:
                    prev_r = active_routes[s_idx - 1]
                    if transfer_rule == "NEXT_WORKING_DAY":
                        incoming_wip = prev_day_actual.get(prev_r.id, 0.0)
                    else:
                        incoming_wip = today_actual_by_route.get(prev_r.id, 0.0)

                # Add any WIP adjustments
                adj_val = adj_map.get((r.id, d), 0.0)
                available_wip = max(0.0, opening_oh + incoming_wip + adj_val)

                # 3. Dynamic Target & Rate Calculation
                prior_cum = cum_complete[r.id]
                rem_req = max(0.0, order_qty - prior_cum)

                daily_tg = float(route_targets_map[r.id].get(d, 0)) if is_workday else 0.0
                total_tg_by_route[r.id] += daily_tg

                req_daily_rate = float((int(round(rem_req)) + rem_work_days - 1) // rem_work_days) if rem_work_days > 0 and rem_req > 0 else float(rem_req)

                # 4. Actual Production
                has_entry = (r.id, d) in entries_by_route_date
                act_qty = entries_by_route_date.get((r.id, d), 0.0) if has_entry else 0.0

                # 5. Complete (Cumulative)
                new_cum = prior_cum + act_qty
                cum_complete[r.id] = new_cum

                # 6. Closing On Hand (Available WIP - Actual Production)
                closing_oh = max(0.0, available_wip - act_qty)
                closing_on_hand[r.id] = closing_oh
                prev_day_actual[r.id] = act_qty

                # 7. Balance
                bal = max(0.0, order_qty - new_cum)

                # 8. Status Evaluation
                if new_cum >= order_qty:
                    status_str = "COMPLETED"
                    status_code = "GREEN"
                elif rem_work_days <= 0 and bal > 0:
                    status_str = "OVERDUE"
                    status_code = "RED"
                elif available_wip <= 0 and bal > 0:
                    status_str = "WAITING FOR WIP"
                    status_code = "ORANGE"
                elif available_wip > 0 and available_wip < req_daily_rate and daily_tg < req_daily_rate:
                    status_str = "PARTIALLY AVAILABLE"
                    status_code = "YELLOW"
                elif has_entry:
                    if act_qty >= daily_tg and daily_tg > 0:
                        status_str = "ON TRACK" if act_qty == daily_tg else "AHEAD"
                        status_code = "GREEN"
                    elif act_qty < daily_tg and daily_tg > 0:
                        status_str = "BEHIND TARGET"
                        status_code = "YELLOW"
                    else:
                        status_str = "ON TRACK"
                        status_code = "GREEN"
                else:
                    if d < running_date and daily_tg > 0:
                        status_str = "BEHIND TARGET"
                        status_code = "YELLOW"
                    elif daily_tg > 0:
                        status_str = "ON TRACK"
                        status_code = "GREEN"
                    elif bal > 0:
                        status_str = "WAITING FOR WIP"
                        status_code = "ORANGE"
                    else:
                        status_str = "COMPLETED"
                        status_code = "GREEN"

                flow_row = {
                    "date": d,
                    "date_str": d.strftime("%Y-%m-%d"),
                    "date_display": d.strftime("%d/%m/%Y"),
                    "is_workday": is_workday,
                    "is_working_day": is_workday,
                    "day_name": day_name,
                    "serial_no": serial,
                    "route_id": r.id,
                    "section_id": r.section_id,
                    "section_name": sec_name,
                    "target": round(daily_tg, 1),
                    "tg": round(daily_tg, 1),
                    "opening_on_hand": round(opening_oh, 1),
                    "incoming_wip": round(incoming_wip, 1),
                    "available_wip": round(available_wip, 1),
                    "actual_production": round(act_qty, 1) if (has_entry or d <= running_date) else None,
                    "actual": round(act_qty, 1) if (has_entry or d <= running_date) else 0.0,
                    "complete": round(new_cum, 1),
                    "closing_on_hand": round(closing_oh, 1),
                    "balance": round(bal, 1),
                    "remaining_working_days": rem_work_days,
                    "remaining_days": rem_work_days,
                    "minimum_daily_target": eff_min_by_route[r.id],
                    "required_daily_rate": req_daily_rate,
                    "executable_tg": round(daily_tg, 1),
                    "wip_availability_status": status_str,
                    "status": status_str,
                    "status_code": status_code,
                    "transfer_rule": transfer_rule,
                }
                daily_flow_rows.append(flow_row)

                matrix_section_data[sec_name] = {
                    "tg": round(daily_tg, 1),
                    "on_hand": round(available_wip, 1),
                    "actual": round(act_qty, 1) if (has_entry or d <= running_date) else None,
                    "ot": round(act_qty, 1),
                    "complete": round(new_cum, 1),
                    "closing_on_hand": round(closing_oh, 1),
                    "balance": round(bal, 1),
                    "minimum_daily_target": eff_min_by_route[r.id],
                    "required_daily_rate": req_daily_rate,
                    "status": status_str,
                    "status_code": status_code,
                }

            matrix_rows.append({
                "date": d,
                "date_str": d.strftime("%Y-%m-%d"),
                "date_display": d.strftime("%d/%m/%Y"),
                "is_workday": is_workday,
                "day_name": day_name,
                "remaining_working_days": rem_work_days,
                "sections": matrix_section_data,
            })

        # 4. Live Cumulative Totals & On Hand (Section 11, 12, 51)
        # Mathematical verification:
        # On Hand(1) = Order Qty - Complete(1)
        # On Hand(N) = Complete(N-1) - Complete(N)
        summary_list: List[Dict[str, Any]] = []
        for s_idx, r in enumerate(active_routes):
            serial = s_idx + 1
            sec_name = r.section.name if r.section else f"Section {r.section_id}"
            tot_complete = cum_complete[r.id]
            tot_tg = total_tg_by_route[r.id]
            bal = max(0.0, order_qty - tot_complete)

            if s_idx == 0:
                live_on_hand = max(0.0, order_qty - tot_complete)
            else:
                prev_r = active_routes[s_idx - 1]
                prev_complete = cum_complete[prev_r.id]
                live_on_hand = max(0.0, prev_complete - tot_complete)

            rem_days_now = rem_working_days_map.get(running_date, 0)
            if tot_complete >= order_qty:
                sec_status = "COMPLETED"
                sec_code = "GREEN"
            elif rem_days_now <= 0 and bal > 0:
                sec_status = "OVERDUE"
                sec_code = "RED"
            elif live_on_hand <= 0 and bal > 0:
                sec_status = "WAITING FOR WIP"
                sec_code = "ORANGE"
            else:
                sec_status = "RUNNING"
                sec_code = "BLUE"

            summary_list.append({
                "serial_no": serial,
                "route_id": r.id,
                "section_id": r.section_id,
                "section_name": sec_name,
                "required_quantity": order_qty,
                "required_qty": order_qty,
                "total_target": round(tot_tg, 1),
                "total_tg": round(tot_tg, 1),
                "complete": round(tot_complete, 1),
                "final_on_hand": round(live_on_hand, 1),
                "closing_on_hand": round(live_on_hand, 1),
                "balance": round(bal, 1),
                "status": sec_status,
                "status_code": sec_code,
                "transfer_rule": getattr(r, "transfer_rule", "IMMEDIATE") or "IMMEDIATE",
            })

        # 5. Bottleneck Identification (Section 36)
        # Section with largest waiting WIP between processes
        bottleneck_sec = "None"
        max_waiting_wip = 0.0

        for s_idx in range(1, len(active_routes)):
            curr_r = active_routes[s_idx]
            prev_r = active_routes[s_idx - 1]
            waiting = max(0.0, cum_complete[prev_r.id] - cum_complete[curr_r.id])
            if waiting > max_waiting_wip:
                max_waiting_wip = waiting
                sec_name = curr_r.section.name if curr_r.section else f"Section {curr_r.section_id}"
                bottleneck_sec = f"{sec_name}"

        # If no internal WIP backlog, bottleneck is the section with lowest cumulative completion
        if bottleneck_sec == "None" and active_routes:
            min_r = min(active_routes, key=lambda r: cum_complete[r.id])
            bottleneck_sec = min_r.section.name if min_r.section else f"Section {min_r.section_id}"
            max_waiting_wip = max(0.0, order_qty - cum_complete[min_r.id])

        # 6. Order Completion (Section 35)
        # Final order completion is based on the LAST REQUIRED WORKFLOW SECTION
        last_route = active_routes[-1] if active_routes else None
        last_complete = cum_complete[last_route.id] if last_route else 0.0
        final_balance = max(0.0, order_qty - last_complete)
        rem_days_now = rem_working_days_map.get(running_date, 0)

        if final_balance <= 0.0:
            order_overall_status = "COMPLETED"
        elif rem_days_now <= 0 and final_balance > 0:
            order_overall_status = "OVERDUE"
        elif any(s["status"] == "WIP SHORTAGE" for s in daily_flow_rows if s["date"] == running_date):
            order_overall_status = "WIP SHORTAGE"
        elif rem_days_now <= 2 or final_balance > (order_qty * 0.7):
            order_overall_status = "AT RISK" if last_complete < (order_qty * 0.3) else "ON TRACK"
        elif last_complete > 0:
            order_overall_status = "RUNNING"
        else:
            order_overall_status = "NOT STARTED"

        completion_summary = {
            "order_quantity": order_qty,
            "completed_quantity": round(last_complete, 1),
            "final_balance": round(final_balance, 1),
            "remaining_balance": round(final_balance, 1),
            "remaining_working_days": rem_days_now,
            "days_remaining": rem_days_now,
            "current_bottleneck": bottleneck_sec,
            "bottleneck_section": bottleneck_sec,
            "wip_waiting": round(max_waiting_wip, 1),
            "wip_waiting_quantity": round(max_waiting_wip, 1),
            "wip_waiting_display": f"{bottleneck_sec} ({max_waiting_wip:,.0f} pairs)" if max_waiting_wip > 0 else "0 pairs",
            "overall_status": order_overall_status,
        }

        # Date-grouped view structure (Section 33)
        dates_grouped: List[Dict[str, Any]] = []
        for d in planning_dates:
            d_rows = [r for r in daily_flow_rows if r["date"] == d]
            dates_grouped.append({
                "date": d,
                "date_str": d.strftime("%Y-%m-%d"),
                "date_display": d.strftime("%d %B %Y"),
                "day_name": d.strftime("%A"),
                "is_workday": working_day_flag[d],
                "remaining_working_days": rem_working_days_map[d],
                "sections": d_rows,
            })

        sections_meta = [
            {
                "serial_no": idx + 1,
                "route_id": r.id,
                "section_id": r.section_id,
                "section_name": r.section.name if r.section else f"Section {r.section_id}"
            }
            for idx, r in enumerate(active_routes)
        ]

        return {
            "order_id": order.id,
            "order_code": order.order_code,
            "buyer_id": order.buyer_id,
            "buyer_name": order.buyer.name if order.buyer else "N/A",
            "customer_ref": order.customer_ref,
            "style_model": order.style_model,
            "order_quantity": order_qty,
            "total_quantity": order_qty,
            "planning_start_date": order.production_start_date,
            "shipment_date": order.current_delivery_date,
            "running_date": running_date,
            "remaining_working_days": rem_days_now,
            "final_balance": round(final_balance, 1),
            "overall_status": order_overall_status,
            "current_bottleneck": bottleneck_sec,
            "bottleneck": bottleneck_sec,
            "bottleneck_process": bottleneck_sec,
            "wip_waiting": round(max_waiting_wip, 1),
            "wip_waiting_quantity": round(max_waiting_wip, 1),
            "sections": sections_meta,
            "workflow": summary_list,
            "summary": summary_list,
            "workflow_summary": summary_list,
            "rows": daily_flow_rows,
            "daily_plan_rows": daily_flow_rows,
            "dates_grouped": dates_grouped,
            "matrix_rows": matrix_rows,
            "completion_summary": completion_summary,
        }

    @classmethod
    def get_available_wip_for_route(
        cls,
        db: Session,
        order_or_route: Any,
        route_id: Optional[int] = None,
        as_of_date: Optional[date] = None,
        exclude_target_cum: bool = False
    ) -> float:
        """
        Returns live available WIP On Hand for an order's section.
        Enforces Rule: Production cannot exceed available On Hand.
        Formula:
        - Section 1: Order Quantity - Section 1 Cumulative Complete
        - Section N: Section (N-1) Cumulative Complete - Section N Cumulative Complete
        """
        if hasattr(order_or_route, "order_id") and hasattr(order_or_route, "section_id"):
            route = order_or_route
            order = getattr(route, "order", None)
            if order is None:
                order = db.query(Order).filter(Order.id == route.order_id).first()
            target_route_id = route.id
        elif isinstance(order_or_route, Order):
            order = order_or_route
            target_route_id = route_id
        else:
            order = getattr(order_or_route, "order", None)
            target_route_id = getattr(order_or_route, "id", route_id)

        if not order:
            return 0.0

        routes = cls.get_order_workflow_routes(order)
        required_routes = [
            r for r in routes
            if r.status == SectionRouteStatus.REQUIRED and r.section and r.section.is_active
        ]
        active_routes = required_routes if required_routes else [
            r for r in routes if r.section and r.section.is_active
        ]

        target_idx = None
        for idx, r in enumerate(active_routes):
            if r.id == target_route_id:
                target_idx = idx
                break

        if target_idx is None:
            return float(order.total_quantity)

        # Query all accepted entries
        query = db.query(DailyProductionEntry).filter(
            DailyProductionEntry.order_id == order.id,
            DailyProductionEntry.is_reversed == False
        )
        if as_of_date:
            query = query.filter(DailyProductionEntry.entry_date <= as_of_date)
        entries = query.all()

        cum_by_route: Dict[int, float] = {r.id: 0.0 for r in active_routes}
        for e in entries:
            if e.route_id in cum_by_route:
                cum_by_route[e.route_id] += float(e.accepted_quantity)

        target_r = active_routes[target_idx]
        target_complete = cum_by_route[target_r.id]

        if target_idx == 0:
            if exclude_target_cum:
                return float(order.total_quantity)
            return max(0.0, float(order.total_quantity) - target_complete)
        else:
            prev_r = active_routes[target_idx - 1]
            prev_complete = cum_by_route[prev_r.id]
            if exclude_target_cum:
                return prev_complete
            return max(0.0, prev_complete - target_complete)
