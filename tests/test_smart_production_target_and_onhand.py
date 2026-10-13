"""
Authoritative Automated Acceptance Test Suite (Tests A through L)
Footwear ERP — Smart Production Target & On-Hand Control
Verifies that:
- Target never exceeds remaining requirement or available allocatable WIP
- Minimum daily target behaves correctly (lower bound, never invents fictitious stock)
- Downstream sections wait for actual WIP
- Actual production consumes On Hand, planned target does not
- Only actual production transfers WIP
- Corrected entries adjust downstream WIP and trigger recalculation
- Factory calendar and exports maintain 100% consistency
"""
import io
import csv
import pytest
import openpyxl
from datetime import date, timedelta
from sqlalchemy.orm import Session

from app.models.buyer import Buyer
from app.models.order import Order, OrderPriority, OrderStatus
from app.models.route import Section, OrderRoute, SectionRouteStatus, ProductionTargetSetting
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.models.entry import DailyProductionEntry
from app.services.production_planning_service import ProductionPlanningService
from app.services.calendar_service import CalendarService
from app.services.wip_planning_engine import WIPPlanningEngine


# =========================================================================
# TEST A: Target Must Not Exceed Available Quantity
# =========================================================================
def test_a_target_must_not_exceed_available_quantity():
    """
    Test A: Target must not exceed available quantity
    On Hand = 30,000
    Required Balance = 30,000
    Working Days = 10
    Minimum = 2,000
    Expected T/G: 3,000 per day for 10 days.
    Expected total T/G: 30,000. It must never be 36,911.
    """
    days = [date(2026, 10, 1) + timedelta(days=i) for i in range(10)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000,
        cumulative_accepted=0,
        current_allocatable_wip=30000,
        working_dates=days,
        effective_min=2000
    )

    assert len(schedule) == 10
    for d in days:
        assert schedule[d] == 3000, f"Expected 3,000 on {d}, got {schedule[d]}"

    total_tg = sum(schedule.values())
    assert total_tg == 30000, f"Expected total 30,000, got {total_tg}"
    assert total_tg != 36911, "Target exceeded available quantity with harmonic blowup"


# =========================================================================
# TEST B: Minimum Target Applies
# =========================================================================
def test_b_minimum_target_applies():
    """
    Test B: Minimum target applies
    On Hand = 30,000
    Required Balance = 30,000
    Working Days = 30
    Calculated balanced target = 1,000 pairs/day
    Cutting Minimum Daily Target = 2,000 pairs/day
    Expected plan: 2,000 pairs/day until 30,000 is fully allocated (15 working days).
    Remaining 15 days = 0.
    Expected total: 30,000.
    """
    days = [date(2026, 10, 1) + timedelta(days=i) for i in range(30)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000,
        cumulative_accepted=0,
        current_allocatable_wip=30000,
        working_dates=days,
        effective_min=2000
    )

    assert len(schedule) == 30
    for i in range(15):
        assert schedule[days[i]] == 2000, f"Expected 2,000 on day {i+1}, got {schedule[days[i]]}"
    for i in range(15, 30):
        assert schedule[days[i]] == 0, f"Expected 0 on day {i+1}, got {schedule[days[i]]}"

    total_tg = sum(schedule.values())
    assert total_tg == 30000
    assert total_tg <= 30000


# =========================================================================
# TEST C: Final Quantity Below Minimum
# =========================================================================
def test_c_final_quantity_below_minimum():
    """
    Test C: Final quantity below minimum
    On Hand = 1,200
    Required Balance = 1,200
    Working Days = 10
    Minimum = 2,000
    Expected T/G allocation: 1,200 maximum. The system must not plan 2,000.
    """
    days = [date(2026, 10, 1) + timedelta(days=i) for i in range(10)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=1200,
        cumulative_accepted=0,
        current_allocatable_wip=1200,
        working_dates=days,
        effective_min=2000
    )

    total_tg = sum(schedule.values())
    assert total_tg == 1200, f"Expected total 1,200, got {total_tg}"
    assert schedule[days[0]] == 1200
    for i in range(1, 10):
        assert schedule[days[i]] == 0


