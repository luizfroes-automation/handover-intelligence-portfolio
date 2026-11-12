"""FastAPI application exposing the handover endpoint."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.diagnostics import (
    CONNECTION_FAILURE_ORIGIN_UNDETERMINED,
    TLS_CERTIFICATE_VERIFICATION_FAILED,
    client_error_identifier,
    connection_failure_identifier,
)
from app.error_contract import (
    CONFIGURATION_ERROR_DETAIL,
    CONNECTION_FAILURE_DETAIL,
    HANDOVER_RESPONSES,
    INVALID_RESPONSE_DETAIL,
    PROVIDER_UNAVAILABLE_DETAIL,
    RATE_LIMITED_DETAIL,
    RATE_LIMITED_FALLBACK,
    TRANSCRIPT_TOO_LARGE_DETAIL,
)
from app.errors import (
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderRateLimitedError,
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


@app.post("/handover", responses=HANDOVER_RESPONSES)
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
    # its origin. Only the neutral branch changes the public message: a failure
    # whose origin is unknown cannot tell the caller the provider is unavailable
    # or that a retry would help. Status and error code stay the same.
    identifier = connection_failure_identifier(exc)
    if identifier == TLS_CERTIFICATE_VERIFICATION_FAILED:
        logger.warning(
            "LLM certificate verification failed: %s %s",
            describe_exception(exc),
            identifier,
        )
    elif identifier == CONNECTION_FAILURE_ORIGIN_UNDETERMINED:
        logger.warning(
            "LLM connection failure: %s %s", describe_exception(exc), identifier
        )
    else:
        logger.warning("LLM provider unavailable: %s", describe_exception(exc))
    detail = (
        CONNECTION_FAILURE_DETAIL
        if identifier == CONNECTION_FAILURE_ORIGIN_UNDETERMINED
        else PROVIDER_UNAVAILABLE_DETAIL
    )
    return JSONResponse(
        status_code=503,
        content={"error": "provider_unavailable", "detail": detail},
    )


@app.exception_handler(ProviderRateLimitedError)
async def handle_provider_rate_limited(
    request: Request, exc: ProviderRateLimitedError
) -> JSONResponse:
    # The status stays 503 because the service cannot complete the operation.
    # The error code separates this refusal from the timeout and transport
    # branches, and the identifier records what the provider answered. The
    # provider's timing hint is not forwarded: the service does not promise that
    # a later attempt would succeed. The body carries the case a person has to
    # review: this request received no usable assessment from the service.
    logger.warning(
        "LLM provider refused the request for capacity: %s %s",
        describe_exception(exc),
        client_error_identifier(exc),
    )
    return JSONResponse(
        status_code=503,
        content={
            "error": "provider_rate_limited",
            "detail": RATE_LIMITED_DETAIL,
            "fallback": RATE_LIMITED_FALLBACK.model_dump(),
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
            "detail": INVALID_RESPONSE_DETAIL,
        },
    )


@app.exception_handler(LLMConfigurationError)
async def handle_llm_configuration_error(
    request: Request, exc: LLMConfigurationError
) -> JSONResponse:
    # The body stays the same for every 4xx, because the caller's action does not
    # change. When the status is one the classifier recognises, the log line
    # names the category the provider reported instead of calling the client
    # misconfigured: the status does not establish that our configuration is
    # wrong, and an expired key, a disabled API or a project restriction remain
    # hypotheses for the investigation.
    identifier = client_error_identifier(exc)
    description = describe_exception(exc)
    if identifier is None:
        logger.error("LLM client is misconfigured: %s", description)
    else:
        logger.error(
            "LLM provider rejected authentication or permission: %s %s",
            description,
            identifier,
        )
    return JSONResponse(
        status_code=500,
        content={
            "error": "llm_configuration_error",
            "detail": CONFIGURATION_ERROR_DETAIL,
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
            "detail": TRANSCRIPT_TOO_LARGE_DETAIL,
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled error while serving the handover request: %s",
        describe_exception(exc),
    )
    return JSONResponse(status_code=500, content={"error": "internal_error"})
