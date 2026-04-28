"""Heuristics for distilling repeated iteration records into reusable lessons.

The distiller intentionally stays deterministic and lightweight:
- group similar failures by project root + failure signature
- only emit a lesson once the pattern repeats
- keep the lesson concise and action-oriented
- reference evidence without copying raw logs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .iteration_schema import IterationRecord


@dataclass(slots=True)
class DistilledLesson:
    signature: str
    lesson: str
    trigger: str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)
    recommended_next_action: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "signature": self.signature,
            "lesson": self.lesson,
            "trigger": self.trigger,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
            "recommended_next_action": self.recommended_next_action,
        }


def _primary_failure_target(record: IterationRecord) -> str:
    if record.failed_tests:
        return record.failed_tests[0]
    for signal in record.signals:
        if signal.startswith("exit:"):
            return signal.split(":", 1)[1]
    return record.summary[:80].strip() or record.status


def _normalize_signature(record: IterationRecord) -> str:
    if record.failed_tests:
        tests = ",".join(sorted(dict.fromkeys(record.failed_tests)))
        return f"{record.project_root}::tests::{tests}"
    signal_bits = [signal for signal in record.signals if signal.startswith(("error", "failed", "exit:", "status:"))]
    if signal_bits:
        return f"{record.project_root}::signals::{','.join(signal_bits)}"
    return f"{record.project_root}::summary::{record.summary[:48].strip().lower()}"


def _build_lesson_text(signature: str, records: list[IterationRecord]) -> tuple[str, str]:
    trigger = _primary_failure_target(records[-1])
    evidence_ids = ", ".join(record.session_id for record in records)
    evidence_refs = ", ".join(
        f"{record.session_id}:{record.failed_tests[0]}" if record.failed_tests else record.session_id
        for record in records
    )
    if records[-1].failed_tests:
        primary_test = records[-1].failed_tests[0]
        next_action = f"Fix the regression around {primary_test} and add a targeted regression test."
        lesson = (
            f"Repeated failure detected for {primary_test} ({len(records)} runs). "
            f"Action: stabilize the shared setup before re-running. "
            f"Evidence: {evidence_ids}."
        )
    else:
        next_action = f"Investigate and stabilize the repeated failure path for {trigger}."
        lesson = (
            f"Repeated failure detected for {trigger} ({len(records)} runs). "
            f"Action: isolate the root cause and add a regression check. "
            f"Evidence: {evidence_ids}."
        )
    lesson = lesson.replace("\n", " ").strip()
    if evidence_refs:
        lesson = f"{lesson} Evidence refs: {evidence_refs}."
    return lesson, next_action


def distill_lessons(records: Iterable[IterationRecord], *, min_occurrences: int = 2) -> list[DistilledLesson]:
    """Group repeated failures into reusable lessons.

    Deterministic grouping: same project_root + same failure signature.
    Only groups with at least ``min_occurrences`` records become lessons.
    """
    groups: dict[str, list[IterationRecord]] = {}
    for record in records:
        if not isinstance(record, IterationRecord):
            continue
        if record.status != "failure":
            continue
        signature = _normalize_signature(record)
        groups.setdefault(signature, []).append(record)

    distilled: list[DistilledLesson] = []
    for signature, group in sorted(groups.items(), key=lambda item: (item[0], item[1][-1].created_at)):
        if len(group) < min_occurrences:
            continue
        lesson, next_action = _build_lesson_text(signature, group)
        evidence_refs = []
        seen: set[str] = set()
        for record in group:
            ref = record.session_id
            if ref not in seen:
                seen.add(ref)
                evidence_refs.append(ref)
        confidence = min(0.95, 0.55 + 0.15 * (len(group) - min_occurrences + 1))
        distilled.append(
            DistilledLesson(
                signature=signature,
                lesson=lesson,
                trigger=_primary_failure_target(group[-1]),
                confidence=confidence,
                evidence_refs=evidence_refs,
                recommended_next_action=next_action,
            )
        )
    return distilled


def select_lesson_for_record(
    record: IterationRecord,
    lessons: Iterable[DistilledLesson],
) -> DistilledLesson | None:
    """Pick the best matching lesson for a specific record."""
    signature = _normalize_signature(record)
    candidates = [lesson for lesson in lessons if lesson.signature == signature]
    if not candidates:
        return None
    return sorted(candidates, key=lambda lesson: (-lesson.confidence, lesson.signature))[0]


__all__ = ["DistilledLesson", "distill_lessons", "select_lesson_for_record"]
