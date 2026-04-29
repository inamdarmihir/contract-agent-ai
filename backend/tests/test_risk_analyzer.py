"""
Tests for the risk analyser helper functions.
"""

from __future__ import annotations

import json
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from risk_analyzer import _analyse_chunk


class TestAnalyseChunk:
    """Tests for the per-chunk Grok risk analysis call."""

    def _make_client(self, content: str) -> MagicMock:
        """Return a mock OpenAI client that returns the given content string."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )
        return mock_client

    def test_valid_json_response(self):
        payload = {
            "risk_level": "high",
            "risk_reason": "Auto-renews without explicit notice requirement.",
            "plain_english": "The contract automatically continues every year.",
        }
        client = self._make_client(json.dumps(payload))
        result = _analyse_chunk(client, "This agreement auto-renews annually.")
        assert result["risk_level"] == "high"
        assert "auto-renew" in result["risk_reason"].lower() or "notice" in result["risk_reason"].lower()
        assert len(result["plain_english"]) > 0

    def test_json_with_markdown_fences(self):
        payload = {
            "risk_level": "medium",
            "risk_reason": "One-sided termination clause.",
            "plain_english": "Only the vendor can terminate.",
        }
        wrapped = f"```json\n{json.dumps(payload)}\n```"
        client = self._make_client(wrapped)
        result = _analyse_chunk(client, "Only the vendor may terminate.")
        assert result["risk_level"] == "medium"

    def test_invalid_json_fallback(self):
        client = self._make_client("not valid json at all")
        result = _analyse_chunk(client, "Some clause text.")
        # Should return a safe fallback rather than raising
        assert result["risk_level"] in {"high", "medium", "low"}
        assert result["risk_reason"] != ""

    def test_api_exception_fallback(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API timeout")
        result = _analyse_chunk(mock_client, "Some clause text.")
        assert result["risk_level"] == "low"
        assert result["risk_reason"] == "Analysis unavailable."

    def test_long_text_truncated(self):
        """Ensure very long text does not crash (truncated to 2000 chars internally)."""
        long_text = "word " * 1000
        payload = {"risk_level": "low", "risk_reason": "Standard.", "plain_english": "OK"}
        client = self._make_client(json.dumps(payload))
        result = _analyse_chunk(client, long_text)
        assert result["risk_level"] == "low"
