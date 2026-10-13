from datetime import date, timedelta
from app.models.route import Section


def test_scenario_h_component_tracking(client, auth_headers, db_session):
    """
    Scenario H: Component tracking
    Configure component conversion factors and test piece-to-pair-equivalent calculations.
    Verify that a section remains incomplete when any mandatory component is short.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Component Buyer",
        "buyer_code": "CMP-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    # Order of 1,000 pairs with 2 components:
    # Component A: Side part (2 pieces per pair -> 2,000 pieces required)
    # Component B: Back (2 pieces per pair -> 2,000 pieces required)
    order_payload = {
        "buyer_id": buyer_id,
        "order_code": "ORD-CMP-1K",
        "customer_ref": "REF-CMP-01",
        "style_model": "Two-Part Oxford",
        "total_quantity": 1000.0,
        "original_delivery_date": str(date.today() + timedelta(days=10)),
        "routes": [
            {
                "section_id": sec_cut.id,
                "status": "REQUIRED",
                "sequence_order": 1,
                "has_components": True,
                "operations": [
                    {
                        "operation_name": "Component Cutting",
                        "unit": "PAIRS",
                        "required_quantity": 1000.0,
                        "components": [
                            {
                                "component_name": "Side part",
                                "unit": "PIECES",
                                "pieces_per_pair": 2.0,
                                "required_total_qty": 2000.0,
                            },
                            {
                                "component_name": "Back",
                                "unit": "PIECES",
                                "pieces_per_pair": 2.0,
                                "required_total_qty": 2000.0,
                            }
                        ]
                    }
                ]
            }
        ]
    }

    r_order = client.post("/api/v1/orders", json=order_payload, headers=admin_hdr)
    assert r_order.status_code == 200
    order_data = r_order.json()
    order_id = order_data["id"]
    route_id = order_data["routes"][0]["id"]
    op = order_data["routes"][0]["operations"][0]
    comp_side = op["components"][0]
    comp_back = op["components"][1]

    # Produce 2,000 pieces of Side part (1,000 pair equivalents -> 100% done)
    r1 = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op["id"],
        "component_id": comp_side["id"],
        "quantity": 2000.0,
        "accepted_quantity": 2000.0,
        "rejected_quantity": 0.0,
        "unit": "PIECES",
        "remarks": "Side parts fully cut"
    }, headers=supervisor_hdr)
    assert r1.status_code == 200

    # Produce only 1,000 pieces of Back (500 pair equivalents -> 50% done, 1,000 pieces short)
    r2 = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op["id"],
        "component_id": comp_back["id"],
        "quantity": 1000.0,
        "accepted_quantity": 1000.0,
        "rejected_quantity": 0.0,
        "unit": "PIECES",
        "remarks": "Back parts half cut"
    }, headers=supervisor_hdr)
    assert r2.status_code == 200

    # Check order status
    chk = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr).json()
    chk_route = chk["routes"][0]
    chk_op = chk_route["operations"][0]

    chk_side = next(c for c in chk_op["components"] if c["component_name"] == "Side part")
    chk_back = next(c for c in chk_op["components"] if c["component_name"] == "Back")

    # Verify pair equivalent calculations
    assert chk_side["pair_equivalent_accepted"] == 1000.0
    assert chk_side["balance_total_qty"] == 0.0

    assert chk_back["pair_equivalent_accepted"] == 500.0
    assert chk_back["balance_total_qty"] == 1000.0

    # Because Back is short, operation and section MUST remain incomplete!
    assert chk_route["is_completed"] is False
    assert chk["status"] != "PRODUCTION_COMPLETE"

    # Now complete the remaining 1,000 pieces of Back
    r3 = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op["id"],
        "component_id": comp_back["id"],
        "quantity": 1000.0,
        "accepted_quantity": 1000.0,
        "unit": "PIECES",
        "remarks": "Remaining Back parts cut"
    }, headers=supervisor_hdr)
    assert r3.status_code == 200

    # Verify section now completes
    chk_final = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr).json()
    assert chk_final["routes"][0]["is_completed"] is True
