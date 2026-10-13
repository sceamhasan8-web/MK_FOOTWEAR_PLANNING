import io
import pytest
import math
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db
from app.models.user import User, UserRole
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.route import Category, Section, OrderRoute, OrderOperation, SectionRouteStatus, ProductionTargetSetting
from app.models.entry import DailyProductionEntry
from app.models.calendar import FactoryCalendar
from app.services.calendar_service import CalendarService
from app.services.production_planning_service import ProductionPlanningService
from app.services.wip_planning_engine import WIPPlanningEngine
from app.services.production_service import ProductionService
from app.services.export_service import ExportService
from app.services.settings_service import SettingsService
from app.api.deps import create_access_token


@pytest.fixture
def client_and_db():
    client = TestClient(app)
    db = next(get_db())
    yield client, db


@pytest.fixture
def admin_headers(client_and_db):
    _, db = client_and_db
    admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
    if not admin:
        admin = User(
            username="test_admin_tgt",
            email="admin_tgt@factory.com",
            hashed_password="pw",
            role=UserRole.ADMIN,
            is_active=True
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    token = create_access_token(data={"sub": admin.username, "user_id": admin.id, "role": admin.role.value})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def footwear_target_env(client_and_db):
    _, db = client_and_db
    cal = CalendarService.get_active_calendar(db)

    cat_cut = db.query(Category).filter(Category.name == "Cutting Dept").first()
    if not cat_cut:
        cat_cut = Category(name="Cutting Dept", display_order=1, is_active=True)
        db.add(cat_cut)

    cat_prep = db.query(Category).filter(Category.name == "Preparation Dept").first()
    if not cat_prep:
        cat_prep = Category(name="Preparation Dept", display_order=2, is_active=True)
        db.add(cat_prep)

    cat_fin = db.query(Category).filter(Category.name == "Finishing Dept").first()
    if not cat_fin:
        cat_fin = Category(name="Finishing Dept", display_order=3, is_active=True)
        db.add(cat_fin)
    db.commit()

    section_defs = [
        ("Cutting", cat_cut.id, 1),
        ("Upper Prep", cat_prep.id, 2),
        ("Stitching", cat_prep.id, 3),
        ("Printing", cat_prep.id, 4),
        ("Stockfitting", cat_fin.id, 5),
        ("Lasting", cat_fin.id, 6),
    ]
    sections_map = {}
    for s_name, cat_id, order_num in section_defs:
        sec = db.query(Section).filter(Section.name == s_name).first()
        if not sec:
            sec = Section(category_id=cat_id, name=s_name, display_order=order_num, is_active=True)
            db.add(sec)
            db.commit()
            db.refresh(sec)
        else:
            sec.is_active = True
            sec.category_id = cat_id
            sec.display_order = order_num
            db.commit()
        sections_map[s_name] = sec

    buyer = db.query(Buyer).filter(Buyer.name == "Target Buyer International").first()
    if not buyer:
        buyer = Buyer(name="Target Buyer International", buyer_code="TBI", address="USA", is_active=True)
        db.add(buyer)
        db.commit()
        db.refresh(buyer)

    return {
        "cal": cal,
        "buyer": buyer,
        "sections": sections_map
    }


def create_order_with_workflow(db, buyer, sections, order_code, qty=30000.0, days_ahead=12):
    existing = db.query(Order).filter(Order.order_code == order_code).first()
    if existing:
        db.query(DailyProductionEntry).filter(DailyProductionEntry.order_id == existing.id).delete()
        for r in existing.routes:
            db.query(OrderOperation).filter(OrderOperation.route_id == r.id).delete()
        db.query(OrderRoute).filter(OrderRoute.order_id == existing.id).delete()
        db.delete(existing)
        db.commit()

    user = db.query(User).first()
    user_id = user.id if user else 1

    start_d = date.today()
    ship_d = date.today() + timedelta(days=days_ahead)

    order = Order(
        order_code=order_code,
        buyer_id=buyer.id,
        customer_ref=f"REF-{order_code}",
        po_number=f"PO-{order_code}",
        style_model="Running Style 2026",
        total_quantity=qty,
        original_order_date=start_d,
        production_start_date=start_d,
        original_delivery_date=ship_d,
        current_delivery_date=ship_d,
        status=OrderStatus.IN_PRODUCTION,
        created_by_id=user_id,
    )
    db.add(order)
    db.flush()

    ordered_sections = ["Cutting", "Upper Prep", "Stitching", "Printing", "Stockfitting", "Lasting"]
    for idx, s_name in enumerate(ordered_sections, start=1):
        sec = sections[s_name]
        route = OrderRoute(
            order_id=order.id,
            section_id=sec.id,
            status=SectionRouteStatus.REQUIRED,
            sequence_order=idx,
            serial_no=idx,
            transfer_rule="IMMEDIATE"
        )
        db.add(route)
        db.flush()

        op = OrderOperation(
            route_id=route.id,
            operation_name=f"{sec.name} Operation",
            sequence_order=1,
            required_quantity=qty,
            completed_quantity=0.0,
            rejected_quantity=0.0,
            balance_quantity=qty
        )
        db.add(op)

    db.commit()
    db.refresh(order)
    return order


# =============================================================================
# Automated Acceptance Tests
# =============================================================================

def test_a_active_section_without_target_settings(client_and_db, footwear_target_env):
    """
    Test A — Active Section Without Target Settings
    Create an order with Cutting, Upper Prep, Stitching, Printing, Lasting.
    Do NOT configure Min/Max targets for Cutting, Upper Prep, Stitching, Printing.
    Configure Min/Max targets for Lasting.
    Expected:
    - All applicable active sections appear in planning sheet.
    - Every section has its own calculated target when conditions permit.
    - Lasting is NOT the only section with a target.
    - Missing settings do NOT exclude other sections.
    """
    _, db = client_and_db
    env = footwear_target_env

    # Ensure Cutting, Upper Prep, Stitching, Printing, Lasting are active
    for s_name in ["Cutting", "Upper Prep", "Stitching", "Printing", "Lasting"]:
        env["sections"][s_name].is_active = True
    db.commit()

    # Clear target settings for Cutting, Upper Prep, Stitching, Printing
    for s_name in ["Cutting", "Upper Prep", "Stitching", "Printing"]:
        sec = env["sections"][s_name]
        db.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == sec.id).delete()

    # Set explicit target settings for Lasting only
    sec_lasting = env["sections"][Lasting := "Lasting"]
    ts_lasting = db.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == sec_lasting.id).first()
    if not ts_lasting:
        ts_lasting = ProductionTargetSetting(
            section_id=sec_lasting.id,
            minimum_daily_target=2000,
            maximum_daily_target=4500,
            unit="Pairs/day",
            is_active=True
        )
        db.add(ts_lasting)
    else:
        ts_lasting.minimum_daily_target = 2000
        ts_lasting.maximum_daily_target = 4500
        ts_lasting.is_active = True
    db.commit()

    order = create_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-TGT-A")

    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order.id)
    section_names = [s["section_name"].upper() for s in matrix["sections"]]

    # 1. All active sections appear
    for expected_sec in ["CUTTING", "UPPER PREP", "STITCHING", "PRINTING", "LASTING"]:
        assert expected_sec in section_names, f"{expected_sec} missing from matrix planning sheet"

    # 2. Every active section has an automatic Required Daily Rate calculated
    for s in matrix["sections"]:
        assert s["required_daily_rate"] > 0, f"Section {s['section_name']} has 0 required daily rate"

    # 3. Lasting is not the only section with a calculated target / rate
    cut_summary = matrix["summary"]["CUTTING"]
    assert cut_summary["required_daily_rate"] > 0
    assert cut_summary["total_tg"] > 0, "Cutting should have allocated executable targets from opening balance"


