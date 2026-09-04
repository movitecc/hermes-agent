"""Safe planning-delegate decision data for the model-router boundary.

This module deliberately does not spawn workers or call providers. It describes
when an existing Hermes delegation rail may be used by a higher-level caller.
Until that caller supplies a verified dispatch function, disabled/unavailable
configuration falls back to direct frontier execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .types import ModelProfile, RoutingRequest, TIER_ECONOMICAL, TURN_PLANNING

PLANNING_DELEGATE = "planning_delegate"
PLANNING_DELEGATE_DISABLED = "planning_delegate_disabled"
PLANNING_DELEGATE_UNAVAILABLE = "planning_delegate_unavailable"
PLANNING_DIRECT_FRONTIER = "planning_direct_frontier"


@dataclass(frozen=True)
class CompressedContextSpec:
    max_messages: int = 12
    max_tokens: int = 16_384
    exclude_execution_history: bool = True


@dataclass(frozen=True)
class PlanningDelegateConfig:
    enabled: bool = False
    available: bool = False
    compressed_context: CompressedContextSpec = field(default_factory=CompressedContextSpec)


@dataclass(frozen=True)
class PlanningDelegatePlan:
    path: str
    primary_model_id: str
    delegate_model_id: Optional[str]
    reason_code: str
    compressed_context: CompressedContextSpec = field(default_factory=CompressedContextSpec)
    fallback_reason: Optional[str] = None


def dispatch_planning_delegate(
    dispatch_fn: Callable[..., Any],
    *,
    plan: PlanningDelegatePlan,
    parent_agent: Any,
    snapshot: list[dict[str, Any]],
) -> Any:
    """Dispatch a prepared plan through Hermes' existing async rail."""
    if plan.path != "delegate":
        return {"status": "direct", "reason": plan.fallback_reason or plan.reason_code}
    spec = plan.compressed_context
    bounded = [
        item for item in snapshot[-spec.max_messages :]
        if not spec.exclude_execution_history or item.get("role") not in {"tool", "assistant"}
    ]
    text = "\n".join(
        f"{item.get('role', 'unknown')}: {str(item.get('content', ''))[:4000]}"
        for item in bounded
    )[: max(1024, spec.max_tokens * 4)]
    return dispatch_fn(
        goal="Produce a concise execution plan for the current planning turn.",
        context=text,
        background=True,
        parent_agent=parent_agent,
        model=plan.delegate_model_id,
    )


def build_planning_delegate_plan(
    request: RoutingRequest,
    *,
    pinned_model: ModelProfile,
    frontier_model: ModelProfile,
    config: Optional[PlanningDelegateConfig] = None,
) -> Optional[PlanningDelegatePlan]:
    """Describe a cache-preserving planning delegation opportunity.

    A plan is produced only for an explicit planning turn where a warm
    economical pin would otherwise switch to a different frontier model. The
    returned delegate plan never mutates the request, pin, or agent cache.
    """
    config = config or PlanningDelegateConfig()
    if request.turn_type != TURN_PLANNING:
        return None
    if pinned_model.tier != TIER_ECONOMICAL:
        return None
    if pinned_model.id == frontier_model.id:
        return None
    if not config.enabled:
        return PlanningDelegatePlan(
            path="direct",
            primary_model_id=pinned_model.id,
            delegate_model_id=frontier_model.id,
            reason_code=PLANNING_DELEGATE_DISABLED,
            compressed_context=config.compressed_context,
            fallback_reason=PLANNING_DELEGATE_DISABLED,
        )
    if not config.available:
        return PlanningDelegatePlan(
            path="direct",
            primary_model_id=pinned_model.id,
            delegate_model_id=frontier_model.id,
            reason_code=PLANNING_DELEGATE_UNAVAILABLE,
            compressed_context=config.compressed_context,
            fallback_reason=PLANNING_DELEGATE_UNAVAILABLE,
        )
    return PlanningDelegatePlan(
        path="delegate",
        primary_model_id=pinned_model.id,
        delegate_model_id=frontier_model.id,
        reason_code=PLANNING_DELEGATE,
        compressed_context=config.compressed_context,
    )
