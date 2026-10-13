import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus, OrderPriority
from app.models.user import User


@pytest.fixture
def base_setup(client: TestClient, db_session: Session, auth_headers):
    admin_hdr = auth_headers("admin")
    planner_hdr = auth_headers("planner")

    r_bata = client.post("/api/v1/buyers", json={
        "name": "BATA Footwear Group",
        "buyer_code": "BATA-01",
        "is_active": True
    }, headers=admin_hdr)
    bata_id = r_bata.json()["id"]

    r_apex = client.post("/api/v1/buyers", json={
        "name": "Apex Footwear Ltd",
        "buyer_code": "APEX-01",
        "is_active": True
    }, headers=admin_hdr)
    apex_id = r_apex.json()["id"]

    r1 = client.post("/api/v1/orders", json={
        "buyer_id": bata_id,
        "order_code": "BAT-001",
        "customer_ref": "BATA Summer",
        "style_model": "Summer Runner",
        "po_number": "PO-9910",
        "total_quantity": 30000.0,
        "original_delivery_date": str(date.today() + timedelta(days=25))
    }, headers=admin_hdr).json()

    r2 = client.post("/api/v1/orders", json={
        "buyer_id": bata_id,
        "order_code": "BAT-002",
        "customer_ref": "BATA Winter",
        "style_model": "Winter Warm ST-200",
        "po_number": "PO-9920",
        "total_quantity": 45000.0,
        "original_delivery_date": str(date.today() + timedelta(days=35))
    }, headers=admin_hdr).json()

    r3 = client.post("/api/v1/orders", json={
        "buyer_id": apex_id,
        "order_code": "APX-999",
        "customer_ref": "Apex Loafers",
        "style_model": "Formal Oxford",
        "po_number": "PO-1120",
        "total_quantity": 15000.0,
        "original_delivery_date": str(date.today() + timedelta(days=20))
    }, headers=admin_hdr).json()

    return {
        "admin_hdr": admin_hdr,
        "planner_hdr": planner_hdr,
        "bata_id": bata_id,
        "apex_id": apex_id,
        "bat1": r1,
        "bat2": r2,
        "apx": r3,
    }


def test_a_click_without_typing_shows_all_eligible_orders(client: TestClient, base_setup):
    """Test A: On focus/click without typing, empty search returns all active unarchived orders."""
    res = client.get("/api/v1/orders", headers=base_setup["planner_hdr"])
    assert res.status_code == 200
    orders = res.json()
    codes = [o["order_code"] for o in orders]
    assert "BAT-001" in codes
    assert "BAT-002" in codes
    assert "APX-999" in codes


def test_b_keyword_search_filters_matching_orders(client: TestClient, base_setup):
    """Test B: Keyword search filters by buyer, code, customer ref, style, or po number."""
    res = client.get("/api/v1/orders?search=BATA", headers=base_setup["planner_hdr"])
    assert res.status_code == 200
    bata_orders = res.json()
    bata_codes = [o["order_code"] for o in bata_orders]
    assert "BAT-001" in bata_codes
    assert "BAT-002" in bata_codes
    assert "APX-999" not in bata_codes


def test_c_partial_order_name_and_style_search(client: TestClient, base_setup):
    """Test C: Partial keyword matching against style model or description."""
    res = client.get("/api/v1/orders?search=Winter", headers=base_setup["planner_hdr"])
    assert res.status_code == 200
    orders = res.json()
    codes = [o["order_code"] for o in orders]
    assert "BAT-002" in codes
    assert "BAT-001" not in codes
    assert "APX-999" not in codes


def test_d_order_reference_and_po_search(client: TestClient, base_setup):
    """Test D: Unique order reference or purchase order number search."""
    res = client.get("/api/v1/orders?search=PO-1120", headers=base_setup["planner_hdr"])
    assert res.status_code == 200
    orders = res.json()
    assert len(orders) == 1
    assert orders[0]["order_code"] == "APX-999"


def test_e_clear_keyword_returns_all_orders(client: TestClient, base_setup):
    """Test E: Clearing the search query restores all eligible orders."""
    res = client.get("/api/v1/orders?search=", headers=base_setup["planner_hdr"])
    assert res.status_code == 200
    orders = res.json()
    codes = [o["order_code"] for o in orders]
    assert "BAT-001" in codes
    assert "BAT-002" in codes
    assert "APX-999" in codes


