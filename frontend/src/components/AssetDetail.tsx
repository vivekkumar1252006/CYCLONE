import { useState } from "react";
import type { AssetRiskDetail } from "../api/types";
import { COMPONENT_LABELS, RISK_COLORS, fmt1, pct } from "../utils/format";
import { ConfidenceBadge, DemoTag, RiskBadge } from "./Badges";

const LEVEL_COLOR = { Low: RISK_COLORS.Low, Moderate: RISK_COLORS.Moderate, High: RISK_COLORS["Very High"] } as const;
const CONTRIB_COLORS: Record<string, string> = {
  hazard_exposure: "#1c3d8c", infrastructure_vulnerability: "#7048e8", environmental_exposure: "#0ca678", criticality: "#868e96",
};
const WEIGHT_KEY: Record<string, string> = {
  hazard_exposure: "w_hazard", infrastructure_vulnerability: "w_vulnerability", environmental_exposure: "w_environment", criticality: "w_criticality",
};
const CONF_COMPONENT_LABELS: Record<string, string> = {
  track: "Track certainty", model_agreement: "Model agreement", data_completeness: "Data completeness", lead_time: "Lead time",
};

function checklistText(d: AssetRiskDetail): string {
  const lines = [
    `PREPAREDNESS CHECKLIST - ${d.asset.name} (${d.asset.asset_type_label})`,
    `${d.asset.district ?? ""} (${d.asset.lat.toFixed(4)}, ${d.asset.lon.toFixed(4)})`,
    `Cyclone: ${d.cyclone_name} | Estimated risk: ${Math.round(d.risk_score)}/100 (${d.risk_category}), ${d.confidence.label} confidence`,
    d.is_demo ? "*** DEMO / SIMULATED DATA - NOT FOR OPERATIONAL USE ***" : "",
    "",
    ...d.recommendations.map((r) => `[ ] (${r.priority}) ${r.action} - ${r.reason}`),
    "",
    d.recommendations_disclaimer,
  ];
  return lines.filter((l, i) => l !== "" || i > 3).join("\n");
}

