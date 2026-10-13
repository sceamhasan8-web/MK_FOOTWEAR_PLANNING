from datetime import date, timedelta
from app.models.route import Section


def test_scenario_b_optional_production_sections(client, auth_headers, db_session):
    """
    Scenario B: Optional production sections
    Configure an order with Lasting required and Dip not required.
    Complete the required Lasting operation.
    Verify that Dip does not block production completion and is not counted as outstanding required production.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    # 1. Create buyer
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Apex Test",
        "buyer_code": "APEX-OPT",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    sec_lasting = db_session.query(Section).filter(Section.name == "Lasting").first()
    sec_dip = db_session.query(Section).filter(Section.name == "Dip").first()

    # 2. Create order with only Lasting (REQUIRED) and Dip (NOT_REQUIRED)
    order_payload = {
        "buyer_id": buyer_id,
        "order_code": "ORD-OPT-TEST",
        "customer_ref": "REF-OPT-01",
        "style_model": "Slip-on EVA",
        "total_quantity": 5000.0,
        "original_delivery_date": str(date.today() + timedelta(days=10)),
        "routes": [
            {
                "section_id": sec_lasting.id,
                "status": "REQUIRED",
                "sequence_order": 1,
                "operations": [
                    {
                        "operation_name": "Direct Lasting",
                        "unit": "PAIRS",
                        "required_quantity": 5000.0,
                    }
                ]
            },
            {
                "section_id": sec_dip.id,
                "status": "NOT_REQUIRED",  # Not required!
                "sequence_order": 2,
                "operations": [
                    {
                        "operation_name": "Dip Coating",
                        "unit": "PAIRS",
                        "required_quantity": 5000.0,
                    }
                ]
            }
        ]
    }

    r_order = client.post("/api/v1/orders", json=order_payload, headers=admin_hdr)
    assert r_order.status_code == 200, r_order.text
    order_data = r_order.json()
    order_id = order_data["id"]

    # Verify Dip is marked NOT_REQUIRED
    routes = order_data["routes"]
    dip_route = next(r for r in routes if r["section_id"] == sec_dip.id)
    assert dip_route["status"] == "NOT_REQUIRED"
    assert dip_route["is_completed"] is True  # NOT_REQUIRED sections are treated as complete (not blocking)

    lasting_route = next(r for r in routes if r["section_id"] == sec_lasting.id)
    assert lasting_route["status"] == "REQUIRED"
    assert lasting_route["is_completed"] is False
    lasting_op = lasting_route["operations"][0]

    # 3. Complete the required Lasting operation
    entry_payload = {
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": lasting_route["id"],
        "operation_id": lasting_op["id"],
        "quantity": 5000.0,
        "accepted_quantity": 5000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }
    r_entry = client.post("/api/v1/production/entry", json=entry_payload, headers=supervisor_hdr)
    assert r_entry.status_code == 200, r_entry.text

    # 4. Check updated order details
    r_check = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr)
    assert r_check.status_code == 200
    updated_order = r_check.json()

    # Verify Lasting is completed
    updated_lasting = next(r for r in updated_order["routes"] if r["section_id"] == sec_lasting.id)
    assert updated_lasting["is_completed"] is True
    assert updated_lasting["operations"][0]["balance_quantity"] == 0.0

    # Verify Dip did not block completion, and total outstanding is 0
    assert updated_order["outstanding_pairs"] == 0.0
    assert updated_order["completed_pairs"] == 5000.0
    assert updated_order["status"] == "PRODUCTION_COMPLETE"
