from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field
from app.models.calendar import ExceptionType


class CalendarExceptionBase(BaseModel):
    exception_date: date
    exception_type: ExceptionType = ExceptionType.HOLIDAY
    description: str = Field(..., max_length=200)


class CalendarExceptionCreate(CalendarExceptionBase):
    pass


class CalendarExceptionOut(CalendarExceptionBase):
    id: int
    calendar_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class FactoryCalendarBase(BaseModel):
    name: str
    is_default: bool = False
    work_monday: bool = True
    work_tuesday: bool = True
    work_wednesday: bool = True
    work_thursday: bool = True
    work_friday: bool = False  # BD standard
    work_saturday: bool = True
    work_sunday: bool = True
    cutoff_hour: int = 18
    cutoff_minute: int = 0
    timezone: str = "Asia/Dhaka"
    use_working_days_only: bool = True
    same_day_category_transfer: bool = False


class FactoryCalendarCreate(FactoryCalendarBase):
    pass


class FactoryCalendarUpdate(BaseModel):
    name: Optional[str] = None
    is_default: Optional[bool] = None
    work_monday: Optional[bool] = None
    work_tuesday: Optional[bool] = None
    work_wednesday: Optional[bool] = None
    work_thursday: Optional[bool] = None
    work_friday: Optional[bool] = None
    work_saturday: Optional[bool] = None
    work_sunday: Optional[bool] = None
    cutoff_hour: Optional[int] = None
    cutoff_minute: Optional[int] = None
    timezone: Optional[str] = None
    use_working_days_only: Optional[bool] = None
    same_day_category_transfer: Optional[bool] = None


class FactoryCalendarOut(FactoryCalendarBase):
    id: int
    created_at: datetime
    updated_at: datetime
    exceptions: List[CalendarExceptionOut] = []

    class Config:
        from_attributes = True
