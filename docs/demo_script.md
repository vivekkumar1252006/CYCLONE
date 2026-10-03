# 3-minute demo script

Before you present: start the backend and frontend (see README), open http://localhost:5173, and keep **Alerts** and **Settings** in mind as optional extras.

| Time | Step | What to do / say |
|---|---|---|
| 0:00 | 1. Open dashboard | Point at the yellow **DEMO / SIMULATED DATA** banner: "Fictional scenario, every number is a model estimate." |
| 0:10 | 2. Select a cyclone | Pick **DEMO Cyclone ALPHA** and click **Load demo scenario**. This generates the track, weather, 320 assets and runs both models in under 1 s. |
| 0:25 | 3. Predicted track | Solid black line = observed track. Dashed blue line = forecast. Dashed circles = growing track uncertainty. Red pin = estimated landfall near Puri in about 30 h. |
| 0:45 | 4. Affected region | Wind-risk zone (on by default). The KPI cards show max wind 180 km/h, affected districts, and an estimated population exposure. |
| 1:00 | 5. Vulnerability map | Layer control (top-right): enable **Vulnerability heatmap**, and optionally **Flood-risk zone** / **Storm-surge exposure**. The legend updates. |
| 1:20 | 6. Click a high-risk asset | Click the top item in **Priority infrastructure**, e.g. *Power Substation – Puri #01*, or any red marker. The map flies to it. |
| 1:35 | 7. Score + explanation | Score ring (≈80/100, Very High, ± band). Predicted hazards. "How the score is built" (points per component, weights). Main contributing factors (distance from track, wind, low elevation, flood exposure, critical category). Model B attribution under the expandable section. |
| 2:05 | 8. Priority list | Back to **Priority list**: ranked by risk then confidence, filterable by district and type. Show the *Hazard contribution* and *District* charts below. |
| 2:25 | 9. Recommendations | In the asset panel: preparedness actions with priority and reason. Use **Copy checklist** / **Print**. Note the guidance disclaimer. |
| 2:40 | 10. Uncertainty | Confidence badge and its four components (track certainty, model agreement, data completeness, lead time). Assets close to an uncertain forecast track get *lower* confidence. Alerts with low confidence become advisories. |
| 2:55 | Close | "Weights and thresholds are configurable assumptions (Settings). Real data plugs in via CSV/GeoJSON upload and provider interfaces." |

## Optional extras

- **Data → Upload:** use `data/samples/sample_infrastructure.csv`. Seven rows are accepted and three rejected, each with a clear reason. The scores update immediately.
- **Settings:** move the hazard weight to 100% → **Save and re-score**. The priority list changes.
- **Scenario BRAVO / CHARLIE:** different landfalls (Dhamra / Gopalpur) and intensities.
