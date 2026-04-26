"""TerpPet — Screen & Activity tracking module (Person C).

Owns:
    * Active-window/title polling (cross-platform, Mac-first)
    * Keyboard / mouse idle tracking via pynput (no key logging)
    * Behavior classification: FOCUSED / DISTRACTED / IDLE / AWAY
    * Pomodoro engine (lives here because completion is tied to focus tracking)
    * ``--mock-activity`` mode that cycles scripted states for the demo

Public surface (consumed by ``app.state`` and ``app.main``):
    * ``start_tracking(mock: bool = False) -> None``
    * ``stop_tracking() -> None``
    * ``current_state() -> ActivitySnapshot``
    * ``pomodoro_start(minutes: int) -> PomodoroState``
    * ``pomodoro_stop() -> PomodoroState``
    * ``pomodoro_status() -> PomodoroState``
    * ``drain_pomodoro_events() -> list[PomodoroCompletedEvent]``

Hard rules:
    * Never log key contents, only timestamps of events.
    * The polling loop never raises; sensor failures degrade quietly.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from queue import Empty, Queue
from typing import Any, Deque, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

BehaviorState = Literal["FOCUSED", "DISTRACTED", "IDLE", "AWAY"]


@dataclass(frozen=True)
class ActivitySnapshot:
    """One tick of derived activity signal. Frozen so callers can't mutate it."""

    state: BehaviorState
    active_app: Optional[str]
    active_window: Optional[str]
    active_url: Optional[str]
    seconds_since_input: float
    focus_seconds_today: float
    distraction_streak_seconds: float
    window_switches_60s: int
    timestamp: datetime
    mock: bool
    ai_screen_state: Optional[BehaviorState] = None
    ai_screen_reason: Optional[str] = None
    ai_screen_checked_at: Optional[datetime] = None
    ai_screen_confidence: Optional[float] = None
    state_source: str = "rules"

    @property
    def distraction_streak(self) -> int:
        """Compatibility field expected by the state aggregator."""
        return int(self.distraction_streak_seconds)


@dataclass(frozen=True)
class PomodoroState:
    running: bool
    minutes: int
    started_at: Optional[datetime]
    ends_at: Optional[datetime]
    seconds_remaining: float


@dataclass(frozen=True)
class PomodoroCompletedEvent:
    completed_at: datetime
    minutes: int


@dataclass(frozen=True)
class ScreenAIReading:
    state: BehaviorState
    reason: str
    confidence: float
    checked_at: datetime
    source_app: Optional[str]
    source_window: Optional[str]


# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

POLL_INTERVAL_S: float = 1.0
IDLE_THRESHOLD_S: float = 30.0
AWAY_THRESHOLD_S: float = 120.0
SWITCH_WINDOW_S: float = 60.0
POMODORO_MIN_MINUTES: int = 1
POMODORO_MAX_MINUTES: int = 180
SCREEN_AI_DEFAULT_INTERVAL_S: float = 10.0
SCREEN_AI_MAX_STALENESS_S: float = 14.0
SCREEN_AI_SCREENSHOT_TIMEOUT_S: float = 3.0
SCREEN_AI_MODEL_DEFAULT: str = "gemini-2.5-flash"

# Substring patterns matched against ``app + title + url`` (lowercased).
DISTRACTION_PATTERNS: Tuple[str, ...] = (
    "youtube", "youtu.be",
    "twitter", "x.com",
    "reddit", "instagram",
    "tiktok", "facebook",
    "netflix", "twitch",
    "9gag", "pinterest", "tumblr",
    "disney+", "hulu",
)

FOCUS_PATTERNS: Tuple[str, ...] = (
    "code", "cursor", "intellij", "pycharm", "webstorm", "datagrip",
    "xcode", "sublime", "vim", "neovim", "emacs",
    "terminal", "iterm", "warp", "hyper",
    "notion", "obsidian", "bear", "logseq",
    "docs.google", "overleaf", "onenote",
    "github.com", "gitlab.com", "stackoverflow",
    "chatgpt", "claude.ai", "gemini.google",
    "umd.edu", "canvas", "kaltura", "elms",
    "figma", "linear",
)

# Domains we look for in window titles for the URL hint.
_URL_DOMAINS: Tuple[str, ...] = (
    "youtube.com", "youtu.be",
    "x.com", "twitter.com",
    "reddit.com", "instagram.com", "tiktok.com",
    "facebook.com", "netflix.com", "twitch.tv",
    "9gag.com", "pinterest.com", "tumblr.com",
    "github.com", "gitlab.com", "stackoverflow.com",
    "docs.google.com", "drive.google.com",
    "chatgpt.com", "claude.ai", "gemini.google.com",
    "umd.edu", "canvas.umd.edu",
    "wikipedia.org",
)

_URL_REGEX = re.compile(
    r"(" + r"|".join(re.escape(d) for d in _URL_DOMAINS) + r")",
    re.IGNORECASE,
)

