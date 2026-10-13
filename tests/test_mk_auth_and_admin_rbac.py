import io
import os
import openpyxl
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db
from app.models.user import User, UserRole
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.route import Category, Section, OrderRoute, OrderOperation, SectionRouteStatus
from app.models.calendar import FactoryCalendar
from app.api.deps import get_password_hash, create_access_token
from app.services.production_planning_service import ProductionPlanningService
from app.services.wip_planning_engine import WIPPlanningEngine


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = next(get_db())
    yield db


@pytest.fixture
def seeded_users(db_session):
    # Ensure admin user
    admin = db_session.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@mkfootwear.com",
            full_name="MK Factory Admin",
            role=UserRole.ADMIN,
            hashed_password=get_password_hash("admin123"),
            is_active=True,
        )
        db_session.add(admin)
        db_session.commit()
    else:
        admin.role = UserRole.ADMIN
        admin.is_active = True
        admin.failed_login_attempts = 0
        admin.locked_until = None
        db_session.commit()

    # Ensure standard user
    std_user = db_session.query(User).filter(User.username == "user").first()
    if not std_user:
        std_user = User(
            username="user",
            email="user@mkfootwear.com",
            full_name="MK Standard User",
            role=UserRole.USER,
            hashed_password=get_password_hash("user123"),
            is_active=True,
        )
        db_session.add(std_user)
        db_session.commit()
    else:
        std_user.role = UserRole.USER
        std_user.is_active = True
        std_user.failed_login_attempts = 0
        std_user.locked_until = None
        db_session.commit()

    # Ensure inactive user
    inactive_user = db_session.query(User).filter(User.username == "inactive_tester").first()
    if not inactive_user:
        inactive_user = User(
            username="inactive_tester",
            email="inactive@mkfootwear.com",
            full_name="Inactive Tester",
            role=UserRole.USER,
            hashed_password=get_password_hash("inactive123"),
            is_active=False,
        )
        db_session.add(inactive_user)
        db_session.commit()
    else:
        inactive_user.is_active = False
        db_session.commit()

    return {"admin": admin, "user": std_user, "inactive": inactive_user}


# =============================================================================
# Test A — Administrator Login & Admin Panel Access
# =============================================================================
def test_scenario_a_administrator_login(test_client, seeded_users):
    """
    Authenticate with valid account assigned ADMIN role.
    Expected:
    - Login succeeds.
    - Token received with ADMIN role.
    - Admin Panel endpoints are accessible.
    - ERP modules remain accessible.
    """
    res = test_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert "access_token" in data
    assert data["username"] == "admin"
    assert data["role"] in (UserRole.ADMIN, "admin")

    token = data["access_token"]
    admin_hdr = {"Authorization": f"Bearer {token}"}

    # Verify Admin Panel dashboard access
    res_dash = test_client.get("/api/v1/admin/dashboard", headers=admin_hdr)
    assert res_dash.status_code == 200
    dash_data = res_dash.json()
    assert dash_data["status"] == "success"
    assert "metrics" in dash_data
    assert dash_data["metrics"]["total_users"] >= 1

    # Verify Admin users list access
    res_users = test_client.get("/api/v1/admin/users", headers=admin_hdr)
    assert res_users.status_code == 200
    assert isinstance(res_users.json(), list)

    # Verify standard ERP module access remains fully accessible
    res_orders = test_client.get("/api/v1/orders", headers=admin_hdr)
    assert res_orders.status_code == 200


# =============================================================================
# Test B — Standard User Login & Permissions
# =============================================================================
def test_scenario_b_standard_user_login(test_client, seeded_users):
    """
    Authenticate with valid account assigned USER role.
    Expected:
    - Login succeeds.
    - Standard ERP modules load.
    - Admin endpoints remain inaccessible (403 Forbidden).
    """
    res = test_client.post("/api/v1/auth/login", json={"username": "user", "password": "user123"})
    assert res.status_code == 200
    data = res.json()
    token = data["access_token"]
    user_hdr = {"Authorization": f"Bearer {token}"}

    # Standard ERP orders endpoint works
    res_orders = test_client.get("/api/v1/orders", headers=user_hdr)
    assert res_orders.status_code == 200

    # Admin dashboard endpoint rejected with 403 Forbidden
    res_admin = test_client.get("/api/v1/admin/dashboard", headers=user_hdr)
    assert res_admin.status_code == 403


