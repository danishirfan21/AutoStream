import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { OverviewPage } from "./OverviewPage";

vi.mock("../api/client", () => ({ getMarketSummary: vi.fn() }));
import { getMarketSummary } from "../api/client";
afterEach(() => vi.resetAllMocks());

test("renders market summary data", async () => {
  vi.mocked(getMarketSummary).mockResolvedValue({ total_vehicles: 4, total_source_records: 6, total_price_observations: 7, average_latest_price: "27950.00", min_latest_price: "21000.00", max_latest_price: "35000.00" });
  render(<OverviewPage />);
  expect(await screen.findByText("Canonical vehicles")).toBeInTheDocument();
  expect(screen.getByText("$27,950.00")).toBeInTheDocument();
});
test("renders an API error", async () => {
  vi.mocked(getMarketSummary).mockRejectedValue(new Error("Service unavailable"));
  render(<OverviewPage />);
  expect(await screen.findByText(/Unable to load data: Service unavailable/)).toBeInTheDocument();
});
