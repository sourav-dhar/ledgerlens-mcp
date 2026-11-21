"""Shapes every tool module uses: annotations, identifier types, the view base."""

from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from kosha_domain.ids import IdPrefix

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)


def _id(prefix: IdPrefix, entity: str) -> Any:
    return Field(
        pattern=rf"^{prefix.value}_[0-7][0-9A-HJKMNP-TV-Z]{{25}}$",
        description=f"A {entity} ID: `{prefix.value}_` followed by a ULID.",
    )


CustomerId = Annotated[str, _id(IdPrefix.CUSTOMER, "Customer")]


class View(BaseModel):
    """What a tool returns: published as its output schema, and masked before it leaves.

    Fields core-api adds are ignored until a view declares them, so the gateway publishes
    only what it chose to.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")
