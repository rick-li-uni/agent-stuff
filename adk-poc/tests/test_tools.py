"""
Unit tests for platform tools — no LLM, no DB, fast and deterministic.

Run: pytest adk-poc/tests/test_tools.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add adk-poc to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import (
    get_user,
    list_resources,
    grant_entitlement,
    check_entitlement,
    revoke_entitlement,
    list_available_tools,
    TOOL_REGISTRY,
    _ENTITLEMENTS,
)


# ---- User tools -------------------------------------------------------------

class TestGetUser:
    def test_found(self):
        result = get_user("alice@corp.com")
        assert result["status"] == "found"
        assert result["user"]["id"] == "u-001"
        assert result["user"]["name"] == "Alice"

    def test_not_found(self):
        result = get_user("nobody@corp.com")
        assert result["status"] == "not_found"
        assert result["email"] == "nobody@corp.com"

    def test_case_sensitive(self):
        result = get_user("Alice@corp.com")
        assert result["status"] == "not_found"


# ---- Resource tools ----------------------------------------------------------

class TestListResources:
    def test_all(self):
        result = list_resources()
        assert result["count"] == 2
        names = {r["name"] for r in result["resources"]}
        assert "billing-dashboard" in names
        assert "prod-database" in names

    def test_filter_by_type(self):
        result = list_resources("dashboard")
        assert result["count"] == 1
        assert result["resources"][0]["name"] == "billing-dashboard"

    def test_filter_no_match(self):
        result = list_resources("nonexistent")
        assert result["count"] == 0
        assert result["resources"] == []


# ---- Entitlement tools -------------------------------------------------------

class TestGrantEntitlement:
    def setup_method(self):
        _ENTITLEMENTS.clear()

    def test_grant_read(self):
        result = grant_entitlement("u-001", "r-001", "read")
        assert result["status"] == "granted"
        assert result["entitlement"]["level"] == "read"
        assert len(_ENTITLEMENTS) == 1

    def test_grant_write(self):
        result = grant_entitlement("u-001", "r-001", "write")
        assert result["status"] == "granted"
        assert result["entitlement"]["level"] == "write"

    def test_admin_blocked(self):
        result = grant_entitlement("u-001", "r-001", "admin")
        assert result["status"] == "rejected"
        assert "approval" in result["reason"].lower()
        assert len(_ENTITLEMENTS) == 0

    def test_multiple_grants(self):
        grant_entitlement("u-001", "r-001", "read")
        grant_entitlement("u-002", "r-002", "write")
        assert len(_ENTITLEMENTS) == 2


class TestCheckEntitlement:
    def setup_method(self):
        _ENTITLEMENTS.clear()

    def test_found(self):
        grant_entitlement("u-001", "r-001", "read")
        result = check_entitlement("u-001", "r-001")
        assert result["status"] == "found"
        assert result["entitlement"]["level"] == "read"

    def test_not_found(self):
        result = check_entitlement("u-001", "r-001")
        assert result["status"] == "none"


class TestRevokeEntitlement:
    def setup_method(self):
        _ENTITLEMENTS.clear()

    def test_revoke_existing(self):
        grant_entitlement("u-001", "r-001", "read")
        result = revoke_entitlement("u-001", "r-001")
        assert result["status"] == "revoked"
        assert result["removed"] == 1
        assert len(_ENTITLEMENTS) == 0

    def test_revoke_nonexistent(self):
        result = revoke_entitlement("u-001", "r-001")
        assert result["status"] == "not_found"
        assert result["removed"] == 0

    def test_revoke_only_matching(self):
        grant_entitlement("u-001", "r-001", "read")
        grant_entitlement("u-002", "r-002", "write")
        revoke_entitlement("u-001", "r-001")
        assert len(_ENTITLEMENTS) == 1
        assert _ENTITLEMENTS[0]["user_id"] == "u-002"


# ---- Tool registry -----------------------------------------------------------

class TestToolRegistry:
    def test_registry_not_empty(self):
        assert len(TOOL_REGISTRY) > 0

    def test_all_have_category_and_description(self):
        for name, info in TOOL_REGISTRY.items():
            assert "category" in info, f"{name} missing category"
            assert "description" in info, f"{name} missing description"

    def test_list_all(self):
        result = list_available_tools()
        assert result["count"] == len(TOOL_REGISTRY)

    def test_list_by_category(self):
        result = list_available_tools("platform")
        assert result["count"] > 0
        for name, info in result["tools"].items():
            assert info["category"] == "platform"

    def test_list_invalid_category(self):
        result = list_available_tools("nonexistent")
        assert result["count"] == 0


# ---- Write contribution file validation --------------------------------------

class TestWriteContributionValidation:
    """Test the file-extension and path-traversal guards without touching disk."""

    def test_rejects_python_files(self):
        from agent import save_contribution
        result = save_contribution(
            contribution_type="skill",
            name="test-skill",
            content="# test",
            author="tester",
            files='{"exploit.py": "import os; os.system(\\\"rm -rf /\\\")"}',
        )
        assert result["status"] == "rejected"
        assert ".py" in result["reason"]

    def test_rejects_shell_files(self):
        from agent import save_contribution
        result = save_contribution(
            contribution_type="skill",
            name="test-skill",
            content="# test",
            author="tester",
            files='{"run.sh": "#!/bin/bash"}',
        )
        assert result["status"] == "rejected"
        assert ".sh" in result["reason"]

    def test_allows_markdown(self):
        from agent import save_contribution
        # This will fail on DB connection, but we're testing the file validation
        # which happens BEFORE the DB call
        result = save_contribution(
            contribution_type="skill",
            name="test-skill",
            content="# test",
            author="tester",
            files='{"reference/api.md": "# API docs"}',
        )
        # If it got past validation, it'll error on DB — that's fine
        assert result.get("status") != "rejected" or "extension" not in result.get("reason", "")
