import pytest
from datetime import date, timedelta
from app.services.production_planning_service import ProductionPlanningService
from app.services.calendar_service import CalendarService
from app.models.route import Section
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType


# =========================================================================
# TEST 1 – Exact Division
# =========================================================================
def test_exact_division_test_1():
    """
    TEST 1 – Exact Division:
    Balance = 30,000, Days = 10
    Expected: 3,000 x 10, Total = 30,000
    """
    balance = 30000
    working_dates = [date(2026, 10, 1) + timedelta(days=i) for i in range(10)]
    result = ProductionPlanningService.distribute_exact_target(balance, working_dates)

    assert len(result) == 10
    assert all(qty == 3000 for qty in result.values())
    assert sum(result.values()) == balance


# =========================================================================
# TEST 2 – Division With Remainder
# =========================================================================
def test_division_with_remainder_test_2():
    """
    TEST 2 – Division With Remainder:
    Balance = 30,000, Days = 9
    Expected:
    Day 1 = 3,334
    Day 2 = 3,334
    Day 3 = 3,334
    Day 4 = 3,333
    ...
    Day 9 = 3,333
    Total = 30,000
    """
    balance = 30000
    working_dates = [date(2026, 10, 1) + timedelta(days=i) for i in range(9)]
    result = ProductionPlanningService.distribute_exact_target(balance, working_dates)

    targets = list(result.values())
    assert targets == [3334, 3334, 3334, 3333, 3333, 3333, 3333, 3333, 3333]
    assert sum(targets) == balance


# =========================================================================
# TEST 3 – Very Small Balance
# =========================================================================
def test_very_small_balance_test_3():
    """
    TEST 3 – Very Small Balance:
    Balance = 5, Days = 9
    Expected:
    1, 1, 1, 1, 1, 0, 0, 0, 0
    Total = 5
    """
    balance = 5
    working_dates = [date(2026, 10, 1) + timedelta(days=i) for i in range(9)]
    result = ProductionPlanningService.distribute_exact_target(balance, working_dates)

    targets = list(result.values())
    assert targets == [1, 1, 1, 1, 1, 0, 0, 0, 0]
    assert sum(targets) == balance


# =========================================================================
# TEST 4 – One Working Day
# =========================================================================
def test_one_working_day_test_4():
    """
    TEST 4 – One Working Day:
    Balance = 30,000, Days = 1
    Expected: 30,000
    """
    balance = 30000
    working_dates = [date(2026, 10, 1)]
    result = ProductionPlanningService.distribute_exact_target(balance, working_dates)

    assert result[date(2026, 10, 1)] == 30000
    assert sum(result.values()) == balance


# =========================================================================
# TEST 5 – No Working Day
# =========================================================================
def test_no_working_day_test_5():
    """
    TEST 5 – No Working Day:
    Balance = 30,000, Days = 0
    Expected: Controlled NO_WORKING_DAYS business error. No division by zero.
    """
    balance = 30000
    working_dates = []
    with pytest.raises(ValueError) as excinfo:
        ProductionPlanningService.distribute_exact_target(balance, working_dates)
    assert "NO_AVAILABLE_WORKING_DAYS" in str(excinfo.value)

    # Balance 0 with 0 days should return empty dict cleanly
    empty_result = ProductionPlanningService.distribute_exact_target(0, working_dates)
    assert empty_result == {}


# =========================================================================
# TEST 6 – Selected Order Filter
# =========================================================================
def test_selected_order_filter_test_6(client, auth_headers, db_session):
    """
    TEST 6 – Selected Order Filter:
    Database contains:
    Order A = 30,000
    Order B = 50,000
    Select Order A.
    Expected total plan = 30,000.
    Order B must not affect the calculation.
    """
    admin_hdr = auth_headers("admin")

    # Create Buyer
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "BATA Selective",
        "buyer_code": "BATA-SEL",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    # Create Order A (30,000 pairs)
    r_ord_a = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-BATA-30K-ISO",
        "customer_ref": "REF-A",
        "style_model": "Style A",
        "total_quantity": 30000.0,
        "production_start_date": "2026-10-08",
        "original_delivery_date": "2026-10-18",
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    assert r_ord_a.status_code == 200
    order_a_id = r_ord_a.json()["id"]

    # Create Order B (50,000 pairs)
    r_ord_b = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-BATA-50K-ISO",
        "customer_ref": "REF-B",
        "style_model": "Style B",
        "total_quantity": 50000.0,
        "production_start_date": "2026-10-08",
        "original_delivery_date": "2026-10-18",
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    assert r_ord_b.status_code == 200
    order_b_id = r_ord_b.json()["id"]

    # Request Matrix Planning Sheet specifically for Order A
    r_matrix_a = client.get(f"/api/v1/orders/{order_a_id}/matrix-planning", headers=admin_hdr)
    assert r_matrix_a.status_code == 200
    data_a = r_matrix_a.json()

    assert data_a["order_id"] == order_a_id
    assert data_a["total_quantity"] == 30000.0
    assert data_a["current_balance"] == 30000.0

    # Total planned target for Order A must be exactly 30,000, not 80,000 or 50,000
    cut_summary = data_a["summary"]["CUTTING"]
    assert cut_summary["total_tg"] == 30000.0
    assert data_a["validation"]["target_equals_balance"] is True


