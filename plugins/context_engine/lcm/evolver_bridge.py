"""Best-effort bridge to the local Evolver CLI.

This is intentionally lightweight: Hermes can opt in to a post-run review
step when Evolver is installed, but the core agent must continue normally when
it is absent or the review invocation fails.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

from cron.jobs import create_job, list_jobs

logger = logging.getLogger(__name__)


def resolve_evolver_binary(configured_path: str | None = None) -> Path | None:
    """Resolve the Evolver executable path.

    Resolution order:
      1. explicit configured path, if provided
      2. `evolver` on PATH
    """
    if configured_path:
        return Path(configured_path).expanduser()

    resolved = shutil.which("evolver")
    if not resolved:
        return None
    return Path(resolved)


def _normalize_args(args: Sequence[str] | None) -> list[str]:
    if args is None:
        return ["review"]
    return [str(arg).strip() for arg in args if str(arg).strip()]


def review_iteration_bundle(
    evidence_path: str | Path | None,
    *,
    enabled: bool = False,
    configured_path: str | None = None,
    args: Sequence[str] | None = None,
    timeout_ms: int = 60_000,
) -> bool:
    """Run Evolver against a post-run evidence bundle.

    Returns True on successful execution and False when skipped or when the
    invocation fails for any reason. Failures are logged but never raised.
    """
    if not enabled:
        logger.debug("Evolver bridge disabled; skipping post-run review")
        return False

    if not evidence_path:
        logger.debug("Evolver bridge enabled but no evidence path was provided")
        return False

    binary = resolve_evolver_binary(configured_path)
    if binary is None:
        logger.info("Evolver bridge enabled but no local evolver binary was found; skipping review")
        return False

    command = [str(binary), *_normalize_args(args), str(Path(evidence_path).expanduser())]
    timeout_seconds = max(1, int(timeout_ms or 0) / 1000)

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        logger.warning("Evolver invocation failed: %s", exc)
        return False
    except subprocess.TimeoutExpired as exc:
        logger.warning("Evolver invocation timed out after %ss: %s", timeout_seconds, exc)
        return False
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or f"exit code {exc.returncode}"
        logger.warning("Evolver review failed: %s", detail)
        return False
    except OSError as exc:
        logger.warning("Evolver invocation failed: %s", exc)
        return False

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        logger.debug("Evolver stdout: %s", stdout)
    if stderr:
        logger.debug("Evolver stderr: %s", stderr)
    logger.info("Evolver review completed for %s", evidence_path)
    return True


def build_scheduled_review_prompt(
    *,
    project_root: str,
    session_id: str | None = None,
    evidence_path: str | Path | None = None,
) -> str:
    evidence_text = str(Path(evidence_path).expanduser()) if evidence_path else project_root
    session_text = session_id or "unknown"
    return (
        "You are running a Hermes post-run review.\n"
        f"Session ID: {session_text}\n"
        f"Project root: {project_root}\n"
        f"Evidence path: {evidence_text}\n\n"
        "Task:\n"
        "1. Use the `evolver_review` tool with action=\"run\" to review the evidence.\n"
        "2. Summarize the highest-value lesson and next action.\n"
        "3. Do not create or modify cron jobs.\n"
        "4. Do not recursively schedule more reviews.\n"
    )


def schedule_evolver_review_job(
    *,
    project_root: str,
    schedule: str,
    evidence_path: str | Path | None = None,
    session_id: str | None = None,
    job_name: str | None = None,
    deliver: str = "local",
    repeat: int | None = 1,
) -> dict[str, object]:
    """Create a cron job that will invoke the evolver_review tool later.

    Duplicate jobs with the same name are skipped to avoid recursive spam.
    """
    if not project_root:
        return {"success": False, "skipped": True, "error": "project_root is required"}

    resolved_name = (job_name or f"Evolver review {session_id or Path(project_root).name}").strip()
    existing = [job for job in list_jobs(include_disabled=True) if job.get("name") == resolved_name]
    if existing:
        return {
            "success": True,
            "skipped": True,
            "reason": "duplicate job name",
            "job": existing[0],
        }

    prompt = build_scheduled_review_prompt(
        project_root=project_root,
        session_id=session_id,
        evidence_path=evidence_path or project_root,
    )
    job = create_job(
        prompt=prompt,
        schedule=schedule,
        name=resolved_name,
        deliver=deliver,
        repeat=repeat,
    )
    return {"success": True, "job": job}


__all__ = ["resolve_evolver_binary", "review_iteration_bundle", "build_scheduled_review_prompt", "schedule_evolver_review_job"]
