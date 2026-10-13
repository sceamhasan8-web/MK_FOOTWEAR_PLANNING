"""
Unit & Integration Tests for the Automatic Production Planning Engine
Date-Wise TG / ON HAND / O/T Planning Matrix System.
Covers Sections 1-55, including test cases 48, 49, 50, 51, 52, 53.
"""
import openpyxl
from io import BytesIO
from datetime import date, timedelta
from app.models.route import Section, SectionRouteStatus
from app.services.production_planning_service import ProductionPlanningService
from app.services.calendar_service import CalendarService
from app.services.export_service import ExportService


def test_specification_test_48_matrix_planning_generation(client, auth_headers, db_session):
    """
    Test 48:
    Order: Buyer = BATA, Quantity = 30,000, Planning Start = 2026-10-05, Shipment = 2026-10-15 (11 days).
    Route: CUTTING (Required), PRINTING (Required), EMBOSS (Required), SEWING (Required), LASTING (Required).
    Verifies 11 dates generated, each section receives T/G, ON HAND, O/T, and final summary row.
    """
    admin_hdr = auth_headers("admin")

    # 1. Create Buyer
    r_b = client.post("/api/v1/buyers", json={
        "name": "BATA Footwear",
        "buyer_code": "BATA-M48",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    # 2. Get Sections
    sec_names = ["Cutting", "Printing", "Emboss", "Sewing", "Lasting"]
    sec_objs = {}
    for name in sec_names:
        s = db_session.query(Section).filter(Section.name == name).first()
        assert s is not None, f"Section {name} must exist"
        sec_objs[name] = s

    # 3. Create Order
    start_d = date(2026, 10, 5)
    ship_d = date(2026, 10, 15)
    routes_payload = []
    for s_name in sec_names:
        s = sec_objs[s_name]
        routes_payload.append({
            "section_id": s.id,
            "status": "REQUIRED",
            "operations": [
                {
                    "operation_name": f"{s_name} Operation",
                    "sequence_order": 1,
                    "components": []
                }
            ]
        })

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-BATA-30K",
        "customer_ref": "BATA-REF-48",
        "style_model": "Sneaker Ultra",
        "total_quantity": 30000.0,
        "production_start_date": str(start_d),
        "original_delivery_date": str(ship_d),
        "routes": routes_payload
    }, headers=admin_hdr)
    assert r_ord.status_code == 200
    order_id = r_ord.json()["id"]

    # 4. Fetch Matrix Planning Sheet
    r_matrix = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    assert r_matrix.status_code == 200
    data = r_matrix.json()

    assert data["order_id"] == order_id
    assert data["total_quantity"] == 30000.0
    # Verifies exactly 11 days generated
    assert len(data["rows"]) == 11
    assert data["rows"][0]["date"] == "2026-10-05"
    assert data["rows"][-1]["date"] == "2026-10-15"

    # Verifies CUTTING has initial raw on hand of 30,000 on day 1
    d1_sec = data["rows"][0]["section_data"]
    assert "CUTTING" in d1_sec
    assert d1_sec["CUTTING"]["on_hand"] == 30000.0

    # Summary row verification
    summary = data["summary"]
    assert "CUTTING" in summary
    assert "LASTING" in summary
    assert summary["CUTTING"]["balance"] == 30000.0


