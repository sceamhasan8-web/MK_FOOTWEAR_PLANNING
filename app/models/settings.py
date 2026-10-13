from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class SystemSetting(Base):
    """
    Central normalized configuration store for ERP settings.
    Stores typed configuration settings with change auditing.
    """
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False, index=True)  # general, wip, production_entry, planning_validation, reports
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    data_type = Column(String(20), default="string", nullable=False)  # string, integer, boolean, json
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    updated_by = relationship("User")
