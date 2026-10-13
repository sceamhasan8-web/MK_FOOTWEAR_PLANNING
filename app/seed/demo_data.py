import sys
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from app.database import Base, engine, SessionLocal
from app.models.user import User, UserRole
from app.models.buyer import Buyer
from app.models.calendar import FactoryCalendar, CalendarException, ExceptionType
from app.models.route import (
    Category,
    Section,
    ProcessTemplate,
    OrderRoute,
    OrderOperation,
    OperationComponent,
    SectionRouteStatus,
    OperationStatus,
    UnitType,
)
from app.models.order import Order, OrderPriority, OrderStatus
from app.models.entry import DailyProductionEntry
from app.api.deps import get_password_hash


def clear_demo_data_only(db: Session):
    """Safely removes only demo records without dropping or deleting real production records."""
    print("Clearing demo records only...")
    demo_order_codes = ["ORD-2026-0001", "ORD-2026-0002", "ORD-2026-0003", "BATA-TEST-001"]
    demo_orders = db.query(Order).filter(Order.order_code.in_(demo_order_codes)).all()
    for o in demo_orders:
        db.query(DailyProductionEntry).filter(DailyProductionEntry.order_id == o.id).delete()
        for r in o.routes:
            for op in r.operations:
                db.query(OperationComponent).filter(OperationComponent.operation_id == op.id).delete()
            db.query(OrderOperation).filter(OrderOperation.route_id == r.id).delete()
        db.query(OrderRoute).filter(OrderRoute.order_id == o.id).delete()
        db.delete(o)
    
    # Remove demo buyers if they have no other orders
    demo_buyer_codes = ["BATA-001", "APEX-002", "BATA-DEMO"]
    demo_buyers = db.query(Buyer).filter(Buyer.buyer_code.in_(demo_buyer_codes)).all()
    for b in demo_buyers:
        has_orders = db.query(Order).filter(Order.buyer_id == b.id).count()
        if not has_orders:
            db.delete(b)
            
    db.commit()
    print("Demo records cleared successfully.")


