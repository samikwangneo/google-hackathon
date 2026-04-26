"""Vision / webcam module — Person B owns this file.

Public surface (do NOT change without pinging the channel):
    current_presence() -> PresenceSnapshot

Person D scaffold: returns PRESENT so state.py / main.py compile and
the WebSocket loop streams sensible values until B's real impl lands.
"""

from __future__ import annotations

from .schemas import PresenceSnapshot, PresenceState


def current_presence() -> PresenceSnapshot:
    """Latest presence reading from the webcam loop.

    Person B will replace with MediaPipe face/gaze detection running on a
    background thread + a thread-safe latest-reading slot.
    """
    return PresenceSnapshot(presence=PresenceState.PRESENT)
