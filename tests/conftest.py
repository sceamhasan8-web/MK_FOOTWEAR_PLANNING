import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.models.calendar import FactoryCalendar
from app.models.route import Category, Section, ProcessTemplate, UnitType
from app.api.deps import get_password_hash, create_access_token

# In-memory SQLite engine for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()

    # Seed baseline calendar
    cal = FactoryCalendar(
        name="Test Calendar",
        is_default=True,
        work_monday=True,
        work_tuesday=True,
        work_wednesday=True,
        work_thursday=True,
        work_friday=False,  # Bangladesh weekend
        work_saturday=True,
        work_sunday=True,
        cutoff_hour=18,
        cutoff_minute=0,
        timezone="Asia/Dhaka",
    )
    session.add(cal)

    # Seed baseline users
    admin = User(
        username="admin_test",
        email="admin@test.com",
        full_name="Admin Test",
        role=UserRole.ADMIN,
        hashed_password=get_password_hash("pass123"),
        is_active=True,
    )
    planner = User(
        username="planner_test",
        email="planner@test.com",
        full_name="Planner Test",
        role=UserRole.PLANNING_MANAGER,
        hashed_password=get_password_hash("pass123"),
        is_active=True,
    )
    supervisor = User(
        username="supervisor_test",
        email="supervisor@test.com",
        full_name="Supervisor Test",
        role=UserRole.SUPERVISOR,
        hashed_password=get_password_hash("pass123"),
        is_active=True,
    )
    viewer = User(
        username="viewer_test",
        email="viewer@test.com",
        full_name="Viewer Test",
        role=UserRole.VIEWER,
        hashed_password=get_password_hash("pass123"),
        is_active=True,
    )
    session.add_all([admin, planner, supervisor, viewer])

    # Seed default footwear department categories & sections
    cat_cut = Category(name="Cutting", display_order=1, is_active=True)
    cat_prep = Category(name="Preparation", display_order=2, is_active=True)
    cat_stock = Category(name="Stockfitting", display_order=3, is_active=True)
    cat_last = Category(name="Lasting & Dip", display_order=4, is_active=True)
    session.add_all([cat_cut, cat_prep, cat_stock, cat_last])
    session.flush()

    sec_lam = Section(category_id=cat_cut.id, name="Lamination", display_order=11, planning_id=11, is_active=True)
    sec_cut = Section(category_id=cat_cut.id, name="Cutting", display_order=1, planning_id=1, is_active=True)
    sec_skv = Section(category_id=cat_cut.id, name="Skiving", display_order=12, planning_id=12, is_active=True)

    sec_up = Section(category_id=cat_prep.id, name="Upper Prep", display_order=2, planning_id=2, is_active=True)
    sec_st = Section(category_id=cat_prep.id, name="Stitching", display_order=3, planning_id=3, is_active=True)
    sec_prt = Section(category_id=cat_prep.id, name="Printing", display_order=4, planning_id=4, is_active=True)
    sec_emb = Section(category_id=cat_prep.id, name="Emboss", display_order=13, planning_id=13, is_active=True)
    sec_sew = Section(category_id=cat_prep.id, name="Sewing", display_order=14, planning_id=14, is_active=True)

    sec_stk = Section(category_id=cat_stock.id, name="Stockfitting", display_order=5, planning_id=5, is_active=True)

    sec_lst = Section(category_id=cat_last.id, name="Lasting", display_order=6, planning_id=6, is_active=True)
    sec_dip = Section(category_id=cat_last.id, name="Dip", display_order=15, planning_id=15, is_active=True)

    session.add_all([sec_lam, sec_cut, sec_skv, sec_up, sec_st, sec_prt, sec_emb, sec_sew, sec_stk, sec_lst, sec_dip])
    session.flush()

    # Printing process templates (Operation 1, 2, 3)
    p1 = ProcessTemplate(section_id=sec_prt.id, name="Operation 1", default_unit=UnitType.PAIRS, display_order=1, is_active=True)
    p2 = ProcessTemplate(section_id=sec_prt.id, name="Operation 2", default_unit=UnitType.PAIRS, display_order=2, is_active=True)
    p3 = ProcessTemplate(section_id=sec_prt.id, name="Operation 3", default_unit=UnitType.PAIRS, display_order=3, is_active=True)
    session.add_all([p1, p2, p3])

    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(db_session):
    def _headers_for_role(role_name: str):
        user = db_session.query(User).filter(User.username == f"{role_name}_test").first()
        token = create_access_token(data={"sub": user.username, "user_id": user.id, "role": user.role.value})
        return {"Authorization": f"Bearer {token}"}
    return _headers_for_role
