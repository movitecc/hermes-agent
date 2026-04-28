from pathlib import Path
from unittest.mock import MagicMock

from plugins.context_engine.lcm.evolver_bridge import build_scheduled_review_prompt, schedule_evolver_review_job


def test_build_scheduled_review_prompt_includes_guardrails(tmp_path):
    prompt = build_scheduled_review_prompt(
        project_root=str(tmp_path),
        session_id="sess-123",
        evidence_path=tmp_path / "bundle",
    )

    assert "Session ID: sess-123" in prompt
    assert f"Project root: {tmp_path}" in prompt
    assert f"Evidence path: {tmp_path / 'bundle'}" in prompt
    assert "do not recursively schedule more reviews" in prompt.lower()


def test_schedule_evolver_review_job_creates_cron_job(monkeypatch, tmp_path):
    created = {}

    def fake_list_jobs(include_disabled=False):
        return []

    def fake_create_job(**kwargs):
        created.update(kwargs)
        return {"id": "job-1", **kwargs}

    monkeypatch.setattr("plugins.context_engine.lcm.evolver_bridge.list_jobs", fake_list_jobs)
    monkeypatch.setattr("plugins.context_engine.lcm.evolver_bridge.create_job", fake_create_job)

    result = schedule_evolver_review_job(
        project_root=str(tmp_path),
        schedule="15m",
        evidence_path=tmp_path / "bundle",
        session_id="sess-123",
        deliver="local",
        repeat=1,
    )

    assert result["success"] is True
    assert result["job"]["id"] == "job-1"
    assert created["schedule"] == "15m"
    assert created["name"] == "Evolver review sess-123"
    assert created["deliver"] == "local"
    assert "Use the `evolver_review` tool" in created["prompt"]


def test_schedule_evolver_review_job_skips_duplicates(monkeypatch, tmp_path):
    existing = {"id": "job-dup", "name": "Evolver review sess-123"}

    monkeypatch.setattr("plugins.context_engine.lcm.evolver_bridge.list_jobs", lambda include_disabled=False: [existing])
    create_job = MagicMock()
    monkeypatch.setattr("plugins.context_engine.lcm.evolver_bridge.create_job", create_job)

    result = schedule_evolver_review_job(
        project_root=str(tmp_path),
        schedule="15m",
        session_id="sess-123",
    )

    assert result["success"] is True
    assert result["skipped"] is True
    create_job.assert_not_called()