# Mock cycle for the --mock-activity demo: (state, duration_seconds).
_MOCK_CYCLE: Tuple[Tuple[BehaviorState, float], ...] = (
    ("FOCUSED", 8.0),
    ("DISTRACTED", 6.0),
    ("IDLE", 4.0),
    ("AWAY", 4.0),
)


# ---------------------------------------------------------------------------
# Active-window adapter — defensive imports, never raises into the polling loop
# ---------------------------------------------------------------------------


def _get_active_window_macos() -> Tuple[Optional[str], Optional[str]]:
    """Return (app_name, window_title) on macOS via Quartz + NSWorkspace.

    Window titles require Screen Recording permission on modern macOS; if that
    is not granted we still try to return the app name and ``None`` for the
    title. Quartz's front-to-back window order is treated as the primary app
    signal because NSWorkspace can report Cursor when called from an integrated
    terminal even while another app is visually frontmost.
    """
    try:
        from AppKit import NSWorkspace  # type: ignore
        import Quartz  # type: ignore
    except Exception as exc:
        logger.debug("macOS active-window deps unavailable: %s", exc)
        return None, None

    app_name: Optional[str] = None
    title: Optional[str] = None
    front_pid: int = -1

    quartz_app: Optional[str] = None
    quartz_title: Optional[str] = None
    quartz_pid: int = -1

    try:
        options = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
        for w in windows:
            try:
                if int(w.get("kCGWindowLayer", 1)) != 0:
                    continue
                owner = w.get("kCGWindowOwnerName")
                # Ignore invisible/system windows that can sit before the real app.
                bounds = w.get("kCGWindowBounds") or {}
                if float(bounds.get("Width", 0)) <= 1 or float(bounds.get("Height", 0)) <= 1:
                    continue
                if owner:
                    quartz_app = str(owner)
                    quartz_pid = int(w.get("kCGWindowOwnerPID", -1))
                    name = w.get("kCGWindowName")
                    quartz_title = str(name) if name else None
                    break
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Quartz top-window lookup failed: %s", exc)

    try:
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is not None:
            localized = front.localizedName()
            app_name = str(localized) if localized else None
            front_pid = int(front.processIdentifier())
    except Exception as exc:
        logger.debug("NSWorkspace frontmost lookup failed: %s", exc)

    # Prefer the actual topmost window owner when Quartz and NSWorkspace differ.
    if quartz_app:
        if app_name and app_name != quartz_app:
            logger.debug(
                "NSWorkspace frontmost app %r differed from Quartz top window %r; using Quartz",
                app_name,
                quartz_app,
            )
        app_name = quartz_app
        title = quartz_title
        front_pid = quartz_pid

    try:
        options = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
        for w in windows:
            try:
                if int(w.get("kCGWindowLayer", 1)) != 0:
                    continue
                if front_pid >= 0 and int(w.get("kCGWindowOwnerPID", -1)) != front_pid:
                    continue
                name = w.get("kCGWindowName")
                if name:
                    title = str(name)
                    break
            except Exception:
                continue
        if app_name is None:
            for w in windows:
                try:
                    if front_pid >= 0 and int(w.get("kCGWindowOwnerPID", -1)) == front_pid:
                        owner = w.get("kCGWindowOwnerName")
                        if owner:
                            app_name = str(owner)
                            break
                except Exception:
                    continue
    except Exception as exc:
        logger.debug("Quartz CGWindowListCopyWindowInfo failed: %s", exc)

    if app_name is None:
        app_name = _get_frontmost_app_macos_applescript()

    return app_name, title


def _get_frontmost_app_macos_applescript() -> Optional[str]:
    """Last-resort macOS frontmost app name via System Events.

    This may require Accessibility permission and is intentionally only a
    fallback, not the hot path.
    """
    try:
        proc = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of first application process whose frontmost is true',
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.75,
        )
    except Exception as exc:
        logger.debug("AppleScript frontmost lookup failed: %s", exc)
        return None
    if proc.returncode != 0:
        logger.debug("AppleScript frontmost lookup returned %s: %s", proc.returncode, proc.stderr)
        return None
    app = proc.stdout.strip()
    return app or None


def _get_active_window_windows() -> Tuple[Optional[str], Optional[str]]:
    """Return (app_name, window_title) on Windows via pygetwindow + pywin32."""
    app_name: Optional[str] = None
    title: Optional[str] = None

    try:
        import pygetwindow  # type: ignore

        win = pygetwindow.getActiveWindow()
        if win is not None and getattr(win, "title", None):
            title = str(win.title)
    except Exception as exc:
        logger.debug("pygetwindow lookup failed: %s", exc)

    try:
        import psutil  # type: ignore
        import win32gui  # type: ignore
        import win32process  # type: ignore

        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid:
                app_name = psutil.Process(int(pid)).name()
            if title is None:
                txt = win32gui.GetWindowText(hwnd)
                if txt:
                    title = str(txt)
    except Exception as exc:
        logger.debug("win32 active-process lookup failed: %s", exc)

    return app_name, title


