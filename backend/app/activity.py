"""Screen / activity tracking module — Person C owns this file.

Public surface (do NOT change without pinging the channel):
    current_state() -> ActivitySnapshot
    pomodoro_state() -> PomodoroState
    start_pomodoro(minutes) -> (started_at, ends_at)
    stop_pomodoro() -> None
    drain_completed_pomodoros() -> int   # number of completions since last call

Person D scaffold: a working in-memory pomodoro timer plus IDLE behavior
so the rest of the system (state.py, main.py) runs end-to-end. Person C
replaces the body of current_state() with real window/keyboard tracking
and the behavior classifier.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from .schemas import ActivitySnapshot, BehaviorState, PomodoroState


# ---------------------------------------------------------------------------
# Pomodoro engine (lives here per the team split)
# ---------------------------------------------------------------------------


_lock = threading.Lock()
_running: bool = False
_started_at: Optional[datetime] = None
_ends_at: Optional[datetime] = None
_minutes: int = 25
_pending_completions: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_completion_locked() -> None:
    """Caller must hold _lock. Promotes a finished timer into a pending event."""
    global _running, _started_at, _ends_at, _pending_completions
    if _running and _ends_at is not None and _now() >= _ends_at:
        _pending_completions += 1
        _running = False
        _started_at = None
        _ends_at = None


def start_pomodoro(minutes: int) -> tuple[datetime, datetime]:
    global _running, _started_at, _ends_at, _minutes
    with _lock:
        _minutes = int(minutes)
        _started_at = _now()
        _ends_at = _started_at + timedelta(minutes=_minutes)
        _running = True
        return _started_at, _ends_at


def stop_pomodoro() -> None:
    global _running, _started_at, _ends_at
    with _lock:
        _running = False
        _started_at = None
        _ends_at = None


def pomodoro_state() -> PomodoroState:
    with _lock:
        _check_completion_locked()
        return PomodoroState(running=_running, ends_at=_ends_at, minutes=_minutes)


def drain_completed_pomodoros() -> int:
    """Return + reset the count of pomodoros that completed since last call."""
    global _pending_completions
    with _lock:
        _check_completion_locked()
        n = _pending_completions
        _pending_completions = 0
        return n


# ---------------------------------------------------------------------------
# Activity classifier (Person C replaces this stub)
# ---------------------------------------------------------------------------


def current_state() -> ActivitySnapshot:
    """Latest activity classification.

    Person C will replace with active-window polling + keyboard/mouse
    sampling + the FOCUSED/DISTRACTED/IDLE/MULTITASKING/AWAY classifier.
    """
    return ActivitySnapshot(
        state=BehaviorState.IDLE,
        active_window=None,
        distraction_streak=0,
    )
