"""FastAPI app entrypoint (Person D).

Owns CORS, all REST route registration, and the /ws/state push loop.
Other modules are imported and called here — no business logic lives in
this file.

Run:  uvicorn app.main:app --port 8765
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import activity, ai, brain, state, umd
from .schemas import (
    BrainSearchResponse,
    BrainTodayResponse,
    DiningRec,
    OkResponse,
    PomodoroStartRequest,
    PomodoroStartResponse,
    StatsTodayResponse,
    StudyPlanRequest,
    StudyPlanResponse,
    StudySpot,
    SummarizeRequest,
    SummarizeResponse,
)


log = logging.getLogger("terppet.main")

app = FastAPI(title="TerpPet backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=OkResponse)
def health() -> OkResponse:
    return OkResponse(ok=True)


# ---------------------------------------------------------------------------
# Pomodoro (C via D — wires HTTP routes to activity.py)
# ---------------------------------------------------------------------------


@app.post("/api/pomodoro/start", response_model=PomodoroStartResponse)
def pomodoro_start(req: PomodoroStartRequest) -> PomodoroStartResponse:
    started_at, ends_at = activity.start_pomodoro(req.minutes)
    brain.log_event(
        "pomodoro_started",
        f"Started a {req.minutes}-minute Pomodoro",
        {"minutes": req.minutes},
    )
    return PomodoroStartResponse(started_at=started_at, ends_at=ends_at)


@app.post("/api/pomodoro/stop", response_model=OkResponse)
def pomodoro_stop() -> OkResponse:
    activity.stop_pomodoro()
    brain.log_event("pomodoro_stopped", "Stopped Pomodoro early")
    return OkResponse(ok=True)


# ---------------------------------------------------------------------------
# AI (D)
# ---------------------------------------------------------------------------


@app.post("/api/study-plan", response_model=StudyPlanResponse)
def study_plan(req: StudyPlanRequest) -> StudyPlanResponse:
    resp = ai.generate_study_plan(req.goal, req.hours_available)
    brain.log_event(
        "study_plan",
        f"Generated study plan for: {req.goal}",
        {"hours_available": req.hours_available, "blocks": len(resp.blocks)},
    )
    return resp


@app.post("/api/summarize", response_model=SummarizeResponse)
def summarize(req: SummarizeRequest) -> SummarizeResponse:
    resp = ai.summarize_and_quiz(req.text)
    brain.log_event(
        "summarize",
        f"Summarized {len(req.text)} chars",
        {"chars": len(req.text), "quiz_count": len(resp.quiz)},
    )
    return resp


# ---------------------------------------------------------------------------
# Brain (D)
# ---------------------------------------------------------------------------


@app.get("/api/brain/search", response_model=BrainSearchResponse)
def brain_search(q: str = "") -> BrainSearchResponse:
    return brain.search(q)


@app.get("/api/brain/today", response_model=BrainTodayResponse)
def brain_today() -> BrainTodayResponse:
    return brain.today_summary()


# ---------------------------------------------------------------------------
# UMD (D)
# ---------------------------------------------------------------------------


@app.get("/api/umd/study-spots", response_model=list[StudySpot])
def umd_study_spots() -> list[StudySpot]:
    return umd.study_spots()


@app.get("/api/umd/dining", response_model=list[DiningRec])
def umd_dining() -> list[DiningRec]:
    return umd.dining()


# ---------------------------------------------------------------------------
# Stats (D)
# ---------------------------------------------------------------------------


@app.get("/api/stats/today", response_model=StatsTodayResponse)
def stats_today() -> StatsTodayResponse:
    return StatsTodayResponse(**state.stats_today())


# ---------------------------------------------------------------------------
# WebSocket: 1 Hz behavior push + special events
# ---------------------------------------------------------------------------


WS_TICK_SECONDS = 1.0


@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            update = state.aggregate(tick_seconds=WS_TICK_SECONDS)
            await websocket.send_text(update.model_dump_json())

            # Drain and forward special events on the same socket.
            for event in state.drain_events():
                await websocket.send_json(event)
                kind = event.get("type", "event")
                brain.log_event(kind, f"event: {kind}", event)

            await asyncio.sleep(WS_TICK_SECONDS)
    except WebSocketDisconnect:
        return
    except Exception as exc:  # pragma: no cover — keep the loop robust
        log.warning("ws_state loop error: %s", exc)
        try:
            await websocket.close()
        except Exception:
            pass
