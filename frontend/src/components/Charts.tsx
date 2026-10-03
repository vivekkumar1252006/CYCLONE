import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { StatisticsResponse } from "../api/types";
import { COMPONENT_LABELS, RISK_COLORS, RISK_ORDER } from "../utils/format";

export function RiskDistributionChart({ data }: { data: StatisticsResponse["risk_distribution"] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="category" tick={{ fontSize: 12 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
        <Tooltip formatter={(v: number) => [`${v} assets`, "Count"]} />
        <Bar dataKey="count" isAnimationActive={false} label={{ position: "top", fontSize: 12 }}>
          {data.map((d) => (
            <Cell key={d.category} fill={RISK_COLORS[d.category]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function RiskByTypeChart({ data }: { data: StatisticsResponse["risk_by_type"] }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 30 + 60)}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, left: 40, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
        <YAxis type="category" dataKey="label" width={110} tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {RISK_ORDER.map((c) => (
          <Bar key={c} dataKey={c} stackId="a" fill={RISK_COLORS[c]} isAnimationActive={false} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

const CONTRIB_COLORS: Record<string, string> = {
  hazard_exposure: "#1c3d8c",
  infrastructure_vulnerability: "#7048e8",
  environmental_exposure: "#0ca678",
  criticality: "#868e96",
};

export function HazardContributionChart({ data, onSelect }: { data: StatisticsResponse["hazard_contribution"]; onSelect?: (id: number) => void }) {
  const rows = data.map((d) => ({ ...d, short: d.name.length > 26 ? `${d.name.slice(0, 25)}...` : d.name }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(240, rows.length * 28 + 60)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 12, left: 60, bottom: 0 }}
        onClick={(e) => {
          const p = (e as { activePayload?: { payload: { asset_id: number } }[] } | null)?.activePayload?.[0]?.payload;
          if (p && onSelect) onSelect(p.asset_id);
        }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 12 }} />
        <YAxis type="category" dataKey="short" width={150} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v: number, name: string) => [`${v.toFixed(1)} pts`, COMPONENT_LABELS[name] ?? name]} />
        <Legend formatter={(v: string) => COMPONENT_LABELS[v] ?? v} wrapperStyle={{ fontSize: 12 }} />
        {Object.keys(CONTRIB_COLORS).map((k) => (
          <Bar key={k} dataKey={k} stackId="c" fill={CONTRIB_COLORS[k]} isAnimationActive={false} cursor="pointer" />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function IntensityTimeline({ data }: { data: StatisticsResponse["intensity_timeline"] }) {
  // split into observed / forecast series that share the "now" point so the lines connect
  const lastObs = data.reduce((i, d, idx) => (!d.is_forecast ? idx : i), 0);
  const rows = data.map((d, i) => ({
    t: d.t_hours,
    observed: i <= lastObs ? d.wind_kmh : null,
    forecast: i >= lastObs ? d.wind_kmh : null,
    pressure: d.pressure_hpa,
    category: d.category,
  }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={rows} margin={{ top: 20, right: 8, left: -8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}h`} tick={{ fontSize: 12 }} />
        <YAxis yAxisId="w" tick={{ fontSize: 12 }} label={{ value: "km/h", angle: -90, position: "insideLeft", fontSize: 11, dx: 14 }} />
        <YAxis yAxisId="p" orientation="right" domain={["dataMin - 5", "dataMax + 5"]} tick={{ fontSize: 12 }} width={44} />
        <Tooltip labelFormatter={(v: number) => `T${v >= 0 ? "+" : ""}${v} h`}
          formatter={(v: number, n: string) => [n === "pressure" ? `${v} hPa` : `${v} km/h`, n === "pressure" ? "Pressure" : n === "observed" ? "Observed wind" : "Forecast wind"]} />
        <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v: string) => (v === "pressure" ? "Pressure (hPa)" : v === "observed" ? "Observed wind" : "Forecast wind (estimate)")} />
        <ReferenceLine yAxisId="w" x={0} stroke="#495057" label={{ value: "Now", position: "top", fontSize: 11 }} />
        <ReferenceLine yAxisId="w" y={62} stroke="#e0a100" strokeDasharray="2 4" label={{ value: "CS 62", position: "insideBottomLeft", fontSize: 10 }} />
        <ReferenceLine yAxisId="w" y={118} stroke="#c92a2a" strokeDasharray="2 4" label={{ value: "VSCS 118", position: "insideBottomLeft", fontSize: 10 }} />
        <Line yAxisId="w" dataKey="observed" stroke="#212529" strokeWidth={2.5} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
        <Line yAxisId="w" dataKey="forecast" stroke="#1c3d8c" strokeWidth={2.5} strokeDasharray="6 4" dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
        <Line yAxisId="p" dataKey="pressure" stroke="#adb5bd" strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function DistrictHighRiskChart({ data }: { data: StatisticsResponse["districts"] }) {
  const rows = data.filter((d) => d.assets > 0).slice(0, 12);
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: -12, bottom: 30 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="district" angle={-35} textAnchor="end" interval={0} tick={{ fontSize: 11 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Legend verticalAlign="top" wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="very_high_risk_assets" name="Very High" stackId="d" fill={RISK_COLORS["Very High"]} isAnimationActive={false} />
        <Bar dataKey={(d: { high_risk_assets: number; very_high_risk_assets: number }) => d.high_risk_assets - d.very_high_risk_assets}
          name="High" stackId="d" fill={RISK_COLORS.High} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
