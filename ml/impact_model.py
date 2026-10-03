"""Model A - Cyclone Impact Model (parametric, physics-informed baseline).

Estimates, for any location, the hazard a cyclone track is expected to deliver:

* peak sustained wind (km/h) -> wind impact index (0-1)
* accumulated rainfall (mm)  -> rainfall impact index (0-1)
* flooding probability (0-1)
* storm-surge exposure index (0-1)

This is NOT a trained black box. It uses well-known simplified relationships:

* Wind: modified Rankine vortex  V(r) = Vmax * (Rmw / r)^alpha  outside the
  radius of maximum wind, with a translational asymmetry term (stronger on the
  right-hand side of motion in the northern hemisphere).
* Rain: an exponentially decaying rain-rate profile integrated hourly along the
  track, scaled by intensity (a simplified R-CLIPER style climatology).
* Flood: logistic combination of the rainfall index with terrain
  susceptibility (low elevation, river proximity, mapped flood zones, flat
  slope).
* Surge: intensity x proximity x right-side factor, attenuated by distance
  from coast and ground elevation.

All coefficients are documented constants below so they can be calibrated
against observations (e.g. IMD best-track + station rainfall) later. The model
implements ``ImpactModel`` so a data-driven model can replace it.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

from .geo import EARTH_RADIUS_KM

# ---- documented coefficients -------------------------------------------------
WIND_DECAY_ALPHA = 0.6          # outer-vortex decay exponent
WIND_IMPACT_FLOOR_KMH = 40.0    # winds below this have ~no structural impact
WIND_IMPACT_CEIL_KMH = 160.0    # winds at/above this (VSCS-force) -> impact index 1
RAIN_EFOLD_KM = 100.0          # rain-rate e-folding distance beyond Rmw
RAIN_IMPACT_FLOOR_MM = 25.0
RAIN_IMPACT_CEIL_MM = 400.0    # multi-day event total treated as maximal impact
SURGE_MIN_WIND_KMH = 62.0       # cyclonic-storm threshold (IMD)
SURGE_MAX_WIND_KMH = 200.0
SURGE_COAST_EFOLD_KM = 8.0      # inland penetration scale of surge
SURGE_ELEV_EFOLD_M = 4.0


@dataclass
class SiteContext:
    lat: float
    lon: float
    elevation_m: float = 10.0
    dist_coast_km: float = 50.0
    dist_river_km: float = 20.0
    in_flood_zone: bool = False
    slope_deg: float = 2.0
    observed_rain_mm: float | None = None  # optional station / gridded observation


@dataclass
class ImpactResult:
    peak_wind_kmh: float
    wind_impact: float
    rainfall_mm: float
    rainfall_impact: float
    flood_probability: float
    surge_exposure: float
    dist_track_km: float
    closest_approach_hours: float
    track_uncertainty_km: float
    right_side_of_track: bool

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def _clip01(x):
    return np.clip(x, 0.0, 1.0)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def terrain_flood_susceptibility(elevation_m: float, dist_river_km: float, in_flood_zone: bool, slope_deg: float) -> float:
    """0-1 terrain susceptibility to flooding (used by Model A and the risk engine)."""
    low_elev = math.exp(-max(elevation_m, 0.0) / 8.0)
    river = math.exp(-max(dist_river_km, 0.0) / 5.0)
    flat = 1.0 if slope_deg < 2.0 else max(0.0, 1.0 - (slope_deg - 2.0) / 8.0)
    return float(0.35 * low_elev + 0.30 * river + 0.25 * (1.0 if in_flood_zone else 0.0) + 0.10 * flat)


class ImpactModel(ABC):
    """Interface for cyclone impact models (swap in a trained model later)."""

    name: str = "abstract"
    version: str = "0"

    @abstractmethod
    def predict(self, track: Sequence[dict], sites: Sequence[SiteContext]) -> list[ImpactResult]:
        ...


class ParametricImpactModel(ImpactModel):
    name = "parametric-rankine-v1"
    version = "1.0.0"

    def _track_arrays(self, track: Sequence[dict]):
        lat = np.array([p["lat"] for p in track], dtype=float)
        lon = np.array([p["lon"] for p in track], dtype=float)
        vmax = np.array([p.get("wind_kmh", 0.0) for p in track], dtype=float)
        rmw = np.array([max(p.get("rmw_km", 30.0), 5.0) for p in track], dtype=float)
        roi = np.array([max(p.get("roi_km", 250.0), 50.0) for p in track], dtype=float)
        t = np.array([p.get("t_hours", i) for i, p in enumerate(track)], dtype=float)
        unc = np.array([p.get("uncertainty_km", 0.0) for p in track], dtype=float)
        # motion vector (km/h) per point, forward difference
        n = len(track)
        vx = np.zeros(n)
        vy = np.zeros(n)
        for i in range(n):
            j0, j1 = (i, i + 1) if i < n - 1 else (i - 1, i)
            if j0 < 0:
                continue
            dt = max(t[j1] - t[j0], 1e-6)
            mlat = math.radians((lat[j0] + lat[j1]) / 2)
            vx[i] = math.radians(lon[j1] - lon[j0]) * EARTH_RADIUS_KM * math.cos(mlat) / dt
            vy[i] = math.radians(lat[j1] - lat[j0]) * EARTH_RADIUS_KM / dt
        # hourly weights for rainfall integration (time each point represents)
        dt_w = np.gradient(t) if n > 1 else np.ones(1)
        return lat, lon, vmax, rmw, roi, t, unc, vx, vy, np.abs(dt_w)

    def predict(self, track: Sequence[dict], sites: Sequence[SiteContext]) -> list[ImpactResult]:
        if not track:
            raise ValueError("track must contain at least one point")
        lat, lon, vmax, rmw, roi, t, unc, vx, vy, dt_w = self._track_arrays(track)
        results: list[ImpactResult] = []
        for s in sites:
            # site position relative to each track point (km, local tangent plane)
            mlat = np.radians((lat + s.lat) / 2)
            dx = np.radians(s.lon - lon) * EARTH_RADIUS_KM * np.cos(mlat)
            dy = np.radians(s.lat - lat) * EARTH_RADIUS_KM
            r = np.hypot(dx, dy)

            # --- wind ---
            r_safe = np.maximum(r, 1e-3)
            inner = vmax * np.clip(r_safe / rmw, 0, 1)
            outer = vmax * np.power(rmw / r_safe, WIND_DECAY_ALPHA)
            v_sym = np.where(r_safe <= rmw, inner, outer)
            # fade to zero beyond 1.5x radius of influence
            v_sym = v_sym * _clip01(1.0 - (r_safe - roi) / (0.5 * roi))
            vt = np.hypot(vx, vy)
            # sin(angle from motion to site); >0 => site on right of motion (NH)
            cross = vx * dy - vy * dx  # z of motion x site-vector; <0 => right side
            sin_side = np.where(vt * r_safe > 0, -cross / (vt * r_safe + 1e-9), 0.0)
            v = np.maximum(v_sym + 0.5 * vt * sin_side * (v_sym > 0), 0.0)
            k = int(np.argmax(v))
            peak_wind = float(v[k])

            # --- rain (hourly accumulation) ---
            r0 = 2.0 + vmax / 15.0  # mm/h near the core (~13 mm/h for a VSCS)
            rate = np.where(r <= rmw, r0, r0 * np.exp(-(r - rmw) / RAIN_EFOLD_KM))
            rate = np.where(r <= 2.0 * roi, rate, 0.0)
            rain = float(np.sum(rate * dt_w))
            if s.observed_rain_mm is not None and s.observed_rain_mm >= 0:
                # blend model with observation (observations weighted 30%)
                rain = 0.7 * rain + 0.3 * float(s.observed_rain_mm)

            wind_impact = float(_clip01((peak_wind - WIND_IMPACT_FLOOR_KMH) / (WIND_IMPACT_CEIL_KMH - WIND_IMPACT_FLOOR_KMH)))
            rain_impact = float(_clip01((rain - RAIN_IMPACT_FLOOR_MM) / (RAIN_IMPACT_CEIL_MM - RAIN_IMPACT_FLOOR_MM)))

            # --- flood ---
            sus = terrain_flood_susceptibility(s.elevation_m, s.dist_river_km, s.in_flood_zone, s.slope_deg)
            flood_p = float(_sigmoid(-5.0 + 5.0 * rain_impact + 4.0 * sus + 3.0 * rain_impact * sus))

            # --- surge ---
            intensity = _clip01((vmax - SURGE_MIN_WIND_KMH) / (SURGE_MAX_WIND_KMH - SURGE_MIN_WIND_KMH))
            proximity = np.exp(-np.maximum(r - rmw, 0.0) / (3.0 * rmw + 40.0))
            side_f = np.where(sin_side > 0, 1.0, 0.5)
            surge_potential = float(np.max(intensity * proximity * side_f))
            coastal = math.exp(-max(s.dist_coast_km, 0.0) / SURGE_COAST_EFOLD_KM)
            elev_f = math.exp(-max(s.elevation_m, 0.0) / SURGE_ELEV_EFOLD_M)
            surge = float(_clip01(surge_potential * coastal * (0.4 + 0.6 * elev_f)))

            # --- closest approach ---
            j = int(np.argmin(r))
            results.append(ImpactResult(
                peak_wind_kmh=peak_wind,
                wind_impact=wind_impact,
                rainfall_mm=rain,
                rainfall_impact=rain_impact,
                flood_probability=flood_p,
                surge_exposure=surge,
                dist_track_km=float(r[j]),
                closest_approach_hours=float(t[j]),
                track_uncertainty_km=float(unc[j]),
                right_side_of_track=bool(sin_side[j] > 0),
            ))
        return results
