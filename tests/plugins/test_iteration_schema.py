import pytest

from plugins.context_engine.lcm.iteration_schema import IterationRecord


def test_iteration_record_round_trip_preserves_fields():
    record = IterationRecord(
        session_id="sess-123",
        project_root="/tmp/project",
        status="failure",
        signals=["pytest failure", "traceback"],
        summary="Test suite failed during auth flow",
        git_commit="abc123",
        failed_tests=["tests/test_auth.py::test_login"],
        lesson="Add missing auth fixture before running login tests.",
        next_action="Write regression test for fixture setup.",
        artifact_refs=["memory/run-42.jsonl"],
        created_at="2026-04-22T09:28:42Z",
    )

    payload = record.to_dict()
    restored = IterationRecord.from_dict(payload)

    assert restored.to_dict() == payload


def test_iteration_record_normalizes_whitespace_and_lists():
    record = IterationRecord(
        session_id="  sess-123  ",
        project_root="  /tmp/project  ",
        status="  SUCCESS  ",
        signals=["  signal one  ", "signal two"],
        summary="  done  ",
        failed_tests=["  tests/test_a.py  "],
        artifact_refs=("  ref-1  ",),
    )

    assert record.session_id == "sess-123"
    assert record.project_root == "/tmp/project"
    assert record.status == "success"
    assert record.summary == "done"
    assert record.signals == ["signal one", "signal two"]
    assert record.failed_tests == ["tests/test_a.py"]
    assert record.artifact_refs == ["ref-1"]


def test_iteration_record_requires_core_fields():
    with pytest.raises(ValueError, match="session_id"):
        IterationRecord(session_id="", project_root="/tmp/project", status="success", summary="ok")

    with pytest.raises(ValueError, match="project_root"):
        IterationRecord(session_id="sess-123", project_root="", status="success", summary="ok")

    with pytest.raises(ValueError, match="status"):
        IterationRecord(session_id="sess-123", project_root="/tmp/project", status="unknown", summary="ok")

    with pytest.raises(ValueError, match="summary"):
        IterationRecord(session_id="sess-123", project_root="/tmp/project", status="success", summary="")


def test_iteration_record_rejects_non_string_items():
    with pytest.raises(TypeError, match=r"signals\[0\]"):
        IterationRecord(
            session_id="sess-123",
            project_root="/tmp/project",
            status="success",
            signals=[123],
            summary="ok",
        )

    with pytest.raises(ValueError, match=r"artifact_refs\[0\]"):
        IterationRecord(
            session_id="sess-123",
            project_root="/tmp/project",
            status="success",
            signals=["signal"],
            summary="ok",
            artifact_refs=["   "],
        )
