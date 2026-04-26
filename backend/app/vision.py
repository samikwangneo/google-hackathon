"""Webcam-based presence + attention detection.

Person B owns this module. Public API:
    start()  -> begin background capture loop
    stop()   -> stop loop and release the camera
    current_presence() -> PresenceSnapshot

Never persists frames. Only the derived signal lives anywhere.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Literal

import cv2
import numpy as np

log = logging.getLogger(__name__)

PresenceState = Literal["PRESENT", "ABSENT", "LOOKING_AWAY"]

try:
    import mediapipe as mp  # type: ignore
except ImportError:
    mp = None  # type: ignore

try:
    from ultralytics import YOLO  # type: ignore
except ImportError:
    YOLO = None  # type: ignore


@dataclass(frozen=True)
class PresenceSnapshot:
    state: PresenceState
    confidence: float
    backend: str       # "mediapipe" | "haar" | "none"
    fps: float
    timestamp: float
    phone_present: bool = False  # orthogonal signal from YOLO; False if detection disabled


_TARGET_FPS = 5
_BUFFER_SIZE = 5
_GAZE_YAW_THRESHOLD = 0.30  # normalized horizontal offset of nose vs face center
_CAMERA_INDEX_ENV = "VISION_CAMERA_INDEX"
_DEFAULT_MAC_CAMERA_INDEX = 1

_PHONE_COCO_CLASS = 67          # "cell phone" in COCO
_PHONE_CONF_THRESHOLD = 0.5
_PHONE_CHECK_EVERY_N = 2        # run YOLO every Nth capture frame
_PHONE_BUFFER_SIZE = 4          # smoothing window for phone signal

_lock = threading.Lock()
_latest: PresenceSnapshot | None = None
_thread: threading.Thread | None = None
_stop = threading.Event()
_cap: "cv2.VideoCapture | None" = None
_detector: "Detector | None" = None
_backend_name: str = "none"
_phone_model: object | None = None


def current_presence() -> PresenceSnapshot:
    with _lock:
        if _latest is None:
            return PresenceSnapshot("ABSENT", 0.0, "none", 0.0, time.time())
        return _latest


def start() -> None:
    """Open the camera + construct the detector synchronously, then spawn the
    capture thread. Blocks for ~3-5s on first call while MediaPipe loads its
    TFLite model — by the time start() returns, current_presence() will return
    real data on the next frame.
    """
    global _thread, _cap, _detector, _backend_name, _phone_model
    if _thread is not None and _thread.is_alive():
        return

    camera_index = _select_camera_index()
    log.info("vision: opening webcam index %d...", camera_index)
    _cap = _open_camera(camera_index)
    if not _cap.isOpened():
        log.error("vision: could not open webcam (index %d)", camera_index)
        _cap = None
        return

    log.info("vision: building detector (this may take a few seconds)...")
    _backend_name, _detector = _make_detector()
    log.info("vision: detector backend = %s, ready", _backend_name)

    _phone_model = _try_yolo()

    _stop.clear()
    _thread = threading.Thread(target=_capture_loop, name="vision", daemon=True)
    _thread.start()


def _try_yolo() -> object | None:
    """Load YOLOv8n for phone detection. None if ultralytics not installed or load fails."""
    if YOLO is None:
        log.info("vision: ultralytics not installed; phone detection disabled")
        return None
    try:
        log.info("vision: loading YOLOv8n for phone detection (downloads ~6MB on first run)...")
        model = YOLO("yolov8n.pt")
        log.info("vision: YOLOv8n ready")
        return model
    except Exception as e:
        log.warning("vision: YOLO init failed (%s); phone detection disabled", e)
        return None


def _select_camera_index() -> int:
    configured = os.environ.get(_CAMERA_INDEX_ENV)
    if configured is not None:
        try:
            return int(configured)
        except ValueError:
            log.warning("vision: ignoring invalid %s=%r", _CAMERA_INDEX_ENV, configured)

    if sys.platform == "darwin":
        return _DEFAULT_MAC_CAMERA_INDEX

    return 0


def _open_camera(index: int) -> "cv2.VideoCapture":
    if sys.platform == "darwin":
        return cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    return cv2.VideoCapture(index)


def stop() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=2.0)
    if _cap is not None:
        _cap.release()


def _capture_loop() -> None:
    global _latest

    cap = _cap
    detect = _detector
    backend = _backend_name
    phone_model = _phone_model
    assert cap is not None and detect is not None, "start() must run first"

    readings: deque[PresenceState] = deque(maxlen=_BUFFER_SIZE)
    confidences: deque[float] = deque(maxlen=_BUFFER_SIZE)
    phone_buffer: deque[bool] = deque(maxlen=_PHONE_BUFFER_SIZE)
    period = 1.0 / _TARGET_FPS
    last_tick = time.time()
    fps_smoothed = 0.0
    frame_idx = 0

    logged_dims = False
    while not _stop.is_set():
        loop_start = time.time()
        ok, frame = cap.read()
        if not ok:
            log.warning("vision: cap.read() returned False; retrying")
            time.sleep(period)
            continue

        if not logged_dims:
            h, w = frame.shape[:2]
            log.info("vision: first frame %dx%d", w, h)
            logged_dims = True

        try:
            state, conf = detect(frame)
        except Exception:
            log.exception("vision: detector error on frame; skipping")
            time.sleep(period)
            continue
        readings.append(state)
        confidences.append(conf)

        # Phone check runs every Nth frame so it doesn't dominate the budget.
        # Skip frames just reuse the smoothed buffer's current verdict.
        frame_idx += 1
        if phone_model is not None and frame_idx % _PHONE_CHECK_EVERY_N == 0:
            try:
                results = phone_model(  # type: ignore[operator]
                    frame,
                    classes=[_PHONE_COCO_CLASS],
                    conf=_PHONE_CONF_THRESHOLD,
                    verbose=False,
                )
                phone_now = len(results[0].boxes) > 0
                log.debug("yolo: phone=%s", phone_now)
            except Exception:
                log.exception("vision: YOLO error on frame; skipping phone check")
                phone_now = phone_buffer[-1] if phone_buffer else False
            phone_buffer.append(phone_now)

        # Majority vote so a single false positive doesn't flip the pet
        phone_smoothed = bool(phone_buffer) and sum(phone_buffer) > len(phone_buffer) / 2

        smoothed = _majority(readings)
        avg_conf = sum(confidences) / len(confidences)

        now = time.time()
        instantaneous = 1.0 / max(now - last_tick, 1e-3)
        fps_smoothed = 0.8 * fps_smoothed + 0.2 * instantaneous
        last_tick = now

        with _lock:
            _latest = PresenceSnapshot(
                state=smoothed,
                confidence=avg_conf,
                backend=backend,
                fps=fps_smoothed,
                timestamp=now,
                phone_present=phone_smoothed,
            )

        slack = period - (time.time() - loop_start)
        if slack > 0:
            time.sleep(slack)


def _majority(buf: deque[PresenceState]) -> PresenceState:
    counts: dict[PresenceState, int] = {}
    for s in buf:
        counts[s] = counts.get(s, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


Detector = Callable[[np.ndarray], tuple[PresenceState, float]]


def _make_detector() -> tuple[str, Detector]:
    mp_detector = _try_mediapipe()
    if mp_detector is not None:
        return "mediapipe", mp_detector
    return "haar", _make_haar_detector()


def _try_mediapipe() -> Detector | None:
    """Construct a MediaPipe FaceMesh detector. Returns None on any failure
    (missing module, removed legacy `solutions` API on newer mediapipe builds, etc).
    """
    if mp is None:
        log.warning("vision: mediapipe not importable; using Haar")
        return None
    try:
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    except Exception as e:
        version = getattr(mp, "__version__", "?")
        log.warning(
            "vision: mediapipe init failed (mediapipe==%s, %s); falling back to Haar. "
            "Pin `mediapipe==0.10.14` in requirements.txt and reinstall to get gaze detection.",
            version, e,
        )
        return None

    log.info("vision: mediapipe FaceMesh ready (version %s)", getattr(mp, "__version__", "?"))

    def detect(frame: np.ndarray) -> tuple[PresenceState, float]:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = face_mesh.process(rgb)
        if not res.multi_face_landmarks:
            log.debug("mediapipe: 0 faces")
            return "ABSENT", 0.0

        lm = res.multi_face_landmarks[0].landmark
        # Yaw estimate: nose tip (1) horizontal offset relative to face width (left=234, right=454)
        nose_x = lm[1].x
        left_x = lm[234].x
        right_x = lm[454].x
        face_center = (left_x + right_x) / 2
        face_width = max(abs(right_x - left_x), 1e-6)
        yaw_norm = (nose_x - face_center) / face_width
        log.debug("mediapipe: face yaw_norm=%.2f", yaw_norm)

        if abs(yaw_norm) > _GAZE_YAW_THRESHOLD:
            return "LOOKING_AWAY", 0.8
        return "PRESENT", 0.9

    return detect


def _make_haar_detector() -> Detector:
    # alt2 is more accurate than the default cascade out of the box
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        log.error("vision: failed to load Haar cascade at %s", cascade_path)
    else:
        log.info("vision: Haar cascade loaded (%s)", cascade_path)

    def detect(frame: np.ndarray) -> tuple[PresenceState, float]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)  # normalize lighting — helps a lot indoors
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=3,
            minSize=(40, 40),
        )
        log.debug("haar: %d face(s)", len(faces))
        if len(faces) == 0:
            return "ABSENT", 0.0
        return "PRESENT", 0.7

    return detect


if __name__ == "__main__":
    level = logging.DEBUG if os.environ.get("VISION_DEBUG") else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    start()
    try:
        for _ in range(40):
            time.sleep(0.5)
            print(current_presence())
    finally:
        stop()
