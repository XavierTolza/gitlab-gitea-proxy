"""Rich API error with full request/response context for debugging."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ApiError(Exception):
    """Raised when an HTTP API call fails, carrying the full context."""

    method: str
    url: str
    request_payload: dict[str, Any] | None = None
    status_code: int | None = None
    response_body: str = ""
    response_json: Any = None

    def __str__(self) -> str:
        parts = [f"{self.method} {self.url}"]
        if self.status_code is not None:
            parts.append(f"→ HTTP {self.status_code}")
        if self.response_body:
            body = self.response_body
            if len(body) > 2000:
                body = body[:2000] + "…"
            parts.append(f"\n{body}")
        return " ".join(parts)

    @classmethod
    def from_httpx(
        cls,
        exc: httpx.HTTPStatusError | httpx.RequestError,
        method: str,
        url: str,
        request_payload: dict[str, Any] | None = None,
    ) -> ApiError:
        """Build a rich error from an httpx exception."""
        detail = cls(method=method, url=url, request_payload=request_payload)
        if isinstance(exc, httpx.HTTPStatusError):
            detail.status_code = exc.response.status_code
            detail.response_body = exc.response.text
            try:
                detail.response_json = exc.response.json()
            except Exception:
                pass
        else:
            # ConnectionError, TimeoutException, etc.
            detail.response_body = str(exc)
        return detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "request_payload": self.request_payload,
            "status_code": self.status_code,
            "response_body": self.response_body[:4000] if self.response_body else "",
            "response_json": self.response_json,
        }


def _redact_token(text: str) -> str:
    """Redact bearer tokens and sensitive data from a string for safe display."""
    import re

    text = re.sub(r"(Authorization:\s*token\s+)[^\s]+", r"\1***REDACTED***", text)
    text = re.sub(r"(PRIVATE-TOKEN:\s*)[^\s]+", r"\1***REDACTED***", text)
    text = re.sub(r'(clone_addr":\s*")[^"]*:([^@]+@)', r'\1***:***@', text)
    text = re.sub(r'("auth_token":\s*")[^"]+', r'\1***REDACTED***', text)
    return text


def format_error_for_display(error: ApiError | dict[str, Any] | None) -> str:
    """Render an error as a human-readable debug string."""
    if error is None:
        return ""
    if isinstance(error, dict):
        error = ApiError(**error)
    payload = json.dumps(error.request_payload, indent=2) if error.request_payload else "—"
    status = f"HTTP {error.status_code}" if error.status_code else "Connection error"
    body = error.response_body or "—"
    text = (
        f"Request:  {error.method} {error.url}\n"
        f"Payload:  {payload}\n"
        f"Status:   {status}\n"
        f"Response: {body}"
    )
    return _redact_token(text)