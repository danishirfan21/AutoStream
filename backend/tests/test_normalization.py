import pytest
from pydantic import ValidationError

from app.adapters import CsvFeedAdapter
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
