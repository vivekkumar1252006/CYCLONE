import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import { useApp } from "./context/AppContext";
import { useApi } from "./hooks/useApi";
import Dashboard from "./pages/Dashboard";
import AlertsPage from "./pages/AlertsPage";
import AssetPage from "./pages/AssetPage";
import DataPage from "./pages/DataPage";
import SettingsPage from "./pages/SettingsPage";
import ModelPage from "./pages/ModelPage";
import { EmptyState } from "./components/States";

function DataModeBanner() {
  const { version } = useApp();
  const { data, error } = useApi(() => api.currentCyclone(), [version]);
  if (error || !data) return null;
  return data.is_demo ? (
    <div className="banner banner-demo" role="note">
      <b>DEMO / SIMULATED DATA</b> - {data.name} is a fictional scenario generated for demonstration. Not real-world observations or
      official forecasts. All risk values are model estimates.
    </div>
  ) : (
    <div className="banner banner-live" role="note">
      <b>{data.data_mode}</b> - {data.name}. Risk values are model estimates with stated confidence; follow official advisories.
    </div>
  );
}

function AlertCount() {
  const { version } = useApp();
  const { data } = useApi(() => api.alerts({ include_acknowledged: false }), [version]);
  const n = data ? data.counts.critical + data.counts.warning : 0;
  return n > 0 ? <span className="nav-count" aria-label={`${n} open alerts`}>{n}</span> : null;
}

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={28} height={28} />
          <div>
            <div className="brand-name">CycloneGuard AI</div>
            <div className="brand-sub">Cyclone impact &amp; infrastructure vulnerability forecast</div>
          </div>
        </div>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/alerts">Alerts <AlertCount /></NavLink>
          <NavLink to="/data">Data</NavLink>
          <NavLink to="/model">Model</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </header>
      <DataModeBanner />
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/asset/:id" element={<AssetPage />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="/model" element={<ModelPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<EmptyState title="Page not found" />} />
        </Routes>
      </main>
      <footer className="footer">
        CycloneGuard AI prototype - predictions are model estimates with uncertainty and must not replace official IMD / SDMA warnings.
        Basemap &copy; OpenStreetMap contributors.
      </footer>
    </div>
  );
}
