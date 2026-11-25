"""Role-aware masking of personal data (LLD §7): a pure function of payload and scopes.

core-api returns values unmasked; the gateway decides what each caller sees. A view model
declares, in a field's type, how the field is masked and which scope reveals it:

    class CustomerView(BaseModel):
        mobile: Mobile  # "******7890" unless the caller holds kyc:pii

and ``mask`` applies every declaration in a model, nested models and lists included.
Declaring the rule on the type keeps it next to the field, where a reviewer sees it, and
lets a guard test require one on every field that holds personal data.
"""

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, cast, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from mcp_gateway.auth.scopes import Scope


@dataclass(frozen=True, slots=True)
class Masked:
    """Field metadata: ``style`` is what a caller without ``unless`` sees; never revealed
    when ``unless`` is ``None``."""

    style: Callable[[str], str]
    unless: Scope | None = None

    def reveals_to(self, scopes: Collection[Scope]) -> bool:
        return self.unless is not None and self.unless in scopes


@dataclass(frozen=True, slots=True)
class Withheld:
    """Field metadata: the value is left out (``None``) unless the caller holds ``unless``.

    For data only some Roles need at all, such as a device's IP address or location.
    """

    unless: Scope

    def style(self, _value: object) -> None:
        return None

    def reveals_to(self, scopes: Collection[Scope]) -> bool:
        return self.unless in scopes


type Rule = Masked | Withheld


def _last4(prefix: str) -> Callable[[str], str]:
    """A fixed-width prefix and the last four characters: the length is hidden too."""

    def style(value: str) -> str:
        return prefix + value[-4:]

    return style


def _email(value: str) -> str:
    local, at, domain = value.rpartition("@")
    return f"{local[:1]}****@{domain}" if at else "****"


def _vpa(value: str) -> str:
    handle, at, provider = value.rpartition("@")
    # Trailing asterisks are an earlier mask, so masking a masked VPA changes nothing.
    return f"{handle.rstrip('*')[:2]}***@{provider}" if at else "***"


def _year(value: str) -> str:
    return value[:4]


Mobile = Annotated[str, Masked(_last4("******"), unless=Scope.KYC_PII)]
Email = Annotated[str, Masked(_email, unless=Scope.KYC_PII)]
BirthDate = Annotated[str, Masked(_year, unless=Scope.KYC_PII)]
"""An ISO date; the year alone unless the caller holds ``kyc:pii``."""
Pan = Annotated[str, Masked(_last4("******"), unless=Scope.KYC_PII)]
Aadhaar = Annotated[str, Masked(_last4("XXXX XXXX "))]
"""Only the last four digits are ever stored, so nothing can reveal more."""
AccountNumber = Annotated[str, Masked(_last4("XXXXXX"))]
"""Never revealed through MCP."""
CounterpartyVpa = Annotated[str, Masked(_vpa, unless=Scope.AML_READ)]
OwnVpa = Annotated[str, Masked(_vpa, unless=Scope.KYC_PII)]
"""A Customer's own VPA: often their mobile number (``9876543210@kosha``), so masked like it."""
AML_ONLY = Withheld(unless=Scope.AML_READ)
"""Device and location detail: ``Annotated[str | None, AML_ONLY]`` is ``None`` without aml:read."""


def _rule(field: FieldInfo) -> Rule | None:
    """The field's rule, whether declared as ``Mobile`` or as ``Mobile | None``."""
    for item in field.metadata:
        if isinstance(item, Masked | Withheld):
            return item
    for member in get_args(field.annotation):
        if get_origin(member) is Annotated:
            for item in member.__metadata__:
                if isinstance(item, Masked | Withheld):
                    return item
    return None


def masked_fields(model: type[BaseModel]) -> Mapping[str, Rule]:
    """The masking rule of each field of ``model`` that has one."""
    return {
        name: rule
        for name, field in model.model_fields.items()
        if (rule := _rule(field)) is not None
    }


def _nested(value: Any, scopes: Collection[Scope]) -> Any:
    match value:
        case BaseModel():
            return mask(value, scopes)
        case list():
            return [_nested(item, scopes) for item in cast("list[Any]", value)]
        case _:
            return value


def mask[M: BaseModel](model: M, scopes: Collection[Scope]) -> M:
    """A copy of ``model`` with every field ``scopes`` do not reveal in its masked form."""
    rules = masked_fields(type(model))
    updates: dict[str, Any] = {}
    for name in type(model).model_fields:
        value = getattr(model, name)
        if name in rules:
            if value is not None and not rules[name].reveals_to(scopes):
                updates[name] = rules[name].style(value)
        else:
            updates[name] = _nested(value, scopes)
    return model.model_copy(update=updates)
