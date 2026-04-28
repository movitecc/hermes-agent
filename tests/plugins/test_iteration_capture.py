from pathlib import Path

import pytest

from plugins.context_engine.lcm.config import LCMConfig
from plugins.context_engine.lcm.engine import LCMEngine


def _make_engine(tmp_path: Path) -> LCMEngine:
    config = LCMConfig(database_path=str(tmp_path / "lcm.db"))
    engine = LCMEngine(config=config, hermes_home=str(tmp_path))
    engine.on_session_start("sess-1", conversation_id="conv-1", platform="cli")
    return engine


def test_on_session_end_persists_iteration_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = _make_engine(tmp_path)

    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "please run the failing test"},
        {"role": "assistant", "content": "All done."},
        {"role": "tool", "content": "FAILED tests/test_alpha.py::test_beta\nTraceback (most recent call last):"},
        {"role": "tool", "content": "MEDIA:/tmp/artifact.png"},
    ]

    engine.on_session_end(
        "sess-1",
        messages,
        project_root=str(tmp_path),
        api_call_count=7,
        turn_exit_reason="shutdown",
        git_commit="abc12345",
    )

    record = engine._store.get_latest_iteration_record("sess-1")
    assert record is not None
    assert record.session_id == "sess-1"
    assert record.project_root == str(tmp_path)
    assert record.status == "failure"
    assert record.summary == "All done."
    assert record.git_commit == "abc12345"
    assert record.failed_tests == ["tests/test_alpha.py::test_beta"]
    assert record.artifact_refs == ["/tmp/artifact.png"]
    assert "engine:lcm" in record.signals
    assert "api_calls:7" in record.signals
    assert "status:failure" in record.signals
    assert "failed_tests:1" in record.signals
    assert "artifacts:1" in record.signals
    assert "exit:shutdown" in record.signals


@pytest.mark.parametrize("flag_name", ["_session_ignored", "_session_stateless"])
def test_on_session_end_skips_ignored_or_stateless_sessions(tmp_path, flag_name):
    engine = _make_engine(tmp_path)
    setattr(engine, flag_name, True)

    engine.on_session_end(
        "sess-1",
        [{"role": "assistant", "content": "Done"}],
        project_root=str(tmp_path),
        api_call_count=1,
        turn_exit_reason="shutdown",
    )

    assert engine._store.get_latest_iteration_record("sess-1") is None