def test_f_select_order_loads_matrix_planning_data(client: TestClient, base_setup):
    """Test F: Selecting an order loads that specific order's matrix production planning sheet."""
    order_id = base_setup["bat1"]["id"]
    res = client.get(f"/api/v1/orders/matrix-planning?order_id={order_id}", headers=base_setup["planner_hdr"])
    assert res.status_code == 200
    data = res.json()
    assert data["order_id"] == order_id
    assert data["order_code"] == "BAT-001"
    assert data["total_quantity"] == 30000.0


def test_g_select_order_loads_wip_flow_plan(client: TestClient, base_setup):
    """Test G: Selecting an order loads its WIP Flow Plan without mixing data."""
    order_id = base_setup["apx"]["id"]
    res = client.get(f"/api/v1/orders/wip-flow-plan?order_id={order_id}", headers=base_setup["planner_hdr"])
    assert res.status_code == 200
    data = res.json()
    assert data["order_id"] == order_id
    assert data["order_code"] == "APX-999"
    assert data["total_quantity"] == 15000.0


def test_h_switching_orders_preserves_independent_plans(client: TestClient, base_setup):
    """Test H: Selecting Order A then Order B produces distinct planning datasets."""
    o1_id = base_setup["bat1"]["id"]
    o2_id = base_setup["bat2"]["id"]

    res1 = client.get(f"/api/v1/orders/matrix-planning?order_id={o1_id}", headers=base_setup["planner_hdr"])
    res2 = client.get(f"/api/v1/orders/matrix-planning?order_id={o2_id}", headers=base_setup["planner_hdr"])

    assert res1.status_code == 200 and res2.status_code == 200
    d1 = res1.json()
    d2 = res2.json()

    assert d1["order_id"] == o1_id and d1["total_quantity"] == 30000.0
    assert d2["order_id"] == o2_id and d2["total_quantity"] == 45000.0
    assert d1["order_id"] != d2["order_id"]


def test_j_many_orders_catalog_support(client: TestClient, db_session: Session, base_setup):
    """Test J: Support large order datasets (100+ orders) without premature pagination truncation."""
    admin_user = db_session.query(User).filter(User.username == "admin_test").first()
    orders_bulk = []
    for i in range(1, 105):
        orders_bulk.append(
            Order(
                order_code=f"BULK-{i:03d}",
                buyer_id=base_setup["bata_id"],
                customer_ref=f"Bulk Style {i}",
                style_model=f"Model-{i}",
                total_quantity=1000 + i,
                original_order_date=date.today(),
                production_start_date=date.today(),
                original_delivery_date=date.today() + timedelta(days=20),
                current_delivery_date=date.today() + timedelta(days=20),
                priority=OrderPriority.MEDIUM,
                status=OrderStatus.SCHEDULED,
                is_archived=False,
                created_by_id=admin_user.id
            )
        )
    db_session.add_all(orders_bulk)
    db_session.commit()

    # Query with limit=1000 to verify all 100+ orders are returned
    res = client.get("/api/v1/orders?limit=1000", headers=base_setup["planner_hdr"])
    assert res.status_code == 200
    all_orders = res.json()
    assert len(all_orders) >= 104
    bulk_codes = [o["order_code"] for o in all_orders if o["order_code"].startswith("BULK-")]
    assert len(bulk_codes) == 104
    assert "BULK-001" in bulk_codes
    assert "BULK-104" in bulk_codes


def test_m_invalid_order_id_error_handling(client: TestClient, base_setup):
    """Test M: Clear error response when requesting a non-existent order ID."""
    res = client.get("/api/v1/orders/matrix-planning?order_id=999999", headers=base_setup["planner_hdr"])
    assert res.status_code in (404, 400)
    data = res.json()
    assert "detail" in data or "error" in data


def test_n_empty_database_handling(client: TestClient, base_setup):
    """Test N: When filtered to an impossible buyer, returns empty list without crashing."""
    res = client.get("/api/v1/orders?buyer_id=88888", headers=base_setup["planner_hdr"])
    assert res.status_code == 200
    assert res.json() == []


def test_o_regression_system_integrity(client: TestClient, base_setup):
    """Test O: Regression test verifying Buyer Management, Order Management, Settings, and Production remain functional."""
    planner_hdr = base_setup["planner_hdr"]

    # Buyers
    b_res = client.get("/api/v1/buyers", headers=planner_hdr)
    assert b_res.status_code == 200

    # Orders
    o_res = client.get("/api/v1/orders?page_size=10", headers=planner_hdr)
    assert o_res.status_code == 200

    # Calendar
    cal_res = client.get("/api/v1/calendar/active", headers=planner_hdr)
    assert cal_res.status_code == 200

    # Production Entries
    prod_res = client.get("/api/v1/production/entries?page=1&page_size=10", headers=planner_hdr)
    assert prod_res.status_code == 200
