"""State aggregator (Person D).

Pulls from vision.current_presence() + activity.current_state() + the
activity-owned pomodoro engine. Emits a unified BehaviorUpdate for the
WebSocket push loop, owns XP/level math, and queues pomodoro_completed /
level_up events for main.py to drain on the same socket.
"""

from __future__ import annotations

import threading
from typing import Any

from . import activity, vision
from .schemas import (
    BehaviorState,
    BehaviorUpdate,
    PetMood,
    PresenceState,
)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

XP_PER_POMODORO = 50

# Cumulative XP required to *reach* each level. Index = level - 1.
# Level 1 starts at 0 XP. Crossing a threshold = level_up event.
LEVEL_THRESHOLDS: list[int] = [0, 100, 250, 500, 1000, 2000, 4000]


# ---------------------------------------------------------------------------
# Mutable session state (single-process; reset on server restart)
# ---------------------------------------------------------------------------


_lock = threading.Lock()
_xp: int = 0
_level: int = 1
_focus_seconds: int = 0
_pomodoros_completed: int = 0
_just_evolved: bool = False
_pending_events: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _level_for_xp(xp: int) -> int:
    level = 1
    for idx, threshold in enumerate(LEVEL_THRESHOLDS, start=1):
        if xp >= threshold:
            level = idx
    return level


def _pet_mood(
    behavior: BehaviorState,
    presence: PresenceState,
    pomodoro_running: bool,
    just_evolved: bool,
) -> PetMood:
    if just_evolved:
        return PetMood.EVOLVED
    if presence == PresenceState.ABSENT:
        return PetMood.SLEEPY
    if pomodoro_running and behavior == BehaviorState.FOCUSED:
        return PetMood.FOCUS_MODE
    if behavior == BehaviorState.DISTRACTED:
        return PetMood.ANNOYED
    if behavior == BehaviorState.FOCUSED:
        return PetMood.HAPPY
    if behavior == BehaviorState.AWAY:
        return PetMood.SLEEPY
    return PetMood.NEUTRAL


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def aggregate(tick_seconds: float = 1.0) -> BehaviorUpdate:
    """Build the next BehaviorUpdate frame.

    Side effects (intentional, called from the WS loop once per tick):
      * Drains completed pomodoros from activity, awards XP, queues events.
      * Increments today's focus_seconds counter when behavior is FOCUSED.
      * Detects level-up crossings and queues level_up events.
    """
    global _xp, _level, _focus_seconds, _pomodoros_completed, _just_evolved

    presence_snap = vision.current_presence()
    activity_snap = activity.current_state()
    pomodoro = activity.pomodoro_state()
    completions = activity.drain_completed_pomodoros()

    with _lock:
        # Drain pomodoro completions → XP + events
        if completions:
            _pomodoros_completed += completions
            for _ in range(completions):
                _xp += XP_PER_POMODORO
                _pending_events.append(
                    {"type": "pomodoro_completed", "xp_delta": XP_PER_POMODORO}
                )

        # Level-up detection (crosses one or more thresholds)
        new_level = _level_for_xp(_xp)
        evolved_this_tick = False
        if new_level > _level:
            for lvl in range(_level + 1, new_level + 1):
                _pending_events.append({"type": "level_up", "level": lvl})
            _level = new_level
            evolved_this_tick = True

        # Focus-time accounting
        if activity_snap.state == BehaviorState.FOCUSED:
            _focus_seconds += int(tick_seconds)

        # EVOLVED mood lasts exactly one frame
        mood = _pet_mood(
            activity_snap.state,
            presence_snap.presence,
            pomodoro.running,
            evolved_this_tick or _just_evolved,
        )
        _just_evolved = False

        return BehaviorUpdate(
            state=activity_snap.state,
            presence=presence_snap.presence,
            pet_mood=mood,
            active_window=activity_snap.active_window,
            focus_seconds=_focus_seconds,
            distraction_streak=activity_snap.distraction_streak,
            xp=_xp,
            level=_level,
            pomodoro=pomodoro,
        )


def drain_events() -> list[dict[str, Any]]:
    """Pop and return any pending special events (pomodoro_completed, level_up)."""
    with _lock:
        events = _pending_events[:]
        _pending_events.clear()
        return events


def stats_today() -> dict[str, int]:
    with _lock:
        return {
            "focus_seconds": _focus_seconds,
            "xp": _xp,
            "level": _level,
            "pomodoros": _pomodoros_completed,
        }