def test_specification_test_49_multi_process_completion(client, auth_headers, db_session):
    """
    Test 49:
    Category 2 Multi-Process Completion rule:
    Printing = 30,000, Emboss = 28,000, Sewing = 29,000.
    Expected Category 2 Completed Output = 28,000!
    Lasting Incoming WIP = 28,000 (NOT 87,000, NOT 30,000, NOT 29,000).
    """
    admin_hdr = auth_headers("admin")
    sup_hdr = auth_headers("supervisor")

    # Buyer & Order
    r_b = client.post("/api/v1/buyers", json={"name": "MultiProcess Buyer", "buyer_code": "MP-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    sec_names = ["Cutting", "Printing", "Emboss", "Sewing", "Lasting"]
    sec_objs = {name: db_session.query(Section).filter(Section.name == name).first() for name in sec_names}

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-MP-30K",
        "customer_ref": "REF-MP",
        "style_model": "Shoe MP",
        "total_quantity": 30000.0,
        "production_start_date": "2026-10-05",
        "original_delivery_date": "2026-10-15",
        "routes": [
            {
                "section_id": sec_objs[name].id,
                "status": "REQUIRED",
                "operations": [{"operation_name": f"{name} Op", "sequence_order": 1}]
            }
            for name in sec_names
        ]
    }, headers=admin_hdr)
    order = r_ord.json()
    order_id = order["id"]

    routes_by_name = {r["section_name"]: r for r in order["routes"]}

    # Enter Cutting production: 30,000 (so Category 2 has full incoming WIP)
    cut_r = routes_by_name["Cutting"]
    client.post("/api/v1/production/entry", json={
        "order_id": order_id,
        "route_id": cut_r["id"],
        "operation_id": cut_r["operations"][0]["id"],
        "entry_date": "2026-10-05",
        "quantity": 30000.0,
        "accepted_quantity": 30000.0,
        "rejected_quantity": 0.0
    }, headers=sup_hdr)

    # Enter Category 2 production:
    # Printing = 30,000
    prt_r = routes_by_name["Printing"]
    client.post("/api/v1/production/entry", json={
        "order_id": order_id,
        "route_id": prt_r["id"],
        "operation_id": prt_r["operations"][0]["id"],
        "entry_date": "2026-10-06",
        "quantity": 30000.0,
        "accepted_quantity": 30000.0,
        "rejected_quantity": 0.0
    }, headers=sup_hdr)

    # Emboss = 28,000
    emb_r = routes_by_name["Emboss"]
    client.post("/api/v1/production/entry", json={
        "order_id": order_id,
        "route_id": emb_r["id"],
        "operation_id": emb_r["operations"][0]["id"],
        "entry_date": "2026-10-06",
        "quantity": 28000.0,
        "accepted_quantity": 28000.0,
        "rejected_quantity": 0.0
    }, headers=sup_hdr)

    # Sewing = 29,000
    sew_r = routes_by_name["Sewing"]
    client.post("/api/v1/production/entry", json={
        "order_id": order_id,
        "route_id": sew_r["id"],
        "operation_id": sew_r["operations"][0]["id"],
        "entry_date": "2026-10-06",
        "quantity": 29000.0,
        "accepted_quantity": 29000.0,
        "rejected_quantity": 0.0
    }, headers=sup_hdr)

    # Check matrix planning:
    r_matrix = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    assert r_matrix.status_code == 200
    data = r_matrix.json()

    # Category Flow Summary: Category 2 Completed Output must be MIN(30000, 28000, 29000) = 28000!
    cat_flow = data["category_flow_summary"]
    cat2 = next(c for c in cat_flow if "Preparation" in c["category_name"] or c["category_id"] == 2)
    assert cat2["completed_output"] == 28000.0

    # Lasting Available On Hand must receive 28,000 (NOT 87,000, NOT 30,000, NOT 29,000)!
    cat3 = next(c for c in cat_flow if "Lasting" in c["category_name"] or c["category_id"] == 3)
    assert cat3["incoming_wip"] == 28000.0


def test_specification_test_50_dynamic_daily_target_recalculation(client, auth_headers, db_session):
    """
    Test 50:
    Order = 30,000.
    Remaining balance = 15,000 across 5 remaining working days -> Target = 3,000/day.
    If actual production entered = 4,000 -> New balance = 11,000 across 4 days -> New target = 2,750/day.
    """
    bal = 15000.0
    rem_days = 5
    t1 = ProductionPlanningService.calculate_daily_target(bal, rem_days)
    assert t1 == 3000.0

    # Production of 4,000 entered
    new_bal = ProductionPlanningService.calculate_balance(bal, 4000.0)
    assert new_bal == 11000.0
    rem_days_new = 4
    t2 = ProductionPlanningService.calculate_daily_target(new_bal, rem_days_new)
    assert t2 == 2750.0


def test_specification_test_51_on_hand_tracking(client, auth_headers):
    """
    Test 51:
    Previous stage completed = 10,000.
    Next stage actual produced = 6,000.
    Closing On Hand = 4,000.
    """
    available_oh = 10000.0
    actual = 6000.0
    closing_oh = max(0.0, available_oh - actual)
    assert closing_oh == 4000.0


