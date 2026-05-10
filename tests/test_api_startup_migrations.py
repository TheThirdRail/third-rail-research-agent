import logging

import pytest

from src.api import main as api_main


@pytest.mark.parametrize(
    ("status", "expected_level", "expected_text"),
    [
        ("ok", logging.INFO, "Database is at Alembic head."),
        ("warn", logging.WARNING, "Run `research-agent init` to apply migrations."),
        ("error", logging.ERROR, "Could not inspect Alembic revision state."),
    ],
)
def test_log_migration_status_uses_status_severity(
    monkeypatch,
    caplog,
    status,
    expected_level,
    expected_text,
):
    detail = {
        "ok": "Database is at Alembic head.",
        "warn": "Database is not stamped with an Alembic revision.",
        "error": "Could not inspect Alembic revision state.",
    }[status]
    monkeypatch.setattr(
        api_main,
        "get_alembic_revision_status",
        lambda: (status, detail),
    )

    with caplog.at_level(logging.INFO, logger=api_main.logger.name):
        api_main._log_migration_status()

    assert any(
        record.levelno == expected_level and expected_text in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_lifespan_logs_migration_status_before_initializing(monkeypatch, caplog):
    calls: list[str] = []

    async def fake_lmstudio_check() -> None:
        calls.append("lmstudio")

    async def fake_close_model_registry() -> None:
        calls.append("close")

    monkeypatch.setattr(
        api_main, "register_task_timing", lambda: calls.append("timing")
    )
    monkeypatch.setattr(api_main, "_check_lmstudio_connectivity", fake_lmstudio_check)
    monkeypatch.setattr(
        api_main,
        "get_alembic_revision_status",
        lambda: ("warn", "Database is not stamped with an Alembic revision."),
    )
    monkeypatch.setattr(api_main, "init_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(api_main, "close_model_registry", fake_close_model_registry)

    with caplog.at_level(logging.WARNING, logger=api_main.logger.name):
        async with api_main.lifespan(api_main.app):
            calls.append("running")

    assert calls == ["timing", "lmstudio", "init_db", "running", "close"]
    assert "Database is not stamped with an Alembic revision." in caplog.text
