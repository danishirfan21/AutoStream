import re
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, field_validator

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def clean_text(value: object | None) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return " ".join(str(value).strip().split())


def parse_int(value: object | None) -> int | None:
    text = clean_text(value)
    return int(re.sub(r"[^0-9-]", "", text)) if text else None


def parse_price(value: object | None) -> Decimal | None:
    text = clean_text(value)
    return Decimal(re.sub(r"[^0-9.]", "", text)) if text else None


def parse_timestamp(value: object | None) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class NormalizedVehicleRecord(BaseModel):
    vin: str
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    manufacturer: str | None = None
    price: Decimal | None = None
    mileage: int | None = None
    location: str | None = None
    source_timestamp: datetime | None = None

    @field_validator("vin")
    @classmethod
    def normalize_vin(cls, value: str) -> str:
        vin = value.strip().upper()
        if not VIN_RE.fullmatch(vin):
            raise ValueError("VIN must be 17 characters and exclude I, O, and Q")
        return vin
