"""FastAPI application exposing the handover endpoint."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors import (
    InvalidLLMResponseError,
    LLMConfigurationError,
    ProviderUnavailableError,
)
from app.llm_client import generate_handover_package
from app.schema import HandoverPackage, TranscriptRequest

logger = logging.getLogger(__name__)

app = FastAPI()


@app.post("/handover")
def create_handover(request: TranscriptRequest) -> HandoverPackage:
    """Generate a handover package from a conversation transcript."""
    transcript = [
        {"role": message.role.value, "content": message.content}
        for message in request.messages
    ]
    return generate_handover_package(transcript)


@app.exception_handler(ProviderUnavailableError)
async def handle_provider_unavailable(
    request: Request, exc: ProviderUnavailableError
) -> JSONResponse:
    logger.warning("LLM provider unavailable", exc_info=exc)
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
    logger.warning("LLM provider returned an invalid response", exc_info=exc)
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
    logger.error("LLM client is misconfigured", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "llm_configuration_error",
            "detail": "The service is misconfigured. Please contact support.",
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error while serving the handover request", exc_info=exc)
    return JSONResponse(status_code=500, content={"error": "internal_error"})
