"""FastAPI application exposing the handover endpoint."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.diagnostics import (
    TLS_CERTIFICATE_VERIFICATION_FAILED,
    certificate_verification_failed,
)
from app.errors import (
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderUnavailableError,
    TranscriptTooLargeError,
)
from app.llm_client import generate_handover_package
from app.sanitization import (
    describe_exception,
    format_validation_errors,
    sanitize_validation_errors,
)
from app.schema import MAX_TRANSCRIPT_CHARS, HandoverPackage, TranscriptRequest

logger = logging.getLogger(__name__)

app = FastAPI()


@app.post("/handover")
def create_handover(request: TranscriptRequest) -> HandoverPackage:
    """Generate a handover package from a conversation transcript."""
    total_chars = sum(len(message.content) for message in request.messages)
    if total_chars > MAX_TRANSCRIPT_CHARS:
        raise TranscriptTooLargeError
    transcript = [
        {"role": message.role.value, "content": message.content}
        for message in request.messages
    ]
    return generate_handover_package(transcript)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Answer a structural violation with the rule, never with the value."""
    errors = sanitize_validation_errors(exc.errors())
    logger.warning(
        "Request rejected by input validation: %s", format_validation_errors(errors)
    )
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(ProviderUnavailableError)
async def handle_provider_unavailable(
    request: Request, exc: ProviderUnavailableError
) -> JSONResponse:
    # The identifier stays in the log: it describes the observed failure, not
    # its origin, and the public body keeps its single stable shape.
    diagnostic = (
        f" {TLS_CERTIFICATE_VERIFICATION_FAILED}"
        if certificate_verification_failed(exc)
        else ""
    )
    logger.warning(
        "LLM provider unavailable: %s%s", describe_exception(exc), diagnostic
    )
    return JSONResponse(
        status_code=503,
        content={
            "error": "provider_unavailable",
            "detail": "The LLM provider is temporarily unavailable. Please retry later.",
        },
    )


@app.exception_handler(InvalidLLMResponseError)
async def handle_invalid_llm_response(
    request: Request, exc: InvalidLLMResponseError
) -> JSONResponse:
    logger.warning(
        "LLM provider returned an invalid response: %s", describe_exception(exc)
    )
    return JSONResponse(
        status_code=502,
        content={
            "error": "invalid_llm_response",
            "detail": (
                "The LLM provider returned an invalid response. "
                "Please retry; if it persists, contact support."
            ),
        },
    )


@app.exception_handler(LLMConfigurationError)
async def handle_llm_configuration_error(
    request: Request, exc: LLMConfigurationError
) -> JSONResponse:
    logger.error("LLM client is misconfigured: %s", describe_exception(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": "llm_configuration_error",
            "detail": "The service is misconfigured. Please contact support.",
        },
    )


@app.exception_handler(TranscriptTooLargeError)
async def handle_transcript_too_large(
    request: Request, exc: TranscriptTooLargeError
) -> JSONResponse:
    logger.warning("Transcript rejected for exceeding the total size limit")
    return JSONResponse(
        status_code=413,
        content={
            "error": "transcript_too_large",
            "detail": (
                "The transcript is too large. The limit is "
                f"{MAX_TRANSCRIPT_CHARS} characters in total."
            ),
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled error while serving the handover request: %s",
        describe_exception(exc),
    )
    return JSONResponse(status_code=500, content={"error": "internal_error"})
