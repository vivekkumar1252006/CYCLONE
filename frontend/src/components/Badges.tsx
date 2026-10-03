import type { ConfidenceLabel, RiskCategory } from "../api/types";
import { RISK_COLORS } from "../utils/format";

export function RiskBadge({ category, score }: { category: RiskCategory; score?: number }) {
  return (
    <span className="badge" style={{ background: RISK_COLORS[category] }}>
      {score != null && <b>{Math.round(score)}</b>} {category}
    </span>
  );
}

const CONF_CLASS: Record<ConfidenceLabel, string> = { High: "conf-high", Medium: "conf-medium", Low: "conf-low" };

export function ConfidenceBadge({ label, value }: { label: ConfidenceLabel; value?: number }) {
  return (
    <span className={`badge badge-outline ${CONF_CLASS[label]}`} title="Model confidence (heuristic: track, model agreement, data, lead time)">
      {label} confidence{value != null ? ` (${Math.round(value * 100)}%)` : ""}
    </span>
  );
}

export function DemoTag() {
  return <span className="badge badge-demo">DEMO / SIMULATED</span>;
}
