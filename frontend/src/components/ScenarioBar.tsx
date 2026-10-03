import { useState } from "react";
import { api } from "../api/client";
import { useApp } from "../context/AppContext";
import { useApi } from "../hooks/useApi";

export default function ScenarioBar() {
  const { version, bump, selectAsset } = useApp();
  const scenarios = useApi(() => api.scenarios(), []);
  const cyclones = useApi(() => api.cyclones(), [version]);
  const [scenario, setScenario] = useState("alpha");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
      selectAsset(null);
      bump();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const active = cyclones.data?.find((c) => c.active);
  const sc = scenarios.data?.find((s) => s.key === scenario);

  return (
    <section className="card scenario-bar" aria-label="Scenario selection">
      <div className="scenario-group">
        <label htmlFor="scenario">Demo scenario</label>
        <select id="scenario" value={scenario} onChange={(e) => setScenario(e.target.value)} disabled={!!busy}>
          {(scenarios.data ?? []).map((s) => (
            <option key={s.key} value={s.key}>{s.name} (peak {s.peak_wind_kmh} km/h)</option>
          ))}
        </select>
        <button className="btn btn-primary" disabled={!!busy || !scenarios.data}
          onClick={() => run("Generating simulated scenario and running models...", () => api.generateDemo(scenario))}>
          Load demo scenario
        </button>
      </div>
      {cyclones.data && cyclones.data.length > 1 && (
        <div className="scenario-group">
          <label htmlFor="cyclone">Active cyclone</label>
          <select id="cyclone" value={active?.id ?? ""} disabled={!!busy}
            onChange={(e) => run("Switching cyclone...", () => api.activateCyclone(Number(e.target.value)))}>
            {cyclones.data.map((c) => (
              <option key={c.id} value={c.id}>{c.name}{c.is_demo ? " [demo]" : ` [${c.source}]`}</option>
            ))}
          </select>
        </div>
      )}
      <div className="scenario-group">
        <button className="btn" disabled={!!busy || !active} onClick={() => run("Re-running models...", () => api.rerun(active?.id))}>
          Re-run models
        </button>
      </div>
      <div className="scenario-desc muted small">
        {busy ? <><span className="spinner" aria-hidden /> {busy}</> : sc?.description}
      </div>
      {error && <div className="inline-error" role="alert">{error}</div>}
    </section>
  );
}
