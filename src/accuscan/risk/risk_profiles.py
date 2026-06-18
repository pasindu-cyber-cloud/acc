"""Risk-profile helpers.

Profiles are loaded from config/risk_profiles.yaml into config.RiskProfile.
This module adds the *decisions* a profile drives: family eligibility and the
readiness gate used by the scanner/executor. Profiles tighten controls; they
never disable them.
"""

from __future__ import annotations

from ..config import RiskProfile
from ..constants import Status
from ..models import MarketScore, StabilityFeatures


def family_allowed(profile: RiskProfile, family: str) -> bool:
    """High-volatility families are only eligible if the profile permits them."""
    if profile.allow_high_vol_families:
        return True
    if not profile.preferred_families:
        return True
    return any(family.startswith(p) or p.startswith(family) for p in profile.preferred_families)


def passes_readiness_gate(
    profile: RiskProfile,
    score: MarketScore,
    stability: StabilityFeatures,
    min_persistence: int,
) -> tuple[bool, list[str]]:
    """Hard readiness gate combining status, persistence and profile floors.

    Returns (ok, failed_reasons). Used by the scanner to decide actionability
    and by the executor as one of several independent safeguards.
    """
    reasons: list[str] = []
    if score.status is not Status.READY:
        reasons.append(f"status_not_ready({score.status.value})")
    if score.ready_persistence < min_persistence:
        reasons.append(
            f"persistence_{score.ready_persistence}<{min_persistence}"
        )
    if score.mqs < profile.ready_threshold:
        reasons.append(f"mqs_{score.mqs:.1f}<{profile.ready_threshold}")
    if stability.stability_score < profile.stability_floor:
        reasons.append(
            f"stability_{stability.stability_score:.1f}<{profile.stability_floor}"
        )
    jump_safety = (1.0 - stability.jump_burst_prob) * 100.0
    if jump_safety < profile.jump_safety_floor:
        reasons.append(f"jump_safety_{jump_safety:.1f}<{profile.jump_safety_floor}")
    if score.veto_reasons:
        reasons.append("veto:" + ",".join(score.veto_reasons))
    return (len(reasons) == 0, reasons)
