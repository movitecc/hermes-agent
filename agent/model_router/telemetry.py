"""Routing telemetry — SQLite history of every pipeline decision.

Records mode, stage, turn type, selected/suggested model, candidate scores,
and routing latency for observability (``hermes router history/stats``).
Privacy: prompts are never stored — only a djb2 hash and a bounded length.
Bounded to the newest ~10k rows. Failure-safe: telemetry never breaks routing.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

from .types import RoutingDecision, RoutingRequest

MAX_ROWS = 10_000

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS routing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL,
    stage TEXT NOT NULL,
    turn_type TEXT NOT NULL DEFAULT 'unknown',
    selected_model TEXT NOT NULL,
    suggestion TEXT NOT NULL DEFAULT '',
    reason_code TEXT NOT NULL DEFAULT '',
    pinned INTEGER NOT NULL DEFAULT 0,
    candidates_json TEXT NOT NULL DEFAULT '[]',
    rejected_json TEXT NOT NULL DEFAULT '[]',
    latency_ms REAL NOT NULL DEFAULT 0,
    prompt_hash TEXT NOT NULL DEFAULT '',
    prompt_chars INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_routing_history_ts ON routing_history(ts DESC);
CREATE INDEX IF NOT EXISTS idx_routing_history_session ON routing_history(session_id, ts DESC);
CREATE TABLE IF NOT EXISTS router_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 0,
    retryable INTEGER NOT NULL DEFAULT 0,
    error_category TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    latency_ms REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_router_outcomes_model ON router_outcomes(model_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_router_outcomes_ts ON router_outcomes(ts DESC);
"""


def prompt_hash(text: str) -> str:
    """Deterministic djb2 hash — identifies repeat prompts without storing them."""
    h = 5381
    for ch in (text or "")[:256]:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return f"{h:x}"


def _candidate_score(candidate) -> float:
    """Return the final score for either pipeline candidate representation."""
    if hasattr(candidate, "composite_score"):
        return candidate.composite_score
    return candidate.score


