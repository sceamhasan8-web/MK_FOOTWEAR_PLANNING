from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class Buyer(Base):
    __tablename__ = "buyers"

    id = Column(Integer, primary_key=True, index=True)
    buyer_code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False, index=True)
    contact_person = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    orders = relationship("Order", back_populates="buyer", cascade="all, delete-orphan")