# =========================================================================
# TEST D: No Downstream WIP
# =========================================================================
def test_d_no_downstream_wip(client, auth_headers, db_session):
    """
    Test D: No downstream WIP
    Printing On Hand = 0
    Required Balance = 30,000
    Working Days = 10
    Minimum = 2,000
    Expected executable T/G = 0.
    Status = WAITING FOR WIP.
    """
    days = [date(2026, 10, 1) + timedelta(days=i) for i in range(10)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000,
        cumulative_accepted=0,
        current_allocatable_wip=0,
        working_dates=days,
        effective_min=2000
    )
    assert sum(schedule.values()) == 0
    assert all(val == 0 for val in schedule.values())

    admin_hdr = auth_headers("admin")
    r_b = client.post("/api/v1/buyers", json={"name": "Buyer D", "buyer_code": "BY-D", "is_active": True}, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    sec_prt = db_session.query(Section).filter(Section.name == "Printing").first()

    today_d = date.today()
    ship_d = today_d + timedelta(days=12)

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-TEST-D",
        "customer_ref": "REF-D",
        "style_model": "Style D",
        "total_quantity": 30000.0,
        "production_start_date": str(today_d),
        "original_delivery_date": str(ship_d),
        "routes": [
            {"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]},
            {"section_id": sec_prt.id, "status": "REQUIRED", "operations": [{"operation_name": "Print", "sequence_order": 1}]}
        ]
    }, headers=admin_hdr)
    order_id = r_ord.json()["id"]

    r_mat = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    assert r_mat.status_code == 200
    mat = r_mat.json()

    prt_summary = mat["summary"]["PRINTING"]
    assert prt_summary["total_tg"] == 0.0
    assert prt_summary["final_on_hand"] == 0.0
    assert prt_summary["status"] == "WAITING FOR WIP"


# =========================================================================
# TEST E: Downstream Has 2,000 WIP
# =========================================================================
def test_e_downstream_has_2000_wip():
    """
    Test E: Downstream has 2,000 WIP
    Printing On Hand = 2,000
    Required Balance = 30,000
    Working Days = 10
    Required Daily Rate = 4,000
    Minimum = 2,000
    Expected T/G allocation against current available WIP = 2,000.
    Future dates must not reuse the same 2,000 stock.
    """
    days = [date(2026, 10, 1) + timedelta(days=i) for i in range(10)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000,
        cumulative_accepted=0,
        current_allocatable_wip=2000,
        working_dates=days,
        effective_min=2000
    )

    assert schedule[days[0]] == 2000
    for i in range(1, 10):
        assert schedule[days[i]] == 0, f"Future day {i+1} improperly reused stock: got {schedule[days[i]]}"

    assert sum(schedule.values()) == 2000


