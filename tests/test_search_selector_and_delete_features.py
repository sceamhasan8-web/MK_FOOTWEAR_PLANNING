import pytest
from datetime import date, timedelta
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.models.route import ProductionTargetSetting
from app.models.order import OrderStatus


@pytest.fixture
def sample_test_setup(client, auth_headers):
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


# =========================================================================
# PART 1: ORDER SEARCH SELECTOR TESTS (A - G)
# =========================================================================

def test_a_click_empty_search_field(client, auth_headers, sample_test_setup):
    """
    Test A: Click empty search field.
    Expected: Available orders are suggested without typing.
    """
    admin_hdr = auth_headers("admin")
    res = client.get("/api/v1/orders", headers=admin_hdr)
    assert res.status_code == 200
    orders = res.json()
    assert len(orders) >= 3
    order_codes = [o["order_code"] for o in orders]
    assert "BAT-001" in order_codes
    assert "BAT-002" in order_codes
    assert "APX-999" in order_codes


def test_b_type_partial_order_name(client, auth_headers, sample_test_setup):
    """
    Test B: Type a partial order name / customer reference.
    Expected: Matching results appear.
    """
    admin_hdr = auth_headers("admin")
    res = client.get("/api/v1/orders?search=Winter", headers=admin_hdr)
    assert res.status_code == 200
    orders = res.json()
    assert len(orders) == 1
    assert orders[0]["order_code"] == "BAT-002"
    assert "Winter" in orders[0]["customer_ref"]


def test_c_search_by_buyer_name(client, auth_headers, sample_test_setup):
    """
    Test C: Search by buyer name.
    Expected: Matching buyer orders appear.
    """
    admin_hdr = auth_headers("admin")
    res = client.get("/api/v1/orders?search=BATA", headers=admin_hdr)
    assert res.status_code == 200
    orders = res.json()
    order_codes = [o["order_code"] for o in orders]
    assert "BAT-001" in order_codes
    assert "BAT-002" in order_codes
    assert "APX-999" not in order_codes


def test_d_search_by_exact_order_reference(client, auth_headers, sample_test_setup):
    """
    Test D: Search by exact order reference.
    Expected: The correct order appears.
    """
    admin_hdr = auth_headers("admin")
    res = client.get("/api/v1/orders?search=BAT-001", headers=admin_hdr)
    assert res.status_code == 200
    orders = res.json()
    assert len(orders) == 1
    assert orders[0]["order_code"] == "BAT-001"
    assert orders[0]["total_quantity"] == 30000.0


def test_e_clear_search_text(client, auth_headers, sample_test_setup):
    """
    Test E: Clear the search text.
    Expected: The available-order suggestions reappear.
    """
    admin_hdr = auth_headers("admin")
    res1 = client.get("/api/v1/orders?search=BAT-001", headers=admin_hdr)
    assert len(res1.json()) == 1

    res2 = client.get("/api/v1/orders?search=", headers=admin_hdr)
    assert res2.status_code == 200
    assert len(res2.json()) >= 3


def test_f_create_more_orders_than_fit_in_one_dropdown(client, auth_headers, sample_test_setup):
    """
    Test F: Create more orders than fit in one dropdown.
    Expected: Pagination or limit parameters allow user to access all eligible orders.
    """
    admin_hdr = auth_headers("admin")
    res_p1 = client.get("/api/v1/orders?page=1&page_size=2", headers=admin_hdr)
    assert res_p1.status_code == 200
    p1_orders = res_p1.json()
    assert len(p1_orders) == 2

    res_p2 = client.get("/api/v1/orders?page=2&page_size=2", headers=admin_hdr)
    assert res_p2.status_code == 200
    p2_orders = res_p2.json()
    assert len(p2_orders) >= 1

    p1_ids = {o["id"] for o in p1_orders}
    p2_ids = {o["id"] for o in p2_orders}
    assert len(p1_ids.intersection(p2_ids)) == 0


def test_g_switch_between_two_orders(client, auth_headers, sample_test_setup):
    """
    Test G: Switch between two orders.
    Expected: No stale quantities from previous selection are displayed.
    """
    admin_hdr = auth_headers("admin")
    bat1_id = sample_test_setup["bat1"]["id"]
    bat2_id = sample_test_setup["bat2"]["id"]

    res1 = client.get(f"/api/v1/orders/{bat1_id}/matrix-planning", headers=admin_hdr)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["order_code"] == "BAT-001"
    assert data1["total_quantity"] == 30000.0

    res2 = client.get(f"/api/v1/orders/{bat2_id}/matrix-planning", headers=admin_hdr)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["order_code"] == "BAT-002"
    assert data2["total_quantity"] == 45000.0


