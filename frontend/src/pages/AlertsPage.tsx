import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useApp } from "../context/AppContext";
import { useApi } from "../hooks/useApi";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { SEVERITY_COLORS } from "../utils/format";

export default function AlertsPage() {
  const { version, bump } = useApp();
  const [severity, setSeverity] = useState("");
  const [district, setDistrict] = useState("");
  const [showAck, setShowAck] = useState(true);
  const [ackError, setAckError] = useState<string | null>(null);
  const alerts = useApi(() => api.alerts({ severity, district, include_acknowledged: showAck }), [version, severity, district, showAck]);
  const rules = useApi(() => api.alertRules(), []);
  const all = useApi(() => api.alerts({}), [version]);
  const districts = [...new Set((all.data?.items ?? []).map((a) => a.district).filter(Boolean) as string[])].sort();

  const ack = async (id: number) => {
    setAckError(null);
    try {
      await api.acknowledgeAlert(id);
      bump();
    } catch (e) {
      setAckError((e as Error).message);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>Alerts</h1>
        <p className="muted">
          Rule-based alerts on model estimates. An alert means elevated <i>estimated</i> risk - it does not confirm that damage will occur.
        </p>
      </div>
      <div className="card toolbar">
        <select value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Filter by severity">
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="advisory">Advisory</option>
        </select>
        <select value={district} onChange={(e) => setDistrict(e.target.value)} aria-label="Filter by district">
          <option value="">All districts</option>
          {districts.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <label className="checkbox">
          <input type="checkbox" checked={showAck} onChange={(e) => setShowAck(e.target.checked)} /> Show acknowledged
        </label>
        {alerts.data && (
          <span className="muted small">
            {alerts.data.counts.critical} critical - {alerts.data.counts.warning} warning - {alerts.data.counts.advisory} advisory
          </span>
        )}
      </div>
      {ackError && <ErrorState message={ackError} />}
      {alerts.error ? <ErrorState message={alerts.error} onRetry={alerts.reload} /> :
        !alerts.data ? <Loading /> :
        alerts.data.items.length === 0 ? <EmptyState title="No alerts match these filters." /> : (
          <div className="alert-list">
            {alerts.data.items.map((a) => (
              <article key={a.id} className={`card alert-card ${a.acknowledged ? "acked" : ""}`} style={{ borderLeftColor: SEVERITY_COLORS[a.severity] }}>
                <header>
                  <span className="sev" style={{ background: SEVERITY_COLORS[a.severity] }}>{a.severity.toUpperCase()}</span>
                  <h3>{a.title}</h3>
                  {a.acknowledged && <span className="badge badge-outline">Acknowledged</span>}
                </header>
                <dl className="kv-grid alert-kv">
                  <dt>Infrastructure</dt><dd>{a.infrastructure} ({a.asset_type_label})</dd>
                  <dt>Location</dt><dd>{a.location}</dd>
                  <dt>Risk</dt><dd>{Math.round(a.risk_score)}/100 - confidence {Math.round(a.confidence * 100)}%</dd>
                  <dt>Main hazard</dt><dd>{a.main_hazard}</dd>
                  <dt>Recommended action</dt><dd>{a.recommended_action}</dd>
                  <dt>Rules triggered</dt><dd className="small">{a.triggered_rules.join(", ")}</dd>
                </dl>
                <p className="small muted">{a.message}</p>
                <div className="btn-row">
                  <Link className="btn btn-small" to={`/asset/${a.asset_id}`}>View asset details</Link>
                  {!a.acknowledged && <button className="btn btn-small" onClick={() => ack(a.id)}>Acknowledge</button>}
                </div>
              </article>
            ))}
          </div>
        )}
      <section className="card">
        <h2>Alert rules</h2>
        {rules.data ? (
          <table className="table">
            <thead><tr><th>Rule</th><th>Severity</th><th>Title</th><th>Condition</th></tr></thead>
            <tbody>
              {rules.data.map((r) => (
                <tr key={r.key}><td><code>{r.key}</code></td><td>{r.severity}</td><td>{r.title}</td><td>{r.condition}</td></tr>
              ))}
            </tbody>
          </table>
        ) : rules.error ? <ErrorState message={rules.error} /> : <Loading />}
        <p className="muted small">Thresholds and minimum confidence are configurable on the Settings page. One alert per asset (most severe rule).</p>
      </section>
    </div>
  );
}
