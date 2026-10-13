from datetime import date, timedelta
from app.models.route import Section


def test_scenario_c_three_printing_operations(client, auth_headers, db_session):
    """
    Scenario C: Three Printing operations
    Create an order for 38,000 pairs. Set three required Printing operations to 38,000 each.
    Enter:
    - Operation 1: 38,000
    - Operation 2: 38,000
    - Operation 3: 25,000
    Expected result:
    - Operation 1 balance = 0
    - Operation 2 balance = 0
    - Operation 3 balance = 13,000
    - Printing section status = In Progress / not complete
    - The system must not report 101,000 completed pairs.
    After entering the remaining 13,000 for Operation 3, verify that Printing becomes complete.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    # 1. Create Buyer
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "BATA Print Client",
        "buyer_code": "BATA-PRT",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_prt = db_session.query(Section).filter(Section.name == "Printing").first()

    # 2. Create order with 38,000 pairs and 3 Printing operations
    order_payload = {
        "buyer_id": buyer_id,
        "order_code": "ORD-PRT-38K",
        "customer_ref": "REF-PRINT-38000",
        "style_model": "Graphic Print Sneaker",
        "total_quantity": 38000.0,
        "original_delivery_date": str(date.today() + timedelta(days=15)),
        "routes": [
            {
                "section_id": sec_prt.id,
                "status": "REQUIRED",
                "sequence_order": 1,
                "operations": [
                    {"operation_name": "Operation 1", "unit": "PAIRS", "required_quantity": 38000.0},
                    {"operation_name": "Operation 2", "unit": "PAIRS", "required_quantity": 38000.0},
                    {"operation_name": "Operation 3", "unit": "PAIRS", "required_quantity": 38000.0},
                ]
            }
        ]
    }
    r_order = client.post("/api/v1/orders", json=order_payload, headers=admin_hdr)
    assert r_order.status_code == 200
    order_data = r_order.json()
    order_id = order_data["id"]

    route = order_data["routes"][0]
    op1 = route["operations"][0]
    op2 = route["operations"][1]
    op3 = route["operations"][2]

    # 3. Enter quantities:
    # Op 1 = 38,000
    r1 = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today() - timedelta(days=2)),
        "order_id": order_id,
        "route_id": route["id"],
        "operation_id": op1["id"],
        "quantity": 38000.0,
        "accepted_quantity": 38000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "remarks": "Operation 1 complete"
    }, headers=supervisor_hdr)
    assert r1.status_code == 200

    # Op 2 = 38,000
    r2 = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today() - timedelta(days=1)),
        "order_id": order_id,
        "route_id": route["id"],
        "operation_id": op2["id"],
        "quantity": 38000.0,
        "accepted_quantity": 38000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "remarks": "Operation 2 complete"
    }, headers=supervisor_hdr)
    assert r2.status_code == 200

    # Op 3 = 25,000
    r3 = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route["id"],
        "operation_id": op3["id"],
        "quantity": 25000.0,
        "accepted_quantity": 25000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "remarks": "Operation 3 partial"
    }, headers=supervisor_hdr)
    assert r3.status_code == 200

    # 4. Check results
    r_check = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr)
    assert r_check.status_code == 200
    data = r_check.json()

    chk_route = data["routes"][0]
    chk_ops = chk_route["operations"]

    # Verify balances
    chk_op1 = next(o for o in chk_ops if o["operation_name"] == "Operation 1")
    chk_op2 = next(o for o in chk_ops if o["operation_name"] == "Operation 2")
    chk_op3 = next(o for o in chk_ops if o["operation_name"] == "Operation 3")

    assert chk_op1["balance_quantity"] == 0.0
    assert chk_op1["status"] == "COMPLETED"

    assert chk_op2["balance_quantity"] == 0.0
    assert chk_op2["status"] == "COMPLETED"

    assert chk_op3["balance_quantity"] == 13000.0
    assert chk_op3["completed_quantity"] == 25000.0
    assert chk_op3["status"] == "IN_PROGRESS"

    # Printing must NOT be marked complete
    assert chk_route["is_completed"] is False

    # The system must NOT report 101,000 completed pairs!
    # Instead, finished pairs reflects the limiting operation (25,000), not the sum!
    assert data["completed_pairs"] == 25000.0
    assert data["completed_pairs"] != 101000.0
    assert data["status"] != "PRODUCTION_COMPLETE"

    # 5. Now enter the remaining 13,000 for Operation 3
    r4 = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route["id"],
        "operation_id": op3["id"],
        "quantity": 13000.0,
        "accepted_quantity": 13000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "remarks": "Operation 3 balance completed"
    }, headers=supervisor_hdr)
    assert r4.status_code == 200

    # 6. Verify Printing becomes complete
    r_final = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr)
    final_data = r_final.json()
    final_route = final_data["routes"][0]

    assert final_route["is_completed"] is True
    assert final_data["completed_pairs"] == 38000.0
    assert final_data["outstanding_pairs"] == 0.0
    assert final_data["status"] == "PRODUCTION_COMPLETE"
