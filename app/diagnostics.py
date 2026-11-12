"""Internal diagnostics derived from an exception chain.

An identifier recorded here describes what was observed, not who caused it: a
certificate that failed verification says nothing about whether the proxy, the
destination or the local trust store introduced it. These identifiers go to the
log only: the HTTP response is still built by the handlers. The module also
exposes the single provider status the client translates into its own exception,
so the number has one definition instead of two.
"""

import ssl

import httpx
from google.genai import errors

from app.errors import ContentBlockedError

TLS_CERTIFICATE_VERIFICATION_FAILED = "tls_certificate_verification_failed"

# The connect branch with no evidence about where the connection failed. The
# exception does not say whether the refused TCP peer was the destination or
# the proxy, so the identifier names the uncertainty instead of a culprit.
CONNECTION_FAILURE_ORIGIN_UNDETERMINED = "connection_failure_origin_undetermined"

# Provider client-error identifiers. The SDK raises one class for every 4xx, so
# the status code is the only structured evidence the exception carries: the
# message and the body are provider text, may quote the request and may name an
# internal project, so they are never read here.
PROVIDER_AUTH_REJECTED = "provider_auth_rejected"
PROVIDER_PERMISSION_DENIED = "provider_permission_denied"

# A 429 says the provider refused the request for capacity. It does not separate
# a short rate-limit window from an exhausted quota: that difference lives in the
# response body, which is not part of the classification.
PROVIDER_THROTTLED_OR_QUOTA_EXHAUSTED = "provider_throttled_or_quota_exhausted"

# The only client-error status the client translates into its own exception
# instead of the configuration error.
RATE_LIMITED_STATUS = 429

_CLIENT_ERROR_IDENTIFIERS = {
    401: PROVIDER_AUTH_REJECTED,
    403: PROVIDER_PERMISSION_DENIED,
    RATE_LIMITED_STATUS: PROVIDER_THROTTLED_OR_QUOTA_EXHAUSTED,
}

# A content block is reported in the body of a 200, in one of two places. The
# identifier names the stage that reported it; the reason travels beside it.
PROMPT_CONTENT_BLOCKED = "prompt_content_blocked"
CANDIDATE_CONTENT_BLOCKED = "candidate_content_blocked"

_CONTENT_BLOCK_IDENTIFIERS = {
    "prompt": PROMPT_CONTENT_BLOCKED,
    "candidate": CANDIDATE_CONTENT_BLOCKED,
}

# The proxy path failed, and the exception carries neither the CONNECT status nor
# the peer it tried to reach. The identifier names the uncertainty.
PROXY_FAILURE_ORIGIN_UNDETERMINED = "proxy_failure_origin_undetermined"


def certificate_verification_failed(exc: BaseException) -> bool:
    """True only for the translated ``httpx.ConnectError`` branch.

    The provider-unavailable handler also receives timeouts, other transport
    failures and SDK server errors. A certificate error sitting in the context
    of one of those is not a verification failure of the connect branch, so the
    type of the translated cause is checked before the chain is read.
    """
    cause = exc.__cause__
    if not isinstance(cause, httpx.ConnectError):
        return False
    return chain_contains_certificate_verification_error(cause)


def connection_failure_identifier(exc: BaseException) -> str | None:
    """The single identifier for a translated ``ConnectError`` branch.

    ``None`` means the branch is not a connect error — a timeout, another
    transport failure or an SDK server error — and keeps its current diagnostic.
    A proven certificate verification failure wins over the undetermined-origin
    token, so the two are mutually exclusive and one log line carries one
    reading.
    """
    if not isinstance(exc.__cause__, httpx.ConnectError):
        return None
    if certificate_verification_failed(exc):
        return TLS_CERTIFICATE_VERIFICATION_FAILED
    return CONNECTION_FAILURE_ORIGIN_UNDETERMINED


def content_block_identifier(exc: BaseException) -> str | None:
    """The identifier for a content block, or ``None`` for another branch.

    ``None`` means the exception is not a content block, so the handler that
    receives it is not the block branch.
    """
    if not isinstance(exc, ContentBlockedError):
        return None
    return _CONTENT_BLOCK_IDENTIFIERS.get(exc.stage)


def client_error_identifier(exc: BaseException) -> str | None:
    """The identifier for a translated provider client error.

    ``None`` means the exception is not a provider client error — a transport
    failure, a server error or one of our own configuration failures — and keeps
    the current diagnostic. Only the status the SDK carries on the cause is read:
    the provider's message and body are free text, may quote the request and may
    name an internal project, so they never take part in a classification.
    """
    cause = exc.__cause__
    if not isinstance(cause, errors.ClientError):
        return None
    return _CLIENT_ERROR_IDENTIFIERS.get(cause.code)


def chain_contains_certificate_verification_error(exc: BaseException) -> bool:
    """True when the chain carries a proven certificate verification failure.

    The walk follows ``__cause__`` or ``__context__`` and stops on a cycle, so a
    malformed chain cannot hold the handler. Only the exception type counts:
    messages are free text and are never inspected or forwarded.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        current = current.__cause__ or current.__context__
    return False
