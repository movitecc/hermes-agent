from agent.model_router.telemetry import RouterTelemetry
from agent.model_router.health import bind_agent_health
from types import SimpleNamespace


def test_router_feedback_records_usage_and_outcome_without_prompt_text(tmp_path):
    telemetry = RouterTelemetry(tmp_path / "router.db")
    telemetry.record_outcome(
        session_id="session-1",
        provider="provider-a",
        model_id="model-a",
        success=True,
        input_tokens=100,
        output_tokens=25,
        cost_usd=0.012,
        latency_ms=321.5,
    )
    telemetry.record_outcome(
        session_id="session-2",
        provider="provider-a",
        model_id="model-a",
        success=False,
        retryable=True,
        error_category="timeout",
        input_tokens=40,
        output_tokens=0,
        cost_usd=0.004,
        latency_ms=1000,
    )

    stats = telemetry.feedback_stats()

    assert stats["total"] == 2
    assert stats["successful"] == 1
    assert stats["retryable_failures"] == 1
    assert stats["by_model"]["model-a"]["input_tokens"] == 140
    assert stats["by_model"]["model-a"]["output_tokens"] == 25
    assert stats["by_model"]["model-a"]["cost_usd"] == 0.016
    assert stats["by_model"]["model-a"]["success_rate"] == 0.5


def test_router_feedback_clamps_invalid_values_and_never_stores_prompt(tmp_path):
    telemetry = RouterTelemetry(tmp_path / "router.db")
    telemetry.record_outcome(
        session_id="s",
        provider="p",
        model_id="m",
        success=True,
        input_tokens=-1,
        output_tokens="bad",
        cost_usd=-4,
        latency_ms=-2,
        error_category="private prompt text",
    )

    row = telemetry.feedback_stats()["by_model"]["m"]
    assert row["input_tokens"] == 0
    assert row["output_tokens"] == 0
    assert row["cost_usd"] == 0.0
    assert row["latency_ms"] == 0.0
    assert "private prompt" not in str(telemetry.feedback_stats())


def test_agent_health_callback_also_records_feedback_outcome(tmp_path):
    telemetry = RouterTelemetry(tmp_path / "router.db")
    agent = SimpleNamespace(
        provider="provider-a", model="model-a", gateway_session_key="session-a"
    )
    bind_agent_health(agent, None, telemetry)

    agent._router_health_callback(
        success=False,
        retryable=True,
        reason="timeout",
        latency_ms=250,
    )
    agent._router_health_callback(success=True, latency_ms=40)

    stats = telemetry.feedback_stats()
    assert stats["total"] == 2
    assert stats["successful"] == 1
    assert stats["retryable_failures"] == 1
