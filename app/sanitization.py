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

# Pydantic composes messages for its own constraints from the schema, so those
# messages describe the rule. A message raised by a field validator is written
# by code that had the value in hand, so it is not forwarded: a validator that
# interpolates the value would otherwise put the transcript back into the body
# and into the log. The guarantee covers the error types below plus the ones
# Pydantic generates; a custom Pydantic error type is not allowlisted and needs
# an explicit decision here before its message can be forwarded.
UNTRUSTED_VALIDATOR_MESSAGE = "Value rejected by a field rule"

_UNTRUSTED_ERROR_TYPES = frozenset({"value_error", "assertion_error"})

# A request can carry up to 100 messages, so a validation failure can repeat the
# same rule 100 times. The log keeps the shape of the failure, not a transcript
# of every rejected field.
MAX_LOGGED_ERRORS = 5


def sanitize_validation_errors(
    errors: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the rule that failed and drop the value that failed it.

    ``type``, ``loc`` and ``msg`` identify the failure without the data, which
    is what a client needs to fix the request and what an operator needs to
    recognise the rule. ``input``, ``ctx`` and the documentation ``url`` are
    discarded, and a message written by a field validator is replaced by a
    fixed text.
    """
    safe_errors: list[dict[str, Any]] = []
    for error in errors:
        error_type = str(error.get("type", "value_error"))
        message = str(error.get("msg", "Invalid value"))
        if error_type in _UNTRUSTED_ERROR_TYPES:
            message = UNTRUSTED_VALIDATOR_MESSAGE
        safe_errors.append(
            {
                "type": error_type,
                "loc": list(error.get("loc", ())),
                "msg": message,
            }
        )
    return safe_errors


def format_validation_errors(errors: Iterable[Mapping[str, Any]]) -> str:
    """Render sanitized errors as a single log line, capped at five rules."""
    safe_errors = sanitize_validation_errors(errors)
    line = "; ".join(
        f"{'/'.join(str(part) for part in error['loc'])} "
        f"[{error['type']}] {error['msg']}"
        for error in safe_errors[:MAX_LOGGED_ERRORS]
    )
    hidden = len(safe_errors) - MAX_LOGGED_ERRORS
    if hidden > 0:
        line = f"{line}; +{hidden} more"
    return line


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
