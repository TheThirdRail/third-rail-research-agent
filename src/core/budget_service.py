"""Budget enforcement service for LLM spending.

Provides pre-flight budget checks and cost tracking to enforce
spending limits, including $0.00 "Free Only" mode.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database.models import DailySpend
from src.database.session import SessionLocal

SessionFactory = Callable[[], Session]

_daily_spend_create_lock = threading.Lock()


class BudgetService:
    """Service for managing LLM spending budgets.

    Tracks daily spending and enforces budget limits. When the budget
    is set to 0.0, only free models are allowed.
    """

    def __init__(
        self,
        session: Session | None = None,
        session_factory: SessionFactory | None = None,
    ) -> None:
        """Initialize budget service.

        Args:
            session: Optional externally managed SQLAlchemy session for tests.
            session_factory: Factory used for per-operation sessions.
        """
        self._external_session = session
        self._session_factory = session_factory or SessionLocal

    def _get_today_key(self) -> datetime:
        """Get the datetime key for today (midnight)."""
        today = date.today()
        return datetime(today.year, today.month, today.day)

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        """Yield either the injected session or a short-lived operation session."""
        if self._external_session is not None:
            yield self._external_session
            return

        session = self._session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _get_record(self, session: Session, today_key: datetime) -> DailySpend | None:
        return session.query(DailySpend).filter(DailySpend.date == today_key).first()

    def _get_or_create_today_record(
        self, session: Session, today_key: datetime
    ) -> DailySpend:
        record = self._get_record(session, today_key)
        if record is not None:
            return record

        with _daily_spend_create_lock:
            record = self._get_record(session, today_key)
            if record is not None:
                return record

            record = DailySpend(date=today_key, amount=0.0, budget_limit=0.0)
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                record = self._get_record(session, today_key)
                if record is None:
                    raise
            else:
                session.refresh(record)

        return record

    def get_today_record(self) -> DailySpend:
        """Get or create today's spending record.

        Returns:
            DailySpend record for today.
        """
        today_key = self._get_today_key()
        with self._session_scope() as session:
            return self._get_or_create_today_record(session, today_key)

    def can_afford(self, model_is_free: bool = False) -> bool:
        """Check if a request can be afforded within budget.

        Args:
            model_is_free: Whether the model being used is free.

        Returns:
            True if request is allowed, False if budget exceeded.
        """
        today_key = self._get_today_key()
        with self._session_scope() as session:
            record = self._get_or_create_today_record(session, today_key)

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

        today_key = self._get_today_key()
        with self._session_scope() as session:
            self._get_or_create_today_record(session, today_key)
            session.execute(
                update(DailySpend)
                .where(DailySpend.date == today_key)
                .values(amount=DailySpend.amount + cost)
            )
            session.commit()

    def set_limit(self, limit: float) -> None:
        """Set the daily budget limit.

        Args:
            limit: New budget limit in USD. Use 0.0 for free-only mode.
        """
        today_key = self._get_today_key()
        with self._session_scope() as session:
            self._get_or_create_today_record(session, today_key)
            session.execute(
                update(DailySpend)
                .where(DailySpend.date == today_key)
                .values(budget_limit=max(0.0, limit))
            )
            session.commit()

    def get_status(self) -> dict[str, float]:
        """Get current budget status.

        Returns:
            Dict with current_spend and limit.
        """
        today_key = self._get_today_key()
        with self._session_scope() as session:
            record = self._get_or_create_today_record(session, today_key)
            return {
                "current_spend": record.amount,
                "limit": record.budget_limit,
            }

    def reset_daily_spend(self) -> None:
        """Reset today's spending to zero (for testing/admin)."""
        today_key = self._get_today_key()
        with self._session_scope() as session:
            self._get_or_create_today_record(session, today_key)
            session.execute(
                update(DailySpend)
                .where(DailySpend.date == today_key)
                .values(amount=0.0)
            )
            session.commit()


# Singleton instance
_budget_service: BudgetService | None = None


def get_budget_service() -> BudgetService:
    """Get the singleton budget service instance.

    Returns:
        Configured BudgetService instance.
    """
    global _budget_service
    if _budget_service is None:
        _budget_service = BudgetService(session_factory=SessionLocal)
    return _budget_service