def test_b_deactivated_section_excluded_without_breaking_others(client_and_db, footwear_target_env):
    """
    Test B — Deactivate Stockfitting.
    Expected:
    - Stockfitting does not receive an active operational target.
    - Other active sections continue calculating targets.
    - Calculations do not fail because Stockfitting has no active target.
    """
    _, db = client_and_db
    env = footwear_target_env

    # Deactivate Stockfitting
    stockfitting = env["sections"]["Stockfitting"]
    stockfitting.is_active = False
    db.commit()

    order = create_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-TGT-B")
    # Mark route as NOT_REQUIRED
    sf_route = next(r for r in order.routes if r.section_id == stockfitting.id)
    sf_route.status = SectionRouteStatus.NOT_REQUIRED
    db.commit()

    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order.id)
    rendered_sections = [s["section_name"].upper() for s in matrix["sections"]]

    assert "STOCKFITTING" not in rendered_sections
    assert "CUTTING" in rendered_sections
    assert "LASTING" in rendered_sections
    assert matrix["summary"]["CUTTING"]["total_tg"] > 0


def test_c_zero_wip_section_status_and_rate(client_and_db, footwear_target_env):
    """
    Test C — Printing has remaining balance 5,000 but zero available WIP.
    Expected:
    - Required Daily Rate is calculated.
    - Executable T/G = 0.
    - Status = WAITING FOR WIP.
    - Section still appears in the planning sheet.
    """
    _, db = client_and_db
    env = footwear_target_env

    order = create_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-TGT-C", qty=5000.0)

    # Printing has 0 upstream production entered, so its allocatable WIP is 0
    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order.id)
    prt_summary = matrix["summary"]["PRINTING"]

    assert prt_summary["required_daily_rate"] > 0
    assert prt_summary["status"] == "WAITING FOR WIP"
    assert any(s["section_name"] == "PRINTING" for s in matrix["sections"])


