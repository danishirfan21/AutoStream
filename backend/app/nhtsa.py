import hashlib
import json

import httpx


class NhtsaClient:
    base_url = "https://vpic.nhtsa.dot.gov/api/vehicles"

    async def decode_vin(self, vin: str) -> tuple[dict, dict]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10), headers={"User-Agent": "AutoStream/0.1"}) as client:
            response = await client.get(f"{self.base_url}/DecodeVinValuesExtended/{vin}?format=json")
        if response.status_code != 200:
            raise RuntimeError(f"NHTSA returned HTTP {response.status_code}")
        payload = response.json()
        results = payload.get("Results")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            raise ValueError("NHTSA response has no decode result")
        row = results[0]
        selected = {key: row.get(key) for key in ("Make", "Model", "ModelYear", "Manufacturer", "VehicleType", "BodyClass", "FuelTypePrimary", "DriveType", "EngineCylinders", "PlantCountry") if row.get(key) not in (None, "")}
        return selected, payload


def enrichment_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
