import { useEffect, useState } from "react";
import { api, apiKey } from "../api/client";
import type { RiskConfig } from "../api/types";
import { useApp } from "../context/AppContext";
import { useApi } from "../hooks/useApi";
import { ErrorState, Loading } from "../components/States";

const WEIGHTS: { key: keyof RiskConfig; label: string; help: string }[] = [
  { key: "w_hazard", label: "Hazard exposure", help: "Wind, rainfall, flooding and surge from Model A" },
  { key: "w_vulnerability", label: "Infrastructure vulnerability", help: "Model B damage/disruption probability" },
  { key: "w_environment", label: "Environmental exposure", help: "Low elevation, river/coast proximity, flood-prone zones" },
  { key: "w_criticality", label: "Infrastructure criticality", help: "Importance of the asset type" },
];

export default function SettingsPage() {
  const { bump } = useApp();
  const settings = useApi(() => api.getRiskSettings(), []);
  const health = useApi(() => api.health(), []);
  const [cfg, setCfg] = useState<RiskConfig | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [key, setKey] = useState(apiKey.get());

  useEffect(() => {
    if (settings.data) setCfg(settings.data.config);
  }, [settings.data]);

  if (settings.error) return <ErrorState message={settings.error} onRetry={settings.reload} />;
  if (!cfg || !settings.data) return <Loading />;

  const wsum = WEIGHTS.reduce((s, w) => s + (cfg[w.key] as number), 0) || 1;
  const set = (k: keyof RiskConfig, v: number) => setCfg({ ...cfg, [k]: Number.isFinite(v) ? v : 0 });
  const thresholdsOk = cfg.threshold_low < cfg.threshold_moderate && cfg.threshold_moderate < cfg.threshold_high;

  const save = async (reset = false) => {
    setSaving(true);
    setStatus(null);
    try {
      const r = reset ? await api.resetRiskSettings() : await api.putRiskSettings(cfg);
      setCfg(r.config);
      setStatus({ ok: true, msg: "Saved. Risk scores and alerts were re-computed for the active cyclone." });
      bump();
    } catch (e) {
      setStatus({ ok: false, msg: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page page-narrow">
      <div className="page-head">
        <h1>Settings</h1>
        <p className="muted">{settings.data.note}</p>
      </div>

      <section className="card">
        <h2>Risk score weights</h2>
        <p className="small">Risk = 100 x weighted average of the components below. Weights are normalised, so they need not sum to 1.</p>
        {WEIGHTS.map((w) => (
          <div key={w.key} className="slider-row">
            <label htmlFor={w.key}>
              <b>{w.label}</b> <span className="muted small">{w.help}</span>
            </label>
            <input id={w.key} type="range" min={0} max={1} step={0.05} value={cfg[w.key] as number}
              onChange={(e) => set(w.key, parseFloat(e.target.value))} />
            <span className="slider-val">{Math.round(((cfg[w.key] as number) / wsum) * 100)}%</span>
          </div>
        ))}
        <div className="slider-row">
          <label htmlFor="gate"><b>Hazard gate</b> <span className="muted small">Environmental & criticality points scale with hazard until it reaches this level (0 = off)</span></label>
          <input id="gate" type="range" min={0} max={1} step={0.05} value={cfg.hazard_gate} onChange={(e) => set("hazard_gate", parseFloat(e.target.value))} />
          <span className="slider-val">{cfg.hazard_gate.toFixed(2)}</span>
        </div>
      </section>

      <section className="card">
        <h2>Risk category thresholds</h2>
        <p className="small">Prototype assumptions. Score &lt;= Low threshold is Low, &lt;= Moderate is Moderate, &lt;= High is High, above is Very High.</p>
        <div className="form-grid">
          {(["threshold_low", "threshold_moderate", "threshold_high"] as const).map((k) => (
            <label key={k}>
              {k.replace("threshold_", "").replace(/^./, (c) => c.toUpperCase())} upper bound
              <input type="number" min={0} max={100} step={1} value={cfg[k]} onChange={(e) => set(k, parseFloat(e.target.value))} />
            </label>
          ))}
        </div>
        {!thresholdsOk && <p className="inline-error">Thresholds must satisfy Low &lt; Moderate &lt; High.</p>}
      </section>

      <section className="card">
        <h2>Alert engine</h2>
        <div className="slider-row">
          <label htmlFor="minconf"><b>Minimum confidence</b> <span className="muted small">Below this, Very High risks become low-confidence advisories</span></label>
          <input id="minconf" type="range" min={0} max={1} step={0.05} value={cfg.alert_min_confidence}
            onChange={(e) => set("alert_min_confidence", parseFloat(e.target.value))} />
          <span className="slider-val">{Math.round(cfg.alert_min_confidence * 100)}%</span>
        </div>
      </section>

      <div className="btn-row">
        <button className="btn btn-primary" disabled={saving || !thresholdsOk} onClick={() => save(false)}>{saving ? "Saving & re-scoring..." : "Save and re-score"}</button>
        <button className="btn" disabled={saving} onClick={() => setCfg(settings.data!.defaults)}>Load defaults</button>
        <button className="btn" disabled={saving} onClick={() => save(true)}>Reset to defaults on server</button>
      </div>
      {status && <p className={status.ok ? "ok-msg" : "inline-error"} role="status">{status.msg}</p>}

      <section className="card">
        <h2>API access</h2>
        <p className="small">
          Server authentication is <b>{health.data?.auth_enabled ? "enabled" : "disabled (development mode)"}</b>.
          When <code>ADMIN_API_KEY</code> is set on the server, changes require the key below. It is stored only in this browser session.
        </p>
        <div className="form-row">
          <input type="password" autoComplete="off" placeholder="X-API-Key" value={key} onChange={(e) => setKey(e.target.value)} aria-label="Admin API key" />
          <button className="btn" onClick={() => { apiKey.set(key.trim()); setStatus({ ok: true, msg: key.trim() ? "API key stored for this session." : "API key cleared." }); }}>
            Save key
          </button>
        </div>
      </section>
    </div>
  );
}
