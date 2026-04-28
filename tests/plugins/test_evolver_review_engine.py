from pathlib import Path
from unittest.mock import MagicMock

from plugins.context_engine.lcm.config import LCMConfig
from plugins.context_engine.lcm.engine import LCMEngine


def _make_engine(tmp_path: Path, *, schedule_enabled: bool = True) -> LCMEngine:
    config = LCMConfig(database_path=str(tmp_path / "lcm.db"), evolver_enabled=False, evolver_schedule_enabled=schedule_enabled)
    engine = LCMEngine(config=config, hermes_home=str(tmp_path))
    engine.on_session_start("sess-1", conversation_id="conv-1", platform="cli")
    return engine


def test_failure_shutdown_queues_followup_review(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path)
    schedule_job = MagicMock(return_value={"success": True, "job": {"id": "followup"}})
    monkeypatch.setattr("plugins.context_engine.lcm.engine.schedule_evolver_review_job", schedule_job)
    monkeypatch.setattr("plugins.context_engine.lcm.engine.review_iteration_bundle", MagicMock(return_value=True))

    engine.on_session_end(
        "sess-1",
        [{"role": "tool", "content": "FAILED tests/test_auth.py::test_login"}],
        project_root=str(tmp_path),
        status="failure",
        turn_exit_reason="shutdown",
        evidence_dir=str(tmp_path / "evidence"),
    )

    schedule_job.assert_called_once()
    kwargs = schedule_job.call_args.kwargs
    assert kwargs["project_root"] == str(tmp_path)
    assert kwargs["schedule"] == engine._config.evolver_followup_delay
    assert kwargs["deliver"] == engine._config.evolver_schedule_deliver
    assert kwargs["session_id"] == "sess-1"


def test_success_shutdown_does_not_queue_followup_review(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path)
    schedule_job = MagicMock(return_value={"success": True, "job": {"id": "followup"}})
    monkeypatch.setattr("plugins.context_engine.lcm.engine.schedule_evolver_review_job", schedule_job)
    monkeypatch.setattr("plugins.context_engine.lcm.engine.review_iteration_bundle", MagicMock(return_value=True))

    engine.on_session_end(
        "sess-1",
        [{"role": "assistant", "content": "All good"}],
        project_root=str(tmp_path),
        status="success",
        turn_exit_reason="shutdown",
    )

    schedule_job.assert_not_called()
