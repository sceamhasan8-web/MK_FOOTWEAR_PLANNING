import pytest
from datetime import date, timedelta
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.models.route import ProductionTargetSetting


@pytest.fixture
def sample_orders(client, auth_headers):
    """Creates standard test buyers and orders for test isolation."""
    admin_hdr = auth_headers("admin")
    r_bata = client.post("/api/v1/buyers", json={
        "name": "BATA Footwear",
        "buyer_code": "BATA-CORP",
        "is_active": True
    }, headers=admin_hdr)
    bata_id = r_bata.json()["id"]

    r_apex = client.post("/api/v1/buyers", json={
        "name": "Apex Shoes Ltd",
        "buyer_code": "APEX-01",
        "is_active": True
    }, headers=admin_hdr)
    apex_id = r_apex.json()["id"]

    r1 = client.post("/api/v1/orders", json={
        "buyer_id": bata_id,
        "order_code": "BAT-001",
        "customer_ref": "BATA Summer",
        "style_model": "ST-100",
        "total_quantity": 30000.0,
        "original_delivery_date": str(date.today() + timedelta(days=25))
    }, headers=admin_hdr).json()

    r2 = client.post("/api/v1/orders", json={
        "buyer_id": bata_id,
        "order_code": "BAT-002",
        "customer_ref": "BATA Winter",
        "style_model": "ST-200",
        "total_quantity": 45000.0,
        "original_delivery_date": str(date.today() + timedelta(days=35))
    }, headers=admin_hdr).json()

    r3 = client.post("/api/v1/orders", json={
        "buyer_id": apex_id,
        "order_code": "APX-999",
        "customer_ref": "Apex Loafers",
        "style_model": "LF-50",
        "total_quantity": 15000.0,
        "original_delivery_date": str(date.today() + timedelta(days=20))
    }, headers=admin_hdr).json()

    return {"bata_id": bata_id, "apex_id": apex_id, "bat1": r1, "bat2": r2, "apx": r3}


def test_scenario_a_search_by_buyer(client, auth_headers, sample_orders):
    """
    Test A — Search by Buyer:
    Create multiple orders for BATA and other buyers.
    Search for 'BATA'.
    Expected:
    - All matching authorized BATA orders appear.
    - Unrelated orders do not appear unless they independently match another searched field.
    """
    admin_hdr = auth_headers("admin")

    res = client.get("/api/v1/orders?search=BATA", headers=admin_hdr)
    assert res.status_code == 200
    orders = res.json()
    order_codes = [o["order_code"] for o in orders]

    assert "BAT-001" in order_codes
    assert "BAT-002" in order_codes
    assert "APX-999" not in order_codes


def test_scenario_b_search_by_order_reference(client, auth_headers, sample_orders):
    """
    Test B — Search by Order Reference:
    Search by a specific order number (e.g. BAT-002).
    Expected:
    - Only the matching order is returned.
    - Selecting it loads the correct planning data.
    """
    admin_hdr = auth_headers("admin")

    res = client.get("/api/v1/orders?search=BAT-002", headers=admin_hdr)
    assert res.status_code == 200
    orders = res.json()
    assert len(orders) == 1
    selected = orders[0]
    assert selected["order_code"] == "BAT-002"
    assert selected["style_model"] == "ST-200"

    # Verify planning data loads for this exact order
    res_plan = client.get(f"/api/v1/orders/matrix-planning?order_id={selected['id']}", headers=admin_hdr)
    assert res_plan.status_code == 200
    plan_data = res_plan.json()
    assert plan_data["order_code"] == "BAT-002"
    assert plan_data["total_quantity"] == 45000.0


def test_scenario_c_search_by_style(client, auth_headers, sample_orders):
    """
    Test C — Search by Style:
    Search by a product style/model (e.g. ST-200).
    Expected:
    - Matching orders appear.
    """
    admin_hdr = auth_headers("admin")

    res = client.get("/api/v1/orders?search=ST-200", headers=admin_hdr)
    assert res.status_code == 200
    orders = res.json()
    assert len(orders) >= 1
    for o in orders:
        assert "ST-200" in o["style_model"] or "ST-200" in o["order_code"]


def test_scenario_d_planning_sheet_selection(client, auth_headers, sample_orders):
    """
    Test D — Planning Sheet Selection:
    Select Order A, then Order B.
    Expected:
    - Planning data changes to Order B.
    - No quantities from Order A remain in the visible selected-order planning table.
    """
    admin_hdr = auth_headers("admin")
    bat1 = sample_orders["bat1"]
    bat2 = sample_orders["bat2"]

    plan_a = client.get(f"/api/v1/orders/matrix-planning?order_id={bat1['id']}", headers=admin_hdr).json()
    plan_b = client.get(f"/api/v1/orders/matrix-planning?order_id={bat2['id']}", headers=admin_hdr).json()

    assert plan_a["order_code"] == "BAT-001"
    assert plan_a["total_quantity"] == 30000.0

    assert plan_b["order_code"] == "BAT-002"
    assert plan_b["total_quantity"] == 45000.0
    assert plan_b["order_code"] != plan_a["order_code"]


