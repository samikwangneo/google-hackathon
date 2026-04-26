 Plan: TerpPet — team split + repo scaffold

 Context

 Hackathon project ("TerpPet"): always-on desktop AI study companion for UMD
 students. A pet lives in the corner, watches you via screen + webcam,
 reacts when you're not locked in, and evolves / levels up as you complete
 Pomodoro sessions. Click the pet → cool radial menu of buttons (Pomodoro
 timer, study tools, etc).

 User has already scaffolded the frontend with the electron-vite React +
 TypeScript template at ./frontend/. No backend exists yet. This internal plan is the
 only doc that will exist; team split lives here for now.

 Demo loop (what the judges actually see)

 1. Pet sits bottom-right, transparent always-on overlay
 2. Webcam sees you → pet alert; you walk away → pet sleepy
 3. Open YouTube/social → pet annoyed, shakes
 4. Open VS Code/Docs → pet happy, glow builds
 5. Click pet → radial orb menu animates open
 6. Click Pomodoro orb → timer starts; pet enters "focus mode"
 7. Finish a Pomodoro → XP gain, level-up sparkle, pet evolves at level X
 8. (Stretch) study plan + UMD spot + brain search

 Architecture

 - frontend/ — existing electron-vite app (Electron main + React renderer)
 - backend/ — new Python FastAPI sidecar on localhost:8765
 - Comms: WebSocket /ws/state (1 Hz behavior pushes) + REST /api/*
 - Storage: backend/data/brain.jsonl (append log) + in-memory stats. No SQLite.
 - AI: Gemini via google-genai (key from repo-root .env)

 Team split (4 people)

 Person A — Frontend & UX

 Owns: frontend/**
 - Make Electron main window transparent / frameless / always-on-top / pinned bottom-right (edit
 frontend/src/main/index.ts)
 - Add deps as needed: tailwindcss, framer-motion, zustand
 - Components (new files under frontend/src/renderer/src/components/):
   - Pet.tsx — sprite + mood-driven animation; reacts to behavior store
   - OrbMenu.tsx — radial expand on pet click; orbs for Pomodoro / Study Plan / Brain / Stats
   - PomodoroPanel.tsx — timer countdown, start/stop, completion event
   - StatsPanel.tsx — XP bar, level, focus minutes today
   - EvolutionEffect.tsx — sparkle / sprite swap on level-up
 - lib/ws.ts — WebSocket client w/ auto-reconnect → store
 - lib/api.ts — REST client (typed against types/contracts.ts)
 - store/index.ts — Zustand store: behavior state, pet mood, xp/level, pomodoro state
 - types/contracts.ts — TS mirror of backend schemas.py
 - Owns demo polish: glow, shake, sparkle, evolution sprite swap

 Person B — Vision & Webcam (CV)

 Owns: backend/app/vision.py
 - Webcam capture loop (OpenCV) on a background thread
 - MediaPipe face detection → PRESENT / ABSENT
 - Attention signal: face landmarks → LOCKED_IN / LOOKING_AWAY (gaze yaw)
 - Thread-safe latest-reading slot
 - Public surface: current_presence() -> PresenceSnapshot
 - Hard rule: never persist frames; only derived signal
 - Fallback if MediaPipe install fails: OpenCV Haar cascade for face presence (no attention signal)

 Person C — Screen & Activity Tracking

 Owns: backend/app/activity.py
 - Active-window/title polling (pygetwindow + win32 fallback)
 - URL/tab heuristic from window title (Chrome/Edge show "Page — Browser")
 - Keyboard/mouse activity sampling (pynput, low frequency, no key logging)
 - Behavior classifier — emits one of:
 FOCUSED / DISTRACTED / IDLE / MULTITASKING / AWAY
 - Pomodoro engine (lives here because it's tied to focus tracking):
   - start(minutes), stop(), tick()
   - On completion: emits a PomodoroCompleted event the state aggregator picks up
 - Public surface: current_state() -> ActivitySnapshot, pomodoro getters
 - Fallback: --mock-activity flag that cycles scripted states for the demo

 Person D — API, AI & Memory

 Owns: backend/app/{main,state,ai,brain,umd}.py + schemas.py
 - main.py — FastAPI app, CORS, route wiring, /ws/state loop
 - schemas.py — single source of truth for all shapes (Pydantic v2)
 - state.py — aggregator: pulls from vision.current_presence() + activity.current_state() + pomodoro
 events → emits unified BehaviorUpdate. Owns XP/level math (Pomodoro completion = +XP; level-up at
 thresholds).
 - ai.py — Gemini wrapper (google-genai); generate_study_plan, summarize_and_quiz
 - brain.py — append events to data/brain.jsonl; search(q) (keyword + Gemini rerank); today_summary()
 - umd.py — study_spots(), dining() (small mock data lists, swappable later)
 - Owns the API contract — when shapes change, ping channel; A mirrors in contracts.ts

 Boundaries

 - Only A touches frontend/
 - Only B touches vision.py
 - Only C touches activity.py
 - Only D touches main.py, state.py, ai.py, brain.py, umd.py, schemas.py
 - main.py is the only place routes are registered → keeps merge conflicts to one file

 API contract

 WebSocket — ws://localhost:8765/ws/state (server pushes ~1 Hz)

 {
   "state": "FOCUSED | DISTRACTED | IDLE | MULTITASKING | AWAY",
   "presence": "PRESENT | ABSENT | LOOKING_AWAY",
   "pet_mood": "HAPPY | NEUTRAL | ANNOYED | SLEEPY | FOCUS_MODE | EVOLVED",
   "active_window": "string | null",
   "focus_seconds": 0,
   "distraction_streak": 0,
   "xp": 0,
   "level": 1,
   "pomodoro": { "running": false, "ends_at": null, "minutes": 25 }
 }

 Special server-pushed events (same socket, different type field):
 - {"type": "pomodoro_completed", "xp_delta": 50}
 - {"type": "level_up", "level": 3}

 REST

 ┌────────┬──────────────────────┬──────────────────────┬───────────────────────────────┬────────┐
 │ Method │         Path         │         Body         │             Resp              │ Owner  │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ GET    │ /api/health          │ —                    │ {ok: true}                    │ D      │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ POST   │ /api/pomodoro/start  │ {minutes}            │ {started_at, ends_at}         │ C via  │
 │        │                      │                      │                               │ D      │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ POST   │ /api/pomodoro/stop   │ —                    │ {ok: true}                    │ C via  │
 │        │                      │                      │                               │ D      │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ POST   │ /api/study-plan      │ {goal,               │ {blocks, summary}             │ D      │
 │        │                      │ hours_available}     │                               │        │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ POST   │ /api/summarize       │ {text}               │ {summary, quiz}               │ D      │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ GET    │ /api/brain/search?q= │ —                    │ {hits: [...]}                 │ D      │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ GET    │ /api/brain/today     │ —                    │ {summary, topics, score}      │ D      │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ GET    │ /api/umd/study-spots │ —                    │ [{name, vibe, busyness}]      │ D      │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ GET    │ /api/umd/dining      │ —                    │ [{hall, recommendation,       │ D      │
 │        │                      │                      │ vibe}]                        │        │
 ├────────┼──────────────────────┼──────────────────────┼───────────────────────────────┼────────┤
 │ GET    │ /api/stats/today     │ —                    │ {focus_seconds, xp, level,    │ D      │
 │        │                      │                      │ pomodoros}                    │        │
 └────────┴──────────────────────┴──────────────────────┴───────────────────────────────┴────────┘

 Files to create (scaffold)

 Backend (all new — Person D writes the skeleton; B/C/D fill modules)

 - backend/requirements.txt — fastapi, uvicorn[standard], pydantic, google-genai, python-dotenv,
 opencv-python, mediapipe, pygetwindow, pynput, psutil
 - backend/.gitignore — .venv/, __pycache__/, data/
 - backend/app/__init__.py
 - backend/app/main.py — FastAPI app, CORS, all routes wired to module fns, /ws/state push loop
 - backend/app/schemas.py — BehaviorState, PresenceState, PetMood, BehaviorUpdate, PomodoroState,
 StudyPlanRequest/Response, SummarizeRequest/Response, BrainHit, StudySpot, DiningRec
 - backend/app/state.py — aggregate() -> BehaviorUpdate, XP/level math, level-up event emission
 - backend/app/activity.py — Person C placeholder: current_state(), pomodoro engine stubs
 - backend/app/vision.py — Person B placeholder: current_presence() stub returning PRESENT
 - backend/app/ai.py — Gemini client init from env, generate_study_plan / summarize_and_quiz stubs
 returning canned data so server runs without API key
 - backend/app/brain.py — log_event, search, today_summary over data/brain.jsonl
 - backend/app/umd.py — small mock lists for study spots + dining

 Frontend (additions only — leave existing electron-vite files untouched)

 - frontend/src/renderer/src/components/Pet.tsx — placeholder button, TODO for Framer Motion + sprite
 - frontend/src/renderer/src/components/OrbMenu.tsx — placeholder, TODO for radial expand
 - frontend/src/renderer/src/components/PomodoroPanel.tsx — placeholder
 - frontend/src/renderer/src/components/StatsPanel.tsx — placeholder
 - frontend/src/renderer/src/components/EvolutionEffect.tsx — placeholder
 - frontend/src/renderer/src/lib/ws.ts — WebSocket client w/ reconnect TODO
 - frontend/src/renderer/src/lib/api.ts — typed REST helpers
 - frontend/src/renderer/src/store/index.ts — Zustand store (will need npm i zustand)
 - frontend/src/renderer/src/types/contracts.ts — mirror of schemas.py

 All placeholders use plain React + inline styles (no Tailwind / Framer Motion
 imports yet) so the renderer keeps compiling before Person A installs deps.

 Non-goals

 - Do not recreate PLAN.md at repo root
 - Do not modify existing electron-vite template files (App.tsx, main/index.ts, etc) — Person A wires
  up integration
 - Do not run npm install or pip install
 - Do not add Tailwind / Framer Motion imports to placeholders (would break compile until deps
 installed)
 - No SQLite, no tests, no CI

 Verification

 1. find backend frontend/src/renderer/src -type f -newer PLAN-doesn-t-exist — confirm new files
 match list above
 2. python -m py_compile backend/app/*.py — backend modules parse
 3. cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8765 — server boots,
  /api/health returns ok, /ws/state accepts a connection and streams placeholder updates
 4. cd frontend && npm run dev — renderer still compiles (no broken imports)
 5. Open backend/app/main.py — every route handler points to a real symbol in a module file

 Approval

