export function formatMoney(value: string | null | undefined): string {
  if (value == null) return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(numeric)
    : "—";
}

export function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(value)) : "—";
}

export function vehicleLabel(vehicle: { year: number | null; make: string | null; model: string | null; trim: string | null }): string {
  return [vehicle.year, vehicle.make, vehicle.model, vehicle.trim].filter(Boolean).join(" ") || "Unknown vehicle";
}
