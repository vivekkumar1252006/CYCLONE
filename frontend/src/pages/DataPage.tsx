import { useState } from "react";
import { api } from "../api/client";
import type { UploadResult } from "../api/types";
import { useApp } from "../context/AppContext";
import { useApi } from "../hooks/useApi";
import { RiskBadge } from "../components/Badges";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { fmt1, fmtTime } from "../utils/format";

const PAGE = 50;
const MAX_MB = 5;

export default function DataPage() {
  const { version, bump, selectAsset } = useApp();
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"append" | "replace">("append");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [offset, setOffset] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);

  const assets = useApi(() => api.infrastructure({ q, asset_type: type, limit: PAGE, offset }), [version, q, type, offset]);
  const types = useApi(() => api.assetTypes(), []);
  const sources = useApi(() => api.dataSources(), []);
  const weather = useApi(() => api.weather(), [version]);

  const onFile = (f: File | null) => {
    setResult(null);
    setUploadError(null);
    if (f && !/\.(csv|geojson|json)$/i.test(f.name)) {
      setUploadError("Please choose a .csv, .geojson or .json file.");
      setFile(null);
      return;
    }
    if (f && f.size > MAX_MB * 1024 * 1024) {
      setUploadError(`File is larger than ${MAX_MB} MB.`);
      setFile(null);
      return;
    }
    setFile(f);
  };

  const upload = async () => {
    if (!file) return;
    if (mode === "replace" && !window.confirm("Replace mode deletes ALL existing infrastructure (including demo assets). Continue?")) return;
    setBusy(true);
    setUploadError(null);
    try {
      const r = await api.upload(file, mode);
      setResult(r);
      selectAsset(null);
      bump();
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const removeUploaded = async () => {
    if (!window.confirm("Delete all uploaded (non-demo) assets?")) return;
    try {
      const r = await api.deleteUploaded();
      setMsg(`Deleted ${r.deleted} uploaded assets.`);
      selectAsset(null);
      bump();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };

  const refreshWeather = async () => {
    try {
      const r = await api.refreshWeather();
      setMsg(r.message ?? `Weather refreshed (${r.stations} locations).`);
      bump();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>Data</h1>
        <p className="muted">Upload infrastructure inventories, review assets, weather inputs and data-source status.</p>
      </div>

      <div className="two-col">
        <section className="card">
          <h2>Upload infrastructure (CSV / GeoJSON)</h2>
          <p className="small">
            Required: <code>name</code>, <code>asset_type</code>, <code>lat</code>, <code>lon</code> (CSV) or a Point / LineString / Polygon geometry
            (GeoJSON). Optional: <code>district, elevation_m, age_years, historical_damage_count, criticality (0-1), capacity</code>.
            Missing elevation, coast/river distance and flood-zone flags are derived from the study-region GIS layers.
          </p>
          <p className="small"><a href={api.templateUrl} download>Download CSV template</a> - sample files are in <code>data/samples/</code>.</p>
          <div className="form-row">
            <input type="file" accept=".csv,.geojson,.json" onChange={(e) => onFile(e.target.files?.[0] ?? null)} aria-label="Infrastructure file" />
            <select value={mode} onChange={(e) => setMode(e.target.value as "append" | "replace")} aria-label="Upload mode">
              <option value="append">Append to existing</option>
              <option value="replace">Replace all assets</option>
            </select>
            <button className="btn btn-primary" disabled={!file || busy} onClick={upload}>{busy ? "Uploading & re-scoring..." : "Upload"}</button>
          </div>
          {uploadError && <ErrorState message={uploadError} />}
          {result && (
            <div className="upload-result">
              <p><b>{result.accepted}</b> assets accepted, <b>{result.rejected_count}</b> rejected. Risk re-computed for the active cyclone.</p>
              {result.warnings.map((w) => <p key={w} className="small">{w}</p>)}
              {result.rejected.length > 0 && (
                <table className="table compact">
                  <thead><tr><th>Row / feature</th><th>Name</th><th>Reason</th></tr></thead>
                  <tbody>
                    {result.rejected.map((r, i) => (
                      <tr key={i}><td>{r.row ?? r.feature}</td><td>{r.name ?? "-"}</td><td>{r.error}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="muted small">{result.derived_fields_note}</p>
            </div>
          )}
          <div className="btn-row">
            <button className="btn btn-small" onClick={removeUploaded}>Delete uploaded assets</button>
          </div>
          {msg && <p className="small">{msg}</p>}
        </section>

        <section className="card">
          <h2>Data sources</h2>
          {sources.error ? <ErrorState message={sources.error} /> : !sources.data ? <Loading /> : (
            <table className="table compact">
              <thead><tr><th>Family</th><th>Provider</th><th>Mode</th><th>Note</th></tr></thead>
              <tbody>
                {sources.data.map((s) => (
                  <tr key={s.family}>
                    <td>{s.family.replace("_", " ")}</td><td>{s.provider}</td>
                    <td><span className={`mode mode-${s.mode}`}>{s.mode}</span></td><td className="small">{s.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted small">Live providers are configured via environment variables on the server (see <code>.env.example</code>). If a provider fails, the system falls back to demo data and says so.</p>
        </section>
      </div>

      <section className="card">
        <div className="section-head">
          <h2>Infrastructure inventory {assets.data && <span className="muted small">({assets.data.total} assets)</span>}</h2>
          <div className="toolbar-inline">
            <input placeholder="Search name or district..." value={q} maxLength={100} onChange={(e) => { setQ(e.target.value); setOffset(0); }} aria-label="Search assets" />
            <select value={type} onChange={(e) => { setType(e.target.value); setOffset(0); }} aria-label="Filter by type">
              <option value="">All types</option>
              {types.data?.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </select>
          </div>
        </div>
        {assets.error ? <ErrorState message={assets.error} onRetry={assets.reload} /> : !assets.data ? <Loading /> :
          assets.data.items.length === 0 ? <EmptyState title="No assets found." /> : (
            <>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr><th>Name</th><th>Type</th><th>District</th><th>Lat, Lon</th><th>Elev. (m)</th><th>Coast (km)</th><th>Flood zone</th><th>Age</th><th>Risk</th><th>Source</th></tr>
                  </thead>
                  <tbody>
                    {assets.data.items.map((a) => (
                      <tr key={a.id}>
                        <td>{a.name}</td><td>{a.asset_type_label}</td><td>{a.district}</td>
                        <td className="small">{a.lat.toFixed(3)}, {a.lon.toFixed(3)}</td>
                        <td>{fmt1(a.elevation_m)}{a.elevation_source !== "provided" && <span className="muted">*</span>}</td>
                        <td>{fmt1(a.dist_coast_km)}</td><td>{a.in_flood_zone ? "Yes" : "-"}</td><td>{a.age_years ?? "?"}</td>
                        <td>{a.risk_category ? <RiskBadge category={a.risk_category} score={a.risk_score} /> : "-"}</td>
                        <td className="small">{a.is_demo ? "demo (simulated)" : a.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="pager">
                <button className="btn btn-small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                <span className="small">{offset + 1}-{Math.min(offset + PAGE, assets.data.total)} of {assets.data.total}</span>
                <button className="btn btn-small" disabled={offset + PAGE >= assets.data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
              </div>
              <p className="muted small">* elevation from the synthetic demo DEM (not measured).</p>
            </>
          )}
      </section>

      <section className="card">
        <div className="section-head">
          <h2>Weather inputs</h2>
          <button className="btn btn-small" onClick={refreshWeather}>Refresh from live provider</button>
        </div>
        {weather.error ? <ErrorState message={weather.error} /> : !weather.data ? <Loading /> :
          weather.data.items.length === 0 ? <EmptyState title="No weather observations." /> : (
            <div className="table-wrap">
              <table className="table compact">
                <thead><tr><th>Station</th><th>Time</th><th>Rain (mm)</th><th>Wind (km/h)</th><th>Dir</th><th>Temp</th><th>RH</th><th>Surge (m)</th><th>Source</th></tr></thead>
                <tbody>
                  {weather.data.items.map((o) => (
                    <tr key={o.id}>
                      <td>{o.station_name}</td><td className="small">{fmtTime(o.observed_at)}</td><td>{o.rainfall_mm ?? "-"}</td>
                      <td>{o.wind_speed_kmh ?? "-"}</td><td>{o.wind_direction_deg ?? "-"}</td><td>{o.temperature_c ?? "-"}</td>
                      <td>{o.humidity_pct ?? "-"}</td><td>{o.surge_indicator_m ?? "-"}</td>
                      <td className="small">{o.is_demo ? "SIMULATED" : o.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        <p className="muted small">Simulated station readings are for display only and are never fed back into the models; live NWP rainfall forecasts (Open-Meteo) are blended into Model A when configured.</p>
      </section>
    </div>
  );
}
