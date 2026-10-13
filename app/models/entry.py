from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class DailyProductionEntry(Base):
    __tablename__ = "daily_production_entries"

    id = Column(Integer, primary_key=True, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    route_id = Column(Integer, ForeignKey("order_routes.id"), nullable=False, index=True)
    operation_id = Column(Integer, ForeignKey("order_operations.id"), nullable=False, index=True)
    component_id = Column(Integer, ForeignKey("operation_components.id"), nullable=True, index=True)

    quantity = Column(Float, nullable=False)
    accepted_quantity = Column(Float, nullable=False)
    rejected_quantity = Column(Float, default=0.0, nullable=False)
    unit = Column(String(20), default="PAIRS", nullable=False)
    remarks = Column(Text, nullable=True)

    entered_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_reversed = Column(Boolean, default=False, nullable=False)
    is_override = Column(Boolean, default=False, nullable=False)

    # Relationships
    order = relationship("Order", back_populates="production_entries")
    route = relationship("OrderRoute")
    operation = relationship("OrderOperation", back_populates="entries")
    component = relationship("OperationComponent", back_populates="entries")
    entered_by_user = relationship("User", back_populates="production_entries")
    corrections = relationship("ProductionEntryCorrection", back_populates="entry", cascade="all, delete-orphan")


class ProductionEntryCorrection(Base):
    __tablename__ = "production_entry_corrections"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(Integer, ForeignKey("daily_production_entries.id"), nullable=False, index=True)
    original_accepted_qty = Column(Float, nullable=False)
    new_accepted_qty = Column(Float, nullable=False)
    original_rejected_qty = Column(Float, nullable=False)
    new_rejected_qty = Column(Float, nullable=False)
    action_type = Column(String(50), default="EDIT", nullable=False)  # EDIT or REVERSAL
    reason = Column(Text, nullable=False)
    authorized_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    entry = relationship("DailyProductionEntry", back_populates="corrections")
    authorized_by_user = relationship("User")
