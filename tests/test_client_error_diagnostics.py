"""Unit tests for the identifier of a provider client-error branch.

The selector reads the status the SDK carries on the exception and nothing else:
the provider's message and body are free text, may quote the request and may
name an internal project, so they are never part of a classification.
"""

import httpx
from google.genai import errors

from app.diagnostics import (
    PROVIDER_AUTH_REJECTED,
    PROVIDER_PERMISSION_DENIED,
    PROVIDER_THROTTLED_OR_QUOTA_EXHAUSTED,
    client_error_identifier,
)
from app.errors import LLMConfigurationError, ProviderRateLimitedError


def _translated(cause: BaseException) -> LLMConfigurationError:
    error = LLMConfigurationError("synthetic")
    error.__cause__ = cause
    return error


def _client_error(status: int, *, message: str = "synthetic") -> errors.ClientError:
    return errors.ClientError(status, {"error": {"code": status, "message": message}})


def test_the_constants_are_the_logged_tokens():
    assert PROVIDER_AUTH_REJECTED == "provider_auth_rejected"
    assert PROVIDER_PERMISSION_DENIED == "provider_permission_denied"
    assert (
        PROVIDER_THROTTLED_OR_QUOTA_EXHAUSTED == "provider_throttled_or_quota_exhausted"
    )


def test_the_selector_maps_the_three_classified_statuses():
    assert client_error_identifier(_translated(_client_error(401))) == (
        PROVIDER_AUTH_REJECTED
    )
    assert client_error_identifier(_translated(_client_error(403))) == (
        PROVIDER_PERMISSION_DENIED
    )
    assert client_error_identifier(_translated(_client_error(429))) == (
        PROVIDER_THROTTLED_OR_QUOTA_EXHAUSTED
    )


def test_the_rate_limited_branch_is_reachable_from_its_own_exception():
    translated = ProviderRateLimitedError("synthetic")
    translated.__cause__ = _client_error(429)
    assert client_error_identifier(translated) == (
        PROVIDER_THROTTLED_OR_QUOTA_EXHAUSTED
    )


def test_the_selector_leaves_the_other_statuses_unclassified():
    for status in (400, 404, 409, 422):
        assert client_error_identifier(_translated(_client_error(status))) is None


def test_the_selector_ignores_a_server_error():
    server_error = errors.ServerError(503, {"error": {"message": "unavailable"}})
    assert client_error_identifier(_translated(server_error)) is None


def test_the_selector_ignores_the_provider_message():
    """A 5xx whose text mentions quota is still a server error, not a 429."""
    lying = errors.ServerError(
        500, {"error": {"message": "quota exceeded, rate limited, retry"}}
    )
    assert client_error_identifier(_translated(lying)) is None


def test_the_selector_trusts_the_status_over_the_body_code():
    diverging = errors.ClientError(
        429, {"error": {"code": 400, "message": "invalid argument"}}
    )
    assert client_error_identifier(_translated(diverging)) == (
        PROVIDER_THROTTLED_OR_QUOTA_EXHAUSTED
    )


def test_the_selector_returns_none_for_other_branches():
    for cause in (
        httpx.ProxyError("synthetic proxy failure"),
        httpx.ConnectTimeout("synthetic timeout"),
        httpx.ReadError("synthetic read failure"),
        RuntimeError("synthetic unexpected error"),
    ):
        assert client_error_identifier(_translated(cause)) is None


def test_the_selector_returns_none_without_a_cause():
    assert client_error_identifier(LLMConfigurationError("synthetic")) is None
