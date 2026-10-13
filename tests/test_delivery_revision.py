from datetime import date, timedelta


def test_scenario_f_delivery_date_revision(client, auth_headers):
    """
    Scenario F: Delivery-date revision
    Revise the delivery date of an existing order.
    Verify that future targets and delivery risk are recalculated,
    the original date is retained, and the revision is recorded.
    """
    admin_hdr = auth_headers("admin")

    # 1. Create Buyer and Order
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Delivery Test Buyer",
        "buyer_code": "DLV-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    orig_delivery = str(date.today() + timedelta(days=20))
    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-DLV-REV",
        "customer_ref": "REF-DLV-01",
        "style_model": "Delivery Model",
        "total_quantity": 10000.0,
        "original_delivery_date": orig_delivery,
    }, headers=admin_hdr)
    assert r_order.status_code == 200
    order_data = r_order.json()
    order_id = order_data["id"]

    initial_working_days = order_data["remaining_working_days"]
    initial_target = order_data["routes"][0]["operations"][0]["daily_target"]

    # 2. Revise delivery date to 7 days earlier (bringing deadline forward)
    new_delivery = str(date.today() + timedelta(days=10))
    revision_payload = {
        "revised_delivery_date": new_delivery,
        "reason": "Customer expedited shipping request for promotional launch."
    }
    r_rev = client.post(
        f"/api/v1/orders/{order_id}/revise-delivery-date",
        json=revision_payload,
        headers=admin_hdr
    )
    assert r_rev.status_code == 200, r_rev.text
    updated_order = r_rev.json()

    # 3. Verify original date retained & current date updated
    assert updated_order["original_delivery_date"] == orig_delivery
    assert updated_order["current_delivery_date"] == new_delivery

    # 4. Verify revision recorded
    revisions = updated_order["delivery_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["previous_delivery_date"] == orig_delivery
    assert revisions[0]["revised_delivery_date"] == new_delivery
    assert revisions[0]["reason"] == "Customer expedited shipping request for promotional launch."
    assert revisions[0]["revised_by_id"] is not None

    # 5. Verify remaining working days and targets recalculated
    new_working_days = updated_order["remaining_working_days"]
    assert new_working_days < initial_working_days

    new_target = updated_order["routes"][0]["operations"][0]["daily_target"]
    assert new_target > initial_target
