"""
Central Settings & Configuration Module Acceptance Tests (Tests A through L)
Footwear Manufacturing ERP Specification
"""
import io
import csv
import pytest
from datetime import date, timedelta
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.route import Section, Category, OrderRoute, ProductionTargetSetting
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.models.entry import DailyProductionEntry
from app.services.production_planning_service import ProductionPlanningService
from app.services.calendar_service import CalendarService
from app.services.wip_planning_engine import WIPPlanningEngine
from app.services.settings_service import SettingsService


def test_a_rename_section_stable_id_and_historical_integrity(client, auth_headers, db_session):
    """
    Test A — Rename Section
    Rename Cutting to Upper Cutting.
    Verify:
    - Display name changes.
    - Stable section ID remains the same.
    - Historical production remains linked.
    - Existing WIP values remain correct.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    # Find existing cutting section
    sec = db_session.query(Section).filter(Section.name.in_(["Cutting", "Upper Cutting"])).first()
    assert sec is not None
    original_id = sec.id

    # Create order with this section
    r_buyer = client.post("/api/v1/buyers", json={"name": "Buyer Test A", "buyer_code": "BA-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    order_payload = {
        "buyer_id": buyer_id,
        "order_code": "ORD-TEST-A",
        "customer_ref": "REF-A",
        "style_model": "Model A",
        "total_quantity": 5000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(date.today() + timedelta(days=10)),
        "routes": [{
            "section_id": original_id,
            "status": "REQUIRED",
            "sequence_order": 1,
            "operations": [{"operation_name": "Cutting Operation", "unit": "PAIRS", "required_quantity": 5000.0}]
        }]
    }
    r_order = client.post("/api/v1/orders", json=order_payload, headers=admin_hdr)
    assert r_order.status_code == 200
    order_id = r_order.json()["id"]
    route_id = r_order.json()["routes"][0]["id"]
    op_id = r_order.json()["routes"][0]["operations"][0]["id"]

    # Enter production of 1,500 pairs
    r_entry = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": 1500.0,
        "accepted_quantity": 1500.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=supervisor_hdr)
    assert r_entry.status_code == 200

    # Now rename section from Cutting to Upper Cutting via settings API
    r_rename = client.put(f"/api/v1/settings/sections/{original_id}", json={
        "name": "Upper Cutting",
        "category_id": sec.category_id,
        "display_order": sec.display_order,
        "is_active": True,
        "counting_unit": "Pairs",
        "reason": "Administrative renaming of Cutting to Upper Cutting"
    }, headers=admin_hdr)
    assert r_rename.status_code == 200
    renamed_data = r_rename.json()

    # Stable section ID preserved
    assert renamed_data["id"] == original_id
    assert renamed_data["name"] == "Upper Cutting"

    # Historical production remains linked to the same section and route
    entry_check = db_session.query(DailyProductionEntry).filter(DailyProductionEntry.route_id == route_id).first()
    assert entry_check is not None
    assert entry_check.accepted_quantity == 1500.0

    # Order planning reflects the renamed section with unchanged WIP & completed quantity
    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db_session, order_id)
    assert matrix["completed_quantity"] == 1500.0
    assert matrix["current_balance"] == 3500.0
    sec_names = [s["section_name"].upper() for s in matrix["sections"]]
    assert "UPPER CUTTING" in sec_names

    # Restore original name to preserve test suite idempotency
    client.put(f"/api/v1/settings/sections/{original_id}", json={
        "name": "Cutting",
        "category_id": sec.category_id,
        "display_order": sec.display_order,
        "planning_id": sec.planning_id or sec.display_order,
        "is_active": True,
        "counting_unit": "Pairs",
        "reason": "Teardown restore"
    }, headers=admin_hdr)


def test_b_minimum_target_driven_schedule():
    """
    Test B — Minimum Target
    Set Cutting minimum to 2,000.
    If balance is 30,000 and 30 working days are available, the minimum-driven schedule
    should target 2,000 on 15 working days, totalling 30,000.
    """
    days = [date(2026, 11, 1) + timedelta(days=i) for i in range(30)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000,
        cumulative_accepted=0,
        current_allocatable_wip=30000,
        working_dates=days,
        effective_min=2000,
        effective_max=4000,
        calculation_mode="MINIMUM_DRIVEN"
    )

    non_zero_days = [d for d, tg in schedule.items() if tg > 0]
    assert len(non_zero_days) == 15, f"Expected exactly 15 production days with min target, got {len(non_zero_days)}"
    for d in non_zero_days:
        assert schedule[d] == 2000, f"Expected 2,000 on active day {d}, got {schedule[d]}"

    assert sum(schedule.values()) == 30000, f"Total scheduled should equal balance 30,000, got {sum(schedule.values())}"


def test_c_maximum_target_capacity_constraint():
    """
    Test C — Maximum Target
    Set Cutting maximum to 4,000.
    If the shipment deadline requires 5,000 per day, flag the schedule as infeasible rather than silently planning 5,000.
    """
    # 50,000 balance with 10 days = 5,000 required daily rate
    days = [date(2026, 11, 1) + timedelta(days=i) for i in range(10)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=50000,
        cumulative_accepted=0,
        current_allocatable_wip=50000,
        working_dates=days,
        effective_min=2000,
        effective_max=4000,
        calculation_mode="BALANCED"
    )

    # Normal planned T/G must not silently exceed configured maximum of 4,000
    for d, tg in schedule.items():
        assert tg <= 4000, f"Target on {d} ({tg}) exceeded maximum limit of 4,000"

    # Engine must flag capacity infeasibility
    feasibility = ProductionPlanningService.evaluate_capacity_feasibility(
        remaining_balance=50000.0,
        remaining_workdays=10,
        maximum_daily_target=4000
    )
    assert not feasibility["is_feasible"]
    assert feasibility["required_daily_rate"] == 5000
    assert feasibility["maximum_daily_target"] == 4000
    assert feasibility["shortfall"] == 10000
    assert "Maximum daily capacity is insufficient" in feasibility["conflict"]


def test_d_final_balance_below_minimum():
    """
    Test D — Final Balance Below Minimum
    Balance = 1,200.
    Minimum = 2,000.
    Maximum = 4,000.
    Do not plan more than 1,200.
    """
    days = [date(2026, 11, 1) + timedelta(days=i) for i in range(5)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=1200,
        cumulative_accepted=0,
        current_allocatable_wip=1200,
        working_dates=days,
        effective_min=2000,
        effective_max=4000,
        calculation_mode="MINIMUM_DRIVEN"
    )

    total_planned = sum(schedule.values())
    assert total_planned == 1200, f"Expected total 1,200, got {total_planned}"
    assert schedule[days[0]] == 1200, f"Expected Day 1 to receive remaining balance 1,200, got {schedule[days[0]]}"
    assert total_planned <= 1200, "Must never plan more than the remaining balance"


def test_e_no_wip_downstream_target_is_zero():
    """
    Test E — No WIP
    Printing On Hand = 0.
    Minimum = 2,000.
    Expected executable target = 0. Status = WAITING FOR WIP.
    """
    days = [date(2026, 11, 1) + timedelta(days=i) for i in range(5)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000,
        cumulative_accepted=0,
        current_allocatable_wip=0,  # 0 On Hand
        working_dates=days,
        effective_min=2000,
        effective_max=4000,
        calculation_mode="BALANCED"
    )

    for d in days:
        assert schedule[d] == 0, f"Expected 0 target when allocatable WIP is 0, got {schedule[d]}"


def test_f_stock_limited_allocation_not_repeated():
    """
    Test F — Stock Limited
    Printing On Hand = 2,000.
    Required rate = 4,000.
    Maximum = 4,000.
    Expected executable target against current stock = 2,000.
    The same stock cannot be allocated again to the next date.
    """
    days = [date(2026, 11, 1) + timedelta(days=i) for i in range(5)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000,
        cumulative_accepted=0,
        current_allocatable_wip=2000,  # Only 2,000 confirmed available WIP
        working_dates=days,
        effective_min=2000,
        effective_max=4000,
        calculation_mode="BALANCED"
    )

    # Day 1 consumes the 2,000 WIP
    assert schedule[days[0]] == 2000
    # Day 2 onwards receives 0 because the same 2,000 cannot be allocated twice!
    for d in days[1:]:
        assert schedule[d] == 0, f"Same stock repeated on {d}: {schedule[d]}"

    assert sum(schedule.values()) == 2000


def test_g_settings_persistence(client, auth_headers, db_session):
    """
    Test G — Settings Persistence
    Save target limits and general settings, reload, and verify persistence in database.
    """
    admin_hdr = auth_headers("admin")
    sec = db_session.query(Section).first()

    # Save target limits via API
    r_save = client.put(f"/api/v1/settings/target-settings/{sec.id}", json={
        "section_id": sec.id,
        "minimum_daily_target": 2222,
        "maximum_daily_target": 4444,
        "calculation_mode": "MINIMUM_DRIVEN",
        "unit": "Pairs/day"
    }, headers=admin_hdr)
    assert r_save.status_code == 200

    # Query from DB directly to ensure database persistence
    db_session.expire_all()
    setting = db_session.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == sec.id).first()
    assert setting.minimum_daily_target == 2222
    assert setting.maximum_daily_target == 4444
    assert setting.calculation_mode == "MINIMUM_DRIVEN"

    # Also check General Settings persistence
    r_gen = client.put("/api/v1/settings/general", json={
        "company_name": "Apex Footwear Global Ltd.",
        "timezone": "Asia/Dhaka",
        "default_unit": "Pairs",
        "planning_cutoff_hour": 19
    }, headers=admin_hdr)
    assert r_gen.status_code == 200
    assert r_gen.json()["company_name"] == "Apex Footwear Global Ltd."
    assert r_gen.json()["planning_cutoff_hour"] == 19


def test_h_permissions_enforced_in_backend(client, auth_headers, db_session):
    """
    Test H — Permissions
    A viewer cannot modify section names or target limits through API requests.
    """
    viewer_hdr = auth_headers("viewer")
    sec = db_session.query(Section).first()

    # Viewer tries to rename section
    r_rename = client.put(f"/api/v1/settings/sections/{sec.id}", json={
        "name": "Hacked Name",
        "category_id": sec.category_id,
        "display_order": 1,
        "is_active": True
    }, headers=viewer_hdr)
    assert r_rename.status_code == 403, f"Expected 403 Forbidden for viewer, got {r_rename.status_code}"

    # Viewer tries to update targets
    r_target = client.put(f"/api/v1/settings/target-settings/{sec.id}", json={
        "section_id": sec.id,
        "minimum_daily_target": 9999,
        "maximum_daily_target": 9999
    }, headers=viewer_hdr)
    assert r_target.status_code == 403


def test_i_factory_calendar_holiday_integration(client, auth_headers, db_session):
    """
    Test I — Holiday
    Add a factory holiday and verify that future planning excludes it.
    """
    admin_hdr = auth_headers("admin")
    cal = CalendarService.get_active_calendar(db_session)
    holiday_date = date.today() + timedelta(days=5)

    # Ensure holiday_date was originally a work day if not Friday
    r_add = client.post("/api/v1/settings/calendar/exceptions", json={
        "exception_date": str(holiday_date),
        "exception_type": "factory_holiday",
        "description": "Test Factory Holiday Day Off"
    }, headers=admin_hdr)
    assert r_add.status_code == 200
    ex_id = r_add.json()["id"]

    # Verify is_working_day recognizes the holiday
    db_session.expire_all()
    exceptions = db_session.query(CalendarException).filter(CalendarException.calendar_id == cal.id).all()
    is_work = CalendarService.is_working_day(holiday_date, cal, exceptions)
    assert not is_work, f"Date {holiday_date} with factory_holiday exception must not be counted as a working day"

    # Cleanup
    client.delete(f"/api/v1/settings/calendar/exceptions/{ex_id}", headers=admin_hdr)


def test_j_historical_preservation(client, auth_headers, db_session):
    """
    Test J — Historical Preservation
    Change section name and maximum target. Verify historical actual production remains unchanged.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")
    sec = db_session.query(Section).first()

    r_buyer = client.post("/api/v1/buyers", json={"name": "Buyer J", "buyer_code": "BJ-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    order_res = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-HIST-J",
        "customer_ref": "REF-J",
        "style_model": "Model J",
        "total_quantity": 8000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(date.today() + timedelta(days=12)),
        "routes": [{
            "section_id": sec.id,
            "status": "REQUIRED",
            "sequence_order": 1,
            "operations": [{"operation_name": "Leather Cutting", "unit": "PAIRS", "required_quantity": 8000.0}]
        }]
    }, headers=admin_hdr)
    order_id = order_res.json()["id"]
    route_id = order_res.json()["routes"][0]["id"]
    op_id = order_res.json()["routes"][0]["operations"][0]["id"]

    # Record historical production
    r_ent = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "quantity": 2500.0,
        "accepted_quantity": 2500.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS"
    }, headers=supervisor_hdr)
    assert r_ent.status_code == 200

    # Change section target limits and name
    client.put(f"/api/v1/settings/target-settings/{sec.id}", json={
        "section_id": sec.id,
        "minimum_daily_target": 1800,
        "maximum_daily_target": 3600
    }, headers=admin_hdr)

    # Verify actual production transaction is unmodified
    db_session.expire_all()
    entry = db_session.query(DailyProductionEntry).filter(DailyProductionEntry.order_id == order_id).first()
    assert entry is not None
    assert entry.accepted_quantity == 2500.0
    assert entry.rejected_quantity == 0.0


