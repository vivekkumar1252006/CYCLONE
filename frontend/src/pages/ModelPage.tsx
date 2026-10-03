import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorState, Loading } from "../components/States";

const FEATURE_LABELS: Record<string, string> = {
  dist_track_km: "Distance from track", peak_wind_kmh: "Peak wind", rainfall_mm: "Rainfall", elevation_m: "Elevation",
  dist_coast_km: "Distance from coast", flood_probability: "Flood probability", surge_exposure: "Surge exposure",
  age_years: "Asset age", age_missing: "Age unknown", historical_damage_count: "Historical damage",
};

export default function ModelPage() {
  const info = useApi(() => api.modelInfo(), []);
  if (info.error) return <ErrorState message={info.error} onRetry={info.reload} />;
  if (!info.data) return <Loading />;
  const m = info.data;
  const fi = Object.entries(m.vulnerability_model.feature_importances)
    .map(([k, v]) => ({ name: FEATURE_LABELS[k] ?? k.replace("type_", "type: "), value: v }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 14);

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1>Models &amp; methodology</h1>
        <p className="muted">How CycloneGuard AI turns a cyclone track into infrastructure risk - and what its limits are.</p>
      </div>

      <section className="card">
        <h2>Pipeline</h2>
        <ol className="pipeline">
          <li><b>Inputs</b> - cyclone track (observed + forecast, intensity, radii, uncertainty), weather, GIS layers, infrastructure inventory.</li>
          <li><b>Validation & preprocessing</b> - schema checks, study-region checks, derived geographic features.</li>
          <li><b>Model A - cyclone impact</b> ({m.impact_model.name}, {m.impact_model.type}): wind, rainfall, flood probability, storm-surge exposure per location.</li>
          <li><b>Model B - infrastructure vulnerability</b> ({m.vulnerability_model.name} v{m.vulnerability_model.version}): probability of significant damage / disruption.</li>
          <li><b>Risk scoring engine</b> - transparent weighted score 0-100 with configurable weights and thresholds.</li>
          <li><b>Confidence</b> - heuristic combining track uncertainty, model agreement (tree spread), data completeness and lead time.</li>
          <li><b>Outputs</b> - risk map, priority list, explanations, rule-based alerts, preparedness guidance.</li>
        </ol>
      </section>

      <section className="card warning-card">
        <h2>Important limitations</h2>
        <ul>
          <li>{m.vulnerability_model.training_data_warning}</li>
          <li>Model A is a simplified parametric model (Rankine-vortex wind, climatological rain profile). It is not a substitute for official IMD forecasts or hydrodynamic surge models.</li>
          <li>Demo geography (coastline, rivers, district zones) is simplified; the elevation surface is synthetic.</li>
          <li>Confidence values are heuristic indicators, not calibrated probabilities.</li>
        </ul>
      </section>

      <section className="card">
        <h2>Model B evaluation (on held-out synthetic data)</h2>
        <table className="table compact">
          <tbody>
            {Object.entries(m.vulnerability_model.metrics).map(([k, v]) => (
              <tr key={k}><th>{k}</th><td>{String(v)}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>Global feature importance (Model B)</h2>
        <ResponsiveContainer width="100%" height={fi.length * 26 + 40}>
          <BarChart data={fi} layout="vertical" margin={{ left: 60, right: 16 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 12 }} />
            <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(v: number) => v.toFixed(3)} />
            <Bar dataKey="value" fill="#1c3d8c" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
        <p className="muted small">{m.explainability}</p>
      </section>
    </div>
  );
}
