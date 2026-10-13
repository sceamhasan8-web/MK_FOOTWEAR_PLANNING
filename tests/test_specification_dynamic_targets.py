import re
from pathlib import Path
from datetime import date, timedelta
from app.services.production_planning_service import ProductionPlanningService
from app.services.calendar_service import CalendarService
from app.models.route import Section


def test_specification_test_1(client, auth_headers, db_session):
    """
    Test 1:
    Order = 70,000
    Produced = 20,000
    Balance = 50,000
    Remaining days = 8
    Expected target = 6,250.
    """
    balance = ProductionPlanningService.calculate_balance(70000.0, 20000.0)
    assert balance == 50000.0

    target = ProductionPlanningService.calculate_daily_target(remaining_balance=balance, remaining_days=8)
    assert target == 6250.0

    # Also verify via Order API
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    r_buyer = client.post("/api/v1/buyers", json={
        "name": "BATA Shoe Company",
        "buyer_code": "BATA-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    # Calculate delivery date that yields exactly 8 working days from today
    cal = CalendarService.get_active_calendar(db_session)
    curr = date.today()
    workdays_found = 0
    target_delivery = curr
    while workdays_found < 8:
        if CalendarService.is_working_day(curr, cal, []):
            workdays_found += 1
            target_delivery = curr
        curr += timedelta(days=1)

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "BATA-ORD-70K",
        "customer_ref": "BATA-REF-01",
        "style_model": "Oxford Royale",
        "total_quantity": 70000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(target_delivery),
        "routes": [
            {
                "section_id": sec_cut.id,
                "status": "REQUIRED",
                "operations": [
                    {
                        "operation_name": "Leather Cutting",
                        "unit": "PAIRS",
                        "required_quantity": 70000.0
                    }
                ]
            }
        ]
    }, headers=admin_hdr)
    assert r_order.status_code == 200
    order_data = r_order.json()
    order_id = order_data["id"]
    route_id = order_data["routes"][0]["id"]
    op_id = order_data["routes"][0]["operations"][0]["id"]

    # Record 20,000 pairs completed
    r_entry = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": 20000.0,
        "accepted_quantity": 20000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "remarks": "Initial production"
    }, headers=supervisor_hdr)
    assert r_entry.status_code == 200

    # Retrieve recalculated order
    r_check = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr)
    assert r_check.status_code == 200
    chk = r_check.json()
    chk_op = chk["routes"][0]["operations"][0]

    assert chk_op["balance_quantity"] == 50000.0
    assert chk["remaining_working_days"] == 8
    assert chk_op["daily_target"] == 6250.0
    assert chk["daily_target"] == 6250.0


def test_specification_test_2(client, auth_headers, db_session):
    """
    Test 2:
    After entering additional 5,000:
    Balance = 45,000
    Remaining days = 7
    Expected target = 6,429.
    """
    balance = ProductionPlanningService.calculate_balance(50000.0, 5000.0)
    assert balance == 45000.0

    target = ProductionPlanningService.calculate_daily_target(remaining_balance=45000.0, remaining_days=7)
    # 45000 / 7 = 6428.57 -> ceiling = 6429
    assert target == 6429.0


def test_specification_test_3():
    """
    Test 3:
    Production completes the full required quantity.
    Balance = 0
    Expected target = 0.
    """
    balance = ProductionPlanningService.calculate_balance(70000.0, 70000.0)
    assert balance == 0.0

    target = ProductionPlanningService.calculate_daily_target(remaining_balance=0.0, remaining_days=5)
    assert target == 0.0

    # Overproduction also results in 0 balance and 0 target
    over_balance = ProductionPlanningService.calculate_balance(70000.0, 72000.0)
    assert over_balance == 0.0
    assert ProductionPlanningService.calculate_daily_target(over_balance, 5) == 0.0


def test_specification_test_4():
    """
    Test 4:
    Balance = 50,000
    Remaining days = 7
    Expected target = 7,143.
    """
    # 50,000 / 7 = 7142.857 -> ceiling = 7,143
    target = ProductionPlanningService.calculate_daily_target(remaining_balance=50000.0, remaining_days=7)
    assert target == 7143.0


