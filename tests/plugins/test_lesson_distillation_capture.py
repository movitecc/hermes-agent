from pathlib import Path

from plugins.context_engine.lcm.config import LCMConfig
from plugins.context_engine.lcm.engine import LCMEngine


def _make_engine(tmp_path: Path) -> LCMEngine:
    config = LCMConfig(database_path=str(tmp_path / "lcm.db"))
    engine = LCMEngine(config=config, hermes_home=str(tmp_path))
    engine.on_session_start("sess-1", conversation_id="conv-1", platform="cli")
    return engine


def test_repeated_failure_is_persisted_as_a_lesson(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = _make_engine(tmp_path)

    first_messages = [
        {"role": "assistant", "content": "Running tests"},
        {"role": "tool", "content": "FAILED tests/test_auth.py::test_login\nTraceback (most recent call last):"},
    ]
    second_messages = [
        {"role": "assistant", "content": "Running tests again"},
        {"role": "tool", "content": "FAILED tests/test_auth.py::test_login\nTraceback (most recent call last):"},
    ]

    engine.on_session_end("sess-1", first_messages, project_root=str(tmp_path), status="failure")
    engine.on_session_start("sess-2", conversation_id="conv-1", platform="cli")
    engine.on_session_end("sess-2", second_messages, project_root=str(tmp_path), status="failure")

    record = engine._store.get_latest_iteration_record("sess-2")
    assert record is not None
    assert record.lesson is not None
    assert "tests/test_auth.py::test_login" in record.lesson
    assert "Action:" in record.lesson
    assert record.next_action is not None
    assert "regression test" in record.next_action.lower()


def test_distillation_stays_empty_for_unique_failures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = _make_engine(tmp_path)

    engine.on_session_end(
        "sess-1",
        [{"role": "tool", "content": "FAILED tests/test_auth.py::test_login\nTraceback"}],
        project_root=str(tmp_path),
        status="failure",
    )
    engine.on_session_start("sess-2", conversation_id="conv-1", platform="cli")
    engine.on_session_end(
        "sess-2",
        [{"role": "tool", "content": "FAILED tests/test_payments.py::test_charge\nTraceback"}],
        project_root=str(tmp_path),
        status="failure",
    )

    record = engine._store.get_latest_iteration_record("sess-2")
    assert record is not None
    assert record.lesson is None
    assert record.next_action is None