def _get_active_window() -> Tuple[Optional[str], Optional[str]]:
    """Return (app_name, window_title). Either component may be None."""
    if sys.platform == "darwin":
        return _get_active_window_macos()
    if sys.platform == "win32":
        return _get_active_window_windows()
    return None, None


def _extract_url_hint(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    m = _URL_REGEX.search(title)
    if not m:
        return None
    return m.group(1).lower()


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _local_today() -> date:
    return datetime.now().astimezone().date()


def _empty_pomodoro() -> PomodoroState:
    return PomodoroState(
        running=False,
        minutes=0,
        started_at=None,
        ends_at=None,
        seconds_remaining=0.0,
    )


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using %.1f", name, raw, default)
        return default
    return max(minimum, value)


def _load_env_for_ai() -> None:
    try:
        from dotenv import find_dotenv, load_dotenv  # type: ignore
    except Exception:
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


def _genai_use_vertex_ai() -> bool:
    _load_env_for_ai()
    return (
        _env_truthy("GOOGLE_GENAI_USE_VERTEXAI")
        or _env_truthy("GEMINI_USE_ADC")
        or _env_truthy("TERPPET_USE_ADC")
    )


def _genai_vertex_project() -> Optional[str]:
    _load_env_for_ai()
    return (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GOOGLE_PROJECT_ID")
        or os.getenv("GCLOUD_PROJECT")
    )


def _genai_vertex_location() -> str:
    _load_env_for_ai()
    return (
        os.getenv("GOOGLE_CLOUD_LOCATION")
        or os.getenv("GOOGLE_CLOUD_REGION")
        or os.getenv("GEMINI_LOCATION")
        or "us-central1"
    )


def _screen_ai_credentials_configured() -> bool:
    _load_env_for_ai()
    return _genai_use_vertex_ai() and bool(_genai_vertex_project())


def _macos_accessibility_trusted() -> bool:
    """Return False when macOS will reject keyboard/mouse event monitoring."""
    if sys.platform != "darwin":
        return True
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore

        return bool(AXIsProcessTrusted())
    except Exception as exc:
        logger.debug("Could not check macOS Accessibility trust: %s", exc)
        # If the trust API itself is unavailable, let pynput attempt startup so
        # non-standard environments still get a chance to work.
        return True


def _build_genai_client() -> Tuple[Any, str]:
    _load_env_for_ai()
    from google import genai  # type: ignore

    if not _genai_use_vertex_ai():
        raise RuntimeError(
            "ADC/Vertex AI is required. Set GOOGLE_GENAI_USE_VERTEXAI=true."
        )

    project = _genai_vertex_project()
    if not project:
        raise RuntimeError(
            "ADC/Vertex AI is enabled but GOOGLE_CLOUD_PROJECT is not set"
        )
    location = _genai_vertex_location()
    return (
        genai.Client(vertexai=True, project=project, location=location),
        f"adc:{project}/{location}",
    )


def capture_screen_jpeg_bytes() -> bytes:
    """Capture the current macOS screen as JPEG bytes and delete the temp file.

    We use the system `screencapture` binary to avoid introducing another
    dependency. The file is temporary and removed immediately after reading.
    """
    if sys.platform != "darwin":
        raise RuntimeError("screen AI capture is currently implemented for macOS only")

    tmp_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_name = tmp.name
        proc = subprocess.run(
            ["screencapture", "-x", "-t", "jpg", tmp_name],
            check=False,
            capture_output=True,
            timeout=SCREEN_AI_SCREENSHOT_TIMEOUT_S,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"screencapture failed ({proc.returncode}): {stderr}")
        with open(tmp_name, "rb") as fh:
            data = fh.read()
        if not data:
            raise RuntimeError("screencapture produced an empty image")
        return data
    finally:
        if tmp_name:
            try:
                os.remove(tmp_name)
            except OSError:
                pass


def _parse_ai_behavior_state(value: object) -> Optional[BehaviorState]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if normalized in {"FOCUSED", "DISTRACTED", "IDLE", "AWAY"}:
        return normalized  # type: ignore[return-value]
    return None


def _classify_screen_with_gemini(
    image_bytes: bytes,
    app: Optional[str],
    title: Optional[str],
) -> ScreenAIReading:
    """Ask Gemini whether the visible screen looks focused or distracting."""
    from google.genai import types  # type: ignore

    client, _auth_mode = _build_genai_client()
    model = os.getenv("GEMINI_SCREEN_MODEL") or os.getenv("GEMINI_MODEL") or SCREEN_AI_MODEL_DEFAULT
    prompt = (
        "You are the focus classifier for TerpPet, an always-on study pet.\n"
        "Look at this screenshot and decide whether the student appears focused "
        "on productive study/work or distracted.\n\n"
        "Return ONLY JSON with this exact shape:\n"
        '{"state":"FOCUSED|DISTRACTED|IDLE|AWAY",'
        '"reason":"short reason under 80 chars","confidence":0.0}\n\n'
        "Rules:\n"
        "- FOCUSED: coding, docs, notes, textbooks, UMD/Canvas, research, IDEs, terminal.\n"
        "- DISTRACTED: YouTube/shorts, social feeds, memes, shopping, streaming, games.\n"
        "- Do not infer IDLE/AWAY unless the screen is locked or blank; input tracking handles that.\n"
        "- Do not quote private screen text. Keep reason high level.\n\n"
        f"Known active app: {app or 'unknown'}\n"
        f"Known window title: {title or 'unknown'}\n"
    )
    resp = client.models.generate_content(
        model=model,
        contents=[
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        ],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    text = getattr(resp, "text", None)
    if not text:
        raise RuntimeError("Gemini returned no text")
    parsed = json.loads(text)
    state = _parse_ai_behavior_state(parsed.get("state"))
    if state is None:
        raise RuntimeError(f"Gemini returned invalid state: {parsed!r}")
    reason = str(parsed.get("reason") or "AI screen classification").strip()
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return ScreenAIReading(
        state=state,
        reason=reason[:160],
        confidence=max(0.0, min(1.0, confidence)),
        checked_at=_utcnow(),
        source_app=app,
        source_window=title,
    )


class ActivityTracker:
    """Owns the 1 Hz polling loop, the input listeners, and the Pomodoro timer.

    The tracker is intentionally stateful and singleton-friendly: ``state.py``
    consumes its public methods as if they were module-level functions (see the
    delegating wrappers at the bottom of this file).
    """

    def __init__(
        self,
        mock: bool = False,
        screen_ai: Optional[bool] = None,
        screen_ai_interval_seconds: Optional[float] = None,
    ) -> None:
        self._mock = mock
        self._screen_ai_enabled = (
            _env_truthy("TERPPET_SCREEN_AI", default=False)
            if screen_ai is None
            else screen_ai
        )
        self._screen_ai_interval_seconds = (
            _env_float(
                "TERPPET_SCREEN_AI_INTERVAL_SECONDS",
                SCREEN_AI_DEFAULT_INTERVAL_S,
                minimum=5.0,
            )
            if screen_ai_interval_seconds is None
            else max(5.0, float(screen_ai_interval_seconds))
        )

        self._snapshot_lock = threading.Lock()
        self._input_lock = threading.Lock()
        self._pomodoro_lock = threading.Lock()
        self._screen_ai_lock = threading.Lock()

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        now = _utcnow()
        self._last_input_at: datetime = now
        self._snapshot: ActivitySnapshot = ActivitySnapshot(
            state="IDLE",
            active_app=None,
            active_window=None,
            active_url=None,
            seconds_since_input=0.0,
            focus_seconds_today=0.0,
            distraction_streak_seconds=0.0,
            window_switches_60s=0,
            timestamp=now,
            mock=mock,
        )

        self._focus_seconds_today: float = 0.0
        self._distraction_streak_seconds: float = 0.0
        self._focus_day: date = _local_today()

        self._switch_history: Deque[datetime] = deque()
        self._last_window_key: Optional[str] = None
        self._last_tick_at: Optional[datetime] = None

        self._pomodoro: PomodoroState = _empty_pomodoro()
        self._events: "Queue[PomodoroCompletedEvent]" = Queue()

        self._mock_started_at: Optional[datetime] = None

        self._kbd_listener = None
        self._mouse_listener = None
        self._listeners_active: bool = False

        self._screen_ai_latest: Optional[ScreenAIReading] = None
        self._screen_ai_inflight = False
        self._screen_ai_next_due_monotonic = 0.0
        self._screen_ai_last_error: Optional[str] = None
        self._screen_ai_started_count = 0
        self._screen_ai_succeeded_count = 0
        self._screen_ai_failed_count = 0
        self._screen_ai_last_started_at: Optional[datetime] = None
        self._screen_ai_last_completed_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        if not self._mock:
            self._start_input_listeners()
        self._mock_started_at = _utcnow() if self._mock else None
        self._thread = threading.Thread(
            target=self._run, name="terppet-activity", daemon=True
        )
        self._thread.start()
        logger.info(
            "ActivityTracker started (mock=%s, listeners=%s, screen_ai=%s, platform=%s)",
            self._mock,
            self._listeners_active,
            self._screen_ai_enabled,
            sys.platform,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=POLL_INTERVAL_S * 2)
            self._thread = None
        self._stop_input_listeners()
        logger.info("ActivityTracker stopped")

    def _start_input_listeners(self) -> None:
        if not _macos_accessibility_trusted():
            logger.warning(
                "macOS Accessibility permission is not granted; IDLE/AWAY "
                "input tracking is disabled. Grant Accessibility to the "
                "terminal app running the backend, then restart."
            )
            return

        try:
            from pynput import keyboard, mouse  # type: ignore
        except Exception as exc:
            logger.warning(
                "pynput unavailable; treating user as always-active: %s", exc
            )
            return

        def _bump(*_args, **_kwargs) -> None:
            with self._input_lock:
                self._last_input_at = _utcnow()

        try:
            self._kbd_listener = keyboard.Listener(on_press=_bump, on_release=_bump)
            self._mouse_listener = mouse.Listener(
                on_move=_bump, on_click=_bump, on_scroll=_bump
            )
            self._kbd_listener.daemon = True
            self._mouse_listener.daemon = True
            self._kbd_listener.start()
            self._mouse_listener.start()
            self._listeners_active = True
        except Exception as exc:
            logger.warning(
                "Could not start pynput listeners (Accessibility permission?): %s. "
                "Falling back to assuming user is active.",
                exc,
            )
            self._kbd_listener = None
            self._mouse_listener = None
            self._listeners_active = False

    def _stop_input_listeners(self) -> None:
        for listener in (self._kbd_listener, self._mouse_listener):
            if listener is None:
                continue
            try:
                listener.stop()
            except Exception:
                pass
        self._kbd_listener = None
        self._mouse_listener = None
        self._listeners_active = False

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop_event.is_set():
            tick_started = time.monotonic()
            try:
                self._tick()
            except Exception:
                logger.exception("Activity tick failed; continuing")
            elapsed = time.monotonic() - tick_started
            self._stop_event.wait(max(0.0, POLL_INTERVAL_S - elapsed))

    def _tick(self) -> None:
        now = _utcnow()
        last_tick = self._last_tick_at or now
        dt = max(0.0, (now - last_tick).total_seconds())
        self._last_tick_at = now

        today = _local_today()
        if today != self._focus_day:
            self._focus_day = today
            self._focus_seconds_today = 0.0

        if self._mock:
            state, app, title, url, seconds_since_input, state_source = self._mock_tick(now)
        else:
            state, app, title, url, seconds_since_input, state_source = self._live_tick(now)
        ai_reading = self._get_applicable_screen_ai(now, app)

        if state == "FOCUSED":
            self._focus_seconds_today += dt
        if state == "DISTRACTED":
            self._distraction_streak_seconds += dt
        else:
            self._distraction_streak_seconds = 0.0

        self._poll_pomodoro(now)

        snapshot = ActivitySnapshot(
            state=state,
            active_app=app,
            active_window=title,
            active_url=url,
            seconds_since_input=seconds_since_input,
            focus_seconds_today=self._focus_seconds_today,
            distraction_streak_seconds=self._distraction_streak_seconds,
            window_switches_60s=len(self._switch_history),
            timestamp=now,
            mock=self._mock,
            ai_screen_state=ai_reading.state if ai_reading is not None else None,
            ai_screen_reason=ai_reading.reason if ai_reading is not None else None,
            ai_screen_checked_at=(
                ai_reading.checked_at if ai_reading is not None else None
            ),
            ai_screen_confidence=(
                ai_reading.confidence if ai_reading is not None else None
            ),
            state_source=state_source,
        )
        with self._snapshot_lock:
            self._snapshot = snapshot

    def _live_tick(
        self, now: datetime
    ) -> Tuple[BehaviorState, Optional[str], Optional[str], Optional[str], float, str]:
        app, title = _get_active_window()
        url = _extract_url_hint(title)

        key = f"{app or ''}|{title or ''}"
        if key != (self._last_window_key or "") and (app or title):
            self._switch_history.append(now)
            self._last_window_key = key
        cutoff = now - timedelta(seconds=SWITCH_WINDOW_S)
        while self._switch_history and self._switch_history[0] < cutoff:
            self._switch_history.popleft()

        with self._input_lock:
            seconds_since_input = max(0.0, (now - self._last_input_at).total_seconds())

        # When pynput could not start (no Accessibility perms), pretend the
        # user is active so the demo keeps working without false IDLE/AWAY.
        if not self._listeners_active:
            seconds_since_input = 0.0

        state = self._classify(app, title, url, seconds_since_input)
        state_source = "rules"

        # Screen AI is a fallback for exactly the case macOS often creates:
        # app/title are unavailable, so the rule classifier has no evidence and
        # says IDLE. Still sample the screenshot on the configured cadence.
        if self._screen_ai_enabled and seconds_since_input < AWAY_THRESHOLD_S:
            self._maybe_start_screen_ai_check(app, title)

        ai_state = self._get_applicable_screen_ai(now, app)
        if ai_state is not None and state != "AWAY":
            state = ai_state.state
            state_source = "screen_ai"
        return state, app, title, url, seconds_since_input, state_source

    def _classify(
        self,
        app: Optional[str],
        title: Optional[str],
        url: Optional[str],
        seconds_since_input: float,
    ) -> BehaviorState:
        if seconds_since_input >= AWAY_THRESHOLD_S:
            return "AWAY"
        if seconds_since_input >= IDLE_THRESHOLD_S:
            return "IDLE"

        haystack = " ".join(filter(None, (app, title, url))).lower()
        if any(p in haystack for p in DISTRACTION_PATTERNS):
            return "DISTRACTED"
        if any(p in haystack for p in FOCUS_PATTERNS):
            return "FOCUSED"
        if haystack.strip():
            return "FOCUSED"
        return "IDLE"

    def _maybe_start_screen_ai_check(
        self,
        app: Optional[str],
        title: Optional[str],
    ) -> None:
        if self._mock or not self._screen_ai_enabled:
            return
        now_monotonic = time.monotonic()
        with self._screen_ai_lock:
            if self._screen_ai_inflight:
                return
            if now_monotonic < self._screen_ai_next_due_monotonic:
                return
            self._screen_ai_inflight = True
            self._screen_ai_next_due_monotonic = (
                now_monotonic + self._screen_ai_interval_seconds
            )
            self._screen_ai_started_count += 1
            self._screen_ai_last_started_at = _utcnow()

        worker = threading.Thread(
            target=self._run_screen_ai_check,
            args=(app, title),
            name="terppet-screen-ai",
            daemon=True,
        )
        worker.start()

    def _run_screen_ai_check(
        self,
        app: Optional[str],
        title: Optional[str],
    ) -> None:
        try:
            if not _screen_ai_credentials_configured():
                raise RuntimeError(
                    "ADC/Vertex AI is required. Set GOOGLE_GENAI_USE_VERTEXAI=true "
                    "and GOOGLE_CLOUD_PROJECT."
                )
            image_bytes = capture_screen_jpeg_bytes()
            reading = _classify_screen_with_gemini(image_bytes, app, title)
            with self._screen_ai_lock:
                self._screen_ai_latest = reading
                self._screen_ai_last_error = None
                self._screen_ai_succeeded_count += 1
                self._screen_ai_last_completed_at = reading.checked_at
        except Exception as exc:
            with self._screen_ai_lock:
                self._screen_ai_last_error = str(exc)
                self._screen_ai_failed_count += 1
                self._screen_ai_last_completed_at = _utcnow()
            logger.info("Screen AI classification skipped/failed: %s", exc)
        finally:
            with self._screen_ai_lock:
                self._screen_ai_inflight = False

    def _get_applicable_screen_ai(
        self,
        now: datetime,
        app: Optional[str],
    ) -> Optional[ScreenAIReading]:
        if not self._screen_ai_enabled:
            return None
        with self._screen_ai_lock:
            reading = self._screen_ai_latest
        if reading is None:
            return None
        age = (now - reading.checked_at).total_seconds()
        if age < 0 or age > SCREEN_AI_MAX_STALENESS_S:
            return None
        if reading.source_app and app and reading.source_app != app:
            return None
        return reading

    def screen_ai_status(self) -> dict[str, object]:
        with self._screen_ai_lock:
            latest = self._screen_ai_latest
            return {
                "enabled": self._screen_ai_enabled,
                "interval_seconds": self._screen_ai_interval_seconds,
                "inflight": self._screen_ai_inflight,
                "last_error": self._screen_ai_last_error,
                "latest_state": latest.state if latest else None,
                "latest_reason": latest.reason if latest else None,
                "latest_confidence": latest.confidence if latest else None,
                "latest_checked_at": latest.checked_at if latest else None,
                "started_count": self._screen_ai_started_count,
                "succeeded_count": self._screen_ai_succeeded_count,
                "failed_count": self._screen_ai_failed_count,
                "last_started_at": self._screen_ai_last_started_at,
                "last_completed_at": self._screen_ai_last_completed_at,
                "auth_mode": (
                    "adc"
                    if _genai_use_vertex_ai() and _genai_vertex_project()
                    else "none"
                ),
            }

    def _mock_tick(
        self, now: datetime
    ) -> Tuple[BehaviorState, Optional[str], Optional[str], Optional[str], float, str]:
        if self._mock_started_at is None:
            self._mock_started_at = now
        cycle_total = sum(d for _, d in _MOCK_CYCLE)
        elapsed = (now - self._mock_started_at).total_seconds() % cycle_total

        running = 0.0
        chosen: BehaviorState = _MOCK_CYCLE[0][0]
        for state, dur in _MOCK_CYCLE:
            running += dur
            if elapsed < running:
                chosen = state
                break

        if chosen == "AWAY":
            seconds_since_input = AWAY_THRESHOLD_S + 5.0
        elif chosen == "IDLE":
            seconds_since_input = IDLE_THRESHOLD_S + 5.0
        else:
            seconds_since_input = 0.5

        scripted_app = {
            "FOCUSED": "Cursor",
            "DISTRACTED": "Google Chrome",
            "IDLE": None,
            "AWAY": None,
        }[chosen]
        scripted_title = {
            "FOCUSED": "activity.py — TerpPet — Cursor",
            "DISTRACTED": "TikTok - Make Your Day",
            "IDLE": None,
            "AWAY": None,
        }[chosen]
        url = _extract_url_hint(scripted_title)

        # Maintain switch history so the snapshot still shows realistic counts.
        if chosen != self._last_window_key:
            self._switch_history.append(now)
            self._last_window_key = chosen
        cutoff = now - timedelta(seconds=SWITCH_WINDOW_S)
        while self._switch_history and self._switch_history[0] < cutoff:
            self._switch_history.popleft()

        return chosen, scripted_app, scripted_title, url, seconds_since_input, "mock"

    # ------------------------------------------------------------------
    # Pomodoro
    # ------------------------------------------------------------------
    def pomodoro_start(self, minutes: int) -> PomodoroState:
        if not isinstance(minutes, int) or isinstance(minutes, bool):
            raise ValueError("minutes must be an int")
        if not (POMODORO_MIN_MINUTES <= minutes <= POMODORO_MAX_MINUTES):
            raise ValueError(
                f"minutes must be in [{POMODORO_MIN_MINUTES},{POMODORO_MAX_MINUTES}]"
            )
        now = _utcnow()
        ends = now + timedelta(minutes=minutes)
        with self._pomodoro_lock:
            self._pomodoro = PomodoroState(
                running=True,
                minutes=minutes,
                started_at=now,
                ends_at=ends,
                seconds_remaining=float(minutes) * 60.0,
            )
            return self._pomodoro

    def pomodoro_stop(self) -> PomodoroState:
        with self._pomodoro_lock:
            self._pomodoro = _empty_pomodoro()
            return self._pomodoro

    def pomodoro_status(self) -> PomodoroState:
        # Opportunistic completion check so callers still see completion events
        # even when the polling thread is paused (e.g. unit tests).
        self._poll_pomodoro(_utcnow())
        with self._pomodoro_lock:
            current = self._pomodoro
            if current.running and current.ends_at is not None:
                remaining = max(
                    0.0, (current.ends_at - _utcnow()).total_seconds()
                )
                return replace(current, seconds_remaining=remaining)
            return current

    def _poll_pomodoro(self, now: datetime) -> None:
        with self._pomodoro_lock:
            current = self._pomodoro
            if not current.running or current.ends_at is None:
                return
            if now >= current.ends_at:
                completed_minutes = current.minutes
                self._pomodoro = _empty_pomodoro()
                self._events.put(
                    PomodoroCompletedEvent(
                        completed_at=now, minutes=completed_minutes
                    )
                )
                logger.info("Pomodoro completed (%d min)", completed_minutes)
            else:
                remaining = max(0.0, (current.ends_at - now).total_seconds())
                self._pomodoro = replace(current, seconds_remaining=remaining)

    def drain_pomodoro_events(self) -> List[PomodoroCompletedEvent]:
        events: List[PomodoroCompletedEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                break
        return events

    # ------------------------------------------------------------------
    # Snapshot accessor
    # ------------------------------------------------------------------
    def current(self) -> ActivitySnapshot:
        with self._snapshot_lock:
            return self._snapshot


# ---------------------------------------------------------------------------
# Module-level singleton + public delegating API
# ---------------------------------------------------------------------------

_tracker: Optional[ActivityTracker] = None
_singleton_lock = threading.Lock()


def _get_or_create(
    mock: bool = False,
    screen_ai: Optional[bool] = None,
    screen_ai_interval_seconds: Optional[float] = None,
) -> ActivityTracker:
    global _tracker
    with _singleton_lock:
        if _tracker is None:
            _tracker = ActivityTracker(
                mock=mock,
                screen_ai=screen_ai,
                screen_ai_interval_seconds=screen_ai_interval_seconds,
            )
    return _tracker


def start_tracking(
    mock: bool = False,
    screen_ai: Optional[bool] = None,
    screen_ai_interval_seconds: Optional[float] = None,
) -> None:
    """Start the activity tracker. Idempotent.

    The first call decides ``mock`` / screen AI options; subsequent calls re-use
    the existing tracker. Call :func:`stop_tracking` first to swap modes.
    """
    tracker = _get_or_create(
        mock=mock,
        screen_ai=screen_ai,
        screen_ai_interval_seconds=screen_ai_interval_seconds,
    )
    tracker.start()


def stop_tracking() -> None:
    """Stop the activity tracker and tear down listeners."""
    global _tracker
    with _singleton_lock:
        existing = _tracker
        _tracker = None
    if existing is not None:
        existing.stop()


def current_state() -> ActivitySnapshot:
    """Return the most recently computed ActivitySnapshot.

    Always safe to call: if the tracker has not been started, returns an
    idle placeholder snapshot rather than raising.
    """
    tracker = _tracker
    if tracker is None:
        now = _utcnow()
        return ActivitySnapshot(
            state="IDLE",
            active_app=None,
            active_window=None,
            active_url=None,
            seconds_since_input=0.0,
            focus_seconds_today=0.0,
            distraction_streak_seconds=0.0,
            window_switches_60s=0,
            timestamp=now,
            mock=False,
        )
    return tracker.current()


def pomodoro_start(minutes: int) -> PomodoroState:
    return _get_or_create().pomodoro_start(minutes)


def pomodoro_stop() -> PomodoroState:
    return _get_or_create().pomodoro_stop()


def pomodoro_status() -> PomodoroState:
    return _get_or_create().pomodoro_status()


def start_pomodoro(minutes: int) -> Tuple[datetime, datetime]:
    """Compatibility wrapper used by main.py routes."""
    state = pomodoro_start(minutes)
    if state.started_at is None or state.ends_at is None:
        raise RuntimeError("Pomodoro failed to start")
    return state.started_at, state.ends_at


def stop_pomodoro() -> PomodoroState:
    """Compatibility wrapper used by main.py routes."""
    return pomodoro_stop()


def pomodoro_state() -> object:
    """Compatibility wrapper returning the wire schema when available."""
    state = pomodoro_status()
    try:
        from .schemas import PomodoroState as WirePomodoroState

        return WirePomodoroState(
            running=state.running,
            ends_at=state.ends_at,
            minutes=state.minutes or 25,
        )
    except Exception:
        return state


def drain_pomodoro_events() -> List[PomodoroCompletedEvent]:
    tracker = _tracker
    if tracker is None:
        return []
    return tracker.drain_pomodoro_events()


def drain_completed_pomodoros() -> int:
    """Compatibility wrapper used by state.py."""
    return len(drain_pomodoro_events())


def screen_ai_status() -> dict[str, object]:
    tracker = _tracker
    if tracker is None:
        return {
            "enabled": False,
            "interval_seconds": SCREEN_AI_DEFAULT_INTERVAL_S,
            "inflight": False,
            "last_error": None,
            "latest_state": None,
            "latest_reason": None,
            "latest_confidence": None,
            "latest_checked_at": None,
            "started_count": 0,
            "succeeded_count": 0,
            "failed_count": 0,
            "last_started_at": None,
            "last_completed_at": None,
            "auth_mode": "none",
        }
    return tracker.screen_ai_status()


# ---------------------------------------------------------------------------
# Self-test (``python -m app.activity [--mock-activity]``)
# ---------------------------------------------------------------------------


def _selftest(mock: bool, duration: float, demo_pomodoro_seconds: float = 5.0) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    start_tracking(mock=mock)
    try:
        # Force a short Pomodoro for the self-test by directly seeding the
        # tracker (the public API floors at 1 minute, which is too long here).
        tracker = _tracker
        if tracker is not None:
            now = _utcnow()
            with tracker._pomodoro_lock:  # noqa: SLF001 — self-test only
                tracker._pomodoro = PomodoroState(  # noqa: SLF001
                    running=True,
                    minutes=1,
                    started_at=now,
                    ends_at=now + timedelta(seconds=demo_pomodoro_seconds),
                    seconds_remaining=demo_pomodoro_seconds,
                )

        end = time.monotonic() + duration
        while time.monotonic() < end:
            snap = current_state()
            pomo = pomodoro_status()
            evts = drain_pomodoro_events()
            print(
                f"[{snap.timestamp.isoformat(timespec='seconds')}] "
                f"state={snap.state:<13} "
                f"app={(snap.active_app or '-')[:18]:<18} "
                f"url={(snap.active_url or '-')[:14]:<14} "
                f"idle={snap.seconds_since_input:5.1f}s "
                f"focus_today={snap.focus_seconds_today:5.1f}s "
                f"streak={snap.distraction_streak_seconds:5.1f}s "
                f"switches60s={snap.window_switches_60s} "
                f"pomo={'RUN' if pomo.running else 'OFF'} "
                f"remaining={pomo.seconds_remaining:5.1f}s "
                f"events={len(evts)}"
            )
            for e in evts:
                print(
                    f"  -> POMODORO COMPLETED at {e.completed_at.isoformat()} "
                    f"({e.minutes} min)"
                )
            time.sleep(1.0)
    finally:
        stop_tracking()
    return 0


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="TerpPet activity tracker self-test"
    )
    parser.add_argument(
        "--mock-activity",
        action="store_true",
        help="Cycle scripted states without using sensors",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=20.0,
        help="Seconds to run the self-test (default 20)",
    )
    args = parser.parse_args()
    return _selftest(mock=args.mock_activity, duration=args.duration)


if __name__ == "__main__":
    raise SystemExit(_main())
