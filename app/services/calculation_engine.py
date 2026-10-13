import math
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from app.models.route import SectionRouteStatus, OperationStatus
from app.models.order import OrderStatus


class CalculationEngine:

    @staticmethod
    def calculate_operation_balance(required_qty: float, cumulative_accepted: float) -> float:
        """Operation balance = MAX(0, required operation quantity - cumulative accepted quantity)"""
        return max(0.0, float(required_qty) - float(cumulative_accepted))

    @staticmethod
    def calculate_operation_completion_percentage(required_qty: float, cumulative_accepted: float) -> float:
        """Operation completion percentage = MIN(100, cumulative accepted quantity / required operation quantity * 100)"""
        if required_qty <= 0:
            return 100.0 if cumulative_accepted >= 0 else 0.0
        pct = (float(cumulative_accepted) / float(required_qty)) * 100.0
        return min(100.0, max(0.0, round(pct, 2)))

    @staticmethod
    def calculate_component_pair_equivalent(accepted_pieces: float, pieces_per_pair: float) -> float:
        """Converts raw accepted piece quantity to normalized pair-equivalent quantity."""
        if pieces_per_pair <= 0:
            return float(accepted_pieces)
        return round(float(accepted_pieces) / float(pieces_per_pair), 2)

    @staticmethod
    def calculate_daily_target(remaining_balance: float, remaining_working_days: int) -> float:
        """
        Daily required target = CEILING(remaining accepted production quantity / remaining working days)
        If remaining working days is 0, returns 0.0 (overdue alert handled separately).
        """
        if remaining_balance <= 0.0:
            return 0.0
        if remaining_working_days <= 0:
            return float(remaining_balance)  # Full balance is due immediately
        return float(math.ceil(remaining_balance / remaining_working_days))

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
    def generate_balanced_daily_schedule(
        remaining_balance: float,
        working_dates: List[date]
    ) -> Dict[date, float]:
        """
        Generates planned quantities for each remaining working day.
        Guarantees that the sum of planned quantities equals the remaining balance exactly.
        """
        schedule: Dict[date, float] = {}
        total_days = len(working_dates)

        if total_days == 0 or remaining_balance <= 0.0:
            for d in working_dates:
                schedule[d] = 0.0
            return schedule

        balance_int = int(remaining_balance)
        fractional = remaining_balance - balance_int

        base_qty = balance_int // total_days
        remainder = balance_int % total_days

        for i, d in enumerate(working_dates):
            qty = base_qty + (1 if i < remainder else 0)
            if i == 0 and fractional > 0:
                qty += fractional
            schedule[d] = float(qty)

        return schedule

    @classmethod
    def evaluate_operation_status(
        cls,
        required_qty: float,
        cumulative_accepted: float,
        components_status_complete: Optional[bool] = None
    ) -> OperationStatus:
        if components_status_complete is not None and not components_status_complete:
            return OperationStatus.IN_PROGRESS if cumulative_accepted > 0 else OperationStatus.PENDING

        balance = cls.calculate_operation_balance(required_qty, cumulative_accepted)
        if balance <= 0 and required_qty > 0:
            return OperationStatus.COMPLETED
        elif cumulative_accepted > 0:
            return OperationStatus.IN_PROGRESS
        return OperationStatus.PENDING

    @classmethod
    def evaluate_section_completion(
        cls,
        route_status: SectionRouteStatus,
        operations: List[Dict[str, Any]]
    ) -> bool:
        """
        Section is complete if:
        1. Marked NOT_REQUIRED -> does not block
        2. Marked REQUIRED -> EVERY required operation has balance <= 0 and all required components are met.
        NEVER sums operation outputs together.
        """
        if route_status == SectionRouteStatus.NOT_REQUIRED:
            return True

        if not operations:
            return False

        for op in operations:
            if op.get("status") != OperationStatus.COMPLETED and op.get("balance_quantity", 1) > 0:
                return False
            # Check components if any
            comps = op.get("components", [])
            for comp in comps:
                if comp.get("balance_total_qty", 1) > 0:
                    return False

        return True

    @classmethod
    def evaluate_order_status(
        cls,
        current_status: OrderStatus,
        required_routes: List[Dict[str, Any]],
        current_delivery_date: date,
        remaining_working_days: int,
        has_any_entries: bool,
        as_of_date: date = None
    ) -> OrderStatus:
        if current_status in [OrderStatus.CLOSED, OrderStatus.ON_HOLD, OrderStatus.DRAFT]:
            return current_status

        if as_of_date is None:
            as_of_date = date.today()

        # Check if all required routes are complete
        all_required_complete = True
        has_required_route = False

        for r in required_routes:
            if r.get("status") == SectionRouteStatus.REQUIRED:
                has_required_route = True
                if not r.get("is_completed", False):
                    all_required_complete = False
                    break

        if has_required_route and all_required_complete:
            return OrderStatus.PRODUCTION_COMPLETE

        # Check overdue / at risk
        if as_of_date > current_delivery_date:
            return OrderStatus.OVERDUE

        if remaining_working_days <= 0:
            return OrderStatus.AT_RISK

        if has_any_entries:
            return OrderStatus.IN_PRODUCTION

        return OrderStatus.SCHEDULED
