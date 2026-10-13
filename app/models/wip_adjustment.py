from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class WipAdjustment(Base):
    """
    Controlled WIP stock adjustment record (Section 42 & 46).
    Normal users cannot manually edit On Hand.
    All stock adjustments require quantity, section/workflow, date, reason, user, and audit trail.
    """
    __tablename__ = "wip_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    workflow_id = Column(Integer, ForeignKey("order_routes.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    quantity = Column(Float, nullable=False)  # positive or negative adjustment
    reason = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(50), default="APPROVED", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    order = relationship("Order")
    route = relationship("OrderRoute")
    user = relationship("User")
