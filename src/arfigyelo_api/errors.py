"""Exception hierarchy for the Árfigyelő API client.

All exceptions derive from :class:`ArfigyeloError`, so consumers can catch
one base class.
"""

from __future__ import annotations


class ArfigyeloError(Exception):
    """Base class for every error raised by this package."""


class ArfigyeloConnectionError(ArfigyeloError):
    """A transport-level failure while talking to the API."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ArfigyeloApiError(ArfigyeloError):
    """The API answered with its ``{"code": ..., "message": ...}`` error envelope."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status_code = status_code


class ArfigyeloUnexpectedResponseError(ArfigyeloError):
    """A response that is not valid API JSON: HTML/WAF pages, or a body that
    fails schema validation (e.g. the framework's default 404 shape)."""

    def __init__(self, status_code: int | None, body: str) -> None:
        super().__init__(f"unexpected response [status {status_code}]: {body[:200]}")
        self.status_code = status_code
        self.body = body


class ArfigyeloValidationError(ArfigyeloError, ValueError):
    """Invalid call arguments, rejected locally before any request is made.

    The API would answer these with a misleading ``500 INTERNAL_SERVER_ERROR``
    (see docs/adr/0003-client-side-prevalidation.md).
    """

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"invalid {field}: {reason}")
        self.field = field
        self.reason = reason
