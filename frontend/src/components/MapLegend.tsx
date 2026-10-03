import { LAYER_LEGENDS } from "./RiskMap";
import { RISK_COLORS, RISK_ORDER } from "../utils/format";

export default function MapLegend({ active, thresholds }: { active: string[]; thresholds: { threshold_low: number; threshold_moderate: number; threshold_high: number } }) {
  const zones = Object.keys(LAYER_LEGENDS).filter((k) => active.includes(k));
  const scoreRanges = [
    `0-${thresholds.threshold_low}`,
    `${thresholds.threshold_low + 1}-${thresholds.threshold_moderate}`,
    `${thresholds.threshold_moderate + 1}-${thresholds.threshold_high}`,
    `${thresholds.threshold_high + 1}-100`,
  ];
  return (
    <div className="map-legend" aria-label="Map legend">
      <div className="legend-title">Asset risk (score)</div>
      {RISK_ORDER.map((c, i) => (
        <div key={c} className="legend-row">
          <span className="legend-dot" style={{ background: RISK_COLORS[c], width: 6 + i * 3, height: 6 + i * 3 }} />
          {c} <span className="muted">({scoreRanges[i]})</span>
        </div>
      ))}
      {zones.map((z) => (
        <div key={z} className="legend-block">
          <div className="legend-title">{z}</div>
          {LAYER_LEGENDS[z].map((label, i) => (
            <div key={label} className="legend-row">
              <span className="legend-swatch" style={{ background: RISK_COLORS[RISK_ORDER[i]] }} /> {label}
            </div>
          ))}
        </div>
      ))}
      {active.includes("Vulnerability heatmap") && (
        <div className="legend-block muted">Heatmap: distance-weighted asset risk (cells within 25 km of assets)</div>
      )}
      <div className="legend-block muted legend-track">
        <span className="line-solid" /> observed&nbsp;&nbsp;<span className="line-dashed" /> forecast
      </div>
    </div>
  );
}
