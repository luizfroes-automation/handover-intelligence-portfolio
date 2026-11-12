"""Unit tests for the CONNECT-status observer.

The trace event carries the status, the reason phrase and the headers, and it is
also emitted for ordinary origin responses. The observer accepts a status only
from the reading whose ``.started`` event identified a ``CONNECT`` request. The
state lives on the request that failed, so two requests through the shared
client cannot read each other's status.
"""

from types import SimpleNamespace

import httpx
import pytest

from app.proxy_observer import observe_proxy_connect, proxy_connect_status

REASON_MARKER = "synthetic-reason-marker-enh13"
HEADER_MARKER = "synthetic-header-marker-enh13"

REQUEST_STARTED = "http11.receive_response_headers.started"
REQUEST_COMPLETE = "http11.receive_response_headers.complete"
REQUEST_FAILED = "http11.receive_response_headers.failed"


def _request() -> httpx.Request:
    request = httpx.Request("POST", "https://example.invalid")
    observe_proxy_connect(request)
    return request


def _read_headers(
    request: httpx.Request,
    *,
    method: bytes = b"CONNECT",
    status: int = 407,
) -> None:
    trace = request.extensions["trace"]
    trace(REQUEST_STARTED, {"request": SimpleNamespace(method=method)})
    trace(
        REQUEST_COMPLETE,
        {
            "return_value": (
                b"HTTP/1.1",
                status,
                REASON_MARKER.encode(),
                [(b"x-synthetic", HEADER_MARKER.encode())],
            )
        },
    )


def _proxy_error(request: httpx.Request) -> httpx.ProxyError:
    error = httpx.ProxyError("synthetic")
    error.request = request
    return error


def test_the_observer_keeps_the_status_and_drops_the_rest():
    request = _request()
    _read_headers(request, status=407)

    assert proxy_connect_status(_proxy_error(request)) == 407
    # The request carries the state and the callback, never the reason phrase
    # or a header value.
    assert REASON_MARKER not in repr(request.extensions)
    assert HEADER_MARKER not in repr(request.extensions)


def test_an_unobserved_request_has_no_status():
    assert proxy_connect_status(httpx.ProxyError("synthetic")) is None


def test_a_complete_without_a_started_reading_is_ignored():
    request = _request()
    request.extensions["trace"](
        REQUEST_COMPLETE,
        {"return_value": (b"HTTP/1.1", 407, b"", [])},
    )

    assert proxy_connect_status(_proxy_error(request)) is None


def test_an_origin_response_is_not_a_connect_status():
    request = _request()
    _read_headers(request, method=b"POST", status=403)

    assert proxy_connect_status(_proxy_error(request)) is None


def test_a_later_origin_reading_clears_the_connect_status():
    request = _request()
    _read_headers(request, status=200)
    _read_headers(request, method=b"POST", status=502)

    assert proxy_connect_status(_proxy_error(request)) is None


@pytest.mark.parametrize(
    "value",
    [
        (b"HTTP/1.1", "407"),
        (b"HTTP/1.1", 407),
        (b"HTTP/1.1", 407, b"reason"),
        (b"HTTP/1.1", 700, b"reason", []),
        (407, []),
        None,
        "not-a-tuple",
    ],
)
def test_a_malformed_complete_is_ignored(value):
    request = _request()
    trace = request.extensions["trace"]
    trace(REQUEST_STARTED, {"request": SimpleNamespace(method=b"CONNECT")})
    trace(REQUEST_COMPLETE, {"return_value": value})

    assert proxy_connect_status(_proxy_error(request)) is None


def test_a_failed_reading_is_ignored():
    request = _request()
    trace = request.extensions["trace"]
    trace(REQUEST_STARTED, {"request": SimpleNamespace(method=b"CONNECT")})
    trace(REQUEST_FAILED, {"exception": httpx.ReadError("synthetic")})

    assert proxy_connect_status(_proxy_error(request)) is None


def test_the_state_does_not_leak_between_requests():
    first = _request()
    _read_headers(first, status=407)
    second = _request()

    assert proxy_connect_status(_proxy_error(first)) == 407
    assert proxy_connect_status(_proxy_error(second)) is None
