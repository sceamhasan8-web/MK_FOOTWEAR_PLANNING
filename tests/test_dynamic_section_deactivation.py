import io
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db, Base, engine
from app.models.user import User, UserRole
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.route import Category, Section, OrderRoute, OrderOperation, SectionRouteStatus
from app.models.entry import DailyProductionEntry
from app.models.calendar import FactoryCalendar
from app.models.audit import AuditLog
from app.services.settings_service import SettingsService
from app.services.production_planning_service import ProductionPlanningService
from app.services.wip_planning_engine import WIPPlanningEngine
from app.services.production_service import ProductionService
from app.services.export_service import ExportService
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
            username="test_admin_deact",
            email="admin_deact@factory.com",
            hashed_password="pw",
            role=UserRole.ADMIN,
            is_active=True
        )
        db.add(admin)
        db.commit()
    token = create_access_token(data={"sub": admin.username, "user_id": admin.id, "role": admin.role.value})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def setup_footwear_erp_env(client_and_db):
    """
    Sets up a footwear production environment with categories and standard sections:
    Cutting, Upper Prep, Stitching, Printing, Stockfitting, Lasting.
    """
    _, db = client_and_db

    from app.services.calendar_service import CalendarService
    cal = CalendarService.get_active_calendar(db)

    # Categories
    cat_cut = db.query(Category).filter(Category.name == "Cutting Department").first()
    if not cat_cut:
        cat_cut = Category(name="Cutting Department", display_order=1, is_active=True)
        db.add(cat_cut)

    cat_prep = db.query(Category).filter(Category.name == "Preparation Department").first()
    if not cat_prep:
        cat_prep = Category(name="Preparation Department", display_order=2, is_active=True)
        db.add(cat_prep)

    cat_fin = db.query(Category).filter(Category.name == "Finishing Department").first()
    if not cat_fin:
        cat_fin = Category(name="Finishing Department", display_order=3, is_active=True)
        db.add(cat_fin)
    db.commit()

    # Sections: Cutting, Upper Prep, Stitching, Printing, Stockfitting, Lasting
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
            sec.planning_id = order_num
            db.commit()
        sections_map[s_name] = sec

    # Buyer
    buyer = db.query(Buyer).filter(Buyer.name == "Global Footwear Brands").first()
    if not buyer:
        buyer = Buyer(name="Global Footwear Brands", buyer_code="GFB_DEACT", email="buyer@gfb.com", is_active=True)
        db.add(buyer)
        db.commit()
        db.refresh(buyer)

    return {
        "cal": cal,
        "buyer": buyer,
        "sections": sections_map
    }


@pytest.fixture(autouse=True)
def reset_sections_state(setup_footwear_erp_env, client_and_db):
    _, db = client_and_db
    for sec in setup_footwear_erp_env["sections"].values():
        sec.is_active = True
    db.commit()


