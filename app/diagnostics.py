"""Internal diagnostics derived from an exception chain.

An identifier recorded here describes what was observed, not who caused it: a
certificate that failed verification says nothing about whether the proxy, the
destination or the local trust store introduced it. These identifiers go to the
log only; the HTTP contract is not part of this module.
"""

import ssl

import httpx

TLS_CERTIFICATE_VERIFICATION_FAILED = "tls_certificate_verification_failed"

# The connect branch with no evidence about where the connection failed. The
# exception does not say whether the refused TCP peer was the destination or
# the proxy, so the identifier names the uncertainty instead of a culprit.
CONNECTION_FAILURE_ORIGIN_UNDETERMINED = "connection_failure_origin_undetermined"


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
