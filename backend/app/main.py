"""FastAPI app entrypoint (Person D).

Owns CORS, all REST route registration, and the /ws/state push loop.
Other modules are imported and called here — no business logic lives in
this file.

Run:  uvicorn app.main:app --port 8765
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import activity, ai, brain, state, umd, vision
from .schemas import (
    BrainChatRequest,
    BrainChatResponse,
    BrainExplainRequest,
    BrainExplainResponse,
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        vision.start()
    except Exception as exc:  # pragma: no cover — webcam may be unavailable
        log.warning("vision.start() failed: %s", exc)
    try:
        activity.start_tracking()
    except Exception as exc:  # pragma: no cover — sensors may be unavailable
        log.warning("activity.start_tracking() failed: %s", exc)
    try:
        yield
    finally:
        try:
            activity.stop_tracking()
        except Exception as exc:  # pragma: no cover
            log.warning("activity.stop_tracking() failed: %s", exc)
        try:
            vision.stop()
        except Exception as exc:  # pragma: no cover
            log.warning("vision.stop() failed: %s", exc)


app = FastAPI(title="TerpPet backend", version="0.1.0", lifespan=lifespan)

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
    pomo = activity.pomodoro_start(req.minutes)
    brain.log_event(
        "pomodoro_started",
        f"Started a {req.minutes}-minute Pomodoro",
        {"minutes": req.minutes},
    )
    return PomodoroStartResponse(started_at=pomo.started_at, ends_at=pomo.ends_at)


@app.post("/api/pomodoro/stop", response_model=OkResponse)
def pomodoro_stop() -> OkResponse:
    activity.pomodoro_stop()
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


# In-memory store of screenshots keyed by session_id. Bounded so a long-lived
# backend doesn't accumulate megabytes of JPEGs forever — eviction is FIFO.
_BRAIN_SESSIONS: "OrderedDict[str, bytes]" = OrderedDict()
_BRAIN_SESSION_CAP = 16


def _brain_session_put(session_id: str, image_bytes: bytes) -> None:
    _BRAIN_SESSIONS[session_id] = image_bytes
    while len(_BRAIN_SESSIONS) > _BRAIN_SESSION_CAP:
        _BRAIN_SESSIONS.popitem(last=False)


@app.post("/api/brain/explain", response_model=BrainExplainResponse)
def brain_explain(req: BrainExplainRequest) -> BrainExplainResponse:
    session_id = req.session_id
    if session_id and session_id in _BRAIN_SESSIONS:
        image_bytes = _BRAIN_SESSIONS[session_id]
    else:
        try:
            image_bytes = activity.capture_screen_jpeg_bytes()
        except Exception as exc:
            log.warning("brain_explain screencap failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"screen capture failed: {exc}")
        session_id = uuid.uuid4().hex
        _brain_session_put(session_id, image_bytes)

    reply = ai.explain_screen(image_bytes)
    brain.log_event("brain_explain", reply[:120])
    return BrainExplainResponse(session_id=session_id, reply=reply)


@app.post("/api/brain/chat", response_model=BrainChatResponse)
def brain_chat(req: BrainChatRequest) -> BrainChatResponse:
    image_bytes = _BRAIN_SESSIONS.get(req.session_id)
    if image_bytes is None:
        raise HTTPException(status_code=404, detail="brain session not found; reopen the panel")
    reply = ai.chat_about_screen(image_bytes, req.history, req.message)
    brain.log_event("brain_chat", req.message[:120])
    return BrainChatResponse(reply=reply)


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
