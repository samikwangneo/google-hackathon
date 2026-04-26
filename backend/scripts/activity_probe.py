"""Interactive probe for TerpPet activity tracking.

Run this from the backend directory:

    python scripts/activity_probe.py

Then switch apps, open distracting/focused pages, stop touching the laptop,
and watch the classifier update once per second.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import activity  # noqa: E402


STATE_BADGES: Dict[str, str] = {
    "FOCUSED": "OK  ",
    "DISTRACTED": "WARN",
    "IDLE": "IDLE",
    "AWAY": "AWAY",
}


def _short(value: Any, width: int) -> str:
    if not value:
        return "-".ljust(width)
    clean = " ".join(str(value).split())
    if len(clean) <= width:
        return clean.ljust(width)
    return clean[: max(0, width - 1)] + "…"


def _tracker_flag(name: str, default: Any = None) -> Any:
    tracker = getattr(activity, "_tracker", None)
    if tracker is None:
        return default
    return getattr(tracker, name, default)


def _print_instructions() -> None:
    print(
        """
TerpPet Activity Probe
======================

What to try while this runs:

1. Focused app test:
   - Click back into Cursor / VS Code / Terminal / Google Docs.
   - Expected: state becomes FOCUSED, focus_today increases.

2. Distracting window test:
   - Open YouTube, Reddit, Instagram, TikTok, Netflix, Twitch, X/Twitter, etc.
   - Expected: state becomes DISTRACTED, distraction_streak increases.
   - If window title is unavailable, rerun with --screen-ai so Gemini can look
     at a screenshot every 10 seconds and classify the visible page.

3. App switching test:
   - Cmd-Tab between windows.
   - Expected: switches_60s climbs for debugging only; state stays focused or
     distracted based on the visible content.

4. Idle test:
   - Do not touch mouse or keyboard for 30+ seconds.
   - Expected: state becomes IDLE.

5. Away test:
   - Do not touch mouse or keyboard for 120+ seconds.
   - Expected: state becomes AWAY.

6. Permission sanity:
   - If app shows but title is always '-', grant Screen Recording permission to
     the terminal app you are running this from, then restart the terminal.
   - If idle_sec never increases, grant Accessibility permission to the same
     terminal app, then restart the terminal.

