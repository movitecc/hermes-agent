from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import subprocess

from plugins.context_engine.lcm.evolver_bridge import resolve_evolver_binary, review_iteration_bundle


def test_disabled_by_default_skips_review(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()

    result = review_iteration_bundle(evidence, enabled=False)

    assert result is False


def test_resolve_evolver_binary_prefers_configured_path(tmp_path, monkeypatch):
    configured = tmp_path / "bin" / "evolver"
    configured.parent.mkdir()
    configured.write_text("#!/bin/sh\n")

    monkeypatch.setattr("plugins.context_engine.lcm.evolver_bridge.shutil.which", lambda name: None)

    resolved = resolve_evolver_binary(str(configured))

    assert resolved == configured


def test_resolve_evolver_binary_uses_path_when_configured_missing(monkeypatch):
    monkeypatch.setattr("plugins.context_engine.lcm.evolver_bridge.shutil.which", lambda name: "/usr/local/bin/evolver")

    resolved = resolve_evolver_binary(None)

    assert resolved == Path("/usr/local/bin/evolver")


def test_review_iteration_bundle_invokes_subprocess(tmp_path, monkeypatch):
    evidence = tmp_path / "bundle"
    evidence.mkdir()

    monkeypatch.setattr(
        "plugins.context_engine.lcm.evolver_bridge.resolve_evolver_binary",
        lambda configured_path=None: Path("/usr/bin/evolver"),
    )
    run_mock = MagicMock(return_value=SimpleNamespace(stdout="ok", stderr=""))
    monkeypatch.setattr("plugins.context_engine.lcm.evolver_bridge.subprocess.run", run_mock)

    result = review_iteration_bundle(
        evidence,
        enabled=True,
        configured_path=None,
        args=["review", "--dry-run"],
        timeout_ms=5000,
    )

    assert result is True
    run_mock.assert_called_once()
    command = run_mock.call_args.args[0]
    assert command[:3] == ["/usr/bin/evolver", "review", "--dry-run"]
    assert command[-1] == str(evidence)


def test_review_iteration_bundle_failure_is_non_fatal(tmp_path, monkeypatch):
    evidence = tmp_path / "bundle"
    evidence.mkdir()

    monkeypatch.setattr(
        "plugins.context_engine.lcm.evolver_bridge.resolve_evolver_binary",
        lambda configured_path=None: Path("/usr/bin/evolver"),
    )

    def _boom(*args, **kwargs):
        raise subprocess.CalledProcessError(2, args[0], output="", stderr="bad news")

    monkeypatch.setattr("plugins.context_engine.lcm.evolver_bridge.subprocess.run", _boom)

    result = review_iteration_bundle(evidence, enabled=True)

    assert result is False
