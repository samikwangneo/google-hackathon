"""Single source of truth for all wire shapes (Pydantic v2).

Person A mirrors these in frontend/src/renderer/src/types/contracts.ts.
When a shape changes here, ping the channel.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BehaviorState(str, Enum):
    FOCUSED = "FOCUSED"
    DISTRACTED = "DISTRACTED"
    IDLE = "IDLE"
    AWAY = "AWAY"


class PresenceState(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LOOKING_AWAY = "LOOKING_AWAY"


class PetMood(str, Enum):
    HAPPY = "HAPPY"
    NEUTRAL = "NEUTRAL"
    ANNOYED = "ANNOYED"
    SLEEPY = "SLEEPY"
    FOCUS_MODE = "FOCUS_MODE"
    EVOLVED = "EVOLVED"
    GOOD_APPLE = "GOOD_APPLE"
    BAD_APPLE = "BAD_APPLE"
    JENGA = "JENGA"
    GAMEBOY = "GAMEBOY"
    GENTLE_BREATHING = "GENTLE_BREATHING"
    ANNOYED_FOOT_TAPPING = "ANNOYED_FOOT_TAPPING"
    ANNOYED_DOOM_SCROLLING = "ANNOYED_DOOM_SCROLLING"
    EXAM_PANIC_MODE = "EXAM_PANIC_MODE"
    WALKING = "WALKING"


# ---------------------------------------------------------------------------
# Internal snapshots (not on the wire — used between modules)
# ---------------------------------------------------------------------------


class PresenceSnapshot(BaseModel):
    """Public surface from vision.py."""

    presence: PresenceState = PresenceState.PRESENT


class ActivitySnapshot(BaseModel):
    """Public surface from activity.py."""

    state: BehaviorState = BehaviorState.IDLE
    active_window: Optional[str] = None
    distraction_streak: int = 0


# ---------------------------------------------------------------------------
# WebSocket: BehaviorUpdate frame
# ---------------------------------------------------------------------------


class PomodoroState(BaseModel):
    running: bool = False
    ends_at: Optional[datetime] = None
    minutes: int = 25


class BehaviorUpdate(BaseModel):
    state: BehaviorState
    presence: PresenceState
    pet_mood: PetMood
    active_window: Optional[str] = None
    focus_seconds: int = 0
    distraction_streak: int = 0
    xp: int = 0
    level: int = 1
    pomodoro: PomodoroState
    phone_present: bool = False


# ---------------------------------------------------------------------------
# REST: Pomodoro
# ---------------------------------------------------------------------------


class PomodoroStartRequest(BaseModel):
    minutes: int = Field(25, ge=1, le=180)


class PomodoroStartResponse(BaseModel):
    started_at: datetime
    ends_at: datetime


class OkResponse(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------------------
# REST: AI study plan
# ---------------------------------------------------------------------------


class StudyPlanRequest(BaseModel):
    goal: str
    hours_available: float = Field(..., ge=0.25, le=24)


class StudyPlanBlock(BaseModel):
    start_minute: int
    duration_minutes: int
    topic: str
    activity: str


class StudyPlanResponse(BaseModel):
    blocks: list[StudyPlanBlock]
    summary: str


# ---------------------------------------------------------------------------
# REST: AI summarize + quiz
# ---------------------------------------------------------------------------


class SummarizeRequest(BaseModel):
    text: str


class QuizQuestion(BaseModel):
    question: str
    answer: str


class SummarizeResponse(BaseModel):
    summary: str
    quiz: list[QuizQuestion]


# ---------------------------------------------------------------------------
# REST: Brain (second-brain log)
# ---------------------------------------------------------------------------


class BrainHit(BaseModel):
    timestamp: datetime
    kind: str
    text: str
    score: float = 0.0


class BrainSearchResponse(BaseModel):
    hits: list[BrainHit]


class BrainTodayResponse(BaseModel):
    summary: str
    topics: list[str]
    score: int


class BrainChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class BrainExplainRequest(BaseModel):
    session_id: Optional[str] = None


class BrainExplainResponse(BaseModel):
    session_id: str
    reply: str


class BrainChatRequest(BaseModel):
    session_id: str
    message: str
    history: list[BrainChatMessage] = []


class BrainChatResponse(BaseModel):
    reply: str


# ---------------------------------------------------------------------------
# REST: UMD spots / dining
# ---------------------------------------------------------------------------


class StudySpot(BaseModel):
    name: str
    vibe: str
    busyness: str


class DiningRec(BaseModel):
    hall: str
    recommendation: str
    vibe: str


# ---------------------------------------------------------------------------
# REST: stats
# ---------------------------------------------------------------------------


class StatsTodayResponse(BaseModel):
    focus_seconds: int
    xp: int
    level: int
    pomodoros: int
