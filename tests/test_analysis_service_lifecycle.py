import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

import src.services as services_module
from src.api.main import app
from src.api.routes import analyze as analyze_route
from src.cli import main as cli_main
from src.services import analysis_service


class FakeSession:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def service_with_session(session: FakeSession) -> analysis_service.AnalysisService:
    service = object.__new__(analysis_service.AnalysisService)
    service._session = session
    service._closed = False
    return service


def test_analysis_service_context_manager_closes_session_after_success() -> None:
    session = FakeSession()
    service = service_with_session(session)

    with service as active:
        assert active is service

    service.close()

    assert session.close_calls == 1


def test_analysis_service_context_manager_closes_session_after_exception() -> None:
    session = FakeSession()
    service = service_with_session(session)

    with pytest.raises(RuntimeError), service:
        raise RuntimeError("boom")

    assert session.close_calls == 1


def test_api_read_helpers_close_service_when_missing(monkeypatch) -> None:
    class FakeAnalysisService:
        close_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            type(self).close_calls += 1

        def get_analysis(self, story_id: str):
            return None

        def get_diagnostics(self, story_id: str):
            return None

        def get_handoff(self, story_id: str, stage: str):
            return None

    monkeypatch.setattr(analyze_route, "AnalysisService", FakeAnalysisService)
    client = TestClient(app)

    for endpoint in (
        "/api/analysis/missing-story",
        "/api/analysis/missing-story/diagnostics",
        "/api/analysis/missing-story/handoff/post_retrieval",
    ):
        FakeAnalysisService.close_calls = 0
        response = client.get(endpoint)

        assert response.status_code == 404
        assert FakeAnalysisService.close_calls == 1


def test_cli_analyze_closes_service(monkeypatch) -> None:
    class FakeAnalysisService:
        close_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            type(self).close_calls += 1

        def analyze(self, description: str, url: str | None, options=None):
            return {"story_id": "story-1234", "report": "report body", "status": "ok"}

    monkeypatch.setattr(services_module, "AnalysisService", FakeAnalysisService)

    result = CliRunner().invoke(
        cli_main.cli,
        ["analyze", "--describe", "test story"],
    )

    assert result.exit_code == 0, result.output
    assert FakeAnalysisService.close_calls == 1


@pytest.mark.parametrize(
    ("args", "expected_output"),
    (
        (["diagnostics", "story-1234"], "No diagnostics found"),
        (["handoff", "story-1234", "post_retrieval"], "No handoff found"),
    ),
)
def test_cli_read_helpers_close_service_when_missing(
    monkeypatch,
    args: list[str],
    expected_output: str,
) -> None:
    class FakeAnalysisService:
        close_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            type(self).close_calls += 1

        def get_diagnostics(self, story_id: str):
            return None

        def get_handoff(self, story_id: str, stage: str):
            return None

    monkeypatch.setattr(services_module, "AnalysisService", FakeAnalysisService)

    result = CliRunner().invoke(cli_main.cli, args)

    assert result.exit_code != 0
    assert expected_output in result.output
    assert FakeAnalysisService.close_calls == 1
