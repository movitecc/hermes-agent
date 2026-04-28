from pathlib import Path
from unittest.mock import MagicMock

from plugins.context_engine.lcm.config import LCMConfig
from plugins.context_engine.lcm.engine import LCMEngine


def _make_engine(tmp_path: Path) -> LCMEngine:
    config = LCMConfig(database_path=str(tmp_path / "lcm.db"), evolver_enabled=True)
    engine = LCMEngine(config=config, hermes_home=str(tmp_path))
    engine.on_session_start("sess-1", conversation_id="conv-1", platform="cli")
    return engine


def test_engine_triggers_evolver_only_on_shutdown(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path)
    bridge = MagicMock(return_value=True)
    monkeypatch.setattr("plugins.context_engine.lcm.engine.review_iteration_bundle", bridge)

    engine.on_session_end(
        "sess-1",
        [{"role": "assistant", "content": "done"}],
        project_root=str(tmp_path),
        turn_exit_reason="shutdown",
        status="success",
        evidence_dir=str(tmp_path / "evidence"),
    )

    bridge.assert_called_once()
    args, kwargs = bridge.call_args
    assert args[0] == str(tmp_path / "evidence")
    assert kwargs["enabled"] is True
    assert kwargs["configured_path"] == ""
    assert kwargs["timeout_ms"] == engine._config.evolver_timeout_ms


def test_engine_does_not_trigger_evolver_on_compression(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path)
    bridge = MagicMock(return_value=True)
    monkeypatch.setattr("plugins.context_engine.lcm.engine.review_iteration_bundle", bridge)

    engine.on_session_end(
        "sess-1",
        [{"role": "assistant", "content": "done"}],
        project_root=str(tmp_path),
        turn_exit_reason="compression",
        status="success",
    )

    bridge.assert_not_called()
