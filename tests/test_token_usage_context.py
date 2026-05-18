from src.core.token_usage_context import (
    merge_token_usage_metadata,
    token_usage_agent_display_name,
    token_usage_run,
)


def test_merge_token_usage_metadata_uses_extra_body_and_preserves_existing_values():
    with token_usage_run("0005 - Trump Carlson story", "Trump Carlson story"):
        merged = merge_token_usage_metadata(
            {
                "extra_body": {
                    "metadata": {"agent_name": "CUSTOM_AGENT", "trace_id": "trace-1"},
                    "store": False,
                }
            },
            agent_name="profile_reader",
        )

    assert merged == {
        "extra_body": {
            "metadata": {
                "run_id": "0005 - Trump Carlson story",
                "run_text": "Trump Carlson story",
                "agent_name": "CUSTOM_AGENT",
                "trace_id": "trace-1",
            },
            "store": False,
        }
    }


def test_token_usage_agent_display_name_maps_hidden_services_to_ui_agents():
    assert token_usage_agent_display_name("semantic_query_expander") == "STORY_PARSER"
    assert token_usage_agent_display_name("bias_classifier") == "BIAS_CLASSIFIER"
