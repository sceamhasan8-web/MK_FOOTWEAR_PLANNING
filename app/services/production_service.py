from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.entry import DailyProductionEntry, ProductionEntryCorrection
from app.models.order import Order
from app.models.route import OrderRoute, OrderOperation, OperationComponent, SectionRouteStatus
from app.models.audit import AuditLog
from app.schemas.entry import (
    DailyProductionEntryCreate,
    ProductionBulkCreate,
    ProductionCorrectionCreate,
    ProductionEntryReversalCreate,
)
from app.services.calculation_engine import CalculationEngine


class ProductionService:

    @classmethod
    def create_production_entry(
        cls,
        db: Session,
        entry_in: DailyProductionEntryCreate,
        user_id: int
    ) -> DailyProductionEntry:
        return cls.record_production_entry(db, entry_in, user_id)

    @classmethod
    def record_production_entry(
        cls,
        db: Session,
        entry_in: DailyProductionEntryCreate,
        user_id: int
    ) -> DailyProductionEntry:
        # Validate operation exists
        op = db.query(OrderOperation).filter(OrderOperation.id == entry_in.operation_id).first()
        if not op:
            raise HTTPException(status_code=404, detail="Operation not found")

        # Disallow production entries for inactive sections
        if op.route and op.route.section and not op.route.section.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot record production entry for inactive section '{op.route.section.name}'. Please activate the section in Settings first."
            )

        order = db.query(Order).filter(Order.id == entry_in.order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Validate duplicate submission within 10 seconds with identical values and remarks
        last_entry = db.query(DailyProductionEntry).filter(
            DailyProductionEntry.order_id == entry_in.order_id,
            DailyProductionEntry.operation_id == entry_in.operation_id,
            DailyProductionEntry.component_id == entry_in.component_id,
            DailyProductionEntry.entry_date == entry_in.entry_date,
            DailyProductionEntry.quantity == entry_in.quantity,
            DailyProductionEntry.accepted_quantity == entry_in.accepted_quantity,
            DailyProductionEntry.remarks == entry_in.remarks,
            DailyProductionEntry.is_reversed == False
        ).order_by(DailyProductionEntry.id.desc()).first()

        if last_entry and (datetime.utcnow() - last_entry.created_at).total_seconds() < 10:
            raise HTTPException(
                status_code=400,
                detail="Duplicate submission detected. An identical entry was just submitted seconds ago."
            )

        existing_entries = db.query(DailyProductionEntry).filter(
            DailyProductionEntry.operation_id == op.id,
            DailyProductionEntry.is_reversed == False
        ).all()

        # Component-wise vs direct operation balance validation
        if entry_in.component_id:
            comp = db.query(OperationComponent).filter(OperationComponent.id == entry_in.component_id).first()
            if not comp:
                raise HTTPException(status_code=404, detail="Component not found")
            comp_entries = [e for e in existing_entries if e.component_id == comp.id]
            comp_cum = sum(e.accepted_quantity for e in comp_entries)
            comp_balance = max(0.0, comp.required_total_qty - comp_cum)

            if entry_in.accepted_quantity > comp_balance and not entry_in.is_override:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Entry quantity ({entry_in.accepted_quantity} {entry_in.unit}) exceeds component remaining balance "
                        f"({comp_balance} {entry_in.unit}). Authorized override required."
                    )
                )
        else:
            current_cum = sum(e.accepted_quantity for e in existing_entries)
            current_balance = CalculationEngine.calculate_operation_balance(op.required_quantity, current_cum)

            # Available On Hand validation (Section 8 & 28: Production Cannot Exceed On Hand)
            from app.services.production_planning_service import ProductionPlanningService
            avail_on_hand = ProductionPlanningService.get_available_on_hand_for_operation(db, op, as_of_date=entry_in.entry_date)
            if entry_in.accepted_quantity > avail_on_hand and not entry_in.is_override:
                shortage = max(0.0, entry_in.accepted_quantity - avail_on_hand)
                if entry_in.accepted_quantity > current_balance:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Entry quantity ({entry_in.accepted_quantity:,.0f}) exceeds remaining balance ({current_balance:,.0f}) "
                            f"and Insufficient On Hand quantity.\n"
                            f"Available On Hand: {avail_on_hand:,.0f}\n"
                            f"Entered Production: {entry_in.accepted_quantity:,.0f}\n"
                            f"Shortage: {shortage:,.0f}\n"
                            f"Production cannot exceed available On Hand. Authorized override required."
                        )
                    )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Insufficient On Hand quantity.\n"
                            f"Available On Hand: {avail_on_hand:,.0f}\n"
                            f"Entered Production: {entry_in.accepted_quantity:,.0f}\n"
                            f"Shortage: {shortage:,.0f}\n"
                            f"Production cannot exceed available On Hand."
                        )
                    )

            # Warn / block if entry exceeds remaining target and override is not enabled
            if entry_in.accepted_quantity > current_balance and not entry_in.is_override:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Entry quantity ({entry_in.accepted_quantity}) exceeds remaining balance ({current_balance}). "
                        "Authorized supervisor override is required to proceed with overproduction."
                    )
                )

        entry = DailyProductionEntry(
            entry_date=entry_in.entry_date,
            order_id=entry_in.order_id,
            route_id=entry_in.route_id,
            operation_id=entry_in.operation_id,
            component_id=entry_in.component_id,
            quantity=entry_in.quantity,
            accepted_quantity=entry_in.accepted_quantity,
            rejected_quantity=entry_in.rejected_quantity,
            unit=entry_in.unit,
            remarks=entry_in.remarks,
            entered_by_id=user_id,
            is_override=entry_in.is_override,
            is_reversed=False,
        )
        db.add(entry)
        db.flush()

        # Update cached rollups
        cls._refresh_operation_rollups(db, op)

        audit = AuditLog(
            entity_name="DailyProductionEntry",
            entity_id=entry.id,
            action="CREATE",
            user_id=user_id,
            details=(
                f"Recorded entry: Date {entry.entry_date}, Accepted {entry.accepted_quantity}, "
                f"Rejected {entry.rejected_quantity} for {op.operation_name}"
            ),
        )
        db.add(audit)
        db.commit()
        db.refresh(entry)
        return entry

    @classmethod
    def record_bulk_production(
        cls,
        db: Session,
        bulk_in: ProductionBulkCreate,
        user_id: int
    ) -> List[DailyProductionEntry]:
        created_entries = []
        for item in bulk_in.items:
            entry_create = DailyProductionEntryCreate(
                entry_date=bulk_in.entry_date,
                order_id=bulk_in.order_id,
                route_id=bulk_in.route_id,
                operation_id=item.operation_id,
                component_id=item.component_id,
                quantity=item.quantity,
                accepted_quantity=item.accepted_quantity,
                rejected_quantity=item.rejected_quantity,
                unit=item.unit,
                remarks=item.remarks,
                is_override=item.is_override,
            )
            entry = cls.record_production_entry(db, entry_create, user_id)
            created_entries.append(entry)
        return created_entries

    @classmethod
    def correct_production_entry(
        cls,
        db: Session,
        entry_id: int,
        correction_in: ProductionCorrectionCreate,
        user_id: int
    ) -> DailyProductionEntry:
        entry = db.query(DailyProductionEntry).filter(DailyProductionEntry.id == entry_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Production entry not found")
        if entry.is_reversed:
            raise HTTPException(status_code=400, detail="Cannot edit an already reversed entry")

        orig_acc = entry.accepted_quantity
        orig_rej = entry.rejected_quantity

        delta = correction_in.new_accepted_quantity - orig_acc
        if delta > 0 and not entry.is_override:
            from app.services.production_planning_service import ProductionPlanningService
            op_check = db.query(OrderOperation).filter(OrderOperation.id == entry.operation_id).first()
            if op_check:
                avail_on_hand = ProductionPlanningService.get_available_on_hand_for_operation(db, op_check)
                if delta > avail_on_hand:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Insufficient On Hand quantity. Category has {avail_on_hand:,.0f} available On Hand. "
                            "Authorized override required."
                        )
                    )

        # Create correction audit record
        correction = ProductionEntryCorrection(
            entry_id=entry.id,
            original_accepted_qty=orig_acc,
            new_accepted_qty=correction_in.new_accepted_quantity,
            original_rejected_qty=orig_rej,
            new_rejected_qty=correction_in.new_rejected_quantity,
            action_type="EDIT",
            reason=correction_in.reason,
            authorized_by_id=user_id,
        )
        db.add(correction)

        entry.accepted_quantity = correction_in.new_accepted_quantity
        entry.rejected_quantity = correction_in.new_rejected_quantity
        entry.quantity = correction_in.new_accepted_quantity + correction_in.new_rejected_quantity

        # Refresh operation rollups
        op = db.query(OrderOperation).filter(OrderOperation.id == entry.operation_id).first()
        if op:
            cls._refresh_operation_rollups(db, op)

        audit = AuditLog(
            entity_name="DailyProductionEntry",
            entity_id=entry.id,
            action="CORRECTION",
            user_id=user_id,
            details=f"Entry {entry.id} corrected: Accepted {orig_acc} -> {entry.accepted_quantity}. Reason: {correction_in.reason}",
            reason=correction_in.reason,
        )
        db.add(audit)
        db.commit()
        db.refresh(entry)
        return entry

    @classmethod
    def reverse_production_entry(
        cls,
        db: Session,
        entry_id: int,
        reversal_in: ProductionEntryReversalCreate,
        user_id: int
    ) -> DailyProductionEntry:
        return cls.cancel_production_entry(db, entry_id, user_id, reversal_in.reason)

    @classmethod
    def cancel_production_entry(
        cls,
        db: Session,
        entry_id: int,
        user_id: int,
        reason: str = "Cancelled by user"
    ) -> DailyProductionEntry:
        entry = db.query(DailyProductionEntry).filter(DailyProductionEntry.id == entry_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Production entry not found")
        if entry.is_reversed:
            raise HTTPException(status_code=400, detail="Entry is already cancelled/reversed")

        entry.is_reversed = True

        correction = ProductionEntryCorrection(
            entry_id=entry.id,
            original_accepted_qty=entry.accepted_quantity,
            new_accepted_qty=0.0,
            original_rejected_qty=entry.rejected_quantity,
            new_rejected_qty=0.0,
            action_type="REVERSAL",
            reason=reason,
            authorized_by_id=user_id,
        )
        db.add(correction)

        op = db.query(OrderOperation).filter(OrderOperation.id == entry.operation_id).first()
        if op:
            cls._refresh_operation_rollups(db, op)

        # WIP integrity validation: check whether downstream categories now exceed available upstream input
        from app.services.production_planning_service import ProductionPlanningService
        wip_warning = None
        if entry.order:
            cat_flow = ProductionPlanningService.calculate_category_flow(db, entry.order)
            for item in cat_flow:
                if item.get("available_on_hand", 0.0) < item.get("actual_production", 0.0):
                    deficit = item.get("actual_production", 0.0) - item.get("available_on_hand", 0.0)
                    wip_warning = (
                        f"WIP Integrity Conflict: Section '{item.get('category_name')}' downstream completed "
                        f"{item.get('actual_production')} pairs, exceeding available input {item.get('available_on_hand')} "
                        f"by {deficit:.0f} pairs. Downstream reconciliation required."
                    )
                    break

        audit = AuditLog(
            entity_name="DailyProductionEntry",
            entity_id=entry.id,
            action="CANCEL",
            user_id=user_id,
            details=f"Entry {entry.id} cancelled. Accepted {entry.accepted_quantity} negated. Reason: {reason}" + (f" [{wip_warning}]" if wip_warning else ""),
            reason=reason,
        )
        db.add(audit)
        db.commit()
        db.refresh(entry)
        return entry

    @classmethod
    def _refresh_operation_rollups(cls, db: Session, op: OrderOperation):
        valid_entries = db.query(DailyProductionEntry).filter(
            DailyProductionEntry.operation_id == op.id,
            DailyProductionEntry.is_reversed == False
        ).all()

        total_rej = sum(e.rejected_quantity for e in valid_entries)
        op.rejected_quantity = total_rej

        # If operation has components, roll up each component and compute limiting pair equivalent
        if op.components:
            all_comps_done = True
            pair_equivalents = []
            for comp in op.components:
                comp_entries = [e for e in valid_entries if e.component_id == comp.id]
                c_acc = sum(e.accepted_quantity for e in comp_entries)
                c_rej = sum(e.rejected_quantity for e in comp_entries)
                comp.accepted_total_qty = c_acc
                comp.rejected_total_qty = c_rej
                comp.balance_total_qty = max(0.0, comp.required_total_qty - c_acc)
                if comp.balance_total_qty > 0:
                    all_comps_done = False
                pair_equivalents.append(CalculationEngine.calculate_component_pair_equivalent(c_acc, comp.pieces_per_pair))

            effective_pairs = min(pair_equivalents) if pair_equivalents else 0.0
            op.completed_quantity = effective_pairs
            op.balance_quantity = CalculationEngine.calculate_operation_balance(op.required_quantity, effective_pairs)
            op.status = CalculationEngine.evaluate_operation_status(op.required_quantity, effective_pairs, all_comps_done)
        else:
            total_acc = sum(e.accepted_quantity for e in valid_entries)
            op.completed_quantity = total_acc
            op.balance_quantity = CalculationEngine.calculate_operation_balance(op.required_quantity, total_acc)
            op.status = CalculationEngine.evaluate_operation_status(op.required_quantity, total_acc)
