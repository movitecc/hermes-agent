"""Iteration record schema for local agent evolution and review.

This module defines the normalized evidence payload used to record a run,
its signals, and the distilled lesson that can be reused later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

_VALID_STATUSES = {"success", "failure", "partial"}


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_str_list(name: str, value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a list of strings")
    result: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{name}[{idx}] must be a string")
        item = item.strip()
        if not item:
            raise ValueError(f"{name}[{idx}] must not be empty")
        result.append(item)
    return result


@dataclass(slots=True)
class IterationRecord:
    """Normalized record for one agent run or review cycle."""

    session_id: str
    project_root: str
    status: str
    signals: list[str] = field(default_factory=list)
    summary: str = ""
    git_commit: str | None = None
    failed_tests: list[str] = field(default_factory=list)
    lesson: str | None = None
    next_action: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso_z)

    def __post_init__(self) -> None:
        self.session_id = self.session_id.strip() if isinstance(self.session_id, str) else self.session_id
        self.project_root = self.project_root.strip() if isinstance(self.project_root, str) else self.project_root
        self.status = self.status.strip().lower() if isinstance(self.status, str) else self.status
        self.summary = self.summary.strip() if isinstance(self.summary, str) else self.summary
        self.git_commit = self.git_commit.strip() if isinstance(self.git_commit, str) else self.git_commit
        self.lesson = self.lesson.strip() if isinstance(self.lesson, str) else self.lesson
        self.next_action = self.next_action.strip() if isinstance(self.next_action, str) else self.next_action
        self.created_at = self.created_at.strip() if isinstance(self.created_at, str) else self.created_at

        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("session_id must be a non-empty string")
        if not isinstance(self.project_root, str) or not self.project_root:
            raise ValueError("project_root must be a non-empty string")
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}")
        if not isinstance(self.summary, str) or not self.summary:
            raise ValueError("summary must be a non-empty string")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ValueError("created_at must be a non-empty string")

        self.signals = _coerce_str_list("signals", self.signals)
        self.failed_tests = _coerce_str_list("failed_tests", self.failed_tests)
        self.artifact_refs = _coerce_str_list("artifact_refs", self.artifact_refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_root": self.project_root,
            "status": self.status,
            "signals": list(self.signals),
            "summary": self.summary,
            "git_commit": self.git_commit,
            "failed_tests": list(self.failed_tests),
            "lesson": self.lesson,
            "next_action": self.next_action,
            "artifact_refs": list(self.artifact_refs),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "IterationRecord":
        if not isinstance(data, Mapping):
            raise TypeError("data must be a mapping")
        return cls(
            session_id=data.get("session_id", ""),
            project_root=data.get("project_root", ""),
            status=data.get("status", ""),
            signals=data.get("signals", []),
            summary=data.get("summary", ""),
            git_commit=data.get("git_commit"),
            failed_tests=data.get("failed_tests", []),
            lesson=data.get("lesson"),
            next_action=data.get("next_action"),
            artifact_refs=data.get("artifact_refs", []),
            created_at=data.get("created_at", _now_iso_z()),
        )


__all__ = ["IterationRecord"]
