from datetime import date, timedelta
from app.services.calculation_engine import CalculationEngine
from app.services.calendar_service import CalendarService
from app.models.route import Section


def test_scenario_d_automatic_daily_target(client, auth_headers, db_session):
    """
    Scenario D: Automatic daily target
    Create an operation with a remaining balance of 24,000 pairs and 12 remaining working days.
    Expected initial daily target = 2,000 pairs.
    Enter actual production, recalculate, and verify that upcoming targets use the new balance and remaining working days.
    """
    admin_hdr = auth_headers("admin")
    supervisor_hdr = auth_headers("supervisor")

    # Verify calculation formula directly first
    target_direct = CalculationEngine.calculate_daily_target(remaining_balance=24000.0, remaining_working_days=12)
    assert target_direct == 2000.0

    # Create an order configured to have exactly 12 remaining working days
    r_buyer = client.post("/api/v1/buyers", json={
        "name": "Target Test Buyer",
        "buyer_code": "TGT-001",
        "is_active": True
    }, headers=admin_hdr)
    buyer_id = r_buyer.json()["id"]

    # Calculate delivery date that yields 12 working days from today
    cal = CalendarService.get_active_calendar(db_session)
    curr = date.today()
    workdays_found = 0
    target_delivery = curr
    while workdays_found < 12:
        if CalendarService.is_working_day(curr, cal, []):
            workdays_found += 1
            target_delivery = curr
        curr += timedelta(days=1)

    sec_cut = db_session.query(Section).filter(Section.name == "Cutting").first()

    order_payload = {
        "buyer_id": buyer_id,
        "order_code": "ORD-TGT-24K",
        "customer_ref": "REF-TGT-24000",
        "style_model": "Daily Target Model",
        "total_quantity": 24000.0,
        "production_start_date": str(date.today()),
        "original_delivery_date": str(target_delivery),
        "routes": [
            {
                "section_id": sec_cut.id,
                "status": "REQUIRED",
                "sequence_order": 1,
                "operations": [
                    {
                        "operation_name": "Laser Cut",
                        "unit": "PAIRS",
                        "required_quantity": 24000.0,
                    }
                ]
            }
        ]
    }

    r_order = client.post("/api/v1/orders", json=order_payload, headers=admin_hdr)
    assert r_order.status_code == 200
    order_data = r_order.json()
    order_id = order_data["id"]

    op = order_data["routes"][0]["operations"][0]
    assert op["balance_quantity"] == 24000.0
    assert order_data["remaining_working_days"] == 12
    assert op["daily_target"] == 2000.0

    # Enter production: 4,000 pairs produced today
    r_entry = client.post("/api/v1/production/entry", json={
        "entry_date": str(date.today()),
        "order_id": order_id,
        "route_id": order_data["routes"][0]["id"],
        "operation_id": op["id"],
        "quantity": 4000.0,
        "accepted_quantity": 4000.0,
        "rejected_quantity": 0.0,
        "unit": "PAIRS",
        "remarks": "Day 1 production"
    }, headers=supervisor_hdr)
    assert r_entry.status_code == 200

    # Recalculate
    r_recalc = client.get(f"/api/v1/orders/{order_id}", headers=admin_hdr)
    assert r_recalc.status_code == 200
    recalc_data = r_recalc.json()
    recalc_op = recalc_data["routes"][0]["operations"][0]

    # Balance is now 20,000
    assert recalc_op["balance_quantity"] == 20000.0
    # Remaining target recalculated using CEILING(20000 / remaining_days)
    assert recalc_op["daily_target"] == CalculationEngine.calculate_daily_target(
        20000.0, recalc_data["remaining_working_days"]
    )
