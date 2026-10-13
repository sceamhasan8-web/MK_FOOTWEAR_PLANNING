from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    entity_name = Column(String(100), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)  # CREATE, UPDATE, REVISE, REVERSE, OVERRIDE
    setting_type = Column(String(50), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    details = Column(Text, nullable=True)  # JSON or descriptive text of old/new values
    reason = Column(Text, nullable=True)
    affected_order_count = Column(Integer, default=0, nullable=True)
    recalculation_status = Column(String(50), nullable=True)

    user = relationship("User")