def seed_demo_data(db: Session, reset_all: bool = False):
    """
    Safely seeds clean development/demo data.
    If reset_all is True, drops and creates tables. Otherwise, seeds or updates idempotently.
    """
    if reset_all:
        print("Dropping and recreating all tables...")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    else:
        Base.metadata.create_all(bind=engine)

    # 1. Factory Calendar
    cal = db.query(FactoryCalendar).filter(FactoryCalendar.is_default == True).first()
    if not cal:
        print("Seeding factory calendar...")
        cal = FactoryCalendar(
            name="Dhaka Factory Standard Calendar",
            is_default=True,
            work_monday=True,
            work_tuesday=True,
            work_wednesday=True,
            work_thursday=True,
            work_friday=False,  # BD weekend
            work_saturday=True,
            work_sunday=True,
            cutoff_hour=18,
            cutoff_minute=0,
            timezone="Asia/Dhaka",
            use_working_days_only=True,
            same_day_category_transfer=False,
        )
        db.add(cal)
        db.flush()

        holiday = CalendarException(
            calendar_id=cal.id,
            exception_date=date.today() + timedelta(days=3),
            exception_type=ExceptionType.HOLIDAY,
            description="Factory Maintenance & Electrical Inspection Holiday"
        )
        db.add(holiday)

    # 2. Users
    users_data = [
        ("admin", "admin@footwearerp.com", "Factory Administrator", UserRole.ADMIN, "admin123"),
        ("planner", "planner@footwearerp.com", "Rahim Planning Manager", UserRole.PLANNING_MANAGER, "planner123"),
        ("supervisor", "supervisor@footwearerp.com", "Karim Cutting Supervisor", UserRole.SUPERVISOR, "supervisor123"),
        ("user", "user@footwearerp.com", "MK Factory Standard User", UserRole.USER, "user123"),
        ("viewer", "viewer@footwearerp.com", "Visitor Viewer", UserRole.VIEWER, "viewer123"),
    ]
    for username, email, full_name, role, pwd in users_data:
        existing = db.query(User).filter(User.username == username).first()
        if not existing:
            db.add(User(
                username=username,
                email=email,
                full_name=full_name,
                role=role,
                hashed_password=get_password_hash(pwd),
                is_active=True,
            ))
    db.flush()
    planner_user = db.query(User).filter(User.username == "planner").first()
    supervisor_user = db.query(User).filter(User.username == "supervisor").first()

    # 3. Categories & Sections
    cat_defs = [
        ("Cutting", 1, [("Lamination", 1), ("Cutting", 2), ("Skiving", 3)]),
        ("Preparation", 2, [("Upper Prep", 1), ("Stitching", 2), ("Printing", 3), ("Emboss", 4), ("Sewing", 5)]),
        ("Stockfitting", 3, [("Stockfitting", 1)]),
        ("Lasting & Dip", 4, [("Lasting", 1), ("Dip", 2)]),
    ]
    for cat_name, cat_order, secs in cat_defs:
        c = db.query(Category).filter(Category.name == cat_name).first()
        if not c:
            c = Category(name=cat_name, display_order=cat_order, is_active=True)
            db.add(c)
            db.flush()
        for sec_name, sec_order in secs:
            s = db.query(Section).filter(Section.category_id == c.id, Section.name == sec_name).first()
            if not s:
                s = Section(category_id=c.id, name=sec_name, display_order=sec_order, is_active=True)
                db.add(s)
                db.flush()

    sec_lam = db.query(Section).filter(Section.name == "Lamination").first()
    sec_cutting = db.query(Section).filter(Section.name == "Cutting").first()
    sec_skv = db.query(Section).filter(Section.name == "Skiving").first()
    sec_up_prep = db.query(Section).filter(Section.name == "Upper Prep").first()
    sec_stitching = db.query(Section).filter(Section.name == "Stitching").first()
    sec_printing = db.query(Section).filter(Section.name == "Printing").first()
    sec_emboss = db.query(Section).filter(Section.name == "Emboss").first()
    sec_sewing = db.query(Section).filter(Section.name == "Sewing").first()
    sec_stockfit = db.query(Section).filter(Section.name == "Stockfitting").first()
    sec_lasting = db.query(Section).filter(Section.name == "Lasting").first()
    sec_dip = db.query(Section).filter(Section.name == "Dip").first()

    # 4. Buyers
    bata = db.query(Buyer).filter(Buyer.buyer_code == "BATA-001").first()
    if not bata:
        bata = Buyer(
            name="BATA Shoe Company",
            buyer_code="BATA-001",
            contact_person="Tariqul Islam",
            phone="+880 1711 000111",
            email="orders@bata-footwear.com",
            address="Tongi Industrial Area, Gazipur, Bangladesh",
            notes="Strategic international retail account. High priority quality assurance.",
            is_active=True,
        )
        db.add(bata)
        db.flush()

    apex = db.query(Buyer).filter(Buyer.buyer_code == "APEX-002").first()
    if not apex:
        apex = Buyer(
            name="Apex Footwear Ltd",
            buyer_code="APEX-002",
            contact_person="Mahmudur Rahman",
            phone="+880 1819 222333",
            email="planning@apexfootwear.com",
            address="Shafipur, Kaliakoir, Gazipur",
            notes="Export volume orders.",
            is_active=True,
        )
        db.add(apex)
        db.flush()

    # 5. Orders with Complete Multi-Department Workflow from Cutting down to Lasting
    # ORD-2026-0001 (BATA 70,000 Pairs): Cutting -> Printing -> Sewing -> Lasting -> Dip
    ord1 = db.query(Order).filter(Order.order_code == "ORD-2026-0001").first()
    if not ord1:
        ord1 = Order(
            order_code="ORD-2026-0001",
            buyer_id=bata.id,
            customer_ref="BATA-SNK-70K",
            po_number="PO-BT-98210",
            style_model="Court Royale Pro v2",
            description="Premium synthetic leather lifestyle sneaker with rubber cupsole",
            total_quantity=70000.0,
            original_order_date=date.today() - timedelta(days=5),
            production_start_date=date.today() - timedelta(days=2),
            original_delivery_date=date.today() + timedelta(days=20),
            current_delivery_date=date.today() + timedelta(days=20),
            priority=OrderPriority.HIGH,
            status=OrderStatus.IN_PRODUCTION,
            created_by_id=planner_user.id if planner_user else 1,
        )
        db.add(ord1)
        db.flush()

        r1_cut = OrderRoute(order_id=ord1.id, section_id=sec_cutting.id, status=SectionRouteStatus.REQUIRED, sequence_order=1)
        r1_prt = OrderRoute(order_id=ord1.id, section_id=sec_printing.id, status=SectionRouteStatus.REQUIRED, sequence_order=2)
        r1_sew = OrderRoute(order_id=ord1.id, section_id=sec_sewing.id, status=SectionRouteStatus.REQUIRED, sequence_order=3)
        r1_lst = OrderRoute(order_id=ord1.id, section_id=sec_lasting.id, status=SectionRouteStatus.REQUIRED, sequence_order=4)
        r1_dip = OrderRoute(order_id=ord1.id, section_id=sec_dip.id, status=SectionRouteStatus.NOT_REQUIRED, sequence_order=5)
        db.add_all([r1_cut, r1_prt, r1_sew, r1_lst, r1_dip])
        db.flush()

        op1_cut = OrderOperation(route_id=r1_cut.id, operation_name="Upper Die Cutting", required_quantity=70000.0, balance_quantity=70000.0, status=OperationStatus.IN_PROGRESS)
        op1_prt1 = OrderOperation(route_id=r1_prt.id, operation_name="Operation 1", required_quantity=70000.0, balance_quantity=70000.0, status=OperationStatus.PENDING)
        op1_prt2 = OrderOperation(route_id=r1_prt.id, operation_name="Operation 2", required_quantity=70000.0, balance_quantity=70000.0, status=OperationStatus.PENDING)
        op1_prt3 = OrderOperation(route_id=r1_prt.id, operation_name="Operation 3", required_quantity=70000.0, balance_quantity=70000.0, status=OperationStatus.PENDING)
        op1_sew = OrderOperation(route_id=r1_sew.id, operation_name="Upper Assembly", required_quantity=70000.0, balance_quantity=70000.0, status=OperationStatus.PENDING)
        op1_lst = OrderOperation(route_id=r1_lst.id, operation_name="Toe & Side Lasting", required_quantity=70000.0, balance_quantity=70000.0, status=OperationStatus.PENDING)
        db.add_all([op1_cut, op1_prt1, op1_prt2, op1_prt3, op1_sew, op1_lst])
        db.flush()

    # ORD-2026-0002 (Apex Runner Velocity 38,000 Pairs): Cutting -> Printing -> Emboss -> Sewing -> Lasting
    ord2 = db.query(Order).filter(Order.order_code == "ORD-2026-0002").first()
    if ord2:
        # Check if route only had Printing, if so update to complete multi-department workflow
        if len(ord2.routes) <= 1:
            for r in ord2.routes:
                for op in r.operations:
                    db.query(DailyProductionEntry).filter(DailyProductionEntry.operation_id == op.id).delete()
                    db.delete(op)
                db.delete(r)
            db.flush()
            r2_cut = OrderRoute(order_id=ord2.id, section_id=sec_cutting.id, status=SectionRouteStatus.REQUIRED, sequence_order=1)
            r2_prt = OrderRoute(order_id=ord2.id, section_id=sec_printing.id, status=SectionRouteStatus.REQUIRED, sequence_order=2)
            r2_emb = OrderRoute(order_id=ord2.id, section_id=sec_emboss.id, status=SectionRouteStatus.REQUIRED, sequence_order=3)
            r2_sew = OrderRoute(order_id=ord2.id, section_id=sec_sewing.id, status=SectionRouteStatus.REQUIRED, sequence_order=4)
            r2_lst = OrderRoute(order_id=ord2.id, section_id=sec_lasting.id, status=SectionRouteStatus.REQUIRED, sequence_order=5)
            db.add_all([r2_cut, r2_prt, r2_emb, r2_sew, r2_lst])
            db.flush()
            op2_cut = OrderOperation(route_id=r2_cut.id, operation_name="Cutting", required_quantity=38000.0, balance_quantity=38000.0, status=OperationStatus.PENDING)
            op2_prt = OrderOperation(route_id=r2_prt.id, operation_name="Printing", required_quantity=38000.0, balance_quantity=38000.0, status=OperationStatus.PENDING)
            op2_emb = OrderOperation(route_id=r2_emb.id, operation_name="Emboss", required_quantity=38000.0, balance_quantity=38000.0, status=OperationStatus.PENDING)
            op2_sew = OrderOperation(route_id=r2_sew.id, operation_name="Sewing", required_quantity=38000.0, balance_quantity=38000.0, status=OperationStatus.PENDING)
            op2_lst = OrderOperation(route_id=r2_lst.id, operation_name="Lasting", required_quantity=38000.0, balance_quantity=38000.0, status=OperationStatus.PENDING)
            db.add_all([op2_cut, op2_prt, op2_emb, op2_sew, op2_lst])
            db.flush()

    # ORD-2026-0004 (BATA Lifestyle Ultra 30,000 Pairs): Cutting -> Upper Prep -> Stitching -> Printing -> Stockfitting -> Lasting
    ord4 = db.query(Order).filter(Order.order_code == "ORD-2026-0004").first()
    if not ord4:
        ord4 = Order(
            order_code="ORD-2026-0004",
            buyer_id=bata.id,
            customer_ref="BATA-ULTRA-30K",
            po_number="PO-BT-99501",
            style_model="Lifestyle Street Ultra",
            description="Multi-department footwear manufacturing workflow: Cutting to Lasting",
            total_quantity=30000.0,
            original_order_date=date.today() - timedelta(days=3),
            production_start_date=date.today(),
            original_delivery_date=date.today() + timedelta(days=12),
            current_delivery_date=date.today() + timedelta(days=12),
            priority=OrderPriority.HIGH,
            status=OrderStatus.SCHEDULED,
            created_by_id=planner_user.id if planner_user else 1,
        )
        db.add(ord4)
        db.flush()

        seq_sections = [
            (sec_cutting, "Cutting"),
            (sec_up_prep, "Upper Prep"),
            (sec_stitching, "Stitching"),
            (sec_printing, "Printing"),
            (sec_stockfit, "Stockfitting"),
            (sec_lasting, "Lasting"),
        ]
        for seq_i, (sec_obj, op_title) in enumerate(seq_sections, start=1):
            if sec_obj:
                r_seq = OrderRoute(order_id=ord4.id, section_id=sec_obj.id, status=SectionRouteStatus.REQUIRED, sequence_order=seq_i)
                db.add(r_seq)
                db.flush()
                op_seq = OrderOperation(route_id=r_seq.id, operation_name=op_title, required_quantity=30000.0, balance_quantity=30000.0, status=OperationStatus.PENDING)
                db.add(op_seq)
        db.flush()

    db.commit()
    print("Demo data seeded/verified successfully!")


if __name__ == "__main__":
    session = SessionLocal()
    try:
        if "--clear-demo" in sys.argv:
            clear_demo_data_only(session)
        elif "--reset-all" in sys.argv:
            seed_demo_data(session, reset_all=True)
        else:
            seed_demo_data(session, reset_all=False)
    finally:
        session.close()
