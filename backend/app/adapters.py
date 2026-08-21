import csv
import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from app.normalization import NormalizedVehicleRecord, clean_text, parse_int, parse_price, parse_timestamp


class VehicleSourceAdapter(ABC):
    source_name: str
    can_update_canonical: bool = False

    @abstractmethod
    def fetch_records(self, path: Path) -> Iterable[dict]: ...

    @abstractmethod
    def normalize_record(self, raw: dict) -> NormalizedVehicleRecord: ...

    @abstractmethod
    def source_record_id(self, raw: dict, record: NormalizedVehicleRecord) -> str: ...


class CsvFeedAdapter(VehicleSourceAdapter):
    source_name = "dealer_csv"
    can_update_canonical = True

    def fetch_records(self, path: Path) -> Iterable[dict]:
        with path.open(newline="", encoding="utf-8") as feed:
            yield from csv.DictReader(feed)

    def normalize_record(self, raw: dict) -> NormalizedVehicleRecord:
        return NormalizedVehicleRecord(
            vin=raw.get("vin", ""), year=parse_int(raw.get("year")), make=clean_text(raw.get("make")),
            model=clean_text(raw.get("model")), trim=clean_text(raw.get("trim")),
            price=parse_price(raw.get("price")), mileage=parse_int(raw.get("mileage")),
            location=clean_text(raw.get("location")), source_timestamp=parse_timestamp(raw.get("updated_at")),
        )

    def source_record_id(self, raw: dict, record: NormalizedVehicleRecord) -> str:
        return record.vin


class MarketplaceJsonAdapter(VehicleSourceAdapter):
    source_name = "marketplace_json"

    def fetch_records(self, path: Path) -> Iterable[dict]:
        with path.open(encoding="utf-8") as feed:
            payload = json.load(feed)
        if not isinstance(payload, list):
            raise ValueError("Marketplace JSON feed must contain an array")
        for row in payload:
            if not isinstance(row, dict):
                raise ValueError("Marketplace JSON records must be objects")
            yield row

    def normalize_record(self, raw: dict) -> NormalizedVehicleRecord:
        return NormalizedVehicleRecord(
            vin=raw.get("vehicle_vin", ""), year=parse_int(raw.get("model_year")),
            make=clean_text(raw.get("brand")), model=clean_text(raw.get("vehicle_model")),
            trim=clean_text(raw.get("variant")), price=parse_price(raw.get("asking_price")),
            mileage=parse_int(raw.get("odometer_miles")), location=clean_text(raw.get("market")),
            source_timestamp=parse_timestamp(raw.get("updated")),
        )

    def source_record_id(self, raw: dict, record: NormalizedVehicleRecord) -> str:
        listing_id = clean_text(raw.get("listing_id"))
        if not listing_id:
            raise ValueError("Marketplace record requires listing_id")
        return listing_id
