from agent.model_router import ModelProfile, RoutingRequest
from agent.model_router.planning_delegate import (
    PlanningDelegateConfig,
    build_planning_delegate_plan,
)
from agent.model_router.types import SessionPin, TURN_MAIN_LOOP, TURN_PLANNING


def _models():
    return (
        ModelProfile(
            "econ", provider="p", tier="economical", quality=0.7,
            cost=0.1, context_window=32_000, reasoning=True,
        ),
        ModelProfile(
            "frontier", provider="p", tier="frontier", quality=1.0,
            cost=0.8, context_window=64_000, reasoning=True,
        ),
    )


def test_planning_delegate_plan_preserves_warm_economical_pin():
    plan = build_planning_delegate_plan(
        RoutingRequest("design a migration plan", session_id="s", turn_type=TURN_PLANNING),
        pinned_model=_models()[0],
        frontier_model=_models()[1],
        config=PlanningDelegateConfig(enabled=True, available=True),
    )

    assert plan.path == "delegate"
    assert plan.primary_model_id == "econ"
    assert plan.delegate_model_id == "frontier"
    assert plan.reason_code == "planning_delegate"
    assert plan.compressed_context.max_messages == 12
    assert plan.compressed_context.exclude_execution_history is True


def test_planning_delegate_disabled_falls_back_to_direct_frontier():
    plan = build_planning_delegate_plan(
        RoutingRequest("plan", turn_type=TURN_PLANNING),
        pinned_model=_models()[0],
        frontier_model=_models()[1],
        config=PlanningDelegateConfig(enabled=False),
    )

    assert plan.path == "direct"
    assert plan.reason_code == "planning_delegate_disabled"
    assert plan.delegate_model_id == "frontier"


def test_planning_delegate_requires_planning_turn_and_economical_pin():
    config = PlanningDelegateConfig(enabled=True)
    assert build_planning_delegate_plan(
        RoutingRequest("plan", turn_type=TURN_MAIN_LOOP),
        pinned_model=_models()[0],
        frontier_model=_models()[1],
        config=config,
    ) is None
    assert build_planning_delegate_plan(
        RoutingRequest("plan", turn_type=TURN_PLANNING),
        pinned_model=_models()[1],
        frontier_model=_models()[1],
        config=config,
    ) is None


def test_planning_delegate_unavailable_is_fail_closed():
    plan = build_planning_delegate_plan(
        RoutingRequest("plan", turn_type=TURN_PLANNING),
        pinned_model=_models()[0],
        frontier_model=_models()[1],
        config=PlanningDelegateConfig(enabled=True, available=False),
    )

    assert plan.path == "direct"
    assert plan.reason_code == "planning_delegate_unavailable"
