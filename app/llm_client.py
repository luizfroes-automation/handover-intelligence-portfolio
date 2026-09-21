"""LLM client responsible for generating structured handover packages."""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.schema import HandoverPackage

load_dotenv()

_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
_API_KEY = os.getenv("GEMINI_API_KEY")

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=_API_KEY)
    return _client


_SYSTEM_INSTRUCTION = (
    "You analyze support conversations between a bot and a customer. "
    "Given the transcript, decide whether the conversation needs to be "
    "handed off to a human and produce a handover package with the fields "
    "handoff_needed, reason, summary, urgency, suggested_team, confidence "
    "and flags."
)


def _format_transcript(transcript: list[dict]) -> str:
    lines: list[str] = []
    for message in transcript:
        role = message.get("role", "unknown")
        content = message.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def generate_handover_package(transcript: list[dict]) -> HandoverPackage:
    """Analyze a transcript and return a validated handover package."""
    formatted = _format_transcript(transcript)
    response = _get_client().models.generate_content(
        model=_MODEL,
        contents=formatted,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=HandoverPackage,
        ),
    )
    # response.parsed já vem como HandoverPackage; model_validate mantido
    # como segunda barreira caso o SDK mude o formato de retorno no futuro.
    return HandoverPackage.model_validate(response.parsed)