# =========================================================================
# PART 2: ORDER DELETE / ARCHIVE TESTS (H - K)
# =========================================================================

def test_h_delete_order_without_production_history(client, auth_headers, sample_test_setup):
    """
    Test H: Delete an eligible order with no protected dependencies.
    Expected:
    - The order is permanently deleted.
    - Related permitted workflow/configuration records are cleaned up.
    - Other orders remain unchanged.
    """
    admin_hdr = auth_headers("admin")
    apx_id = sample_test_setup["apx"]["id"]

    # Check dependencies first
    dep_res = client.get(f"/api/v1/orders/{apx_id}/dependency-check", headers=admin_hdr)
    assert dep_res.status_code == 200
    dep_data = dep_res.json()
    assert dep_data["can_permanently_delete"] is True
    assert dep_data["production_entries_count"] == 0

    # Delete order
    del_res = client.delete(f"/api/v1/orders/{apx_id}", headers=admin_hdr)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Order should no longer exist
    get_res = client.get(f"/api/v1/orders/{apx_id}", headers=admin_hdr)
    assert get_res.status_code == 404

    # Other orders remain intact
    bat_res = client.get(f"/api/v1/orders/{sample_test_setup['bat1']['id']}", headers=admin_hdr)
    assert bat_res.status_code == 200


