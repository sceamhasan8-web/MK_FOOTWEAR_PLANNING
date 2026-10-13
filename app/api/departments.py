from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.route import Category, Section, ProcessTemplate, UnitType, ProductionTargetSetting
from app.models.user import User, UserRole
from app.schemas.route import (
    CategoryOut,
    SectionOut,
    ProcessTemplateOut,
    ProductionTargetSettingOut,
    ProductionTargetSettingUpdate,
)
from app.api.deps import get_current_user, require_roles
from app.services.settings_service import SettingsService
from pydantic import BaseModel

router = APIRouter(prefix="/departments", tags=["Department & Process Structure"])


class CategoryCreate(BaseModel):
    name: str
    display_order: int = 0
    is_active: bool = True


class SectionCreate(BaseModel):
    category_id: int
    name: str
    display_order: int = 0
    is_active: bool = True


class ProcessTemplateCreate(BaseModel):
    section_id: int
    name: str
    default_unit: UnitType = UnitType.PAIRS
    display_order: int = 0
    is_active: bool = True


@router.get("/categories", response_model=List[CategoryOut])
def get_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Category).order_by(Category.display_order).all()


@router.post("/categories", response_model=CategoryOut)
def create_category(
    cat_in: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    cat = Category(**cat_in.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    cat_in: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    for k, v in cat_in.model_dump().items():
        setattr(cat, k, v)
    db.commit()
    db.refresh(cat)
    return cat


@router.get("/sections", response_model=List[SectionOut])
def get_sections(
    category_id: Optional[int] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Section)
    if category_id:
        query = query.filter(Section.category_id == category_id)
    if not include_inactive:
        query = query.filter(Section.is_active == True)
    return query.order_by(Section.display_order).all()


@router.post("/sections", response_model=SectionOut)
def create_section(
    sec_in: SectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    sec = Section(**sec_in.model_dump())
    db.add(sec)
    db.commit()
    db.refresh(sec)
    return sec


@router.put("/sections/{section_id}", response_model=SectionOut)
def update_section(
    section_id: int,
    sec_in: SectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    sec = db.query(Section).filter(Section.id == section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")
    for k, v in sec_in.model_dump().items():
        setattr(sec, k, v)
    db.commit()
    db.refresh(sec)
    return sec


@router.post("/templates", response_model=ProcessTemplateOut)
def create_process_template(
    tmpl_in: ProcessTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    tmpl = ProcessTemplate(**tmpl_in.model_dump())
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat.is_active = False
    db.commit()
    return {"detail": "Category deactivated successfully"}


@router.delete("/sections/{section_id}")
def delete_section(
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    sec = db.query(Section).filter(Section.id == section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")
    sec.is_active = False
    db.commit()
    return {"detail": "Section deactivated successfully"}


@router.get("/templates", response_model=List[ProcessTemplateOut])
def get_process_templates(
    section_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(ProcessTemplate)
    if section_id:
        query = query.filter(ProcessTemplate.section_id == section_id)
    return query.order_by(ProcessTemplate.display_order).all()


@router.put("/templates/{template_id}", response_model=ProcessTemplateOut)
def update_process_template(
    template_id: int,
    tmpl_in: ProcessTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    tmpl = db.query(ProcessTemplate).filter(ProcessTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    for k, v in tmpl_in.model_dump().items():
        setattr(tmpl, k, v)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.delete("/templates/{template_id}")
def delete_process_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    tmpl = db.query(ProcessTemplate).filter(ProcessTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    tmpl.is_active = False
    db.commit()
    return {"detail": "Process template deactivated successfully"}


# -------------------------------------------------------------------------
# PRODUCTION TARGET SETTINGS (Minimum Daily Target per Section)
# -------------------------------------------------------------------------
DEFAULT_SECTION_MINIMUMS = {
    "Cutting": 2000,
    "Printing": 1500,
    "Emboss": 1000,
    "Embosse": 1000,
    "Sewing": 2000,
    "Lasting": 2000,
}


@router.get("/target-settings", response_model=List[ProductionTargetSettingOut])
def get_production_target_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns configured Minimum Daily Targets for all production sections.
    Ensures every section has an active or configurable target setting row.
    """
    sections = db.query(Section).filter(Section.is_active == True).order_by(
        Section.category_id, Section.display_order, Section.id
    ).all()

    existing_settings = {
        s.section_id: s
        for s in db.query(ProductionTargetSetting).all()
    }

    result = []
    for sec in sections:
        setting = existing_settings.get(sec.id)
        if not setting:
            # Auto-initialize with standard factory default or 0
            default_target = DEFAULT_SECTION_MINIMUMS.get(sec.name, 0)
            setting = ProductionTargetSetting(
                section_id=sec.id,
                minimum_daily_target=default_target,
                unit="Pairs/day",
                is_active=True,
                notes="Initial section target setting",
                updated_by_id=current_user.id
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
            existing_settings[sec.id] = setting

        cat_name = sec.category.name if sec.category else "General"
        updater = setting.updated_by.username if setting.updated_by else "System"

        result.append(ProductionTargetSettingOut(
            id=setting.id,
            section_id=sec.id,
            section_name=sec.name,
            category_id=sec.category_id,
            category_name=cat_name,
            minimum_daily_target=setting.minimum_daily_target,
            maximum_daily_target=setting.maximum_daily_target or 0,
            calculation_mode=setting.calculation_mode or "BALANCED",
            override_policy=setting.override_policy or "ALLOWED",
            unit=setting.unit or "Pairs/day",
            is_active=setting.is_active,
            notes=setting.notes,
            updated_at=setting.updated_at,
            updated_by_id=setting.updated_by_id,
            updated_by_username=updater
        ))

    return result


@router.put("/target-settings/{section_id}", response_model=ProductionTargetSettingOut)
def update_production_target_setting(
    section_id: int,
    setting_in: ProductionTargetSettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.PLANNING_MANAGER]))
):
    """
    Sets or updates the daily targets for a section with min <= max validation and audit recording.
    """
    try:
        sec_id = section_id or setting_in.section_id
        if not sec_id:
            raise HTTPException(status_code=400, detail="Section ID is required")
        res = SettingsService.update_section_target_setting(
            db=db,
            section_id=sec_id,
            min_target=setting_in.minimum_daily_target,
            max_target=setting_in.maximum_daily_target or 0,
            unit=setting_in.unit or "Pairs/day",
            calculation_mode=setting_in.calculation_mode or "BALANCED",
            override_policy=setting_in.override_policy or "ALLOWED",
            is_active=setting_in.is_active,
            notes=setting_in.notes,
            user_id=current_user.id,
            reason="Updated target limits via departments endpoint"
        )
        return res
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