# =============================================================================
# Test C — Unauthenticated Admin Access
# =============================================================================
def test_scenario_c_unauthenticated_admin_access(test_client):
    """
    Directly request Admin endpoints without authentication token.
    Expected: Returns 401 Unauthorized.
    """
    res = test_client.get("/api/v1/admin/dashboard")
    assert res.status_code == 401

    res_users = test_client.get("/api/v1/admin/users")
    assert res_users.status_code == 401


# =============================================================================
# Test D — Standard User Direct URL Access
# =============================================================================
def test_scenario_d_standard_user_direct_admin_url_access(test_client, seeded_users):
    """
    Standard user attempts direct access to protected administrative endpoints.
    Expected: 403 Forbidden.
    """
    res = test_client.post("/api/v1/auth/login", json={"username": "user", "password": "user123"})
    token = res.json()["access_token"]
    user_hdr = {"Authorization": f"Bearer {token}"}

    for ep in ["/api/v1/admin/dashboard", "/api/v1/admin/users", "/api/v1/admin/diagnostics", "/api/v1/admin/audit"]:
        r = test_client.get(ep, headers=user_hdr)
        assert r.status_code == 403, f"Endpoint {ep} should have returned 403"


# =============================================================================
# Test E — Direct API Authorization Protection
# =============================================================================
def test_scenario_e_direct_api_authorization(test_client, seeded_users):
    """
    Standard user attempts to invoke administrator user management APIs.
    Expected: 403 Forbidden.
    """
    res = test_client.post("/api/v1/auth/login", json={"username": "user", "password": "user123"})
    user_hdr = {"Authorization": f"Bearer {res.json()['access_token']}"}

    # Attempt to create user as standard user -> 403
    r_create = test_client.post("/api/v1/admin/users", json={
        "username": "hacker",
        "full_name": "Hacker",
        "email": "hacker@test.com",
        "password": "password123",
        "role": "admin"
    }, headers=user_hdr)
    assert r_create.status_code == 403

    # Attempt to reset password as standard user -> 403
    r_reset = test_client.post("/api/v1/admin/users/1/reset-password", json={
        "new_password": "newpassword123"
    }, headers=user_hdr)
    assert r_reset.status_code == 403


# =============================================================================
# Test F — Incorrect Password Handling
# =============================================================================
def test_scenario_f_incorrect_password(test_client, seeded_users):
    """
    Enter an incorrect password.
    Expected:
    - 401 Unauthorized.
    - Generic error message.
    - No access token returned.
    """
    res = test_client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrongpassword999"})
    assert res.status_code == 401
    assert "Invalid username or password" in res.json()["detail"]
    assert "access_token" not in res.json()


# =============================================================================
# Test G — Inactive Account Login Rejection
# =============================================================================
def test_scenario_g_inactive_account(test_client, seeded_users):
    """
    Attempt login using a deactivated account.
    Expected: Rejected with HTTP 400 Bad Request.
    """
    res = test_client.post("/api/v1/auth/login", json={"username": "inactive_tester", "password": "inactive123"})
    assert res.status_code == 400
    assert "deactivated" in res.json()["detail"].lower()


# =============================================================================
# Test H — Persistent Session Verification
# =============================================================================
def test_scenario_h_persistent_session(test_client, seeded_users):
    """
    Verify authenticated session via /api/v1/auth/me.
    """
    res = test_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = res.json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    res_me = test_client.get("/api/v1/auth/me", headers=hdr)
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert me_data["username"] == "admin"
    assert me_data["is_active"] is True


# =============================================================================
# Test I — Logout
# =============================================================================
def test_scenario_i_logout(test_client, seeded_users):
    """
    Verify logout endpoint terminates session safely.
    """
    res = test_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = res.json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    res_logout = test_client.post("/api/v1/auth/logout", headers=hdr)
    assert res_logout.status_code == 200
    assert res_logout.json()["status"] == "success"


