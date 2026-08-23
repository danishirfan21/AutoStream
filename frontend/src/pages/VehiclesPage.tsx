import { FormEvent, useEffect, useState } from "react";
import { getVehicles } from "../api/client";
import type { Vehicle, VehicleFilters } from "../api/types";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { vehicleLabel } from "../utils/format";

export function VehiclesPage() {
  const [draft, setDraft] = useState<VehicleFilters>({}); const [filters, setFilters] = useState<VehicleFilters>({});
  const [vehicles, setVehicles] = useState<Vehicle[]>(); const [error, setError] = useState<string>();
  useEffect(() => { setVehicles(undefined); setError(undefined); getVehicles(filters).then(setVehicles).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unknown error")); }, [filters]);
  function apply(event: FormEvent) { event.preventDefault(); setFilters(draft); }
  return <><h1>Vehicles</h1><form className="filters" onSubmit={apply}>
    <input aria-label="Make" placeholder="Make" value={draft.make ?? ""} onChange={(event) => setDraft({ ...draft, make: event.target.value || undefined })} />
    <input aria-label="Model" placeholder="Model" value={draft.model ?? ""} onChange={(event) => setDraft({ ...draft, model: event.target.value || undefined })} />
    <input aria-label="Year" placeholder="Year" inputMode="numeric" value={draft.year ?? ""} onChange={(event) => setDraft({ ...draft, year: event.target.value ? Number(event.target.value) : undefined })} />
    <button type="submit">Apply filters</button></form>
    {error ? <ErrorState message={error} /> : !vehicles ? <LoadingState label="Loading vehicles…" /> : vehicles.length === 0 ? <p className="state">No vehicles match those filters.</p> : <table><thead><tr><th>VIN</th><th>Vehicle</th></tr></thead><tbody>{vehicles.map((vehicle) => <tr key={vehicle.vin}><td><a href={`/vehicles/${vehicle.vin}`}>{vehicle.vin}</a></td><td>{vehicleLabel(vehicle)}</td></tr>)}</tbody></table>}
  </>;
}