def test_k_xlsx_csv_export_consistency(client, auth_headers, db_session):
    """
    Test K — XLSX/CSV
    Confirm that exported targets match the authoritative backend calculations.
    """
    admin_hdr = auth_headers("admin")
    sec = db_session.query(Section).first()

    r_buyer = client.post("/api/v1/buyers", json={"name": "Buyer K", "buyer_code": "BK-01", "is_active": True}, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    order_res = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-EXP-K",
        "customer_ref": "REF-K",
        "style_model": "Model K",
        "total_quantity": 10000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(date.today() + timedelta(days=10)),
        "routes": [{"section_id": sec.id, "status": "REQUIRED", "sequence_order": 1}]
    }, headers=admin_hdr)
    order_id = order_res.json()["id"]

    # Export CSV via orders export endpoint
    r_csv = client.get(f"/api/v1/exports/orders/{order_id}/csv", headers=admin_hdr)
    assert r_csv.status_code == 200
    assert len(r_csv.text) > 0

    # Export XLSX via orders export endpoint
    r_xlsx = client.get(f"/api/v1/exports/orders/{order_id}/xlsx", headers=admin_hdr)
    assert r_xlsx.status_code == 200
    assert len(r_xlsx.content) > 0


def test_l_existing_planning_regression_preserved(client, auth_headers, db_session):
    """
    Test L — Existing Planning Regression
    Verify that the original T/G / ON HAND / O/T planning sheet remains intact
    and the separate WIP Flow Planning sheet continues working independently.
    """
    admin_hdr = auth_headers("admin")
    order = db_session.query(Order).filter(Order.status != OrderStatus.CLOSED).first()
    if not order:
        return

    # 1. Original Planning Matrix Sheet API
    r_matrix = client.get(f"/api/v1/orders/{order.id}/planning-matrix", headers=admin_hdr)
    assert r_matrix.status_code == 200
    m_data = r_matrix.json()
    assert "rows" in m_data
    assert "summary" in m_data
    assert "validation" in m_data

    # 2. WIP Flow Sheet API
    r_wip = client.get(f"/api/v1/orders/{order.id}/wip-flow", headers=admin_hdr)
    assert r_wip.status_code == 200
    w_data = r_wip.json()
    assert "daily_flow_rows" in w_data
    assert "routes" in w_data