# =========================================================================
# TEST 7 – Production Entry & Replanning
# =========================================================================
def test_production_entry_replanning_test_7(client, auth_headers, db_session):
    """
    TEST 7 – Production Entry:
    Balance = 30,000
    Actual = 5,000
    New balance = 25,000.
    Rebuild remaining plan:
    SUM(Future T/G) == 25,000
    """
    admin_hdr = auth_headers("admin")
    sup_hdr = auth_headers("supervisor")

    r_buyer = client.post("/api/v1/buyers", json={"name": "Replan Buyer", "buyer_code": "RP-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    today_str = str(date.today())
    ship_str = str(date.today() + timedelta(days=12))

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-REPLAN-30K",
        "customer_ref": "REF-RP",
        "style_model": "Style Replan",
        "total_quantity": 30000.0,
        "production_start_date": today_str,
        "original_delivery_date": ship_str,
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    order = r_ord.json()
    order_id = order["id"]
    route_id = order["routes"][0]["id"]
    op_id = order["routes"][0]["operations"][0]["id"]

    # Initial plan: total_tg = 30,000
    r_m1 = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    assert r_m1.json()["summary"]["CUTTING"]["total_tg"] == 30000.0

    # Log 5,000 pairs actual production for today
    r_entry = client.post("/api/v1/production/entry", json={
        "entry_date": today_str,
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": 5000.0,
        "accepted_quantity": 5000.0,
        "rejected_quantity": 0.0
    }, headers=sup_hdr)
    assert r_entry.status_code == 200

    # Retrieve recalculated matrix plan
    r_m2 = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    assert r_m2.status_code == 200
    data2 = r_m2.json()

    cut_sum2 = data2["summary"]["CUTTING"]
    assert cut_sum2["total_ot"] == 5000.0
    assert cut_sum2["balance"] == 25000.0
    # Future target total must equal the new balance of 25,000 exactly!
    assert cut_sum2["future_target_total"] == 25000.0
    assert data2["validation"]["target_equals_balance"] is True


# =========================================================================
# TEST 8 – Shipment Date Change
# =========================================================================
def test_shipment_date_change_test_8(client, auth_headers, db_session):
    """
    TEST 8 – Shipment Date Change:
    Increase shipment date.
    Verify more working dates and regenerated future targets.
    """
    admin_hdr = auth_headers("admin")

    r_buyer = client.post("/api/v1/buyers", json={"name": "Ship Ext Buyer", "buyer_code": "SE-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    today_str = str(date.today())
    ship1_str = str(date.today() + timedelta(days=5))

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-SHIP-EXT",
        "customer_ref": "REF-SE",
        "style_model": "Style Ext",
        "total_quantity": 20000.0,
        "production_start_date": today_str,
        "original_delivery_date": ship1_str,
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    order_id = r_ord.json()["id"]

    r_m1 = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    initial_rows = len(r_m1.json()["rows"])

    # Revise shipment date +5 days further
    ship2_str = str(date.today() + timedelta(days=10))
    r_rev = client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": ship2_str,
        "reason": "Customer agreed extension"
    }, headers=admin_hdr)
    assert r_rev.status_code == 200

    r_m2 = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    new_data = r_m2.json()
    new_rows = len(new_data["rows"])

    assert new_rows > initial_rows
    assert new_data["summary"]["CUTTING"]["total_tg"] == 20000.0
    assert new_data["validation"]["target_equals_balance"] is True


# =========================================================================
# TEST 9 – Factory Holiday
# =========================================================================
def test_factory_holiday_test_9(client, auth_headers, db_session):
    """
    TEST 9 – Factory Holiday:
    Add one factory holiday.
    Verify target distribution is recalculated across remaining working days,
    and the holiday receives 0 T/G.
    """
    admin_hdr = auth_headers("admin")

    r_buyer = client.post("/api/v1/buyers", json={"name": "Holiday Buyer", "buyer_code": "HB-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    today_str = str(date.today())
    ship_str = str(date.today() + timedelta(days=7))

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-HOLIDAY-TEST",
        "customer_ref": "REF-HB",
        "style_model": "Style Holiday",
        "total_quantity": 21000.0,
        "production_start_date": today_str,
        "original_delivery_date": ship_str,
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    order_id = r_ord.json()["id"]

    # Add a custom factory holiday 2 days from today
    cal = CalendarService.get_active_calendar(db_session)
    holiday_date = date.today() + timedelta(days=2)
    holiday = CalendarException(
        calendar_id=cal.id,
        exception_date=holiday_date,
        exception_type=ExceptionType.FACTORY_HOLIDAY,
        description="Factory Maintenance Day"
    )
    db_session.add(holiday)
    db_session.commit()

    r_m = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    data = r_m.json()

    # Find the row for the holiday date
    holiday_row = next((r for r in data["rows"] if r["date"] == str(holiday_date)), None)
    assert holiday_row is not None
    assert holiday_row["is_workday"] is False
    assert holiday_row["section_data"]["CUTTING"]["tg"] == 0.0

    # Total planned targets must still sum exactly to 21,000 across the working days!
    assert data["summary"]["CUTTING"]["total_tg"] == 21000.0
    assert data["validation"]["target_equals_balance"] is True


# =========================================================================
# TEST 10 – Friday Off
# =========================================================================
def test_friday_off_test_10(client, auth_headers, db_session):
    """
    TEST 10 – Friday Off:
    Mark Friday as weekly off in factory calendar.
    Verify no target is assigned to Friday (T/G = 0).
    """
    admin_hdr = auth_headers("admin")

    # Ensure active calendar has Friday marked as off
    cal = CalendarService.get_active_calendar(db_session)
    cal.work_friday = False
    db_session.commit()

    r_buyer = client.post("/api/v1/buyers", json={"name": "Friday Buyer", "buyer_code": "FB-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    # Create order spanning at least 14 days to guarantee a Friday
    today_d = date.today()
    ship_d = today_d + timedelta(days=14)

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-FRIDAY-OFF",
        "customer_ref": "REF-FB",
        "style_model": "Friday Shoe",
        "total_quantity": 30000.0,
        "production_start_date": str(today_d),
        "original_delivery_date": str(ship_d),
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    order_id = r_ord.json()["id"]

    r_m = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    data = r_m.json()

    friday_rows = [r for r in data["rows"] if r["day_name"] == "Friday"]
    assert len(friday_rows) > 0, "Plan must contain at least one Friday"

    for f_row in friday_rows:
        assert f_row["is_workday"] is False
        assert f_row["section_data"]["CUTTING"]["tg"] == 0.0

    # Total targets sum to 30,000 exactly
    assert data["summary"]["CUTTING"]["total_tg"] == 30000.0


# =========================================================================
# TEST 11 – Exact Total Validation Assertion
# =========================================================================
def test_exact_total_validation_test_11(client, auth_headers, db_session):
    """
    TEST 11 – Exact Total Validation:
    For every generated plan: SUM(T/G) == Current Balance must be true.
    Automated assertion verifying that no rounding drift occurs.
    """
    admin_hdr = auth_headers("admin")

    r_buyer = client.post("/api/v1/buyers", json={"name": "Validation Buyer", "buyer_code": "VB-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_names = ["Cutting", "Printing", "Sewing"]
    sec_objs = [db_session.query(Section).filter(Section.name == name).first() for name in sec_names]

    # Test with prime quantities and odd working day counts (e.g., 29,999 pairs over 11 days)
    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-VALIDATE-EXACT",
        "customer_ref": "REF-VB",
        "style_model": "Validation Shoe",
        "total_quantity": 29999.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(date.today() + timedelta(days=12)),
        "routes": [
            {"section_id": s.id, "status": "REQUIRED", "operations": [{"operation_name": f"{s.name} Op", "sequence_order": 1}]}
            for s in sec_objs
        ]
    }, headers=admin_hdr)
    order_id = r_ord.json()["id"]

    r_m = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    data = r_m.json()

    # Validation banner flag must be True
    assert data["validation"]["target_equals_balance"] is True

    # Validate Cutting (Section 1 with 29,999 On Hand) allocates exactly 29,999
    cut_sum = data["summary"]["CUTTING"]
    assert cut_sum["total_tg"] == 29999.0
    assert cut_sum["target_matches_balance"] is True
    computed_cut_sum = sum(r["section_data"]["CUTTING"]["tg"] for r in data["rows"])
    assert computed_cut_sum == 29999.0

    # Downstream sections without WIP received cannot allocate targets (Rule 2 & Test D)
    for s_name in ["PRINTING", "SEWING"]:
        sec_sum = data["summary"][s_name]
        assert sec_sum["total_tg"] == 0.0
        assert sec_sum["status"] == "WAITING FOR WIP"
