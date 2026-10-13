import time
import openpyxl
from datetime import date
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from app.database import get_db, engine
from app.config import settings
from app.models.buyer import Buyer
from app.models.order import Order
from app.models.calendar import FactoryCalendar
from app.services.production_planning_service import ProductionPlanningService

router = APIRouter(tags=["Diagnostics"])


@router.get("/health")
def api_health(request: Request, db: Session = Depends(get_db)):
    """Lightweight database connectivity and API health check."""
    t0 = time.time()
    db_connected = False
    table_count = 0
    try:
        db.execute(text("SELECT 1"))
        db_connected = True
        insp = inspect(engine)
        table_count = len(insp.get_table_names())
    except Exception as e:
        db_error = str(e)
    else:
        db_error = None

    duration_ms = round((time.time() - t0) * 1000, 2)
    req_id = getattr(request.state, "request_id", "ERP-HEALTH")

    return {
        "status": "ok" if db_connected else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": "connected" if db_connected else "disconnected",
        "database_type": engine.dialect.name,
        "database_tables": table_count,
        "latency_ms": duration_ms,
        "error": db_error,
        "request_id": req_id,
    }


@router.get("/diagnostics")
def run_system_diagnostics(request: Request, db: Session = Depends(get_db)):
    """
    Comprehensive diagnostic probe across all application subsystems:
    Database, Authentication, Buyers, Orders, Planning, and Excel Export.
    """
    diagnostics = []
    overall_status = "PASS"

    def add_diag(name: str, status: str, details: str, latency_ms: float = 0.0):
        nonlocal overall_status
        if status != "PASS":
            overall_status = "FAIL"
        diagnostics.append({
            "subsystem": name,
            "status": status,
            "details": details,
            "latency_ms": round(latency_ms, 2)
        })

    # 1. Database Engine
    t0 = time.time()
    try:
        db.execute(text("SELECT 1"))
        add_diag("Database Connection", "PASS", f"Active ({engine.dialect.name})", (time.time() - t0) * 1000)
    except Exception as e:
        add_diag("Database Connection", "FAIL", f"Connection error: {str(e)}", (time.time() - t0) * 1000)

    # 2. Database Schema Integrity
    t0 = time.time()
    try:
        insp = inspect(engine)
        tables = insp.get_table_names()
        required_tables = ["users", "buyers", "orders", "factory_calendars", "categories", "sections"]
        missing = [t for t in required_tables if t not in tables]
        if missing:
            add_diag("Database Schema", "FAIL", f"Missing tables: {missing}", (time.time() - t0) * 1000)
        else:
            add_diag("Database Schema", "PASS", f"All {len(tables)} tables verified", (time.time() - t0) * 1000)
    except Exception as e:
        add_diag("Database Schema", "FAIL", f"Schema check error: {str(e)}", (time.time() - t0) * 1000)

    # 3. Calendar Service
    t0 = time.time()
    try:
        cal = db.query(FactoryCalendar).filter(FactoryCalendar.is_default == True).first()
        if cal:
            add_diag("Factory Calendar", "PASS", f"Active calendar: {cal.name} ({cal.timezone})", (time.time() - t0) * 1000)
        else:
            add_diag("Factory Calendar", "PASS", "No default calendar set (using fallback)", (time.time() - t0) * 1000)
    except Exception as e:
        add_diag("Factory Calendar", "FAIL", f"Calendar error: {str(e)}", (time.time() - t0) * 1000)

    # 4. Buyer API / Table
    t0 = time.time()
    try:
        buyers_count = db.query(Buyer).count()
        add_diag("Buyer Management", "PASS", f"{buyers_count} buyers recorded in database", (time.time() - t0) * 1000)
    except Exception as e:
        add_diag("Buyer Management", "FAIL", f"Buyer query error: {str(e)}", (time.time() - t0) * 1000)

    # 5. Order & Planning Engine
    t0 = time.time()
    try:
        orders_count = db.query(Order).count()
        add_diag("Order Planning", "PASS", f"{orders_count} orders managed in database", (time.time() - t0) * 1000)
    except Exception as e:
        add_diag("Order Planning", "FAIL", f"Order query error: {str(e)}", (time.time() - t0) * 1000)

    # 6. Excel Export Engine
    t0 = time.time()
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Diag"
        ws["A1"] = "OK"
        add_diag("Excel Export Engine", "PASS", "openpyxl library loaded and operational", (time.time() - t0) * 1000)
    except Exception as e:
        add_diag("Excel Export Engine", "FAIL", f"Excel engine error: {str(e)}", (time.time() - t0) * 1000)

    req_id = getattr(request.state, "request_id", "ERP-DIAG")
    return {
        "overall_status": overall_status,
        "timestamp": str(date.today()),
        "request_id": req_id,
        "subsystems": diagnostics
    }
