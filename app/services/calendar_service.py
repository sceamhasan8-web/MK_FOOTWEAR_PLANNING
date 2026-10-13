import math
from datetime import date, datetime, timedelta, time
from typing import List, Tuple, Set, Optional
from sqlalchemy.orm import Session
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.config import settings


class CalendarService:
    @staticmethod
    def get_active_calendar(db: Session, calendar_id: int = None) -> FactoryCalendar:
        if calendar_id:
            cal = db.query(FactoryCalendar).filter(FactoryCalendar.id == calendar_id).first()
            if cal:
                return cal
        # Try default
        cal = db.query(FactoryCalendar).filter(FactoryCalendar.is_default == True).first()
        if cal:
            return cal
        # Fallback first or create standard
        cal = db.query(FactoryCalendar).first()
        if not cal:
            cal = FactoryCalendar(
                name="Standard Factory Calendar",
                is_default=True,
                work_monday=True,
                work_tuesday=True,
                work_wednesday=True,
                work_thursday=True,
                work_friday=False,  # Bangladesh factory standard weekend
                work_saturday=True,
                work_sunday=True,
                cutoff_hour=settings.DEFAULT_CUTOFF_HOUR,
                cutoff_minute=settings.DEFAULT_CUTOFF_MINUTE,
                timezone=settings.DEFAULT_TIMEZONE
            )
            db.add(cal)
            db.commit()
            db.refresh(cal)
        return cal

    @classmethod
    def is_working_day(
        cls,
        d: date,
        calendar: FactoryCalendar,
        exceptions: List[CalendarException],
        use_working_days_only: Optional[bool] = None
    ) -> bool:
        working_days_mode = (
            use_working_days_only 
            if use_working_days_only is not None 
            else getattr(calendar, "use_working_days_only", True)
        )

        off_types = {
            ExceptionType.HOLIDAY, ExceptionType.CLOSURE,
            ExceptionType.FACTORY_HOLIDAY, ExceptionType.GOVERNMENT_HOLIDAY,
            ExceptionType.EMERGENCY_OFF, ExceptionType.FACTORY_SHUTDOWN,
            "holiday", "closure", "factory_holiday", "government_holiday",
            "emergency_off", "factory_shutdown"
        }
        work_types = {
            ExceptionType.EXTRA_WORKDAY, ExceptionType.SPECIAL_WORKING_DAY,
            "extra_workday", "special_working_day"
        }

        # In calendar days mode (working_days_mode is False), count every day except factory closures/holidays
        if not working_days_mode:
            for ex in exceptions:
                if ex.exception_date == d and ex.exception_type in off_types:
                    return False
            return True

        # Check explicit calendar exceptions first
        for ex in exceptions:
            if ex.exception_date == d:
                if ex.exception_type in off_types:
                    return False
                if ex.exception_type in work_types:
                    return True

        # Check day of week (Monday is 0, Sunday is 6) - fully configurable from Settings
        weekday = d.weekday()
        weekday_map = {
            0: calendar.work_monday,
            1: calendar.work_tuesday,
            2: calendar.work_wednesday,
            3: calendar.work_thursday,
            4: calendar.work_friday,
            5: calendar.work_saturday,
            6: calendar.work_sunday,
        }
        return weekday_map.get(weekday, True)

    @classmethod
    def get_remaining_working_days(
        cls,
        db: Session,
        start_date: date,
        delivery_date: date,
        calendar_id: int = None,
        as_of_date: date = None,
        current_time: time = None,
        use_working_days_only: Optional[bool] = None
    ) -> Tuple[int, List[date]]:
        """
        Calculates remaining working/available production days from running date up to delivery_date.
        Respects configured factory working days, factory holidays/closures, and cutoff time.
        """
        calendar = cls.get_active_calendar(db, calendar_id)
        exceptions = db.query(CalendarException).filter(CalendarException.calendar_id == calendar.id).all()

        # Authoritative planning starts from as_of_date (current running date)
        if as_of_date is not None:
            plan_start = as_of_date
        else:
            plan_start = max(start_date, date.today())
        
        if plan_start > delivery_date:
            return 0, []

        working_dates: List[date] = []
        curr = plan_start
        while curr <= delivery_date:
            if cls.is_working_day(curr, calendar, exceptions, use_working_days_only):
                # If curr is today, check if cutoff has passed
                if as_of_date is not None and curr == as_of_date and current_time is not None:
                    cutoff = time(calendar.cutoff_hour, calendar.cutoff_minute)
                    if current_time <= cutoff:
                        working_dates.append(curr)
                else:
                    working_dates.append(curr)
            curr += timedelta(days=1)

        return len(working_dates), working_dates
