"""Diagnostics for a rejected request that never reproduce its content.

Pydantic's ``ValidationError.errors()`` carries the rejected value in ``input``
(and can echo it in ``ctx``), and the message of an exception raised while
serving a request can quote that request. Both are removed here, before a body
or a log record is built, so the leak cannot come back through a new call site.
"""

import traceback
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any

from pydantic import ValidationError


def sanitize_validation_errors(
    errors: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the rule that failed and drop the value that failed it.

    ``type``, ``loc`` and ``msg`` identify the failure without the data, which
    is what a client needs to fix the request and what an operator needs to
    recognise the rule. ``input``, ``ctx`` and the documentation ``url`` are
    discarded.
    """
    safe_errors: list[dict[str, Any]] = []
    for error in errors:
        safe_errors.append(
            {
                "type": str(error.get("type", "value_error")),
                "loc": list(error.get("loc", ())),
                "msg": str(error.get("msg", "Invalid value")),
            }
        )
    return safe_errors


def format_validation_errors(errors: Iterable[Mapping[str, Any]]) -> str:
    """Render sanitized errors as a single log line."""
    return "; ".join(
        f"{'/'.join(str(part) for part in error['loc'])} "
        f"[{error['type']}] {error['msg']}"
        for error in sanitize_validation_errors(errors)
    )


def describe_exception(exc: BaseException) -> str:
    """Describe an exception chain by type and location, never by message.

    The type and the raising frame are enough to locate a failure; the message
    is what can quote the request. A chained ``ValidationError`` contributes
    its sanitized errors, because those name the rule rather than the value.
    """
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(_describe_one(current))
        current = current.__cause__ or current.__context__
    return " <- ".join(parts)


def _describe_one(exc: BaseException) -> str:
    description = f"{type(exc).__name__} at {_last_frame_location(exc.__traceback__)}"
    if isinstance(exc, ValidationError):
        details = format_validation_errors(exc.errors())
        if details:
            description = f"{description} [{details}]"
    return description


def _last_frame_location(tb: TracebackType | None) -> str:
    """Return the innermost frame as ``file:line in function``."""
    if tb is None:
        return "unknown location"
    frames = traceback.extract_tb(tb)
    if not frames:
        return "unknown location"
    frame = frames[-1]
    return f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}"