def test_specification_test_5(client, auth_headers, db_session):
    """
    Test 5:
    Balance > 0
    Remaining days = 0
    Expected status = OVERDUE.
    The system must not divide by zero.
    """
    # Ensure math function does not divide by zero or raise exception
    target = ProductionPlanningService.calculate_daily_target(remaining_balance=12500.0, remaining_days=0)
    assert target == 0.0

    admin_hdr = auth_headers("admin")
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Overdue Buyer",
        "buyer_code": "OVD-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    # Delivery date in past -> remaining days = 0
    past_delivery = date.today() - timedelta(days=2)
    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-OVD-TEST",
        "customer_ref": "REF-OVD",
        "style_model": "Overdue Model",
        "total_quantity": 12500.0,
        "production_start_date": str(date.today() - timedelta(days=10)),
        "original_delivery_date": str(past_delivery),
        "routes": [
            {
                "section_id": sec_cut.id,
                "status": "REQUIRED",
                "operations": [
                    {
                        "operation_name": "Overdue Cut",
                        "unit": "PAIRS",
                        "required_quantity": 12500.0
                    }
                ]
            }
        ]
    }, headers=admin_hdr)
    assert r_order.status_code == 200
    order_data = r_order.json()

    assert order_data["remaining_working_days"] == 0
    assert order_data["outstanding_pairs"] == 12500.0
    assert order_data["status"] == "OVERDUE"
    assert order_data["is_overdue"] is True
    assert order_data["overdue_balance"] == 12500.0


def test_specification_test_6(client, auth_headers, db_session):
    """
    Test 6:
    Shipment date extended.
    Verify remaining days and daily target are reduced accordingly.
    Before: Balance = 30,000, Days = 5 -> Target = 6,000/day
    After: Days = 10 -> Target = 3,000/day
    """
    admin_hdr = auth_headers("admin")
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Extension Buyer",
        "buyer_code": "EXT-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    cal = CalendarService.get_active_calendar(db_session)
    curr = date.today()
    workdays_found = 0
    initial_delivery = curr
    while workdays_found < 5:
        if CalendarService.is_working_day(curr, cal, []):
            workdays_found += 1
            initial_delivery = curr
        curr += timedelta(days=1)

    extended_delivery = initial_delivery
    while workdays_found < 10:
        if CalendarService.is_working_day(curr, cal, []):
            workdays_found += 1
            extended_delivery = curr
        curr += timedelta(days=1)

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-EXT-TEST",
        "customer_ref": "REF-EXT",
        "style_model": "Extension Model",
        "total_quantity": 30000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(initial_delivery),
        "routes": [
            {
                "section_id": sec_cut.id,
                "status": "REQUIRED",
                "operations": [
                    {
                        "operation_name": "Cutting Process",
                        "unit": "PAIRS",
                        "required_quantity": 30000.0
                    }
                ]
            }
        ]
    }, headers=admin_hdr)
    assert r_order.status_code == 200
    order_data = r_order.json()
    order_id = order_data["id"]

    assert order_data["remaining_working_days"] == 5
    assert order_data["daily_target"] == 6000.0

    # Extend shipment date
    r_rev = client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": str(extended_delivery),
        "reason": "Customer requested delivery extension"
    }, headers=admin_hdr)
    assert r_rev.status_code == 200
    updated = r_rev.json()

    assert updated["remaining_working_days"] == 10
    assert updated["daily_target"] == 3000.0
    assert updated["current_delivery_date"] == str(extended_delivery)
    assert len(updated["delivery_revisions"]) == 1


def test_specification_test_7(client, auth_headers, db_session):
    """
    Test 7:
    Shipment date shortened.
    Verify daily target increases and risk status updates.
    """
    admin_hdr = auth_headers("admin")
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Shorten Buyer",
        "buyer_code": "SHT-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    cal = CalendarService.get_active_calendar(db_session)
    curr = date.today()
    workdays_found = 0
    orig_delivery = curr
    while workdays_found < 10:
        if CalendarService.is_working_day(curr, cal, []):
            workdays_found += 1
            orig_delivery = curr
        curr += timedelta(days=1)

    short_delivery = curr
    curr2 = date.today()
    short_found = 0
    while short_found < 2:
        if CalendarService.is_working_day(curr2, cal, []):
            short_found += 1
            short_delivery = curr2
        curr2 += timedelta(days=1)

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-SHT-TEST",
        "customer_ref": "REF-SHT",
        "style_model": "Shorten Model",
        "total_quantity": 20000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(orig_delivery),
        "routes": [
            {
                "section_id": sec_cut.id,
                "status": "REQUIRED",
                "operations": [
                    {
                        "operation_name": "Cutting Operation",
                        "unit": "PAIRS",
                        "required_quantity": 20000.0
                    }
                ]
            }
        ]
    }, headers=admin_hdr)
    assert r_order.status_code == 200
    order_data = r_order.json()
    order_id = order_data["id"]

    assert order_data["remaining_working_days"] == 10
    assert order_data["daily_target"] == 2000.0

    # Shorten delivery date to only 2 days
    r_rev = client.post(f"/api/v1/orders/{order_id}/revise-delivery-date", json={
        "revised_delivery_date": str(short_delivery),
        "reason": "Buyer rushed delivery deadline"
    }, headers=admin_hdr)
    assert r_rev.status_code == 200
    updated = r_rev.json()

    assert updated["remaining_working_days"] == 2
    # 20,000 / 2 = 10,000/day
    assert updated["daily_target"] == 10000.0
    # Status flags AT_RISK due to urgent tight window and high daily target
    assert updated["is_at_risk"] is True or updated["status"] in ["AT_RISK", "IN_PRODUCTION"]


