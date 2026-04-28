"""
Tests for the ingestion helper functions that don't require external services.
"""

from __future__ import annotations

import sys
import os

# Ensure the backend directory is on the path so we can import modules directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest import _detect_clause_type, _is_header_line


class TestDetectClauseType:
    """Tests for the clause-type keyword detector."""

    def test_liability_detected(self):
        text = "The company's total liability shall not exceed the fees paid."
        assert _detect_clause_type(text) == "liability"

    def test_termination_detected(self):
        text = "Either party may terminate this agreement upon 30 days' written notice."
        assert _detect_clause_type(text) == "termination"

    def test_payment_detected(self):
        text = "All invoices are due and payable within 30 days."
        assert _detect_clause_type(text) == "payment"

    def test_ip_detected(self):
        text = "All intellectual property created under this agreement belongs to Client."
        assert _detect_clause_type(text) == "IP"

    def test_confidentiality_detected(self):
        text = "Recipient agrees to keep all confidential information strictly private."
        assert _detect_clause_type(text) == "confidentiality"

    def test_auto_renewal_detected(self):
        text = "This agreement will auto-renew annually unless cancelled in writing."
        assert _detect_clause_type(text) == "auto-renewal"

    def test_indemnification_detected(self):
        text = "Vendor shall indemnify and hold harmless Client from any third-party claims."
        assert _detect_clause_type(text) == "indemnification"

    def test_other_for_unknown(self):
        text = "The parties agree to meet quarterly to review progress."
        assert _detect_clause_type(text) == "other"

    def test_case_insensitive(self):
        text = "LIMITATION OF LIABILITY: In no event shall..."
        assert _detect_clause_type(text) == "liability"


class TestIsHeaderLine:
    """Tests for the section header detector."""

    def test_article_header(self):
        assert _is_header_line("Article 3. Definitions") is True

    def test_section_header(self):
        assert _is_header_line("Section 1.2 Payment Terms") is True

    def test_clause_header(self):
        assert _is_header_line("Clause 5. Termination") is True

    def test_numbered_header(self):
        assert _is_header_line("1. Definitions") is True

    def test_all_caps_header(self):
        assert _is_header_line("LIMITATION OF LIABILITY") is True

    def test_normal_sentence_not_header(self):
        assert _is_header_line("The vendor agrees to provide services.") is False

    def test_short_line_not_header(self):
        assert _is_header_line("by") is False

    def test_exhibit_header(self):
        assert _is_header_line("Exhibit A. Scope of Work") is True
