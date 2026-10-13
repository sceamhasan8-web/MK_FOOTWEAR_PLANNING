from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.models.user import UserRole, User
from app.schemas.calendar import (
    FactoryCalendarCreate,
    FactoryCalendarUpdate,
    FactoryCalendarOut,
    CalendarExceptionCreate,
    CalendarExceptionOut,
)
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/calendar", tags=["Factory Calendar"])


@router.get("", response_model=List[FactoryCalendarOut])
def get_calendars(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(FactoryCalendar).all()


@router.get("/active", response_model=FactoryCalendarOut)
def get_active_calendar(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cal = db.query(FactoryCalendar).filter(FactoryCalendar.is_default == True).first()
    if not cal:
        cal = db.query(FactoryCalendar).first()
    if not cal:
        raise HTTPException(status_code=404, detail="No factory calendar found")
    return cal


@router.put("/{calendar_id}", response_model=FactoryCalendarOut)
def update_calendar(
    calendar_id: int,
    cal_update: FactoryCalendarUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    cal = db.query(FactoryCalendar).filter(FactoryCalendar.id == calendar_id).first()
    if not cal:
        raise HTTPException(status_code=404, detail="Calendar not found")

    update_data = cal_update.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(cal, field, val)

    db.commit()
    db.refresh(cal)
    return cal


@router.post("/{calendar_id}/exceptions", response_model=CalendarExceptionOut)
def add_calendar_exception(
    calendar_id: int,
    ex_in: CalendarExceptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    cal = db.query(FactoryCalendar).filter(FactoryCalendar.id == calendar_id).first()
    if not cal:
        raise HTTPException(status_code=404, detail="Calendar not found")

    # Check existing exception on same date
    existing = db.query(CalendarException).filter(
        CalendarException.calendar_id == calendar_id,
        CalendarException.exception_date == ex_in.exception_date
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Exception for this date already exists")

    ex = CalendarException(calendar_id=calendar_id, **ex_in.model_dump())
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return ex


@router.put("/exceptions/{exception_id}", response_model=CalendarExceptionOut)
def update_calendar_exception(
    exception_id: int,
    ex_in: CalendarExceptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    ex = db.query(CalendarException).filter(CalendarException.id == exception_id).first()
    if not ex:
        raise HTTPException(status_code=404, detail="Exception not found")
    ex.exception_date = ex_in.exception_date
    ex.exception_type = ex_in.exception_type
    ex.description = ex_in.description
    db.commit()
    db.refresh(ex)
    return ex


@router.delete("/exceptions/{exception_id}")
def delete_calendar_exception(
    exception_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    ex = db.query(CalendarException).filter(CalendarException.id == exception_id).first()
    if not ex:
        raise HTTPException(status_code=404, detail="Exception not found")
    db.delete(ex)
    db.commit()
    return {"detail": "Calendar exception deleted successfully"}

