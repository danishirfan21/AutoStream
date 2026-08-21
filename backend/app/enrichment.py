from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vehicle, VehicleEnrichment
from app.nhtsa import NhtsaClient, enrichment_hash


async def enrich_nhtsa(session: AsyncSession, vin: str, client: NhtsaClient | None = None) -> VehicleEnrichment:
    vehicle = await session.scalar(select(Vehicle).where(Vehicle.vin == vin.upper()))
    if not vehicle:
        raise LookupError("Vehicle not found")
    selected, payload = await (client or NhtsaClient()).decode_vin(vehicle.vin)
    digest = enrichment_hash(payload)
    existing = await session.scalar(select(VehicleEnrichment).where(VehicleEnrichment.vehicle_id == vehicle.id, VehicleEnrichment.source_name == "nhtsa_vpic", VehicleEnrichment.payload_hash == digest))
    if existing:
        return existing
    fill = {"manufacturer": selected.get("Manufacturer"), "body_class": selected.get("BodyClass"), "vehicle_type": selected.get("VehicleType"), "fuel_type": selected.get("FuelTypePrimary"), "drive_type": selected.get("DriveType"), "plant_country": selected.get("PlantCountry")}
    for key, value in fill.items():
        if value and getattr(vehicle, key) is None:
            setattr(vehicle, key, value)
    enrichment = VehicleEnrichment(vehicle_id=vehicle.id, payload_hash=digest, selected_attributes=selected, raw_payload=payload)
    session.add(enrichment)
    await session.commit()
    await session.refresh(enrichment)
    return enrichment
