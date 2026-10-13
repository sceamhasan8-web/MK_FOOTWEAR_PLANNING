from datetime import date, timedelta


def test_scenario_g_production_correction_and_reversal(client, auth_headers):
    """
    Scenario G: Production correction
    Edit or reverse a production entry.
    Verify that the entry history is retained and all affected balances and future plans are recalculated correctly.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    # 1. Create Buyer and Order
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Audit Test Buyer",
        "buyer_code": "AUD-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-AUD-REV",
        "customer_ref": "REF-AUD-01",
        "style_model": "Audit Model",
        "total_quantity": 5000.0,
        "original_delivery_date": str(date.today() + timedelta(days=10)),
    }, headers=admin_hdr)
    order_data = r_order.json()
    order_id = order_data["id"]
    route_id = order_data["routes"][0]["id"]
    op_id = order_data["routes"][0]["operations"][0]["id"]

    # 2. Record initial production entry: 1,500 pairs
    r_entry = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": 1500.0,
        "accepted_quantity": 1500.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "remarks": "Initial entry"
    }, headers=supervisor_hdr)
    assert r_entry.status_code == 200
    entry_id = r_entry.json()["id"]

    # Balance after entry should be 3,500
    chk1 = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr).json()
    assert chk1["routes"][0]["operations"][0]["balance_quantity"] == 3500.0

    # 3. Correct entry: Supervisor made a typo, it was actually 1,200 pairs
    r_corr = client.put(f"/api/v1/production/entries/{entry_id}/correct", json={
        "new_accepted_quantity": 1200.0,
        "new_rejected_quantity": 50.0,
        "reason": "Correction of operator log typo."
    }, headers=supervisor_hdr)
    assert r_corr.status_code == 200
    corr_entry = r_corr.json()

    # Verify correction audit trail
    assert len(corr_entry["corrections"]) == 1
    assert corr_entry["corrections"][0]["original_accepted_qty"] == 1500.0
    assert corr_entry["corrections"][0]["new_accepted_qty"] == 1200.0
    assert corr_entry["corrections"][0]["reason"] == "Correction of operator log typo."

    # Balance after correction should be 5000 - 1200 = 3,800
    chk2 = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr).json()
    assert chk2["routes"][0]["operations"][0]["balance_quantity"] == 3800.0

    # 4. Reverse the entry completely
    r_rev = client.post(f"/api/v1/production/entries/{entry_id}/reverse", json={
        "reason": "Production batch failed QA test; entry reversed."
    }, headers=admin_hdr)
    assert r_rev.status_code == 200
    rev_entry = r_rev.json()
    assert rev_entry["is_reversed"] is True

    # Balance after reversal should be fully restored to 5,000
    chk3 = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr).json()
    assert chk3["routes"][0]["operations"][0]["balance_quantity"] == 5000.0
    assert chk3["routes"][0]["operations"][0]["completed_quantity"] == 0.0

    # Verify entry is still retained in history (not silently deleted!)
    r_list = client.get(f"/api/v1/production/entries?order_id={order_id}&include_reversed=true", headers=admin_hdr)
    assert r_list.status_code == 200
    entries_list = r_list.json()
    assert len(entries_list) == 1
    assert entries_list[0]["id"] == entry_id
    assert entries_list[0]["is_reversed"] is True
