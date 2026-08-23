export function MetricCard({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return <article className="card"><small>{label}</small><strong>{value}</strong>{detail && <small>{detail}</small>}</article>;
}
