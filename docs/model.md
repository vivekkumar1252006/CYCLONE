# Models and risk methodology

## Overview

```
track (observed + forecast, 1-h interpolation)
   │
   ├─► Model A  Parametric impact model ──► peak wind, rainfall, flood probability, surge exposure
   │                                          │
   │   asset features (type, age, history,   │
   │   elevation, coast/river distance) ─────┤
   │                                          ▼
   ├─► Model B  Vulnerability model (RandomForest) ──► P(significant damage / disruption)
   │                                          │
   ▼                                          ▼
 Risk scoring engine (weighted, configurable) ──► score 0–100, category, contributions
 Confidence heuristic ──► value 0–1, label, components
 Explanations ──► plain-language factors + occlusion attribution
 Alert rules + preparedness recommendations
```

## Model A: cyclone impact (`ml/impact_model.py`)

This is a **physics-informed parametric baseline**, not a trained black box. All constants are named and documented in the module.

| Output | Method |
|---|---|
| Peak sustained wind | Modified Rankine vortex: `V = Vmax·(Rmw/r)^0.6` outside the radius of maximum wind, linear inside, faded beyond 1.5× radius of influence. A translational asymmetry term (+0.5·Vtrans·sinθ) makes the right-hand side stronger, as in the northern hemisphere. The maximum is taken over the hourly-interpolated track. |
| Wind impact (0–1) | Linear from 40 km/h (≈ no structural impact) to 160 km/h (VSCS-force) |
| Rainfall (mm) | Rain rate `R0 = 2 + Vmax/15` mm/h in the core, e-folding 100 km beyond Rmw, integrated hourly along the track |
| Rainfall impact (0–1) | Linear from 25 mm to 400 mm event total |
| Flood probability | `sigmoid(−5 + 5·rain + 4·S + 3·rain·S)`. S is terrain susceptibility: low elevation, river proximity, mapped flood zone, flat slope. |
| Storm-surge exposure | Intensity × proximity to the core × right-side factor × `exp(−coast_km/8)` × elevation factor |

If a **live** gridded rainfall forecast is configured (Open-Meteo), it is blended with the model estimate at a 30% weight. Simulated stations are never blended.

## Model B: infrastructure vulnerability (`ml/vulnerability_model.py`)

- **Algorithm:** RandomForest, 200 trees, depth ≤ 10. XGBoost is an optional backend: `VULN_MODEL_BACKEND=xgboost`, then `python -m ml.train --backend xgboost`.
- **Features:**
  - distance from track
  - predicted peak wind
  - rainfall
  - elevation
  - distance from coast
  - flood probability
  - surge exposure
  - asset age (missing values imputed, with a missing flag)
  - historical damage count
  - one-hot asset type
- **Target:** significant damage / service disruption (binary).
- **Training data: SYNTHETIC.** No labelled asset-level damage dataset was available. Labels come from a documented logistic fragility process per asset type, plus noise (`ml/synthetic_training.py`).
  - Reported metrics (ROC-AUC ≈ 0.96) only show that the model reproduces that assumed process.
  - They are **not** evidence of real-world skill.
- **Interface:** any class implementing `VulnerabilityModel` (`fit`, `predict_proba`, optional `predict_spread`) can replace it, for example a model trained on post-event damage assessments, or a graph model over infrastructure networks.

## Risk score (`ml/risk_scoring.py`)

```
Risk = 100 × ( wH·H + wV·V + wE·E·g + wC·C·g ) / (wH + wV + wE + wC)
```

| Component | Default weight | Definition |
|---|---|---|
| H, hazard exposure | 40% | `0.6·max(hazards) + 0.4·weighted mean`. Sub-weights: wind 0.45, rain 0.20, flood 0.20, surge 0.15. |
| V, infrastructure vulnerability | 30% | Model B probability |
| E, environmental exposure | 20% | `0.6·terrain susceptibility + 0.4·exp(−coast_km/15)` |
| C, criticality | 10% | Asset-type importance (hospital 1.0, substation 0.95, …) or a per-asset override |
| g, hazard gate | 0.25 | `min(1, H/0.25)`. A critical, low-lying asset far from the storm cannot become "high risk" from E and C alone. Set it to 0 to disable. |

Categories (configurable prototype assumptions): 0–25 Low · 26–50 Moderate · 51–75 High · 76–100 Very High.

The API returns the points each component contributes, and they sum to the score. This is what the UI's stacked bar shows.

## Confidence (heuristic)

```
confidence = 0.40·track + 0.25·model_agreement + 0.20·data_completeness + 0.15·lead_time
```

- **Track certainty:** `1 − exp(−(d + 30)/(u + 1))`. Here d is the distance to the track and u is the forecast-cone radius at closest approach. It's low when the asset is near a track whose position is still uncertain.
- **Model agreement:** `1 − 2.5·std(per-tree probabilities)`.
- **Data completeness:** −0.15 for each missing or imputed field (age, synthetic elevation, damage history).
- **Lead time:** `exp(−hours/120)`.

The label is High (≥ 0.75), Medium (≥ 0.5) or Low. The score band shown in the UI (± points) is `(1 − confidence)·20`. These are **indicators, not calibrated probabilities**.

## Explanations

1. **Score composition:** exact weighted contribution of each component.
2. **Plain-language factors**, ranked by strength. Examples: "18 km from predicted cyclone track", "Low elevation (2.1 m)", "Critical infrastructure category".
3. **Model B occlusion attribution:** each feature group is replaced with its training baseline, and the change in predicted probability is reported. It's model-agnostic and cheap, but approximate (not exact Shapley values).

## Upgrade path

| Prototype | Production upgrade |
|---|---|
| Parametric wind/rain | Calibrate against IMD best-track + AWS/ARG rainfall. Use ensemble NWP / HWRF wind fields. |
| Surge index | Couple to ADCIRC / IMD storm-surge guidance |
| Synthetic fragility labels | Post-event damage records (SDMA damage reports, utility outage logs) joined to hazard footprints |
| Synthetic DEM, simplified geometry | SRTM/Copernicus DEM, OSM/Bhuvan layers, Survey of India boundaries |
| Heuristic confidence | Ensemble track forecasts → Monte-Carlo risk distribution and calibrated intervals |
| Per-asset scoring | Network-aware cascading-failure model (power → water/hospitals) |
