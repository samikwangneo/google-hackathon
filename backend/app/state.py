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

# How long EVOLVED stays pinned after a level-up event. Outranks every other
# mood (apples, sleepy, etc.) so the level-up animation always plays cleanly.
EVOLVED_DURATION_S: float = 10.0

# Max time the pet stays in the WALKING neutral substate before auto-advancing
# to the next entry in the neutral cycle. Other neutral substates hold until
# the mood category changes.
WALKING_DURATION_S: float = 15.0

# A pomodoro fails when its base mood stays ANNOYED for this long.
POMO_FAIL_ANNOYED_THRESHOLD_S: float = 60.0

# Sub-state cycles. Cycled in declared order on every category re-entry.
# WALKING is the 4th slot, so roughly 1 in 4 neutral sessions show the walk.
_NEUTRAL_CYCLE: tuple[PetMood, ...] = (
    PetMood.JENGA,
    PetMood.GAMEBOY,
    PetMood.GENTLE_BREATHING,
    PetMood.WALKING,
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

# Level-up "EVOLVED" deadline. Same shape as the apple windows but checked
# first in _resolve_mood so the level-up animation plays for the full duration
# even when a pomodoro completion already armed _good_apple_until.
_evolved_until: Optional[float] = None

# Cumulative annoyed time during the current pomodoro (monotonic seconds).
# Only ticks while a pomodoro is running and base category == "ANNOYED".
_annoyed_streak_started_at: Optional[float] = None

# Whether a pomodoro was running at the end of the previous aggregate tick.
# Used to detect a True->False transition that wasn't a normal completion,
# i.e. the user manually clicked Stop mid-session.
_pomo_running_last_tick: bool = False

# When the current WALKING neutral substate began (monotonic seconds). None
# whenever the active substate isn't WALKING.
_walking_started_at: Optional[float] = None


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
    global _walking_started_at, _pomo_running_last_tick, _evolved_until

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

        # Manual stop detection: a pomo was running last tick, isn't now, and
        # no completion was drained → user clicked Stop. Treat as a give-up
        # and trigger the BAD_APPLE window (same as the auto-fail path).
        # Skipped on the auto-fail tick because that path locally flips the
        # running flag *after* this check, so pomodoro_raw still says True.
        if (
            _pomo_running_last_tick
            and not pomodoro_raw.running
            and not completions
        ):
            _pending_events.append({"type": "pomodoro_stopped_early"})
            _bad_apple_until = now_monotonic + APPLE_DURATION_S
            _good_apple_until = None
            _annoyed_streak_started_at = None

        # Level-up detection (crosses one or more thresholds)
        new_level = _level_for_xp(_xp)
        evolved_this_tick = False
        if new_level > _level:
            for lvl in range(_level + 1, new_level + 1):
                _pending_events.append({"type": "level_up", "level": lvl})
            _level = new_level
            evolved_this_tick = True
            # Pin EVOLVED for the full duration and suppress any apple windows
            # so the level-up animation doesn't get clobbered by the GOOD_APPLE
            # window the pomodoro-completion branch above already armed.
            _evolved_until = now_monotonic + EVOLVED_DURATION_S
            _good_apple_until = None
            _bad_apple_until = None

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

        # Cap the WALKING neutral substate so the pet doesn't walk indefinitely
        # when the user lingers in NEUTRAL. After the cap fires we auto-advance
        # to the next entry in the neutral cycle.
        if category == "NEUTRAL" and _NEUTRAL_CYCLE[_neutral_idx] == PetMood.WALKING:
            if _walking_started_at is None:
                _walking_started_at = now_monotonic
            elif now_monotonic - _walking_started_at >= WALKING_DURATION_S:
                _neutral_idx = (_neutral_idx + 1) % len(_NEUTRAL_CYCLE)
                _walking_started_at = None
        else:
            _walking_started_at = None

        # Resolve final mood (apple windows + sub-state rotation).
        mood = _resolve_mood(category, now_monotonic)

        # Remember running state for next-tick manual-stop detection. Use the
        # post-auto-fail value so the auto-fail tick doesn't double-trigger
        # BAD_APPLE on the following tick.
        _pomo_running_last_tick = pomodoro.running

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
    # EVOLVED always wins for its full window so the level-up animation gets
    # the screen to itself (no apple/sleepy/annoyed bleed-through).
    if _evolved_until is not None and now_monotonic < _evolved_until:
        return PetMood.EVOLVED
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
