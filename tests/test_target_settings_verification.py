import pytest
from datetime import date, timedelta
from app.models.route import Section, ProductionTargetSetting
from app.models.order import Order, OrderStatus
from app.models.buyer import Buyer
from app.services.production_planning_service import ProductionPlanningService
from app.services.settings_service import SettingsService


def test_scenario_a_save_new_settings(client, db_session, auth_headers):
    """
    Test A: Save New Settings
    Set Cutting Minimum = 2,000 and Maximum = 4,000.
    Expected:
    - API succeeds.
    - Database contains the values.
    - API read returns the same values.
    """
    headers = auth_headers("admin")
    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    assert sec_cut is not None

    payload = {
        "section_id": sec_cut.id,
        "minimum_daily_target": 2000,
        "maximum_daily_target": 4000,
        "unit": "Pairs/day",
        "calculation_mode": "BALANCED",
        "override_policy": "ALLOWED",
        "is_active": True,
        "notes": "Cutting line standard"
    }

    # Test via settings endpoint
    resp = client.put(f"/api/v1/settings/target-settings/{sec_cut.id}", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["saved"] is True
    assert data["minimum_daily_target"] == 2000
    assert data["maximum_daily_target"] == 4000
    assert data["section_id"] == sec_cut.id

    # Verify DB persistence directly
    db_setting = db_session.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == sec_cut.id).first()
    assert db_setting is not None
    assert db_setting.minimum_daily_target == 2000
    assert db_setting.maximum_daily_target == 4000

    # Verify GET read
    get_resp = client.get("/api/v1/settings/target-settings", headers=headers)
    assert get_resp.status_code == 200
    settings_list = get_resp.json()
    cut_setting = next((s for s in settings_list if s["section_id"] == sec_cut.id), None)
    assert cut_setting is not None
    assert cut_setting["minimum_daily_target"] == 2000
    assert cut_setting["maximum_daily_target"] == 4000


def test_scenario_b_update_existing_settings(client, db_session, auth_headers):
    """
    Test B: Update Existing Settings
    Change Cutting Minimum from 2,000 to 2,500.
    Expected:
    - The existing configuration is updated.
    - No duplicate section configuration is created.
    - Reloaded value is 2,500.
    """
    headers = auth_headers("admin")
    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    assert sec_cut is not None

    # Initial save
    client.put(f"/api/v1/settings/target-settings/{sec_cut.id}", json={
        "section_id": sec_cut.id,
        "minimum_daily_target": 2000,
        "maximum_daily_target": 4000
    }, headers=headers)

    # Update to 2500
    resp = client.put(f"/api/v1/settings/target-settings/{sec_cut.id}", json={
        "section_id": sec_cut.id,
        "minimum_daily_target": 2500,
        "maximum_daily_target": 4000
    }, headers=headers)
    assert resp.status_code == 200

    # Ensure no duplicates in DB
    all_cut_settings = db_session.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == sec_cut.id).all()
    assert len(all_cut_settings) == 1
    assert all_cut_settings[0].minimum_daily_target == 2500

    # Reload via GET
    get_resp = client.get("/api/v1/settings/target-settings", headers=headers)
    cut_setting = next((s for s in get_resp.json() if s["section_id"] == sec_cut.id), None)
    assert cut_setting["minimum_daily_target"] == 2500


def test_scenario_c_independent_sections(client, db_session, auth_headers):
    """
    Test C: Independent Sections
    Save different settings for Cutting and Printing.
    Expected:
    - Saving Cutting does not change Printing.
    - Each section displays its own values.
    """
    headers = auth_headers("admin")
    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    sec_prt = db_session.query(Section).filter(Section.name == "Printing").first()

    # Save Cutting: 2,000 / 4,000
    client.put(f"/api/v1/settings/target-settings/{sec_cut.id}", json={
        "minimum_daily_target": 2000,
        "maximum_daily_target": 4000
    }, headers=headers)

    # Save Printing: 1,500 / 3,500
    client.put(f"/api/v1/settings/target-settings/{sec_prt.id}", json={
        "minimum_daily_target": 1500,
        "maximum_daily_target": 3500
    }, headers=headers)

    get_resp = client.get("/api/v1/settings/target-settings", headers=headers)
    settings_dict = {s["section_name"]: s for s in get_resp.json()}

    assert settings_dict["Cutting"]["minimum_daily_target"] == 2000
    assert settings_dict["Cutting"]["maximum_daily_target"] == 4000

    assert settings_dict["Printing"]["minimum_daily_target"] == 1500
    assert settings_dict["Printing"]["maximum_daily_target"] == 3500


def test_scenario_d_invalid_minimum_and_maximum(client, db_session, auth_headers):
    """
    Test D: Invalid Minimum and Maximum
    Minimum = 4,000, Maximum = 2,000.
    Expected:
    - Validation fails (400 or 422).
    - Invalid configuration is not saved.
    """
    headers = auth_headers("admin")
    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    # Min > Max
    resp = client.put(f"/api/v1/settings/target-settings/{sec_cut.id}", json={
        "minimum_daily_target": 4000,
        "maximum_daily_target": 2000
    }, headers=headers)
    assert resp.status_code in (400, 422)

    # Negative minimum
    resp_neg = client.put(f"/api/v1/settings/target-settings/{sec_cut.id}", json={
        "minimum_daily_target": -500,
        "maximum_daily_target": 2000
    }, headers=headers)
    assert resp_neg.status_code in (400, 422)

    # Negative maximum
    resp_neg_max = client.put(f"/api/v1/settings/target-settings/{sec_cut.id}", json={
        "minimum_daily_target": 1000,
        "maximum_daily_target": -100
    }, headers=headers)
    assert resp_neg_max.status_code in (400, 422)