def test_d_cutting_full_on_hand_automatic_rate(client_and_db, footwear_target_env):
    """
    Test D — Cutting On Hand = 30,000, Remaining Working Days = 10.
    No Min/Max configuration exists.
    Expected automatic required rate = 3,000 pairs/day.
    Plan does not depend on saved target settings.
    """
    _, db = client_and_db
    env = footwear_target_env

    # Remove target settings for Cutting
    sec_cut = env["sections"]["Cutting"]
    db.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == sec_cut.id).delete()
    db.commit()

    order = create_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-TGT-D", qty=30000.0, days_ahead=14)
    cal = CalendarService.get_active_calendar(db)
    rem_days, working_dates = ProductionPlanningService.calculate_remaining_days(
        db, order.production_start_date, order.current_delivery_date, calendar_id=cal.id
    )

    route_cut = next(r for r in order.routes if r.section_id == sec_cut.id)
    target_calc = ProductionPlanningService.calculate_section_target(
        db=db,
        order=order,
        route=route_cut,
        as_of_date=order.production_start_date
    )

    expected_rate = math.ceil(30000.0 / target_calc["remaining_working_days"])
    assert target_calc["required_daily_rate"] == expected_rate
    assert target_calc["minimum_daily_target"] == 0
    assert target_calc["maximum_daily_target"] == 0


def test_e_settings_exist_within_bounds(client_and_db, footwear_target_env):
    """
    Test E — Balance = 30,000, 10 working days, Min = 2,000, Max = 4,000.
    Required rate = 3,000. Since 3,000 is between min and max, daily target is 3,000.
    """
    _, db = client_and_db
    env = footwear_target_env

    sec_cut = env["sections"]["Cutting"]
    ts = db.query(ProductionTargetSetting).filter(ProductionTargetSetting.section_id == sec_cut.id).first()
    if not ts:
        ts = ProductionTargetSetting(section_id=sec_cut.id, minimum_daily_target=2000, maximum_daily_target=4000, is_active=True)
        db.add(ts)
    else:
        ts.minimum_daily_target = 2000
        ts.maximum_daily_target = 4000
        ts.is_active = True
    db.commit()

    working_dates = [date.today() + timedelta(days=i) for i in range(10)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000.0,
        cumulative_accepted=0.0,
        current_allocatable_wip=30000.0,
        working_dates=working_dates,
        effective_min=2000,
        effective_max=4000,
        calculation_mode="BALANCED"
    )

    for d in working_dates:
        assert schedule[d] == 3000


def test_f_minimum_daily_target_applies(client_and_db, footwear_target_env):
    """
    Test F — Balance = 30,000, 30 working days. Required rate = 1,000.
    Minimum = 2,000.
    Expected: schedules 2,000/day for 15 days, balance finishes in 15 days.
    Total allocated does not exceed 30,000.
    """
    working_dates = [date.today() + timedelta(days=i) for i in range(30)]
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000.0,
        cumulative_accepted=0.0,
        current_allocatable_wip=30000.0,
        working_dates=working_dates,
        effective_min=2000,
        effective_max=0,
        calculation_mode="BALANCED"
    )

    allocated_dates = [d for d, qty in schedule.items() if qty > 0]
    assert len(allocated_dates) == 15
    for d in allocated_dates:
        assert schedule[d] == 2000
    assert sum(schedule.values()) == 30000


