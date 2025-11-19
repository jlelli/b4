#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Tests for ReviewEngine."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from b4.review import ReviewEngine, ReviewResult
from b4.llm.base import LLMResponse, ToolCall, Message
from b4.mcp_client import SemcodeMCPClient
from b4.review_prompts import ReviewPromptsLoader


class TestReviewEngine:
    """Test ReviewEngine class."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock LLM provider."""
        provider = Mock()
        provider.name = 'mock-llm'
        provider.model = 'mock-model'
        return provider

    @pytest.fixture
    def mock_mcp_client(self):
        """Create a mock MCP client."""
        client = Mock(spec=SemcodeMCPClient)
        client.get_tools.return_value = {
            'find_function': {
                'name': 'find_function',
                'description': 'Find a function',
                'inputSchema': {'type': 'object', 'properties': {}}
            }
        }
        return client

    @pytest.fixture
    def mock_prompts_loader(self, tmp_path):
        """Create a mock prompts loader."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        (prompts_dir / "review-core.md").write_text("# Core Protocol")
        (prompts_dir / "technical-patterns.md").write_text("# Patterns")
        (prompts_dir / "scheduler.md").write_text("# Scheduler")

        return ReviewPromptsLoader(str(prompts_dir))

    def test_init(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test ReviewEngine initialization."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        assert engine.provider == mock_provider
        assert engine.mcp_client == mock_mcp_client
        assert engine.prompts_loader == mock_prompts_loader
        assert len(engine.tools) > 0

    def test_build_system_prompt(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test system prompt building."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        diff = """
diff --git a/kernel/sched/core.c b/kernel/sched/core.c
--- a/kernel/sched/core.c
+++ b/kernel/sched/core.c
@@ -100,1 +100,1 @@
-    schedule();
+    __schedule();
"""

        system_prompt = engine.build_system_prompt(diff)

        # Should contain core protocol
        assert "Core Protocol" in system_prompt
        # Should contain patterns
        assert "Patterns" in system_prompt
        # Should contain scheduler subsystem (detected from path)
        assert "Scheduler" in system_prompt

    def test_build_user_prompt(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test user prompt building."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        diff = "diff --git a/test.c b/test.c\n+new line"
        metadata = {
            'subject': 'Test patch',
            'commit_message': 'Fix something'
        }

        user_prompt = engine.build_user_prompt(diff, metadata)

        assert "Test patch" in user_prompt
        assert "Fix something" in user_prompt
        assert diff in user_prompt

    def test_parse_review_response_no_regressions(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test parsing response with no regressions."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        mock_response = Mock()
        mock_response.content = "Review complete. Regressions found: 0\n\nNo issues detected."

        result = engine.parse_review_response(mock_response, 100)

        assert result.regressions_found == 0
        assert result.tokens_used == 100
        assert "No issues" in result.review_text

    def test_parse_review_response_with_regressions(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test parsing response with regressions."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        mock_response = Mock()
        mock_response.content = """
Review Complete

## Regressions (2)

1. Pattern P001: Missing null check
2. Pattern P015: Incorrect locking

Total regressions found: 2
"""

        result = engine.parse_review_response(mock_response, 250)

        assert result.regressions_found == 2
        assert 'P001' in result.patterns_triggered
        assert 'P015' in result.patterns_triggered
        assert len(result.patterns_triggered) == 2
        assert result.tokens_used == 250

    def test_execute_review_protocol_simple(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test review execution with no tool calls."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        # Mock LLM to return immediate response
        mock_response = LLMResponse(
            content="Review complete. Regressions found: 0",
            tool_calls=[],
            finish_reason='stop',
            tokens_used=50
        )
        mock_provider.generate.return_value = mock_response

        result = engine.execute_review_protocol("System prompt", "User prompt")

        assert result.regressions_found == 0
        assert result.tokens_used == 50
        assert mock_provider.generate.call_count == 1

    def test_execute_review_protocol_with_tools(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test review execution with tool calls."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        # First response: LLM makes a tool call
        tool_call = ToolCall(
            id='call_1',
            name='find_function',
            arguments={'name': '__schedule'}
        )
        response1 = LLMResponse(
            content='',
            tool_calls=[tool_call],
            finish_reason='tool_calls',
            tokens_used=30
        )

        # Second response: LLM finishes after getting tool result
        response2 = LLMResponse(
            content='Review complete. Regressions found: 0',
            tool_calls=[],
            finish_reason='stop',
            tokens_used=40
        )

        mock_provider.generate.side_effect = [response1, response2]

        # Mock tool execution
        mock_mcp_client.invoke_tool.return_value = {
            'content': [{'type': 'text', 'text': 'Function found'}],
            'isError': False
        }

        result = engine.execute_review_protocol("System prompt", "User prompt")

        assert result.regressions_found == 0
        assert result.tokens_used == 70  # 30 + 40
        assert mock_provider.generate.call_count == 2
        assert mock_mcp_client.invoke_tool.call_count == 1

    def test_execute_review_protocol_max_turns(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test review execution hits max turns limit."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        # Always return tool calls (infinite loop scenario)
        tool_call = ToolCall(id='call_1', name='find_function', arguments={})
        mock_response = LLMResponse(
            content='Still analyzing...',
            tool_calls=[tool_call],
            finish_reason='tool_calls',
            tokens_used=10
        )

        mock_provider.generate.return_value = mock_response
        mock_mcp_client.invoke_tool.return_value = {
            'content': [{'type': 'text', 'text': 'Result'}],
            'isError': False
        }

        result = engine.execute_review_protocol("System prompt", "User prompt")

        # Should stop at max_turns (50)
        assert mock_provider.generate.call_count == 50
        assert "Still analyzing" in result.review_text

    def test_review_patch_end_to_end(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test complete review_patch workflow."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        # Mock simple review
        mock_response = LLMResponse(
            content='Review complete. Regressions found: 1. Pattern P001 triggered.',
            tool_calls=[],
            finish_reason='stop',
            tokens_used=100
        )
        mock_provider.generate.return_value = mock_response

        diff = "diff --git a/test.c b/test.c\n+new line"
        metadata = {'subject': 'Test patch', 'author': 'Test Author'}

        result = engine.review_patch(diff, metadata)

        assert result.regressions_found == 1
        assert 'P001' in result.patterns_triggered
        assert result.tokens_used == 100
        assert result.analysis_time > 0
        assert result.patch_info == metadata

    def test_parse_review_response_various_formats(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test parsing different regression count formats."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        test_cases = [
            ("Regressions found: 3", 3),
            ("## Regressions (5)", 5),
            ("Total regressions: 2", 2),
            ("REGRESSIONS FOUND: 1", 1),
            ("No regressions", 0),
        ]

        for content, expected_count in test_cases:
            mock_response = Mock()
            mock_response.content = content

            result = engine.parse_review_response(mock_response, 50)
            assert result.regressions_found == expected_count, f"Failed for: {content}"

    def test_parse_review_response_duplicate_patterns(self, mock_provider, mock_mcp_client, mock_prompts_loader):
        """Test that duplicate pattern IDs are deduplicated."""
        engine = ReviewEngine(mock_provider, mock_mcp_client, mock_prompts_loader)

        mock_response = Mock()
        mock_response.content = "Pattern P001 and P002. Also P001 again."

        result = engine.parse_review_response(mock_response, 50)

        assert len(result.patterns_triggered) == 2
        assert 'P001' in result.patterns_triggered
        assert 'P002' in result.patterns_triggered