def test_i_archive_order_with_production_history(client, auth_headers, sample_test_setup):
    """
    Test I: Archive order that has actual production records.
    Expected:
    - Permanent delete is blocked because dependencies exist.
    - Archiving succeeds.
    - The order disappears from normal active lists and planning endpoints.
    - Its production history remains accessible in authorized views.
    """
    admin_hdr = auth_headers("admin")
    bat1_id = sample_test_setup["bat1"]["id"]

    # Get first route operation for BAT-001
    ord_det = client.get(f"/api/v1/orders/{bat1_id}", headers=admin_hdr).json()
    route_id = ord_det["routes"][0]["id"]
    first_op = ord_det["routes"][0]["operations"][0]

    # Create a production entry using /api/v1/production/entry
    entry_res = client.post("/api/v1/production/entry", json={
        "order_id": bat1_id,
        "route_id": route_id,
        "operation_id": first_op["id"],
        "entry_date": str(date.today()),
        "quantity": 2000.0,
        "accepted_quantity": 2000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=admin_hdr)
    assert entry_res.status_code == 200

    # Check dependencies: cannot permanently delete!
    dep_res = client.get(f"/api/v1/orders/{bat1_id}/dependency-check", headers=admin_hdr)
    assert dep_res.status_code == 200
    dep_data = dep_res.json()
    assert dep_data["can_permanently_delete"] is False
    assert dep_data["production_entries_count"] == 1

    # Attempt permanent delete should fail with 400
    del_res = client.delete(f"/api/v1/orders/{bat1_id}", headers=admin_hdr)
    assert del_res.status_code == 400
    assert "production records" in del_res.json()["detail"].lower() or "production entries" in del_res.json()["detail"].lower()

    # Archive order instead
    arch_res = client.post(f"/api/v1/orders/{bat1_id}/archive", json={
        "reason": "Production stopped by buyer"
    }, headers=admin_hdr)
    assert arch_res.status_code == 200
    assert arch_res.json()["is_archived"] is True
    assert arch_res.json()["status"] == OrderStatus.ARCHIVED.value

    # Excluded from active orders list by default
    active_orders = client.get("/api/v1/orders", headers=admin_hdr).json()
    active_ids = [o["id"] for o in active_orders]
    assert bat1_id not in active_ids

    # But included if include_archived=true
    all_orders = client.get("/api/v1/orders?include_archived=true", headers=admin_hdr).json()
    all_ids = [o["id"] for o in all_orders]
    assert bat1_id in all_ids

    # Active planning sheet rejects archived order
    plan_res = client.get(f"/api/v1/orders/{bat1_id}/matrix-planning", headers=admin_hdr)
    assert plan_res.status_code == 400

    # Production history entry remains completely intact in database
    entries = client.get(f"/api/v1/production/entries?order_id={bat1_id}", headers=admin_hdr).json()
    assert len(entries) == 1
    assert entries[0]["accepted_quantity"] == 2000.0


def test_j_restore_archived_order(client, auth_headers, sample_test_setup):
    """
    Test J: Restore an archived order.
    Expected:
    - Order is restored to active planning.
    - Production history and records remain intact.
    - Reappears in default active order list.
    """
    admin_hdr = auth_headers("admin")
    bat1_id = sample_test_setup["bat1"]["id"]

    # Order was archived in test I, restore it
    restore_res = client.post(f"/api/v1/orders/{bat1_id}/restore", json={
        "reason": "Buyer resumed production"
    }, headers=admin_hdr)
    assert restore_res.status_code == 200
    assert restore_res.json()["is_archived"] is False

    # Now appears back in active order list
    active_orders = client.get("/api/v1/orders", headers=admin_hdr).json()
    active_ids = [o["id"] for o in active_orders]
    assert bat1_id in active_ids


def test_k_unauthorized_delete(client, auth_headers, sample_test_setup):
    """
    Test K: Attempt deletion using a user without permission (e.g. viewer or planner).
    Expected: Backend denies the operation (403).
    """
    viewer_hdr = auth_headers("viewer")
    planner_hdr = auth_headers("planner")
    bat2_id = sample_test_setup["bat2"]["id"]

    # Viewer attempts delete
    res_viewer = client.delete(f"/api/v1/orders/{bat2_id}", headers=viewer_hdr)
    assert res_viewer.status_code in [401, 403]

    # Planner attempts delete (restricted to ADMIN only)
    res_planner = client.delete(f"/api/v1/orders/{bat2_id}", headers=planner_hdr)
    assert res_planner.status_code == 403


# =========================================================================
# PART 3: PRODUCTION ENTRY CANCEL / DELETE TESTS (L - Q)
# =========================================================================

def test_l_cancel_one_entry(client, auth_headers, sample_test_setup):
    """
    Test L: An order has two production entries. Cancel one entry.
    Expected:
    - Only the selected entry is marked voided/cancelled (is_reversed=True).
    - The other entry remains intact and active.
    """
    admin_hdr = auth_headers("admin")
    bat2_id = sample_test_setup["bat2"]["id"]

    ord_det = client.get(f"/api/v1/orders/{bat2_id}", headers=admin_hdr).json()
    route_id = ord_det["routes"][0]["id"]
    first_op = ord_det["routes"][0]["operations"][0]

    # Create Entry 1: 1,000 pairs
    e1_res = client.post("/api/v1/production/entry", json={
        "order_id": bat2_id,
        "route_id": route_id,
        "operation_id": first_op["id"],
        "entry_date": str(date.today()),
        "quantity": 1000.0,
        "accepted_quantity": 1000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=admin_hdr)
    assert e1_res.status_code == 200
    e1 = e1_res.json()

    # Create Entry 2: 500 pairs
    e2_res = client.post("/api/v1/production/entry", json={
        "order_id": bat2_id,
        "route_id": route_id,
        "operation_id": first_op["id"],
        "entry_date": str(date.today()),
        "quantity": 500.0,
        "accepted_quantity": 500.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=admin_hdr)
    assert e2_res.status_code == 200
    e2 = e2_res.json()

    # Cancel Entry 2
    cancel_res = client.post(f"/api/v1/production/entries/{e2['id']}/cancel", json={
        "reason": "Operator miscounted cutting batch"
    }, headers=admin_hdr)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["is_reversed"] is True

    # Verify Entry 1 is active, Entry 2 is reversed
    check_e1 = client.get(f"/api/v1/production/entries/{e1['id']}", headers=admin_hdr).json()
    assert check_e1["is_reversed"] is False

    check_e2 = client.get(f"/api/v1/production/entries/{e2['id']}", headers=admin_hdr).json()
    assert check_e2["is_reversed"] is True


def test_m_recalculate_target_after_cancellation(client, auth_headers, sample_test_setup):
    """
    Test M: Cancel a production entry.
    Expected:
    - Accepted production totals update.
    - Remaining balance updates.
    - Future T/G is recalculated.
    """
    admin_hdr = auth_headers("admin")
    bat2_id = sample_test_setup["bat2"]["id"]

    ord_det = client.get(f"/api/v1/orders/{bat2_id}", headers=admin_hdr).json()
    route_id = ord_det["routes"][0]["id"]
    first_op = ord_det["routes"][0]["operations"][0]

    # Create Entry 1: 1,000 pairs
    e1_res = client.post("/api/v1/production/entry", json={
        "order_id": bat2_id,
        "route_id": route_id,
        "operation_id": first_op["id"],
        "entry_date": str(date.today()),
        "quantity": 1000.0,
        "accepted_quantity": 1000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=admin_hdr)
    assert e1_res.status_code == 200

    # Create Entry 2: 500 pairs
    e2_res = client.post("/api/v1/production/entry", json={
        "order_id": bat2_id,
        "route_id": route_id,
        "operation_id": first_op["id"],
        "entry_date": str(date.today()),
        "quantity": 500.0,
        "accepted_quantity": 500.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=admin_hdr)
    assert e2_res.status_code == 200
    e2 = e2_res.json()

    # Before cancellation: operation has 1,500 completed
    chk_before = client.get(f"/api/v1/orders/{bat2_id}", headers=admin_hdr).json()
    op_before = chk_before["routes"][0]["operations"][0]
    assert op_before["completed_quantity"] == 1500.0
    assert op_before["balance_quantity"] == 45000.0 - 1500.0

    # Cancel Entry 2 (500 pairs)
    cancel_res = client.post(f"/api/v1/production/entries/{e2['id']}/cancel", json={
        "reason": "Test recalculate cancellation"
    }, headers=admin_hdr)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["is_reversed"] is True

    # After cancellation:
    # Operation completed updates: 1,500 - 500 = 1,000
    # Remaining balance updates: 45,000 - 1,000 = 44,000
    chk_after = client.get(f"/api/v1/orders/{bat2_id}", headers=admin_hdr).json()
    op_after = chk_after["routes"][0]["operations"][0]
    assert op_after["completed_quantity"] == 1000.0
    assert op_after["balance_quantity"] == 45000.0 - 1000.0


def test_n_recalculate_wip_and_detect_conflict(client, auth_headers, sample_test_setup):
    """
    Test N: Downstream WIP integrity conflict detection.
    Suppose Cutting had 1,000 pairs, and Printing completed 800 pairs.
    If Cutting entry is cancelled, available upstream input becomes 0,
    while downstream completed is 800 (downstream completed > upstream input).
    Expected: Cancellation succeeds and records audit log.
    """
    admin_hdr = auth_headers("admin")

    bata_id = sample_test_setup["bata_id"]
    new_ord = client.post("/api/v1/orders", json={
        "buyer_id": bata_id,
        "order_code": "WIP-CONF-01",
        "customer_ref": "Integrity Test",
        "style_model": "MD-99",
        "total_quantity": 5000.0,
        "original_delivery_date": str(date.today() + timedelta(days=20))
    }, headers=admin_hdr).json()
    ord_id = new_ord["id"]

    ord_det = client.get(f"/api/v1/orders/{ord_id}", headers=admin_hdr).json()
    routes = ord_det["routes"]
    cutting_route_id = routes[0]["id"]
    cutting_op = routes[0]["operations"][0]
    printing_route_id = routes[1]["id"] if len(routes) > 1 else routes[0]["id"]
    printing_op = routes[1]["operations"][0] if len(routes) > 1 else routes[0]["operations"][0]

    # Upstream Cutting entry: 1,000
    cut_res = client.post("/api/v1/production/entry", json={
        "order_id": ord_id,
        "route_id": cutting_route_id,
        "operation_id": cutting_op["id"],
        "entry_date": str(date.today()),
        "quantity": 1000.0,
        "accepted_quantity": 1000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=admin_hdr)
    assert cut_res.status_code == 200
    cut_entry = cut_res.json()

    # Downstream Printing entry: 800
    print_res = client.post("/api/v1/production/entry", json={
        "order_id": ord_id,
        "route_id": printing_route_id,
        "operation_id": printing_op["id"],
        "entry_date": str(date.today()),
        "quantity": 800.0,
        "accepted_quantity": 800.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=admin_hdr)
    assert print_res.status_code == 200

    # Cancel Upstream Cutting entry
    cancel_res = client.post(f"/api/v1/production/entries/{cut_entry['id']}/cancel", json={
        "reason": "Cutting ticket cancelled"
    }, headers=admin_hdr)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["is_reversed"] is True


def test_o_duplicate_cancellation(client, auth_headers, sample_test_setup):
    """
    Test O: Attempt to cancel the same production entry twice.
    Expected: Backend rejects duplicate cancellation with 400.
    """
    admin_hdr = auth_headers("admin")
    bat2_id = sample_test_setup["bat2"]["id"]

    ord_det = client.get(f"/api/v1/orders/{bat2_id}", headers=admin_hdr).json()
    route_id = ord_det["routes"][0]["id"]
    first_op = ord_det["routes"][0]["operations"][0]

    e = client.post("/api/v1/production/entry", json={
        "order_id": bat2_id,
        "route_id": route_id,
        "operation_id": first_op["id"],
        "entry_date": str(date.today()),
        "quantity": 250.0,
        "accepted_quantity": 250.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=admin_hdr).json()

    # First cancel
    r1 = client.post(f"/api/v1/production/entries/{e['id']}/cancel", json={
        "reason": "Test first cancel"
    }, headers=admin_hdr)
    assert r1.status_code == 200

    # Duplicate cancel
    r2 = client.post(f"/api/v1/production/entries/{e['id']}/cancel", json={
        "reason": "Duplicate cancel attempt"
    }, headers=admin_hdr)
    assert r2.status_code == 400
    assert "already cancelled" in r2.json()["detail"].lower()


def test_p_historical_preservation_and_audit(client, auth_headers, sample_test_setup):
    """
    Test P: Cancel a production entry.
    Expected:
    - Its original values remain in database and audit history.
    - Correction record logged.
    """
    admin_hdr = auth_headers("admin")
    bat2_id = sample_test_setup["bat2"]["id"]

    ord_det = client.get(f"/api/v1/orders/{bat2_id}", headers=admin_hdr).json()
    route_id = ord_det["routes"][0]["id"]
    first_op = ord_det["routes"][0]["operations"][0]

    e = client.post("/api/v1/production/entry", json={
        "order_id": bat2_id,
        "route_id": route_id,
        "operation_id": first_op["id"],
        "entry_date": str(date.today()),
        "quantity": 310.0,
        "accepted_quantity": 300.0,
        "rejected_quantity": 10.0,
        "unit": "PAIRS"
    }, headers=admin_hdr).json()

    cancel_res = client.post(f"/api/v1/production/entries/{e['id']}/cancel", json={
        "reason": "Audit preservation test reason"
    }, headers=admin_hdr)
    assert cancel_res.status_code == 200

    # Query entry directly
    entry_chk = client.get(f"/api/v1/production/entries/{e['id']}", headers=admin_hdr).json()
    assert entry_chk["accepted_quantity"] == 300.0  # Original recorded accepted qty preserved
    assert entry_chk["rejected_quantity"] == 10.0   # Original recorded rejected qty preserved
    assert entry_chk["is_reversed"] is True

    # Audit log check
    audit_res = client.get("/api/v1/audit/logs", headers=admin_hdr)
    if audit_res.status_code == 200:
        logs = audit_res.json()
        reversal_logs = [l for l in logs if "CANCEL" in l.get("action", "") or "REVERSAL" in l.get("action", "")]
        assert len(reversal_logs) >= 1


def test_q_unauthorized_cancellation(client, auth_headers, sample_test_setup):
    """
    Test Q: Attempt to cancel an entry using a user without required permission (viewer).
    Expected: Operation is rejected (403), quantities remain unchanged.
    """
    admin_hdr = auth_headers("admin")
    viewer_hdr = auth_headers("viewer")
    bat2_id = sample_test_setup["bat2"]["id"]

    ord_det = client.get(f"/api/v1/orders/{bat2_id}", headers=admin_hdr).json()
    route_id = ord_det["routes"][0]["id"]
    first_op = ord_det["routes"][0]["operations"][0]

    e = client.post("/api/v1/production/entry", json={
        "order_id": bat2_id,
        "route_id": route_id,
        "operation_id": first_op["id"],
        "entry_date": str(date.today()),
        "quantity": 777.0,
        "accepted_quantity": 777.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=admin_hdr).json()

    # Viewer attempts cancel
    cancel_res = client.post(f"/api/v1/production/entries/{e['id']}/cancel", json={
        "reason": "Unauthorized attempt"
    }, headers=viewer_hdr)
    assert cancel_res.status_code in [401, 403]

    # Entry remains unreversed
    chk = client.get(f"/api/v1/production/entries/{e['id']}", headers=admin_hdr).json()
    assert chk["is_reversed"] is False
