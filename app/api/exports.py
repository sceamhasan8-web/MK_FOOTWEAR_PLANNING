from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.order import Order
from app.models.user import User
from app.api.deps import get_current_user
from app.services.export_service import ExportService

router = APIRouter(prefix="/exports", tags=["Reports & Exports"])


@router.get("/orders/{order_id}/xlsx")
def export_order_planning_xlsx(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    excel_stream = ExportService.generate_order_planning_xlsx(db, order)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    filename = f"Planning_{order.order_code}_{timestamp}.xlsx"

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/orders/{order_id}/csv")
def export_order_csv(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    csv_data = ExportService.generate_order_csv(db, order)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    filename = f"Order_{order.order_code}_{timestamp}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/planning/xlsx")
def export_category_flow_planning_xlsx(
    order_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    excel_stream = ExportService.generate_category_flow_planning_xlsx(db, order_id=order_id)
    filename = "Production_Planning.xlsx"

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/orders/{order_id}/matrix-planning/xlsx")
def export_matrix_planning_xlsx(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Downloads the 5-sheet Date-Wise TG / ON HAND / O/T Planning XLSX workbook (Sections 39, 40).
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    excel_stream = ExportService.generate_matrix_planning_xlsx(db, order)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    filename = f"Planning_Matrix_{order.order_code}_{timestamp}.xlsx"

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/orders/{order_id}/matrix-planning/csv")
def export_matrix_planning_csv(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Downloads CSV of the Date-Wise TG / ON HAND / O/T planning matrix.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    csv_data = ExportService.generate_matrix_planning_csv(db, order)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    filename = f"Planning_Matrix_{order.order_code}_{timestamp}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/orders/{order_id}/wip-flow/xlsx")
def export_wip_flow_xlsx(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Downloads the authoritative 5-sheet Serial WIP Flow Planning XLSX workbook (Sections 43 & 44).
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    excel_stream = ExportService.generate_wip_flow_xlsx(db, order)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    filename = f"WIP_Flow_{order.order_code}_{timestamp}.xlsx"

    return StreamingResponse(
        excel_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/orders/{order_id}/wip-flow/csv")
def export_wip_flow_csv(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Downloads CSV of the Serial WIP Flow Planning Sheet.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    csv_data = ExportService.generate_wip_flow_csv(db, order)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    filename = f"WIP_Flow_{order.order_code}_{timestamp}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )



