import pytest
from datetime import date
from sqlalchemy.orm import Session
import openpyxl

from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus, OrderPriority
from app.models.route import OrderRoute, OrderOperation
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.models.entry import DailyProductionEntry
from app.models.user import User, UserRole
from app.services.order_service import OrderService
from app.services.calendar_service import CalendarService
from app.services.production_service import ProductionService
from app.services.wip_planning_engine import WIPPlanningEngine
from app.services.export_service import ExportService
from app.schemas.order import OrderCreate, OrderUpdate
from app.schemas.route import OrderRouteCreate
from app.schemas.entry import DailyProductionEntryCreate


@pytest.fixture
def test_user(db_session: Session):
    return db_session.query(User).filter(User.username == "admin_test").first()


@pytest.fixture
def test_buyer(db_session: Session):
    buyer = Buyer(
        name="BATA BANGLADESH",
        buyer_code="BATA-TEST-BD",
        contact_person="Planning Team",
        phone="+8801700000000",
        email="bata@example.com",
        is_active=True
    )
    db_session.add(buyer)
    db_session.commit()
    db_session.refresh(buyer)
    return buyer


@pytest.fixture
def factory_cal(db_session: Session):
    return db_session.query(FactoryCalendar).filter(FactoryCalendar.is_default == True).first()


def test_serial_workflow_order_creation_and_initial_wip(db_session: Session, test_user: User, test_buyer: Buyer, factory_cal: FactoryCalendar):
    """
    Requirements 1, 2, 3:
    Order Quantity: 70,000 pairs
    Workflow: 1. Cutting -> 2. Printing -> 3. Embosse -> 4. Sewing -> 5. Lasting
    Initially:
    Cutting On Hand = 70,000
    Printing On Hand = 0
    Embosse On Hand = 0
    Sewing On Hand = 0
    Lasting On Hand = 0
    """
    start_d = date(2026, 10, 7)
    ship_d = date(2026, 10, 20)

    routes = [
        OrderRouteCreate(serial_no=1, section_name="Cutting", transfer_rule="IMMEDIATE"),
        OrderRouteCreate(serial_no=2, section_name="Printing", transfer_rule="IMMEDIATE"),
        OrderRouteCreate(serial_no=3, section_name="Embosse", transfer_rule="IMMEDIATE"),
        OrderRouteCreate(serial_no=4, section_name="Sewing", transfer_rule="IMMEDIATE"),
        OrderRouteCreate(serial_no=5, section_name="Lasting", transfer_rule="IMMEDIATE"),
    ]

    order_in = OrderCreate(
        buyer_id=test_buyer.id,
        order_code="BATA-001-FLOW",
        customer_ref="BATA-001",
        style_model="Court Royale Pro",
        total_quantity=70000.0,
        production_start_date=start_d,
        original_delivery_date=ship_d,
        priority=OrderPriority.MEDIUM,
        routes=routes
    )

    order = OrderService.create_order(db_session, order_in, test_user.id)
    assert order.id is not None
    assert len(order.routes) == 5

    # Check serial ordering
    sorted_routes = sorted(order.routes, key=lambda r: r.serial_no or 0)
    expected_sections = ["Cutting", "Printing", "Embosse", "Sewing", "Lasting"]
    for idx, r in enumerate(sorted_routes):
        assert r.serial_no == idx + 1
        assert r.section.name == expected_sections[idx]

    # Calculate initial WIP flow plan
    plan = WIPPlanningEngine.calculate_order_wip_flow(db_session, order, as_of_date=start_d)
    assert plan["total_quantity"] == 70000.0
    assert plan["final_balance"] == 70000.0

    # Verify initial summary On Hand
    wf_summary = {w["section_name"]: w for w in plan["workflow_summary"]}
    assert wf_summary["Cutting"]["final_on_hand"] == 70000.0
    assert wf_summary["Cutting"]["complete"] == 0.0
    assert wf_summary["Printing"]["final_on_hand"] == 0.0
    assert wf_summary["Embosse"]["final_on_hand"] == 0.0
    assert wf_summary["Sewing"]["final_on_hand"] == 0.0
    assert wf_summary["Lasting"]["final_on_hand"] == 0.0


