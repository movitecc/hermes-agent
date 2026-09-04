"""Bounded, opt-in feedback adjustment for router candidate scores."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .scoring import ScoredCandidate


@dataclass(frozen=True)
class FeedbackConfig:
    enabled: bool = False
    min_samples: int = 5
    max_adjustment: float = 0.10


def adjust_scores(
    candidates: tuple[ScoredCandidate, ...],
    stats: dict,
    config: FeedbackConfig | None = None,
) -> tuple[ScoredCandidate, ...]:
    config = config or FeedbackConfig()
    if not config.enabled:
        return candidates
    minimum = max(1, int(config.min_samples))
    cap = min(0.5, max(0.0, float(config.max_adjustment)))
    by_model = stats.get("by_model", {}) if isinstance(stats, dict) else {}
    adjusted = []
    for candidate in candidates:
        if candidate.rejected_reason is not None:
            adjusted.append(candidate)
            continue
        row = by_model.get(candidate.model_id, {})
        total = int(row.get("total", 0) or 0)
        if total < minimum:
            adjusted.append(candidate)
            continue
        try:
            rate = min(1.0, max(0.0, float(row.get("success_rate", 0.0))))
        except (TypeError, ValueError):
            adjusted.append(candidate)
            continue
        adjustment = min(cap, abs(rate - 0.5) * 2.0 * cap)
        adjustment = adjustment if rate >= 0.5 else -adjustment
        adjusted.append(replace(candidate, composite_score=round(candidate.composite_score + adjustment, 12)))
    return tuple(sorted(adjusted, key=lambda item: (-item.composite_score, item.model_id)))
