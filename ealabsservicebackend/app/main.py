# app/main.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal, Annotated

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import (
    create_engine,
    String,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    func,
    select,
    Index,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
    Session,
)
from .database import Base as AuthBase, engine as AuthEngine, SessionLocal as AuthSession
from .routers import customers, files, plates, search, service_orders, smart, vehicles
from .routers import auth_routes, admin_users, ai_imports, export
from .models import Role, User, UserRole 
from .auth import hash_password
import os
from app.ai.router import router as ai_router

# ========= DB SETUP =========
DB_URL = "sqlite:///./service.db"  # proje kökünde service.db dosyası oluşur.
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(20), default="person")  # person | company
    name: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    orders: Mapped[List[Order]] = relationship(back_populates="customer", cascade="all,delete")

    __table_args__ = (
        Index("ix_customer_name", "name"),
    )


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    plate: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    orders: Mapped[List[Order]] = relationship(back_populates="vehicle", cascade="all,delete")

    __table_args__ = (
        Index("ix_plate_unique", "plate"),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"))

    started_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=datetime.utcnow)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | closed

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped[Customer] = relationship(back_populates="orders")
    vehicle: Mapped[Vehicle] = relationship(back_populates="orders")
    items: Mapped[List[OrderItem]] = relationship(back_populates="order", cascade="all,delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16))  # part | labor
    name: Mapped[str] = mapped_column(String(255))
    qty: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float] = mapped_column(Float, default=0.0)

    order: Mapped[Order] = relationship(back_populates="items")


def create_db():
    Base.metadata.create_all(engine)


# ========= Pydantic Schemas =========
class OrderItemIn(BaseModel):
    type: Literal["part", "labor"]
    name: str
    qty: int = Field(ge=1)
    price: float = Field(ge=0)


class CustomerIn(BaseModel):
    type: Literal["person", "company"]
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None


class VehicleIn(BaseModel):
    plate: str
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    km: Optional[int] = None


class ServiceOrderIn(BaseModel):
    customer: CustomerIn
    vehicle: VehicleIn
    startedAt: datetime
    notes: Optional[str] = None
    items: List[OrderItemIn]
    status: Optional[Literal["open", "closed"]] = "open"


# Out models (ORM'den dönmek için from_attributes=True önemli)
class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: Literal["part", "labor"]
    name: str
    qty: int
    price: float


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: Literal["person", "company"]
    name: str
    phone: Optional[str]
    email: Optional[str]


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate: str
    brand: Optional[str]
    model: Optional[str]
    year: Optional[int]
    km: Optional[int]


class ServiceOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    startedAt: datetime = Field(alias="started_at")
    notes: Optional[str]
    status: Literal["open", "closed"]
    created_at: datetime
    updated_at: datetime
    total: float

    customer: CustomerOut
    vehicle: VehicleOut
    items: List[OrderItemOut]


# ========= Utils / Dependencies =========
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def compute_total(items: List[OrderItem]) -> float:
    return round(sum(i.qty * (i.price or 0) for i in items), 2)


def upsert_customer(db: Session, payload: CustomerIn) -> Customer:
    existing = db.scalar(
        select(Customer).where(func.lower(Customer.name) == payload.name.strip().lower())
    )
    if existing:
        # varsa hafif güncelle
        existing.type = payload.type
        if payload.phone:
            existing.phone = payload.phone
        if payload.email:
            existing.email = payload.email
        return existing
    c = Customer(
        type=payload.type,
        name=payload.name.strip(),
        phone=payload.phone,
        email=payload.email,
    )
    db.add(c)
    db.flush()
    return c


def upsert_vehicle(db: Session, payload: VehicleIn) -> Vehicle:
    plate = payload.plate.strip().upper()
    existing = db.scalar(select(Vehicle).where(Vehicle.plate == plate))
    if existing:
        # varsa güncelle (boş olmayanları yaz)
        if payload.brand:
            existing.brand = payload.brand
        if payload.model:
            existing.model = payload.model
        if payload.year is not None:
            existing.year = payload.year
        if payload.km is not None:
            existing.km = payload.km
        return existing
    v = Vehicle(
        plate=plate,
        brand=payload.brand,
        model=payload.model,
        year=payload.year,
        km=payload.km,
    )
    db.add(v)
    db.flush()
    return v


