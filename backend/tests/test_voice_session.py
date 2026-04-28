"""
Tests for the voice session helper functions.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from voice_session import build_session_config, SYSTEM_PROMPT


class TestBuildSessionConfig:
    """Tests for the xAI session configuration builder."""

    def test_returns_dict(self):
        config = build_session_config("test-collection-id")
        assert isinstance(config, dict)

    def test_model_set(self):
        config = build_session_config("abc")
        assert "model" in config

    def test_instructions_contain_system_prompt(self):
        config = build_session_config("abc")
        assert config["instructions"] == SYSTEM_PROMPT

    def test_turn_detection_is_server_vad(self):
        config = build_session_config("abc")
        assert config["turn_detection"]["type"] == "server_vad"

    def test_search_contract_tool_present(self):
        config = build_session_config("abc")
        tools = config.get("tools", [])
        tool_names = [t["name"] for t in tools]
        assert "search_contract" in tool_names

    def test_collection_id_in_metadata(self):
        cid = "my-collection-123"
        config = build_session_config(cid)
        assert config["metadata"]["collection_id"] == cid

    def test_modalities_include_audio(self):
        config = build_session_config("abc")
        assert "audio" in config["modalities"]

    def test_tool_parameters_have_query(self):
        config = build_session_config("abc")
        tools = config["tools"]
        search_tool = next(t for t in tools if t["name"] == "search_contract")
        assert "query" in search_tool["parameters"]["required"]
