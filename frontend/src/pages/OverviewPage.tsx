import { useEffect, useState } from "react";
import { getMarketSummary } from "../api/client";
import type { MarketSummary } from "../api/types";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { MetricCard } from "../components/MetricCard";
import { formatMoney } from "../utils/format";

export function OverviewPage() {
  const [summary, setSummary] = useState<MarketSummary>();
  const [error, setError] = useState<string>();
  useEffect(() => { getMarketSummary().then(setSummary).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unknown error")); }, []);
  if (error) return <ErrorState message={error} />;
  if (!summary) return <LoadingState label="Loading market overview…" />;
  return <>
    <h1>Market overview</h1><p>Canonical vehicles are deduplicated by VIN while every source payload and price observation remains available.</p>
    <div className="cards">
      <MetricCard label="Canonical vehicles" value={summary.total_vehicles} />
      <MetricCard label="Source records" value={summary.total_source_records} />
      <MetricCard label="Price observations" value={summary.total_price_observations} />
      <MetricCard label="Average latest price" value={formatMoney(summary.average_latest_price)} />
      <MetricCard label="Lowest latest price" value={formatMoney(summary.min_latest_price)} />
      <MetricCard label="Highest latest price" value={formatMoney(summary.max_latest_price)} />
    </div>
    <section><h2>Data flow</h2><p className="flow">CSV + JSON → normalization → canonical VIN → provenance + observations → NHTSA enrichment → analytics</p></section>
  </>;
}