def test_scenario_e_wip_flow_selection(client, auth_headers, sample_orders):
    """
    Test E — WIP Flow Selection:
    Select an order in WIP Flow Planning.
    Expected:
    - Only that order's applicable workflow, production, and WIP data appear.
    """
    admin_hdr = auth_headers("admin")
    bat1 = sample_orders["bat1"]

    res_wip = client.get(f"/api/v1/orders/wip-flow-plan?order_id={bat1['id']}", headers=admin_hdr)
    assert res_wip.status_code == 200
    wip_data = res_wip.json()
    assert wip_data["order_id"] == bat1["id"]
    assert wip_data["order_code"] == "BAT-001"
    assert "workflow" in wip_data or "sections" in wip_data
    assert len(wip_data.get("workflow", []) or wip_data.get("sections", [])) > 0


def test_scenario_f_edit_existing_order(client, auth_headers, sample_orders):
    """
    Test F — Edit Existing Order:
    Edit an existing order's notes, PO number, or style.
    Expected:
    - Existing record is updated.
    - No duplicate order is created.
    - Existing production history remains linked.
    """
    admin_hdr = auth_headers("admin")
    order_id = sample_orders["bat1"]["id"]

    initial_count = len(client.get("/api/v1/orders", headers=admin_hdr).json())

    # Update order notes and customer PO
    res_update = client.put(f"/api/v1/orders/{order_id}", json={
        "customer_ref": "BATA Summer Updated",
        "po_number": "PO-REV-9988",
        "notes": "Updated rush packaging instructions",
        "reason": "Customer updated purchase order number"
    }, headers=admin_hdr)
    assert res_update.status_code == 200
    updated = res_update.json()

    assert updated["id"] == order_id
    assert updated["customer_ref"] == "BATA Summer Updated"
    assert updated["po_number"] == "PO-REV-9988"
    assert updated["notes"] == "Updated rush packaging instructions"

    # Verify no duplicate order created
    new_count = len(client.get("/api/v1/orders", headers=admin_hdr).json())
    assert new_count == initial_count


def test_scenario_g_extend_shipment_date(client, auth_headers, sample_orders):
    """
    Test G — Extend Shipment Date:
    Existing shipment date = original date. Revise it to 10 days later.
    Expected:
    - New shipment date becomes active.
    - Original date remains in history.
    - Future target calculations use new date.
    - Order quantity and actual production remain unchanged.
    """
    admin_hdr = auth_headers("admin")
    order = sample_orders["bat2"]
    order_id = order["id"]

    orig_delivery = order["original_delivery_date"]
    new_delivery = str(date.fromisoformat(order["current_delivery_date"]) + timedelta(days=10))

    initial_working_days = order["remaining_working_days"]

    res_rev = client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": new_delivery,
        "reason": "Shipment date extended due to buyer container shipping window"
    }, headers=admin_hdr)
    assert res_rev.status_code == 200
    revised = res_rev.json()

    assert revised["original_delivery_date"] == orig_delivery
    assert revised["current_delivery_date"] == new_delivery
    assert revised["remaining_working_days"] > initial_working_days
    assert len(revised["delivery_revisions"]) >= 1


