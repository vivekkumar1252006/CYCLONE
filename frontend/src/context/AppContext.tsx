import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface AppState {
  /** Incremented whenever server-side predictions change, so views refetch. */
  version: number;
  bump: () => void;
  district: string;
  setDistrict: (d: string) => void;
  assetType: string;
  setAssetType: (t: string) => void;
  selectedAssetId: number | null;
  selectAsset: (id: number | null) => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0);
  const [district, setDistrict] = useState("");
  const [assetType, setAssetType] = useState("");
  const [selectedAssetId, selectAsset] = useState<number | null>(null);
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const value = useMemo(
    () => ({ version, bump, district, setDistrict, assetType, setAssetType, selectedAssetId, selectAsset }),
    [version, bump, district, assetType, selectedAssetId],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used inside AppProvider");
  return v;
}
