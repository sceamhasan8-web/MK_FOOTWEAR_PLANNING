import pytest
from app.db_migration import verify_and_sync_schema
from app.database import Base
from tests.conftest import test_engine


def test_api_health_endpoint(client):
    """Verify /api/v1/health returns healthy status and DB connection."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "x-request-id" in res.headers
    assert data["request_id"].startswith("ERP-")


def test_system_diagnostics_endpoint(client):
    """Verify /api/v1/diagnostics runs probes across all core subsystems."""
    res = client.get("/api/v1/diagnostics")
    assert res.status_code == 200
    data = res.json()
    assert data["overall_status"] == "PASS"
    assert "subsystems" in data
    assert len(data["subsystems"]) >= 5

    names = [s["subsystem"] for s in data["subsystems"]]
    assert "Database Connection" in names
    assert "Database Schema" in names
    assert "Buyer Management" in names
    assert "Order Planning" in names
    assert "Excel Export Engine" in names


def test_schema_self_healing_migration(db_session):
    """Verify verify_and_sync_schema connects and reports valid tables."""
    result = verify_and_sync_schema(test_engine, Base)
    assert result["connected"] is True
    assert result["tables_checked"] >= 10
    assert len(result["errors"]) == 0
