"""Budget API routes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import require_admin_api_key
from src.core.budget_service import get_budget_service

router = APIRouter()


class BudgetStatus(BaseModel):
    """Current budget status."""

    current_spend: float
    limit: float


class SetLimitRequest(BaseModel):
    """Request to set budget limit."""

    limit: float


class SetLimitResponse(BaseModel):
    """Response after setting budget limit."""

    status: str
    new_limit: float


@router.get(
    "/budget",
    response_model=BudgetStatus,
    dependencies=[Depends(require_admin_api_key)],
)
def get_budget() -> BudgetStatus:
    """Get current budget status including spend and limit."""
    service = get_budget_service()
    return BudgetStatus(**service.get_status())


@router.post(
    "/budget/limit",
    response_model=SetLimitResponse,
    dependencies=[Depends(require_admin_api_key)],
)
def set_budget_limit(request: SetLimitRequest) -> SetLimitResponse:
    """Set the daily budget limit.

    Set to 0.0 for "free only" mode.
    """
    service = get_budget_service()
    service.set_limit(request.limit)
    return SetLimitResponse(status="ok", new_limit=request.limit)


@router.post("/budget/reset", dependencies=[Depends(require_admin_api_key)])
def reset_budget() -> dict:
    """Reset today's spending to zero (admin only)."""
    service = get_budget_service()
    service.reset_daily_spend()
    return {"status": "ok", "message": "Daily spend reset to 0"}
