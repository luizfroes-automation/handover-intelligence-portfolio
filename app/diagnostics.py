"""Internal diagnostics derived from an exception chain.

An identifier recorded here describes what was observed, not who caused it: a
certificate that failed verification says nothing about whether the proxy, the
destination or the local trust store introduced it. These identifiers go to the
log only; the HTTP contract is not part of this module.
"""

import ssl

import httpx

TLS_CERTIFICATE_VERIFICATION_FAILED = "tls_certificate_verification_failed"


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
