"""`/v1/customers/{customer_id}/kyc`: a Customer's KYC status and document metadata."""

from typing import Any

from fastapi import APIRouter

from core_api.deps import CallerDep, DatabaseDep, checked_id, require
from core_api.errors import NotFoundError
from core_api.repositories.kyc import KycRepository
from core_api.schemas.kyc import KycDocumentList, KycProfile
from kosha_domain.ids import IdPrefix

router = APIRouter(prefix="/v1/customers/{customer_id}/kyc", tags=["kyc"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Invalid argument"},
    404: {"description": "No such Customer, or no KYC profile"},
    503: {"description": "Database unavailable; retry shortly"},
    504: {"description": "Deadline exceeded"},
}


def _customer_not_found(customer_id: str) -> NotFoundError:
    return NotFoundError(f"customer {customer_id} not found")


@router.get("", summary="Get a Customer's KYC status", responses=_ERRORS)
async def get_kyc_status(customer_id: str, caller: CallerDep, database: DatabaseDep) -> KycProfile:
    """The profile in force (the newest) with its status history; PAN and Aadhaar as last 4."""
    checked_id(customer_id, IdPrefix.CUSTOMER, name="customer_id")
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        kyc = KycRepository(conn)
        profile = await kyc.current_profile(customer_id)
        if profile is None and not await kyc.customer_exists(customer_id):
            raise _customer_not_found(customer_id)
    if profile is None:
        msg = f"customer {customer_id} has no KYC profile"
        raise NotFoundError(msg)
    return profile


@router.get("/documents", summary="List a Customer's KYC documents", responses=_ERRORS)
async def list_kyc_documents(
    customer_id: str, caller: CallerDep, database: DatabaseDep
) -> KycDocumentList:
    """Metadata of every document, newest first; the documents themselves are never served."""
    checked_id(customer_id, IdPrefix.CUSTOMER, name="customer_id")
    async with require(database).unit_of_work(caller, read_only=True) as conn:
        kyc = KycRepository(conn)
        if not await kyc.customer_exists(customer_id):
            raise _customer_not_found(customer_id)
        documents = await kyc.documents(customer_id)
    return KycDocumentList(documents=documents)
