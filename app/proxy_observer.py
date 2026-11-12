"""Observe the proxy CONNECT status without retaining the response text.

httpcore exposes a trace extension on each request. The trace event for the
response headers carries the status, the reason phrase and the headers; this
module keeps only the numeric status. The observation travels in the request
that failed, so concurrent requests through the shared client cannot read each
other's result.
"""

import httpx

_STATUS_EXTENSION = "proxy_connect_status"
_TRACE_EXTENSION = "trace"
_HEADERS_EVENT = "http11.receive_response_headers"
_STARTED_EVENT = f"{_HEADERS_EVENT}.started"
_COMPLETE_EVENT = f"{_HEADERS_EVENT}.complete"
_FAILED_EVENT = f"{_HEADERS_EVENT}.failed"


def _status_from_headers(value: object) -> int | None:
    """Read the status from the HTTP/1.1 headers tuple, or return ``None``.

    The expected shape is ``(http_version, status, reason_phrase, headers)``.
    A different shape is not interpreted: without the status in the known
    position, the caller omits the field.
    """
    if not isinstance(value, tuple) or len(value) != 4:
        return None
    http_version, status, reason_phrase, _headers = value
    if not isinstance(http_version, bytes):
        return None
    if not isinstance(reason_phrase, bytes):
        return None
    if not isinstance(status, int) or not 100 <= status <= 599:
        return None
    return status


def observe_proxy_connect(request: httpx.Request) -> None:
    """Attach a trace recorder that retains only the CONNECT status.

    The response-headers event is also emitted for ordinary origin responses.
    The recorder accepts a status only when the matching ``.started`` event
    identified a ``CONNECT`` request, and clears the previous reading first.
    """
    state: dict[str, object] = {"status": None, "connect_reading": False}
    request.extensions[_STATUS_EXTENSION] = state

    def trace(name: str, info: dict[str, object]) -> None:
        if name == _STARTED_EVENT:
            started_request = info.get("request")
            state["connect_reading"] = (
                getattr(started_request, "method", None) == b"CONNECT"
            )
            state["status"] = None
            return
        if name not in (_COMPLETE_EVENT, _FAILED_EVENT):
            return
        if not state["connect_reading"]:
            return
        state["connect_reading"] = False
        if name == _FAILED_EVENT:
            return
        status = _status_from_headers(info.get("return_value"))
        if status is not None:
            state["status"] = status

    request.extensions[_TRACE_EXTENSION] = trace


def proxy_connect_status(exc: BaseException) -> int | None:
    """Return the CONNECT status recorded on the failed request, if any.

    Only the request that failed is read. The exception message, the reason
    phrase and the headers are never inspected.
    """
    try:
        request = exc.request
    except RuntimeError:
        return None
    extensions = getattr(request, "extensions", None)
    if not isinstance(extensions, dict):
        return None
    state = extensions.get(_STATUS_EXTENSION)
    if not isinstance(state, dict):
        return None
    status = state.get("status")
    return status if isinstance(status, int) else None