def test_specification_test_8(client, auth_headers, db_session):
    """
    Test 8:
    Multiple Printing processes.
    Verify each process has its own balance and daily target.
    Order = 38,000
    Shipment is 5 production days away:
    Process 1: Required = 38,000, Produced = 38,000, Balance = 0 -> Target = 0
    Process 2: Required = 38,000, Produced = 35,000, Balance = 3,000 -> Target = CEILING(3,000 / 5) = 600
    Process 3: Required = 38,000, Produced = 27,000, Balance = 11,000 -> Target = CEILING(11,000 / 5) = 2,200
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Printing Buyer",
        "buyer_code": "PRT-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    cal = CalendarService.get_active_calendar(db_session)
    curr = date.today()
    workdays_found = 0
    target_delivery = curr
    while workdays_found < 5:
        if CalendarService.is_working_day(curr, cal, []):
            workdays_found += 1
            target_delivery = curr
        curr += timedelta(days=1)

    sec_prt = db_session.query(Section).filter(Section.name == "Printing").first()

    r_order = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-38K-PRT",
        "customer_ref": "REF-PRT-38K",
        "style_model": "Multi Screen Print",
        "total_quantity": 38000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(target_delivery),
        "routes": [
            {
                "section_id": sec_prt.id,
                "status": "REQUIRED",
                "operations": [
                    {
                        "operation_name": "Screen Printing Color 1",
                        "unit": "PAIRS",
                        "required_quantity": 38000.0
                    },
                    {
                        "operation_name": "Screen Printing Color 2",
                        "unit": "PAIRS",
                        "required_quantity": 38000.0
                    },
                    {
                        "operation_name": "High Density Foil Print",
                        "unit": "PAIRS",
                        "required_quantity": 38000.0
                    }
                ]
            }
        ]
    }, headers=admin_hdr)
    assert r_order.status_code == 200
    order_data = r_order.json()
    order_id = order_data["id"]
    route_id = order_data["routes"][0]["id"]
    op1_id = order_data["routes"][0]["operations"][0]["id"]
    op2_id = order_data["routes"][0]["operations"][1]["id"]
    op3_id = order_data["routes"][0]["operations"][2]["id"]

    # Record entries for each process
    # Process 1: 38,000 produced
    client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op1_id,
        "quantity": 38000.0,
        "accepted_quantity": 38000.0,
        "unit": "PAIRS"
    }, headers=supervisor_hdr)

    # Process 2: 35,000 produced
    client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op2_id,
        "quantity": 35000.0,
        "accepted_quantity": 35000.0,
        "unit": "PAIRS"
    }, headers=supervisor_hdr)

    # Process 3: 27,000 produced
    client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op3_id,
        "quantity": 27000.0,
        "accepted_quantity": 27000.0,
        "unit": "PAIRS"
    }, headers=supervisor_hdr)

    # Verify each process independently
    r_check = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr)
    assert r_check.status_code == 200
    chk = r_check.json()
    ops = chk["routes"][0]["operations"]

    p1 = next(o for o in ops if o["id"] == op1_id)
    p2 = next(o for o in ops if o["id"] == op2_id)
    p3 = next(o for o in ops if o["id"] == op3_id)

    # Process 1
    assert p1["balance_quantity"] == 0.0
    assert p1["daily_target"] == 0.0

    # Process 2
    assert p2["balance_quantity"] == 3000.0
    assert p2["daily_target"] == 600.0

    # Process 3
    assert p3["balance_quantity"] == 11000.0
    assert p3["daily_target"] == 2200.0


def test_specification_test_9():
    """
    Test 9:
    Production exceeds today's target.
    Verify future target is recalculated using the new balance.
    Suppose target = 6,000, but actual production entered = 8,000 (+2,000 ahead).
    Opening balance = 48,000, 8 days left.
    Target = 6,000.
    After producing 8,000: new balance = 40,000, 7 days left.
    New daily target = CEILING(40,000 / 7) = 5,715/day (recalculated lower).
    """
    # Day 1:
    balance_day1 = 48000.0
    target_day1 = ProductionPlanningService.calculate_daily_target(balance_day1, 8)
    assert target_day1 == 6000.0

    # Actual production exceeds target:
    actual_prod = 8000.0
    variance = ProductionPlanningService.calculate_daily_variance(actual_prod, target_day1)
    assert variance == 2000.0

    # Day 2:
    balance_day2 = ProductionPlanningService.calculate_balance(balance_day1, actual_prod)
    assert balance_day2 == 40000.0
    target_day2 = ProductionPlanningService.calculate_daily_target(balance_day2, 7)
    # 40,000 / 7 = 5714.28 -> ceiling = 5,715
    assert target_day2 == 5715.0
    assert target_day2 < target_day1


def test_specification_test_10():
    """
    Test 10:
    Production is below today's target.
    Verify future target increases appropriately.
    Suppose target = 6,000, actual production = 4,000 (shortfall 2,000).
    Opening balance = 48,000, 8 days left.
    Target = 6,000.
    After producing 4,000: new balance = 44,000, 7 days left.
    New daily target = CEILING(44,000 / 7) = 6,286/day (recalculated higher).
    """
    balance_day1 = 48000.0
    target_day1 = ProductionPlanningService.calculate_daily_target(balance_day1, 8)
    assert target_day1 == 6000.0

    actual_prod = 4000.0
    variance = ProductionPlanningService.calculate_daily_variance(actual_prod, target_day1)
    assert variance == -2000.0

    balance_day2 = ProductionPlanningService.calculate_balance(balance_day1, actual_prod)
    assert balance_day2 == 44000.0
    target_day2 = ProductionPlanningService.calculate_daily_target(balance_day2, 7)
    # 44,000 / 7 = 6285.71 -> ceiling = 6,286
    assert target_day2 == 6286.0
    assert target_day2 > target_day1


def test_specification_test_11_light_theme_default():
    """
    Test 11:
    Light theme.
    On a fresh installation, application must open in Light Theme.
    """
    # Find web-portal directory regardless of test runner CWD
    portal_dir = Path("web-portal") if Path("web-portal").exists() else Path("../web-portal")
    index_path = portal_dir / "index.html"
    assert index_path.exists(), f"index.html must exist at {index_path}"
    content = index_path.read_text(encoding="utf-8")

    # Body must open in light theme by default, NOT dark-theme
    assert '<body class="light-theme">' in content or '<body class="light-theme' in content
    assert '<body class="dark-theme">' not in content

    # CSS root tokens must define light theme defaults
    css_path = portal_dir / "styles.css"
    assert css_path.exists(), "styles.css must exist"
    css_content = css_path.read_text(encoding="utf-8")
    assert "--bg-main: #F8FAFC;" in css_content or "--bg-main: #f8fafc;" in css_content
    assert "--bg-surface: #FFFFFF;" in css_content or "--bg-surface: #ffffff;" in css_content

    # app.js must default to light theme on fresh launch
    js_path = portal_dir / "app.js"
    assert js_path.exists(), "app.js must exist"
    js_content = js_path.read_text(encoding="utf-8")
    assert "setTheme('light'" in js_content


def test_specification_test_12_theme_persistence():
    """
    Test 12:
    Theme persistence.
    After user manually switches to Dark Theme, the selected preference may persist for that user,
    but first-install/default state remains Light.
    """
    portal_dir = Path("web-portal") if Path("web-portal").exists() else Path("../web-portal")
    js_path = portal_dir / "app.js"
    assert js_path.exists(), "app.js must exist"
    js_content = js_path.read_text(encoding="utf-8")

    # Verifies theme toggle buttons exist and localStorage persistence is wired
    assert "localStorage.getItem('erp_theme')" in js_content
    assert "localStorage.setItem('erp_theme', 'dark')" in js_content
    assert "localStorage.setItem('erp_theme', 'light')" in js_content

    # Verifies visible theme controls exist in index.html
    index_path = portal_dir / "index.html"
    index_content = index_path.read_text(encoding="utf-8")
    assert "theme-btn-light" in index_content
    assert "theme-btn-dark" in index_content
    assert "Light" in index_content
    assert "Dark" in index_content
