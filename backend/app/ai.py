"""Gemini wrapper (Person D).

Lazy-initialized google-genai client. If the lib isn't installed or
GEMINI_API_KEY is missing / invalid, every public function falls back to
deterministic canned data so the server still boots and the demo loop
keeps working.

Public surface:
    generate_study_plan(goal, hours_available) -> StudyPlanResponse
    summarize_and_quiz(text) -> SummarizeResponse
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from dotenv import find_dotenv, load_dotenv

from .schemas import (
    QuizQuestion,
    StudyPlanBlock,
    StudyPlanResponse,
    SummarizeResponse,
)


log = logging.getLogger("terppet.ai")

# Load .env once from wherever it lives (repo root walked up from CWD).
load_dotenv(find_dotenv(usecwd=True))


_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

_client: Optional[Any] = None


def _get_client() -> Optional[Any]:
    """Return a google-genai Client or None if unavailable."""
    global _client
    if _client is not None:
        return _client
    if not _API_KEY:
        return None
    try:
        from google import genai  # type: ignore

        _client = genai.Client(api_key=_API_KEY)
        return _client
    except Exception as exc:  # pragma: no cover — runtime fallback
        log.warning("Gemini client init failed: %s", exc)
        return None


def _generate_json(prompt: str, response_schema: Any) -> Optional[Any]:
    """Best-effort structured JSON call. Returns parsed dict/list or None."""
    client = _get_client()
    if client is None:
        return None
    try:
        from google.genai import types  # type: ignore

        resp = client.models.generate_content(
            model=_DEFAULT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )
        text = getattr(resp, "text", None)
        if not text:
            return None
        return json.loads(text)
    except Exception as exc:  # pragma: no cover — runtime fallback
        log.warning("Gemini call failed (%s); using canned response", exc)
        return None


# ---------------------------------------------------------------------------
# Study plan
# ---------------------------------------------------------------------------


def _canned_study_plan(goal: str, hours_available: float) -> StudyPlanResponse:
    total_minutes = max(30, int(hours_available * 60))
    block_len = 25
    break_len = 5
    blocks: list[StudyPlanBlock] = []
    cursor = 0
    i = 0
    while cursor + block_len <= total_minutes:
        blocks.append(
            StudyPlanBlock(
                start_minute=cursor,
                duration_minutes=block_len,
                topic=goal,
                activity=("Read & take notes" if i % 2 == 0 else "Practice problems"),
            )
        )
        cursor += block_len
        if cursor + break_len <= total_minutes:
            blocks.append(
                StudyPlanBlock(
                    start_minute=cursor,
                    duration_minutes=break_len,
                    topic="Break",
                    activity="Stretch, water, look away from screen",
                )
            )
            cursor += break_len
        i += 1
    return StudyPlanResponse(
        blocks=blocks,
        summary=(
            f"Pomodoro plan for '{goal}' over {hours_available} hours. "
            "Alternate 25-min focus blocks with 5-min breaks."
        ),
    )


def generate_study_plan(goal: str, hours_available: float) -> StudyPlanResponse:
    prompt = (
        "You are a study coach for a UMD student. Build a focused study plan.\n"
        f"Goal: {goal}\n"
        f"Time available: {hours_available} hours\n"
        "Return JSON matching the schema. Use 25-minute focus blocks separated "
        "by 5-minute breaks. Each block must have start_minute (offset from "
        "the start), duration_minutes, topic, and a concrete activity."
    )
    parsed = _generate_json(prompt, StudyPlanResponse)
    if parsed is None:
        return _canned_study_plan(goal, hours_available)
    try:
        return StudyPlanResponse.model_validate(parsed)
    except Exception as exc:
        log.warning("Gemini study-plan parse failed (%s); using canned", exc)
        return _canned_study_plan(goal, hours_available)


# ---------------------------------------------------------------------------
# Summarize + quiz
# ---------------------------------------------------------------------------


def _canned_summary_quiz(text: str) -> SummarizeResponse:
    snippet = text.strip().split("\n", 1)[0][:140]
    return SummarizeResponse(
        summary=(
            f"Summary placeholder for input starting: '{snippet}'. "
            "Connect a Gemini API key to get real summaries."
        ),
        quiz=[
            QuizQuestion(
                question="What is the main idea of the passage?",
                answer="Add GEMINI_API_KEY to .env to generate real quiz questions.",
            ),
            QuizQuestion(
                question="Name one supporting detail.",
                answer="Canned response — real model output requires an API key.",
            ),
            QuizQuestion(
                question="How would you apply this material?",
                answer="Canned response — real model output requires an API key.",
            ),
        ],
    )


def summarize_and_quiz(text: str) -> SummarizeResponse:
    prompt = (
        "You are a study assistant. Read the text and return JSON matching the "
        "schema with: a 3-sentence summary, and 3 quiz questions with answers "
        "that test understanding.\n\n"
        f"TEXT:\n{text}"
    )
    parsed = _generate_json(prompt, SummarizeResponse)
    if parsed is None:
        return _canned_summary_quiz(text)
    try:
        return SummarizeResponse.model_validate(parsed)
    except Exception as exc:
        log.warning("Gemini summarize parse failed (%s); using canned", exc)
        return _canned_summary_quiz(text)
