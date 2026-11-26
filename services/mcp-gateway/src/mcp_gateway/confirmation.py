"""Has the user agreed to this write? (LLD §3)

A client that can ask its user is asked through MCP elicitation, in whichever protocol era
the connection negotiated:

- 2026-07-28 and later have no server-initiated requests. The tool answers
  ``input_required`` with the question, and the client calls the tool again carrying the
  user's answer in ``input_responses``. No ``request_state`` is used, so the second leg may
  land on any gateway instance.
- Earlier eras ask with an ``elicitation/create`` request during the call.

Only a client that cannot ask its user may pass ``confirm: true`` instead. When the client
can ask, ``confirm`` is ignored: a model sets arguments, and only the client's own prompt
reaches the person.
"""

from fastmcp.server.context import Context
from fastmcp.server.elicitation import AcceptedElicitation, parse_elicit_response_type
from mcp_types import ElicitRequest, ElicitRequestFormParams, ElicitResult, InputRequiredResult
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

from mcp_gateway.errors import DeclinedError, InvalidArgumentError

QUESTION = "confirm"
"""The key of the gateway's question among a call's ``input_requests``."""

_ANSWER = parse_elicit_response_type(bool, response_title="Go ahead")
NOT_AGREED = "the user did not agree, so nothing was written"
NO_PROMPT = (
    "this write needs the user's agreement and this client cannot ask them: "
    "describe the write to the user and, once they agree, call again with confirm: true"
)


def _can_ask(ctx: Context) -> bool:
    capabilities = ctx.session.client_capabilities
    return capabilities is not None and capabilities.elicitation is not None


def _modern(ctx: Context) -> bool:
    request = ctx.request_context
    return request is not None and request.protocol_version in MODERN_PROTOCOL_VERSIONS


async def agreed(ctx: Context, question: str, *, confirm: bool) -> InputRequiredResult | None:
    """``None`` once the user has agreed to the write ``question`` describes.

    Returns:
        The question to return from the tool, when a 2026-07-28 client has yet to ask it.

    Raises:
        DeclinedError: the user said no, declined, or dismissed the question.
        InvalidArgumentError: the client cannot ask its user and ``confirm`` is not true.
    """
    if not _can_ask(ctx):
        if not confirm:
            raise InvalidArgumentError(NO_PROMPT)
        return None
    if _modern(ctx):
        answer = (ctx.input_responses or {}).get(QUESTION)
        if answer is None:
            params = ElicitRequestFormParams(message=question, requested_schema=_ANSWER.schema)
            return InputRequiredResult(input_requests={QUESTION: ElicitRequest(params=params)})
        yes = (
            isinstance(answer, ElicitResult)
            and answer.action == "accept"
            and (answer.content or {}).get("value") is True
        )
    else:
        result = await ctx.elicit(question, bool, response_title="Go ahead")
        yes = isinstance(result, AcceptedElicitation) and result.data is True
    if not yes:
        raise DeclinedError(NOT_AGREED)
    return None
