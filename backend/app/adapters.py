import csv
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from app.normalization import NormalizedVehicleRecord, clean_text, parse_int, parse_price, parse_timestamp


class VehicleSourceAdapter(ABC):
    source_name: str

    @abstractmethod
    def fetch_records(self, path: Path) -> Iterable[dict]: ...

    @abstractmethod
    def normalize_record(self, raw: dict) -> NormalizedVehicleRecord: ...


class CsvFeedAdapter(VehicleSourceAdapter):
    source_name = "dealer_csv"

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