export default function AssetDetail({ d }: { d: AssetRiskDetail }) {
  const [copied, setCopied] = useState(false);
  const wsum = Object.values(d.weights).slice(0, 4).reduce((a, b) => a + b, 0) || 1;
  const a = d.asset;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(checklistText(d));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };
  const print = () => {
    const w = window.open("", "_blank", "width=720,height=800");
    if (!w) return;
    const pre = w.document.createElement("pre");
    pre.style.cssText = "font: 14px/1.5 system-ui, sans-serif; white-space: pre-wrap; padding: 24px";
    pre.textContent = checklistText(d); // textContent: no HTML injection
    w.document.title = `Checklist - ${a.name}`;
    w.document.body.appendChild(pre);
    w.print();
  };

  return (
    <article className="asset-detail">
      <header className="detail-header">
        <div>
          <h2>{a.name}</h2>
          <div className="muted">
            {a.asset_type_label} - {a.district ?? "Unknown district"} - {a.lat.toFixed(4)}, {a.lon.toFixed(4)}
          </div>
        </div>
        {a.is_demo ? <DemoTag /> : <span className="badge badge-outline">Uploaded asset</span>}
      </header>

      <div className="detail-score">
        <div className="score-big" style={{ borderColor: RISK_COLORS[d.risk_category] }}>
          <span className="score-num">{Math.round(d.risk_score)}</span>
          <span className="score-den">/ 100</span>
          <span className="score-band" title="Indicative uncertainty band derived from confidence">+/- {fmt1(d.score_band)}</span>
        </div>
        <div className="score-side">
          <RiskBadge category={d.risk_category} />
          <ConfidenceBadge label={d.confidence.label} value={d.confidence.value} />
          <div className="conf-components">
            {Object.entries(d.confidence.components).map(([k, v]) => (
              <div key={k} className="mini-bar-row" title={k}>
                <span>{CONF_COMPONENT_LABELS[k] ?? k}</span>
                <span className="mini-bar"><span style={{ width: `${v * 100}%` }} /></span>
                <span>{pct(v)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <p className="estimate-note">
        Model estimate for <b>{d.cyclone_name}</b>, not an observation. {d.note}
      </p>

      <section>
        <h3>Predicted hazards</h3>
        <div className="hazard-grid">
          {d.predicted_hazards.map((h) => (
            <div key={h.hazard} className="hazard-tile" style={{ borderLeftColor: LEVEL_COLOR[h.level] }}>
              <div className="hazard-name">{h.hazard}</div>
              <div className="hazard-level" style={{ color: LEVEL_COLOR[h.level] }}>{h.level}</div>
              <div className="muted small">{h.detail}</div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3>Key exposure metrics</h3>
        <dl className="kv-grid">
          <dt>Distance from cyclone track</dt><dd>{fmt1(d.distance_from_track_km)} km ({d.right_side_of_track ? "right/stronger side" : "left side"})</dd>
          <dt>Closest approach</dt><dd>{d.closest_approach_hours >= 0 ? `in ~${Math.round(d.closest_approach_hours)} h` : `${Math.round(-d.closest_approach_hours)} h ago`}</dd>
          <dt>Track uncertainty there</dt><dd>+/- {Math.round(d.track_uncertainty_km)} km</dd>
          <dt>Wind exposure</dt><dd>{pct(d.wind_exposure)} (peak ~{Math.round(d.peak_wind_kmh)} km/h)</dd>
          <dt>Flood exposure</dt><dd>{pct(d.flood_exposure)} probability</dd>
          <dt>Rainfall (accumulated)</dt><dd>~{Math.round(d.rainfall_mm)} mm</dd>
          <dt>Storm-surge exposure</dt><dd>{d.surge_exposure.toFixed(2)} index</dd>
          <dt>Infrastructure criticality</dt><dd>{pct(d.criticality)}</dd>
          <dt>Damage/disruption probability (Model B)</dt><dd>{pct(d.vulnerability_probability)}</dd>
          <dt>Elevation</dt><dd>{fmt1(a.elevation_m)} m {a.elevation_source !== "provided" && <span className="muted">({a.elevation_source})</span>}</dd>
          <dt>Distance from coast / river</dt><dd>{fmt1(a.dist_coast_km)} km / {fmt1(a.dist_river_km)} km</dd>
          <dt>Mapped flood-prone zone</dt><dd>{a.in_flood_zone ? "Yes" : "No"}</dd>
        </dl>
      </section>

      <section>
        <h3>How the score is built</h3>
        <div className="stack-bar" role="img" aria-label="Risk score composition">
          {Object.entries(d.contributions).map(([k, v]) => (
            <span key={k} style={{ width: `${v}%`, background: CONTRIB_COLORS[k] }} title={`${COMPONENT_LABELS[k]}: ${v.toFixed(1)} pts`} />
          ))}
        </div>
        <table className="table compact">
          <thead><tr><th>Component</th><th>Value (0-1)</th><th>Weight</th><th>Points</th></tr></thead>
          <tbody>
            {Object.entries(d.contributions).map(([k, v]) => (
              <tr key={k}>
                <td><span className="legend-swatch" style={{ background: CONTRIB_COLORS[k] }} /> {COMPONENT_LABELS[k]}</td>
                <td>{d.components[k]?.toFixed(2)}</td>
                <td>{Math.round((d.weights[WEIGHT_KEY[k]] / wsum) * 100)}%</td>
                <td>{v.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {d.components.hazard_gate < 1 && (
          <p className="muted small">
            Hazard gate {d.components.hazard_gate.toFixed(2)}: environmental and criticality points are scaled down because hazard exposure is limited.
          </p>
        )}
      </section>

      <section>
        <h3>Main contributing factors</h3>
        <ul className="factor-list">
          {d.main_risk_factors.map((f) => (
            <li key={f.factor} className={f.direction}>
              <span className="factor-arrow" aria-hidden>{f.direction === "increases" ? "+" : "-"}</span> {f.factor}
            </li>
          ))}
        </ul>
        <details>
          <summary>Model B feature attribution (occlusion analysis)</summary>
          <p className="muted small">Change in predicted damage probability when each feature is replaced by a typical value.</p>
          {d.ml_attributions.map((m) => (
            <div key={m.key} className="mini-bar-row attr">
              <span>{m.feature}</span>
              <span className="mini-bar signed">
                <span className={m.effect >= 0 ? "pos" : "neg"} style={{ width: `${Math.min(100, Math.abs(m.effect) * 100)}%` }} />
              </span>
              <span>{m.effect >= 0 ? "+" : ""}{(m.effect * 100).toFixed(1)} pp</span>
            </div>
          ))}
        </details>
      </section>

      <section>
        <div className="section-head">
          <h3>Recommended preparedness actions</h3>
          <div className="btn-row">
            <button className="btn btn-small" onClick={copy}>{copied ? "Copied" : "Copy checklist"}</button>
            <button className="btn btn-small" onClick={print}>Print</button>
          </div>
        </div>
        <ul className="rec-list">
          {d.recommendations.map((r) => (
            <li key={r.action}>
              <span className={`prio prio-${r.priority.toLowerCase()}`}>{r.priority}</span>
              <span>
                {r.action}
                <span className="muted small"> - {r.reason}</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="muted small">{d.recommendations_disclaimer}</p>
      </section>

      <section>
        <h3>Asset attributes</h3>
        <dl className="kv-grid">
          <dt>Age</dt><dd>{a.age_years != null ? `${a.age_years} years` : "Unknown (median imputed)"}</dd>
          <dt>Historical damage records</dt><dd>{a.historical_damage_count ?? "Unknown"}</dd>
          <dt>Capacity</dt><dd>{a.capacity ?? "-"}</dd>
          <dt>Land use</dt><dd>{a.land_use ?? "-"}</dd>
          <dt>Data source</dt><dd>{a.source}</dd>
          <dt>Models</dt><dd className="small">{d.models.impact}; {d.models.vulnerability}</dd>
        </dl>
      </section>
    </article>
  );
}
