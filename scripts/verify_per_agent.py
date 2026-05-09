import os
import sys
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.getcwd())

# --- MOCKING START ---
# We need to mock 'crewai' as a package that can have submodules if needed.
# But simply putting it in sys.modules usually works.
# The issue might be that some code does 'from crewai.tools import ...' which implies crewai is a package.
# If sys.modules['crewai'] is a MagicMock, accessing .tools returns a MagicMock, but import mechanics might fail check.
# We will pre-seed 'crewai.tools'.

mock_crewai = MagicMock()
mock_crewai.__path__ = []  # Mark as package
sys.modules["crewai"] = mock_crewai

mock_crewai_tools = MagicMock()
sys.modules["crewai_tools"] = mock_crewai_tools
# Also populate crewai.tools just in case
sys.modules["crewai.tools"] = mock_crewai_tools
# And attach it
mock_crewai.tools = mock_crewai_tools


# Mock Agent class specifically
class MockAgent:
    def __init__(self, role, goal, backstory, tools, llm, **_kwargs):
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.tools = tools
        self.llm = llm


mock_crewai.Agent = MockAgent

# Other deps
MOCKED_DEPS = [
    "duckduckgo_search",
    "trafilatura",
    "newspaper",
    "feedparser",
    "lancedb",
    "chromadb",
    "litellm",
    "pydantic_settings",
]
for dep in MOCKED_DEPS:
    sys.modules[dep] = MagicMock()

# Mock Config Settings (CRITICAL for SQLAlchemy)
mock_config_module = MagicMock()
mock_settings = MagicMock()
# Use a specific test DB file
TEST_DB_URL = "sqlite:///./test_agent_verify.db"
mock_settings.database_url = TEST_DB_URL
mock_settings.debug = False
mock_settings.llm_provider = "ollama"
mock_settings.selected_model = "llama3"
mock_settings.config_dir = MagicMock()
mock_settings.config_dir.__truediv__.return_value = "dummy_path"

mock_config_module.settings = mock_settings
# We must mock src.core.config BEFORE importing anything from src that uses it
sys.modules["src.core.config"] = mock_config_module

# --- MOCKING END ---

# Clean up previous test DB
if os.path.exists("test_agent_verify.db"):
    os.remove("test_agent_verify.db")

try:
    from src.agents.profile_reader import create_profile_reader_agent
    from src.database.session import get_session, init_db
    from src.services.agent_config_service import AgentConfigService
except ImportError as e:
    print(f"ImportError during setup: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)


def verify():
    print("Initializing DB...")
    try:
        init_db()
    except Exception as e:
        print(f"DB Init failed: {e}")
        import traceback

        traceback.print_exc()
        return

    # Open local session
    session = get_session()
    service = AgentConfigService(session)

    # Set config for profile_reader
    agent_name = "profile_reader"
    test_model = "ollama/verify-model-v2"
    print(f"Setting config for {agent_name} to model={test_model}...")
    service.set_config(agent_name=agent_name, model=test_model, provider="ollama")

    # Create agent
    print("Creating agent...")
    try:
        agent = create_profile_reader_agent()

        # Check
        print(f"Agent LLM: {agent.llm}")

        expected_substring = "verify-model-v2"

        if expected_substring in str(agent.llm):
            print(
                f"SUCCESS: Agent uses configured model! (Found '{expected_substring}' in '{agent.llm}')"
            )
        else:
            print(
                f"FAILURE: Agent uses {agent.llm}, expected to contain {expected_substring}"
            )

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    verify()
