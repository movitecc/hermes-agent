"""Hermes tool for triggering or scheduling Evolver reviews.

This tool is intentionally opt-in. Immediate reviews only run when explicitly
enabled or when the LCM config has Evolver enabled. Scheduled reviews are
created as cron jobs that re-enter this tool later.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from plugins.context_engine.lcm.config import LCMConfig
from plugins.context_engine.lcm.evolver_bridge import (
    review_iteration_bundle,
    schedule_evolver_review_job,
)
from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)


EvolverReviewSchema = {
    "name": "evolver_review",
    "description": (
        "Trigger a local Evolver review immediately or schedule a follow-up review job. "
        "Immediate runs are best-effort and non-fatal; scheduled jobs create a cron entry "
        "that will call this tool later. The tool is disabled by default unless explicitly enabled."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["run", "schedule"],
                "description": "Run Evolver now or create a follow-up cron job.",
                "default": "run",
            },
            "enabled": {
                "type": "boolean",
                "description": "Explicit opt-in for immediate Evolver runs.",
                "default": False,
            },
            "project_root": {
                "type": "string",
                "description": "Project root used for review context and scheduling.",
            },
            "session_id": {
                "type": "string",
                "description": "Optional session id attached to the review bundle.",
            },
            "evidence_path": {
                "type": "string",
                "description": "Path to the run evidence directory or bundle.",
            },
            "schedule": {
                "type": "string",
                "description": "Cron/interval schedule for scheduled reviews (for example: '15m' or 'every 24h').",
            },
            "job_name": {
                "type": "string",
                "description": "Optional human-friendly job name for scheduled reviews.",
            },
            "deliver": {
                "type": "string",
                "description": "Where scheduled job output should be delivered (default: local).",
            },
            "repeat": {
                "type": "integer",
                "description": "Optional repeat count for the cron job (1 = one-shot).",
            },
        },
        "required": ["action"],
    },
}


def _load_settings() -> LCMConfig:
    return LCMConfig.from_env()


def _resolve_review_target(
    project_root: Optional[str],
    evidence_path: Optional[str],
    session_id: Optional[str],
) -> str:
    target = evidence_path or project_root or ""
    if target:
        return target
    if session_id:
        return session_id
    return ""


def evolver_review(
    action: str,
    enabled: bool = False,
    project_root: Optional[str] = None,
    session_id: Optional[str] = None,
    evidence_path: Optional[str] = None,
    schedule: Optional[str] = None,
    job_name: Optional[str] = None,
    deliver: Optional[str] = None,
    repeat: Optional[int] = None,
    **_: Any,
) -> str:
    """Immediate or scheduled Evolver review."""
    normalized_action = (action or "").strip().lower()
    settings = _load_settings()

    if normalized_action == "run":
        if not (enabled or settings.evolver_enabled):
            return tool_result(success=True, skipped=True, reason="Evolver disabled by config or call")

        target = _resolve_review_target(project_root, evidence_path, session_id)
        if not target:
            return tool_error("project_root or evidence_path is required for immediate review", success=False)

        ok = review_iteration_bundle(
            target,
            enabled=True,
            configured_path=settings.evolver_path,
            args=settings.evolver_args,
            timeout_ms=settings.evolver_timeout_ms,
        )
        return tool_result(
            success=True,
            reviewed=bool(ok),
            enabled=True,
            target=target,
            session_id=session_id,
        )

    if normalized_action == "schedule":
        if not project_root:
            return tool_error("project_root is required for scheduled review jobs", success=False)
        schedule_text = (schedule or "").strip()
        if not schedule_text:
            return tool_error("schedule is required for scheduled review jobs", success=False)

        result = schedule_evolver_review_job(
            project_root=project_root,
            schedule=schedule_text,
            evidence_path=evidence_path,
            session_id=session_id,
            job_name=job_name,
            deliver=(deliver or settings.evolver_schedule_deliver or "local"),
            repeat=repeat if repeat is not None else 1,
        )
        return json.dumps(result, ensure_ascii=False)

    return tool_error(f"Unknown action: {action!r}. Use 'run' or 'schedule'.", success=False)


registry.register(
    name="evolver_review",
    toolset="cronjob",
    schema=EvolverReviewSchema,
    handler=evolver_review,
    check_fn=None,
    emoji="🧬",
    description="Run or schedule a local Evolver review for iteration evidence",
)
