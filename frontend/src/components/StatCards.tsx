import type { StatisticsResponse } from "../api/types";
import { compass, compactPopulation, fmtInt, fmtTime } from "../utils/format";

export default function StatCards({ stats }: { stats: StatisticsResponse }) {
  const c = stats.cards;
  const s = c.cyclone_status;
  return (
    <section className="cards" aria-label="Key indicators">
      <div className="card stat stat-primary">
        <div className="stat-label">Current cyclone status</div>
        <div className="stat-value">{s.category_name}</div>
        <div className="stat-sub">
          {s.name} - {Math.round(s.wind_kmh)} km/h{s.pressure_hpa ? `, ${s.pressure_hpa} hPa` : ""}
          {s.movement && ` - moving ${compass(s.movement.bearing_deg)} at ${s.movement.speed_kmh} km/h`}
        </div>
        <div className="stat-sub">
          {s.landfall
            ? `Est. landfall near ${s.landfall.district} in ~${Math.round(s.landfall.t_hours)} h`
            : "No landfall within forecast window"}{" "}
          - as of {fmtTime(s.analysis_time)}
        </div>
      </div>
      <div className="card stat">
        <div className="stat-label">Maximum wind speed (forecast)</div>
        <div className="stat-value">{fmtInt(c.max_wind_kmh)} <small>km/h</small></div>
        <div className="stat-sub">Peak sustained wind over the forecast period</div>
      </div>
      <div className="card stat">
        <div className="stat-label">Affected districts</div>
        <div className="stat-value">{c.affected_districts}</div>
        <div className="stat-sub" title={c.affected_district_names.join(", ")}>
          {c.affected_district_names.slice(0, 4).join(", ")}
          {c.affected_district_names.length > 4 ? ` +${c.affected_district_names.length - 4}` : ""}
        </div>
      </div>
      <div className="card stat">
        <div className="stat-label">High-risk infrastructure</div>
        <div className="stat-value">{c.high_risk_infrastructure} <small>/ {c.total_assets}</small></div>
        <div className="stat-sub">{c.very_high_risk_infrastructure} Very High - {c.alerts} alerts</div>
      </div>
      <div className="card stat">
        <div className="stat-label">Est. population exposure</div>
        <div className="stat-value">{compactPopulation(c.population_exposed)}</div>
        <div className="stat-sub" title={c.population_note}>In areas forecast &gt;= 62 km/h winds (estimate, see info)</div>
      </div>
    </section>
  );
}