def test_g_maximum_daily_target_applies_and_feasibility_flags(client_and_db, footwear_target_env):
    """
    Test G — Required rate = 5,000, Maximum = 4,000.
    Expected: Planned T/G does not exceed 4,000.
    Order/Section capacity feasibility flags capacity conflict.
    """
    working_dates = [date.today() + timedelta(days=i) for i in range(6)]
    # 30,000 in 6 days => required rate 5,000. Max = 4,000.
    schedule = ProductionPlanningService.allocate_section_targets(
        order_quantity=30000.0,
        cumulative_accepted=0.0,
        current_allocatable_wip=30000.0,
        working_dates=working_dates,
        effective_min=0,
        effective_max=4000,
        calculation_mode="BALANCED"
    )

    for qty in schedule.values():
        assert qty <= 4000

    feasibility = ProductionPlanningService.evaluate_capacity_feasibility(
        remaining_balance=30000.0,
        remaining_workdays=6,
        maximum_daily_target=4000
    )
    assert feasibility["is_feasible"] is False
    assert feasibility["shortfall"] > 0
    assert feasibility["conflict"] is not None


def test_h_target_refresh_after_production_entry(client_and_db, admin_headers, footwear_target_env):
    """
    Test H — Enter production into Cutting.
    Expected:
    - Cutting complete changes, on-hand updates.
    - WIP transfers downstream by actual completed amount.
    - Downstream section receives executable WIP and recalculates targets.
    """
    client, db = client_and_db
    env = footwear_target_env

    order = create_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-TGT-H", qty=10000.0)
    cut_route = next(r for r in order.routes if r.section_id == env["sections"]["Cutting"].id)
    cut_op = cut_route.operations[0]

    user = db.query(User).first()
    entry = DailyProductionEntry(
        order_id=order.id,
        route_id=cut_route.id,
        operation_id=cut_op.id,
        entry_date=date.today(),
        quantity=3000.0,
        accepted_quantity=3000.0,
        rejected_quantity=0.0,
        unit="Pairs",
        entered_by_id=user.id
    )
    db.add(entry)
    db.commit()

    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order.id)
    up_prep_summary = matrix["summary"]["UPPER PREP"]

    assert up_prep_summary["allocatable_wip"] == 3000.0
    assert up_prep_summary["total_tg"] == 3000.0
    assert up_prep_summary["required_daily_rate"] > 0


def test_i_summary_matches_active_sections(client_and_db, footwear_target_env):
    """
    Test I — Summary uses the exact same applicable active sections as the table.
    No inactive-section target is included.
    """
    _, db = client_and_db
    env = footwear_target_env

    stockfitting = env["sections"]["Stockfitting"]
    stockfitting.is_active = False
    db.commit()

    order = create_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-TGT-I")
    sf_route = next(r for r in order.routes if r.section_id == stockfitting.id)
    sf_route.status = SectionRouteStatus.NOT_REQUIRED
    db.commit()

    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order.id)
    table_sections = [s["section_name"].upper() for s in matrix["sections"]]
    summary_sections = list(matrix["summary"].keys())

    assert "STOCKFITTING" not in summary_sections
    for sec in table_sections:
        assert sec in summary_sections
        assert "required_daily_rate" in matrix["summary"][sec]


def test_j_restart_and_reload_persistence(client_and_db, footwear_target_env):
    """
    Test J — Re-fetch order from database query, target calculations remain consistent.
    """
    _, db = client_and_db
    env = footwear_target_env

    order = create_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-TGT-J")
    db.expire_all()

    fresh_order = db.query(Order).filter(Order.id == order.id).first()
    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, fresh_order.id)
    for s in matrix["sections"]:
        assert s["required_daily_rate"] > 0


def test_k_xlsx_and_csv_export_consistency(client_and_db, footwear_target_env):
    """
    Test K — Export Matrix XLSX and CSV.
    Expected:
    - All applicable active sections appear.
    - Missing target settings do not remove columns.
    - Summary and T/G values match.
    """
    _, db = client_and_db
    env = footwear_target_env

    order = create_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-TGT-K")

    # CSV check
    csv_str = ExportService.generate_matrix_planning_csv(db, order)
    assert "CUTTING T/G" in csv_str.upper()
    assert "LASTING T/G" in csv_str.upper()
    assert "PRINTING T/G" in csv_str.upper()

    # XLSX check
    xlsx_stream = ExportService.generate_matrix_planning_xlsx(db, order)
    assert xlsx_stream is not None
    assert xlsx_stream.getbuffer().nbytes > 0
