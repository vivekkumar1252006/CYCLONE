import { useEffect, useMemo } from "react";
import L from "leaflet";
import {
  Circle, CircleMarker, GeoJSON, LayerGroup, LayersControl, MapContainer, Marker, Pane, Polyline, TileLayer, Tooltip, useMap,
  useMapEvents,
} from "react-leaflet";
import type { Feature, FeatureCollection, Polygon as GJPolygon } from "geojson";
import type { CycloneStatus, RiskCategory, RiskMapResponse, TrackPoint, TrackResponse } from "../api/types";
import { RISK_COLORS, fmtTime } from "../utils/format";

type Classifier = (v: number) => RiskCategory | null;

const windClass: Classifier = (v) => (v >= 118 ? "Very High" : v >= 89 ? "High" : v >= 62 ? "Moderate" : v >= 40 ? "Low" : null);
const rainClass: Classifier = (v) => (v >= 300 ? "Very High" : v >= 200 ? "High" : v >= 100 ? "Moderate" : v >= 50 ? "Low" : null);
const probClass: Classifier = (v) => (v >= 0.8 ? "Very High" : v >= 0.6 ? "High" : v >= 0.4 ? "Moderate" : v >= 0.2 ? "Low" : null);
const surgeClass: Classifier = (v) => (v >= 0.75 ? "Very High" : v >= 0.5 ? "High" : v >= 0.25 ? "Moderate" : v >= 0.1 ? "Low" : null);

export const LAYER_LEGENDS: Record<string, string[]> = {
  "Wind-risk zone": ["40-61 km/h", "62-88 km/h", "89-117 km/h", ">=118 km/h"],
  "Rainfall-risk zone": ["50-100 mm", "100-200 mm", "200-300 mm", ">=300 mm"],
  "Flood-risk zone": ["20-40%", "40-60%", "60-80%", ">=80%"],
  "Storm-surge exposure": ["0.10-0.25", "0.25-0.50", "0.50-0.75", ">=0.75"],
};

function cellsToGeoJSON(rows: number[][], col: number, res: number, classify: Classifier): FeatureCollection<GJPolygon> {
  const h = res / 2;
  const features: Feature<GJPolygon>[] = [];
  for (const r of rows) {
    const cls = classify(r[col]);
    if (!cls) continue;
    const [lat, lon] = r;
    features.push({
      type: "Feature",
      properties: { cls, value: r[col] },
      geometry: { type: "Polygon", coordinates: [[[lon - h, lat - h], [lon + h, lat - h], [lon + h, lat + h], [lon - h, lat + h], [lon - h, lat - h]]] },
    });
  }
  return { type: "FeatureCollection", features };
}

const zoneStyle = (f?: Feature) => ({
  stroke: false,
  fillColor: RISK_COLORS[(f?.properties?.cls as RiskCategory) ?? "Low"],
  fillOpacity: 0.32,
});

const MARKER_RADIUS: Record<RiskCategory, number> = { Low: 4, Moderate: 5, High: 7, "Very High": 9 };

const cycloneIcon = L.divIcon({
  className: "cyclone-icon",
  html: `<svg viewBox="0 0 32 32" width="30" height="30" aria-label="Current cyclone position"><circle cx="16" cy="16" r="15" fill="#0b3954" stroke="#fff" stroke-width="2"/><path d="M16 6a10 10 0 0 1 9 6c-3-2-7-2-9 0a4 4 0 1 0 0 8c-2 2-6 2-9 0a10 10 0 0 1 9-14z" fill="#fff"/></svg>`,
  iconSize: [30, 30],
  iconAnchor: [15, 15],
});

const landfallIcon = L.divIcon({
  className: "landfall-icon",
  html: `<div class="landfall-pin">LANDFALL</div>`,
  iconSize: [70, 20],
  iconAnchor: [35, 26],
});

function MapController({ bounds, flyTo }: { bounds: L.LatLngBoundsExpression | null; flyTo: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [20, 20], maxZoom: 9 });
  }, [map, bounds]);
  useEffect(() => {
    if (flyTo) map.flyTo(flyTo, Math.max(map.getZoom(), 10), { duration: 0.6 });
  }, [map, flyTo]);
  return null;
}

export const DEFAULT_OVERLAYS = [
  "Predicted track + uncertainty", "Historical (observed) track", "Wind-risk zone", "Infrastructure assets",
  "District boundaries (schematic)",
];

function OverlayWatcher({ onChange }: { onChange?: (name: string, active: boolean) => void }) {
  useMapEvents({
    overlayadd: (e) => onChange?.(e.name, true),
    overlayremove: (e) => onChange?.(e.name, false),
  });
  return null;
}

