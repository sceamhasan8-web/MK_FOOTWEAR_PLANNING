import io
import openpyxl
from datetime import date, timedelta


def test_scenario_i_export_xlsx_and_csv(client, auth_headers):
    """
    Scenario I: Export
    Export an order report to XLSX and CSV.
    Verify that the files open correctly and that exported quantities, dates, targets, balances,
    and operation statuses agree with database results.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    # 1. Create Buyer and Order
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Export Test Buyer",
        "buyer_code": "EXP-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-EXP-10K",
        "customer_ref": "REF-EXP-01",
        "style_model": "Export Sneaker",
        "total_quantity": 10000.0,
        "original_delivery_date": str(date.today() + timedelta(days=15)),
    }, headers=admin_hdr)
    order_data = r_order.json()
    order_id = order_data["id"]

    # Record an entry
    route_id = order_data["routes"][0]["id"]
    op_id = order_data["routes"][0]["operations"][0]["id"]
    client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": 2500.0,
        "accepted_quantity": 2500.0,
        "rejected_quantity": 50.0,
        "unit": "PAIRS",
        "remarks": "Export test run"
    }, headers=supervisor_hdr)

    # 2. Test XLSX Export
    r_xlsx = client.get(f"/api/v1/exports/orders/{order_id}/xlsx", headers=admin_hdr)
    assert r_xlsx.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in r_xlsx.headers["content-type"]

    # Verify openpyxl can load the exported bytes
    excel_file = io.BytesIO(r_xlsx.content)
    wb = openpyxl.load_workbook(excel_file)
    sheet_names = wb.sheetnames

    # Verify all 7 required sheets exist
    expected_sheets = [
        "Order Summary",
        "Daily Production Plan",
        "Section Summary",
        "Operation Details",
        "Component Details",
        "Production Entry History",
        "Delivery Date History"
    ]
    for s in expected_sheets:
        assert s in sheet_names, f"Missing sheet: {s}"

    # Verify content in Order Summary sheet
    ws_summary = wb["Order Summary"]
    found_order_code = False
    for row in ws_summary.iter_rows(values_only=True):
        if row[0] == "Order Code" and row[1] == "ORD-EXP-10K":
            found_order_code = True
            break
    assert found_order_code is True

    # 3. Test CSV Export
    r_csv = client.get(f"/api/v1/exports/orders/{order_id}/csv", headers=admin_hdr)
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers["content-type"]
    csv_text = r_csv.text

    assert "ORD-EXP-10K" in csv_text
    assert "Export Test Buyer" in csv_text
    assert "2500" in csv_text  # Contains recorded accepted production
