import sys
import os
import pytest
from unittest.mock import MagicMock

# --- MOCKING START ---
# We verify logic without needing heavy dependencies
MOCKED_MODULES = [
    "crewai",
    "crewai_tools",
    "duckduckgo_search",
    "trafilatura",
    "newspaper",
    "feedparser",
    "yt_dlp",
    "lancedb",
    "chromadb",
    "litellm",
    "pydantic_settings",
]

# Apply mocks to sys.modules
for mod_name in MOCKED_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Setup CrewAI mocks
mock_crewai = MagicMock()
mock_crewai.__path__ = []
sys.modules["crewai"] = mock_crewai
sys.modules["crewai.tools"] = MagicMock()


class MockAgent:
    def __init__(self, role, goal, backstory, tools, llm, **kwargs):
        self.role = role
        self.llm = llm


mock_crewai.Agent = MockAgent

# Mock Settings
mock_config_module = MagicMock()
mock_settings = MagicMock()
mock_settings.database_url = "sqlite:///./test_agent_flow.db"
mock_settings.debug = False
mock_settings.llm_provider = "ollama"
mock_settings.selected_model = "llama3"
mock_settings.config_dir = MagicMock()
mock_settings.config_dir.__truediv__.return_value = "dummy_path"
mock_config_module.settings = mock_settings
sys.modules["src.core.config"] = mock_config_module

# --- END MOCKS ---

from src.database.session import init_db, get_session
from src.services.agent_config_service import AgentConfigService
from src.agents.profile_reader import create_profile_reader_agent


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    if os.path.exists("test_agent_flow.db"):
        os.remove("test_agent_flow.db")
    init_db()
    yield
    if os.path.exists("test_agent_flow.db"):
        try:
            os.remove("test_agent_flow.db")
        except PermissionError:
            pass


def test_agent_config_flow():
    """Verify that agent configuration is loaded from DB and applied to Agent."""
    session = get_session()
    service = AgentConfigService(session)

    agent_name = "profile_reader"
    test_model = "ollama/test-model-v1"

    # Set config
    service.set_config(agent_name=agent_name, model=test_model, provider="ollama")

    # Create agent
    agent = create_profile_reader_agent()

    # Verify
    assert "test-model-v1" in str(agent.llm), f"Expected 'test-model-v1' in {agent.llm}"

    session.close()
