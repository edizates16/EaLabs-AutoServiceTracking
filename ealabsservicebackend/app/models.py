import uuid
from sqlalchemy import Column, String, DateTime, Integer, Text, Float, Numeric, Date, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
from datetime import datetime

def uuid_col(primary=False):
    return Column(String, primary_key=primary, default=lambda: str(uuid.uuid4()))

class Customer(Base):
    __tablename__ = "customers"
    id = uuid_col(True)
    name = Column(String, nullable=False, index=True)
    phone = Column(String)
    email = Column(String)  # NEW
    type = Column(String, default="individual")
    created_at = Column(DateTime, server_default=func.now())
    ownerships = relationship("Ownership", back_populates="customer")

class Vehicle(Base):
    __tablename__ = "vehicles"
    id = uuid_col(True)
    vin = Column(String, unique=True, nullable=True)
    brand = Column(String)
    model = Column(String)
    year = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    plates = relationship("Plate", back_populates="vehicle", cascade="all, delete-orphan")
    ownerships = relationship("Ownership", back_populates="vehicle", cascade="all, delete-orphan")
    service_orders = relationship("ServiceOrder", back_populates="vehicle", cascade="all, delete-orphan")

class Plate(Base):
    __tablename__ = "plates"
    id = uuid_col(True)
    vehicle_id = Column(String, ForeignKey("vehicles.id"), nullable=False)
    plate_normalized = Column(String, nullable=False, index=True)
    valid_from = Column(Date, nullable=False, server_default=func.current_date())
    valid_to = Column(Date)
    vehicle = relationship("Vehicle", back_populates="plates")

class Ownership(Base):
    __tablename__ = "ownerships"
    id = uuid_col(True)
    vehicle_id = Column(String, ForeignKey("vehicles.id"), nullable=False)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    from_date = Column(Date, nullable=False, server_default=func.current_date())
    to_date = Column(Date)
    vehicle = relationship("Vehicle", back_populates="ownerships")
    customer = relationship("Customer", back_populates="ownerships")

class ServiceOrder(Base):
    __tablename__ = "service_orders"
    id = uuid_col(True)
    vehicle_id = Column(String, ForeignKey("vehicles.id"), nullable=False)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    opened_at = Column(DateTime, nullable=False, server_default=func.now())
    closed_at = Column(DateTime)
    odometer_km = Column(Integer)
    status = Column(String, default="open")  # open|completed|cancelled
    notes = Column(Text)
    source = Column(String, default="manual")  # manual|ocr
    vehicle = relationship("Vehicle", back_populates="service_orders")
    items = relationship("ServiceItem", back_populates="order", cascade="all, delete-orphan")

class ServiceItem(Base):
    __tablename__ = "service_items"
    id = uuid_col(True)
    service_order_id = Column(String, ForeignKey("service_orders.id"), nullable=False)
    type = Column(String, nullable=False)  # labor | part
    description = Column(String, nullable=False)
    qty = Column(Float, default=1.0)
    unit_price = Column(Numeric(12, 2), default=0)
    vat_rate = Column(Float, default=0.20)
    order = relationship("ServiceOrder", back_populates="items")

class File(Base):
    __tablename__ = "files"
    id = uuid_col(True)
    path = Column(String, nullable=False)
    kind = Column(String, default="scan")  # scan|photo|pdf
    status = Column(String, default="raw")  # raw|linked
    service_order_id = Column(String, ForeignKey("service_orders.id"))
    vehicle_id = Column(String, ForeignKey("vehicles.id"))
    created_at = Column(DateTime, server_default=func.now())

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)  # OWNER, AI_DIRECTOR, STAFF, READONLY

class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"))
    user = relationship("User", back_populates="roles")
    role = relationship("Role")
    __table_args__ = (UniqueConstraint('user_id', 'role_id', name='uq_user_role'),)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String(100), nullable=False)
    entity = Column(String(100), nullable=True)
    entity_id = Column(Integer, nullable=True)
    meta = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ImportedDocument(Base):
    __tablename__ = "imported_documents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    status = Column(String(20), default="queued")  # queued/parsed/failed
    original_url = Column(String(512))
    parsed_json = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)