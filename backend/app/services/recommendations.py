"""Preparedness recommendations (rule-based guidance, NOT guaranteed outcomes).

Recommendations combine (1) asset-type specific preparedness checklists and
(2) hazard-specific actions triggered by the model estimates. Each item carries
a priority and the reason it was suggested so operators can judge relevance.
"""
from __future__ import annotations

DISCLAIMER = ("Preparedness guidance generated from model estimates. It does not imply that damage will occur; "
              "follow official advisories (e.g. IMD, OSDMA/SDMA, district administration) and local SOPs.")

TYPE_ACTIONS: dict[str, list[str]] = {
    "power_substation": ["Inspect critical equipment (transformers, switchgear, control room)",
                         "Prepare backup power / mobile DG sets for essential feeders",
                         "Review emergency access routes and keep restoration crews on standby",
                         "Protect vulnerable equipment from flooding (raise, seal, sandbag)"],
    "road": ["Identify alternate routes and publish diversion plans",
             "Inspect and clear drainage culverts and side drains",
             "Prepare barricades, signage and tree-clearing equipment",
             "Prioritise the segment for post-event inspection"],
    "bridge": ["Inspect bearings, piers and approaches before the event",
               "Monitor river levels and set closure thresholds",
               "Prepare barricades and alternate route signage",
               "Schedule post-event scour / structural inspection"],
    "hospital": ["Verify backup power and fuel for at least 72 hours",
                 "Check emergency medical supplies, oxygen and blood stocks",
                 "Confirm access routes for ambulances; pre-position at safer locations",
                 "Prepare emergency communication (satellite phone / HAM / VHF)"],
    "school": ["Assess use as temporary shelter; check structural condition",
               "Secure loose roofing, windows and outdoor objects",
               "Move records and equipment to upper floors",
               "Coordinate closure/opening decisions with district administration"],
    "mobile_tower": ["Verify backup batteries / DG fuel at the site",
                     "Inspect tower guying, antenna mounts and foundation",
                     "Pre-position cell-on-wheels and repair teams",
                     "Coordinate with telecom operators for intra-circle roaming"],
    "water_facility": ["Protect pumps and electrical panels from flooding",
                       "Arrange backup power for pumping and treatment",
                       "Stock disinfection chemicals and plan water-quality testing",
                       "Pre-arrange water tankers for supply disruption"],
    "emergency_shelter": ["Confirm structural readiness, doors/shutters and access",
                          "Stock drinking water, food, first-aid and lighting",
                          "Check backup power and sanitation facilities",
                          "Coordinate evacuation lists and shelter management teams"],
    "railway": ["Coordinate with railway control on train regulation/cancellation",
                "Inspect track drainage, embankments and signalling",
                "Pre-position track-maintenance and tree-clearing crews",
                "Prioritise post-event track and bridge inspection"],
}

HAZARD_ACTIONS = {
    "wind": "Secure or remove loose objects, hoardings and temporary structures; trim overhanging trees",
    "flood": "Move critical equipment and records above expected flood level; arrange dewatering pumps",
    "surge": "Review coastal evacuation plans with authorities; avoid stationing staff in surge-prone low ground",
    "rain": "Clear drains and check roof drainage ahead of heavy rainfall",
}


def generate(asset_type: str, impact: dict, category: str, confidence_label: str) -> list[dict]:
    urgent = category in ("Very High", "High")
    base_priority = "High" if category == "Very High" else "Medium" if category == "High" else "Low"
    recs: list[dict] = []
    for i, action in enumerate(TYPE_ACTIONS.get(asset_type, [])):
        recs.append({"action": action, "priority": base_priority if i < 2 or urgent else "Low",
                     "reason": f"Standard preparedness for this asset type (risk: {category})"})
    if impact["wind_impact"] >= 0.4:
        recs.append({"action": HAZARD_ACTIONS["wind"], "priority": "High" if impact["wind_impact"] >= 0.6 else "Medium",
                     "reason": f"Predicted peak wind ~{impact['peak_wind_kmh']:.0f} km/h"})
    if impact["flood_probability"] >= 0.4:
        recs.append({"action": HAZARD_ACTIONS["flood"], "priority": "High" if impact["flood_probability"] >= 0.6 else "Medium",
                     "reason": f"Estimated flooding probability {impact['flood_probability']:.0%}"})
    if impact["surge_exposure"] >= 0.25:
        recs.append({"action": HAZARD_ACTIONS["surge"], "priority": "High",
                     "reason": f"Storm-surge exposure index {impact['surge_exposure']:.2f}"})
    if impact["rainfall_mm"] >= 150:
        recs.append({"action": HAZARD_ACTIONS["rain"], "priority": "Medium",
                     "reason": f"Predicted rainfall ~{impact['rainfall_mm']:.0f} mm"})
    if confidence_label == "Low":
        recs.append({"action": "Track updated forecasts closely - estimate has low confidence and may change",
                     "priority": "Medium", "reason": "Low prediction confidence"})
    order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda r: order[r["priority"]])
    return recs