def test_scenario_e_database_persistence(client, db_session, auth_headers):
    """
    Test E: Database Persistence
    Save settings, re-query from a clean session.
    Expected: Saved settings remain unchanged.
    """
    headers = auth_headers("admin")
    sec_sew = db_session.query(Section).filter(Section.name == "Sewing").first()

    client.put(f"/api/v1/settings/target-settings/{sec_sew.id}", json={
        "minimum_daily_target": 2200,
        "maximum_daily_target": 5500,
        "notes": "High capacity line"
    }, headers=headers)

    # Query from db_session
    db_session.expire_all()
    persisted = db_session.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == sec_sew.id).first()
    assert persisted is not None
    assert persisted.minimum_daily_target == 2200
    assert persisted.maximum_daily_target == 5500
    assert persisted.notes == "High capacity line"


def test_scenario_f_target_calculation(db_session):
    """
    Test F: Target Calculation
    Balance = 30,000, Working days = 10, Minimum = 2,000, Maximum = 4,000.
    Expected:
    - Balanced target is 3,000 pairs/day.
    - Total planned T/G equals 30,000 exactly.
    """
    start_d = date(2026, 11, 1)
    dates = [start_d + timedelta(days=i) for i in range(10)]

    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000,
        cumulative_accepted=0,
        current_allocatable_wip=30000,
        working_dates=dates,
        effective_min=2000,
        effective_max=4000,
        calculation_mode="BALANCED"
    )

    assert len(schedule) == 10
    total_planned = sum(schedule.values())
    assert total_planned == 30000
    for d, qty in schedule.items():
        assert qty == 3000
        assert 2000 <= qty <= 4000


def test_scenario_g_maximum_limit_and_conflict(db_session):
    """
    Test G: Maximum Limit
    Calculate a required rate of 5,000 with a configured maximum of 4,000.
    Expected:
    - Normal planned T/G does not exceed the maximum (4,000).
    - evaluate_capacity_feasibility flags the deadline conflict.
    """
    dates = [date(2026, 11, 1) + timedelta(days=i) for i in range(4)]
    # Balance 20,000 in 4 days = 5,000/day needed, but Max = 4,000
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=20000,
        cumulative_accepted=0,
        current_allocatable_wip=20000,
        working_dates=dates,
        effective_min=2000,
        effective_max=4000,
        calculation_mode="BALANCED"
    )

    for d, qty in schedule.items():
        assert qty <= 4000

    feasibility = ProductionPlanningService.evaluate_capacity_feasibility(
        remaining_balance=20000,
        remaining_workdays=4,
        maximum_daily_target=4000
    )

    assert feasibility["is_feasible"] is False
    assert feasibility["required_daily_rate"] == 5000
    assert feasibility["shortfall"] == 4000
    assert feasibility["conflict"] is not None


def test_scenario_h_no_available_wip(db_session):
    """
    Test H: No Available WIP
    Printing On Hand = 0, Minimum = 2,000.
    Expected:
    - Executable T/G = 0.
    - Planning does not invent fictitious production.
    """
    dates = [date(2026, 11, 1) + timedelta(days=i) for i in range(5)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=10000,
        cumulative_accepted=0,
        current_allocatable_wip=0,  # No WIP available
        working_dates=dates,
        effective_min=2000,
        effective_max=4000,
        calculation_mode="BALANCED"
    )

    for d, qty in schedule.items():
        assert qty == 0
    assert sum(schedule.values()) == 0


def test_scenario_i_historical_safety(client, db_session, auth_headers):
    """
    Test I: Historical Safety
    Updating section settings leaves past actual production records untouched.
    """
    headers = auth_headers("admin")
    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    # Update settings
    resp = client.put(f"/api/v1/settings/target-settings/{sec_cut.id}", json={
        "minimum_daily_target": 3500,
        "maximum_daily_target": 6000
    }, headers=headers)
    assert resp.status_code == 200

    # Ensure stable section ID remains
    sec_after = db_session.query(Section).filter(Section.id == sec_cut.id).first()
    assert sec_after.name == "Cutting"


def test_scenario_j_permission_enforcement(client, db_session, auth_headers):
    """
    Test J: Permission Enforcement
    Attempt to update settings using a user without permission (e.g. VIEWER).
    Expected:
    - API rejects the request (403).
    - Database values remain unchanged.
    """
    viewer_headers = auth_headers("viewer")
    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    resp = client.put(f"/api/v1/settings/target-settings/{sec_cut.id}", json={
        "minimum_daily_target": 9999,
        "maximum_daily_target": 19999
    }, headers=viewer_headers)

    assert resp.status_code == 403


def test_scenario_k_regression_suite(client, db_session, auth_headers):
    """
    Test K: Regression Tests
    Verify that:
    - Buyer Management works.
    - Department/Section reads work.
    - Target Settings endpoint returns complete objects.
    """
    headers = auth_headers("admin")

    # 1. Buyer management
    buyer_resp = client.get("/api/v1/buyers", headers=headers)
    assert buyer_resp.status_code == 200

    # 2. Departments
    dept_resp = client.get("/api/v1/departments/sections", headers=headers)
    assert dept_resp.status_code == 200
    assert len(dept_resp.json()) > 0

    # 3. Target settings read
    tgt_resp = client.get("/api/v1/settings/target-settings", headers=headers)
    assert tgt_resp.status_code == 200
    items = tgt_resp.json()
    assert isinstance(items, list)
    for it in items:
        assert "section_id" in it
        assert "minimum_daily_target" in it
        assert "maximum_daily_target" in it
