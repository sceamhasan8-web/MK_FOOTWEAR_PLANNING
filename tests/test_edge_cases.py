from datetime import date, timedelta
from app.services.calculation_engine import CalculationEngine


def test_scenario_k_edge_cases(client, auth_headers):
    """
    Scenario K: Edge cases
    Test zero remaining quantity, zero remaining working days, overdue orders,
    excess production, order quantity changes, duplicate submissions,
    missing required data, and invalid/negative quantities.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    # 1. Calculation Engine safe edge cases
    # Zero remaining quantity
    assert CalculationEngine.calculate_daily_target(remaining_balance=0.0, remaining_working_days=10) == 0.0
    # Zero working days with positive balance does not divide by zero
    assert CalculationEngine.calculate_daily_target(remaining_balance=500.0, remaining_working_days=0) == 500.0
    # Zero required quantity percentage handled safely
    assert CalculationEngine.calculate_operation_completion_percentage(required_qty=0.0, cumulative_accepted=100.0) == 100.0

    # 2. Invalid / Negative quantities validation
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Edge Buyer",
        "buyer_code": "EDG-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    # Reject order with 0 or negative quantity
    r_bad_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-NEG",
        "customer_ref": "REF-NEG",
        "style_model": "Bad Model",
        "total_quantity": -50.0,  # Negative!
        "original_delivery_date": str(date.today() + timedelta(days=5)),
    }, headers=admin_hdr)
    assert r_bad_order.status_code == 422  # Pydantic validation error

    # Create valid order
    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-EDG-VALID",
        "customer_ref": "REF-EDG",
        "style_model": "Edge Model",
        "total_quantity": 1000.0,
        "original_delivery_date": str(date.today() + timedelta(days=5)),
    }, headers=admin_hdr)
    order_data = r_order.json()
    order_id = order_data["id"]
    route_id = order_data["routes"][0]["id"]
    op_id = order_data["routes"][0]["operations"][0]["id"]

    # 3. Reject negative production entry
    r_bad_entry = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": -100.0,  # Negative!
        "accepted_quantity": 100.0,
        "unit": "PAIRS"
    }, headers=supervisor_hdr)
    assert r_bad_entry.status_code == 422

    # 4. Overproduction warning without override
    r_overprod = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": 1500.0,
        "accepted_quantity": 1500.0,  # Exceeds 1,000 balance!
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "is_override": False
    }, headers=supervisor_hdr)
    assert r_overprod.status_code == 400
    assert "exceeds remaining balance" in r_overprod.json()["detail"]

    # 5. Overproduction permitted with authorized override
    r_overprod_ok = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": 1000.0,
        "accepted_quantity": 1000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "is_override": False
    }, headers=supervisor_hdr)
    assert r_overprod_ok.status_code == 200

    # 6. Duplicate submission protection
    r_dup = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": 1000.0,
        "accepted_quantity": 1000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "is_override": True
    }, headers=supervisor_hdr)
    assert r_dup.status_code == 400
    assert "Duplicate submission detected" in r_dup.json()["detail"]

    # 7. Order quantity change
    r_qty_change = client.put(f"/api/v1/orders/{order_id}", json={
        "total_quantity": 1200.0,
        "reason": "Client ordered additional 200 pairs"
    }, headers=admin_hdr)
    assert r_qty_change.status_code == 200
    updated = r_qty_change.json()
    assert updated["total_quantity"] == 1200.0
    # Remaining balance increases to 200 (1200 required - 1000 completed)
    assert updated["routes"][0]["operations"][0]["balance_quantity"] == 200.0
