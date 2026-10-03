import type { AssetRiskSummary } from "../api/types";
import { RiskBadge } from "./Badges";
import { EmptyState } from "./States";

interface Props {
  items: AssetRiskSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export default function PriorityList({ items, selectedId, onSelect }: Props) {
  if (!items.length) return <EmptyState title="No assets match the current filters." />;
  return (
    <ol className="priority-list">
      {items.map((a, i) => (
        <li key={a.asset_id}>
          <button className={`priority-item ${a.asset_id === selectedId ? "selected" : ""}`} onClick={() => onSelect(a.asset_id)}>
            <span className="rank">{i + 1}</span>
            <span className="priority-main">
              <span className="priority-name">{a.name}</span>
              <span className="priority-meta">
                {a.asset_type_label} - {a.district} - {a.dist_track_km.toFixed(0)} km from track - main hazard: {a.main_hazard.toLowerCase()}
              </span>
            </span>
            <span className="priority-badges">
              <RiskBadge category={a.risk_category} score={a.risk_score} />
              <span className={`conf-dot conf-${a.confidence_label.toLowerCase()}`} title={`${a.confidence_label} confidence (${Math.round(a.confidence * 100)}%)`}>
                {a.confidence_label[0]}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
