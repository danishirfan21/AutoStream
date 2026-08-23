export interface Vehicle {
  vin: string;
  year: number | null;
  make: string | null;
  model: string | null;
  trim: string | null;
}

export interface MarketSummary {
  total_vehicles: number;
  total_source_records: number;
  total_price_observations: number;
  average_latest_price: string | null;
  min_latest_price: string | null;
  max_latest_price: string | null;
}

export interface MarketSnapshot {
  vin: string;
  latest_price: string | null;
  previous_price: string | null;
  price_change: string | null;
  price_change_percent: number | null;
  observation_count: number;
  latest_mileage: number | null;
  latest_location: string | null;
}

export interface PriceObservation {
  source_name: string;
  price: string | null;
  mileage: number | null;
  location: string | null;
  observed_at: string;
}

export interface VehicleSource {
  source_name: string;
  source_record_id: string;
  source_timestamp: string | null;
  ingested_at: string;
}

export interface VehicleEnrichment {
  source_name: string;
  status: string;
  selected_attributes: Record<string, unknown>;
  fetched_at: string;
}

export interface VehicleFilters {
  make?: string;
  model?: string;
  year?: number;
}