def test_serial_wip_flow_and_actual_transfer(db_session: Session, test_user: User, test_buyer: Buyer, factory_cal: FactoryCalendar):
    """
    Requirements 4, 5, 6, 7, 8, 9, 10, 11:
    1. Cutting produces 10,000 pairs:
       - Cutting Complete = 10,000
       - Cutting On Hand = 70,000 - 10,000 = 60,000
       - Printing Incoming WIP = 10,000
       - Printing On Hand = 10,000
    2. Printing produces 4,000 pairs:
       - Printing Complete = 4,000
       - Printing Closing On Hand = 10,000 - 4,000 = 6,000
       - Embosse receives 4,000 (Embosse On Hand = 4,000)
    3. Formula Verification:
       - On Hand(N) = Complete(N-1) - Complete(N)
       - On Hand(1) = Order Quantity - Complete(1)
    """
    start_d = date(2026, 10, 7)
    ship_d = date(2026, 10, 20)

    routes = [
        OrderRouteCreate(serial_no=1, section_name="Cutting", transfer_rule="IMMEDIATE"),
        OrderRouteCreate(serial_no=2, section_name="Printing", transfer_rule="IMMEDIATE"),
        OrderRouteCreate(serial_no=3, section_name="Embosse", transfer_rule="IMMEDIATE"),
        OrderRouteCreate(serial_no=4, section_name="Sewing", transfer_rule="IMMEDIATE"),
        OrderRouteCreate(serial_no=5, section_name="Lasting", transfer_rule="IMMEDIATE"),
    ]

    order_in = OrderCreate(
        buyer_id=test_buyer.id,
        order_code="BATA-002-TRANSFER",
        customer_ref="BATA-002",
        style_model="Apex Runner",
        total_quantity=70000.0,
        production_start_date=start_d,
        original_delivery_date=ship_d,
        priority=OrderPriority.HIGH,
        routes=routes
    )
    order = OrderService.create_order(db_session, order_in, test_user.id)
    sorted_routes = sorted(order.routes, key=lambda r: r.serial_no or 0)
    cutting_route = sorted_routes[0]
    printing_route = sorted_routes[1]
    embosse_route = sorted_routes[2]

    # Entry 1: Cutting produces 10,000
    entry1 = DailyProductionEntry(
        order_id=order.id,
        route_id=cutting_route.id,
        operation_id=cutting_route.operations[0].id,
        entry_date=start_d,
        quantity=10000.0,
        accepted_quantity=10000.0,
        rejected_quantity=0.0,
        entered_by_id=test_user.id
    )
    db_session.add(entry1)
    db_session.commit()

    # Verify after Cutting production
    cutting_avail = WIPPlanningEngine.get_available_wip_for_route(db_session, cutting_route)
    printing_avail = WIPPlanningEngine.get_available_wip_for_route(db_session, printing_route)
    assert cutting_avail == 60000.0  # 70,000 - 10,000
    assert printing_avail == 10000.0  # 10,000 received from cutting

    # Entry 2: Printing produces 4,000
    entry2 = DailyProductionEntry(
        order_id=order.id,
        route_id=printing_route.id,
        operation_id=printing_route.operations[0].id,
        entry_date=start_d,
        quantity=4000.0,
        accepted_quantity=4000.0,
        rejected_quantity=0.0,
        entered_by_id=test_user.id
    )
    db_session.add(entry2)
    db_session.commit()

    # Verify after Printing production
    printing_avail_after = WIPPlanningEngine.get_available_wip_for_route(db_session, printing_route)
    embosse_avail = WIPPlanningEngine.get_available_wip_for_route(db_session, embosse_route)
    assert printing_avail_after == 6000.0  # 10,000 - 4,000 = 6,000
    assert embosse_avail == 4000.0  # 4,000 received from printing

    # Check full WIP plan structure
    plan = WIPPlanningEngine.calculate_order_wip_flow(db_session, order, as_of_date=start_d)
    wf_summary = {w["section_name"]: w for w in plan["workflow_summary"]}
    assert wf_summary["Cutting"]["complete"] == 10000.0
    assert wf_summary["Cutting"]["final_on_hand"] == 60000.0
    assert wf_summary["Printing"]["complete"] == 4000.0
    assert wf_summary["Printing"]["final_on_hand"] == 6000.0
    assert wf_summary["Embosse"]["complete"] == 0.0
    assert wf_summary["Embosse"]["final_on_hand"] == 4000.0


