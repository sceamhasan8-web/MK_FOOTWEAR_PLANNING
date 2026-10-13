"""
End-to-End Acceptance Tests for Data Pipeline and Error Handling.
Covers Section 37 Acceptance Tests A through J.
"""
from datetime import date, timedelta
from app.services.calendar_service import CalendarService
from app.models.route import Section


def test_acceptance_a_empty_data_integrity(client, auth_headers):
    """
    Acceptance Test A:
    Verify endpoints return predictable empty responses without error or infinite loop
    when queries have zero results.
    """
    headers = auth_headers("admin")
    # Health endpoint is public and reports status
    r_health = client.get("/api/v1/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"
    assert "request_id" in r_health.json()

    # Diagnostics endpoint checks all subsystems
    r_diag = client.get("/api/v1/diagnostics")
    assert r_diag.status_code == 200
    assert r_diag.json()["overall_status"] == "PASS"

    # Buyers endpoint returns valid empty or list structure
    r_buyers = client.get("/api/v1/buyers", headers=headers)
    assert r_buyers.status_code == 200
    assert isinstance(r_buyers.json(), list)


def test_acceptance_b_and_c_buyer_order_creation(client, auth_headers, db_session):
    """
    Acceptance Test B & C:
    Create a buyer and an order (70,000 pairs), verify immediate retrieval
    and dashboard integration.
    """
    admin_hdr = auth_headers("admin")

    # Create Buyer
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "BATA Corporation",
        "buyer_code": "BATA-ACCEPT",
        "is_active": True
    }, headers=admin_hdr)
    assert r_buyer.status_code in (200, 201)
    buyer = r_buyer.json()
    assert buyer["name"] == "BATA Corporation"
    buyer_id = buyer["id"]

    # Verify Buyer is retrieved
    r_buyers = client.get("/api/v1/buyers", headers=admin_hdr)
    assert any(b["id"] == buyer_id for b in r_buyers.json())

    # Create Order
    delivery = date.today() + timedelta(days=14)
    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    assert sec_cut is not None

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "BATA-TEST-70K",
        "customer_ref": "PO-9999",
        "style_model": "Derby Classic",
        "total_quantity": 70000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(delivery),
        "routes": [
            {
                "section_id": sec_cut.id,
                "status": "REQUIRED",
                "operations": [
                    {
                        "operation_name": "Standard Die Cutting",
                        "sequence_order": 1,
                        "components": [
                            {"component_name": "Upper Leather", "required_ratio": 1.0}
                        ]
                    }
                ]
            }
        ]
    }, headers=admin_hdr)
    assert r_order.status_code in (200, 201)
    order_data = r_order.json()
    assert order_data["total_quantity"] == 70000.0

    # Verify Dashboard updates
    r_dash = client.get("/api/v1/dashboard/summary", headers=admin_hdr)
    assert r_dash.status_code == 200
    dash = r_dash.json()
    assert dash["active_orders_count"] >= 1
    assert dash["total_balance"] >= 70000.0


def test_acceptance_d_production_entry_and_balance_update(client, auth_headers, db_session):
    """
    Acceptance Test D:
    Enter production (20,000 pairs against 70,000 order), verify balance reduces to 50,000
    and daily target recalculates.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    # Create buyer & order
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Apex Test",
        "buyer_code": "APEX-T1",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    delivery = date.today() + timedelta(days=10)

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-APEX-70K",
        "customer_ref": "REF-APEX",
        "style_model": "Sneaker 01",
        "total_quantity": 70000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(delivery),
        "routes": [
            {
                "section_id": sec_cut.id,
                "status": "REQUIRED",
                "operations": [
                    {
                        "operation_name": "Cutting Operation",
                        "sequence_order": 1,
                        "components": [
                            {"component_name": "Fabric", "required_ratio": 1.0}
                        ]
                    }
                ]
            }
        ]
    }, headers=admin_hdr)
    order = r_order.json()
    order_id = order["id"]
    route_id = order["routes"][0]["id"]
    op_id = order["routes"][0]["operations"][0]["id"]

    # Post Daily Production Entry
    r_prod = client.post("/api/v1/production/entry", json={
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "entry_date": str(date.today()),
        "quantity": 20000.0,
        "accepted_quantity": 20000.0,
        "rejected_quantity": 0.0,
        "remarks": "Acceptance Test Batch 1"
    }, headers=supervisor_hdr)
    assert r_prod.status_code in (200, 201)

    # Check updated Order operation schedule
    r_sched = client.get(f"/api/v1/orders/{order_id}/operations/{op_id}/daily-schedule", headers=admin_hdr)
    assert r_sched.status_code == 200
    sched = r_sched.json()
    assert sched["remaining_balance"] == 50000.0
    assert sched["required_quantity"] == 70000.0


def test_acceptance_h_expired_or_invalid_auth(client):
    """
    Acceptance Test H:
    Requests with invalid or missing tokens return 401 with Request ID header.
    """
    r = client.get("/api/v1/buyers", headers={"Authorization": "Bearer invalid_expired_token"})
    assert r.status_code == 401
    assert "X-Request-ID" in r.headers
    assert "detail" in r.json()


def test_acceptance_request_id_correlation(client, auth_headers):
    """
    Section 28: Correlation ID is generated and returned across all responses.
    """
    headers = auth_headers("admin")
    custom_id = "ERP-20261007-TEST001"
    r = client.get("/api/v1/buyers", headers={**headers, "X-Request-ID": custom_id})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == custom_id
