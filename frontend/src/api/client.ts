import type { MarketSnapshot, MarketSummary, PriceObservation, Vehicle, VehicleEnrichment, VehicleFilters, VehicleSource } from "./types";

const baseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function getMarketSummary() { return request<MarketSummary>("/api/v1/analytics/market-summary"); }
export function getVehicle(vin: string) { return request<Vehicle>(`/api/v1/vehicles/${encodeURIComponent(vin)}`); }
export function getMarketSnapshot(vin: string) { return request<MarketSnapshot>(`/api/v1/vehicles/${encodeURIComponent(vin)}/market-snapshot`); }
export function getPriceHistory(vin: string) { return request<PriceObservation[]>(`/api/v1/vehicles/${encodeURIComponent(vin)}/price-history`); }
export function getVehicleSources(vin: string) { return request<VehicleSource[]>(`/api/v1/vehicles/${encodeURIComponent(vin)}/sources`); }
export function getVehicleEnrichment(vin: string) { return request<VehicleEnrichment[]>(`/api/v1/vehicles/${encodeURIComponent(vin)}/enrichment`); }

export function getVehicles(filters: VehicleFilters = {}) {
  const query = new URLSearchParams();
  if (filters.make) query.set("make", filters.make);
  if (filters.model) query.set("model", filters.model);
  if (filters.year) query.set("year", String(filters.year));
  const suffix = query.size ? `?${query}` : "";
  return request<Vehicle[]>(`/api/v1/vehicles${suffix}`);
}