# ========= App =========
app = FastAPI(
    title="EaLabs Service API",
    version="1.0.0",
    contact={"name": "EaLabs", "email": "edizates16@icloud.com"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_db()
    # örnek lookup için bir araç seed (sadece yoksa)
    with SessionLocal() as db:
        if not db.scalar(select(Vehicle).where(Vehicle.plate == "PB7219KE")):
            db.add(Vehicle(plate="PB7219KE", brand="FORD", model="FOCUS", year=2009))
            db.commit()


# ========= Health / Root =========
@app.get("/", tags=["meta"])
def root():
    return {"ok": True, "service": "EaLabs Service API", "time": datetime.utcnow().isoformat()}


@app.get("/health", tags=["meta"])
def health():
    return {"status": "healthy"}


# ========= Vehicles =========
@app.get("/vehicles/by-plate/{plate}", response_model=Optional[VehicleOut], tags=["vehicles"])
def vehicle_by_plate(plate: str, db: Session = Depends(get_db)):
    v = db.scalar(select(Vehicle).where(Vehicle.plate == plate.strip().upper()))
    return v  # None dönerse 200 + null


@app.get("/vehicles/{vehicle_id}", response_model=VehicleOut, tags=["vehicles"])
def vehicle_get(vehicle_id: int, db: Session = Depends(get_db)):
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    return v


# ========= Customers =========
@app.get("/customers/search", response_model=List[CustomerOut], tags=["customers"])
def customer_search(q: Annotated[str, Query(min_length=1)], limit: int = 10, db: Session = Depends(get_db)):
    ql = f"%{q.lower()}%"
    rows = db.scalars(select(Customer).where(func.lower(Customer.name).like(ql)).limit(limit)).all()
    return rows


# ========= Orders =========
def order_to_out(o: Order) -> ServiceOrderOut:
    # manual map: Pydantic alias (startedAt) için started_at alan adı korunur
    return ServiceOrderOut(
        id=o.id,
        started_at=o.started_at,
        notes=o.notes,
        status=o.status,  # type: ignore
        created_at=o.created_at,
        updated_at=o.updated_at,
        total=compute_total(o.items),
        customer=o.customer,
        vehicle=o.vehicle,
        items=o.items,
    )


@app.get("/orders", response_model=List[ServiceOrderOut], tags=["orders"])
def orders_list(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    plate: Optional[str] = None,
    status: Optional[Literal["open", "closed"]] = None,
):
    stmt = select(Order).order_by(Order.created_at.desc())
    if plate:
        stmt = stmt.join(Order.vehicle).where(Vehicle.plate == plate.strip().upper())
    if status:
        stmt = stmt.where(Order.status == status)

    stmt = stmt.limit(size).offset((page - 1) * size)
    rows = db.scalars(stmt).unique().all()
    return [order_to_out(o) for o in rows]


@app.get("/orders/{order_id}", response_model=ServiceOrderOut, tags=["orders"])
def orders_get(order_id: int, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    return order_to_out(o)


@app.get("/orders/by-plate/{plate}", response_model=List[ServiceOrderOut], tags=["orders"])
def orders_by_plate(plate: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Order).join(Order.vehicle).where(Vehicle.plate == plate.strip().upper()).order_by(Order.created_at.desc())
    ).unique().all()
    return [order_to_out(o) for o in rows]


@app.post("/orders", response_model=ServiceOrderOut, tags=["orders"])
def orders_create(payload: ServiceOrderIn, db: Session = Depends(get_db)):
    customer = upsert_customer(db, payload.customer)
    vehicle = upsert_vehicle(db, payload.vehicle)

    o = Order(
        customer=customer,
        vehicle=vehicle,
        started_at=payload.startedAt,
        notes=payload.notes,
        status=payload.status or "open",
    )
    db.add(o)
    db.flush()  # o.id

    for it in payload.items:
        db.add(OrderItem(order=o, type=it.type, name=it.name, qty=it.qty, price=it.price))

    db.commit()
    db.refresh(o)
    return order_to_out(o)


class OrderUpdateIn(BaseModel):
    notes: Optional[str] = None
    status: Optional[Literal["open", "closed"]] = None
    items: Optional[List[OrderItemIn]] = None


@app.put("/orders/{order_id}", response_model=ServiceOrderOut, tags=["orders"])
def orders_update(order_id: int, payload: OrderUpdateIn, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")

    if payload.notes is not None:
        o.notes = payload.notes
    if payload.status is not None:
        o.status = payload.status

    if payload.items is not None:
        # tüm kalemleri sıfırla ve yeniden yaz (basit yaklaşım)
        for ex in list(o.items):
            db.delete(ex)
        for it in payload.items:
            db.add(OrderItem(order=o, type=it.type, name=it.name, qty=it.qty, price=it.price))

    db.commit()
    db.refresh(o)
    return order_to_out(o)


@app.delete("/orders/{order_id}", tags=["orders"])
def orders_delete(order_id: int, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    db.delete(o)
    db.commit()
    return {"ok": True, "deleted_id": order_id}

@app.on_event("startup")
def on_startup_auth_seed():
    # 1) Auth tablolarını oluştur
    AuthBase.metadata.create_all(bind=AuthEngine)

    # 2) OWNER + AI_DIRECTOR seed
    owner_email = os.getenv("OWNER_EMAIL")
    owner_pass  = os.getenv("OWNER_PASSWORD")
    if owner_email and owner_pass:
        db = AuthSession()
        try:
            # Roller
            owner = db.query(Role).filter(Role.name == "OWNER").first()
            if not owner:
                owner = Role(name="OWNER")
                db.add(owner)
                db.flush()

            ai = db.query(Role).filter(Role.name == "AI_DIRECTOR").first()
            if not ai:
                ai = Role(name="AI_DIRECTOR")
                db.add(ai)
                db.flush()

            staff = db.query(Role).filter(Role.name == "STAFF").first()
            if not staff:
                staff = Role(name="STAFF")
                db.add(staff)
                db.flush()

            # Kullanıcı
            u = db.query(User).filter(User.email == owner_email).first()
            if not u:
                u = User(email=owner_email, name="Owner", password_hash=hash_password(owner_pass))
                db.add(u)
                db.flush()
                # OWNER + AI_DIRECTOR rolleri
                db.add(UserRole(user_id=u.id, role_id=owner.id))
                db.add(UserRole(user_id=u.id, role_id=ai.id))

            db.commit()
        finally:
            db.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080","http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(admin_users.router)
app.include_router(ai_imports.router)
app.include_router(ai_router)
app.include_router(export.router)