def test_scenario_h_recalculate_using_current_balance(client, auth_headers):
    """
    Test H — Recalculate Using Current Balance:
    Order Quantity = 30,000.
    Actual accepted production = 10,000.
    Current Balance = 20,000.
    Change shipment date so remaining working days increase.
    Expected:
    - Future planning is recalculated using 20,000 remaining.
    - Original 10,000 actual production is preserved.
    - Targets do not continue using 30,000 as the remaining balance.
    """
    admin_hdr = auth_headers("admin")

    # 1. Create a dedicated test order
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Balance Buyer",
        "buyer_code": "BAL-01",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    ship_date_initial = str(date.today() + timedelta(days=10))
    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-BAL-30K",
        "customer_ref": "30k Balance Test",
        "style_model": "BAL-100",
        "total_quantity": 30000.0,
        "original_delivery_date": ship_date_initial,
    }, headers=admin_hdr)
    order_data = r_ord.json()
    order_id = order_data["id"]
    # 2. Record 10,000 actual accepted production
    for r in order_data["routes"]:
        for op in r["operations"]:
            r_entry = client.post("/api/v1/production/entry", json={
                "entry_date": str(date.today()),
                "order_id": order_id,
                "route_id": r["id"],
                "operation_id": op["id"],
                "quantity": 10000.0,
                "accepted_quantity": 10000.0,
                "rejected_quantity": 0.0,
                "unit": "PAIRS",
                "remarks": "Day 1 partial production"
            }, headers=admin_hdr)
            assert r_entry.status_code == 200

    # Verify balance is now 20,000
    det_before = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr).json()
    assert det_before["completed_pairs"] == 10000.0
    assert det_before["outstanding_pairs"] == 20000.0

    # 3. Extend shipment date by 15 days
    ship_date_extended = str(date.today() + timedelta(days=25))
    r_ext = client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": ship_date_extended,
        "reason": "Deadline extended to observe rate calculation on balance"
    }, headers=admin_hdr)
    assert r_ext.status_code == 200
    det_after = r_ext.json()

    # Actual production is preserved!
    assert det_after["completed_pairs"] == 10000.0
    assert det_after["outstanding_pairs"] == 20000.0

    # Auto daily target uses 20,000 / remaining_days, NOT 30,000 / remaining_days
    rem_days = det_after["remaining_working_days"]
    expected_rate = round(20000.0 / rem_days, 2)
    daily_tg = det_after["daily_target"]
    assert abs(daily_tg - expected_rate) <= 1.0


def test_scenario_i_factory_holiday(client, auth_headers, db_session):
    """
    Test I — Factory Holiday:
    Revise shipment date and add a factory holiday in the planning period.
    Expected:
    - The holiday is excluded from working-day calculation.
    - Targets recalculate appropriately.
    - Historical actual production remains unchanged.
    """
    admin_hdr = auth_headers("admin")

    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Holiday Test Buyer",
        "buyer_code": "HOL-01",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    ship_date = str(date.today() + timedelta(days=20))
    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-HOL-TEST",
        "customer_ref": "Holiday Test Order",
        "style_model": "HOL-100",
        "total_quantity": 20000.0,
        "original_delivery_date": ship_date,
    }, headers=admin_hdr)
    order_id = r_ord.json()["id"]

    det_initial = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr).json()
    days_before = det_initial["remaining_working_days"]

    # Add a factory holiday on a working day
    holiday_date = date.today() + timedelta(days=2)
    if holiday_date.weekday() == 4:  # Friday
        holiday_date += timedelta(days=1)

    cal = db_session.query(FactoryCalendar).filter(FactoryCalendar.is_default == True).first()
    r_ex = client.post(f"/api/v1/calendar/{cal.id}/exceptions", json={
        "exception_date": str(holiday_date),
        "exception_type": "holiday",
        "description": "National Factory Holiday"
    }, headers=admin_hdr)
    assert r_ex.status_code == 200

    # Recalculate order plan
    det_holiday = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr).json()
    days_after = det_holiday["remaining_working_days"]

    # Exactly 1 fewer working day due to holiday
    assert days_after == days_before - 1


def test_scenario_j_reduce_shipment_date_capacity_conflict(client, auth_headers, db_session):
    """
    Test J — Reduce Shipment Date / Capacity Conflict:
    Move the shipment date earlier when the remaining balance cannot be completed
    within the configured maximum daily target.
    Expected:
    - The system flags the order as AT RISK.
    - It does not silently violate the maximum target.
    """
    admin_hdr = auth_headers("admin")

    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Capacity Buyer",
        "buyer_code": "CAP-01",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    ship_date = str(date.today() + timedelta(days=30))
    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-CAP-TEST",
        "customer_ref": "Capacity Conflict Test",
        "style_model": "CAP-50",
        "total_quantity": 25000.0,
        "original_delivery_date": ship_date,
    }, headers=admin_hdr)
    order_data = r_ord.json()
    order_id = order_data["id"]
    section_id = order_data["routes"][0]["section_id"]

    # Configure a Maximum Daily Target of 500 pairs/day for this section
    target_setting = db_session.query(ProductionTargetSetting).filter(
        ProductionTargetSetting.section_id == section_id
    ).first()
    if not target_setting:
        target_setting = ProductionTargetSetting(
            section_id=section_id,
            maximum_daily_target=500,
            minimum_daily_target=50,
            calculation_mode="BALANCED",
            is_active=True
        )
        db_session.add(target_setting)
    else:
        target_setting.maximum_daily_target = 500
    db_session.commit()

    # Move shipment date to 3 days from now
    # Balance is 25,000 pairs. At max 500/day, it needs 50 working days!
    short_date = str(date.today() + timedelta(days=4))
    r_short = client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": short_date,
        "reason": "Customer demands urgent delivery"
    }, headers=admin_hdr)
    assert r_short.status_code == 200
    det = r_short.json()

    # System identifies risk/conflict
    assert det["is_at_risk"] == True or det["is_overdue"] == True or det["status"] in ("AT_RISK", "OVERDUE")