Press Ctrl-C to stop.
"""
    )


def _print_permission_hint() -> None:
    listeners_active = bool(_tracker_flag("_listeners_active", False))
    print("Permission / sensor status:")
    print(f"  input listeners active: {'yes' if listeners_active else 'no'}")
    if not listeners_active:
        print(
            "  hint: on macOS, enable Accessibility for Terminal/iTerm/Cursor "
            "if you want IDLE/AWAY detection."
        )

    try:
        app_name, title = activity._get_active_window()  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - diagnostic path
        app_name, title = None, None
        print(f"  active-window probe raised: {exc!r}")

    print(f"  current active app: {app_name or '-'}")
    print(f"  current window title: {title or '-'}")
    if app_name and not title and sys.platform == "darwin":
        print(
            "  hint: app detection works but title is missing; enable Screen "
            "Recording for the terminal app, then restart it."
        )
    print()


def _format_row(snapshot: Any) -> str:
    badge = STATE_BADGES.get(snapshot.state, "????")
    ai_state = getattr(snapshot, "ai_screen_state", None)
    ai_reason = getattr(snapshot, "ai_screen_reason", None)
    ai_confidence = getattr(snapshot, "ai_screen_confidence", None)
    state_source = getattr(snapshot, "state_source", "rules")
    ai_part = ""
    if ai_state:
        confidence = ""
        if isinstance(ai_confidence, (int, float)):
            confidence = f"({ai_confidence:.2f})"
        ai_part = f" ai={ai_state}{confidence}:{_short(ai_reason, 24).strip()}"
    return (
        f"{time.strftime('%H:%M:%S')} "
        f"{badge} "
        f"state={snapshot.state:<13} "
        f"src={state_source:<9} "
        f"app={_short(snapshot.active_app, 18)} "
        f"title={_short(snapshot.active_window, 34)} "
        f"url={_short(snapshot.active_url, 18)} "
        f"idle_sec={snapshot.seconds_since_input:6.1f} "
        f"switches_60s={snapshot.window_switches_60s:2d} "
        f"focus_today={snapshot.focus_seconds_today:7.1f} "
        f"streak={snapshot.distraction_streak_seconds:6.1f}"
        f"{ai_part}"
    )


def _dump_jsonish(snapshot: Any) -> None:
    payload = asdict(snapshot)
    payload["timestamp"] = snapshot.timestamp.isoformat()
    print(payload)


def run(
    duration: Optional[float],
    interval: float,
    only_changes: bool,
    debug_sensors: bool,
    screen_ai: bool,
    ai_interval: float,
    heartbeat_seconds: float,
) -> int:
    activity.start_tracking(
        mock=False,
        screen_ai=screen_ai,
        screen_ai_interval_seconds=ai_interval,
    )
    _print_permission_hint()
    if screen_ai:
        print(
            "Screen AI: enabled. A screenshot is sent to Gemini at most every "
            f"{ai_interval:.0f}s. Screenshots are temporary and deleted immediately.\n"
        )

    print(
        "Legend: OK=FOCUSED, WARN=DISTRACTED, "
        "IDLE=inactive, AWAY=long inactive\n"
    )

    start = time.monotonic()
    last_printed_at = 0.0
    last_signature: Optional[tuple[Any, ...]] = None

    try:
        while True:
            snapshot = activity.current_state()
            status = activity.screen_ai_status() if screen_ai else {}
            signature = (
                snapshot.state,
                snapshot.active_app,
                snapshot.active_window,
                snapshot.active_url,
                int(snapshot.seconds_since_input),
                snapshot.window_switches_60s,
                getattr(snapshot, "state_source", None),
                getattr(snapshot, "ai_screen_state", None),
                status.get("inflight"),
                status.get("started_count"),
                status.get("succeeded_count"),
                status.get("failed_count"),
            )
            now_monotonic = time.monotonic()
            heartbeat_due = (
                only_changes
                and heartbeat_seconds > 0
                and now_monotonic - last_printed_at >= heartbeat_seconds
            )
            if not only_changes or signature != last_signature or heartbeat_due:
                print(_format_row(snapshot), flush=True)
                if screen_ai:
                    print(
                        "    screen_ai "
                        f"enabled={status.get('enabled')} "
                        f"auth={status.get('auth_mode')} "
                        f"inflight={status.get('inflight')} "
                        f"calls={status.get('started_count')}/"
                        f"{status.get('succeeded_count')}/"
                        f"{status.get('failed_count')} "
                        f"latest={status.get('latest_state')} "
                        f"reason={_short(status.get('latest_reason'), 50).strip()} "
                        f"err={_short(status.get('last_error'), 80).strip()}",
                        flush=True,
                    )
                if debug_sensors:
                    try:
                        app_name, title = activity._get_active_window()  # type: ignore[attr-defined]
                    except Exception as exc:  # pragma: no cover - diagnostic path
                        print(f"    raw_sensor_error={exc!r}", flush=True)
                    else:
                        print(
                            f"    raw_sensor app={app_name or '-'} "
                            f"title={_short(title, 70)}",
                            flush=True,
                        )
                last_signature = signature
                last_printed_at = now_monotonic

            if duration is not None and now_monotonic - start >= duration:
                break
            time.sleep(interval)
    finally:
        activity.stop_tracking()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe TerpPet activity tracking.")
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Seconds to run. Defaults to forever until Ctrl-C.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between rows. Defaults to 1.0.",
    )
    parser.add_argument(
        "--only-changes",
        action="store_true",
        help="Print only when key fields change.",
    )
    parser.add_argument(
        "--jsonish-once",
        action="store_true",
        help="Start tracking, print one snapshot dict, and exit.",
    )
    parser.add_argument(
        "--debug-sensors",
        action="store_true",
        help="Also print direct active-window sensor readings.",
    )
    parser.add_argument(
        "--screen-ai",
        action="store_true",
        help="Enable Gemini screenshot classification for ambiguous screens.",
    )
    parser.add_argument(
        "--ai-interval",
        type=float,
        default=10.0,
        help="Seconds between Gemini screenshot classifications (min 5, default 10).",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=5.0,
        help="With --only-changes, still print status this often (0 disables).",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda _signum, _frame: raise_keyboard_interrupt())
    _print_instructions()

    if args.jsonish_once:
        activity.start_tracking(
            mock=False,
            screen_ai=args.screen_ai,
            screen_ai_interval_seconds=args.ai_interval,
        )
        try:
            wait = max(1.0, args.interval)
            if args.screen_ai:
                wait = max(wait, min(12.0, args.ai_interval + 2.0))
            time.sleep(wait)
            _dump_jsonish(activity.current_state())
            if args.screen_ai:
                print(activity.screen_ai_status())
        finally:
            activity.stop_tracking()
        return 0

    try:
        return run(
            args.duration,
            args.interval,
            args.only_changes,
            args.debug_sensors,
            args.screen_ai,
            args.ai_interval,
            args.heartbeat_seconds,
        )
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


def raise_keyboard_interrupt() -> None:
    raise KeyboardInterrupt


if __name__ == "__main__":
    raise SystemExit(main())
