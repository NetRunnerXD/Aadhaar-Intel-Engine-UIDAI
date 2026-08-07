import { fmt } from "../api";

export default function KpiCard({ label, value, delta, format = true }) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value">{format && typeof value === "number" ? fmt(value) : value ?? "—"}</div>
      {delta != null && delta !== "" && <div className="delta">{delta}</div>}
    </div>
  );
}