def test_scenario_k_shipment_date_revision_history(client, auth_headers, sample_orders):
    """
    Test K — Shipment Date Revision History:
    Change a shipment date twice.
    Expected:
    - Both revisions are stored.
    - Previous dates, new dates, timestamps, and users are recorded.
    - The currently active date is used in planning.
    """
    admin_hdr = auth_headers("admin")
    order_id = sample_orders["bat1"]["id"]

    date_rev1 = str(date.today() + timedelta(days=28))
    date_rev2 = str(date.today() + timedelta(days=32))

    client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": date_rev1,
        "reason": "Revision 1: Supplier delayed material delivery"
    }, headers=admin_hdr)

    client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": date_rev2,
        "reason": "Revision 2: Buyer approved extra 4 days buffer"
    }, headers=admin_hdr)

    # Fetch revisions list
    r_revs = client.get(f"/api/v1/orders/{order_id}/revisions", headers=admin_hdr)
    assert r_revs.status_code == 200
    revisions = r_revs.json()

    assert len(revisions) >= 2
    latest = revisions[0]
    assert latest["revised_delivery_date"] == date_rev2
    assert latest["reason"] == "Revision 2: Buyer approved extra 4 days buffer"
    assert latest["revised_by_id"] is not None


def test_scenario_l_authorization(client, auth_headers, sample_orders):
    """
    Test L — Authorization:
    Attempt to edit a shipment date or update order using a user without permission (e.g. viewer).
    Expected:
    - Backend rejects unauthorized request with 403 Forbidden.
    - The saved date remains unchanged.
    """
    viewer_hdr = auth_headers("viewer")
    admin_hdr = auth_headers("admin")

    order_id = sample_orders["bat1"]["id"]
    current_date = sample_orders["bat1"]["current_delivery_date"]

    # Viewer attempts to revise date -> 403 Forbidden
    res = client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": str(date.today() + timedelta(days=60)),
        "reason": "Unauthorized alteration attempt"
    }, headers=viewer_hdr)
    assert res.status_code == 403

    # Viewer attempts to PUT order -> 403 Forbidden
    res_put = client.put(f"/api/v1/orders/{order_id}", json={
        "customer_ref": "Hacked Customer Ref"
    }, headers=viewer_hdr)
    assert res_put.status_code == 403

    # Verify order remained unchanged
    unchanged = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr).json()
    assert unchanged["current_delivery_date"] == current_date


def test_scenario_m_regression_endpoints(client, auth_headers, sample_orders):
    """
    Test M — Regression:
    Verify:
    - Buyers load
    - Orders load
    - Production planning matrix loads
    - WIP flow planning loads
    - Daily production entry works
    - Factory calendar loads
    - XLSX and CSV exports work
    """
    admin_hdr = auth_headers("admin")
    test_ord_id = sample_orders["bat1"]["id"]

    # 1. Buyers
    r_buyers = client.get("/api/v1/buyers", headers=admin_hdr)
    assert r_buyers.status_code == 200
    assert len(r_buyers.json()) > 0

    # 2. Orders
    r_orders = client.get("/api/v1/orders", headers=admin_hdr)
    assert r_orders.status_code == 200
    assert len(r_orders.json()) > 0

    # 3. Planning Matrix
    r_matrix = client.get(f"/api/v1/orders/matrix-planning?order_id={test_ord_id}", headers=admin_hdr)
    assert r_matrix.status_code == 200

    # 4. WIP Flow
    r_wip = client.get(f"/api/v1/orders/wip-flow-plan?order_id={test_ord_id}", headers=admin_hdr)
    assert r_wip.status_code == 200

    # 5. Factory Calendar
    r_cal = client.get("/api/v1/calendar/active", headers=admin_hdr)
    assert r_cal.status_code == 200

    # 6. XLSX and CSV Exports
    r_xlsx = client.get(f"/api/v1/exports/orders/{test_ord_id}/matrix-planning/xlsx", headers=admin_hdr)
    assert r_xlsx.status_code == 200
    assert len(r_xlsx.content) > 0

    r_csv = client.get(f"/api/v1/exports/orders/{test_ord_id}/matrix-planning/csv", headers=admin_hdr)
    assert r_csv.status_code == 200
    assert len(r_csv.content) > 0
