"""Diagnostic run: fail if collection or tests attempt outbound network access.

Temporary audit for the CI ticket. It patches ``socket.connect``,
``socket.connect_ex`` and ``socket.getaddrinfo`` so that only loopback is
allowed, proves the guard is armed, then runs the deterministic suite. The
in-process ASGI transport used by ``TestClient`` does not open sockets, so the
suite must pass unchanged.
"""

import os
import socket
import sys

BLOCKED_MESSAGE = "outbound network access attempted"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


class BlockedNetworkAccess(RuntimeError):
    """Raised before an outbound connection can leave the process."""


def _host_of(address: object) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


def _is_local(host: str) -> bool:
    return host in LOCAL_HOSTS or host.startswith("127.")


_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def _guarded_connect(self, address):
    if _is_local(_host_of(address)):
        return _connect(self, address)
    raise BlockedNetworkAccess(f"{BLOCKED_MESSAGE}: {_host_of(address)}")


def _guarded_connect_ex(self, address):
    if _is_local(_host_of(address)):
        return _connect_ex(self, address)
    raise BlockedNetworkAccess(f"{BLOCKED_MESSAGE}: {_host_of(address)}")


def _guarded_getaddrinfo(host, *args, **kwargs):
    if _is_local(str(host)):
        return _getaddrinfo(host, *args, **kwargs)
    raise BlockedNetworkAccess(f"{BLOCKED_MESSAGE}: {host}")


def _report_environment() -> None:
    """Report presence, never values."""
    print(f".env present: {os.path.exists('.env')}")
    print(f"GEMINI_API_KEY set: {'GEMINI_API_KEY' in os.environ}")
    print(f"GOOGLE_API_KEY set: {'GOOGLE_API_KEY' in os.environ}")


def _assert_guard_is_armed() -> None:
    """Prove the guard fires: 192.0.2.1 is TEST-NET-1, reserved for docs."""
    probe = socket.socket()
    probe.settimeout(0.2)
    try:
        probe.connect(("192.0.2.1", 81))
    except BlockedNetworkAccess:
        print("guard armed: an outbound connect is blocked before the syscall")
    else:
        raise SystemExit("guard inactive: the probe reached the network stack")
    finally:
        probe.close()


if __name__ == "__main__":
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    socket.getaddrinfo = _guarded_getaddrinfo

    _report_environment()
    _assert_guard_is_armed()

    import pytest

    sys.exit(pytest.main(["-q"]))