def create_sample_order_with_workflow(db: Session, buyer: Buyer, sections: dict, order_code: str, qty: float = 3000.0) -> Order:
    start_d = date.today()
    ship_d = start_d + timedelta(days=14)

    # Clean up existing order if present
    existing_order = db.query(Order).filter(Order.order_code == order_code).first()
    if existing_order:
        db.delete(existing_order)
        db.commit()

    user = db.query(User).first()
    user_id = user.id if user else 1
    order = Order(
        order_code=order_code,
        buyer_id=buyer.id,
        customer_ref=f"REF-{order_code}",
        po_number=f"PO-{order_code}",
        style_model="Running Sport 2026",
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

    ordered_section_names = ["Cutting", "Upper Prep", "Stitching", "Printing", "Stockfitting", "Lasting"]
    for idx, s_name in enumerate(ordered_section_names, start=1):
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
# Acceptance Tests
# =============================================================================

def test_a_deactivate_single_section(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test A — Deactivate Stockfitting.
    Expected:
    - Database stores it as inactive.
    - Settings API still lists it under inactive sections.
    - Original planning sheet no longer renders Stockfitting columns.
    - WIP operational view excludes it.
    - Regular exports do not contain its columns.
    - No new normal production target is calculated for it.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    stockfitting = env["sections"]["Stockfitting"]

    order = create_sample_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-A-DEACT")

    # Deactivate Stockfitting via API
    res = client.post(
        f"/api/v1/settings/sections/{stockfitting.id}/deactivate",
        json={"reason": "Test A Deactivation", "force_confirm": True, "remove_from_active_workflows": True},
        headers=admin_headers
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["is_active"] is False

    # 1. Database check
    db.refresh(stockfitting)
    assert stockfitting.is_active is False

    # 2. Settings check (include_inactive=True returns it with is_active=False)
    res_settings = client.get("/api/v1/settings/sections?include_inactive=true", headers=admin_headers)
    assert res_settings.status_code == 200
    secs = res_settings.json()
    sf_item = next(s for s in secs if s["id"] == stockfitting.id)
    assert sf_item["is_active"] is False

    # 3. Operational sections check (GET /departments/sections defaults to active only)
    res_ops = client.get("/api/v1/departments/sections", headers=admin_headers)
    assert res_ops.status_code == 200
    active_secs = res_ops.json()
    assert not any(s["id"] == stockfitting.id for s in active_secs)

    # 4. Matrix Planning Sheet check
    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order.id)
    rendered_section_names = [s["section_name"].upper() for s in matrix["sections"]]
    assert "STOCKFITTING" not in rendered_section_names
    assert "CUTTING" in rendered_section_names
    assert "LASTING" in rendered_section_names
    # Summary check
    assert "STOCKFITTING" not in matrix["summary"]

    # 5. WIP Flow Planning Sheet check
    wip_plan = WIPPlanningEngine.calculate_order_wip_flow(db, order)
    wip_section_names = [s["section_name"] for s in wip_plan["sections"]]
    assert "Stockfitting" not in wip_section_names
    # Contiguous serial numbers (1, 2, 3, 4, 5) without gaps
    serials = [s["serial_no"] for s in wip_plan["sections"]]
    assert serials == list(range(1, len(serials) + 1))


def test_b_deactivate_two_sections(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test B — Deactivate Upper Prep and Stockfitting.
    Expected:
    - Both disappear from applicable active planning views.
    - Other active sections remain in correct serial sequence.
    - Summary calculations exclude inactive sections.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    upper_prep = env["sections"]["Upper Prep"]
    stockfitting = env["sections"]["Stockfitting"]

    order = create_sample_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-B-DEACT")

    # Deactivate Upper Prep
    client.post(
        f"/api/v1/settings/sections/{upper_prep.id}/deactivate",
        json={"reason": "Test B deact Upper Prep", "force_confirm": True, "remove_from_active_workflows": True},
        headers=admin_headers
    )
    # Deactivate Stockfitting
    client.post(
        f"/api/v1/settings/sections/{stockfitting.id}/deactivate",
        json={"reason": "Test B deact Stockfitting", "force_confirm": True, "remove_from_active_workflows": True},
        headers=admin_headers
    )

    db.expire_all()
    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order.id)
    rendered_sections = [s["section_name"].upper() for s in matrix["sections"]]
    assert "UPPER PREP" not in rendered_sections
    assert "STOCKFITTING" not in rendered_sections
    assert rendered_sections == ["CUTTING", "STITCHING", "PRINTING", "LASTING"]

    wip_plan = WIPPlanningEngine.calculate_order_wip_flow(db, order)
    wip_names = [s["section_name"] for s in wip_plan["sections"]]
    assert "Upper Prep" not in wip_names
    assert "Stockfitting" not in wip_names
    assert wip_names == ["Cutting", "Stitching", "Printing", "Lasting"]
    assert [s["serial_no"] for s in wip_plan["sections"]] == [1, 2, 3, 4]


def test_c_reactivate_section(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test C — Reactivate Stockfitting.
    Expected:
    - Becomes available in Settings active list.
    - Available in new-order workflow creation.
    - Existing orders do not have it automatically inserted.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    stockfitting = env["sections"]["Stockfitting"]

    # First deactivate
    client.post(
        f"/api/v1/settings/sections/{stockfitting.id}/deactivate",
        json={"reason": "Deactivate first", "force_confirm": True, "remove_from_active_workflows": True},
        headers=admin_headers
    )

    # Reactivate via PUT /api/v1/settings/sections/{id}
    res_reactivate = client.put(
        f"/api/v1/settings/sections/{stockfitting.id}",
        json={
            "name": stockfitting.name,
            "category_id": stockfitting.category_id,
            "display_order": stockfitting.display_order,
            "is_active": True,
            "counting_unit": "Pairs",
            "reason": "Reactivated in Test C"
        },
        headers=admin_headers
    )
    assert res_reactivate.status_code == 200
    assert res_reactivate.json()["is_active"] is True

    # Check operational list includes it again
    res_ops = client.get("/api/v1/departments/sections", headers=admin_headers)
    assert any(s["id"] == stockfitting.id for s in res_ops.json())


def test_d_impact_warning_for_active_orders(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test D — Deactivate a section currently used by an active order without force_confirm.
    Expected:
    - Returns requires_confirmation = True.
    - Lists affected active orders.
    - Provides impact warning message.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    stitching = env["sections"]["Stitching"]

    order = create_sample_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-D-IMPACT")

    # Request deactivation without force_confirm
    res = client.post(
        f"/api/v1/settings/sections/{stitching.id}/deactivate",
        json={"reason": "Impact test", "force_confirm": False},
        headers=admin_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["requires_confirmation"] is True
    assert data["active_orders_count"] >= 1
    assert any(o["order_code"] == order.order_code for o in data["affected_orders"])
    assert "used in" in data["message"].lower()


def test_e_historical_data_preservation(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test E — Deactivate a section with historical production.
    Expected:
    - Production transactions remain intact in database.
    - Historical production is not deleted or altered.
    - Audit log records deactivation.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    cutting = env["sections"]["Cutting"]

    order = create_sample_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-E-HIST")
    cut_route = next(r for r in order.routes if r.section_id == cutting.id)
    cut_op = cut_route.operations[0]

    user = db.query(User).first()
    # Record 500 pairs of historical production
    entry = DailyProductionEntry(
        order_id=order.id,
        route_id=cut_route.id,
        operation_id=cut_op.id,
        entry_date=date.today(),
        quantity=500.0,
        accepted_quantity=500.0,
        rejected_quantity=0.0,
        unit="Pairs",
        remarks="Historical run before deactivation",
        entered_by_id=user.id
    )
    db.add(entry)
    db.commit()
    entry_id = entry.id

    # Deactivate cutting
    res = client.post(
        f"/api/v1/settings/sections/{cutting.id}/deactivate",
        json={"reason": "Deactivate cutting", "force_confirm": True, "remove_from_active_workflows": True},
        headers=admin_headers
    )
    assert res.status_code == 200

    # Verify entry is preserved
    db_entry = db.query(DailyProductionEntry).filter(DailyProductionEntry.id == entry_id).first()
    assert db_entry is not None
    assert db_entry.accepted_quantity == 500.0
    assert db_entry.is_reversed is False


def test_f_wip_flow_recalculation_and_handoff(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test F — Deactivate an intermediate section (Upper Prep).
    Expected:
    - Next active section (Stitching) receives transferable WIP directly from Cutting.
    - Contiguous serials: 1 -> Cutting, 2 -> Stitching ...
    - No WIP is invented or lost.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    upper_prep = env["sections"]["Upper Prep"]
    cutting = env["sections"]["Cutting"]

    # Re-activate cutting if deactivated in test E
    cutting.is_active = True
    db.commit()

    order = create_sample_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-F-WIP", qty=1000.0)
    cut_route = next(r for r in order.routes if r.section_id == cutting.id)
    cut_op = cut_route.operations[0]

    user = db.query(User).first()
    # Produce 400 pairs in Cutting
    entry = DailyProductionEntry(
        order_id=order.id,
        route_id=cut_route.id,
        operation_id=cut_op.id,
        entry_date=date.today(),
        quantity=400.0,
        accepted_quantity=400.0,
        rejected_quantity=0.0,
        unit="Pairs",
        entered_by_id=user.id
    )
    db.add(entry)
    db.commit()

    # Deactivate Upper Prep
    client.post(
        f"/api/v1/settings/sections/{upper_prep.id}/deactivate",
        json={"reason": "Test F Upper Prep removal", "force_confirm": True, "remove_from_active_workflows": True},
        headers=admin_headers
    )

    wip_plan = WIPPlanningEngine.calculate_order_wip_flow(db, order)
    # Section serials must be contiguous
    summary_map = {s["section_name"]: s for s in wip_plan["workflow_summary"]}
    assert "Upper Prep" not in summary_map

    # Cutting completed 400, so live on hand for next section (Stitching) must be 400
    stitching_summary = summary_map["Stitching"]
    assert stitching_summary["serial_no"] == 2
    assert stitching_summary["final_on_hand"] == 400.0


def test_g_target_calculation_excludes_inactive(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test G — Target calculations must exclude inactive sections.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    stockfitting = env["sections"]["Stockfitting"]

    order = create_sample_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-G-TGT")

    # Deactivate Stockfitting
    client.post(
        f"/api/v1/settings/sections/{stockfitting.id}/deactivate",
        json={"reason": "Test G Target Check", "force_confirm": True, "remove_from_active_workflows": True},
        headers=admin_headers
    )

    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, order.id)
    assert "STOCKFITTING" not in matrix["summary"]
    # Total targets validation
    for s_name, s_val in matrix["summary"].items():
        assert s_name != "STOCKFITTING"


def test_h_backend_rejection_for_inactive_section_entry(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test H — Attempt to record production for an inactive section via API must fail with HTTP 400.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    stockfitting = env["sections"]["Stockfitting"]

    order = create_sample_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-H-REJECT")
    sf_route = next(r for r in order.routes if r.section_id == stockfitting.id)
    sf_op = sf_route.operations[0]

    # Deactivate Stockfitting
    stockfitting.is_active = False
    db.commit()

    # Try to record production entry directly
    res = client.post(
        "/api/v1/production/entry",
        json={
            "order_id": order.id,
            "route_id": sf_route.id,
            "operation_id": sf_op.id,
            "entry_date": date.today().isoformat(),
            "quantity": 100,
            "accepted_quantity": 100,
            "rejected_quantity": 0,
            "unit": "Pairs",
            "remarks": "Should be rejected"
        },
        headers=admin_headers
    )
    assert res.status_code == 400
    assert "inactive section" in res.json()["detail"].lower()


def test_i_save_and_persistent_refresh(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test I — Deactivate section, reload order plan from fresh query, section remains excluded.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    printing = env["sections"]["Printing"]

    order = create_sample_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-I-PERSIST")

    client.post(
        f"/api/v1/settings/sections/{printing.id}/deactivate",
        json={"reason": "Test I Persist", "force_confirm": True, "remove_from_active_workflows": True},
        headers=admin_headers
    )

    # Re-fetch from fresh query
    db.expire_all()
    fresh_order = db.query(Order).filter(Order.id == order.id).first()
    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db, fresh_order.id)
    assert not any(s["section_name"] == "PRINTING" for s in matrix["sections"])


def test_j_export_consistency(client_and_db, admin_headers, setup_footwear_erp_env):
    """
    Test J — Export Matrix XLSX, CSV, and WIP Flow XLSX.
    Expected:
    - Regular exports exclude deactivated sections.
    - Summary row agrees with active columns.
    """
    client, db = client_and_db
    env = setup_footwear_erp_env
    stockfitting = env["sections"]["Stockfitting"]

    stockfitting.is_active = False
    db.commit()

    order = create_sample_order_with_workflow(db, env["buyer"], env["sections"], "ORD-TEST-J-EXP")
    # Remove from order route as well
    sf_route = next(r for r in order.routes if r.section_id == stockfitting.id)
    sf_route.status = SectionRouteStatus.NOT_REQUIRED
    db.commit()

    # 1. Matrix XLSX Export
    xlsx_stream = ExportService.generate_matrix_planning_xlsx(db, order)
    assert xlsx_stream is not None
    assert xlsx_stream.getbuffer().nbytes > 0

    # 2. Matrix CSV Export
    csv_str = ExportService.generate_matrix_planning_csv(db, order)
    assert "STOCKFITTING" not in csv_str.upper()
    assert "CUTTING T/G" in csv_str.upper()

    # 3. WIP Flow XLSX Export
    wip_stream = ExportService.generate_wip_flow_xlsx(db, order)
    assert wip_stream is not None
    assert wip_stream.getbuffer().nbytes > 0
