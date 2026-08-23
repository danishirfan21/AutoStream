import { useEffect, useState } from "react";
import { getMarketSnapshot, getPriceHistory, getVehicle, getVehicleEnrichment, getVehicleSources } from "../api/client";
import type { MarketSnapshot, PriceObservation, Vehicle, VehicleEnrichment, VehicleSource } from "../api/types";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { MetricCard } from "../components/MetricCard";
import { formatDate, formatMoney, vehicleLabel } from "../utils/format";

type DetailData = { vehicle: Vehicle; snapshot?: MarketSnapshot; history?: PriceObservation[]; sources?: VehicleSource[]; enrichment?: VehicleEnrichment[] };
export function VehicleDetailPage({ vin }: { vin: string }) {
  const [data, setData] = useState<DetailData>(); const [error, setError] = useState<string>();
  useEffect(() => { setData(undefined); setError(undefined); (async () => {
    try { const vehicle = await getVehicle(vin); const [snapshot, history, sources, enrichment] = await Promise.allSettled([getMarketSnapshot(vin), getPriceHistory(vin), getVehicleSources(vin), getVehicleEnrichment(vin)]);
      setData({ vehicle, snapshot: snapshot.status === "fulfilled" ? snapshot.value : undefined, history: history.status === "fulfilled" ? history.value : undefined, sources: sources.status === "fulfilled" ? sources.value : undefined, enrichment: enrichment.status === "fulfilled" ? enrichment.value : undefined });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unknown error"); }
  })(); }, [vin]);
  if (error) return <ErrorState message={error} />; if (!data) return <LoadingState label="Loading vehicle…" />;
  const enrichment = data.enrichment?.[0]; const attributes = enrichment?.selected_attributes ?? {};
  return <><h1>{vehicleLabel(data.vehicle)}</h1><p className="vin">{data.vehicle.vin}</p>
    {data.snapshot && <div className="cards"><MetricCard label="Latest price" value={formatMoney(data.snapshot.latest_price)} detail={`Previous ${formatMoney(data.snapshot.previous_price)}`} /><MetricCard label="Price change" value={formatMoney(data.snapshot.price_change)} detail={data.snapshot.price_change_percent == null ? undefined : `${data.snapshot.price_change_percent.toFixed(2)}%`} /><MetricCard label="Observations" value={data.snapshot.observation_count} detail={data.snapshot.latest_location ?? undefined} /></div>}
    <section><h2>Price history</h2>{!data.history?.length ? <p>No price history available.</p> : <table><thead><tr><th>Date</th><th>Source</th><th>Price</th><th>Mileage</th><th>Location</th></tr></thead><tbody>{data.history.map((item, index) => <tr key={`${item.observed_at}-${index}`}><td>{formatDate(item.observed_at)}</td><td>{item.source_name}</td><td>{formatMoney(item.price)}</td><td>{item.mileage ?? "—"}</td><td>{item.location ?? "—"}</td></tr>)}</tbody></table>}</section>
    <section><h2>Source provenance</h2><p>1 canonical vehicle · {data.sources?.length ?? 0} historical source records</p>{data.sources?.map((item) => <p key={`${item.source_name}-${item.source_record_id}`}>{item.source_name} · {item.source_record_id} · {formatDate(item.source_timestamp)}</p>)}</section>
    <section><h2>Vehicle specifications</h2>{!enrichment ? <p>No NHTSA enrichment available</p> : <dl className="attributes">{Object.entries(attributes).filter(([, value]) => value != null && value !== "").map(([key, value]) => <div key={key}><dt>{key.replace(/([A-Z])/g, " $1")}</dt><dd>{String(value)}</dd></div>)}</dl>}</section>
  </>;
}