function trackTooltip(p: TrackPoint) {
  return (
    <Tooltip direction="top">
      <div>
        <b>{p.is_forecast ? "Forecast" : "Observed"}</b> - {fmtTime(p.time)}
        <br />
        {p.category} - {Math.round(p.wind_kmh)} km/h{p.pressure_hpa ? `, ${p.pressure_hpa} hPa` : ""}
        {p.is_forecast && (
          <>
            <br />
            Track uncertainty radius ~{Math.round(p.uncertainty_km)} km
          </>
        )}
      </div>
    </Tooltip>
  );
}

interface Props {
  map: RiskMapResponse;
  track: TrackResponse;
  status: CycloneStatus | null;
  selectedAssetId: number | null;
  onSelectAsset: (id: number) => void;
  focusBounds: L.LatLngBoundsExpression | null;
  flyTo: [number, number] | null;
  onOverlayChange?: (name: string, active: boolean) => void;
}

export default function RiskMap({ map, track, status, selectedAssetId, onSelectAsset, focusBounds, flyTo, onOverlayChange }: Props) {
  const res = map.grids?.resolution_deg ?? 0.1;
  const hazard = map.grids?.hazard ?? [];
  const t = map.thresholds;
  const scoreClass: Classifier = (v) =>
    v > t.threshold_high ? "Very High" : v > t.threshold_moderate ? "High" : v > t.threshold_low ? "Moderate" : "Low";

  const layers = useMemo(
    () => ({
      wind: cellsToGeoJSON(hazard, 2, res, windClass),
      rain: cellsToGeoJSON(hazard, 3, res, rainClass),
      flood: cellsToGeoJSON(hazard, 4, res, probClass),
      surge: cellsToGeoJSON(hazard, 5, res, surgeClass),
      vuln: cellsToGeoJSON(map.grids?.vulnerability ?? [], 2, res, scoreClass),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [map.model_run_id, res],
  );
  const zoneRenderer = useMemo(() => L.canvas({ padding: 0.3 }), []);
  const key = `${map.model_run_id}`;
  const observed = track.observed;
  const forecast = track.forecast;
  const current = observed[observed.length - 1];
  const sortedAssets = useMemo(() => [...map.assets].sort((a, b) => a.risk_score - b.risk_score), [map.assets]);

  return (
    <MapContainer center={[20.0, 86.0]} zoom={7} minZoom={5} maxZoom={16} className="map" worldCopyJump>
      <MapController bounds={focusBounds} flyTo={flyTo} />
      <OverlayWatcher onChange={onOverlayChange} />
      <Pane name="zones" style={{ zIndex: 350 }} />
      <Pane name="boundaries" style={{ zIndex: 380 }} />
      <Pane name="tracks" style={{ zIndex: 420 }} />
      <Pane name="assets" style={{ zIndex: 450 }} />
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="OpenStreetMap">
          <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19}
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Light (CARTO, OSM data)">
          <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" maxZoom={19}
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>' />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satellite imagery (Esri)">
          <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" maxZoom={18}
            attribution="Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community" />
        </LayersControl.BaseLayer>

        <LayersControl.Overlay checked name="Predicted track + uncertainty">
          <LayerGroup>
            {forecast.slice(1).map((p) => (
              <Circle key={`u-${p.time}`} center={[p.lat, p.lon]} radius={p.uncertainty_km * 1000} pane="tracks"
                pathOptions={{ color: "#5c7cfa", weight: 1, dashArray: "4 4", fillOpacity: 0.04, interactive: false }} />
            ))}
            <Polyline positions={forecast.map((p) => [p.lat, p.lon])} pane="tracks"
              pathOptions={{ color: "#1c3d8c", weight: 3, dashArray: "8 6" }} />
            {forecast.slice(1).map((p) => (
              <CircleMarker key={`f-${p.time}`} center={[p.lat, p.lon]} radius={5} pane="tracks"
                pathOptions={{ color: "#1c3d8c", fillColor: "#fff", fillOpacity: 1, weight: 2 }}>
                {trackTooltip(p)}
              </CircleMarker>
            ))}
            {status?.landfall && (
              <Marker position={[status.landfall.lat, status.landfall.lon]} icon={landfallIcon} pane="tracks">
                <Tooltip>Estimated landfall near {status.landfall.district} in ~{Math.round(status.landfall.t_hours)} h (forecast estimate)</Tooltip>
              </Marker>
            )}
          </LayerGroup>
        </LayersControl.Overlay>

        <LayersControl.Overlay checked name="Historical (observed) track">
          <LayerGroup>
            <Polyline positions={observed.map((p) => [p.lat, p.lon])} pane="tracks" pathOptions={{ color: "#212529", weight: 3 }} />
            {observed.map((p) => (
              <CircleMarker key={`o-${p.time}`} center={[p.lat, p.lon]} radius={4} pane="tracks"
                pathOptions={{ color: "#212529", fillColor: "#212529", fillOpacity: 1 }}>
                {trackTooltip(p)}
              </CircleMarker>
            ))}
            {current && (
              <>
                <Circle center={[current.lat, current.lon]} radius={current.roi_km * 1000} pane="tracks"
                  pathOptions={{ color: "#495057", weight: 1, dashArray: "2 6", fillOpacity: 0, interactive: false }} />
                <Marker position={[current.lat, current.lon]} icon={cycloneIcon} pane="tracks">
                  <Tooltip>
                    Current position ({fmtTime(current.time)}) - {current.category}, {Math.round(current.wind_kmh)} km/h.
                    Dotted ring: approx. extent of strong winds.
                  </Tooltip>
                </Marker>
              </>
            )}
          </LayerGroup>
        </LayersControl.Overlay>

        <LayersControl.Overlay checked name="Wind-risk zone">
          <GeoJSON key={`wind-${key}`} data={layers.wind} style={zoneStyle} pane="zones" interactive={false} {...{ renderer: zoneRenderer }} />
        </LayersControl.Overlay>
        <LayersControl.Overlay name="Rainfall-risk zone">
          <GeoJSON key={`rain-${key}`} data={layers.rain} style={zoneStyle} pane="zones" interactive={false} {...{ renderer: zoneRenderer }} />
        </LayersControl.Overlay>
        <LayersControl.Overlay name="Flood-risk zone">
          <LayerGroup>
            <GeoJSON key={`flood-${key}`} data={layers.flood} style={zoneStyle} pane="zones" interactive={false} {...{ renderer: zoneRenderer }} />
            {map.reference.flood_zones.map((z) => (
              <GeoJSON key={`fz-${z.name}`} data={z.geometry as GJPolygon} pane="boundaries"
                style={{ color: "#1864ab", weight: 1.5, dashArray: "3 3", fillOpacity: 0 }}>
                <Tooltip sticky>Mapped flood-prone zone (simplified): {z.name}</Tooltip>
              </GeoJSON>
            ))}
          </LayerGroup>
        </LayersControl.Overlay>
        <LayersControl.Overlay name="Storm-surge exposure">
          <GeoJSON key={`surge-${key}`} data={layers.surge} style={zoneStyle} pane="zones" interactive={false} {...{ renderer: zoneRenderer }} />
        </LayersControl.Overlay>
        <LayersControl.Overlay name="Vulnerability heatmap">
          <GeoJSON key={`vuln-${key}`} data={layers.vuln} pane="zones" interactive={false} {...{ renderer: zoneRenderer }}
            style={(f) => ({ stroke: false, fillColor: RISK_COLORS[(f?.properties?.cls as RiskCategory) ?? "Low"], fillOpacity: 0.45 })} />
        </LayersControl.Overlay>

        <LayersControl.Overlay checked name="Infrastructure assets">
          <LayerGroup>
            {sortedAssets.map((a) => {
              const sel = a.asset_id === selectedAssetId;
              return (
                <CircleMarker key={`a-${a.asset_id}-${key}`} center={[a.lat, a.lon]} pane="assets"
                  radius={MARKER_RADIUS[a.risk_category] + (sel ? 4 : 0)}
                  pathOptions={{ color: sel ? "#000" : "#fff", weight: sel ? 3 : 1, fillColor: RISK_COLORS[a.risk_category], fillOpacity: 0.95 }}
                  eventHandlers={{ click: () => onSelectAsset(a.asset_id) }}>
                  <Tooltip direction="top">
                    <b>{a.name}</b>
                    <br />
                    {a.asset_type_label} - Risk {Math.round(a.risk_score)}/100 ({a.risk_category}), {a.confidence_label} confidence
                  </Tooltip>
                </CircleMarker>
              );
            })}
          </LayerGroup>
        </LayersControl.Overlay>

        <LayersControl.Overlay checked name="District boundaries (schematic)">
          <GeoJSON key={`d-${key}`} data={map.districts as unknown as FeatureCollection} pane="boundaries"
            style={{ color: "#495057", weight: 1, dashArray: "5 4", fillOpacity: 0 }}
            onEachFeature={(f, layer) =>
              layer.bindTooltip(`${f.properties.name} (${f.properties.state}) - pop. ${Number(f.properties.population).toLocaleString("en-IN")} (Census 2011)<br/><i>Schematic zone, not an official boundary</i>`, { sticky: true })
            } />
        </LayersControl.Overlay>
        <LayersControl.Overlay name="Rivers & coastline (reference)">
          <LayerGroup>
            <GeoJSON key="coast" data={map.reference.coastline as never} pane="boundaries" style={{ color: "#0b7285", weight: 2 }} interactive={false} />
            {map.reference.rivers.map((r) => (
              <GeoJSON key={`r-${r.name}`} data={r.geometry as never} pane="boundaries" style={{ color: "#339af0", weight: 2 }}>
                <Tooltip sticky>{r.name} (simplified course)</Tooltip>
              </GeoJSON>
            ))}
          </LayerGroup>
        </LayersControl.Overlay>
      </LayersControl>
    </MapContainer>
  );
}
