"""Second-brain log (Person D).

Append-only JSONL at backend/data/brain.jsonl. No SQLite, per the plan.

Public surface:
    log_event(kind, text, meta=None) -> None
    search(q, limit=20) -> BrainSearchResponse
    today_summary() -> BrainTodayResponse
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .schemas import BrainHit, BrainSearchResponse, BrainTodayResponse


_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "brain.jsonl"
_lock = threading.Lock()


def _ensure_path() -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _LOG_PATH.exists():
        _LOG_PATH.touch()


def _read_all() -> list[dict[str, Any]]:
    _ensure_path()
    rows: list[dict[str, Any]] = []
    with _LOG_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def log_event(kind: str, text: str, meta: Optional[dict[str, Any]] = None) -> None:
    """Append a single event to brain.jsonl."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "text": text,
        "meta": meta or {},
    }
    with _lock:
        _ensure_path()
        with _LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")


def _score(text: str, query_terms: list[str]) -> float:
    if not query_terms:
        return 0.0
    hay = text.lower()
    return float(sum(hay.count(t) for t in query_terms))


def search(q: str, limit: int = 20) -> BrainSearchResponse:
    """Keyword search over the log (case-insensitive token-overlap score).

    Gemini rerank is a TODO — keep the contract stable so we can layer it on
    without touching callers.
    """
    terms = [t for t in q.lower().split() if t]
    rows = _read_all()
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        text = str(row.get("text", ""))
        s = _score(text, terms)
        if s > 0:
            scored.append((s, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    hits: list[BrainHit] = []
    for score, row in scored[:limit]:
        try:
            ts = datetime.fromisoformat(row["timestamp"])
        except (KeyError, ValueError):
            ts = datetime.now(timezone.utc)
        hits.append(
            BrainHit(
                timestamp=ts,
                kind=str(row.get("kind", "event")),
                text=str(row.get("text", "")),
                score=score,
            )
        )
    return BrainSearchResponse(hits=hits)


def today_summary() -> BrainTodayResponse:
    """Naive summary of today's log: top topics + a focus score 0-100."""
    rows = _read_all()
    today = datetime.now(timezone.utc).date()
    todays: list[dict[str, Any]] = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(str(row.get("timestamp", "")))
        except ValueError:
            continue
        if ts.date() == today:
            todays.append(row)

    # Top topics = most frequent `kind` values.
    topic_counts = Counter(str(row.get("kind", "event")) for row in todays)
    topics = [kind for kind, _ in topic_counts.most_common(5)]

    # Focus score heuristic: pomodoros completed * 20, capped at 100.
    pomodoros = sum(1 for row in todays if row.get("kind") == "pomodoro_completed")
    score = min(100, pomodoros * 20)

    if todays:
        summary = (
            f"Logged {len(todays)} events today across {len(topic_counts)} topics. "
            f"{pomodoros} pomodoros completed."
        )
    else:
        summary = "No events logged today yet — start a Pomodoro to begin."

    return BrainTodayResponse(summary=summary, topics=topics, score=score)
