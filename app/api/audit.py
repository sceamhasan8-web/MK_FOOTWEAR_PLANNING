from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.audit import AuditLog
from app.models.user import User, UserRole
from app.api.deps import require_roles
from pydantic import BaseModel

router = APIRouter(prefix="/audit", tags=["Audit History"])


class AuditLogOut(BaseModel):
    id: int
    entity_name: str
    entity_id: Optional[int]
    action: str
    user_id: Optional[int]
    user_name: Optional[str] = None
    timestamp: datetime
    details: Optional[str]
    reason: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=List[AuditLogOut])
def get_audit_logs(
    entity_name: Optional[str] = None,
    entity_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    query = db.query(AuditLog)
    if entity_name:
        query = query.filter(AuditLog.entity_name == entity_name)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if action:
        query = query.filter(AuditLog.action == action)

    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    results = []
    for l in logs:
        results.append(
            AuditLogOut(
                id=l.id,
                entity_name=l.entity_name,
                entity_id=l.entity_id,
                action=l.action,
                user_id=l.user_id,
                user_name=l.user.full_name if l.user else None,
                timestamp=l.timestamp,
                details=l.details,
                reason=l.reason,
            )
        )
    return results
