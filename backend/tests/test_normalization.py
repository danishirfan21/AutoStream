import pytest
from pydantic import ValidationError

from app.adapters import CsvFeedAdapter, MarketplaceJsonAdapter
from app.normalization import NormalizedVehicleRecord


def test_csv_adapter_normalizes_common_values() -> None:
    record = CsvFeedAdapter().normalize_record({
        "vin": " 1hgcm82633a004352 ", "year": "2023", "make": " Honda  ", "model": " Accord ",
        "trim": "EX", "price": "$28,500", "mileage": "12,400", "location": " Austin TX ",
        "updated_at": "2026-01-10T10:00:00Z",
    })
    assert record.vin == "1HGCM82633A004352"
    assert record.make == "Honda"
    assert record.price == 28500
    assert record.mileage == 12400


@pytest.mark.parametrize("vin", ["INVALIDVIN", "1HGCM82633A00435I", "1HGCM82633A00435"])
def test_invalid_vins_are_rejected(vin: str) -> None:
    with pytest.raises(ValidationError):
        NormalizedVehicleRecord(vin=vin)


def test_marketplace_json_adapter_maps_heterogeneous_fields() -> None:
    raw = {"listing_id": "mk-1001", "vehicle_vin": "1hgcm82633a004352", "model_year": "2023",
           "brand": " Honda ", "vehicle_model": "Accord", "variant": "EX-L", "asking_price": "$27,950",
           "odometer_miles": "12,100", "market": "Dallas, TX", "updated": "2026-08-01T10:30:00Z"}
    adapter = MarketplaceJsonAdapter()
    record = adapter.normalize_record(raw)
    assert (record.vin, record.make, record.trim, record.price, record.mileage) == ("1HGCM82633A004352", "Honda", "EX-L", 27950, 12100)
    assert adapter.source_record_id(raw, record) == "mk-1001"


def test_marketplace_json_adapter_requires_listing_id() -> None:
    record = NormalizedVehicleRecord(vin="1HGCM82633A004352")
    with pytest.raises(ValueError, match="listing_id"):
        MarketplaceJsonAdapter().source_record_id({}, record)
