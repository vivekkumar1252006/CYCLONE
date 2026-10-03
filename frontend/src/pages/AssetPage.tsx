import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useApp } from "../context/AppContext";
import { useApi } from "../hooks/useApi";
import AssetDetail from "../components/AssetDetail";
import { ErrorState, Loading } from "../components/States";

export default function AssetPage() {
  const { id } = useParams();
  const { version } = useApp();
  const assetId = Number(id);
  const valid = Number.isInteger(assetId) && assetId > 0;
  const detail = useApi(() => (valid ? api.assetRisk(assetId) : Promise.reject(new Error("Invalid asset id"))), [assetId, version]);
  return (
    <div className="page page-narrow">
      <Link to="/" className="btn btn-small">&larr; Back to dashboard</Link>
      <div className="card">
        {detail.error ? <ErrorState message={detail.error} onRetry={detail.reload} /> :
          detail.data ? <AssetDetail d={detail.data} /> : <Loading label="Loading asset risk..." />}
      </div>
    </div>
  );
}
