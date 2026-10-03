// Thin fetch wrapper. No secrets are bundled: the optional admin API key is typed by the
// operator in Settings and kept only in sessionStorage for the browser session.
import type {
  AlertRule, AlertsResponse, AlertItem, AssetRiskDetail, CycloneListItem, CycloneStatus, DataSource, ModelInfo,
  RiskConfig, RiskMapResponse, Scenario, StatisticsResponse, TrackResponse, UploadResult, Asset, WeatherObs,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
const KEY_STORAGE = "cg_admin_api_key";

export class ApiError extends Error {
  status: number;
  details: unknown;
  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export const apiKey = {
  get: () => sessionStorage.getItem(KEY_STORAGE) ?? "",
  set: (v: string) => (v ? sessionStorage.setItem(KEY_STORAGE, v) : sessionStorage.removeItem(KEY_STORAGE)),
};

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const key = apiKey.get();
  if (key) headers.set("X-API-Key", key);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the CycloneGuard API. Is the backend running on port 8000?");
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const d = data as { detail?: unknown; errors?: { loc: string[]; msg: string }[] } | null;
    let msg = `Request failed (${res.status})`;
    if (d?.errors?.length) msg = d.errors.map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`).join("; ");
    else if (typeof d?.detail === "string") msg = d.detail;
    else if (d?.detail && typeof d.detail === "object" && "message" in d.detail) msg = String((d.detail as { message: string }).message);
    throw new ApiError(res.status, msg, d);
  }
  return data as T;
}

type Filters = { cyclone_id?: number | null; district?: string | null; asset_type?: string | null };

export const api = {
  health: () => request<{ status: string; auth_enabled: boolean }>("/api/health"),
  cyclones: () => request<CycloneListItem[]>("/api/cyclones"),
  currentCyclone: (cyclone_id?: number | null) => request<CycloneStatus>(`/api/cyclone/current${qs({ cyclone_id })}`),
  activateCyclone: (id: number) => request<CycloneStatus>(`/api/cyclone/${id}/activate`, { method: "POST" }),
  track: (cyclone_id?: number | null) => request<TrackResponse>(`/api/cyclone/track${qs({ cyclone_id })}`),
  riskMap: (f: Filters) => request<RiskMapResponse>(`/api/risk/map${qs(f)}`),
  priority: (f: Filters & { limit?: number }) =>
    request<{ items: RiskMapResponse["assets"] }>(`/api/risk/priority${qs(f)}`),
  assetRisk: (id: number, cyclone_id?: number | null) => request<AssetRiskDetail>(`/api/risk/${id}${qs({ cyclone_id })}`),
  statistics: (f: Filters) => request<StatisticsResponse>(`/api/statistics${qs({ cyclone_id: f.cyclone_id, district: f.district })}`),
  alerts: (f: Filters & { severity?: string; include_acknowledged?: boolean }) => request<AlertsResponse>(`/api/alerts${qs(f)}`),
  alertRules: () => request<AlertRule[]>("/api/alerts/rules"),
  acknowledgeAlert: (id: number) => request<AlertItem>(`/api/alerts/${id}/acknowledge`, { method: "POST" }),
  scenarios: () => request<Scenario[]>("/api/demo/scenarios"),
  generateDemo: (scenario: string, regenerate_assets = true) =>
    request<{ cyclone: CycloneStatus; model_run_id: number; n_assets: number }>("/api/demo/generate", {
      method: "POST",
      body: JSON.stringify({ scenario, regenerate_assets }),
    }),
  rerun: (cyclone_id?: number | null) =>
    request<{ model_run_id: number }>("/api/predict", { method: "POST", body: JSON.stringify({ cyclone_id: cyclone_id ?? null }) }),
  getRiskSettings: () => request<{ config: RiskConfig; defaults: RiskConfig; note: string }>("/api/settings/risk"),
  putRiskSettings: (cfg: RiskConfig) =>
    request<{ config: RiskConfig; model_run_id: number | null }>("/api/settings/risk", { method: "PUT", body: JSON.stringify(cfg) }),
  resetRiskSettings: () => request<{ config: RiskConfig }>("/api/settings/risk/reset", { method: "POST" }),
  modelInfo: () => request<ModelInfo>("/api/model/info"),
  dataSources: () => request<DataSource[]>("/api/data-sources"),
  infrastructure: (p: { asset_type?: string; district?: string; q?: string; limit?: number; offset?: number }) =>
    request<{ total: number; items: Asset[] }>(`/api/infrastructure${qs(p)}`),
  assetTypes: () => request<{ key: string; label: string; criticality: number }[]>("/api/infrastructure/types"),
  upload: (file: File, mode: "append" | "replace") => {
    const fd = new FormData();
    fd.append("file", file);
    return request<UploadResult>(`/api/infrastructure/upload${qs({ mode })}`, { method: "POST", body: fd });
  },
  deleteUploaded: () => request<{ deleted: number }>("/api/infrastructure/uploaded", { method: "DELETE" }),
  weather: (cyclone_id?: number | null) => request<{ items: WeatherObs[] }>(`/api/weather${qs({ cyclone_id })}`),
  refreshWeather: () => request<{ status: string; message?: string; stations?: number }>("/api/weather/refresh", { method: "POST" }),
  templateUrl: `${BASE}/api/infrastructure/template.csv`,
};