def test_bangladesh_factory_calendar_and_target_recalculation(db_session: Session, test_user: User, test_buyer: Buyer, factory_cal: FactoryCalendar):
    """
    Requirements 15, 16, 17, 18, 19, 20, 21:
    - Friday is OFF by default.
    - Remaining working days counts production-allowed days only.
    - CEILING(Remaining Required / Remaining Working Days).
    - Custom holiday excludes that date and recalculates T/G upwards.
    - Target changes dynamically when calendar changes.
    """
    start_d = date(2026, 10, 7)
    ship_d = date(2026, 10, 16)

    # Oct 7 (Wed) to Oct 16 (Fri) = 10 days, 2 Fridays off (Oct 9 & 16) = 8 working days.
    work_days_before, _ = CalendarService.get_remaining_working_days(db_session, start_d, ship_d, factory_cal.id, as_of_date=start_d)
    assert work_days_before == 8

    # Create order: 32,000 pairs over 8 working days => Daily T/G = 32,000 / 8 = 4,000
    order_in = OrderCreate(
        buyer_id=test_buyer.id,
        order_code="BATA-003-CALENDAR",
        customer_ref="BATA-003",
        style_model="Starlight Jogger",
        total_quantity=32000.0,
        production_start_date=start_d,
        original_delivery_date=ship_d,
        priority=OrderPriority.HIGH,
        routes=[
            OrderRouteCreate(serial_no=1, section_name="Cutting"),
            OrderRouteCreate(serial_no=2, section_name="Lasting")
        ]
    )
    order = OrderService.create_order(db_session, order_in, test_user.id)

    plan_before = WIPPlanningEngine.calculate_order_wip_flow(db_session, order, as_of_date=start_d)
    assert plan_before["remaining_working_days"] == 8
    # Section 1 target on day 1 should be 32,000 / 8 = 4,000
    first_row = plan_before["rows"][0]
    assert first_row["tg"] == 4000.0

    # Add custom factory holiday on 2026-10-12 (Monday)
    holiday = CalendarException(
        calendar_id=factory_cal.id,
        exception_date=date(2026, 10, 12),
        exception_type=ExceptionType.FACTORY_HOLIDAY,
        description="Boiler Inspection Holiday"
    )
    db_session.add(holiday)
    db_session.commit()

    # Now working days = 7.
    # New target = CEILING(32,000 / 7) = CEILING(4571.428) = 4,572.
    work_days_after, _ = CalendarService.get_remaining_working_days(db_session, start_d, ship_d, factory_cal.id, as_of_date=start_d)
    assert work_days_after == 7

    plan_after = WIPPlanningEngine.calculate_order_wip_flow(db_session, order, as_of_date=start_d)
    assert plan_after["remaining_working_days"] == 7
    first_row_after = plan_after["rows"][0]
    assert first_row_after["tg"] == 4572.0


def test_production_entry_wip_validation(db_session: Session, test_user: User, test_buyer: Buyer):
    """
    Requirement 28:
    A section cannot produce more than its available WIP without override.
    Printing On Hand = 5,000. User enters 6,000 -> Rejected!
    """
    start_d = date(2026, 10, 7)
    ship_d = date(2026, 10, 20)

    routes = [
        OrderRouteCreate(serial_no=1, section_name="Cutting"),
        OrderRouteCreate(serial_no=2, section_name="Printing"),
        OrderRouteCreate(serial_no=3, section_name="Lasting"),
    ]
    order_in = OrderCreate(
        buyer_id=test_buyer.id,
        order_code="BATA-004-VALIDATION",
        customer_ref="BATA-004",
        style_model="Urban Street",
        total_quantity=50000.0,
        production_start_date=start_d,
        original_delivery_date=ship_d,
        routes=routes
    )
    order = OrderService.create_order(db_session, order_in, test_user.id)
    sorted_routes = sorted(order.routes, key=lambda r: r.serial_no or 0)
    cutting_route = sorted_routes[0]
    printing_route = sorted_routes[1]

    # Cutting produces 5,000
    db_session.add(DailyProductionEntry(
        order_id=order.id,
        route_id=cutting_route.id,
        operation_id=cutting_route.operations[0].id,
        entry_date=start_d,
        quantity=5000.0,
        accepted_quantity=5000.0,
        entered_by_id=test_user.id
    ))
    db_session.commit()

    # Printing has 5,000 available. Trying to enter 6,000 should raise HTTPException 400
    entry_in = DailyProductionEntryCreate(
        order_id=order.id,
        route_id=printing_route.id,
        operation_id=printing_route.operations[0].id,
        entry_date=start_d,
        quantity=6000.0,
        accepted_quantity=6000.0,
        rejected_quantity=0.0,
        is_override=False
    )

    with pytest.raises(Exception) as exc_info:
        ProductionService.create_production_entry(db_session, entry_in, test_user.id)
    assert "Insufficient" in str(exc_info.value) or "exceeds" in str(exc_info.value)


