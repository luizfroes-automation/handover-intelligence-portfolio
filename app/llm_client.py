"""LLM client responsible for generating structured handover packages."""

import os
from collections.abc import Mapping

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.errors import (
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderUnavailableError,
)
from app.schema import HandoverPackage

load_dotenv()


def _resolve_api_key(environ: Mapping[str, str] | None = None) -> str | None:
    """Return the API key, preferring GEMINI_API_KEY over GOOGLE_API_KEY.

    When both variables hold a value, GEMINI_API_KEY wins, which is the
    opposite of the SDK's default precedence. Blank values count as unset.
    """
    source = os.environ if environ is None else environ
    gemini_key = (source.get("GEMINI_API_KEY") or "").strip()
    google_key = (source.get("GOOGLE_API_KEY") or "").strip()
    return gemini_key or google_key or None


_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
_API_KEY = _resolve_api_key()

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Return the shared client, creating it on first use."""
    global _client
    if _client is None:
        if not _API_KEY:
            raise LLMConfigurationError("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
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
    """Render the transcript as one role-prefixed line per message."""
    lines: list[str] = []
    for message in transcript:
        role = message.get("role", "unknown")
        content = message.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def generate_handover_package(transcript: list[dict]) -> HandoverPackage:
    """Analyze a transcript and return a validated handover package."""
    formatted = _format_transcript(transcript)
    client = _get_client()
    try:
        response = client.models.generate_content(
            model=_MODEL,
            contents=formatted,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=HandoverPackage,
            ),
        )
    except httpx.TimeoutException as exc:
        raise ProviderUnavailableError("LLM provider request timed out") from exc
    except httpx.ConnectError as exc:
        raise ProviderUnavailableError("LLM provider is unreachable") from exc
    except errors.ServerError as exc:
        raise ProviderUnavailableError(
            "LLM provider failed to serve the request"
        ) from exc
    except errors.ClientError as exc:
        raise LLMConfigurationError(
            "LLM provider rejected the client configuration"
        ) from exc

    # Uma resposta sem saída estruturada não tem exceção do provider para
    # encadear: a falha está no conteúdo devolvido, não no transporte.
    if response.parsed is None:
        raise InvalidLLMResponseError("LLM provider returned no structured output")

    # response.parsed já vem como HandoverPackage; model_validate mantido
    # como segunda barreira caso o SDK mude o formato de retorno no futuro.
    try:
        return HandoverPackage.model_validate(response.parsed)
    except ValidationError as exc:
        raise InvalidLLMResponseError(
            "LLM provider output does not match the handover package schema"
        ) from exc
