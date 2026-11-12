"""LLM client responsible for generating structured handover packages."""

import logging
import os
from collections.abc import Mapping
from typing import Literal, NamedTuple

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.diagnostics import RATE_LIMITED_STATUS
from app.errors import (
    ContentBlockedError,
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
    ProxyFailureError,
)
from app.proxy_observer import observe_proxy_connect, proxy_connect_status
from app.schema import HandoverPackage

load_dotenv()

logger = logging.getLogger(__name__)

ApiKeySource = Literal["GEMINI_API_KEY", "GOOGLE_API_KEY"]


class ApiKey(NamedTuple):
    """A resolved API key and the variable it came from."""

    value: str | None
    source: ApiKeySource | None


def _resolve_api_key(environ: Mapping[str, str] | None = None) -> ApiKey:
    """Return the API key and its source, preferring GEMINI_API_KEY.

    When both variables hold a value, GEMINI_API_KEY wins, which is the
    opposite of the SDK's default precedence. Blank values count as unset, so
    the source names the variable that actually supplied the key.
    """
    source = os.environ if environ is None else environ
    gemini_key = (source.get("GEMINI_API_KEY") or "").strip()
    google_key = (source.get("GOOGLE_API_KEY") or "").strip()
    if gemini_key:
        return ApiKey(gemini_key, "GEMINI_API_KEY")
    if google_key:
        return ApiKey(google_key, "GOOGLE_API_KEY")
    return ApiKey(None, None)


DEFAULT_MODEL = "gemini-3.1-flash-lite"

# Provisional transport timeout, in milliseconds. It bounds how long a read may
# wait for the next block of data; it is not a deadline for the whole call, and
# it does not cancel work on the provider side. The value is an operational
# hypothesis, not a measured p99: the live suite does not record durations yet.
DEFAULT_TIMEOUT_MS = 20_000


def _resolve_model(environ: Mapping[str, str] | None = None) -> str:
    """Return the model name, falling back to the default.

    Blank counts as unset, the same rule the API key follows: an empty value
    would otherwise reach the provider as a model name and fail as a
    configuration error instead of falling back.
    """
    source = os.environ if environ is None else environ
    return (source.get("GEMINI_MODEL") or "").strip() or DEFAULT_MODEL


def _warn_on_key_fallback(source: ApiKeySource | None) -> None:
    """Announce, once at startup, when the key comes from the fallback.

    The message names the variables only: no value, prefix, length or hash.
    """
    if source == "GOOGLE_API_KEY":
        logger.warning("GEMINI_API_KEY is not set; using GOOGLE_API_KEY")


_MODEL = _resolve_model()
_API_KEY_RESOLUTION = _resolve_api_key()
_API_KEY = _API_KEY_RESOLUTION.value
_warn_on_key_fallback(_API_KEY_RESOLUTION.source)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Return the shared client, creating it on first use."""
    global _client
    if _client is None:
        if not _API_KEY:
            raise LLMConfigurationError("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
        _client = genai.Client(
            api_key=_API_KEY,
            http_options={
                "timeout": DEFAULT_TIMEOUT_MS,
                "client_args": {
                    "event_hooks": {"request": [observe_proxy_connect]},
                },
            },
        )
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


# A content block is a refusal, not an unusable response: the provider answers
# 200 and reports the refusal in the body. These are the values this service
# classifies. OTHER, the image reasons, MODEL_ARMOR and JAILBREAK (unavailable
# in the Gemini API) and unknown values stay unclassified.
PROMPT_BLOCK_REASONS = frozenset(
    {
        types.BlockedReason.SAFETY,
        types.BlockedReason.BLOCKLIST,
        types.BlockedReason.PROHIBITED_CONTENT,
    }
)

CANDIDATE_BLOCK_REASONS = frozenset(
    {
        types.FinishReason.SAFETY,
        types.FinishReason.BLOCKLIST,
        types.FinishReason.PROHIBITED_CONTENT,
        types.FinishReason.SPII,
        types.FinishReason.RECITATION,
    }
)


def _content_block(
    response: types.GenerateContentResponse,
) -> tuple[str, str] | None:
    """Return the stage and reason of a content block, or ``None``.

    The prompt feedback is read first, then the first candidate — the one the
    SDK uses to build ``parsed``. A block reported on another candidate is not
    read, because the service would never see that candidate's text.
    """
    feedback = response.prompt_feedback
    if feedback is not None and feedback.block_reason in PROMPT_BLOCK_REASONS:
        return "prompt", feedback.block_reason.value

    candidates = response.candidates or []
    if candidates and candidates[0].finish_reason in CANDIDATE_BLOCK_REASONS:
        return "candidate", candidates[0].finish_reason.value
    return None


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
    except httpx.ProxyError as exc:
        # The status is read from the request trace before HTTPX builds this
        # exception; the message and the reason phrase are never read. The
        # peer and the cause remain unestablished: the fixed message states
        # only the observation.
        raise ProxyFailureError(
            "Proxy request failed",
            proxy_connect_status=proxy_connect_status(exc),
        ) from exc
    except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        # Upstream transport failures: the connection dropped mid-stream or the
        # peer spoke something unexpected. LocalProtocolError and
        # UnsupportedProtocol are our side of the wire, so they keep rising to
        # the generic handler instead of blaming the provider.
        raise ProviderUnavailableError("LLM provider connection failed") from exc
    except errors.ServerError as exc:
        raise ProviderUnavailableError(
            "LLM provider failed to serve the request"
        ) from exc
    except errors.ClientError as exc:
        # The SDK raises one class for every 4xx, so the status is the only
        # structured evidence: a 429 is a refusal for capacity, not a rejected
        # client configuration. The body is provider text and is not read.
        if exc.code == RATE_LIMITED_STATUS:
            raise ProviderRateLimitedError(
                "LLM provider refused the request for capacity"
            ) from exc
        raise LLMConfigurationError(
            "LLM provider rejected the client configuration"
        ) from exc

    # A block is reported in the body of a successful response, and the SDK
    # still builds `parsed` from the candidate's text, so the check has to come
    # before the package is trusted. A truncated output (MAX_TOKENS) is not a
    # block and keeps the invalid-response branch.
    block = _content_block(response)
    if block is not None:
        stage, reason = block
        raise ContentBlockedError(stage=stage, reason=reason)

    # A response without structured output has no provider exception to
    # chain: the failure is in the content returned, not in the transport.
    if response.parsed is None:
        raise InvalidLLMResponseError("LLM provider returned no structured output")

    # response.parsed already arrives as a HandoverPackage; model_validate is
    # kept as a second barrier in case the SDK changes its return format.
    try:
        return HandoverPackage.model_validate(response.parsed)
    except ValidationError as exc:
        raise InvalidLLMResponseError(
            "LLM provider output does not match the handover package schema"
        ) from exc