def test_target_never_creates_wip_and_bottleneck_detection(db_session: Session, test_user: User, test_buyer: Buyer):
    """
    Requirements 22, 23, 24, 36:
    - Target does NOT transfer or create WIP.
    - WIP Shortage status detected when T/G > On Hand.
    - Bottleneck detected where downstream flow is constrained.
    """
    start_d = date(2026, 10, 7)
    ship_d = date(2026, 10, 20)

    routes = [
        OrderRouteCreate(serial_no=1, section_name="Cutting"),
        OrderRouteCreate(serial_no=2, section_name="Printing"),
        OrderRouteCreate(serial_no=3, section_name="Lasting"),
    ]
    order_in = OrderCreate(
        buyer_id=test_buyer.id,
        order_code="BATA-005-BOTTLENECK",
        customer_ref="BATA-005",
        style_model="Pro Court",
        total_quantity=60000.0,
        production_start_date=start_d,
        original_delivery_date=ship_d,
        routes=routes
    )
    order = OrderService.create_order(db_session, order_in, test_user.id)
    sorted_routes = sorted(order.routes, key=lambda r: r.serial_no or 0)
    cutting_route = sorted_routes[0]

    # Cutting produces only 2,000 (even though target was e.g. 5,000)
    db_session.add(DailyProductionEntry(
        order_id=order.id,
        route_id=cutting_route.id,
        operation_id=cutting_route.operations[0].id,
        entry_date=start_d,
        quantity=2000.0,
        accepted_quantity=2000.0,
        entered_by_id=test_user.id
    ))
    db_session.commit()

    plan = WIPPlanningEngine.calculate_order_wip_flow(db_session, order, as_of_date=start_d)
    # Printing receives exactly 2,000, NOT the planned target!
    wf_summary = {w["section_name"]: w for w in plan["workflow_summary"]}
    assert wf_summary["Printing"]["final_on_hand"] == 2000.0

    # Bottleneck detection should report where WIP is waiting
    assert plan["bottleneck_process"] is not None
    assert plan["wip_waiting_quantity"] >= 0


def test_wip_flow_excel_5_sheet_export(db_session: Session, test_user: User, test_buyer: Buyer):
    """
    Requirements 43 & 44:
    Export to XLSX must contain 5 sheets:
    - Sheet 1: WIP Flow Plan
    - Sheet 2: Workflow Summary
    - Sheet 3: Factory Calendar
    - Sheet 4: Production Entries
    - Sheet 5: Order Details
    """
    routes = [
        OrderRouteCreate(serial_no=1, section_name="Cutting"),
        OrderRouteCreate(serial_no=2, section_name="Printing"),
        OrderRouteCreate(serial_no=3, section_name="Lasting"),
    ]
    order_in = OrderCreate(
        buyer_id=test_buyer.id,
        order_code="BATA-006-EXPORT",
        customer_ref="BATA-006",
        style_model="Export Model",
        total_quantity=50000.0,
        production_start_date=date(2026, 10, 7),
        original_delivery_date=date(2026, 10, 20),
        routes=routes
    )
    order = OrderService.create_order(db_session, order_in, test_user.id)

    stream = ExportService.generate_wip_flow_xlsx(db_session, order)
    wb = openpyxl.load_workbook(stream)
    sheet_names = wb.sheetnames

    assert "WIP Flow Plan" in sheet_names
    assert "Workflow Summary" in sheet_names
    assert "Factory Calendar" in sheet_names
    assert "Production Entries" in sheet_names
    assert "Order Details" in sheet_names

    # Verify Sheet 1 headers
    ws_plan = wb["WIP Flow Plan"]
    headers = [cell.value for cell in ws_plan[4]]
    expected_headers = ["Date", "Serial", "Section", "T/G", "Opening On Hand", "Incoming WIP", "Actual", "Complete", "Closing On Hand", "Balance", "Remaining Working Days", "Status"]
    for h in expected_headers:
        assert h in headers
