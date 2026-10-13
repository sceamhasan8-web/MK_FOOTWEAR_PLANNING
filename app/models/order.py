import enum
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Text, Date, DateTime, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class OrderPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class OrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    IN_PRODUCTION = "IN_PRODUCTION"
    AT_RISK = "AT_RISK"
    OVERDUE = "OVERDUE"
    PRODUCTION_COMPLETE = "PRODUCTION_COMPLETE"
    ON_HOLD = "ON_HOLD"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_code = Column(String(50), unique=True, index=True, nullable=False)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False, index=True)
    customer_ref = Column(String(100), nullable=False)
    po_number = Column(String(100), nullable=True)
    style_model = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    total_quantity = Column(Float, nullable=False)  # in pairs
    
    original_order_date = Column(Date, default=date.today, nullable=False)
    production_start_date = Column(Date, default=date.today, nullable=False)
    original_delivery_date = Column(Date, nullable=False)
    current_delivery_date = Column(Date, nullable=False)

    priority = Column(Enum(OrderPriority), default=OrderPriority.MEDIUM, nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.SCHEDULED, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    buyer = relationship("Buyer", back_populates="orders")
    creator = relationship("User", back_populates="orders_created", foreign_keys=[created_by_id])
    routes = relationship("OrderRoute", back_populates="order", cascade="all, delete-orphan", order_by="OrderRoute.sequence_order")
    delivery_revisions = relationship("DeliveryDateRevision", back_populates="order", cascade="all, delete-orphan", order_by="DeliveryDateRevision.created_at.desc()")
    production_entries = relationship("DailyProductionEntry", back_populates="order", cascade="all, delete-orphan")


class DeliveryDateRevision(Base):
    __tablename__ = "delivery_date_revisions"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    previous_delivery_date = Column(Date, nullable=False)
    revised_delivery_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)
    revised_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    order = relationship("Order", back_populates="delivery_revisions")
    revised_by_user = relationship("User")
