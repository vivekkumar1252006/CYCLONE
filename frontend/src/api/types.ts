export type RiskCategory = "Low" | "Moderate" | "High" | "Very High";
export type ConfidenceLabel = "Low" | "Medium" | "High";

export interface DataLabel {
  is_demo: boolean;
  data_mode: string;
  source: string;
  disclaimer: string;
}

export interface Landfall {
  lat: number;
  lon: number;
  t_hours: number;
  wind_kmh: number;
  district: string;
  is_forecast: boolean;
}

export interface CycloneStatus extends DataLabel {
  id: number;
  name: string;
  description: string | null;
  basin: string;
  analysis_time: string;
  position: { lat: number; lon: number };
  wind_kmh: number;
  pressure_hpa: number | null;
  category: string;
  category_name: string;
  movement: { bearing_deg: number; speed_kmh: number } | null;
  max_forecast_wind_kmh: number;
  forecast_hours: number;
  landfall: Landfall | null;
  model_run_id: number | null;
}

export interface CycloneListItem extends DataLabel {
  id: number;
  name: string;
  description: string | null;
  scenario_key: string | null;
  active: boolean;
}

export interface TrackPoint {
  time: string;
  t_hours: number;
  lat: number;
  lon: number;
  wind_kmh: number;
  pressure_hpa: number | null;
  category: string;
  rmw_km: number;
  roi_km: number;
  uncertainty_km: number;
  is_forecast: boolean;
}

export interface TrackResponse extends DataLabel {
  cyclone_id: number;
  name: string;
  points: TrackPoint[];
  observed: TrackPoint[];
  forecast: TrackPoint[];
  note: string;
}

export interface AssetRiskSummary {
  asset_id: number;
  name: string;
  asset_type: string;
  asset_type_label: string;
  district: string | null;
  lat: number;
  lon: number;
  risk_score: number;
  risk_category: RiskCategory;
  confidence: number;
  confidence_label: ConfidenceLabel;
  main_hazard: string;
  dist_track_km: number;
  source: string;
  is_demo: boolean;
}

export interface Grids {
  resolution_deg: number;
  hazard_columns: string[];
  hazard: number[][]; // lat, lon, wind, rain, flood, surge
  vulnerability_columns: string[];
  vulnerability: number[][]; // lat, lon, score
}

export interface GeoJSONGeometry {
  type: string;
  coordinates: unknown;
}

export interface RiskMapResponse extends DataLabel {
  cyclone_id: number;
  model_run_id: number;
  assets: AssetRiskSummary[];
  grids: Grids;
  districts: {
    type: "FeatureCollection";
    features: { type: "Feature"; geometry: GeoJSONGeometry; properties: { name: string; state: string; population: number; note: string } }[];
  };
  reference: {
    coastline: GeoJSONGeometry;
    rivers: { name: string; geometry: GeoJSONGeometry }[];
    flood_zones: { name: string; geometry: GeoJSONGeometry }[];
    note: string;
  };
  bbox: [number, number, number, number];
  thresholds: { threshold_low: number; threshold_moderate: number; threshold_high: number };
}

export interface Factor {
  factor: string;
  direction: "increases" | "decreases";
  strength: number;
}

export interface MlAttribution {
  key: string;
  feature: string;
  effect: number;
  direction: "increases" | "decreases";
}

export interface Recommendation {
  action: string;
  priority: "High" | "Medium" | "Low";
  reason: string;
}

export interface ConfidenceDetail {
  value: number;
  label: ConfidenceLabel;
  components: Record<string, number>;
  model_spread?: number | null;
  score_band?: number;
}

export interface PredictedHazard {
  hazard: string;
  level: "Low" | "Moderate" | "High";
  index: number;
  detail: string;
}

export interface Asset {
  id: number;
  name: string;
  asset_type: string;
  asset_type_label?: string;
  lat: number;
  lon: number;
  district: string | null;
  elevation_m: number;
  elevation_source: string;
  slope_deg: number;
  dist_coast_km: number;
  dist_river_km: number;
  in_flood_zone: boolean;
  land_use: string | null;
  age_years: number | null;
  historical_damage_count: number | null;
  criticality: number | null;
  capacity: string | null;
  source: string;
  is_demo: boolean;
  risk_score?: number;
  risk_category?: RiskCategory;
  confidence?: number;
}

