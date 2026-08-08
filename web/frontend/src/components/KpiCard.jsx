import { fmt } from "../api";

/**
 * @param {object} props
 * @param {string} props.label
 * @param {string|number} props.value
 * @param {string} [props.delta]
 * @param {boolean} [props.format]
 * @param {import('react').ReactNode} [props.icon]
 * @param {'blue'|'green'|'amber'|'violet'|'rose'|'slate'} [props.accent]
 * @param {boolean} [props.compact]
 * @param {string} [props.className]
 */
export default function KpiCard({
  label,
  value,
  delta,
  format = true,
  icon = null,
  accent = "blue",
  compact = false,
  className = "",
}) {
  const display = format && typeof value === "number" ? fmt(value) : value ?? "—";

  return (
    <div className={`kpi-card kpi-card--${accent} ${compact ? "kpi-card--compact" : ""} ${className}`.trim()}>
      <div className="kpi-card__top">
        <span className="kpi-card__label">{label}</span>
        {icon && <span className="kpi-card__icon" aria-hidden>{icon}</span>}
      </div>
      <div className="kpi-card__value">{display}</div>
      {delta != null && delta !== "" && <div className="kpi-card__delta">{delta}</div>}
    </div>
  );
}
