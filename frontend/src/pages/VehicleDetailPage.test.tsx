import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { VehicleDetailPage } from "./VehicleDetailPage";
vi.mock("../api/client", () => ({ getVehicle: vi.fn(), getMarketSnapshot: vi.fn(), getPriceHistory: vi.fn(), getVehicleSources: vi.fn(), getVehicleEnrichment: vi.fn() }));
import { getMarketSnapshot, getPriceHistory, getVehicle, getVehicleEnrichment, getVehicleSources } from "../api/client";
function mockBase(enrichment = [{ source_name: "nhtsa", status: "ok", selected_attributes: { BodyClass: "Sedan" }, fetched_at: "2026-01-01T00:00:00Z" }]) {
  vi.mocked(getVehicle).mockResolvedValue({ vin: "1HGCM82633A004352", year: 2003, make: "Honda", model: "Accord", trim: "EX" });
  vi.mocked(getMarketSnapshot).mockResolvedValue({ vin: "1HGCM82633A004352", latest_price: "27950.00", previous_price: "27900.00", price_change: "50.00", price_change_percent: 0.179, observation_count: 3, latest_mileage: 12100, latest_location: "Dallas, TX" });
  vi.mocked(getPriceHistory).mockResolvedValue([]); vi.mocked(getVehicleSources).mockResolvedValue([{ source_name: "dealer_csv", source_record_id: "dealer-1", source_timestamp: null, ingested_at: "2026-01-01T00:00:00Z" }]); vi.mocked(getVehicleEnrichment).mockResolvedValue(enrichment);
}
afterEach(() => vi.resetAllMocks());
test("renders money, observation count, provenance, and NHTSA data", async () => { mockBase(); render(<VehicleDetailPage vin="1HGCM82633A004352" />); expect(await screen.findByText("$27,950.00")).toBeInTheDocument(); expect(screen.getByText(/Previous \$27,900\.00/)).toBeInTheDocument(); expect(screen.getByText("1 canonical vehicle · 1 historical source records")).toBeInTheDocument(); expect(screen.getByText("Sedan")).toBeInTheDocument(); });
test("renders the missing enrichment state", async () => { mockBase([]); render(<VehicleDetailPage vin="1HGCM82633A004352" />); expect(await screen.findByText("No NHTSA enrichment available")).toBeInTheDocument(); });
