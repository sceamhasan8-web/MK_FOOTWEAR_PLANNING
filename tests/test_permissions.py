from datetime import date, timedelta


def test_scenario_j_permissions_and_rbac(client, auth_headers):
    """
    Scenario J: Permissions
    Verify that unauthorized users cannot modify orders, revise deadlines,
    change production entries, or access restricted endpoints through direct API calls.
    """
    admin_hdr = auth_headers("admin")
    viewer_hdr = auth_headers("viewer")
    supervisor_hdr = auth_headers("supervisor")

    # 1. Create Buyer and Order as Admin
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "RBAC Test Buyer",
        "buyer_code": "RBAC-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-RBAC-01",
        "customer_ref": "REF-RBAC",
        "style_model": "RBAC Style",
        "total_quantity": 5000.0,
        "original_delivery_date": str(date.today() + timedelta(days=10)),
    }, headers=admin_hdr)
    order_id = r_order.json()["id"]

    # 2. Viewer tries to modify order -> 403 Forbidden
    r_viewer_mod = client.put(f"/api/v1/orders/{order_id}", json={
        "total_quantity": 9999.0
    }, headers=viewer_hdr)
    assert r_viewer_mod.status_code == 403

    # 3. Viewer tries to revise delivery date -> 403 Forbidden
    r_viewer_rev = client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": str(date.today() + timedelta(days=5)),
        "reason": "Unauthorized attempt"
    }, headers=viewer_hdr)
    assert r_viewer_rev.status_code == 403

    # 4. Viewer tries to enter production -> 403 Forbidden
    r_viewer_entry = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": 1,
        "operation_id": 1,
        "quantity": 100.0,
        "accepted_quantity": 100.0,
        "unit": "PAIRS"
    }, headers=viewer_hdr)
    assert r_viewer_entry.status_code == 403

    # 5. Supervisor tries to access audit history -> 403 Forbidden (Admin/Planner only)
    r_sup_audit = client.get("/api/v1/audit", headers=supervisor_hdr)
    assert r_sup_audit.status_code == 403

    # 6. Unauthenticated request -> 401 Unauthorized
    r_unauth = client.get("/api/v1/orders")
    assert r_unauth.status_code == 401
