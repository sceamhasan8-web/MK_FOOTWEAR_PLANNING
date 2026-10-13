from datetime import date, timedelta


def test_scenario_a_buyer_and_order_creation(client, auth_headers):
    """
    Scenario A: Buyer and order creation
    Create a buyer named BATA and an order with 70,000 pairs.
    Verify that the order, its buyer relationship, delivery date,
    and configured production route are saved correctly.
    """
    admin_hdr = auth_headers("admin")

    # 1. Create buyer BATA
    buyer_payload = {
        "name": "BATA Shoe Company",
        "buyer_code": "BATA-001",
        "contact_person": "Tariqul Islam",
        "phone": "+880 1711 000111",
        "email": "orders@bata.com",
        "address": "Tongi, Gazipur",
        "notes": "Key retail client",
        "is_active": True
    }
    r_buyer = client.post("/api/v1/buyers", json=buyer_payload, headers=admin_hdr)
    assert r_buyer.status_code == 200, r_buyer.text
    buyer_data = r_buyer.json()
    assert buyer_data["id"] is not None
    assert buyer_data["buyer_code"] == "BATA-001"
    buyer_id = buyer_data["id"]

    # 2. Create order with 70,000 pairs
    delivery_date = str(date.today() + timedelta(days=25))
    order_payload = {
        "buyer_id": buyer_id,
        "order_code": "ORD-BATA-70K",
        "customer_ref": "BATA-PRO-70000",
        "po_number": "PO-9921",
        "style_model": "Court Pro Classic",
        "description": "70,000 pairs men footwear",
        "total_quantity": 70000.0,
        "original_delivery_date": delivery_date,
        "priority": "HIGH",
        "notes": "First production batch"
    }
    r_order = client.post("/api/v1/orders", json=order_payload, headers=admin_hdr)
    assert r_order.status_code == 200, r_order.text
    order_data = r_order.json()

    # 3. Verify order and relationships
    assert order_data["order_code"] == "ORD-BATA-70K"
    assert order_data["total_quantity"] == 70000.0
    assert order_data["buyer_id"] == buyer_id
    assert order_data["buyer_name"] == "BATA Shoe Company"
    assert order_data["current_delivery_date"] == delivery_date
    assert order_data["original_delivery_date"] == delivery_date

    # 4. Verify configured production routes were created
    routes = order_data["routes"]
    assert len(routes) > 0
    section_names = [r["section_name"] for r in routes]
    assert "Cutting" in section_names
    assert "Printing" in section_names
    assert "Lasting" in section_names

    # Check that required operations have 70,000 required quantity
    for r in routes:
        for op in r["operations"]:
            assert op["required_quantity"] == 70000.0
            assert op["balance_quantity"] == 70000.0
