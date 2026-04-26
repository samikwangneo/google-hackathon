"""State aggregator (Person D).

Pulls from vision.current_presence() + activity.current_state() + the
activity-owned pomodoro engine. Emits a unified BehaviorUpdate for the
WebSocket push loop, owns XP/level math, and queues pomodoro_completed /
level_up events for main.py to drain on the same socket.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from . import activity, vision
from .schemas import (
    BehaviorState,
    BehaviorUpdate,
    PetMood,
    PomodoroState as SchemaPomodoroState,
    PresenceState,
)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

XP_PER_POMODORO = 50

# Cumulative XP required to *reach* each level. Index = level - 1.
# Level 1 starts at 0 XP. Crossing a threshold = level_up event.
LEVEL_THRESHOLDS: list[int] = [0, 100, 250, 500, 1000, 2000, 4000]

# How long GOOD_APPLE / BAD_APPLE moods stick after their triggering event.
APPLE_DURATION_S: float = 10.0

# A pomodoro fails when its base mood stays ANNOYED for this long.
POMO_FAIL_ANNOYED_THRESHOLD_S: float = 60.0

# Sub-state cycles. Cycled in declared order on every category re-entry.
_NEUTRAL_CYCLE: tuple[PetMood, ...] = (
    PetMood.JENGA,
    PetMood.GAMEBOY,
    PetMood.GENTLE_BREATHING,
)
_ANNOYED_CYCLE: tuple[PetMood, ...] = (
    PetMood.ANNOYED_FOOT_TAPPING,
    PetMood.ANNOYED_DOOM_SCROLLING,
    PetMood.EXAM_PANIC_MODE,
)


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

# Sub-state rotation. Indices start at -1 so the first entry into a category
# advances to 0 (= first item in the cycle tuple).
_neutral_idx: int = -1
_annoyed_idx: int = -1
_last_mood_category: Optional[str] = None

# Apple-window deadlines (monotonic seconds). None = window inactive.
_good_apple_until: Optional[float] = None
_bad_apple_until: Optional[float] = None

# Cumulative annoyed time during the current pomodoro (monotonic seconds).
# Only ticks while a pomodoro is running and base category == "ANNOYED".
_annoyed_streak_started_at: Optional[float] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _level_for_xp(xp: int) -> int:
    level = 1
    for idx, threshold in enumerate(LEVEL_THRESHOLDS, start=1):
        if xp >= threshold:
            level = idx
    return level


def _base_category(
    behavior: BehaviorState,
    presence: PresenceState,
    pomodoro_running: bool,
    just_evolved: bool,
    phone_present: bool,
) -> str:
    """Resolve the abstract mood category before sub-state rotation / apple windows.

    Returns one of: "EVOLVED", "SLEEPY", "ANNOYED", "FOCUS_MODE", "HAPPY", "NEUTRAL".
    The aggregate loop layers GOOD_APPLE / BAD_APPLE windows on top of this.
    """
    if just_evolved:
        return "EVOLVED"

    if presence == PresenceState.ABSENT or behavior == BehaviorState.AWAY:
        return "SLEEPY"

    if (
        phone_present
        or presence == PresenceState.LOOKING_AWAY
        or behavior == BehaviorState.DISTRACTED
    ):
        return "ANNOYED"

    if (
        pomodoro_running
        and behavior == BehaviorState.FOCUSED
        and presence == PresenceState.PRESENT
    ):
        return "FOCUS_MODE"

    if behavior == BehaviorState.FOCUSED and presence == PresenceState.PRESENT:
        return "HAPPY"

    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def aggregate(tick_seconds: float = 1.0) -> BehaviorUpdate:
    """Build the next BehaviorUpdate frame.

    Side effects (intentional, called from the WS loop once per tick):
      * Drains completed pomodoros from activity, awards XP, queues events.
      * Increments today's focus_seconds counter when behavior is FOCUSED.
      * Detects level-up crossings and queues level_up events.
      * Maintains GOOD_APPLE / BAD_APPLE mood windows.
      * Auto-fails a pomodoro that stays ANNOYED past the threshold.
    """
    global _xp, _level, _focus_seconds, _pomodoros_completed, _just_evolved
    global _neutral_idx, _annoyed_idx, _last_mood_category
    global _good_apple_until, _bad_apple_until, _annoyed_streak_started_at

    now_monotonic = time.monotonic()

    presence_snap = vision.current_presence()
    phone_present = bool(getattr(presence_snap, "phone_present", False))
    activity_snap = activity.current_state()
    pomodoro_raw = activity.pomodoro_status()
    completions = len(activity.drain_pomodoro_events())
    pomodoro = SchemaPomodoroState(
        running=pomodoro_raw.running,
        ends_at=pomodoro_raw.ends_at,
        minutes=pomodoro_raw.minutes,
    )

    with _lock:
        # Drain pomodoro completions → XP + events + GOOD_APPLE window
        if completions:
            _pomodoros_completed += completions
            for _ in range(completions):
                _xp += XP_PER_POMODORO
                _pending_events.append(
                    {"type": "pomodoro_completed", "xp_delta": XP_PER_POMODORO}
                )
            _good_apple_until = now_monotonic + APPLE_DURATION_S
            _bad_apple_until = None
            _annoyed_streak_started_at = None

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

        # Resolve the abstract mood category for this tick
        category = _base_category(
            activity_snap.state,
            presence_snap.state,
            pomodoro.running,
            evolved_this_tick or _just_evolved,
            phone_present,
        )
        _just_evolved = False

        # Track annoyed-during-pomodoro streak; auto-fail when it crosses the
        # threshold. Only counts time the pomo has actually been running.
        if pomodoro.running and category == "ANNOYED":
            if _annoyed_streak_started_at is None:
                _annoyed_streak_started_at = now_monotonic
            elif (
                now_monotonic - _annoyed_streak_started_at
                >= POMO_FAIL_ANNOYED_THRESHOLD_S
            ):
                try:
                    activity.pomodoro_stop()
                except Exception:
                    pass
                _pending_events.append({"type": "pomodoro_failed"})
                _bad_apple_until = now_monotonic + APPLE_DURATION_S
                _good_apple_until = None
                _annoyed_streak_started_at = None
                # Reflect the stop locally so this tick's frame is consistent.
                pomodoro = SchemaPomodoroState(
                    running=False,
                    ends_at=None,
                    minutes=pomodoro.minutes,
                )
        else:
            _annoyed_streak_started_at = None

        # Advance sub-state rotation on category re-entry only.
        if category != _last_mood_category:
            if category == "NEUTRAL":
                _neutral_idx = (_neutral_idx + 1) % len(_NEUTRAL_CYCLE)
            elif category == "ANNOYED":
                _annoyed_idx = (_annoyed_idx + 1) % len(_ANNOYED_CYCLE)
            _last_mood_category = category

        # Resolve final mood (apple windows + sub-state rotation).
        mood = _resolve_mood(category, now_monotonic)

        return BehaviorUpdate(
            state=activity_snap.state,
            presence=presence_snap.state,
            pet_mood=mood,
            active_window=activity_snap.active_window,
            focus_seconds=_focus_seconds,
            distraction_streak=int(activity_snap.distraction_streak_seconds),
            xp=_xp,
            level=_level,
            pomodoro=pomodoro,
            phone_present=phone_present,
        )


def _resolve_mood(category: str, now_monotonic: float) -> PetMood:
    """Layer EVOLVED / GOOD_APPLE / BAD_APPLE windows on top of the base category,
    then map NEUTRAL / ANNOYED categories to their rotated sub-states.
    """
    if category == "EVOLVED":
        return PetMood.EVOLVED
    if _good_apple_until is not None and now_monotonic < _good_apple_until:
        return PetMood.GOOD_APPLE
    if _bad_apple_until is not None and now_monotonic < _bad_apple_until:
        return PetMood.BAD_APPLE
    if category == "SLEEPY":
        return PetMood.SLEEPY
    if category == "ANNOYED":
        return _ANNOYED_CYCLE[_annoyed_idx]
    if category == "FOCUS_MODE":
        return PetMood.FOCUS_MODE
    if category == "HAPPY":
        return PetMood.HAPPY
    return _NEUTRAL_CYCLE[_neutral_idx]


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