class RouterTelemetry:
    """SQLite-backed routing decision log. Thread-safe, failure-safe."""

    def __init__(self, db_path):
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._available = True
        try:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
            os.chmod(self._db_path, 0o600)
        except Exception as exc:
            self._available = False
            logger.warning(
                "Model router telemetry initialization failed: db=%s error_type=%s",
                self._db_path,
                type(exc).__name__,
            )

    @property
    def available(self) -> bool:
        return self._available

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def record(self, request: RoutingRequest, decision: RoutingDecision, *, mode: str, session_id: str = "") -> None:
        if not self._available:
            return
        try:
            candidates = [
                {
                    "model": candidate.model_id,
                    "score": round(_candidate_score(candidate), 4),
                    "rejected": candidate.rejected_reason,
                }
                for candidate in decision.candidates
            ]
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO routing_history (ts, session_id, mode, stage, turn_type,"
                    " selected_model, suggestion, reason_code, pinned, candidates_json,"
                    " rejected_json, latency_ms, prompt_hash, prompt_chars)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        time.time(),
                        session_id or request.session_id or "",
                        mode,
                        decision.stage,
                        decision.turn_type,
                        decision.selected_model,
                        decision.suggestion,
                        decision.reason_code,
                        1 if decision.pinned else 0,
                        json.dumps(candidates),
                        json.dumps(list(decision.rejected)),
                        decision.routing_latency_ms,
                        prompt_hash(request.prompt_text),
                        len(request.prompt_text or ""),
                    ),
                )
                conn.execute(
                    "DELETE FROM routing_history WHERE id NOT IN"
                    " (SELECT id FROM routing_history ORDER BY id DESC LIMIT ?)",
                    (MAX_ROWS,),
                )
        except Exception as exc:
            logger.warning(
                "Model router telemetry write failed: db=%s mode=%s stage=%s "
                "error_type=%s",
                self._db_path,
                mode,
                decision.stage,
                type(exc).__name__,
            )

    def record_outcome(
        self,
        *,
        session_id: str = "",
        provider: str = "",
        model_id: str = "",
        success: bool = False,
        retryable: bool = False,
        error_category: str = "",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        latency_ms=0.0,
    ) -> None:
        """Persist bounded, prompt-free outcome data; failures are non-fatal."""
        if not self._available or not str(model_id or "").strip():
            return
        try:
            import math

            def nonnegative_int(value):
                try:
                    return max(0, int(value))
                except (TypeError, ValueError, OverflowError):
                    return 0

            def nonnegative_float(value):
                try:
                    number = float(value)
                    return number if math.isfinite(number) and number >= 0 else 0.0
                except (TypeError, ValueError, OverflowError):
                    return 0.0

            allowed_categories = {
                "timeout", "rate_limit", "server_error", "overloaded",
                "network", "auth", "billing", "format_error", "unknown",
            }
            category = str(error_category or "").strip().lower()
            if category not in allowed_categories:
                category = ""
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO router_outcomes "
                    "(ts, session_id, provider, model_id, success, retryable, "
                    "error_category, input_tokens, output_tokens, cost_usd, latency_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        time.time(), str(session_id or "")[:200],
                        str(provider or "")[:100], str(model_id)[:200],
                        1 if success else 0, 1 if retryable else 0, category,
                        nonnegative_int(input_tokens), nonnegative_int(output_tokens),
                        nonnegative_float(cost_usd), nonnegative_float(latency_ms),
                    ),
                )
                conn.execute(
                    "DELETE FROM router_outcomes WHERE id NOT IN "
                    "(SELECT id FROM router_outcomes ORDER BY id DESC LIMIT ?)",
                    (MAX_ROWS,),
                )
        except Exception as exc:
            logger.warning(
                "Model router outcome write failed: db=%s error_type=%s",
                self._db_path, type(exc).__name__,
            )

    def feedback_stats(self) -> dict:
        """Return aggregate outcome data for observation, not auto-retraining."""
        empty = {"total": 0, "successful": 0, "retryable_failures": 0, "by_model": {}}
        if not self._available:
            return empty
        try:
            with self._lock, self._connect() as conn:
                total, successful, retryable = conn.execute(
                    "SELECT COUNT(*), COALESCE(SUM(success), 0), "
                    "COALESCE(SUM(CASE WHEN retryable=1 THEN 1 ELSE 0 END), 0) "
                    "FROM router_outcomes"
                ).fetchone()
                rows = conn.execute(
                    "SELECT model_id, COUNT(*), COALESCE(SUM(success), 0), "
                    "COALESCE(SUM(retryable), 0), COALESCE(SUM(input_tokens), 0), "
                    "COALESCE(SUM(output_tokens), 0), COALESCE(SUM(cost_usd), 0), "
                    "COALESCE(AVG(latency_ms), 0) FROM router_outcomes GROUP BY model_id"
                ).fetchall()
            by_model = {}
            for model, count, ok, retry_count, input_total, output_total, cost, latency in rows:
                by_model[model] = {
                    "total": count, "successful": ok,
                    "retryable_failures": retry_count,
                    "success_rate": round(ok / count, 6) if count else 0.0,
                    "input_tokens": input_total, "output_tokens": output_total,
                    "cost_usd": round(float(cost), 8),
                    "latency_ms": round(float(latency), 3),
                }
            return {
                "total": total, "successful": successful,
                "retryable_failures": retryable, "by_model": by_model,
            }
        except Exception:
            return empty

    def history(self, *, limit: int = 20, session_id: str = "") -> list:
        if not self._available:
            return []
        try:
            with self._lock, self._connect() as conn:
                if session_id:
                    rows = conn.execute(
                        "SELECT ts, session_id, mode, stage, turn_type, selected_model,"
                        " suggestion, reason_code, pinned, latency_ms FROM routing_history"
                        " WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                        (session_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT ts, session_id, mode, stage, turn_type, selected_model,"
                        " suggestion, reason_code, pinned, latency_ms FROM routing_history"
                        " ORDER BY id DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
        except Exception:
            return []
        return [
            {
                "ts": r[0], "session_id": r[1], "mode": r[2], "stage": r[3],
                "turn_type": r[4], "selected_model": r[5], "suggestion": r[6],
                "reason_code": r[7], "pinned": bool(r[8]), "latency_ms": r[9],
            }
            for r in rows
        ]

    def stats(self) -> dict:
        if not self._available:
            return {}
        try:
            with self._lock, self._connect() as conn:
                total = conn.execute("SELECT COUNT(*) FROM routing_history").fetchone()[0]
                by_stage = dict(
                    conn.execute(
                        "SELECT stage, COUNT(*) FROM routing_history GROUP BY stage ORDER BY 2 DESC"
                    ).fetchall()
                )
                by_model = dict(
                    conn.execute(
                        "SELECT selected_model, COUNT(*) FROM routing_history"
                        " GROUP BY selected_model ORDER BY 2 DESC"
                    ).fetchall()
                )
                avg_latency = conn.execute(
                    "SELECT AVG(latency_ms) FROM routing_history"
                ).fetchone()[0]
        except Exception:
            return {}
        return {
            "total": total,
            "by_stage": by_stage,
            "by_model": by_model,
            "avg_latency_ms": round(avg_latency or 0.0, 3),
        }
