import json
from unittest.mock import MagicMock

from tools.evolver_review_tool import evolver_review


def test_evolver_review_run_disabled_by_default(tmp_path):
    result = json.loads(
        evolver_review(
            action="run",
            project_root=str(tmp_path),
            evidence_path=str(tmp_path / "bundle"),
            enabled=False,
        )
    )

    assert result["success"] is True
    assert result["skipped"] is True


def test_evolver_review_run_invokes_bridge(monkeypatch, tmp_path):
    bridge = MagicMock(return_value=True)
    monkeypatch.setattr("tools.evolver_review_tool.review_iteration_bundle", bridge)
    monkeypatch.setattr("tools.evolver_review_tool.LCMConfig.from_env", lambda: __import__("types").SimpleNamespace(
        evolver_enabled=True,
        evolver_path="/usr/bin/evolver",
        evolver_args=["review"],
        evolver_timeout_ms=5000,
        evolver_schedule_deliver="local",
    ))

    result = json.loads(
        evolver_review(
            action="run",
            project_root=str(tmp_path),
            evidence_path=str(tmp_path / "bundle"),
            enabled=True,
        )
    )

    assert result["success"] is True
    assert result["reviewed"] is True
    bridge.assert_called_once()
    assert bridge.call_args.args[0] == str(tmp_path / "bundle")
    assert bridge.call_args.kwargs["enabled"] is True


def test_evolver_review_schedule_returns_job_json(monkeypatch, tmp_path):
    schedule_job = MagicMock(return_value={"success": True, "job": {"id": "job-1"}})
    monkeypatch.setattr("tools.evolver_review_tool.schedule_evolver_review_job", schedule_job)

    result = json.loads(
        evolver_review(
            action="schedule",
            project_root=str(tmp_path),
            evidence_path=str(tmp_path / "bundle"),
            schedule="15m",
            session_id="sess-1",
            deliver="local",
        )
    )

    assert result["success"] is True
    assert result["job"]["id"] == "job-1"
    schedule_job.assert_called_once()
