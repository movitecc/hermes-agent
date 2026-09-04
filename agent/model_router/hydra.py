"""HyDRA-style requirement/capability matcher (deterministic port).

pi-smart-router's HyDRA matcher projects a prompt embedding into a 3D
requirement space (reasoning, code_gen, tool_use) and scores models by
capability shortfall with a multi-objective re-rank. The neural encoder is an
optional artifact there; the structure — requirement vector, shortfall gate,
multi-objective selection — is what this module ports.

Hermes default is fully deterministic: the requirement vector is derived from
triage signals, the turn envelope, and structural prompt features. If
``hydra.embeddings: true`` is configured, a semantic-similarity backend may be
layered on later; the deterministic vector remains the fallback and the gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .low_intensity import compute_code_block_ratio
from .scoring import FrugalityWeights, MultiObjectiveResult, score_multi_objective
from .triage import CYCLOMATIC_THRESHOLD, TriageResult
from .types import CandidateScore, ModelProfile, RoutingRequest, TURN_PLANNING, TURN_TOOL_RESULT

# Hard-gate thresholds: requirements above these demand declared capabilities.
REASONING_REQUIREMENT_GATE = 0.6
SHORTFALL_TOLERANCE = 0.25


class OnnxEmbeddingBackend:
    """Optional ONNX sentence-embedding adapter with a fail-closed API.

    ``session`` and ``tokenizer`` are injected so the router does not discover
    credentials, download artifacts, or import ONNX at startup. The tokenizer
    must return numpy-compatible ``input_ids`` and ``attention_mask`` arrays.
    """

    def __init__(self, *, session: Any, tokenizer: Callable[[str], dict]):
        self._session = session
        self._tokenizer = tokenizer

    def embed(self, text: str):
        import numpy as np

        encoded = self._tokenizer(text or "")
        inputs = {item.name: encoded[item.name] for item in self._session.get_inputs() if item.name in encoded}
        if not inputs:
            raise ValueError("ONNX tokenizer produced no model inputs")
        output = self._session.run(None, inputs)[0]
        values = np.asarray(output, dtype=np.float32)
        if values.ndim == 3:
            mask = np.asarray(encoded.get("attention_mask"), dtype=np.float32)
            if mask.ndim == 2:
                values = (values * mask[:, :, None]).sum(axis=1) / np.maximum(mask.sum(axis=1, keepdims=True), 1.0)
            else:
                values = values.mean(axis=1)
        if values.ndim == 2:
            values = values[0]
        norm = float(np.linalg.norm(values))
        return values / norm if norm > 0 else values

    def try_embed(self, text: str) -> Optional[Any]:
        try:
            return self.embed(text)
        except Exception:
            return None

_CODE_RE = re.compile(
    r"\b(code|coding|debug|traceback|python|javascript|typescript|sql|api|implement|refactor|test|"
    r"代码|调试|报错|脚本|编程|函数|接口)\b",
    re.I,
)
_REASON_RE = re.compile(
    r"\b(why|prove|tradeoff|architecture|分析|推导|证明|原因|权衡|架构|设计)\b",
    re.I,
)
_TOOL_CUE_PATTERNS = tuple(
    re.compile(p, re.I)
    for p in (
        r"\b(run|execute|shell|terminal|command|bash)\b",
        r"\b(read|write|edit|patch|create)\s+(the\s+)?(file|config|code)\b",
        r"\b(search|fetch|browse|scrape|download)\b",
        r"\b(git|docker|ssh|curl)\b",
        r"\b(deploy|install|build|test)\b",
    )
)


@dataclass(frozen=True)
class RequirementVector:
    reasoning: float
    code_gen: float
    tool_use: float

    @property
    def magnitude(self) -> float:
        return max(self.reasoning, self.code_gen, self.tool_use)


def _clamp01(value: float) -> float:
    return 0.0 if value <= 0 else (1.0 if value >= 1 else value)


def _semantic_requirement_vector(text: str, backend) -> Optional[RequirementVector]:
    """Map optional embedding similarity to requirement axes."""
    try:
        import math

        query = backend.try_embed(text)
        if query is None:
            return None
        query = list(query)
        qnorm = math.sqrt(sum(float(x) * float(x) for x in query))
        if qnorm <= 0:
            return None
        axes = ("code", "reason", "tool")
        values = []
        for axis in axes:
            proto = backend.try_embed(axis)
            if proto is None:
                return None
            proto = list(proto)
            pnorm = math.sqrt(sum(float(x) * float(x) for x in proto))
            if pnorm <= 0 or len(proto) != len(query):
                return None
            similarity = sum(float(a) * float(b) for a, b in zip(query, proto)) / (qnorm * pnorm)
            values.append(_clamp01(similarity))
        return RequirementVector(values[1], values[0], values[2])
    except Exception:
        return None


def build_requirement_vector(
    request: RoutingRequest,
    triage_result: TriageResult,
    embedding_backend=None,
) -> RequirementVector:
    """Derive a 3D requirement vector, optionally blending semantic signals."""
    text = request.prompt_text or ""
    turn_type = request.turn_type or "unknown"

    reasoning = _clamp01(
        0.35 * (1.0 if _REASON_RE.search(text) else 0.0)
        + 0.30 * min(triage_result.complex_hits / 3.0, 1.0)
        + 0.20 * (1.0 if triage_result.cyclomatic_score >= CYCLOMATIC_THRESHOLD else 0.0)
        + 0.15 * (1.0 if turn_type == TURN_PLANNING else 0.0)
    )
    code_gen = _clamp01(
        0.40 * (1.0 if _CODE_RE.search(text) else 0.0)
        + 0.35 * compute_code_block_ratio(text)
        + 0.25 * min(triage_result.cyclomatic_score / CYCLOMATIC_THRESHOLD, 1.0)
    )
    cue_hits = sum(1 for p in _TOOL_CUE_PATTERNS if p.search(text))
    tool_use = _clamp01(
        0.50 * (1.0 if turn_type == TURN_TOOL_RESULT or any(getattr(m, "role", None) == "tool" for m in request.messages or ()) else 0.0)
        + 0.50 * min(cue_hits / 3.0, 1.0)
    )
    deterministic = RequirementVector(reasoning, code_gen, tool_use)
    if embedding_backend is None:
        return deterministic
    semantic = _semantic_requirement_vector(text, embedding_backend)
    if semantic is None:
        return deterministic
    return RequirementVector(
        reasoning=0.7 * deterministic.reasoning + 0.3 * semantic.reasoning,
        code_gen=0.7 * deterministic.code_gen + 0.3 * semantic.code_gen,
        tool_use=0.7 * deterministic.tool_use + 0.3 * semantic.tool_use,
    )


def _capability_scores(profile: ModelProfile):
    """(reasoning_cap, code_cap, tool_cap) in 0..1 from declared capabilities."""
    reasoning_cap = 1.0 if profile.reasoning else 0.3 + 0.4 * profile.quality
    code_cap = 0.5 + 0.5 * profile.quality
    name = profile.id.lower()
    if "code" in name or "kimi" in name or "codex" in name:
        code_cap = min(1.0, code_cap + 0.15)
    tool_cap = 0.4 + 0.6 * profile.quality
    return reasoning_cap, code_cap, tool_cap


def score_fleet(
    fleet,
    requirements: RequirementVector,
    request: RoutingRequest,
) -> tuple:
    """Capability-score every candidate with a shortfall gate.

    Hard gates: vision required, reasoning required above the gate, unhealthy.
    Soft shortfall: capability gaps beyond tolerance reject the candidate.
    """
    scores = []
    for profile in fleet:
        if not profile.healthy:
            scores.append(CandidateScore(profile.id, 0.0, rejected_reason="unhealthy"))
            continue
        if request.has_images and not profile.vision:
            scores.append(CandidateScore(profile.id, 0.0, rejected_reason="requires_vision"))
            continue
        if requirements.reasoning >= REASONING_REQUIREMENT_GATE and not profile.reasoning:
            scores.append(CandidateScore(profile.id, 0.0, rejected_reason="requires_reasoning"))
            continue

        reasoning_cap, code_cap, tool_cap = _capability_scores(profile)
        short_r = max(0.0, requirements.reasoning - reasoning_cap)
        short_c = max(0.0, requirements.code_gen - code_cap)
        short_t = max(0.0, requirements.tool_use - tool_cap)
        shortfall = short_r + short_c + short_t
        if shortfall > SHORTFALL_TOLERANCE * 3:
            scores.append(
                CandidateScore(profile.id, 0.0, shortfall=shortfall, rejected_reason="capability_shortfall")
            )
            continue

        capability = profile.quality - 0.6 * short_r - 0.5 * short_c - 0.4 * short_t
        if request.has_images and profile.vision:
            capability += 0.1
        scores.append(CandidateScore(profile.id, capability, shortfall=shortfall))
    return tuple(scores)


def hydra_match(
    fleet,
    requirements: RequirementVector,
    request: RoutingRequest,
    weights: FrugalityWeights = FrugalityWeights(),
) -> MultiObjectiveResult:
    """Full deterministic HyDRA-style match: capability gate + multi-objective."""
    capability_scores = score_fleet(fleet, requirements, request)
    return score_multi_objective(capability_scores, fleet, weights)
