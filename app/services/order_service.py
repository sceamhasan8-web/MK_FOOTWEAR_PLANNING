from datetime import date, datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.order import Order, DeliveryDateRevision, OrderPriority, OrderStatus
from app.models.buyer import Buyer
from app.models.route import (
    Category,
    Section,
    ProcessTemplate,
    OrderRoute,
    OrderOperation,
    OperationComponent,
    SectionRouteStatus,
    OperationStatus,
    UnitType,
)
from app.models.entry import DailyProductionEntry
from app.models.audit import AuditLog
from app.schemas.order import OrderCreate, OrderUpdate, DeliveryRevisionCreate
from app.services.calendar_service import CalendarService
from app.services.calculation_engine import CalculationEngine
from app.services.production_planning_service import ProductionPlanningService


class OrderService:

    @staticmethod
    def generate_order_code(db: Session) -> str:
        count = db.query(Order).count() + 1
        year = datetime.utcnow().year
        return f"ORD-{year}-{count:04d}"

    @classmethod
    def create_order(cls, db: Session, order_in: OrderCreate, user_id: int) -> Order:
        # Verify buyer exists
        buyer = db.query(Buyer).filter(Buyer.id == order_in.buyer_id).first()
        if not buyer:
            raise HTTPException(status_code=404, detail="Buyer not found")

        order_code = order_in.order_code or cls.generate_order_code(db)
        # Check duplicate code
        if db.query(Order).filter(Order.order_code == order_code).first():
            raise HTTPException(status_code=400, detail="Order code already exists")

        order_date = order_in.original_order_date or date.today()
        prod_start = order_in.production_start_date or date.today()

        order = Order(
            order_code=order_code,
            buyer_id=order_in.buyer_id,
            customer_ref=order_in.customer_ref,
            po_number=order_in.po_number,
            style_model=order_in.style_model,
            description=order_in.description,
            total_quantity=order_in.total_quantity,
            original_order_date=order_date,
            production_start_date=prod_start,
            original_delivery_date=order_in.original_delivery_date,
            current_delivery_date=order_in.original_delivery_date,
            priority=order_in.priority,
            status=OrderStatus.SCHEDULED,
            notes=order_in.notes,
            created_by_id=user_id,
        )
        db.add(order)
        db.flush()

        # If custom routes are provided, configure them; otherwise build default routes
        # If custom routes are provided, configure them; otherwise build default routes
        if order_in.routes:
            for idx, r_in in enumerate(order_in.routes):
                sec_id = r_in.section_id
                if not sec_id and r_in.section_name:
                    sec = db.query(Section).filter(Section.name.ilike(r_in.section_name.strip())).first()
                    if not sec:
                        cat = db.query(Category).first()
                        if not cat:
                            cat = Category(name="Production", display_order=1, is_active=True)
                            db.add(cat)
                            db.flush()
                        sec = Section(category_id=cat.id, name=r_in.section_name.strip(), display_order=idx + 1, is_active=True)
                        db.add(sec)
                        db.flush()
                    sec_id = sec.id

                serial = r_in.serial_no if (r_in.serial_no is not None and r_in.serial_no > 0) else None
                seq = r_in.sequence_order if (r_in.sequence_order is not None and r_in.sequence_order > 0) else (idx + 1)
                t_rule = r_in.transfer_rule or "IMMEDIATE"

                route = OrderRoute(
                    order_id=order.id,
                    section_id=sec_id,
                    status=r_in.status,
                    sequence_order=seq,
                    serial_no=serial,
                    transfer_rule=t_rule,
                    has_components=r_in.has_components,
                    notes=r_in.notes,
                )
                db.add(route)
                db.flush()

                if r_in.operations:
                    for op_in in r_in.operations:
                        op_qty = op_in.required_quantity if op_in.required_quantity is not None else order.total_quantity
                        op = OrderOperation(
                            route_id=route.id,
                            operation_name=op_in.operation_name,
                            sequence_order=op_in.sequence_order or 1,
                            unit=op_in.unit,
                            required_quantity=op_qty,
                            completed_quantity=0.0,
                            rejected_quantity=0.0,
                            balance_quantity=op_qty,
                            status=OperationStatus.PENDING,
                            notes=op_in.notes,
                        )
                        db.add(op)
                        db.flush()

                        for c_in in op_in.components:
                            comp_req = c_in.required_total_qty
                            if comp_req is None:
                                comp_req = op_qty * c_in.pieces_per_pair
                            comp = OperationComponent(
                                operation_id=op.id,
                                component_name=c_in.component_name,
                                unit=c_in.unit,
                                pieces_per_pair=c_in.pieces_per_pair,
                                required_total_qty=comp_req,
                                accepted_total_qty=0.0,
                                rejected_total_qty=0.0,
                                balance_total_qty=comp_req,
                            )
                            db.add(comp)
                else:
                    # Single section-level operation automatically generated
                    s_obj = db.query(Section).filter(Section.id == sec_id).first()
                    sec_name_str = s_obj.name if s_obj else f"Section {sec_id}"
                    op = OrderOperation(
                        route_id=route.id,
                        operation_name=sec_name_str,
                        sequence_order=1,
                        unit=UnitType.PAIRS,
                        required_quantity=order.total_quantity,
                        completed_quantity=0.0,
                        rejected_quantity=0.0,
                        balance_quantity=order.total_quantity,
                        status=OperationStatus.PENDING,
                    )
                    db.add(op)
        else:
            # Default routes from active sections
            sections = db.query(Section).filter(Section.is_active == True).order_by(Section.display_order).all()
            for s_idx, s in enumerate(sections):
                serial = s_idx + 1
                route = OrderRoute(
                    order_id=order.id,
                    section_id=s.id,
                    status=SectionRouteStatus.REQUIRED,
                    sequence_order=serial,
                    serial_no=serial,
                    transfer_rule="IMMEDIATE",
                    has_components=False,
                )
                db.add(route)
                db.flush()

                templates = db.query(ProcessTemplate).filter(
                    ProcessTemplate.section_id == s.id,
                    ProcessTemplate.is_active == True
                ).order_by(ProcessTemplate.display_order).all()

                if templates:
                    for t in templates:
                        op = OrderOperation(
                            route_id=route.id,
                            operation_name=t.name,
                            sequence_order=t.display_order,
                            unit=t.default_unit,
                            required_quantity=order.total_quantity,
                            completed_quantity=0.0,
                            rejected_quantity=0.0,
                            balance_quantity=order.total_quantity,
                            status=OperationStatus.PENDING,
                        )
                        db.add(op)
                else:
                    # Single section-level operation
                    op = OrderOperation(
                        route_id=route.id,
                        operation_name=s.name,
                        sequence_order=1,
                        unit=UnitType.PAIRS,
                        required_quantity=order.total_quantity,
                        completed_quantity=0.0,
                        rejected_quantity=0.0,
                        balance_quantity=order.total_quantity,
                        status=OperationStatus.PENDING,
                    )
                    db.add(op)

        # Audit log
        audit = AuditLog(
            entity_name="Order",
            entity_id=order.id,
            action="CREATE",
            user_id=user_id,
            details=f"Order {order.order_code} created for {order.total_quantity} pairs",
        )
        db.add(audit)
        db.commit()
        db.refresh(order)
        return order

    @classmethod
    def revise_delivery_date(
        cls,
        db: Session,
        order_id: int,
        rev_in: DeliveryRevisionCreate,
        user_id: int
    ) -> Order:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        old_date = order.current_delivery_date
        new_date = rev_in.revised_delivery_date

        revision = DeliveryDateRevision(
            order_id=order.id,
            previous_delivery_date=old_date,
            revised_delivery_date=new_date,
            reason=rev_in.reason,
            revised_by_id=user_id,
        )
        db.add(revision)

        order.current_delivery_date = new_date

        audit = AuditLog(
            entity_name="Order",
            entity_id=order.id,
            action="REVISE_DELIVERY_DATE",
            user_id=user_id,
            details=f"Delivery date changed from {old_date} to {new_date}. Reason: {rev_in.reason}",
            reason=rev_in.reason,
        )
        db.add(audit)
        db.commit()
        db.refresh(order)
        return order

    @classmethod
    def update_order(
        cls,
        db: Session,
        order_id: int,
        order_update: OrderUpdate,
        user_id: int
    ) -> Order:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        old_quantity = order.total_quantity
        if order_update.total_quantity is not None and order_update.total_quantity != old_quantity:
            new_qty = order_update.total_quantity
            # Check if any operation cumulative accepted exceeds new quantity
            for r in order.routes:
                for op in r.operations:
                    if op.completed_quantity > new_qty:
                        # Don't silently discard; warn/record overproduction
                        pass
                    # Adjust required quantity
                    op.required_quantity = new_qty
                    op.balance_quantity = CalculationEngine.calculate_operation_balance(
                        new_qty, op.completed_quantity
                    )
                    # Adjust components if any
                    for comp in op.components:
                        comp.required_total_qty = new_qty * comp.pieces_per_pair
                        comp.balance_total_qty = max(
                            0.0, comp.required_total_qty - comp.accepted_total_qty
                        )

            order.total_quantity = new_qty
            audit = AuditLog(
                entity_name="Order",
                entity_id=order.id,
                action="UPDATE_QUANTITY",
                user_id=user_id,
                details=f"Order quantity changed from {old_quantity} to {new_qty}. Reason: {order_update.reason or 'User update'}",
                reason=order_update.reason,
            )
            db.add(audit)

        if order_update.current_delivery_date is not None and order_update.current_delivery_date != order.current_delivery_date:
            old_deliv = order.current_delivery_date
            new_deliv = order_update.current_delivery_date
            rev = DeliveryDateRevision(
                order_id=order.id,
                previous_delivery_date=old_deliv,
                revised_delivery_date=new_deliv,
                reason=order_update.reason or "Delivery date revised via order update",
                revised_by_id=user_id,
            )
            db.add(rev)
            order.current_delivery_date = new_deliv
            audit = AuditLog(
                entity_name="Order",
                entity_id=order.id,
                action="REVISE_DELIVERY_DATE",
                user_id=user_id,
                details=f"Delivery date changed from {old_deliv} to {new_deliv}. Reason: {order_update.reason or 'Order update'}",
                reason=order_update.reason,
            )
            db.add(audit)

        if order_update.customer_ref is not None:
            order.customer_ref = order_update.customer_ref
        if order_update.po_number is not None:
            order.po_number = order_update.po_number
        if order_update.style_model is not None:
            order.style_model = order_update.style_model
        if order_update.description is not None:
            order.description = order_update.description
        if order_update.production_start_date is not None:
            order.production_start_date = order_update.production_start_date
        if order_update.priority is not None:
            order.priority = order_update.priority
        if order_update.status is not None:
            order.status = order_update.status
        if order_update.notes is not None:
            order.notes = order_update.notes

        if order_update.routes is not None:
            # Check for existing routes with production history
            existing_routes = {r.id: r for r in order.routes}
            for r_id, r_obj in existing_routes.items():
                entries = db.query(DailyProductionEntry).filter(
                    DailyProductionEntry.route_id == r_id,
                    DailyProductionEntry.is_reversed == False
                ).all()
                if entries:
                    matching = False
                    for new_r in order_update.routes:
                        if new_r.section_id == r_obj.section_id or (new_r.section_name and r_obj.section and new_r.section_name.strip().lower() == r_obj.section.name.lower()):
                            matching = True
                            break
                    if not matching and not order_update.confirm_workflow_change:
                        sec_name = r_obj.section.name if r_obj.section else f"Section {r_obj.section_id}"
                        tot_acc = sum(e.accepted_quantity for e in entries)
                        raise HTTPException(
                            status_code=400,
                            detail=f"{sec_name} already contains production history. Completed: {tot_acc:,.0f} pairs. Changing this workflow may affect WIP calculations. Set confirm_workflow_change=true to proceed."
                        )

            # Re-map or re-sequence routes
            for idx, r_in in enumerate(order_update.routes):
                sec_id = r_in.section_id
                if not sec_id and r_in.section_name:
                    sec = db.query(Section).filter(Section.name.ilike(r_in.section_name.strip())).first()
                    if not sec:
                        cat = db.query(Category).first()
                        if not cat:
                            cat = Category(name="Production", display_order=1, is_active=True)
                            db.add(cat)
                            db.flush()
                        sec = Section(category_id=cat.id, name=r_in.section_name.strip(), display_order=idx + 1, is_active=True)
                        db.add(sec)
                        db.flush()
                    sec_id = sec.id

                serial = r_in.serial_no if (r_in.serial_no and r_in.serial_no > 0) else (idx + 1)
                t_rule = r_in.transfer_rule or "IMMEDIATE"

                # Check if matching route exists on order
                existing_r = next((r for r in order.routes if r.section_id == sec_id), None)
                if existing_r:
                    existing_r.serial_no = serial
                    existing_r.sequence_order = serial
                    existing_r.transfer_rule = t_rule
                    existing_r.status = r_in.status
                else:
                    new_route = OrderRoute(
                        order_id=order.id,
                        section_id=sec_id,
                        status=r_in.status,
                        sequence_order=serial,
                        serial_no=serial,
                        transfer_rule=t_rule,
                        has_components=False,
                    )
                    db.add(new_route)
                    db.flush()
                    s_obj = db.query(Section).filter(Section.id == sec_id).first()
                    op_name = s_obj.name if s_obj else f"Section {sec_id}"
                    new_op = OrderOperation(
                        route_id=new_route.id,
                        operation_name=op_name,
                        sequence_order=1,
                        unit=UnitType.PAIRS,
                        required_quantity=order.total_quantity,
                        completed_quantity=0.0,
                        rejected_quantity=0.0,
                        balance_quantity=order.total_quantity,
                        status=OperationStatus.PENDING,
                    )
                    db.add(new_op)

            audit = AuditLog(
                entity_name="Order",
                entity_id=order.id,
                action="UPDATE_WORKFLOW",
                user_id=user_id,
                details=f"Order {order.order_code} workflow updated with {len(order_update.routes)} sections",
                reason=order_update.reason or "Workflow re-sequencing",
            )
            db.add(audit)

        db.commit()
        db.refresh(order)
        return order

    @classmethod
    def get_order_calculated_details(
        cls,
        db: Session,
        order: Order,
        as_of_date: date = None
    ) -> Dict[str, Any]:
        """Calculates comprehensive order planning metrics, section statuses, and daily targets via authoritative ProductionPlanningService."""
        details = ProductionPlanningService.calculate_order_plan(db=db, order=order, as_of_date=as_of_date)
        details["is_archived"] = getattr(order, "is_archived", False)
        return details

    @classmethod
    def check_order_dependencies(cls, db: Session, order_id: int) -> Dict[str, Any]:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        from app.models.wip_adjustment import WipAdjustment

        prod_count = db.query(DailyProductionEntry).filter(DailyProductionEntry.order_id == order.id).count()
        wip_count = db.query(WipAdjustment).filter(WipAdjustment.order_id == order.id).count()
        has_history = (prod_count > 0 or wip_count > 0)
        can_perm_delete = (not has_history)
        buyer_name = order.buyer.name if order.buyer else "Unknown Buyer"

        if has_history:
            message = (
                f"This order contains {prod_count} production entries and {wip_count} WIP records. "
                "Permanent deletion is blocked to preserve factory manufacturing history. "
                "Archive or cancel this order to remove it from active planning."
            )
        else:
            message = "This order has 0 production records and can be permanently deleted."

        return {
            "order_id": order.id,
            "order_code": order.order_code,
            "customer_ref": order.customer_ref,
            "buyer_name": buyer_name,
            "total_quantity": float(order.total_quantity),
            "production_entries_count": prod_count,
            "has_production_history": has_history,
            "can_permanently_delete": can_perm_delete,
            "can_archive": True,
            "message": message,
        }

    @classmethod
    def delete_order(cls, db: Session, order_id: int, user_id: int) -> Dict[str, Any]:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        from app.models.wip_adjustment import WipAdjustment

        prod_count = db.query(DailyProductionEntry).filter(DailyProductionEntry.order_id == order.id).count()
        if prod_count > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot permanently delete order {order.order_code}. "
                    f"It contains {prod_count} production records. Please archive or cancel this order instead."
                )
            )

        # Delete any WIP adjustments if existing
        db.query(WipAdjustment).filter(WipAdjustment.order_id == order.id).delete(synchronize_session=False)

        order_code = order.order_code
        db.delete(order)

        audit = AuditLog(
            entity_name="Order",
            entity_id=order_id,
            action="DELETE",
            user_id=user_id,
            details=f"Order {order_code} permanently deleted (0 production dependencies).",
            reason="Permanent deletion by authorized user",
        )
        db.add(audit)
        db.commit()

        return {
            "success": True,
            "message": f"Order {order_code} permanently deleted successfully.",
            "order_id": order_id,
            "order_code": order_code,
            "action": "DELETED"
        }

    @classmethod
    def archive_order(cls, db: Session, order_id: int, user_id: int, reason: str = "Archived by user") -> Order:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        order.is_archived = True
        order.status = OrderStatus.ARCHIVED

        audit = AuditLog(
            entity_name="Order",
            entity_id=order.id,
            action="ARCHIVE",
            user_id=user_id,
            details=f"Order {order.order_code} archived. Excluded from active planning. Reason: {reason}",
            reason=reason,
        )
        db.add(audit)
        db.commit()
        db.refresh(order)
        return order

    @classmethod
    def restore_order(cls, db: Session, order_id: int, user_id: int) -> Order:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        order.is_archived = False
        order.status = OrderStatus.SCHEDULED

        audit = AuditLog(
            entity_name="Order",
            entity_id=order.id,
            action="RESTORE",
            user_id=user_id,
            details=f"Order {order.order_code} restored to active operational status.",
            reason="Order restored by authorized user",
        )
        db.add(audit)
        db.commit()
        db.refresh(order)
        return order

