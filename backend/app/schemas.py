from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_name: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    total_records: int
    inserted_records: int
    updated_records: int
    duplicate_records: int
    invalid_records: int
    failed_records: int
    error_message: str | None


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    vin: str
    year: int | None
    make: str | None
    model: str | None
    trim: str | None


class ErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source_record_id: str | None
    error_type: str
    error_message: str
    created_at: datetime
