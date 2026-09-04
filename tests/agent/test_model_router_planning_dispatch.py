from agent.model_router.planning_delegate import (
    CompressedContextSpec,
    PlanningDelegateConfig,
    build_planning_delegate_plan,
    dispatch_planning_delegate,
)
from agent.model_router.types import ModelProfile, RoutingRequest, TURN_PLANNING, TIER_ECONOMICAL


def test_dispatch_planning_delegate_uses_existing_background_rail():
    calls = []
    plan = type("Plan", (), {"path": "delegate", "delegate_model_id": "frontier", "compressed_context": CompressedContextSpec()})()
    result = dispatch_planning_delegate(
        lambda **kwargs: calls.append(kwargs) or {"status": "dispatched"},
        plan=plan,
        parent_agent="parent",
        snapshot=[{"role": "user", "content": "plan"}],
    )
    assert result["status"] == "dispatched"
    assert calls[0]["background"] is True
    assert calls[0]["parent_agent"] == "parent"
