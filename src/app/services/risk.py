"""
KrishiKavach Risk Assessment Service.

Calculates risk levels, crop vulnerability tiers, and PMFBY insurance advisory categories
based on inundated surface area and village flood percentages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class RiskEvaluation:
    risk_level: str  # "Low", "Moderate", "Severe", "Catastrophic"
    risk_score: float  # 0.0 to 100.0
    crop_loss_estimate_pct: float
    pmfby_claim_recommended: bool
    priority: str  # "P1 - Critical", "P2 - High", "P3 - Medium", "P4 - Low"
    details: Dict[str, Any]


def calculate_flood_risk(flooded_hectares: float, flood_percentage: float) -> RiskEvaluation:
    """
    Computes comprehensive flood risk assessment.

    :param flooded_hectares: Inundated area in hectares.
    :param flood_percentage: Percentage of village grid flooded (0.0 to 100.0).
    :return: RiskEvaluation object.
    """
    # Base risk score calculation
    score = min(100.0, (flood_percentage * 0.7) + (min(flooded_hectares, 500.0) / 500.0 * 30.0))

    if flood_percentage >= 50.0 or flooded_hectares >= 200.0:
        risk_level = "Catastrophic"
        crop_loss = min(100.0, flood_percentage * 1.2)
        pmfby_claim = True
        priority = "P1 - Critical"
    elif flood_percentage >= 20.0 or flooded_hectares >= 80.0:
        risk_level = "Severe"
        crop_loss = min(85.0, flood_percentage * 1.1)
        pmfby_claim = True
        priority = "P2 - High"
    elif flood_percentage >= 5.0 or flooded_hectares >= 20.0:
        risk_level = "Moderate"
        crop_loss = min(45.0, flood_percentage * 1.0)
        pmfby_claim = True
        priority = "P3 - Medium"
    else:
        risk_level = "Low"
        crop_loss = flood_percentage * 0.8
        pmfby_claim = False
        priority = "P4 - Low"

    details = {
        "score": round(score, 1),
        "flooded_hectares": round(flooded_hectares, 2),
        "flood_percentage": round(flood_percentage, 2),
        "estimated_damage_tier": f"{risk_level} Inundation Impact",
        "action_timeline_hours": 72 if pmfby_claim else 168,
    }

    return RiskEvaluation(
        risk_level=risk_level,
        risk_score=round(score, 1),
        crop_loss_estimate_pct=round(crop_loss, 1),
        pmfby_claim_recommended=pmfby_claim,
        priority=priority,
        details=details,
    )
