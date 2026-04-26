"""Smoke-test Gemini via Vertex AI + ADC.

Prereqs (one time):
    gcloud auth application-default login
    gcloud config set project YOUR_PROJECT_ID

Run from repo root:
    python test_gemini.py                       # interactive REPL
    python test_gemini.py "what is 2+2"         # one-shot

Reads from .env (or shell env):
    GOOGLE_GENAI_USE_VERTEXAI=true
    GOOGLE_CLOUD_PROJECT=...
    GOOGLE_CLOUD_LOCATION=us-central1   (default if unset)
    GEMINI_MODEL=gemini-2.5-flash       (default if unset)
"""

import os
import sys
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()

from google import genai  # noqa: E402

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

if not PROJECT:
    sys.exit(
        "GOOGLE_CLOUD_PROJECT not set. Add it to .env or run:\n"
        "    set GOOGLE_CLOUD_PROJECT=your-project-id"
    )

client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)


def call(prompt: str) -> str:
    resp = client.models.generate_content(model=MODEL, contents=prompt)
    return resp.text or "(no text returned)"


def main() -> None:
    if len(sys.argv) > 1:
        print(call(" ".join(sys.argv[1:])))
        return

    print(f"Vertex AI · project={PROJECT} · location={LOCATION} · model={MODEL}")
    print("Type a prompt (Ctrl+C to quit).")
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not prompt:
            continue
        try:
            print(call(prompt))
        except Exception as e:
            print(f"error: {e}")


if __name__ == "__main__":
    main()
