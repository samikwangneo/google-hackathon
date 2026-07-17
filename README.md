# Terpo

Terpo is an always-on desktop AI study companion designed for students at the University of Maryland (UMD).

It features a virtual pet that lives in the corner of your screen as a transparent overlay, watches your screen activity and webcam presence, reacts to your focus levels, and evolves as you complete Pomodoro sessions.

## Architecture

- **Frontend**: Electron + Vite + React + TypeScript app. Renders the transparent always-on window.
- **Backend**: Python FastAPI sidecar running locally. Handles webcam vision processing, screen activity tracking, Pomodoro logic, and integration with the Gemini API (via `google-genai`) for study plans and summarizations.
- **Communication**: WebSocket for real-time behavior pushes and REST API for other commands.
- **Storage**: Append-only event log and in-memory stats.

## Features

- **Activity Tracking**: Uses screen activity and facial recognition to determine focus state (e.g., FOCUSED, DISTRACTED, IDLE, MULTITASKING, AWAY).
- **Interactive Pet**: Pet reacts to your study habits (shakes when distracted, glows when focused).
- **Pomodoro Timer**: Gain XP and level up your pet by completing focused study sessions.
- **Study Tools**: Features a radial orb menu for starting Pomodoros, viewing study plans, accessing memory (brain), and checking UMD-specific study spots and dining options.