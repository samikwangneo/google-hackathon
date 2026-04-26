"""Run the TerpPet FastAPI backend.

Usage:
    python run.py
    python run.py --reload
    python run.py --screen-ai --screen-ai-interval 10

This script intentionally lives at backend/run.py so teammates do not need to
remember the uvicorn module path or port.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

import uvicorn
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _load_env() -> None:
    """Load backend/.env without overriding already-exported shell vars."""
    load_dotenv(BACKEND_DIR / ".env", override=False)


def _apply_runtime_env(args: argparse.Namespace) -> None:
    if args.screen_ai:
        os.environ["TERPPET_SCREEN_AI"] = "1"
    if args.no_screen_ai:
        os.environ["TERPPET_SCREEN_AI"] = "0"
    if args.screen_ai_interval is not None:
        os.environ["TERPPET_SCREEN_AI_INTERVAL_SECONDS"] = str(args.screen_ai_interval)
    if args.camera_index is not None:
        os.environ["VISION_CAMERA_INDEX"] = str(args.camera_index)
    if args.vision_debug:
        os.environ["VISION_DEBUG"] = "1"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the TerpPet backend server.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host (default {DEFAULT_HOST}).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default {DEFAULT_PORT}).")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload for development.")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help="Uvicorn log level (default info).",
    )
    parser.add_argument("--screen-ai", action="store_true", help="Enable Gemini screenshot focus classifier.")
    parser.add_argument("--no-screen-ai", action="store_true", help="Force-disable Gemini screenshot classifier.")
    parser.add_argument(
        "--screen-ai-interval",
        type=float,
        default=None,
        help="Seconds between Gemini screenshot classifications. Minimum is enforced in activity.py.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=None,
        help="Override webcam index (sets VISION_CAMERA_INDEX).",
    )
    parser.add_argument(
        "--vision-debug",
        action="store_true",
        help="Enable verbose vision logs (sets VISION_DEBUG=1).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _load_env()
    parser = _build_parser()
    args = parser.parse_args(argv)
    _apply_runtime_env(args)

    print(f"TerpPet backend: http://{args.host}:{args.port}")
    print("Health check:     GET /api/health")
    print("WebSocket:        /ws/state")
    if os.environ.get("TERPPET_SCREEN_AI") == "1":
        print(
            "Screen AI:        enabled "
            f"(interval={os.environ.get('TERPPET_SCREEN_AI_INTERVAL_SECONDS', 'default')}s)"
        )
    else:
        print("Screen AI:        disabled")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        app_dir=str(BACKEND_DIR),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
