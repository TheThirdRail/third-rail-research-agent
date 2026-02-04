"""Budget enforcement service for LLM spending.

Provides pre-flight budget checks and cost tracking to enforce
spending limits, including $0.00 "Free Only" mode.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from src.database import get_session
from src.database.models import DailySpend

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class BudgetService:
    """Service for managing LLM spending budgets.

    Tracks daily spending and enforces budget limits. When the budget
    is set to 0.0, only free models are allowed.
    """

    def __init__(self, session: "Session | None" = None) -> None:
        """Initialize budget service.

        Args:
            session: Optional SQLAlchemy session. Creates new if not provided.
        """
        self._session = session or get_session()

    def _get_today_key(self) -> datetime:
        """Get the datetime key for today (midnight)."""
        today = date.today()
        return datetime(today.year, today.month, today.day)

    def get_today_record(self) -> DailySpend:
        """Get or create today's spending record.

        Returns:
            DailySpend record for today.
        """
        today_key = self._get_today_key()

        record = (
            self._session.query(DailySpend).filter(DailySpend.date == today_key).first()
        )

        if record is None:
            record = DailySpend(date=today_key, amount=0.0, budget_limit=0.0)
            self._session.add(record)
            self._session.commit()

        return record

    def can_afford(self, model_is_free: bool = False) -> bool:
        """Check if a request can be afforded within budget.

        Args:
            model_is_free: Whether the model being used is free.

        Returns:
            True if request is allowed, False if budget exceeded.
        """
        record = self.get_today_record()

        # If budget is 0.0 (free only mode), only allow free models
        if record.budget_limit == 0.0:
            return model_is_free

        # Otherwise check if we're under the limit
        return record.amount < record.budget_limit

    def track_spend(self, cost: float) -> None:
        """Record spending from a completed LLM call.

        Args:
            cost: Cost in USD of the completed request.
        """
        if cost <= 0:
            return

        record = self.get_today_record()
        record.amount += cost
        self._session.commit()

    def set_limit(self, limit: float) -> None:
        """Set the daily budget limit.

        Args:
            limit: New budget limit in USD. Use 0.0 for free-only mode.
        """
        record = self.get_today_record()
        record.budget_limit = max(0.0, limit)  # Ensure non-negative
        self._session.commit()

    def get_status(self) -> dict[str, float]:
        """Get current budget status.

        Returns:
            Dict with current_spend and limit.
        """
        record = self.get_today_record()
        return {
            "current_spend": record.amount,
            "limit": record.budget_limit,
        }

    def reset_daily_spend(self) -> None:
        """Reset today's spending to zero (for testing/admin)."""
        record = self.get_today_record()
        record.amount = 0.0
        self._session.commit()


# Singleton instance
_budget_service: BudgetService | None = None


def get_budget_service() -> BudgetService:
    """Get the singleton budget service instance.

    Returns:
        Configured BudgetService instance.
    """
    global _budget_service
    if _budget_service is None:
        _budget_service = BudgetService()
    return _budget_service
