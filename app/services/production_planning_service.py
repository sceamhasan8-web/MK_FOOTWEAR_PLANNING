import math
from datetime import date, datetime, timedelta, time
from typing import List, Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.config import settings
from app.models.order import Order, OrderStatus
from app.models.route import (
    OrderRoute,
    OrderOperation,
    OperationComponent,
    SectionRouteStatus,
    OperationStatus,
    ProductionTargetSetting,
)
from app.models.entry import DailyProductionEntry
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.services.calendar_service import CalendarService


class ProductionPlanningService:
    """
    Authoritative calculation service for Footwear Manufacturing Production Planning ERP.
    Single source of truth for:
    - Current business running date (Asia/Dhaka)
    - Outstanding production balance = MAX(0, Required - Accepted)
    - Remaining production days
    - Auto daily target = CEILING(Balance / Remaining Days)
    - Today's actual & schedule variance = Actual - Target
    - Continuous future schedule recalculation
    - Risk & overdue status evaluation
    """

    DEFAULT_TIMEZONE = "Asia/Dhaka"

    @classmethod
    def get_running_date(cls, timezone_name: Optional[str] = None) -> date:
        """
        Returns the authoritative server business running date.
        Timezone defaults to Asia/Dhaka.
        """
        tz_str = timezone_name or settings.DEFAULT_TIMEZONE or cls.DEFAULT_TIMEZONE
        try:
            tz = ZoneInfo(tz_str)
            return datetime.now(tz).date()
        except Exception:
            return date.today()

    @classmethod
    def get_planning_date_display(cls, d: Optional[date] = None) -> str:
        """Formats business running date nicely e.g. '07 October 2026'."""
        target_d = d or cls.get_running_date()
        return target_d.strftime("%d %B %Y")

    @staticmethod
    def calculate_balance(required_qty: float, cumulative_accepted: float) -> float:
        """
        Current Balance = MAX(0, Required Quantity - Cumulative Accepted Production).
        Never allows displayed balance to become negative.
        """
        req = float(required_qty or 0.0)
        acc = float(cumulative_accepted or 0.0)
        return max(0.0, req - acc)

    @classmethod
    def calculate_remaining_days(
        cls,
        db: Session,
        start_date: date,
        delivery_date: date,
        calendar_id: Optional[int] = None,
        as_of_date: Optional[date] = None,
        use_working_days_only: Optional[bool] = None
    ) -> Tuple[int, List[date]]:
        """
        Calculates remaining production days from running date to current active delivery date.
        Respects configurable factory calendar (working days mode or all calendar days,
        factory closures and holidays).
        """
        running_date = as_of_date or cls.get_running_date()
        return CalendarService.get_remaining_working_days(
            db=db,
            start_date=start_date,
            delivery_date=delivery_date,
            calendar_id=calendar_id,
            as_of_date=running_date,
            use_working_days_only=use_working_days_only
        )

    @staticmethod
    def distribute_exact_target(
        balance: int,
        working_dates: List[date]
    ) -> Dict[date, int]:
        """
        Exact Daily Target Distribution Algorithm (Footwear ERP Specification):
        Given:
            Balance = B
            Working Days = D
        Calculate:
            Base Target = FLOOR(B / D)
            Remainder = B MOD D
        Then:
            First `Remainder` working days receive `Base Target + 1`
            Remaining working days receive `Base Target`
        Guarantees:
            SUM(All Daily Targets) = Balance exactly.
        Requirements:
            - Input balance must be non-negative.
            - Input working date list must be ordered chronologically.
            - Return one target for each working date.
            - Sum of returned targets must equal balance.
            - Never return negative target.
            - Return empty mapping if there are no working dates and balance is zero.
            - Raise a controlled business error if balance > 0 and no working date exists.
            - Integer arithmetic only.
        """
        if balance < 0:
            raise ValueError("Balance must be non-negative")

        sorted_dates = sorted(working_dates)
        days = len(sorted_dates)

        if days == 0:
            if balance == 0:
                return {}
            raise ValueError("NO_AVAILABLE_WORKING_DAYS")

        balance_int = int(balance)
        base = balance_int // days
        remainder = balance_int % days

        schedule: Dict[date, int] = {}
        for index, working_date in enumerate(sorted_dates):
            target = base + (1 if index < remainder else 0)
            schedule[working_date] = target

        assert sum(schedule.values()) == balance_int, (
            f"Exact target distribution check failed: sum({sum(schedule.values())}) != balance({balance_int})"
        )
        return schedule

    @staticmethod
    def calculate_daily_target(remaining_balance: float, remaining_days: int) -> float:
        """
        Main Daily Target Formula:
        Daily Target = CEILING(Current Balance / Remaining Production Days, 1)

        Rules:
        - If Balance <= 0: return 0.0 (Production Complete).
        - If Remaining Days <= 0 and Balance > 0: do NOT divide by zero. Return 0.0 (flagged OVERDUE).
        - Always round upward so no balance is left behind at the deadline.
        """
        balance = max(0.0, float(remaining_balance or 0.0))
        if balance <= 0.0:
            return 0.0
        if remaining_days <= 0:
            # Overdue condition: avoid division by zero
            return 0.0
        return float(math.ceil(balance / remaining_days))

    @staticmethod
    def calculate_daily_variance(actual_quantity: float, auto_target: float) -> float:
        """
        Today's Variance = Today's Actual Production - Auto Daily Target.
        Positive = Ahead by X pairs.
        Negative = Behind by X pairs.
        """
        return round(float(actual_quantity or 0.0) - float(auto_target or 0.0), 2)

    @classmethod
    def get_effective_minimum_target(
        cls,
        db: Session,
        section_id: int,
        order_route: Optional[OrderRoute] = None
    ) -> int:
        """
        Determines the authoritative effective minimum daily target for a section.
        Priority:
        1. Order-specific section setting (order_route.minimum_daily_target), if one exists.
        2. Global section minimum (ProductionTargetSetting.minimum_daily_target), if active.
        3. Zero if neither is configured.
        Enforces non-negative values.
        """
        rules = cls.get_effective_target_rules(db, section_id, order_route)
        return rules["minimum_daily_target"]

    @classmethod
    def get_effective_target_rules(
        cls,
        db: Session,
        section_id: int,
        order_route: Optional[OrderRoute] = None
    ) -> Dict[str, Any]:
        """
        Determines authoritative effective target rules (min, max, mode) for a section.
        Priority:
        1. Order-specific section setting (order_route overrides), if configured.
        2. Global section target setting (ProductionTargetSetting), if active or exists.
        3. Safe factory defaults (min=0, max=0/unlimited, mode="BALANCED").
        Supports sections without explicit target settings.
        Handles missing fields independently.
        """
        eff_min = 0
        eff_max = 0
        mode = "BALANCED"

        setting = db.query(ProductionTargetSetting).filter(
            ProductionTargetSetting.section_id == section_id
        ).first()

        if setting and getattr(setting, "is_active", True):
            if setting.minimum_daily_target is not None:
                eff_min = max(0, int(setting.minimum_daily_target))
            if setting.maximum_daily_target is not None:
                eff_max = max(0, int(setting.maximum_daily_target))
            if setting.calculation_mode:
                mode = setting.calculation_mode

        if order_route is not None:
            if getattr(order_route, "minimum_daily_target", None) is not None:
                eff_min = max(0, int(order_route.minimum_daily_target))
            if getattr(order_route, "maximum_daily_target", None) is not None:
                eff_max = max(0, int(order_route.maximum_daily_target))
            if getattr(order_route, "calculation_mode", None):
                mode = order_route.calculation_mode

        validation_error = None
        if eff_min > 0 and eff_max > 0 and eff_min > eff_max:
            validation_error = f"Invalid configuration: Minimum target ({eff_min}) exceeds Maximum target ({eff_max})."

        return {
            "minimum_daily_target": eff_min,
            "maximum_daily_target": eff_max,
            "calculation_mode": mode,
            "validation_error": validation_error
        }

    @classmethod
    def evaluate_capacity_feasibility(
        cls,
        remaining_balance: float,
        remaining_workdays: int,
        maximum_daily_target: int
    ) -> Dict[str, Any]:
        """
        Evaluates whether the section's maximum daily capacity is sufficient to complete
        the remaining balance within the remaining working days.
        """
        if remaining_balance <= 0 or remaining_workdays <= 0:
            return {"is_feasible": True, "required_daily_rate": 0, "shortfall": 0, "conflict": None}

        required_daily_rate = math.ceil(remaining_balance / remaining_workdays)
        if maximum_daily_target > 0 and required_daily_rate > maximum_daily_target:
            max_possible_output = maximum_daily_target * remaining_workdays
            shortfall = remaining_balance - max_possible_output
            days_needed = math.ceil(remaining_balance / maximum_daily_target)
            delay_days = days_needed - remaining_workdays
            return {
                "is_feasible": False,
                "required_daily_rate": required_daily_rate,
                "maximum_daily_target": maximum_daily_target,
                "remaining_balance": remaining_balance,
                "remaining_workdays": remaining_workdays,
                "shortfall": shortfall,
                "delay_days": delay_days,
                "conflict": "Maximum daily capacity is insufficient to complete this balance before shipment."
            }

        return {
            "is_feasible": True,
            "required_daily_rate": required_daily_rate,
            "maximum_daily_target": maximum_daily_target,
            "remaining_balance": remaining_balance,
            "remaining_workdays": remaining_workdays,
            "shortfall": 0,
            "delay_days": 0,
            "conflict": None
        }

    @classmethod
    def calculate_section_target(
        cls,
        db: Session,
        order: Order,
        route: OrderRoute,
        as_of_date: Optional[date] = None,
        production_entries: Optional[List[DailyProductionEntry]] = None,
        available_on_hand: Optional[float] = None,
        calendar: Optional[FactoryCalendar] = None,
        exceptions: Optional[List[CalendarException]] = None,
        wip_records: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Authoritative automatic target calculation function for any applicable active section.
        Works identically whether target settings are saved or missing:
        1. Confirms section is active and required for the order.
        2. Reads section's stable internal ID.
        3. Calculates current remaining requirement (balance).
        4. Retrieves remaining valid working dates from Factory Calendar.
        5. Calculates Required Daily Rate: CEILING(Remaining Balance / Remaining Workdays).
        6. Retrieves optional minimum/maximum limits (safe defaults: min=0, max=0/unlimited).
        7. Calculates available allocatable WIP.
        8. Calculates executable T/G against available WIP and limits.
        9. Determines authoritative section status and capacity feasibility.
        """
        sec = route.section
        sec_id = sec.id if sec else route.section_id
        sec_name = sec.name.upper() if sec else f"SECTION {sec_id}"

        is_active = bool(sec and getattr(sec, "is_active", True))
        is_required = (route.status == SectionRouteStatus.REQUIRED)

        if not is_active or not is_required:
            return {
                "section_id": sec_id,
                "section_name": sec_name,
                "route_id": route.id,
                "is_applicable": False,
                "is_active": is_active,
                "is_required": is_required,
                "remaining_balance": 0.0,
                "total_accepted": 0.0,
                "remaining_working_days": 0,
                "working_dates": [],
                "required_daily_rate": 0,
                "minimum_daily_target": 0,
                "maximum_daily_target": 0,
                "calculation_mode": "BALANCED",
                "allocatable_wip": 0.0,
                "executable_tg": 0,
                "status": "NOT REQUIRED" if not is_required else "INACTIVE",
                "status_code": "GRAY",
                "feasibility": {"is_feasible": True, "conflict": None}
            }

        running_date = as_of_date or cls.get_running_date()
        cal = calendar or CalendarService.get_active_calendar(db)
        excs = exceptions if exceptions is not None else db.query(CalendarException).filter(CalendarException.calendar_id == cal.id).all()

        # Cumulative accepted production for this route
        if production_entries is not None:
            route_entries = [e for e in production_entries if e.route_id == route.id and not e.is_reversed]
        else:
            route_entries = db.query(DailyProductionEntry).filter(
                DailyProductionEntry.route_id == route.id,
                DailyProductionEntry.is_reversed == False
            ).all()

        cum_accepted = sum(e.accepted_quantity for e in route_entries)
        curr_balance = max(0, int(round(order.total_quantity)) - int(round(cum_accepted)))

        # Remaining working days from running date through shipment
        rem_workdays, working_dates = cls.calculate_remaining_days(
            db=db,
            start_date=order.production_start_date,
            delivery_date=order.current_delivery_date,
            as_of_date=running_date,
            calendar_id=cal.id
        )

        # Required Daily Rate: CEILING(Remaining Balance / Remaining Workdays)
        if rem_workdays > 0 and curr_balance > 0:
            required_daily_rate = math.ceil(curr_balance / rem_workdays)
        elif curr_balance > 0:
            required_daily_rate = int(curr_balance)
        else:
            required_daily_rate = 0

        # Retrieve optional target settings with safe defaults (min=0, max=0=unlimited)
        eff_rules = cls.get_effective_target_rules(db, sec_id, route)
        eff_min = eff_rules["minimum_daily_target"]
        eff_max = eff_rules["maximum_daily_target"]
        eff_mode = eff_rules["calculation_mode"]
        val_error = eff_rules.get("validation_error")

        # Allocatable WIP calculation
        if available_on_hand is not None:
            allocatable_wip = max(0.0, float(available_on_hand))
        else:
            req_routes = [
                r for r in order.routes
                if r.section and r.section.is_active and r.status == SectionRouteStatus.REQUIRED
            ]
            req_routes.sort(key=lambda r: (
                r.sequence_order if (r.sequence_order and r.sequence_order > 0) else 999,
                getattr(r, "serial_no", 999) or 999,
                r.id
            ))
            route_idx = next((i for i, r in enumerate(req_routes) if r.id == route.id), 0)
            if route_idx == 0:
                allocatable_wip = float(curr_balance)
            else:
                prev_r = req_routes[route_idx - 1]
                if production_entries is not None:
                    prev_entries = [e for e in production_entries if e.route_id == prev_r.id and not e.is_reversed]
                else:
                    prev_entries = db.query(DailyProductionEntry).filter(
                        DailyProductionEntry.route_id == prev_r.id,
                        DailyProductionEntry.is_reversed == False
                    ).all()
                prev_accepted = sum(e.accepted_quantity for e in prev_entries)
                allocatable_wip = max(0.0, float(int(round(prev_accepted)) - int(round(cum_accepted))))

        # Executable T/G based on available stock and target rules
        if allocatable_wip <= 0 or curr_balance <= 0:
            executable_tg = 0
        else:
            if eff_mode in ("MINIMUM_DRIVEN", "MODE_B") and eff_min > 0:
                desired = eff_min
            else:
                desired = max(required_daily_rate, eff_min)
            if eff_max > 0:
                desired = min(desired, eff_max)
            executable_tg = min(desired, curr_balance, int(allocatable_wip))

        # Capacity feasibility check
        feasibility = cls.evaluate_capacity_feasibility(
            remaining_balance=float(curr_balance),
            remaining_workdays=rem_workdays,
            maximum_daily_target=eff_max
        )
        if val_error:
            feasibility["is_feasible"] = False
            feasibility["conflict"] = val_error

        # Section status
        if curr_balance <= 0:
            status_str = "COMPLETED"
            status_code = "GREEN"
        elif rem_workdays <= 0:
            status_str = "OVERDUE"
            status_code = "RED"
        elif allocatable_wip <= 0:
            status_str = "WAITING FOR WIP"
            status_code = "ORANGE"
        elif allocatable_wip < required_daily_rate or executable_tg < required_daily_rate:
            status_str = "PARTIALLY AVAILABLE"
            status_code = "YELLOW"
        else:
            status_str = "ON TRACK"
            status_code = "GREEN"

        return {
            "section_id": sec_id,
            "section_name": sec_name,
            "route_id": route.id,
            "is_applicable": True,
            "is_active": True,
            "is_required": True,
            "remaining_balance": curr_balance,
            "total_accepted": float(cum_accepted),
            "remaining_working_days": rem_workdays,
            "working_dates": working_dates,
            "required_daily_rate": required_daily_rate,
            "minimum_daily_target": eff_min,
            "maximum_daily_target": eff_max,
            "calculation_mode": eff_mode,
            "allocatable_wip": allocatable_wip,
            "available_on_hand": allocatable_wip,
            "executable_tg": executable_tg,
            "executable_daily_target": executable_tg,
            "status": status_str,
            "status_code": status_code,
            "feasibility": feasibility
        }

    @classmethod
    def allocate_section_targets(
        cls,
        order_quantity: float,
        cumulative_accepted: float,
        current_allocatable_wip: float,
        working_dates: List[date],
        effective_min: int = 0,
        effective_max: Optional[int] = 0,
        calculation_mode: str = "BALANCED"
    ) -> Dict[date, int]:
        """
        Intelligent Production Planning Target Engine (Footwear ERP Specification):
        - Planned daily target cannot exceed available planned production quantity.
        - Target allocation must respect current WIP availability.
        - Does NOT repeat the same WIP quantity across days: each allocation reduces allocatable WIP.
        - Supports Calculation Modes:
          * Mode A — BALANCED: Distribute evenly across remaining working dates, respecting min target.
          * Mode B — MINIMUM_DRIVEN: Prefer configured minimum daily target, completing balance in fewer days.
          * Mode C — SHIPMENT_PRIORITY: Target required rate to meet deadline, constrained by capacity.
          * Mode D — MANUAL: Respects user-entered quantities with constraint checks.
        - Applied Constraints:
          * Upper limit: Maximum Daily Target (effective_max) if > 0.
          * Lower limit: Minimum Daily Target preference when WIP allows.
          * Never exceeds remaining balance: final day balance < minimum schedules only remaining balance.
          * Downstream sections with 0 On Hand receive 0 planned target until WIP becomes available.
          * Integer arithmetic only. Non-working days receive 0.
        """
        sorted_dates = sorted(working_dates)
        schedule: Dict[date, int] = {}
        if not sorted_dates:
            return schedule

        rem_balance = max(0, int(round(order_quantity)) - int(round(cumulative_accepted)))
        allocatable_wip = max(0, int(round(current_allocatable_wip)))
        eff_min = max(0, int(effective_min or 0))
        eff_max = max(0, int(effective_max or 0))
        mode = (calculation_mode or "BALANCED").upper()

        for idx, d in enumerate(sorted_dates):
            rem_days = len(sorted_dates) - idx
            if rem_balance <= 0 or allocatable_wip <= 0:
                schedule[d] = 0
                continue

            balanced_target = (rem_balance + rem_days - 1) // rem_days

            if mode in ("MINIMUM_DRIVEN", "MODE_B"):
                # Mode B: Prefer the configured minimum daily target and allocate production until planned qty is allocated
                desired_target = eff_min if eff_min > 0 else balanced_target
            elif mode in ("SHIPMENT_PRIORITY", "MODE_C"):
                # Mode C: Attempt to finish remaining required qty by shipment deadline
                desired_target = balanced_target
            else:  # "BALANCED" (Mode A default)
                desired_target = max(balanced_target, eff_min)

            # Daily executable/planned target cannot exceed remaining balance or available WIP
            daily_tg = min(desired_target, rem_balance, allocatable_wip)

            # Apply maximum capacity cap if configured (> 0)
            if eff_max > 0:
                daily_tg = min(daily_tg, eff_max)

            schedule[d] = daily_tg
            rem_balance -= daily_tg
            allocatable_wip -= daily_tg

        return schedule

    @classmethod
    def calculate_forecast_completion_date(
        cls,
        remaining_balance: float,
        daily_rate: float,
        from_date: Optional[date] = None,
        working_dates: Optional[List[date]] = None
    ) -> Optional[date]:
        """
        Forecasts expected completion date based on daily production rate.
        """
        if remaining_balance <= 0.0:
            return from_date or cls.get_running_date()
        if daily_rate <= 0.0:
            return None
        
        needed_days = math.ceil(remaining_balance / daily_rate)
        if working_dates and len(working_dates) >= needed_days:
            return working_dates[needed_days - 1]
        
        start = from_date or cls.get_running_date()
        return start + timedelta(days=needed_days)

    @classmethod
    def generate_future_daily_plan(
        cls,
        db: Session,
        order: Order,
        operation: OrderOperation,
        as_of_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates dynamic continuous future daily planning schedule.
        Columns: Date | Day | Opening Balance | Auto Target | Actual | Closing Balance | Status

        Dynamically recalculates:
        - For past / today: displays actual entered production and resulting closing balance.
        - For upcoming days: recalculates auto target from current outstanding balance
          and remaining available days, reducing balance until 0 by delivery date.
        """
        running_date = as_of_date or cls.get_running_date()
        rem_days, working_dates = cls.calculate_remaining_days(
            db=db,
            start_date=order.production_start_date,
            delivery_date=order.current_delivery_date,
            as_of_date=running_date
        )

        # Get non-reversed production entries for this operation
        entries = db.query(DailyProductionEntry).filter(
            DailyProductionEntry.operation_id == operation.id,
            DailyProductionEntry.is_reversed == False
        ).order_by(DailyProductionEntry.entry_date.asc()).all()

        total_accepted = sum(e.accepted_quantity for e in entries)
        total_rejected = sum(e.rejected_quantity for e in entries)

        # Current balance as of running date
        current_balance = cls.calculate_balance(operation.required_quantity, total_accepted)

        # Build map of actual production by date
        actual_by_date: Dict[date, float] = {}
        rejected_by_date: Dict[date, float] = {}
        remarks_by_date: Dict[date, str] = {}
        for e in entries:
            actual_by_date[e.entry_date] = actual_by_date.get(e.entry_date, 0.0) + e.accepted_quantity
            rejected_by_date[e.entry_date] = rejected_by_date.get(e.entry_date, 0.0) + e.rejected_quantity
            if e.remarks:
                remarks_by_date[e.entry_date] = e.remarks

        plan_rows: List[Dict[str, Any]] = []

        if not working_dates:
            # Overdue or outside range
            if current_balance > 0:
                plan_rows.append({
                    "date": running_date,
                    "day_name": running_date.strftime("%A"),
                    "opening_balance": current_balance,
                    "auto_target": "OVERDUE",
                    "auto_target_numeric": 0.0,
                    "actual": actual_by_date.get(running_date, 0.0),
                    "closing_balance": current_balance,
                    "variance": 0.0,
                    "status": "OVERDUE",
                    "remarks": f"Overdue balance: {current_balance:,.0f} pairs"
                })
            return plan_rows

        # Calculate opening balance for today before today's entries
        today_actual = actual_by_date.get(running_date, 0.0)
        # Running balance that gets planned forward starting from today
        active_balance = current_balance + today_actual
        remaining_slots = len(working_dates)

        cum_accepted_so_far = 0.0

        for idx, d in enumerate(working_dates):
            opening = round(active_balance, 2)
            avail_days = max(1, remaining_slots - idx)
            target = cls.calculate_daily_target(opening, avail_days)

            has_actual = d in actual_by_date
            act_qty = actual_by_date.get(d, 0.0)
            rej_qty = rejected_by_date.get(d, 0.0)

            if d < running_date or (d == running_date and has_actual):
                # Historical or today's recorded actual
                closing = cls.calculate_balance(opening, act_qty)
                variance = cls.calculate_daily_variance(act_qty, target)
                cum_accepted_so_far += act_qty
                active_balance = closing
                status_str = "COMPLETED" if closing <= 0 else ("AHEAD" if variance > 0 else "BEHIND" if variance < 0 else "ON_TARGET")
            else:
                # Future projected day
                planned_production = min(opening, target) if idx < remaining_slots - 1 else opening
                closing = round(max(0.0, opening - planned_production), 2)
                variance = 0.0
                active_balance = closing
                status_str = "SCHEDULED"

            plan_rows.append({
                "date": d,
                "day_name": d.strftime("%A"),
                "opening_balance": opening,
                "auto_target": int(target) if target > 0 else (0 if opening <= 0 else "OVERDUE"),
                "auto_target_numeric": float(target),
                "actual": act_qty if has_actual else None,
                "rejected": rej_qty if has_actual else 0.0,
                "closing_balance": closing,
                "variance": variance if has_actual else None,
                "status": status_str,
                "remarks": remarks_by_date.get(d)
            })

        return plan_rows

    @classmethod
    def calculate_order_plan(
        cls,
        db: Session,
        order: Order,
        as_of_date: Optional[date] = None,
        calendar_id: Optional[int] = None,
        use_working_days_only: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive authoritative order planning calculations.
        Returns all business metrics required by API, dashboard, order details, and exports:
        - Balance quantity
        - Remaining days
        - Auto daily target
        - Today's actual
        - Today's variance
        - Process-wise breakdown
        - Overall status
        """
        running_date = as_of_date or cls.get_running_date()
        rem_days, working_dates = cls.calculate_remaining_days(
            db=db,
            start_date=order.production_start_date,
            delivery_date=order.current_delivery_date,
            calendar_id=calendar_id,
            as_of_date=running_date,
            use_working_days_only=use_working_days_only
        )

        routes_data = []
        has_any_entries = False
        today_total_actual_order = 0.0
        required_route_pairs = []
        highest_daily_target = 0.0

        for r in order.routes:
            if not r.section or not r.section.is_active:
                continue
            route_is_required = (r.status == SectionRouteStatus.REQUIRED)
            ops_data = []

            for op in r.operations:
                entries = db.query(DailyProductionEntry).filter(
                    DailyProductionEntry.operation_id == op.id,
                    DailyProductionEntry.is_reversed == False
                ).all()

                if entries:
                    has_any_entries = True

                cum_accepted = sum(e.accepted_quantity for e in entries)
                cum_rejected = sum(e.rejected_quantity for e in entries)

                today_entries = [e for e in entries if e.entry_date == running_date]
                today_acc = sum(e.accepted_quantity for e in today_entries)
                if route_is_required:
                    today_total_actual_order += today_acc
                comps_data = []
                all_comps_done = True if op.components else None
                for comp in op.components:
                    comp_entries = [e for e in entries if e.component_id == comp.id]
                    c_acc = sum(e.accepted_quantity for e in comp_entries)
                    c_rej = sum(e.rejected_quantity for e in comp_entries)
                    c_bal = max(0.0, comp.required_total_qty - c_acc)
                    pair_eq = round(c_acc / comp.pieces_per_pair, 2) if comp.pieces_per_pair > 0 else c_acc
                    if c_bal > 0:
                        all_comps_done = False
                    comps_data.append({
                        "id": comp.id,
                        "operation_id": comp.operation_id,
                        "component_name": comp.component_name,
                        "unit": comp.unit,
                        "pieces_per_pair": comp.pieces_per_pair,
                        "required_total_qty": comp.required_total_qty,
                        "accepted_total_qty": c_acc,
                        "rejected_total_qty": c_rej,
                        "balance_total_qty": c_bal,
                        "pair_equivalent_accepted": pair_eq,
                    })

                if op.components:
                    effective_pairs = min([c["pair_equivalent_accepted"] for c in comps_data]) if comps_data else 0.0
                    cum_accepted = effective_pairs
                    balance = cls.calculate_balance(op.required_quantity, effective_pairs)
                    if not all_comps_done:
                        op_status = OperationStatus.IN_PROGRESS if cum_accepted > 0 else OperationStatus.PENDING
                    elif balance <= 0 and op.required_quantity > 0:
                        op_status = OperationStatus.COMPLETED
                    else:
                        op_status = OperationStatus.IN_PROGRESS if cum_accepted > 0 else OperationStatus.PENDING
                else:
                    balance = cls.calculate_balance(op.required_quantity, cum_accepted)
                    if balance <= 0 and op.required_quantity > 0:
                        op_status = OperationStatus.COMPLETED
                    elif cum_accepted > 0:
                        op_status = OperationStatus.IN_PROGRESS
                    else:
                        op_status = OperationStatus.PENDING

                pct = 100.0 if op.required_quantity <= 0 else min(100.0, max(0.0, round((cum_accepted / op.required_quantity) * 100.0, 2)))
                daily_target = cls.calculate_daily_target(balance, rem_days)

                if route_is_required and daily_target > highest_daily_target:
                    highest_daily_target = daily_target

                today_var = cls.calculate_daily_variance(today_acc, daily_target)

                # Overproduction check
                is_overproduced = (cum_accepted > op.required_quantity)
                overproduction_qty = max(0.0, cum_accepted - op.required_quantity)

                ops_data.append({
                    "id": op.id,
                    "route_id": op.route_id,
                    "operation_name": op.operation_name,
                    "sequence_order": op.sequence_order,
                    "unit": op.unit,
                    "required_quantity": op.required_quantity,
                    "completed_quantity": cum_accepted,
                    "rejected_quantity": cum_rejected,
                    "balance_quantity": balance,
                    "completion_percentage": pct,
                    "daily_target": daily_target,
                    "today_actual": today_acc,
                    "today_variance": today_var,
                    "is_overproduced": is_overproduced,
                    "overproduction_quantity": overproduction_qty,
                    "start_date": op.start_date,
                    "expected_finish_date": op.expected_finish_date,
                    "status": op_status,
                    "notes": op.notes,
                    "components": comps_data,
                })

            # Check section completion
            section_completed = True
            if route_is_required:
                if not ops_data:
                    section_completed = False
                else:
                    for o in ops_data:
                        if o["status"] != OperationStatus.COMPLETED and o["balance_quantity"] > 0:
                            section_completed = False
                            break
                        for comp in o.get("components", []):
                            if comp.get("balance_total_qty", 0) > 0:
                                section_completed = False
                                break
                        if not section_completed:
                            break
                    limiting_op_pairs = min(o["completed_quantity"] for o in ops_data) if ops_data else 0.0
                    required_route_pairs.append(limiting_op_pairs)

            sec_name = r.section.name if r.section else f"Section {r.section_id}"
            cat_name = r.section.category.name if (r.section and r.section.category) else "General"

            routes_data.append({
                "id": r.id,
                "order_id": r.order_id,
                "section_id": r.section_id,
                "section_name": sec_name,
                "category_name": cat_name,
                "status": r.status,
                "sequence_order": r.sequence_order,
                "has_components": r.has_components,
                "notes": r.notes,
                "operations": ops_data,
                "is_completed": section_completed,
            })

        # Category-to-category flow calculation (Section 22 & 27)
        category_flow = cls.calculate_category_flow(db, order, as_of_date=running_date)
        if category_flow:
            final_cat = category_flow[-1]
            order_completed_pairs = final_cat["completed_output"]
            outstanding_pairs = cls.calculate_balance(order.total_quantity, order_completed_pairs)
        else:
            order_completed_pairs = min(required_route_pairs) if required_route_pairs else 0.0
            outstanding_pairs = cls.calculate_balance(order.total_quantity, order_completed_pairs)

        order_pct = 100.0 if order.total_quantity <= 0 else min(100.0, max(0.0, round((order_completed_pairs / order.total_quantity) * 100.0, 2)))

        # Check capacity feasibility across sections (Requirement 18 & Test J)
        has_capacity_conflict = False
        if rem_days > 0 and outstanding_pairs > 0:
            for r in order.routes:
                if not r.section or not r.section.is_active or r.status != SectionRouteStatus.REQUIRED:
                    continue
                rules = cls.get_effective_target_rules(db, r.section_id, r)
                sec_max = rules.get("maximum_daily_target", 0)
                if sec_max and sec_max > 0:
                    feas = cls.evaluate_capacity_feasibility(
                        remaining_balance=outstanding_pairs,
                        remaining_workdays=rem_days,
                        maximum_daily_target=sec_max
                    )
                    if not feas.get("is_feasible", True):
                        has_capacity_conflict = True
                        break

        # Status determination
        is_complete = (outstanding_pairs <= 0 and order_completed_pairs >= order.total_quantity)
        is_overdue = (rem_days <= 0 and outstanding_pairs > 0)
        is_at_risk = (not is_overdue and not is_complete and (rem_days <= 3 or highest_daily_target > (order.total_quantity * 0.3) or has_capacity_conflict))

        if order.status in [OrderStatus.CLOSED, OrderStatus.ON_HOLD, OrderStatus.ARCHIVED, OrderStatus.CANCELLED]:
            computed_status = order.status
        elif is_complete:
            computed_status = OrderStatus.PRODUCTION_COMPLETE
        elif is_overdue:
            computed_status = OrderStatus.OVERDUE
        elif is_at_risk:
            computed_status = OrderStatus.AT_RISK
        elif has_any_entries:
            computed_status = OrderStatus.IN_PRODUCTION
        else:
            computed_status = OrderStatus.SCHEDULED

        # Order-level auto daily target: based on limiting required balance / remaining days
        order_daily_target = cls.calculate_daily_target(outstanding_pairs, rem_days)
        order_variance = cls.calculate_daily_variance(today_total_actual_order, order_daily_target)

        # Forecast completion date
        forecast_date = None
        if order_daily_target > 0:
            forecast_date = cls.calculate_forecast_completion_date(
                remaining_balance=outstanding_pairs,
                daily_rate=order_daily_target,
                from_date=running_date,
                working_dates=working_dates
            )

        revisions_data = [
            {
                "id": rev.id,
                "order_id": rev.order_id,
                "previous_delivery_date": rev.previous_delivery_date,
                "revised_delivery_date": rev.revised_delivery_date,
                "reason": rev.reason,
                "revised_by_id": rev.revised_by_id,
                "revised_by_name": rev.revised_by_user.full_name if rev.revised_by_user else None,
                "created_at": rev.created_at,
            }
            for rev in order.delivery_revisions
        ]

        return {
            "id": order.id,
            "order_id": order.id,
            "order_code": order.order_code,
            "buyer_id": order.buyer_id,
            "buyer_name": order.buyer.name if order.buyer else None,
            "customer_ref": order.customer_ref,
            "po_number": order.po_number,
            "style_model": order.style_model,
            "description": order.description,
            "total_quantity": order.total_quantity,
            "order_quantity": order.total_quantity,
            "produced_quantity": order_completed_pairs,
            "balance_quantity": outstanding_pairs,
            "original_order_date": order.original_order_date,
            "production_start_date": order.production_start_date,
            "original_delivery_date": order.original_delivery_date,
            "current_delivery_date": order.current_delivery_date,
            "shipment_date": order.current_delivery_date,
            "running_date": running_date,
            "priority": order.priority,
            "status": computed_status,
            "notes": order.notes,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "remaining_working_days": rem_days,
            "remaining_days": rem_days,
            "daily_target": order_daily_target,
            "today_actual": today_total_actual_order,
            "today_variance": order_variance,
            "completed_pairs": order_completed_pairs,
            "outstanding_pairs": outstanding_pairs,
            "overdue_balance": outstanding_pairs if is_overdue else 0.0,
            "completion_percentage": order_pct,
            "is_at_risk": is_at_risk,
            "is_overdue": is_overdue,
            "forecast_completion_date": forecast_date,
            "routes": routes_data,
            "delivery_revisions": revisions_data,
            "categories": category_flow,
        }

    @classmethod
    def recalculate_order_targets(cls, db: Session, order_id: int) -> Dict[str, Any]:
        """Triggers recalculation and returns refreshed planning values."""
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order with ID {order_id} not found")
        return cls.calculate_order_plan(db, order)

    @classmethod
    def get_order_category_structure(cls, order: Order) -> List[Dict[str, Any]]:
        """
        Extracts sequenced categories for an order that have at least one REQUIRED section/route.
        Sorted by category.display_order.
        If an order does not require Category 1 and starts from Category 2,
        Category 2 becomes the initial starting point (Section 5).
        """
        cats_dict: Dict[int, Dict[str, Any]] = {}
        for r in order.routes:
            if not r.section or not r.section.category:
                continue
            if not r.section.is_active:
                continue
            cat = r.section.category
            if cat.id not in cats_dict:
                cats_dict[cat.id] = {
                    "category": cat,
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "display_order": cat.display_order if cat.display_order is not None else 0,
                    "routes": [],
                    "required_routes": [],
                    "required_operations": [],
                    "all_operations": [],
                }
            cats_dict[cat.id]["routes"].append(r)
            for op in r.operations:
                cats_dict[cat.id]["all_operations"].append(op)
            if r.status == SectionRouteStatus.REQUIRED:
                cats_dict[cat.id]["required_routes"].append(r)
                for op in r.operations:
                    cats_dict[cat.id]["required_operations"].append(op)

        active_cats = [
            c_info for c_info in cats_dict.values()
            if len(c_info["required_routes"]) > 0
        ]
        if not active_cats:
            active_cats = list(cats_dict.values())

        active_cats.sort(key=lambda c: (c["display_order"], c["category_id"]))
        return active_cats

    @classmethod
    def calculate_category_completed_output(
        cls,
        category_info: Dict[str, Any],
        entries_by_op: Dict[int, List[DailyProductionEntry]]
    ) -> float:
        """
        A category's completed output to the next category is based on the common quantity
        that has completed all required processes for that category:
        Category Completed Output = MIN(completed of each required process in that category).
        Not-required processes are excluded from the MIN calculation (Sections 9, 10, 11, 12).
        """
        req_ops = category_info.get("required_operations", [])
        if not req_ops:
            return 0.0

        op_completions: List[float] = []
        for op in req_ops:
            op_entries = entries_by_op.get(op.id, [])
            if op.components:
                comp_eqs = []
                for comp in op.components:
                    comp_ents = [e for e in op_entries if e.component_id == comp.id]
                    acc = sum(e.accepted_quantity for e in comp_ents)
                    factor = comp.pieces_per_pair if comp.pieces_per_pair > 0 else 1.0
                    comp_eqs.append(acc / factor)
                effective_pairs = min(comp_eqs) if comp_eqs else 0.0
                op_completions.append(effective_pairs)
            else:
                acc = sum(e.accepted_quantity for e in op_entries)
                op_completions.append(acc)

        return min(op_completions) if op_completions else 0.0

    @classmethod
    def calculate_category_flow(
        cls,
        db: Session,
        order: Order,
        as_of_date: Optional[date] = None,
        same_day_transfer: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Authoritative Category-to-Category On-Hand WIP Flow.
        Category 1 Output -> Category 2 Incoming On Hand.
        Category 2 Output -> Category 3 Incoming On Hand.
        Maintains:
        - Opening On Hand
        - Incoming from Previous Category
        - Available On Hand = Opening + Incoming
        - Actual Production / Consumed
        - Output Completed = MIN(required operations)
        - Closing On Hand / Current On Hand = MAX(0, Available - Consumed)
        - Balance = MAX(0, Order Qty - Output Completed)
        - Status & WIP Status
        """
        cat_structure = cls.get_order_category_structure(order)
        if not cat_structure:
            return []

        query = db.query(DailyProductionEntry).filter(
            DailyProductionEntry.order_id == order.id,
            DailyProductionEntry.is_reversed == False
        )
        if as_of_date:
            query = query.filter(DailyProductionEntry.entry_date <= as_of_date)
        entries = query.all()

        entries_by_op: Dict[int, List[DailyProductionEntry]] = {}
        for e in entries:
            entries_by_op.setdefault(e.operation_id, []).append(e)

        flow_results: List[Dict[str, Any]] = []

        for idx, cat_info in enumerate(cat_structure):
            cat_out = cls.calculate_category_completed_output(cat_info, entries_by_op)

            req_ops = cat_info.get("required_operations", [])
            cat_actual_consumed = 0.0
            if req_ops:
                op_acc_list = [
                    sum(e.accepted_quantity for e in entries_by_op.get(op.id, []))
                    for op in req_ops
                ]
                cat_actual_consumed = max(op_acc_list) if op_acc_list else 0.0

            if idx == 0:
                opening_oh = float(order.total_quantity)
                incoming = 0.0
                available_oh = opening_oh
                closing_oh = max(0.0, available_oh - cat_actual_consumed)
            else:
                prev_cat_output = flow_results[idx - 1]["completed_output"]
                incoming = prev_cat_output
                opening_oh = 0.0
                available_oh = incoming
                closing_oh = max(0.0, available_oh - cat_actual_consumed)

            balance = cls.calculate_balance(order.total_quantity, cat_out)

            if balance <= 0.0 and cat_out >= order.total_quantity:
                status_str = "COMPLETED"
                wip_status_str = "COMPLETED"
            elif available_oh <= 0.0:
                status_str = "WAITING FOR WIP"
                wip_status_str = "WAITING FOR WIP"
            elif available_oh < balance:
                status_str = "PARTIALLY AVAILABLE"
                wip_status_str = "PARTIALLY AVAILABLE"
            else:
                status_str = "READY"
                wip_status_str = "READY"

            flow_results.append({
                "category_id": cat_info["category_id"],
                "category_name": cat_info["category_name"],
                "display_order": cat_info["display_order"],
                "required_quantity": float(order.total_quantity),
                "opening_on_hand": round(opening_oh, 2),
                "incoming_wip": round(incoming, 2),
                "available_on_hand": round(available_oh, 2),
                "actual_production": round(cat_actual_consumed, 2),
                "completed_output": round(cat_out, 2),
                "closing_on_hand": round(closing_oh, 2),
                "current_on_hand": round(closing_oh, 2),
                "balance": round(balance, 2),
                "status": status_str,
                "wip_status": wip_status_str,
            })

        return flow_results

    @classmethod
    def get_available_on_hand_for_operation(
        cls,
        db: Session,
        operation: OrderOperation,
        as_of_date: Optional[date] = None
    ) -> float:
        """
        Returns available On Hand for an operation's section/category (Section 8 & 38).
        Enforces: Production cannot exceed available On Hand without authorized override.
        """
        route = operation.route
        if not route or not route.order:
            return float("inf")
        order = route.order

        from app.services.wip_planning_engine import WIPPlanningEngine

        # Check if order has explicit serial workflow configured by the user
        has_serials = any(r.serial_no is not None for r in order.routes if r.section and r.section.is_active)

        # 1. Multiple operations within the SAME route (e.g. 3 printing operations)
        if len(route.operations) > 1:
            op_entries = [e for e in operation.entries if not e.is_reversed and (as_of_date is None or e.entry_date <= as_of_date)]
            op_cum = sum(e.accepted_quantity for e in op_entries)

            if has_serials:
                raw_wip = WIPPlanningEngine.get_available_wip_for_route(db, order, route.id, as_of_date=as_of_date, exclude_target_cum=True)
            else:
                cat_flow = cls.calculate_category_flow(db, order, as_of_date=as_of_date)
                route_cat_id = route.section.category_id if route.section else None
                this_cat = next((c for c in cat_flow if c["category_id"] == route_cat_id), None) if route_cat_id else None
                raw_wip = this_cat["available_on_hand"] if this_cat else float(order.total_quantity)

            return max(0.0, raw_wip - op_cum)

        # 2. If it's a serial workflow order, strictly follow WIPPlanningEngine
        if has_serials:
            return WIPPlanningEngine.get_available_wip_for_route(db, order, route.id, as_of_date=as_of_date)

        # 3. Legacy category flow order: check if multiple routes share the same category (parallel processes)
        route_cat_id = route.section.category_id if route.section else None
        same_cat_routes = [r for r in order.routes if r.section and r.section.is_active and r.section.category_id == route_cat_id] if route_cat_id else []
        if len(same_cat_routes) > 1:
            cat_flow = cls.calculate_category_flow(db, order, as_of_date=as_of_date)
            this_cat = next((c for c in cat_flow if c["category_id"] == route_cat_id), None)
            if this_cat:
                op_entries = [e for e in operation.entries if not e.is_reversed and (as_of_date is None or e.entry_date <= as_of_date)]
                op_cum = sum(e.accepted_quantity for e in op_entries)
                return max(0.0, this_cat["available_on_hand"] - op_cum)

        return WIPPlanningEngine.get_available_wip_for_route(db, order, route.id, as_of_date=as_of_date)

    @classmethod
    def generate_category_flow_planning_sheet(
        cls,
        db: Session,
        order_id: Optional[int] = None,
        buyer_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        as_of_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates the automatic multi-day Production Planning Sheet based on
        Category-to-Category On-Hand WIP flow (Sections 13, 14, 15, 16, 20, 21, 23, 24).
        """
        running_date = as_of_date or cls.get_running_date()
        cal = CalendarService.get_active_calendar(db)
        same_day_transfer = getattr(cal, "same_day_category_transfer", False)

        orders_query = db.query(Order).filter(
            Order.status.notin_([OrderStatus.CLOSED, OrderStatus.PRODUCTION_COMPLETE])
        )
        if order_id:
            orders_query = orders_query.filter(Order.id == order_id)
        if buyer_id:
            orders_query = orders_query.filter(Order.buyer_id == buyer_id)
        orders = orders_query.order_by(Order.current_delivery_date.asc(), Order.id.asc()).all()

        sheet_rows: List[Dict[str, Any]] = []

        for ord_obj in orders:
            cat_structure = cls.get_order_category_structure(ord_obj)
            if not cat_structure:
                continue

            all_entries = db.query(DailyProductionEntry).filter(
                DailyProductionEntry.order_id == ord_obj.id,
                DailyProductionEntry.is_reversed == False
            ).all()

            plan_start = ord_obj.production_start_date or running_date
            if start_date:
                plan_start = max(plan_start, start_date)
            plan_end = ord_obj.current_delivery_date
            if end_date:
                plan_end = min(plan_end, end_date)

            entry_dates = {e.entry_date for e in all_entries}
            num_days = max(1, (plan_end - plan_start).days + 1) if plan_end >= plan_start else 1
            dates_set = {plan_start + timedelta(days=i) for i in range(num_days)}
            dates_set.update(d for d in entry_dates if (start_date is None or d >= start_date) and (end_date is None or d <= plan_end))
            planning_dates = sorted(list(dates_set))

            cat_closing_history: Dict[int, Dict[date, float]] = {c["category_id"]: {} for c in cat_structure}
            cat_output_history: Dict[int, Dict[date, float]] = {c["category_id"]: {} for c in cat_structure}
            op_balance: Dict[int, float] = {}
            for c in cat_structure:
                for op in c["all_operations"]:
                    op_balance[op.id] = float(op.required_quantity)

            if planning_dates:
                earliest_d = planning_dates[0]
                for e in all_entries:
                    if e.entry_date < earliest_d and e.operation_id in op_balance:
                        op_balance[e.operation_id] = max(0.0, op_balance[e.operation_id] - e.accepted_quantity)

            prev_date: Optional[date] = None

            for d_idx, d in enumerate(planning_dates):
                rem_days = CalendarService.get_remaining_working_days(
                    db=db,
                    start_date=d,
                    delivery_date=ord_obj.current_delivery_date,
                    calendar_id=cal.id,
                    as_of_date=d
                )[0]

                for cat_idx, cat_info in enumerate(cat_structure):
                    cat_id = cat_info["category_id"]

                    if d_idx == 0:
                        if cat_idx == 0:
                            opening_oh = float(ord_obj.total_quantity)
                        else:
                            opening_oh = 0.0
                    else:
                        opening_oh = cat_closing_history[cat_id].get(prev_date, 0.0)

                    if cat_idx == 0:
                        incoming = 0.0
                    else:
                        prev_cat_id = cat_structure[cat_idx - 1]["category_id"]
                        if same_day_transfer:
                            incoming = cat_output_history[prev_cat_id].get(d, 0.0)
                        else:
                            incoming = cat_output_history[prev_cat_id].get(prev_date, 0.0) if prev_date else 0.0

                    available_oh = max(0.0, opening_oh + incoming)
                    op_outputs_today: List[float] = []
                    op_closings_today: List[float] = []

                    for route in cat_info["routes"]:
                        route_required = (route.status == SectionRouteStatus.REQUIRED)
                        for op in route.operations:
                            curr_bal = op_balance.get(op.id, 0.0)
                            daily_tgt = cls.calculate_daily_target(curr_bal, rem_days) if route_required else 0.0
                            exec_tgt = min(daily_tgt, available_oh) if route_required else 0.0

                            ents_on_d = [e for e in all_entries if e.operation_id == op.id and e.entry_date == d]
                            if ents_on_d:
                                act_qty = sum(e.accepted_quantity for e in ents_on_d)
                                has_act = True
                            elif d < running_date:
                                act_qty = 0.0
                                has_act = True
                            else:
                                act_qty = None
                                has_act = False

                            eff_consumed = act_qty if has_act else exec_tgt
                            closing_oh = max(0.0, available_oh - eff_consumed)
                            out_completed = eff_consumed

                            if route_required:
                                op_outputs_today.append(out_completed)
                                op_closings_today.append(closing_oh)
                                new_bal = max(0.0, curr_bal - eff_consumed)
                                op_balance[op.id] = new_bal
                            else:
                                new_bal = 0.0

                            variance = round(act_qty - daily_tgt, 2) if has_act else None

                            if not route_required:
                                wip_status = "NOT REQUIRED"
                                prod_status = "NOT REQUIRED"
                            elif curr_bal <= 0 or (has_act and new_bal <= 0):
                                wip_status = "COMPLETED"
                                prod_status = "COMPLETED"
                            elif rem_days <= 0 and curr_bal > 0:
                                wip_status = "OVERDUE"
                                prod_status = "OVERDUE"
                            elif available_oh <= 0 and daily_tgt > 0:
                                wip_status = "WAITING FOR WIP"
                                prod_status = "WAITING FOR WIP"
                            elif available_oh < daily_tgt:
                                wip_status = "PARTIALLY AVAILABLE"
                                prod_status = "BEHIND TARGET" if (has_act and act_qty < daily_tgt) else "PARTIALLY AVAILABLE"
                            else:
                                wip_status = "READY"
                                if has_act:
                                    if act_qty > daily_tgt:
                                        prod_status = "AHEAD"
                                    elif act_qty == daily_tgt:
                                        prod_status = "ON TARGET"
                                    else:
                                        prod_status = "BEHIND TARGET"
                                else:
                                    prod_status = "READY"

                            sheet_rows.append({
                                "date": d,
                                "buyer_id": ord_obj.buyer_id,
                                "buyer_name": ord_obj.buyer.name if ord_obj.buyer else "N/A",
                                "order_id": ord_obj.id,
                                "order_code": ord_obj.order_code,
                                "order_quantity": float(ord_obj.total_quantity),
                                "category_id": cat_info["category_id"],
                                "category_name": cat_info["category_name"],
                                "section_id": route.section_id,
                                "section_name": route.section.name if route.section else f"Section {route.section_id}",
                                "operation_id": op.id,
                                "operation_name": op.operation_name,
                                "opening_on_hand": round(opening_oh, 2),
                                "incoming_wip": round(incoming, 2),
                                "available_on_hand": round(available_oh, 2),
                                "daily_target": float(daily_tgt),
                                "executable_target": float(exec_tgt),
                                "actual_production": float(act_qty) if act_qty is not None else None,
                                "completed_output": float(out_completed),
                                "closing_on_hand": round(closing_oh, 2),
                                "balance": round(new_bal, 2),
                                "variance": variance,
                                "wip_status": wip_status,
                                "production_status": prod_status,
                                "shipment_date": ord_obj.current_delivery_date,
                            })

                    cat_out_d = min(op_outputs_today) if op_outputs_today else 0.0
                    cat_close_d = min(op_closings_today) if op_closings_today else closing_oh
                    cat_output_history[cat_id][d] = cat_out_d
                    cat_closing_history[cat_id][d] = cat_close_d

                prev_date = d

        return sheet_rows

    @classmethod
    def generate_order_matrix_planning_sheet(
        cls,
        db: Session,
        order_id: int,
        as_of_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Generates the Date-Wise TG / ON HAND / O/T Planning Matrix Sheet for an order.
        Columns: Date | <SEC1> T/G | <SEC1> ON HAND | <SEC1> O/T | <SEC2> ...
        Category WIP Sequence: Category 1 (Cutting) -> Category 2 (Preparation) -> Category 3 (Finishing).
        Category 2 Completion: MIN(required processes) transferred as usable On Hand to Category 3.
        Summary Row: Total T/G = SUM(Daily T/G), Final On Hand = Closing On Hand on last date, Total O/T = SUM(Daily O/T).
        Enforces Exact Daily Target Distribution: SUM(Daily Targets) == Current Balance exactly!
        """
        running_date = as_of_date or cls.get_running_date()
        cal = CalendarService.get_active_calendar(db)
        exceptions = db.query(CalendarException).filter(CalendarException.calendar_id == cal.id).all()

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order with ID {order_id} not found")

        # 1. Date Range
        plan_start = order.production_start_date or running_date
        plan_end = order.current_delivery_date

        all_entries = db.query(DailyProductionEntry).filter(
            DailyProductionEntry.order_id == order.id,
            DailyProductionEntry.is_reversed == False
        ).all()

        if all_entries:
            min_ent_date = min(e.entry_date for e in all_entries)
            if min_ent_date < plan_start:
                plan_start = min_ent_date
            max_ent_date = max(e.entry_date for e in all_entries)
            if max_ent_date > plan_end:
                plan_end = max_ent_date

        num_days = max(1, (plan_end - plan_start).days + 1) if plan_end >= plan_start else 1
        planning_dates = [plan_start + timedelta(days=i) for i in range(num_days)]

        # 2. Extract sections & order routes
        routes = list(order.routes)
        routes.sort(key=lambda r: (
            r.sequence_order if (r.sequence_order and r.sequence_order > 0) else 999,
            r.section.category.display_order if (r.section and r.section.category) else 999,
            r.section.display_order if r.section else 999
        ))

        sections_meta = []
        for r in routes:
            if not r.section:
                continue
            if not r.section.is_active:
                continue
            if r.status != SectionRouteStatus.REQUIRED:
                continue
            sec_name = r.section.name.upper()
            cat = r.section.category
            pid = getattr(r.section, "planning_id", None) or getattr(r.section, "display_order", None) or r.section.id
            sections_meta.append({
                "route_id": r.id,
                "section_id": r.section.id,
                "planning_id": int(pid),
                "display_order": int(pid),
                "section_name": sec_name,
                "category_id": cat.id if cat else 0,
                "category_name": cat.name if cat else "General",
                "category_display_order": cat.display_order if cat else 0,
                "sequence_order": getattr(r, "sequence_order", 0) or 0,
                "status": r.status.value,
                "is_required": (r.status == SectionRouteStatus.REQUIRED),
                "operations": [
                    {"id": op.id, "name": op.operation_name, "required_quantity": float(op.required_quantity)}
                    for op in r.operations
                ]
            })

        # CRITICAL: Sort applicable active sections strictly by editable planning_id ASC
        sections_meta.sort(key=lambda s: (s["planning_id"], s["section_id"]))

        is_shipment_workday = CalendarService.is_working_day(order.current_delivery_date, cal, exceptions)

        if not sections_meta:
            return {
                "order_id": order.id,
                "order_code": order.order_code,
                "buyer_id": order.buyer_id,
                "buyer_name": order.buyer.name if order.buyer else "N/A",
                "style_model": order.style_model,
                "total_quantity": float(order.total_quantity),
                "order_quantity": float(order.total_quantity),
                "completed_quantity": 0.0,
                "current_balance": float(order.total_quantity),
                "production_start_date": plan_start,
                "shipment_date": plan_end,
                "running_date": running_date,
                "planning_date": cls.get_planning_date_display(running_date),
                "original_delivery_date": order.original_delivery_date,
                "remaining_working_days": 0,
                "working_days": 0,
                "working_dates": [],
                "final_balance": float(order.total_quantity),
                "total_planned_target": 0.0,
                "validation": {"target_equals_balance": True, "checks_passed": True, "message": "No sections configured"},
                "overall_status": "PENDING",
                "sections": [],
                "rows": [],
                "summary": {},
                "category_flow_summary": [],
                "order_completion_summary": {}
            }

        unique_cat_ids = []
        for s in sections_meta:
            if s["category_id"] not in unique_cat_ids:
                unique_cat_ids.append(s["category_id"])

        req_sections = [s for s in sections_meta if s["is_required"]]

        # Precalculate all working days in planning range and future working days
        all_order_workdays = [
            d for d in planning_dates
            if d <= order.current_delivery_date and CalendarService.is_working_day(d, cal, exceptions)
        ]
        future_workdays_from_running = [
            d for d in all_order_workdays
            if d >= running_date
        ]
        future_workdays_strictly_after_running = [
            d for d in all_order_workdays
            if d > running_date
        ]

        # 3. Precompute section-wise exact daily target distributions and allocatable WIP
        sec_daily_targets: Dict[str, Dict[date, int]] = {}
        sec_current_balances: Dict[str, float] = {}
        sec_allocatable_wip: Dict[str, float] = {}
        sec_future_workdays_used: Dict[str, List[date]] = {}
        sec_effective_mins: Dict[str, int] = {}
        sec_effective_maxs: Dict[str, int] = {}
        sec_calculation_modes: Dict[str, str] = {}
        sec_feasibility: Dict[str, Dict[str, Any]] = {}

        for s in sections_meta:
            s_name = s["section_name"]
            if not s["is_required"]:
                sec_daily_targets[s_name] = {}
                sec_current_balances[s_name] = 0.0
                sec_allocatable_wip[s_name] = 0.0
                sec_future_workdays_used[s_name] = []
                sec_effective_mins[s_name] = 0
                sec_effective_maxs[s_name] = 0
                sec_calculation_modes[s_name] = "BALANCED"
                sec_feasibility[s_name] = {"is_feasible": True}
                s["minimum_daily_target"] = 0
                s["maximum_daily_target"] = 0
                s["calculation_mode"] = "BALANCED"
                continue

            order_route = db.query(OrderRoute).filter(OrderRoute.id == s["route_id"]).first()
            target_calc = cls.calculate_section_target(
                db=db,
                order=order,
                route=order_route,
                as_of_date=running_date,
                production_entries=all_entries,
                calendar=cal,
                exceptions=exceptions
            )

            eff_min = target_calc["minimum_daily_target"]
            eff_max = target_calc["maximum_daily_target"]
            eff_mode = target_calc["calculation_mode"]
            allocatable_wip = target_calc["allocatable_wip"]
            curr_balance = target_calc["remaining_balance"]
            req_daily_rate = target_calc["required_daily_rate"]
            exec_daily_tg = target_calc["executable_tg"]
            sec_feasibility[s_name] = target_calc["feasibility"]

            sec_effective_mins[s_name] = eff_min
            sec_effective_maxs[s_name] = eff_max
            sec_calculation_modes[s_name] = eff_mode
            sec_current_balances[s_name] = float(curr_balance)
            sec_allocatable_wip[s_name] = float(allocatable_wip)

            s["minimum_daily_target"] = eff_min
            s["maximum_daily_target"] = eff_max
            s["calculation_mode"] = eff_mode
            s["required_daily_rate"] = req_daily_rate
            s["executable_daily_target"] = exec_daily_tg
            s["executable_tg"] = exec_daily_tg
            s["allocatable_wip"] = allocatable_wip
            s["available_on_hand"] = allocatable_wip
            s["current_balance"] = float(curr_balance)
            s["balance"] = float(curr_balance)
            s["status"] = target_calc["status"]
            s["status_code"] = target_calc["status_code"]
            s["feasibility"] = target_calc["feasibility"]

            sec_entries = [e for e in all_entries if e.route_id == s["route_id"]]
            has_today_entry = any(e.entry_date == running_date for e in sec_entries)
            past_accepted = sum(e.accepted_quantity for e in sec_entries if e.entry_date < running_date)
            today_accepted = sum(e.accepted_quantity for e in sec_entries if e.entry_date == running_date)
            total_accepted_to_date = past_accepted + today_accepted

            sec_sched: Dict[date, int] = {}

            if has_today_entry:
                # Today had production: preserve today's planned target & actual, replan future from tomorrow
                sec_future_workdays_used[s_name] = future_workdays_strictly_after_running
                today_oh = allocatable_wip + int(round(today_accepted))
                today_dist = cls.allocate_section_targets(
                    order.total_quantity, past_accepted, today_oh, future_workdays_from_running,
                    effective_min=eff_min, effective_max=eff_max, calculation_mode=eff_mode
                )
                sec_sched[running_date] = today_dist.get(running_date, 0)

                if future_workdays_strictly_after_running and curr_balance > 0 and allocatable_wip > 0:
                    future_dist = cls.allocate_section_targets(
                        order.total_quantity, total_accepted_to_date, allocatable_wip, future_workdays_strictly_after_running,
                        effective_min=eff_min, effective_max=eff_max, calculation_mode=eff_mode
                    )
                    sec_sched.update(future_dist)
            else:
                # Today has no production entered yet: today is the active starting point of the future plan
                sec_future_workdays_used[s_name] = future_workdays_from_running
                if future_workdays_from_running and curr_balance > 0 and allocatable_wip > 0:
                    future_dist = cls.allocate_section_targets(
                        order.total_quantity, total_accepted_to_date, allocatable_wip, future_workdays_from_running,
                        effective_min=eff_min, effective_max=eff_max, calculation_mode=eff_mode
                    )
                    sec_sched.update(future_dist)

            # Historical dates prior to running date:
            # If actual production was recorded, set target equal to recorded quantity.
            # If no production was recorded on that past day, do NOT hold unfulfilled target on past dates!
            for d in all_order_workdays:
                if d < running_date:
                    past_d_ents = [e for e in sec_entries if e.entry_date == d]
                    if past_d_ents:
                        sec_sched[d] = int(round(sum(e.accepted_quantity for e in past_d_ents)))
                    else:
                        sec_sched[d] = 0

            sec_daily_targets[s_name] = sec_sched

        # 4. Generate Date-Wise Matrix Rows
        matrix_rows = []
        sec_cum_output = {s["section_name"]: 0.0 for s in sections_meta}
        sec_closing_on_hand = {s["section_name"]: 0.0 for s in sections_meta}
        sec_balance = {s["section_name"]: (float(order.total_quantity) if s["is_required"] else 0.0) for s in sections_meta}
        cat_cum_completed_output = {c_id: 0.0 for c_id in unique_cat_ids}

        for d_idx, d in enumerate(planning_dates):
            is_workday = CalendarService.is_working_day(d, cal, exceptions)
            day_name = d.strftime("%A")
            rem_days = CalendarService.get_remaining_working_days(
                db=db,
                start_date=d,
                delivery_date=order.current_delivery_date,
                calendar_id=cal.id,
                as_of_date=d
            )[0]

            row_section_data = {}

            # Process all sections in sequential route order
            for s in sections_meta:
                s_name = s["section_name"]
                is_req = s["is_required"]

                if not is_req:
                    row_section_data[s_name] = {
                        "tg": 0.0,
                        "on_hand": 0.0,
                        "ot": 0.0,
                        "closing_on_hand": 0.0,
                        "balance": 0.0,
                        "status": "NOT REQUIRED",
                        "status_code": "GRAY",
                        "is_required": False
                    }
                    continue

                req_idx = req_sections.index(s)
                ents_d = [e for e in all_entries if e.route_id == s["route_id"] and e.entry_date == d]
                act_ot = sum(e.accepted_quantity for e in ents_d) if ents_d else 0.0

                if d < running_date:
                    # Past historical dates
                    if req_idx == 0:
                        avail_oh = float(order.total_quantity) if d_idx == 0 else sec_closing_on_hand[s_name]
                    else:
                        prev_sec = req_sections[req_idx - 1]
                        prev_sec_name = prev_sec["section_name"]
                        avail_oh = max(0.0, sec_cum_output[prev_sec_name] - sec_cum_output[s_name])
                    daily_tg = float(sec_daily_targets[s_name].get(d, 0)) if is_workday else 0.0
                    closing_oh = max(0.0, avail_oh - act_ot)
                    sec_closing_on_hand[s_name] = closing_oh
                    sec_cum_output[s_name] += act_ot
                    new_bal = max(0.0, float(order.total_quantity) - sec_cum_output[s_name])
                    sec_balance[s_name] = new_bal
                elif d == running_date:
                    # Today
                    if req_idx == 0:
                        avail_oh = float(order.total_quantity) if d_idx == 0 else sec_closing_on_hand[s_name]
                    else:
                        prev_sec = req_sections[req_idx - 1]
                        prev_sec_name = prev_sec["section_name"]
                        avail_oh = max(0.0, sec_cum_output[prev_sec_name] - sec_cum_output[s_name])
                    daily_tg = float(sec_daily_targets[s_name].get(d, 0)) if is_workday else 0.0
                    closing_oh = max(0.0, avail_oh - act_ot)
                    sec_closing_on_hand[s_name] = closing_oh
                    sec_cum_output[s_name] += act_ot
                    new_bal = max(0.0, float(order.total_quantity) - sec_cum_output[s_name])
                    sec_balance[s_name] = new_bal
                else:
                    # Future dates: consume from allocatable On Hand
                    avail_oh = sec_closing_on_hand[s_name]
                    daily_tg = float(sec_daily_targets[s_name].get(d, 0)) if is_workday else 0.0
                    closing_oh = max(0.0, avail_oh - daily_tg)
                    sec_closing_on_hand[s_name] = closing_oh
                    new_bal = max(0.0, sec_balance[s_name] - daily_tg)
                    sec_balance[s_name] = new_bal

                # Status evaluation
                if not is_workday:
                    status_str = "OFF"
                    code = "GRAY"
                elif new_bal <= 0:
                    status_str = "COMPLETED"
                    code = "GREEN"
                elif rem_days <= 0 and new_bal > 0:
                    status_str = "OVERDUE"
                    code = "RED"
                elif d >= running_date and avail_oh <= 0 and new_bal > 0 and daily_tg == 0:
                    status_str = "WAITING FOR WIP"
                    code = "ORANGE"
                elif d >= running_date and daily_tg > 0 and avail_oh < daily_tg:
                    status_str = "PARTIALLY AVAILABLE"
                    code = "YELLOW"
                elif act_ot >= daily_tg and daily_tg > 0:
                    status_str = "ON TARGET" if act_ot == daily_tg else "AHEAD"
                    code = "GREEN"
                elif act_ot < daily_tg and (ents_d or d < running_date):
                    status_str = "BEHIND TARGET"
                    code = "YELLOW"
                elif d > running_date and daily_tg > 0:
                    status_str = "ON TRACK"
                    code = "GREEN"
                elif d > running_date and daily_tg == 0 and avail_oh <= 0:
                    status_str = "WAITING FOR WIP"
                    code = "ORANGE"
                else:
                    status_str = "ON TRACK"
                    code = "GREEN"

                row_section_data[s_name] = {
                    "tg": round(daily_tg, 1),
                    "on_hand": round(avail_oh, 1),
                    "ot": round(act_ot, 1),
                    "closing_on_hand": round(closing_oh, 1),
                    "balance": round(new_bal, 1),
                    "status": status_str,
                    "status_code": code,
                    "is_required": True
                }

            # Update cumulative completed output per category for category flow rollup
            for c_id in unique_cat_ids:
                req_cat_secs = [sec for sec in req_sections if sec["category_id"] == c_id]
                if req_cat_secs:
                    cat_cum_completed_output[c_id] = min(sec_cum_output[sec["section_name"]] for sec in req_cat_secs)
                else:
                    cat_cum_completed_output[c_id] = float(order.total_quantity)

            matrix_rows.append({
                "date": d,
                "is_workday": is_workday,
                "day_name": day_name,
                "remaining_working_days": rem_days,
                "section_data": row_section_data
            })

        # 5. Summary Row & Section Validations
        summary = {}
        section_validations = {}
        for s in sections_meta:
            s_name = s["section_name"]
            is_req = s["is_required"]
            if not is_req:
                summary[s_name] = {
                    "section_name": s_name,
                    "total_tg": 0.0,
                    "final_on_hand": 0.0,
                    "total_ot": 0.0,
                    "balance": 0.0,
                    "status": "NOT REQUIRED",
                    "status_code": "GRAY",
                    "target_matches_balance": True,
                    "future_target_total": 0.0,
                    "daily_target": 0.0,
                    "required_daily_rate": 0.0,
                    "executable_daily_target": 0.0,
                    "executable_tg": 0.0,
                    "allocatable_wip": 0.0,
                    "effective_minimum_target": 0,
                }
                continue

            total_tg = sum(r["section_data"].get(s_name, {}).get("tg", 0.0) for r in matrix_rows if r["is_workday"])
            final_oh = matrix_rows[-1]["section_data"].get(s_name, {}).get("closing_on_hand", 0.0) if matrix_rows else 0.0
            total_ot = sum(r["section_data"].get(s_name, {}).get("ot", 0.0) for r in matrix_rows)
            final_sec_bal = max(0.0, float(order.total_quantity) - total_ot)

            used_workdays = sec_future_workdays_used.get(s_name, [])
            future_tg_total = sum(
                r["section_data"].get(s_name, {}).get("tg", 0.0)
                for r in matrix_rows
                if r["date"] in used_workdays and r["is_workday"]
            )
            expected_bal = sec_current_balances.get(s_name, final_sec_bal)
            sec_wip = sec_allocatable_wip.get(s_name, 0.0)
            expected_future_tg = min(expected_bal, sec_wip)

            tgt_matches = (
                round(future_tg_total, 1) == round(expected_future_tg, 1) or
                (round(future_tg_total, 1) == round(expected_bal, 1) and sec_wip >= expected_bal) or
                round(total_tg, 1) == round(float(order.total_quantity), 1)
            )

            sec_feas = sec_feasibility.get(s_name, {"is_feasible": True})
            if not sec_feas.get("is_feasible", True):
                s_stat = "CAPACITY CONSTRAINT"
                s_code = "RED"
            elif final_sec_bal <= 0:
                s_stat = "COMPLETED"
                s_code = "GREEN"
            elif rem_days <= 0 and final_sec_bal > 0:
                s_stat = "OVERDUE"
                s_code = "RED"
            elif sec_wip <= 0 and expected_bal > 0:
                s_stat = "WAITING FOR WIP"
                s_code = "ORANGE"
            elif sec_wip > 0 and future_tg_total < expected_bal:
                s_stat = "PARTIALLY AVAILABLE"
                s_code = "YELLOW"
            elif total_ot >= total_tg and total_tg > 0:
                s_stat = "ON TRACK"
                s_code = "GREEN"
            else:
                s_stat = "ON TRACK"
                s_code = "GREEN"

            summary[s_name] = {
                "section_name": s_name,
                "section_id": s["section_id"],
                "planning_id": s["planning_id"],
                "total_tg": round(total_tg, 1),
                "final_on_hand": round(final_oh, 1),
                "total_ot": round(total_ot, 1),
                "balance": round(final_sec_bal, 1),
                "status": s_stat,
                "status_code": s_code,
                "target_matches_balance": tgt_matches,
                "future_target_total": round(future_tg_total, 1),
                "daily_target": s.get("required_daily_rate", 0),
                "effective_minimum_target": sec_effective_mins.get(s_name, 0),
                "maximum_daily_target": sec_effective_maxs.get(s_name, 0),
                "calculation_mode": sec_calculation_modes.get(s_name, "BALANCED"),
                "feasibility": sec_feas,
                "required_daily_rate": s.get("required_daily_rate", 0),
                "executable_daily_target": s.get("executable_daily_target", 0),
                "executable_tg": s.get("executable_daily_target", 0),
                "allocatable_wip": round(sec_wip, 1),
            }
            section_validations[s_name] = {
                "target_matches_balance": tgt_matches,
                "current_balance": round(expected_bal, 1),
                "future_target_total": round(future_tg_total, 1),
                "total_tg": round(total_tg, 1),
                "allocatable_wip": round(sec_wip, 1),
                "required_daily_rate": s.get("required_daily_rate", 0),
                "executable_tg": s.get("executable_daily_target", 0),
                "effective_minimum_target": sec_effective_mins.get(s_name, 0),
                "maximum_daily_target": sec_effective_maxs.get(s_name, 0),
                "calculation_mode": sec_calculation_modes.get(s_name, "BALANCED"),
                "feasibility": sec_feas,
            }


        cat_flow = cls.calculate_category_flow(db, order)

        final_completed = cat_cum_completed_output[unique_cat_ids[-1]] if unique_cat_ids else 0.0
        final_balance = max(0.0, float(order.total_quantity) - final_completed)
        rem_work_days = CalendarService.get_remaining_working_days(
            db=db,
            start_date=running_date,
            delivery_date=order.current_delivery_date,
            calendar_id=cal.id,
            as_of_date=running_date
        )[0]

        if req_sections:
            bottleneck_sec = min(req_sections, key=lambda s: sec_cum_output[s["section_name"]])["section_name"]
            primary_sec = req_sections[0]["section_name"]
            order_planned_tg = summary.get(primary_sec, {}).get("future_target_total", 0.0)
            if not all_entries:
                order_planned_tg = summary.get(primary_sec, {}).get("total_tg", float(order.total_quantity))
        else:
            bottleneck_sec = "None"
            order_planned_tg = 0.0

        all_feasible = all(f.get("is_feasible", True) for f in sec_feasibility.values())
        capacity_conflicts = [f for f in sec_feasibility.values() if not f.get("is_feasible", True)]

        if final_balance <= 0:
            overall_status = "COMPLETED"
        elif not all_feasible:
            overall_status = "CAPACITY CONSTRAINT"
        elif rem_work_days <= 0 and final_balance > 0:
            overall_status = "OVERDUE"
        elif any(summary.get(s["section_name"], {}).get("status_code") == "RED" for s in req_sections):
            overall_status = "AT RISK"
        elif any(summary.get(s["section_name"], {}).get("status_code") == "ORANGE" for s in req_sections):
            overall_status = "WAITING FOR WIP"
        else:
            overall_status = "ON TRACK"

        order_completion_summary = {
            "order_quantity": float(order.total_quantity),
            "completed_quantity": round(final_completed, 1),
            "remaining_balance": round(final_balance, 1),
            "days_remaining": rem_work_days,
            "bottleneck_section": bottleneck_sec,
            "overall_status": overall_status,
            "is_feasible": all_feasible,
            "capacity_conflicts": capacity_conflicts
        }

        # 6. Build Validation Report (Requirement 46)
        all_targets_valid = all(v["target_matches_balance"] for v in section_validations.values())
        warning_msg = None
        if not all_feasible:
            warning_msg = "Maximum daily capacity is insufficient to complete this balance before shipment."
        elif not is_shipment_workday:
            warning_msg = f"Shipment date {order.current_delivery_date} is a non-working day. Planned production finishes on preceding working days."
        elif rem_work_days <= 0 and final_balance > 0:
            warning_msg = "NO AVAILABLE WORKING DAYS — OVERDUE / NO CAPACITY"

        validation_result = {
            "target_equals_balance": all_targets_valid,
            "checks_passed": all_targets_valid and all_feasible,
            "is_feasible": all_feasible,
            "capacity_conflicts": capacity_conflicts,
            "message": "✓ Target matches balance" if (all_targets_valid and all_feasible) else (warning_msg or "⚠️ Target mismatch detected"),
            "warning": warning_msg,
            "shipment_date_is_workday": is_shipment_workday,
            "section_validations": section_validations
        }

        display_working_dates = [
            d for d in planning_dates
            if d >= running_date and d <= order.current_delivery_date and CalendarService.is_working_day(d, cal, exceptions)
        ]

        return {
            "order_id": order.id,
            "order_code": order.order_code,
            "buyer_id": order.buyer_id,
            "buyer_name": order.buyer.name if order.buyer else "N/A",
            "style_model": order.style_model,
            "total_quantity": float(order.total_quantity),
            "order_quantity": float(order.total_quantity),
            "completed_quantity": round(final_completed, 1),
            "current_balance": round(final_balance, 1),
            "production_start_date": plan_start,
            "shipment_date": plan_end,
            "running_date": running_date,
            "planning_date": cls.get_planning_date_display(running_date),
            "original_delivery_date": order.original_delivery_date,
            "remaining_working_days": rem_work_days,
            "working_days": rem_work_days,
            "working_dates": display_working_dates,
            "final_balance": round(final_balance, 1),
            "total_planned_target": round(order_planned_tg, 1),
            "validation": validation_result,
            "overall_status": overall_status,
            "sections": sections_meta,
            "rows": matrix_rows,
            "summary": summary,
            "category_flow_summary": cat_flow,
            "order_completion_summary": order_completion_summary
        }


