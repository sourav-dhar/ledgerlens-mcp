"""The gateway's error taxonomy, and how a failed tool call reaches the client (LLD §4).

A tool failure is returned as an MCP result with ``isError: true`` and a structured body,
so the agent can reason about it: a stable ``code``, a ``message`` safe to show, the
``trace_id`` to quote, and ``retry_after_s`` or ``dependency`` when they apply. Bodies never
carry stack traces, SQL or upstream payloads; anything unexpected becomes ``internal``.

Protocol-level failures (``unauthenticated``, ``rate_limited``, ``overloaded``) are HTTP
responses, not tool results; they share the codes so logs and metrics use one vocabulary.
"""

import json
import logging
import uuid
from enum import StrEnum
from typing import ClassVar, override

from fastmcp.exceptions import ToolError, ValidationError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
from mcp import types as mt
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    INVALID_ARGUMENT = "invalid_argument"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    DECLINED = "declined"
    RATE_LIMITED = "rate_limited"
    OVERLOADED = "overloaded"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    INTERNAL = "internal"


class ErrorBody(BaseModel):
    """What the client sees of a failure."""

    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    trace_id: str
    retry_after_s: float | None = None
    dependency: str | None = None


class GatewayError(ToolError):
    """A failure the caller can act on; its message is safe to show them.

    It subclasses FastMCP's ``ToolError`` so FastMCP passes it through unmasked, logged at
    ``level`` rather than as a crash with a traceback.
    """

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL
    level: ClassVar[int] = logging.WARNING

    def __init__(
        self, message: str, *, retry_after_s: float | None = None, dependency: str | None = None
    ) -> None:
        super().__init__(message, log_level=self.level)
        self.message = message
        self.retry_after_s = retry_after_s
        self.dependency = dependency


class UnauthenticatedError(GatewayError):
    """No verified identity came with the call.

    Over HTTP the authentication layer answers `401` before any tool runs; this is the
    fail-closed answer for any path that reaches a tool without one.
    """

    code = ErrorCode.UNAUTHENTICATED


class ForbiddenError(GatewayError):
    """A scope is missing, or a document is above the caller's ceiling."""

    code = ErrorCode.FORBIDDEN


class InvalidArgumentError(GatewayError):
    code = ErrorCode.INVALID_ARGUMENT
    level = logging.INFO


class NotFoundError(GatewayError):
    """Absent, or not visible to the caller: the two are indistinguishable on purpose."""

    code = ErrorCode.NOT_FOUND
    level = logging.INFO


class ConflictError(GatewayError):
    """An idempotency key reused for another request, or a change the domain refuses."""

    code = ErrorCode.CONFLICT
    level = logging.INFO


class DeclinedError(GatewayError):
    """The user did not agree to a write, so nothing was written."""

    code = ErrorCode.DECLINED
    level = logging.INFO


class DeadlineExceededError(GatewayError):
    code = ErrorCode.DEADLINE_EXCEEDED


class DependencyUnavailableError(GatewayError):
    """A downstream failed after retries, or its breaker is open."""

    code = ErrorCode.DEPENDENCY_UNAVAILABLE


class InternalError(GatewayError):
    """A defect: the caller learns only the trace ID."""

    code = ErrorCode.INTERNAL
    level = logging.ERROR


INTERNAL_MESSAGE = "an unexpected error occurred; quote the trace_id when reporting it"


def _describe(exc: ValidationError) -> str:
    """Which arguments failed and why, without echoing their values."""
    cause = exc.__cause__
    if not isinstance(cause, PydanticValidationError):
        return "the arguments are invalid"
    problems = [
        f"{'.'.join(str(part) for part in error['loc']) or 'arguments'}: {error['msg']}"
        for error in cause.errors(include_url=False, include_input=False, include_context=False)
    ]
    return "; ".join(problems)


def _result(body: ErrorBody) -> ToolResult:
    """The body as structured content, and as JSON text for clients that read only text."""
    payload = {"error": body.model_dump(mode="json", exclude_none=True)}
    return ToolResult(
        content=[mt.TextContent(type="text", text=json.dumps(payload))],
        structured_content=payload,
        is_error=True,
    )


class ErrorResults(Middleware):
    """Outermost tool middleware: every failure becomes a structured error result."""

    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        trace_id = uuid.uuid4().hex
        try:
            return await call_next(context)
        except GatewayError as exc:
            body = ErrorBody(
                code=exc.code,
                message=exc.message,
                trace_id=trace_id,
                retry_after_s=exc.retry_after_s,
                dependency=exc.dependency,
            )
        except ValidationError as exc:
            body = ErrorBody(
                code=ErrorCode.INVALID_ARGUMENT, message=_describe(exc), trace_id=trace_id
            )
        except ToolError:
            # FastMCP has already logged the original exception with its traceback.
            logger.error(  # noqa: TRY400
                "tool %s failed unexpectedly; trace_id=%s", context.message.name, trace_id
            )
            body = ErrorBody(code=ErrorCode.INTERNAL, message=INTERNAL_MESSAGE, trace_id=trace_id)
        return _result(body)
