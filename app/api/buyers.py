from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.user import UserRole, User
from app.schemas.buyer import BuyerCreate, BuyerUpdate, BuyerOut, BuyerSummaryOut
from app.api.deps import get_current_user, require_roles
from app.services.order_service import OrderService

router = APIRouter(prefix="/buyers", tags=["Buyers"])


@router.get("", response_model=List[BuyerSummaryOut])
def get_buyers(
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Buyer)
    if search:
        query = query.filter(
            or_(
                Buyer.name.ilike(f"%{search}%"),
                Buyer.buyer_code.ilike(f"%{search}%"),
                Buyer.contact_person.ilike(f"%{search}%"),
            )
        )
    if is_active is not None:
        query = query.filter(Buyer.is_active == is_active)

    buyers = query.order_by(Buyer.name).all()
    results = []

    for b in buyers:
        orders = db.query(Order).filter(Order.buyer_id == b.id).all()
        active_cnt = sum(1 for o in orders if o.status not in [OrderStatus.CLOSED, OrderStatus.PRODUCTION_COMPLETE])
        comp_cnt = sum(1 for o in orders if o.status == OrderStatus.PRODUCTION_COMPLETE)
        tot_qty = sum(o.total_quantity for o in orders)
        
        # Calculate outstanding production across active orders
        outstanding = 0.0
        for o in orders:
            if o.status not in [OrderStatus.CLOSED, OrderStatus.PRODUCTION_COMPLETE]:
                det = OrderService.get_order_calculated_details(db, o)
                outstanding += det["outstanding_pairs"]

        results.append(
            BuyerSummaryOut(
                id=b.id,
                name=b.name,
                buyer_code=b.buyer_code,
                contact_person=b.contact_person,
                phone=b.phone,
                email=b.email,
                address=b.address,
                notes=b.notes,
                is_active=b.is_active,
                created_at=b.created_at,
                updated_at=b.updated_at,
                active_orders_count=active_cnt,
                completed_orders_count=comp_cnt,
                total_ordered_pairs=tot_qty,
                outstanding_production_pairs=outstanding,
            )
        )

    return results


@router.post("", response_model=BuyerOut)
def create_buyer(
    buyer_in: BuyerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    # Check duplicate buyer code
    existing = db.query(Buyer).filter(Buyer.buyer_code == buyer_in.buyer_code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Buyer code '{buyer_in.buyer_code}' already exists."
        )

    buyer = Buyer(**buyer_in.model_dump())
    db.add(buyer)
    db.commit()
    db.refresh(buyer)
    return buyer


@router.get("/{buyer_id}", response_model=BuyerSummaryOut)
def get_buyer_detail(
    buyer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    b = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Buyer not found")

    orders = db.query(Order).filter(Order.buyer_id == b.id).all()
    active_cnt = sum(1 for o in orders if o.status not in [OrderStatus.CLOSED, OrderStatus.PRODUCTION_COMPLETE])
    comp_cnt = sum(1 for o in orders if o.status == OrderStatus.PRODUCTION_COMPLETE)
    tot_qty = sum(o.total_quantity for o in orders)

    outstanding = 0.0
    for o in orders:
        if o.status not in [OrderStatus.CLOSED, OrderStatus.PRODUCTION_COMPLETE]:
            det = OrderService.get_order_calculated_details(db, o)
            outstanding += det["outstanding_pairs"]

    return BuyerSummaryOut(
        id=b.id,
        name=b.name,
        buyer_code=b.buyer_code,
        contact_person=b.contact_person,
        phone=b.phone,
        email=b.email,
        address=b.address,
        notes=b.notes,
        is_active=b.is_active,
        created_at=b.created_at,
        updated_at=b.updated_at,
        active_orders_count=active_cnt,
        completed_orders_count=comp_cnt,
        total_ordered_pairs=tot_qty,
        outstanding_production_pairs=outstanding,
    )


@router.put("/{buyer_id}", response_model=BuyerOut)
def update_buyer(
    buyer_id: int,
    buyer_in: BuyerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    buyer = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")

    if buyer_in.buyer_code and buyer_in.buyer_code != buyer.buyer_code:
        existing = db.query(Buyer).filter(Buyer.buyer_code == buyer_in.buyer_code).first()
        if existing:
            raise HTTPException(status_code=400, detail="Buyer code already exists")

    update_data = buyer_in.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(buyer, field, val)

    db.commit()
    db.refresh(buyer)
    return buyer


@router.delete("/{buyer_id}")
def delete_buyer(
    buyer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    buyer = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")

    has_orders = db.query(Order).filter(Order.buyer_id == buyer.id).first()
    if has_orders:
        # Prevent permanent deletion of buyers that have linked orders; deactivate instead
        buyer.is_active = False
        db.commit()
        return {"detail": "Buyer has linked orders; deactivated instead of permanent deletion"}

    db.delete(buyer)
    db.commit()
    return {"detail": "Buyer deleted successfully"}
