import type { RiskCategory } from "../api/types";

// Colour-blind-aware sequential palette (also distinguished by marker size and labels).
export const RISK_COLORS: Record<RiskCategory, string> = {
  Low: "#2b8a3e",
  Moderate: "#e0a100",
  High: "#e8590c",
  "Very High": "#c92a2a",
};

export const RISK_ORDER: RiskCategory[] = ["Low", "Moderate", "High", "Very High"];

export const SEVERITY_COLORS = { critical: "#c92a2a", warning: "#e8590c", advisory: "#1971c2" } as const;

export function riskColorForScore(score: number, t = { low: 25, moderate: 50, high: 75 }): string {
  if (score <= t.low) return RISK_COLORS.Low;
  if (score <= t.moderate) return RISK_COLORS.Moderate;
  if (score <= t.high) return RISK_COLORS.High;
  return RISK_COLORS["Very High"];
}

export const fmtInt = (n: number | null | undefined) => (n == null ? "-" : Math.round(n).toLocaleString("en-IN"));
export const fmt1 = (n: number | null | undefined) => (n == null ? "-" : n.toFixed(1));
export const pct = (n: number | null | undefined) => (n == null ? "-" : `${Math.round(n * 100)}%`);

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZoneName: "short" });
}

export function compass(deg: number): string {
  const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return dirs[Math.round(deg / 22.5) % 16];
}

export function compactPopulation(n: number): string {
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(1)} L`;
  return fmtInt(n);
}

export const COMPONENT_LABELS: Record<string, string> = {
  hazard_exposure: "Hazard exposure",
  infrastructure_vulnerability: "Infrastructure vulnerability",
  environmental_exposure: "Environmental exposure",
  criticality: "Criticality",
};