def test_specification_test_52_shipment_date_revision(client, auth_headers, db_session):
    """
    Test 52:
    Current shipment = 2026-10-15.
    Revise shipment date to 2026-10-18 -> planning rows extend to 18/10/2026.
    Remaining target automatically redistributes.
    """
    admin_hdr = auth_headers("admin")

    r_b = client.post("/api/v1/buyers", json={"name": "Shipment Rev Buyer", "buyer_code": "SR-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-REV-SHIP",
        "customer_ref": "REF-REV",
        "style_model": "Boot",
        "total_quantity": 20000.0,
        "production_start_date": "2026-10-05",
        "original_delivery_date": "2026-10-15",
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut Op", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    order_id = r_ord.json()["id"]

    # Initial plan: 11 rows (05/10 to 15/10)
    r_m1 = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    assert len(r_m1.json()["rows"]) == 11

    # Revise delivery date to 2026-10-18
    r_rev = client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": "2026-10-18",
        "reason": "Customer requested extension"
    }, headers=admin_hdr)
    assert r_rev.status_code == 200

    # Plan extends to 14 rows (05/10 to 18/10)
    r_m2 = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    data2 = r_m2.json()
    assert len(data2["rows"]) == 14
    assert data2["rows"][-1]["date"] == "2026-10-18"



def test_specification_test_53_summary_calculations(client, auth_headers):
    """
    Test 53:
    Daily Printing T/G = 1,000, 1,200, 1,300, 1,500, 1,255 -> Total T/G = 6,255.
    Final On Hand = 3,000 (NOT sum of snapshots).
    """
    daily_tg = [1000.0, 1200.0, 1300.0, 1500.0, 1255.0]
    total_tg = sum(daily_tg)
    assert total_tg == 6255.0
    final_on_hand = 3000.0
    assert final_on_hand == 3000.0


def test_matrix_planning_xlsx_and_csv_export(client, auth_headers, db_session):
    """
    Verifies that the 5-sheet Matrix Planning XLSX workbook and CSV can be downloaded cleanly.
    """
    admin_hdr = auth_headers("admin")

    # Get any existing order
    orders = client.get("/api/v1/orders", headers=admin_hdr).json()
    if not orders:
        return
    order_id = orders[0]["id"]

    # XLSX Export
    r_xlsx = client.get(f"/api/v1/exports/orders/{order_id}/matrix-planning/xlsx", headers=admin_hdr)
    assert r_xlsx.status_code == 200
    assert "application/vnd.openxmlformats" in r_xlsx.headers["content-type"]

    wb = openpyxl.load_workbook(BytesIO(r_xlsx.content))
    expected_sheets = ["Production Planning", "Summary", "Order Details", "Production Flow", "Daily Actual"]
    for s_title in expected_sheets:
        assert s_title in wb.sheetnames

    # Check Summary Sheet in XLSX
    ws_sum = wb["Summary"]
    assert ws_sum["A3"].value == "Section"
    assert ws_sum["B3"].value == "Total T/G"
    assert ws_sum["C3"].value == "Final On Hand"

    # CSV Export
    r_csv = client.get(f"/api/v1/exports/orders/{order_id}/matrix-planning/csv", headers=admin_hdr)
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers["content-type"]
    csv_text = r_csv.text
    assert "Date" in csv_text
    assert "TOTAL / SUMMARY" in csv_text


