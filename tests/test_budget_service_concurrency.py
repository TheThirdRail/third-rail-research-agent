from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.budget_service import BudgetService
from src.database.models import Base, DailySpend


def _session_factory(tmp_path, *, session_class=Session):
    db_path = tmp_path / "budget.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, class_=session_class)


def test_concurrent_track_spend_uses_atomic_increment(tmp_path):
    factory = _session_factory(tmp_path)
    service = BudgetService(session_factory=factory)
    service.set_limit(1.0)

    with ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(lambda _index: service.track_spend(0.01), range(10)))

    assert service.get_status()["current_spend"] == pytest.approx(0.10)


def test_zero_and_negative_spend_do_not_create_usage(tmp_path):
    factory = _session_factory(tmp_path)
    service = BudgetService(session_factory=factory)

    service.track_spend(0)
    service.track_spend(-1)

    with factory() as session:
        assert session.query(DailySpend).count() == 0


def test_free_only_budget_behavior_is_preserved(tmp_path):
    factory = _session_factory(tmp_path)
    service = BudgetService(session_factory=factory)

    service.set_limit(-1)

    assert service.can_afford(model_is_free=True) is True
    assert service.can_afford(model_is_free=False) is False
    assert service.get_status() == {"current_spend": 0.0, "limit": 0.0}


def test_default_service_operations_close_sessions(tmp_path):
    closed_sessions = []

    class TrackingSession(Session):
        def close(self):
            closed_sessions.append(id(self))
            super().close()

    factory = _session_factory(tmp_path, session_class=TrackingSession)
    service = BudgetService(session_factory=factory)

    service.set_limit(2.0)
    service.track_spend(0.25)
    status = service.get_status()

    assert status == {"current_spend": 0.25, "limit": 2.0}
    assert len(closed_sessions) >= 3


def test_injected_session_remains_usable_after_service_operation(tmp_path):
    factory = _session_factory(tmp_path)
    session = factory()
    service = BudgetService(session=session)

    service.set_limit(0.5)
    service.track_spend(0.1)

    assert session.query(DailySpend).count() == 1
    assert service.get_status()["current_spend"] == pytest.approx(0.1)

    session.close()
