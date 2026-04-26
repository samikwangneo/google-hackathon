"""FastAPI app entrypoint (Person D).

Owns CORS, all REST route registration, and the /ws/state push loop.
Other modules are imported and called here — no business logic lives in
this file.

Run:  uvicorn app.main:app --port 8765
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import uuid
from collections import OrderedDict
import traceback
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

_ws_client_counter = itertools.count(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("lifespan: starting vision...")
    try:
        vision.start()
        log.info("lifespan: vision.start() returned")
    except Exception as exc:  # pragma: no cover — webcam may be unavailable
        log.warning("vision.start() failed: %s\n%s", exc, traceback.format_exc())
    log.info("lifespan: starting activity tracker...")
    try:
        activity.start_tracking()
        log.info("lifespan: activity.start_tracking() returned")
    except Exception as exc:  # pragma: no cover — sensors may be unavailable
        log.warning(
            "activity.start_tracking() failed: %s\n%s", exc, traceback.format_exc()
        )
    log.info("lifespan: ready, accepting requests")
    try:
        yield
    finally:
        log.info("lifespan: shutting down")
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
# Print every Nth frame at INFO so logs stay readable but you can see the
# stream is alive. The first frame and any errors always log.
WS_FRAME_LOG_EVERY = 5


@app.websocket("/ws/state")
async def ws_state(websocket: WebSocket) -> None:
    client_id = next(_ws_client_counter)
    peer = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "?"
    log.info("ws_state[%d]: connection from %s, accepting...", client_id, peer)
    await websocket.accept()
    log.info("ws_state[%d]: accepted; entering send loop", client_id)
    frames_sent = 0
    try:
        while True:
            try:
                update = state.aggregate(tick_seconds=WS_TICK_SECONDS)
            except Exception as exc:
                log.exception("ws_state[%d]: state.aggregate() raised: %s", client_id, exc)
                await asyncio.sleep(WS_TICK_SECONDS)
                continue

            try:
                payload = update.model_dump_json()
            except Exception as exc:
                log.exception(
                    "ws_state[%d]: model_dump_json() raised: %s", client_id, exc
                )
                await asyncio.sleep(WS_TICK_SECONDS)
                continue

            await websocket.send_text(payload)
            frames_sent += 1
            if frames_sent == 1 or frames_sent % WS_FRAME_LOG_EVERY == 0:
                log.info(
                    "ws_state[%d]: sent frame #%d state=%s presence=%s mood=%s xp=%d lvl=%d window=%r",
                    client_id,
                    frames_sent,
                    update.state.value if hasattr(update.state, "value") else update.state,
                    update.presence.value if hasattr(update.presence, "value") else update.presence,
                    update.pet_mood.value if hasattr(update.pet_mood, "value") else update.pet_mood,
                    update.xp,
                    update.level,
                    (update.active_window or "")[:60],
                )

            # Drain and forward special events on the same socket.
            for event in state.drain_events():
                log.info("ws_state[%d]: special event %r", client_id, event)
                await websocket.send_json(event)
                kind = event.get("type", "event")
                brain.log_event(kind, f"event: {kind}", event)

            await asyncio.sleep(WS_TICK_SECONDS)
    except WebSocketDisconnect as exc:
        log.info(
            "ws_state[%d]: client disconnected after %d frame(s) (code=%s)",
            client_id,
            frames_sent,
            getattr(exc, "code", "?"),
        )
        return
    except Exception as exc:  # pragma: no cover — keep the loop robust
        log.exception(
            "ws_state[%d]: loop error after %d frame(s): %s",
            client_id,
            frames_sent,
            exc,
        )
        try:
            await websocket.close()
        except Exception:
            pass
