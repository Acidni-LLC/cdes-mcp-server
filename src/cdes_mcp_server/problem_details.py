"""RFC 7807 Problem Details for MCP tool responses.

MCP tools return strings, not HTTP responses. This module provides
structured error JSON that LLM clients (VS Code Copilot, Claude) can
parse to present meaningful errors instead of raw exception messages.

CDES MCP tools are synchronous and work with local schema/reference
files -- the error surface is FileNotFoundError, JSONDecodeError,
jsonschema errors, and general exceptions.

Reference: https://api.acidni.net/problems/
Standard:  acidni-config/.github/standards/rfc7807/
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# -- Problem type base URL ---------------------------------------------

PROBLEM_BASE_URL = "https://api.acidni.net/problems"


# -- Models -------------------------------------------------------------

class ProblemAction(BaseModel):
    """Recovery action hint for LLM clients."""

    type: str = Field(description="openUrl | retry | signIn")
    label: str = Field(description="Human-readable button label")
    url: str | None = Field(default=None, description="URL for openUrl actions")


class FieldError(BaseModel):
    """Individual field-level validation error."""

    field: str
    message: str
    code: str | None = None


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details with Acidni extensions."""

    type: str = Field(default=f"{PROBLEM_BASE_URL}/internal-error")
    title: str = Field(default="Internal Server Error")
    status: int = Field(default=500)
    detail: str | None = None
    instance: str | None = None
    code: str | None = Field(default=None, description="Machine-readable SCREAMING_SNAKE")
    correlation_id: str | None = None
    trace_id: str | None = None
    action: ProblemAction | None = None
    errors: list[FieldError] | None = None
    retry_after_seconds: int | None = None


# -- Defaults per status code -------------------------------------------

_DEFAULTS: dict[int, dict[str, str]] = {
    400: {"title": "Bad Request", "slug": "bad-request", "code": "BAD_REQUEST"},
    404: {"title": "Not Found", "slug": "not-found", "code": "NOT_FOUND"},
    422: {"title": "Validation Error", "slug": "validation-error", "code": "VALIDATION_ERROR"},
    500: {"title": "Internal Server Error", "slug": "internal-error", "code": "INTERNAL_ERROR"},
    502: {"title": "Bad Gateway", "slug": "bad-gateway", "code": "BAD_GATEWAY"},
    503: {"title": "Service Unavailable", "slug": "service-unavailable", "code": "SERVICE_UNAVAILABLE"},
}


# -- Build helpers ------------------------------------------------------

def build_problem(
    status: int = 500,
    *,
    title: str | None = None,
    detail: str | None = None,
    code: str | None = None,
    instance: str | None = None,
    action: ProblemAction | None = None,
    errors: list[FieldError] | None = None,
    retry_after_seconds: int | None = None,
    correlation_id: str | None = None,
) -> ProblemDetail:
    """Build a ProblemDetail with sensible defaults."""
    defaults = _DEFAULTS.get(status, _DEFAULTS[500])
    return ProblemDetail(
        type=f"{PROBLEM_BASE_URL}/{defaults['slug']}",
        title=title or defaults["title"],
        status=status,
        detail=detail,
        instance=instance,
        code=code or defaults["code"],
        correlation_id=correlation_id or uuid.uuid4().hex[:16],
        action=action,
        errors=errors,
        retry_after_seconds=retry_after_seconds,
    )


def problem_json(
    status: int = 500,
    **kwargs: Any,
) -> str:
    """Build a ProblemDetail and return it as a JSON string."""
    problem = build_problem(status, **kwargs)
    _log_problem(problem, tool_name=kwargs.get("instance", ""))
    return json.dumps(
        problem.model_dump(exclude_none=True),
        default=str,
    )


# -- Logging ------------------------------------------------------------

def _log_problem(
    problem: ProblemDetail,
    *,
    tool_name: str = "",
    exc: BaseException | None = None,
) -> None:
    """Log a problem with structured properties for App Insights."""
    level = logging.WARNING if problem.status < 500 else logging.ERROR
    extra: dict[str, Any] = {
        "custom_dimensions": {
            "problem_type": problem.type,
            "problem_code": problem.code or "",
            "problem_status": problem.status,
            "correlation_id": problem.correlation_id or "",
            "tool_name": tool_name,
        }
    }
    logger.log(
        level,
        "Problem [%s] %s: %s",
        problem.code,
        problem.title,
        problem.detail or "(no detail)",
        extra=extra,
        exc_info=exc if problem.status >= 500 else None,
    )


# -- MCP tool error wrapper (synchronous) --------------------------------

def safe_tool_call(
    fn: Callable[..., str],
    *args: Any,
    tool_name: str,
    context: str = "",
    **kwargs: Any,
) -> str:
    """Wrap a synchronous MCP tool function with RFC 7807 error handling.

    Usage::

        @mcp.tool()
        def get_schema(name: str) -> str:
            return safe_tool_call(
                _get_schema_impl, name,
                tool_name="get_schema",
                context=f"name={name}",
            )

    On success the raw result string is returned unchanged.
    On failure a structured RFC 7807 ProblemDetail JSON string is returned
    so the LLM client can present a meaningful error to the user.
    """
    try:
        return fn(*args, **kwargs)

    except FileNotFoundError as exc:
        problem = build_problem(
            status=404,
            title="Resource Not Found",
            detail=str(exc),
            code="SCHEMA_NOT_FOUND" if "schema" in str(exc).lower() else "REFERENCE_NOT_FOUND",
            instance=f"/mcp/tool/{tool_name}",
        )
        _log_problem(problem, tool_name=tool_name, exc=exc)
        return json.dumps(problem.model_dump(exclude_none=True), default=str)

    except json.JSONDecodeError as exc:
        problem = build_problem(
            status=500,
            title="Data Corruption",
            detail=f"Failed to parse JSON data in {tool_name}: {exc.msg}",
            code="DATA_CORRUPTION",
            instance=f"/mcp/tool/{tool_name}",
            action=ProblemAction(type="retry", label="Sync schemas from GitHub"),
        )
        _log_problem(problem, tool_name=tool_name, exc=exc)
        return json.dumps(problem.model_dump(exclude_none=True), default=str)

    except KeyError as exc:
        problem = build_problem(
            status=400,
            title="Invalid Reference Key",
            detail=f"Key not found in reference data: {exc}",
            code="INVALID_KEY",
            instance=f"/mcp/tool/{tool_name}",
        )
        _log_problem(problem, tool_name=tool_name, exc=exc)
        return json.dumps(problem.model_dump(exclude_none=True), default=str)

    except Exception as exc:
        detail_msg = f"Unexpected error in {tool_name}"
        if context:
            detail_msg += f" ({context})"
        detail_msg += f": {type(exc).__name__}: {exc}"

        problem = build_problem(
            status=500,
            detail=detail_msg,
            code="CDES_INTERNAL_ERROR",
            instance=f"/mcp/tool/{tool_name}",
            action=ProblemAction(type="retry", label="Retry"),
        )
        _log_problem(problem, tool_name=tool_name, exc=exc)
        return json.dumps(problem.model_dump(exclude_none=True), default=str)
