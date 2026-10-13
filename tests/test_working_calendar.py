from datetime import date, timedelta
from app.services.calendar_service import CalendarService
from app.models.calendar import CalendarException, ExceptionType


def test_scenario_e_working_calendar(client, auth_headers, db_session):
    """
    Scenario E: Working calendar
    Add a factory holiday and exclude non-working weekdays.
    Verify that these dates are not included in the available production-day count.
    """
    admin_hdr = auth_headers("admin")

    cal = CalendarService.get_active_calendar(db_session)
    assert cal.work_friday is False  # Friday is excluded as non-working weekday

    start_d = date(2026, 10, 1)  # Thursday
    end_d = date(2026, 10, 7)    # Wednesday (7 calendar days total)

    # Count without holiday first
    days_count_initial, dates_initial = CalendarService.get_remaining_working_days(
        db_session, start_d, end_d, as_of_date=start_d
    )

    # Friday Oct 2 is non-working, so standard working days are 6 (Thu, Sat, Sun, Mon, Tue, Wed)
    assert days_count_initial == 6
    assert date(2026, 10, 2) not in dates_initial  # Friday excluded!

    # Add a holiday on Monday Oct 5
    holiday_date = date(2026, 10, 5)
    r_ex = client.post(f"/api/v1/calendar/{cal.id}/exceptions", json={
        "exception_date": str(holiday_date),
        "exception_type": "holiday",
        "description": "National Holiday"
    }, headers=admin_hdr)
    assert r_ex.status_code == 200, r_ex.text

    # Recount
    days_count_after, dates_after = CalendarService.get_remaining_working_days(
        db_session, start_d, end_d, as_of_date=start_d
    )

    # Monday Oct 5 must now be excluded, so count drops to 5
    assert days_count_after == 5
    assert holiday_date not in dates_after
    assert date(2026, 10, 2) not in dates_after
