import enum
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


class SectionRouteStatus(str, enum.Enum):
    REQUIRED = "REQUIRED"
    NOT_REQUIRED = "NOT_REQUIRED"
    COMPLETED = "COMPLETED"


class OperationStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class UnitType(str, enum.Enum):
    PAIRS = "PAIRS"
    PIECES = "PIECES"
    SETS = "SETS"


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    sections = relationship("Section", back_populates="category", cascade="all, delete-orphan", order_by="Section.display_order")


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    planning_id = Column(Integer, nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    counting_unit = Column(String(50), default="Pairs", nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    @property
    def effective_planning_id(self) -> int:
        if self.planning_id is not None and self.planning_id > 0:
            return self.planning_id
        if self.display_order is not None and self.display_order > 0:
            return self.display_order
        return self.id

    category = relationship("Category", back_populates="sections")
    templates = relationship("ProcessTemplate", back_populates="section", cascade="all, delete-orphan", order_by="ProcessTemplate.display_order")


class ProcessTemplate(Base):
    """Default operations configured for a section (e.g. Operation 1, Operation 2, etc.)"""
    __tablename__ = "process_templates"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    default_unit = Column(Enum(UnitType), default=UnitType.PAIRS, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    section = relationship("Section", back_populates="templates")


class OrderRoute(Base):
    """Order-specific route configuration per section. Preserves order snapshot."""
    __tablename__ = "order_routes"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False, index=True)
    status = Column(Enum(SectionRouteStatus), default=SectionRouteStatus.REQUIRED, nullable=False)
    sequence_order = Column(Integer, default=0, nullable=False)
    serial_no = Column(Integer, nullable=True)
    transfer_rule = Column(String(50), default="IMMEDIATE", nullable=False)
    has_components = Column(Boolean, default=False, nullable=False)
    minimum_daily_target = Column(Integer, nullable=True)  # Order-specific override
    maximum_daily_target = Column(Integer, nullable=True)  # Order-specific override
    calculation_mode = Column(String(50), nullable=True)  # Order-specific override
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    order = relationship("Order", back_populates="routes")
    section = relationship("Section")
    operations = relationship("OrderOperation", back_populates="route", cascade="all, delete-orphan", order_by="OrderOperation.sequence_order")


class OrderOperation(Base):
    """Sub-process / operation tracked within an order's section."""
    __tablename__ = "order_operations"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("order_routes.id"), nullable=False, index=True)
    operation_name = Column(String(150), nullable=False)
    sequence_order = Column(Integer, default=0, nullable=False)
    unit = Column(Enum(UnitType), default=UnitType.PAIRS, nullable=False)
    required_quantity = Column(Float, nullable=False, default=0.0)
    completed_quantity = Column(Float, nullable=False, default=0.0)  # Cached rollup
    rejected_quantity = Column(Float, nullable=False, default=0.0)
    balance_quantity = Column(Float, nullable=False, default=0.0)
    start_date = Column(Date, nullable=True)
    expected_finish_date = Column(Date, nullable=True)
    status = Column(Enum(OperationStatus), default=OperationStatus.PENDING, nullable=False)
    notes = Column(Text, nullable=True)

    route = relationship("OrderRoute", back_populates="operations")
    components = relationship("OperationComponent", back_populates="operation", cascade="all, delete-orphan")
    entries = relationship("DailyProductionEntry", back_populates="operation", cascade="all, delete-orphan")


class OperationComponent(Base):
    """Component-wise tracking for footwear parts (e.g. Back, Collar, Side part, Toe cap)."""
    __tablename__ = "operation_components"

    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(Integer, ForeignKey("order_operations.id"), nullable=False, index=True)
    component_name = Column(String(100), nullable=False)
    unit = Column(Enum(UnitType), default=UnitType.PIECES, nullable=False)
    pieces_per_pair = Column(Float, default=1.0, nullable=False)  # Conversion factor
    required_total_qty = Column(Float, nullable=False, default=0.0)
    accepted_total_qty = Column(Float, nullable=False, default=0.0)
    rejected_total_qty = Column(Float, nullable=False, default=0.0)
    balance_total_qty = Column(Float, nullable=False, default=0.0)

    operation = relationship("OrderOperation", back_populates="components")
    entries = relationship("DailyProductionEntry", back_populates="component")


class ProductionTargetSetting(Base):
    """
    Dedicated Minimum and Maximum Daily Production Target configuration per section.
    Supports factory-wide target rules and calculation modes.
    Order-specific overrides can be set on OrderRoute.
    """
    __tablename__ = "production_target_settings"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), unique=True, nullable=False, index=True)
    minimum_daily_target = Column(Integer, default=0, nullable=False)
    maximum_daily_target = Column(Integer, default=0, nullable=False)  # 0 = unlimited capacity
    calculation_mode = Column(String(50), default="BALANCED", nullable=False)  # BALANCED, MINIMUM_DRIVEN, SHIPMENT_PRIORITY, MANUAL
    override_policy = Column(String(50), default="ALLOWED", nullable=False)  # ALLOWED, RESTRICTED, SUPERVISOR_APPROVAL
    unit = Column(String(50), default="Pairs/day", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    section = relationship("Section")
    updated_by = relationship("User")