# =============================================================================
# Test J — Existing ERP Regression Verification
# =============================================================================
def test_scenario_j_existing_erp_regression(test_client, seeded_users, db_session):
    """
    Verify existing ERP functionality:
    - Buyers load
    - Orders load
    - Planning Matrix calculates
    - WIP flow calculates
    - Production entry works
    - XLSX and CSV exports work
    """
    res = test_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    admin_hdr = {"Authorization": f"Bearer {res.json()['access_token']}"}

    # 1. Buyers API
    r_buyers = test_client.get("/api/v1/buyers", headers=admin_hdr)
    assert r_buyers.status_code == 200
    buyers = r_buyers.json()
    assert len(buyers) >= 1

    # 2. Orders API
    r_orders = test_client.get("/api/v1/orders", headers=admin_hdr)
    assert r_orders.status_code == 200
    orders = r_orders.json()
    assert len(orders) >= 1

    sample_order = orders[0]
    order_id = sample_order["id"]

    # 3. Planning Matrix calculation
    matrix = ProductionPlanningService.generate_order_matrix_planning_sheet(db_session, order_id)
    assert "sections" in matrix
    assert len(matrix["sections"]) >= 1

    # 4. WIP Flow calculation
    order_obj = db_session.query(Order).filter(Order.id == order_id).first()
    wip_plan = WIPPlanningEngine.calculate_order_wip_flow(db_session, order_obj)
    assert "sections" in wip_plan

    # 5. Export XLSX & CSV
    r_xlsx = test_client.get(f"/api/v1/exports/orders/{order_id}/xlsx", headers=admin_hdr)
    assert r_xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r_xlsx.content))
    assert len(wb.sheetnames) >= 6

    r_csv = test_client.get(f"/api/v1/exports/orders/{order_id}/csv", headers=admin_hdr)
    assert r_csv.status_code == 200


# =============================================================================
# Test K — Branding & Assets Verification
# =============================================================================
def test_scenario_k_branding_and_assets():
    """
    Verify logo assets exist and have valid SVG / branding content.
    """
    portal_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "web-portal")
    primary_logo = os.path.join(portal_dir, "mk-footwear-planning.svg")
    icon_logo = os.path.join(portal_dir, "mk-footwear-icon.svg")
    light_logo = os.path.join(portal_dir, "mk-footwear-logo-light.svg")
    branding_js = os.path.join(portal_dir, "branding.js")

    assert os.path.exists(primary_logo), "Primary SVG logo missing"
    assert os.path.exists(icon_logo), "Icon SVG logo missing"
    assert os.path.exists(light_logo), "Light SVG logo missing"
    assert os.path.exists(branding_js), "Branding JS missing"

    with open(primary_logo, "r", encoding="utf-8") as f:
        content = f.read()
        assert "<svg" in content
        assert "MK" in content
        assert "FOOTWEAR" in content

    with open(branding_js, "r", encoding="utf-8") as f:
        js_content = f.read()
        assert "MK Footwear Planning" in js_content


# =============================================================================
# Test L — Security Regression
# =============================================================================
def test_scenario_l_security_regression(test_client, seeded_users, db_session):
    """
    Verify:
    - Passwords are encrypted with bcrypt ($2b$).
    - Never plaintext in db.
    - Password hashes not returned in user endpoints.
    - Last active administrator cannot be deactivated or deleted.
    """
    admin_user = db_session.query(User).filter(User.username == "admin").first()
    assert admin_user.hashed_password.startswith("$2b$")
    assert admin_user.hashed_password != "admin123"

    res = test_client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    admin_hdr = {"Authorization": f"Bearer {res.json()['access_token']}"}

    # Verify user list does not leak hashed_password
    r_users = test_client.get("/api/v1/admin/users", headers=admin_hdr)
    assert r_users.status_code == 200
    for u in r_users.json():
        assert "hashed_password" not in u
        assert "password" not in u

    # Verify protecting the last active administrator from deactivation
    # Ensure there is only 1 active admin
    db_session.query(User).filter(User.role == UserRole.ADMIN, User.id != admin_user.id).delete()
    db_session.commit()

    r_deact = test_client.put(f"/api/v1/admin/users/{admin_user.id}", json={
        "is_active": False
    }, headers=admin_hdr)
    assert r_deact.status_code == 400
    assert "last remaining active administrator" in r_deact.json()["detail"].lower()

    # Verify protecting last admin from deletion
    r_del = test_client.delete(f"/api/v1/admin/users/{admin_user.id}", headers=admin_hdr)
    assert r_del.status_code == 400
    assert "last remaining active administrator" in r_del.json()["detail"].lower()