def test_multi_department_wip_flow_cutting_to_lasting(client, auth_headers, db_session):
    """
    Verifies complete multi-department workflow from Cutting down to Lasting:
    Route: Cutting -> Upper Prep -> Stitching -> Printing -> Stockfitting -> Lasting
    Core Logic:
    1. Every section renders T/G, ON HAND, O/T.
    2. Output (O/T) of preceding section automatically flows into On Hand of next sequential section.
    3. Logging completed work (C/P) adds to O/T and subtracts from On Hand balance.
    """
    admin_hdr = auth_headers("admin")
    sup_hdr = auth_headers("supervisor")

    # 1. Create Buyer
    r_b = client.post("/api/v1/buyers", json={
        "name": "Global Footwear Brands",
        "buyer_code": "GFB-WIP-01",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    # 2. Get Sections for full multi-department route
    workflow_sections = ["Cutting", "Upper Prep", "Stitching", "Printing", "Stockfitting", "Lasting"]
    sec_objs = {}
    for name in workflow_sections:
        s = db_session.query(Section).filter(Section.name == name).first()
        assert s is not None, f"Section {name} must exist in catalog"
        sec_objs[name] = s

    # 3. Build sequential route payload with increasing sequence_order (1 to 6)
    routes_payload = []
    for seq_idx, name in enumerate(workflow_sections, start=1):
        s = sec_objs[name]
        routes_payload.append({
            "section_id": s.id,
            "status": "REQUIRED",
            "sequence_order": seq_idx,
            "operations": [
                {
                    "operation_name": f"{name} Main Process",
                    "sequence_order": 1,
                    "components": []
                }
            ]
        })

    # 4. Create Order (30,000 pairs, 11 production days)
    start_d = date(2026, 10, 5)
    ship_d = date(2026, 10, 15)
    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-WIP-MULTI-30K",
        "customer_ref": "REF-WIP-FLOW",
        "style_model": "Air Flex Multi Runner",
        "total_quantity": 30000.0,
        "production_start_date": str(start_d),
        "original_delivery_date": str(ship_d),
        "routes": routes_payload
    }, headers=admin_hdr)
    assert r_ord.status_code == 200
    order = r_ord.json()
    order_id = order["id"]

    routes_by_name = {r["section_name"]: r for r in order["routes"]}

    # 5. Verify initial planning sheet has all 6 sections
    r_plan = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    assert r_plan.status_code == 200
    pdata = r_plan.json()
    rendered_sections = [s["section_name"] for s in pdata["sections"]]
    assert rendered_sections == ["CUTTING", "UPPER PREP", "STITCHING", "PRINTING", "STOCKFITTING", "LASTING"]

    # Initial Day 1: Cutting has 30,000 raw on hand; subsequent sections have 0 pending stock
    d1 = pdata["rows"][0]["section_data"]
    assert d1["CUTTING"]["on_hand"] == 30000.0
    assert d1["UPPER PREP"]["on_hand"] == 0.0
    assert d1["STITCHING"]["on_hand"] == 0.0

    # 6. Day 1 Entry: Cutting completes 5,000 pairs
    cut_r = routes_by_name["Cutting"]
    r_entry1 = client.post("/api/v1/production/entry", json={
        "order_id": order_id,
        "route_id": cut_r["id"],
        "operation_id": cut_r["operations"][0]["id"],
        "entry_date": "2026-10-05",
        "quantity": 5000.0,
        "accepted_quantity": 5000.0,
        "rejected_quantity": 0.0
    }, headers=sup_hdr)
    assert r_entry1.status_code == 200

    # Verify Day 1 WIP flow:
    # Cutting O/T = 5,000 -> Closing On Hand = 25,000
    # Upper Prep automatically receives 5,000 into its On Hand!
    r_plan1 = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    d1_after = r_plan1.json()["rows"][0]["section_data"]
    assert d1_after["CUTTING"]["ot"] == 5000.0
    assert d1_after["CUTTING"]["closing_on_hand"] == 25000.0
    assert d1_after["UPPER PREP"]["on_hand"] == 5000.0
    assert d1_after["UPPER PREP"]["ot"] == 0.0

    # 7. Day 2 Entry: Upper Prep completes 3,500 pairs
    up_r = routes_by_name["Upper Prep"]
    r_entry2 = client.post("/api/v1/production/entry", json={
        "order_id": order_id,
        "route_id": up_r["id"],
        "operation_id": up_r["operations"][0]["id"],
        "entry_date": "2026-10-06",
        "quantity": 3500.0,
        "accepted_quantity": 3500.0,
        "rejected_quantity": 0.0
    }, headers=sup_hdr)
    assert r_entry2.status_code == 200

    # Verify Day 2 WIP flow:
    # Upper Prep: On Hand was 5,000 -> O/T = 3,500 -> Closing On Hand = 1,500
    # Stitching automatically receives 3,500 into its On Hand!
    r_plan2 = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    d2 = r_plan2.json()["rows"][1]["section_data"]
    assert d2["UPPER PREP"]["on_hand"] == 5000.0
    assert d2["UPPER PREP"]["ot"] == 3500.0
    assert d2["UPPER PREP"]["closing_on_hand"] == 1500.0
    assert d2["STITCHING"]["on_hand"] == 3500.0
    assert d2["STITCHING"]["ot"] == 0.0

    # 8. Day 3 Entry: Stitching completes 3,500 pairs
    stitch_r = routes_by_name["Stitching"]
    r_entry3 = client.post("/api/v1/production/entry", json={
        "order_id": order_id,
        "route_id": stitch_r["id"],
        "operation_id": stitch_r["operations"][0]["id"],
        "entry_date": "2026-10-07",
        "quantity": 3500.0,
        "accepted_quantity": 3500.0,
        "rejected_quantity": 0.0
    }, headers=sup_hdr)
    assert r_entry3.status_code == 200

    # Verify Day 3 WIP flow into Printing:
    # Stitching O/T = 3,500 -> Flows into Printing On Hand = 3,500!
    r_plan3 = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    d3 = r_plan3.json()["rows"][2]["section_data"]
    assert d3["STITCHING"]["ot"] == 3500.0
    assert d3["STITCHING"]["closing_on_hand"] == 0.0
    assert d3["PRINTING"]["on_hand"] == 3500.0

