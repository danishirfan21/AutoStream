import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vin: Mapped[str] = mapped_column(String(17), unique=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    trim: Mapped[str | None] = mapped_column(String(80))
    body_class: Mapped[str | None] = mapped_column(String(80))
    vehicle_type: Mapped[str | None] = mapped_column(String(80))
    fuel_type: Mapped[str | None] = mapped_column(String(80))
    engine_cylinders: Mapped[int | None] = mapped_column(Integer)
    engine_displacement: Mapped[float | None] = mapped_column(Numeric(4, 1))
    drive_type: Mapped[str | None] = mapped_column(String(80))
    transmission: Mapped[str | None] = mapped_column(String(80))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    plant_country: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (Index("ix_vehicles_make_model_year", "make", "model", "year"),)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    inserted_records: Mapped[int] = mapped_column(Integer, default=0)
    updated_records: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_records: Mapped[int] = mapped_column(Integer, default=0)
    invalid_records: Mapped[int] = mapped_column(Integer, default=0)
    failed_records: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class VehicleSourceRecord(Base):
    __tablename__ = "vehicle_source_records"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    source_name: Mapped[str] = mapped_column(String(50), index=True)
    source_record_id: Mapped[str] = mapped_column(String(160))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("source_name", "source_record_id", "payload_hash", name="uq_source_record_payload"),)


class VehiclePriceObservation(Base):
    __tablename__ = "vehicle_price_observations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    source_name: Mapped[str] = mapped_column(String(50), index=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), index=True)
    mileage: Mapped[int | None] = mapped_column(Integer, index=True)
    location: Mapped[str | None] = mapped_column(String(120))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (UniqueConstraint("vehicle_id", "source_name", "observed_at", "price", "mileage", name="uq_price_observation"),)


class IngestionError(Base):
    __tablename__ = "ingestion_errors"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="CASCADE"), index=True)
    source_record_id: Mapped[str | None] = mapped_column(String(160))
    error_type: Mapped[str] = mapped_column(String(80))
    error_message: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
