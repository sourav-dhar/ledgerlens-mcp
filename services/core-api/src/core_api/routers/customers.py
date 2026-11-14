"""`/v1/customers`: find Customers and read their profiles."""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from core_api.deps import CallerDep, DatabaseDep, checked_id, require
from core_api.errors import InvalidArgumentError, NotFoundError
from core_api.repositories.customers import CustomerRepository, CustomerSearch
from core_api.schemas.customers import CustomerProfile, CustomerSearchResult
from kosha_domain.ids import IdPrefix

router = APIRouter(prefix="/v1/customers", tags=["customers"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Invalid argument"},
    503: {"description": "Database unavailable; retry shortly"},
    504: {"description": "Deadline exceeded"},
}


@router.get("", summary="Search Customers", responses=_ERRORS)
async def search_customers(
    *,
    caller: CallerDep,
    database: DatabaseDep,
    name: Annotated[
        str | None,
        Query(min_length=2, max_length=64, description="Part of the first and last name."),
    ] = None,
    cif_number: Annotated[str | None, Query(pattern=r"^\d{10}$")] = None,
    mobile_last4: Annotated[str | None, Query(pattern=r"^\d{4}$")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CustomerSearchResult:
    """Customers matching every criterion given, in name order."""
    criteria = CustomerSearch(name=name, cif_number=cif_number, mobile_last4=mobile_last4)
    if criteria.is_empty:
        msg = "give at least one of name, cif_number or mobile_last4"
        raise InvalidArgumentError(msg)
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        found = await CustomerRepository(conn).search(criteria, limit=limit)
    return CustomerSearchResult(customers=found)


@router.get(
    "/{customer_id}",
    summary="Get a Customer's profile",
    responses={**_ERRORS, 404: {"description": "No such Customer"}},
)
async def get_customer(
    customer_id: str, caller: CallerDep, database: DatabaseDep
) -> CustomerProfile:
    """The Customer with the Addresses in force today."""
    checked_id(customer_id, IdPrefix.CUSTOMER, name="customer_id")
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        profile = await CustomerRepository(conn).profile(customer_id)
    if profile is None:
        msg = f"customer {customer_id} not found"
        raise NotFoundError(msg)
    return profile