export interface AssetRiskDetail extends DataLabel {
  cyclone_id: number;
  cyclone_name: string;
  model_run_id: number;
  asset: Asset;
  risk_score: number;
  risk_category: RiskCategory;
  score_band: number;
  confidence: ConfidenceDetail;
  vulnerability_probability: number;
  main_hazard: string;
  predicted_hazards: PredictedHazard[];
  distance_from_track_km: number;
  closest_approach_hours: number;
  track_uncertainty_km: number;
  right_side_of_track: boolean;
  flood_exposure: number;
  wind_exposure: number;
  peak_wind_kmh: number;
  rainfall_mm: number;
  surge_exposure: number;
  criticality: number;
  components: Record<string, number>;
  contributions: Record<string, number>;
  main_risk_factors: Factor[];
  ml_attributions: MlAttribution[];
  recommendations: Recommendation[];
  recommendations_disclaimer: string;
  weights: Record<string, number>;
  models: { impact: string; vulnerability: string };
  note: string;
}

export interface DistrictStat {
  district: string;
  state: string;
  population: number;
  assets: number;
  high_risk_assets: number;
  very_high_risk_assets: number;
  max_risk: number;
  mean_risk: number;
  area_fraction_gale: number;
  area_fraction_flood: number;
  population_exposed_gale: number;
  population_exposed_severe: number;
}

export interface StatisticsResponse extends DataLabel {
  cyclone_id: number;
  model_run_id: number;
  cards: {
    cyclone_status: CycloneStatus;
    max_wind_kmh: number;
    affected_districts: number;
    affected_district_names: string[];
    high_risk_infrastructure: number;
    very_high_risk_infrastructure: number;
    population_exposed: number;
    population_note: string;
    total_assets: number;
    alerts: number;
  };
  risk_distribution: { category: RiskCategory; count: number }[];
  risk_by_type: ({ asset_type: string; label: string; total: number } & Record<RiskCategory, number>)[];
  hazard_contribution: {
    name: string;
    asset_id: number;
    risk_score: number;
    hazard_exposure: number;
    infrastructure_vulnerability: number;
    environmental_exposure: number;
    criticality: number;
  }[];
  average_hazard_index: Record<string, number>;
  districts: DistrictStat[];
  intensity_timeline: { time: string; t_hours: number; wind_kmh: number; pressure_hpa: number | null; category: string; is_forecast: boolean }[];
}

export interface AlertItem {
  id: number;
  rule: string;
  severity: "critical" | "warning" | "advisory";
  title: string;
  message: string;
  location: string;
  district: string | null;
  asset_id: number;
  infrastructure: string;
  asset_type: string;
  asset_type_label: string;
  lat: number;
  lon: number;
  risk_score: number;
  confidence: number;
  main_hazard: string;
  recommended_action: string;
  triggered_rules: string[];
  acknowledged: boolean;
  created_at: string;
}

export interface AlertsResponse extends DataLabel {
  cyclone_id: number;
  counts: Record<"critical" | "warning" | "advisory", number>;
  items: AlertItem[];
  note: string;
}

export interface AlertRule {
  key: string;
  severity: string;
  title: string;
  condition: string;
}

export interface Scenario {
  key: string;
  name: string;
  description: string;
  peak_wind_kmh: number;
  data_mode: string;
}

export interface RiskConfig {
  w_hazard: number;
  w_vulnerability: number;
  w_environment: number;
  w_criticality: number;
  hazard_gate: number;
  threshold_low: number;
  threshold_moderate: number;
  threshold_high: number;
  alert_min_confidence: number;
  hazard_subweights: { wind: number; rain: number; flood: number; surge: number };
}

export interface ModelInfo {
  impact_model: { name: string; version: string; type: string; outputs: string[] };
  vulnerability_model: {
    name: string;
    version: string;
    metrics: Record<string, string | number>;
    feature_importances: Record<string, number>;
    training_data_warning: string;
  };
  explainability: string;
}

export interface DataSource {
  family: string;
  provider: string;
  mode: string;
  note: string;
}

export interface UploadResult {
  accepted: number;
  rejected: { row?: number; feature?: number; name?: string; error: string }[];
  rejected_count: number;
  warnings: string[];
  mode: string;
  model_run_id: number | null;
  derived_fields_note: string;
}

export interface WeatherObs {
  id: number;
  station_name: string;
  lat: number;
  lon: number;
  observed_at: string;
  rainfall_mm: number | null;
  wind_speed_kmh: number | null;
  wind_direction_deg: number | null;
  temperature_c: number | null;
  humidity_pct: number | null;
  surge_indicator_m: number | null;
  source: string;
  is_demo: boolean;
}
