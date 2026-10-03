import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import L from "leaflet";
import { api } from "../api/client";
import { useApp } from "../context/AppContext";
import { useApi } from "../hooks/useApi";
import RiskMap, { DEFAULT_OVERLAYS } from "../components/RiskMap";
import MapLegend from "../components/MapLegend";
import StatCards from "../components/StatCards";
import PriorityList from "../components/PriorityList";
import AssetDetail from "../components/AssetDetail";
import ScenarioBar from "../components/ScenarioBar";
import {
  DistrictHighRiskChart, HazardContributionChart, IntensityTimeline, RiskByTypeChart, RiskDistributionChart,
} from "../components/Charts";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { compactPopulation, fmtInt, pct } from "../utils/format";

function NoCyclone() {
  return (
    <EmptyState title="No cyclone loaded">
      Choose a demo scenario above and click <b>Load demo scenario</b>, or create a track via <code>POST /api/cyclones</code>.
    </EmptyState>
  );
}

export default function Dashboard() {
  const { version, district, setDistrict, assetType, setAssetType, selectedAssetId, selectAsset } = useApp();
  const [search, setSearch] = useState("");
  const [flyTo, setFlyTo] = useState<[number, number] | null>(null);
  const [overlays, setOverlays] = useState<string[]>(DEFAULT_OVERLAYS);

  const status = useApi(() => api.currentCyclone(), [version]);
  const mapData = useApi(() => api.riskMap({ district, asset_type: assetType }), [version, district, assetType]);
  const track = useApi(() => api.track(), [version]);
  const stats = useApi(() => api.statistics({ district }), [version, district]);
  const priority = useApi(() => api.priority({ district, asset_type: assetType, limit: 25 }), [version, district, assetType]);
  const types = useApi(() => api.assetTypes(), []);
  const detail = useApi(
    () => (selectedAssetId ? api.assetRisk(selectedAssetId) : Promise.resolve(null)),
    [selectedAssetId, version],
  );

  const districtNames = useMemo(
    () => (mapData.data?.districts.features.map((f) => f.properties.name) ?? []).sort(),
    [mapData.data],
  );

  const focusBounds = useMemo(() => {
    if (!mapData.data || !district) return null;
    const f = mapData.data.districts.features.find((x) => x.properties.name === district);
    if (!f) return null;
    return L.geoJSON(f as never).getBounds();
  }, [mapData.data, district]);

  const selectAndFly = (id: number) => {
    selectAsset(id);
    const a = mapData.data?.assets.find((x) => x.asset_id === id);
    if (a) setFlyTo([a.lat, a.lon]);
  };

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = search.trim().toLowerCase();
    if (!q || !mapData.data) return;
    const hit = mapData.data.assets.find((a) => a.name.toLowerCase() === q) ??
      mapData.data.assets.find((a) => a.name.toLowerCase().includes(q));
    if (hit) selectAndFly(hit.asset_id);
  };
  const searchMiss = search.trim().length > 1 && mapData.data &&
    !mapData.data.assets.some((a) => a.name.toLowerCase().includes(search.trim().toLowerCase()));

  const notLoaded = [status.error, mapData.error].some((e) => e?.startsWith("No cyclone loaded"));

  return (
    <div className="dashboard">
      <ScenarioBar />
      {notLoaded ? (
        <NoCyclone />
      ) : (
        <>
          {stats.error ? <ErrorState message={stats.error} onRetry={stats.reload} /> :
            stats.data ? <StatCards stats={stats.data} /> : <Loading label="Loading indicators..." />}

          <div className="dash-main">
            <section className="card map-card" aria-label="Interactive risk map">
              <div className="map-toolbar">
                <form onSubmit={onSearch} className="search" role="search">
                  <input list="asset-names" placeholder="Search infrastructure..." value={search}
                    onChange={(e) => setSearch(e.target.value)} aria-label="Search infrastructure by name" maxLength={100} />
                  <datalist id="asset-names">
                    {mapData.data?.assets.slice(0, 400).map((a) => <option key={a.asset_id} value={a.name} />)}
                  </datalist>
                  <button className="btn btn-small" type="submit">Find</button>
                  {searchMiss && <span className="muted small">No match</span>}
                </form>
                <select value={district} onChange={(e) => setDistrict(e.target.value)} aria-label="Filter by district">
                  <option value="">All districts</option>
                  {districtNames.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
                <select value={assetType} onChange={(e) => setAssetType(e.target.value)} aria-label="Filter by asset type">
                  <option value="">All asset types</option>
                  {types.data?.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                </select>
                {(district || assetType) && (
                  <button className="btn btn-small" onClick={() => { setDistrict(""); setAssetType(""); }}>Clear filters</button>
                )}
              </div>
              <div className="map-wrap">
                {mapData.error ? <ErrorState message={mapData.error} onRetry={mapData.reload} /> :
                  track.error ? <ErrorState message={track.error} onRetry={track.reload} /> :
                  mapData.data && track.data ? (
                    <>
                      <RiskMap map={mapData.data} track={track.data} status={status.data} selectedAssetId={selectedAssetId}
                        onSelectAsset={selectAsset} focusBounds={focusBounds} flyTo={flyTo}
                        onOverlayChange={(name, on) => setOverlays((o) => (on ? [...new Set([...o, name])] : o.filter((x) => x !== name)))} />
                      <MapLegend active={overlays} thresholds={mapData.data.thresholds} />
                      {mapData.loading && <div className="map-loading"><Loading label="Updating..." /></div>}
                    </>
                  ) : <Loading label="Loading map..." />}
              </div>
              <div className="muted small map-foot">
                {mapData.data?.reference.note} District zones are schematic. Use the layer control (top-right) to toggle hazard
                zones, the vulnerability heatmap and satellite imagery.
              </div>
            </section>

            <aside className="card side-panel" aria-label={selectedAssetId ? "Infrastructure detail" : "Priority infrastructure"}>
              {selectedAssetId ? (
                <>
                  <div className="side-head">
                    <button className="btn btn-small" onClick={() => selectAsset(null)}>&larr; Priority list</button>
                    <Link className="btn btn-small" to={`/asset/${selectedAssetId}`}>Open full page</Link>
                  </div>
                  {detail.error ? (
                    <ErrorState message={detail.error} onRetry={detail.reload} />
                  ) : detail.data && detail.data.asset.id === selectedAssetId ? (
                    <AssetDetail d={detail.data} />
                  ) : (
                    <Loading label="Loading asset risk..." />
                  )}
                </>
              ) : (
                <>
                  <div className="side-head">
                    <h2>Priority infrastructure</h2>
                    <span className="muted small">Ranked by estimated risk</span>
                  </div>
                  {priority.error ? <ErrorState message={priority.error} onRetry={priority.reload} /> :
                    priority.data ? <PriorityList items={priority.data.items} selectedId={selectedAssetId} onSelect={selectAndFly} /> :
                    <Loading />}
                </>
              )}
            </aside>
          </div>

          {stats.data && (
            <>
              <div className="charts-grid">
                <section className="card">
                  <h3>Risk distribution</h3>
                  <RiskDistributionChart data={stats.data.risk_distribution} />
                </section>
                <section className="card">
                  <h3>Cyclone intensity timeline</h3>
                  <IntensityTimeline data={stats.data.intensity_timeline} />
                </section>
                <section className="card">
                  <h3>Infrastructure risk by type</h3>
                  <RiskByTypeChart data={stats.data.risk_by_type} />
                </section>
                <section className="card">
                  <h3>Hazard contribution - top 10 assets</h3>
                  <p className="muted small">Points contributed by each risk component (click a bar to inspect).</p>
                  <HazardContributionChart data={stats.data.hazard_contribution} onSelect={selectAndFly} />
                </section>
              </div>
              <section className="card">
                <h3>District-level statistics</h3>
                <div className="district-grid">
                  <DistrictHighRiskChart data={stats.data.districts} />
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>District</th><th>Assets</th><th>High+</th><th>Max risk</th><th>Area &gt;= 62 km/h</th>
                          <th>Flood-prone area</th><th>Pop. exposed (est.)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.data.districts.map((d) => (
                          <tr key={d.district} className={d.district === district ? "row-selected" : ""}>
                            <td><button className="link" onClick={() => setDistrict(d.district === district ? "" : d.district)}>{d.district}</button></td>
                            <td>{d.assets}</td>
                            <td>{d.high_risk_assets}</td>
                            <td>{fmtInt(d.max_risk)}</td>
                            <td>{pct(d.area_fraction_gale)}</td>
                            <td>{pct(d.area_fraction_flood)}</td>
                            <td>{compactPopulation(d.population_exposed_gale)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <p className="muted small">{stats.data.cards.population_note}</p>
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