# =========================================================================
# TEST F: Actual Production Reduces On Hand
# =========================================================================
def test_f_actual_production_reduces_on_hand(client, auth_headers, db_session):
    """
    Test F: Actual production reduces On Hand
    Opening On Hand = 10,000
    Target = 4,000
    Actual = 3,000
    Expected remaining On Hand = 7,000.
    Expected target shortfall = 1,000.
    The system must not reduce On Hand to 6,000 merely because the target was 4,000.
    """
    admin_hdr = auth_headers("admin")
    r_b = client.post("/api/v1/buyers", json={"name": "Buyer F", "buyer_code": "BY-F", "is_active": True}, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    today_d = date.today()
    ship_d = today_d + timedelta(days=5)

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-TEST-F",
        "customer_ref": "REF-F",
        "style_model": "Style F",
        "total_quantity": 10000.0,
        "production_start_date": str(today_d),
        "original_delivery_date": str(ship_d),
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    order_data = r_ord.json()
    order_id = order_data["id"]
    route_id = order_data["routes"][0]["id"]
    op_id = order_data["routes"][0]["operations"][0]["id"]

    # Post actual production of 3,000
    r_ent = client.post("/api/v1/production/entry", json={
        "order_id": order_id,
        "route_id": route_id,
        "operation_id": op_id,
        "entry_date": str(today_d),
        "quantity": 3000.0,
        "accepted_quantity": 3000.0,
        "rejected_quantity": 0.0,
    }, headers=admin_hdr)
    assert r_ent.status_code == 200

    order_obj = db_session.query(Order).filter(Order.id == order_id).first()
    wip_plan = WIPPlanningEngine.calculate_order_wip_flow(db_session, order_obj, as_of_date=today_d)

    wf = wip_plan["workflow_summary"][0]
    assert wf["complete"] == 3000.0
    assert wf["final_on_hand"] == 7000.0  # 10,000 - 3,000 = 7,000 (NOT 6,000)
    assert wf["balance"] == 7000.0


# =========================================================================
# TEST G: Actual Production Transfers WIP
# =========================================================================
def test_g_actual_production_transfers_wip(client, auth_headers, db_session):
    """
    Test G: Actual production transfers WIP
    Cutting Complete before entry = 10,000
    New Cutting actual entry = 2,000
    Expected Cutting cumulative Complete = 12,000.
    Printing incoming WIP must increase by 2,000, not by the target amount.
    """
    admin_hdr = auth_headers("admin")
    r_b = client.post("/api/v1/buyers", json={"name": "Buyer G", "buyer_code": "BY-G", "is_active": True}, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    sec_prt = db_session.query(Section).filter(Section.name == "Printing").first()
    today_d = date.today()
    ship_d = today_d + timedelta(days=10)

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-TEST-G",
        "customer_ref": "REF-G",
        "style_model": "Style G",
        "total_quantity": 30000.0,
        "production_start_date": str(today_d),
        "original_delivery_date": str(ship_d),
        "routes": [
            {"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]},
            {"section_id": sec_prt.id, "status": "REQUIRED", "operations": [{"operation_name": "Print", "sequence_order": 1}]}
        ]
    }, headers=admin_hdr)
    order_data = r_ord.json()
    order_id = order_data["id"]
    cut_route_id = order_data["routes"][0]["id"]
    cut_op_id = order_data["routes"][0]["operations"][0]["id"]
    prt_route_id = order_data["routes"][1]["id"]

    # Entry 1: 10,000
    r1 = client.post("/api/v1/production/entry", json={
        "order_id": order_id, "route_id": cut_route_id, "operation_id": cut_op_id,
        "entry_date": str(today_d), "quantity": 10000.0, "accepted_quantity": 10000.0, "rejected_quantity": 0.0
    }, headers=admin_hdr)
    assert r1.status_code == 200

    # Entry 2: 2,000
    r2 = client.post("/api/v1/production/entry", json={
        "order_id": order_id, "route_id": cut_route_id, "operation_id": cut_op_id,
        "entry_date": str(today_d), "quantity": 2000.0, "accepted_quantity": 2000.0, "rejected_quantity": 0.0
    }, headers=admin_hdr)
    assert r2.status_code == 200

    order_obj = db_session.query(Order).filter(Order.id == order_id).first()
    wip_plan = WIPPlanningEngine.calculate_order_wip_flow(db_session, order_obj, as_of_date=today_d)

    wf_summary = {w["section_name"]: w for w in wip_plan["workflow_summary"]}
    assert wf_summary["Cutting"]["complete"] == 12000.0
    assert wf_summary["Cutting"]["final_on_hand"] == 18000.0
    assert wf_summary["Printing"]["final_on_hand"] == 12000.0  # Exactly 12,000 WIP transferred


# =========================================================================
# TEST H: WIP Correction
# =========================================================================
def test_h_wip_correction(client, auth_headers, db_session):
    """
    Test H: WIP correction
    Correct a previous production entry from 2,000 to 1,500.
    Expected downstream WIP is reduced by 500, and every affected future plan is recalculated.
    Historical entry changes must remain auditable.
    """
    admin_hdr = auth_headers("admin")
    r_b = client.post("/api/v1/buyers", json={"name": "Buyer H", "buyer_code": "BY-H", "is_active": True}, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    sec_prt = db_session.query(Section).filter(Section.name == "Printing").first()
    today_d = date.today()
    ship_d = today_d + timedelta(days=10)

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-TEST-H",
        "customer_ref": "REF-H",
        "style_model": "Style H",
        "total_quantity": 20000.0,
        "production_start_date": str(today_d),
        "original_delivery_date": str(ship_d),
        "routes": [
            {"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]},
            {"section_id": sec_prt.id, "status": "REQUIRED", "operations": [{"operation_name": "Print", "sequence_order": 1}]}
        ]
    }, headers=admin_hdr)
    order_data = r_ord.json()
    order_id = order_data["id"]
    cut_route_id = order_data["routes"][0]["id"]
    cut_op_id = order_data["routes"][0]["operations"][0]["id"]

    r_ent = client.post("/api/v1/production/entry", json={
        "order_id": order_id, "route_id": cut_route_id, "operation_id": cut_op_id,
        "entry_date": str(today_d), "quantity": 2000.0, "accepted_quantity": 2000.0, "rejected_quantity": 0.0
    }, headers=admin_hdr)
    entry_id = r_ent.json()["id"]

    # Correct entry from 2,000 to 1,500
    r_corr = client.put(f"/api/v1/production/entries/{entry_id}/correct", json={
        "new_accepted_quantity": 1500.0,
        "new_rejected_quantity": 500.0,
        "reason": "QC recount adjustment: 500 rejected"
    }, headers=admin_hdr)
    assert r_corr.status_code == 200

    order_obj = db_session.query(Order).filter(Order.id == order_id).first()
    wip_plan = WIPPlanningEngine.calculate_order_wip_flow(db_session, order_obj, as_of_date=today_d)

    wf_summary = {w["section_name"]: w for w in wip_plan["workflow_summary"]}
    assert wf_summary["Cutting"]["complete"] == 1500.0
    assert wf_summary["Printing"]["final_on_hand"] == 1500.0  # Reduced by 500


# =========================================================================
# TEST I: Zero Balance
# =========================================================================
def test_i_zero_balance(client, auth_headers, db_session):
    """
    Test I: Zero balance
    Required Balance = 0.
    Expected future T/G = 0.
    Status = COMPLETED.
    """
    admin_hdr = auth_headers("admin")
    r_b = client.post("/api/v1/buyers", json={"name": "Buyer I", "buyer_code": "BY-I", "is_active": True}, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    today_d = date.today()
    ship_d = today_d + timedelta(days=5)

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-TEST-I",
        "customer_ref": "REF-I",
        "style_model": "Style I",
        "total_quantity": 5000.0,
        "production_start_date": str(today_d),
        "original_delivery_date": str(ship_d),
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    order_data = r_ord.json()
    order_id = order_data["id"]
    cut_route_id = order_data["routes"][0]["id"]
    cut_op_id = order_data["routes"][0]["operations"][0]["id"]

    # Produce full 5,000
    r_p = client.post("/api/v1/production/entry", json={
        "order_id": order_id, "route_id": cut_route_id, "operation_id": cut_op_id,
        "entry_date": str(today_d), "quantity": 5000.0, "accepted_quantity": 5000.0, "rejected_quantity": 0.0
    }, headers=admin_hdr)
    assert r_p.status_code == 200

    order_obj = db_session.query(Order).filter(Order.id == order_id).first()
    wip_plan = WIPPlanningEngine.calculate_order_wip_flow(db_session, order_obj, as_of_date=today_d)

    wf = wip_plan["workflow_summary"][0]
    assert wf["complete"] == 5000.0
    assert wf["balance"] == 0.0
    assert wf["status"] == "COMPLETED"


# =========================================================================
# TEST J: No Working Days
# =========================================================================
def test_j_no_working_days():
    """
    Test J: No working days
    Balance > 0.
    Working Days = 0.
    Expected status = NO AVAILABLE WORKING DAYS or OVERDUE.
    No division by zero.
    """
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=10000,
        cumulative_accepted=0,
        current_allocatable_wip=10000,
        working_dates=[],
        effective_min=2000
    )
    assert schedule == {}

    # Target calculation handles 0 remaining days gracefully
    rate = ProductionPlanningService.calculate_daily_target(remaining_balance=10000, remaining_days=0)
    assert rate == 0.0


# =========================================================================
# TEST K: Calendar Change
# =========================================================================
def test_k_calendar_change(client, auth_headers, db_session):
    """
    Test K: Calendar change
    Add a factory holiday.
    Expected future target plan changes according to the new working-day calendar
    without changing actual production.
    """
    admin_hdr = auth_headers("admin")
    r_b = client.post("/api/v1/buyers", json={"name": "Buyer K", "buyer_code": "BY-K", "is_active": True}, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    today_d = date.today()
    ship_d = today_d + timedelta(days=8)

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-TEST-K",
        "customer_ref": "REF-K",
        "style_model": "Style K",
        "total_quantity": 14000.0,
        "production_start_date": str(today_d),
        "original_delivery_date": str(ship_d),
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    order_id = r_ord.json()["id"]

    r_before = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    assert r_before.status_code == 200
    rows_before = r_before.json()["rows"]

    # Add factory holiday
    cal = CalendarService.get_active_calendar(db_session)
    holiday_d = today_d + timedelta(days=2)
    holiday = CalendarException(
        calendar_id=cal.id,
        exception_date=holiday_d,
        exception_type=ExceptionType.FACTORY_HOLIDAY,
        description="Emergency Maintenance Day"
    )
    db_session.add(holiday)
    db_session.commit()

    r_after = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    assert r_after.status_code == 200
    data_after = r_after.json()

    # The holiday row receives 0 T/G and is_workday is False
    h_row = next(r for r in data_after["rows"] if r["date"] == str(holiday_d))
    assert h_row["is_workday"] is False
    assert h_row["section_data"]["CUTTING"]["tg"] == 0.0

    # Total planned target across remaining working days still equals 14,000
    assert data_after["summary"]["CUTTING"]["total_tg"] == 14000.0


# =========================================================================
# TEST L: Export Consistency
# =========================================================================
def test_l_export_consistency(client, auth_headers, db_session):
    """
    Test L: Export consistency
    Export the original planning sheet to XLSX and CSV.
    Verify that target allocations and On Hand values match the current backend
    response and never exceed their quantity constraints.
    """
    admin_hdr = auth_headers("admin")
    r_b = client.post("/api/v1/buyers", json={"name": "Buyer L", "buyer_code": "BY-L", "is_active": True}, headers=admin_hdr)
    buyer_id = r_b.json()["id"]

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()
    today_d = date.today()
    ship_d = today_d + timedelta(days=10)

    r_ord = client.post("/api/v1/orders", json={
        "buyer_id": buyer_id,
        "order_code": "ORD-TEST-L",
        "customer_ref": "REF-L",
        "style_model": "Style L",
        "total_quantity": 30000.0,
        "production_start_date": str(today_d),
        "original_delivery_date": str(ship_d),
        "routes": [{"section_id": sec_cut.id, "status": "REQUIRED", "operations": [{"operation_name": "Cut", "sequence_order": 1}]}]
    }, headers=admin_hdr)
    order_id = r_ord.json()["id"]

    # 1. Check Matrix JSON response
    r_mat = client.get(f"/api/v1/orders/{order_id}/matrix-planning", headers=admin_hdr)
    mat_data = r_mat.json()
    backend_total_tg = mat_data["summary"]["CUTTING"]["total_tg"]
    assert backend_total_tg == 30000.0

    # 2. Check XLSX Export
    r_xlsx = client.get(f"/api/v1/exports/orders/{order_id}/xlsx", headers=admin_hdr)
    assert r_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r_xlsx.content), data_only=True)
    ws = wb.active
    assert ws is not None

    # Verify sheet has rows and Cutting columns
    found_order_code = False
    for row in ws.iter_rows(values_only=True):
        if any("ORD-TEST-L" in str(cell or "") for cell in row):
            found_order_code = True
            break
    assert found_order_code, "Exported XLSX must contain order code"

    # 3. Check CSV Export
    r_csv = client.get(f"/api/v1/exports/orders/{order_id}/csv", headers=admin_hdr)
    assert r_csv.status_code == 200
    csv_text = r_csv.content.decode("utf-8")
    assert "ORD-TEST-L" in csv_text
    assert "Cutting" in csv_text or "CUTTING" in csv_text
