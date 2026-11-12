"""The public error contract: the bodies the handlers send and their schema.

Both readers of this contract — the JSON body and the generated OpenAPI document
— are built from the constants below, so a message exists once. The examples are
the exact bodies the handlers return; `tests/test_openapi_contract.py` compares
every one of them against a live response, so a handler edited without the
document fails the suite.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, RootModel

from app.schema import MAX_TRANSCRIPT_CHARS

PROVIDER_UNAVAILABLE_DETAIL = (
    "The LLM provider is temporarily unavailable. Please retry later."
)

# A failure whose origin is unknown cannot tell the caller the provider is
# unavailable or that a retry would help, so it gets a neutral message.
CONNECTION_FAILURE_DETAIL = (
    "A connection failure prevented the request from completing."
)

RATE_LIMITED_DETAIL = (
    "The LLM provider is rate-limiting this service or its quota is exhausted."
)

INVALID_RESPONSE_DETAIL = (
    "The LLM provider returned an invalid response. "
    "Please retry; if it persists, contact support."
)

CONFIGURATION_ERROR_DETAIL = "The service is misconfigured. Please contact support."

TRANSCRIPT_TOO_LARGE_DETAIL = (
    "The transcript is too large. The limit is "
    f"{MAX_TRANSCRIPT_CHARS} characters in total."
)


class ErrorResponse(BaseModel):
    """An error with a message for a person."""

    error: str
    detail: str


class ConfigurationErrorResponse(BaseModel):
    """The 500 raised when the client or generation configuration is rejected."""

    model_config = ConfigDict(extra="forbid")

    error: Literal["llm_configuration_error"]
    detail: str


class InternalErrorResponse(BaseModel):
    """The generic 500, the only error in the contract with no ``detail``."""

    model_config = ConfigDict(extra="forbid")

    error: Literal["internal_error"]


class ErrorResponses(RootModel[ConfigurationErrorResponse | InternalErrorResponse]):
    """A 500 is one of two bodies, and ``error`` says whether ``detail`` exists.

    Each branch pins its own code and refuses unknown properties, so a client
    that reads ``error`` to decide whether ``detail`` is available cannot be
    handed a body that contradicts the code.
    """


class ValidationErrorItem(BaseModel):
    """One rejected rule, without the value that broke it."""

    type: str
    loc: list[str | int]
    msg: str


class ValidationErrorResponse(BaseModel):
    """The sanitized 422 body: `input` and `ctx` are never returned."""

    detail: list[ValidationErrorItem]


def _body(error: str, detail: str) -> dict:
    return {"error": error, "detail": detail}


HANDOVER_RESPONSES: dict[int, dict] = {
    413: {
        "model": ErrorResponse,
        "description": "The transcript is larger than the accepted total.",
        "content": {
            "application/json": {
                "examples": {
                    "transcript_too_large": {
                        "summary": "The input exceeds the total size limit",
                        "value": _body(
                            "transcript_too_large", TRANSCRIPT_TOO_LARGE_DETAIL
                        ),
                    }
                }
            }
        },
    },
    422: {
        "model": ValidationErrorResponse,
        "description": (
            "A rule over the request body was rejected. The rejected value is "
            "neither echoed nor recorded, so `input` and `ctx` never appear."
        ),
    },
    500: {
        "model": ErrorResponses,
        "description": (
            "The service is misconfigured, or an unexpected failure occurred. "
            "Each branch pins its `error` code: `llm_configuration_error` always "
            "carries `detail`, and `internal_error` never does."
        ),
        "content": {
            "application/json": {
                "examples": {
                    "configuration_error": {
                        "summary": (
                            "The client or generation configuration was rejected"
                        ),
                        "value": _body(
                            "llm_configuration_error", CONFIGURATION_ERROR_DETAIL
                        ),
                    },
                    "internal_error": {
                        "summary": (
                            "An unexpected failure outside the provider contract"
                        ),
                        "value": {"error": "internal_error"},
                    },
                }
            }
        },
    },
    502: {
        "model": ErrorResponse,
        "description": "The provider output does not satisfy the handover contract.",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_llm_response": {
                        "summary": (
                            "No structured output, or output that fails validation"
                        ),
                        "value": _body("invalid_llm_response", INVALID_RESPONSE_DETAIL),
                    }
                }
            }
        },
    },
    503: {
        "model": ErrorResponse,
        "description": (
            "The service cannot complete the operation: the provider failed, a "
            "connection failure had an undetermined origin, or the provider "
            "refused the request for capacity."
        ),
        "content": {
            "application/json": {
                "examples": {
                    "provider_unavailable": {
                        "summary": "The provider is unreachable, timed out or 5xx",
                        "value": _body(
                            "provider_unavailable", PROVIDER_UNAVAILABLE_DETAIL
                        ),
                    },
                    "provider_unavailable_connection_failure": {
                        "summary": (
                            "A connection failure whose origin is undetermined"
                        ),
                        "value": _body(
                            "provider_unavailable", CONNECTION_FAILURE_DETAIL
                        ),
                    },
                    "provider_rate_limited": {
                        "summary": (
                            "The provider refused the request for capacity or quota"
                        ),
                        "value": _body("provider_rate_limited", RATE_LIMITED_DETAIL),
                    },
                }
            }
        },
    },
}
