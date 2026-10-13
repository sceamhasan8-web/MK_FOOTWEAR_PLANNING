import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class ExceptionType(str, enum.Enum):
    HOLIDAY = "holiday"
    CLOSURE = "closure"
    EXTRA_WORKDAY = "extra_workday"
    FACTORY_HOLIDAY = "factory_holiday"
    GOVERNMENT_HOLIDAY = "government_holiday"
    EMERGENCY_OFF = "emergency_off"
    SPECIAL_WORKING_DAY = "special_working_day"
    FACTORY_SHUTDOWN = "factory_shutdown"


class FactoryCalendar(Base):
    __tablename__ = "factory_calendars"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    
    # Working days of the week (Default Bangladesh/standard: Friday is weekend off, Sat-Thu work)
    work_monday = Column(Boolean, default=True, nullable=False)
    work_tuesday = Column(Boolean, default=True, nullable=False)
    work_wednesday = Column(Boolean, default=True, nullable=False)
    work_thursday = Column(Boolean, default=True, nullable=False)
    work_friday = Column(Boolean, default=False, nullable=False)  # Weekend in BD factory
    work_saturday = Column(Boolean, default=True, nullable=False)
    work_sunday = Column(Boolean, default=True, nullable=False)

    cutoff_hour = Column(Integer, default=18, nullable=False)
    cutoff_minute = Column(Integer, default=0, nullable=False)
    timezone = Column(String(50), default="Asia/Dhaka", nullable=False)
    use_working_days_only = Column(Boolean, default=True, nullable=False)
    same_day_category_transfer = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    exceptions = relationship("CalendarException", back_populates="calendar", cascade="all, delete-orphan")


class CalendarException(Base):
    __tablename__ = "calendar_exceptions"

    id = Column(Integer, primary_key=True, index=True)
    calendar_id = Column(Integer, ForeignKey("factory_calendars.id"), nullable=False, index=True)
    exception_date = Column(Date, nullable=False, index=True)
    exception_type = Column(Enum(ExceptionType), default=ExceptionType.HOLIDAY, nullable=False)
    description = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    calendar = relationship("FactoryCalendar", back_populates="exceptions")
