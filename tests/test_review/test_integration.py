#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Integration tests for LLM + MCP workflow."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from b4.llm.ollama import OllamaProvider
from b4.llm.base import Message, ToolCall, LLMResponse
from b4.mcp_client import SemcodeMCPClient
from b4.tool_bridge import (
    convert_mcp_to_ollama_tools,
    execute_tool_call,
)


class TestLLMMCPIntegration:
    """Test LLM + MCP integration."""

    @pytest.mark.skip(reason="Requires running Ollama and semcode-mcp")
    def test_full_workflow_with_real_services(self):
        """
        End-to-end test with real Ollama and semcode-mcp.

        This test is skipped by default as it requires:
        - Ollama running locally
        - semcode-mcp binary available
        - Indexed kernel tree

        Run with: pytest -v -k test_full_workflow --run-integration
        """
        # Initialize Ollama provider
        ollama = OllamaProvider({
            'url': 'http://localhost:11434',
            'model': 'qwen2.5-coder:7b',
            'timeout': 60
        })

        # Initialize MCP client
        with SemcodeMCPClient() as mcp_client:
            # Get available tools
            mcp_tools = mcp_client.get_tools()
            assert len(mcp_tools) > 0, "No tools discovered from semcode-mcp"

            # Convert to Ollama format
            ollama_tools = convert_mcp_to_ollama_tools(mcp_tools)

            # Create a simple prompt that should trigger tool use
            messages = [
                Message(role='user', content='Find the definition of the __schedule function')
            ]

            # Generate with tools available
            response = ollama.generate(messages, tools=ollama_tools)

            # Should get either content or tool calls
            assert response.content or response.has_tool_calls

            # If tool calls were made, execute them
            if response.has_tool_calls:
                for tool_call in response.tool_calls:
                    result = execute_tool_call(tool_call, mcp_client)
                    assert not result.is_error
                    assert len(result.result) > 0

    def test_mock_llm_mcp_workflow(self):
        """Test LLM + MCP workflow with mocks."""
        # Mock MCP client
        mock_mcp = Mock(spec=SemcodeMCPClient)
        mock_mcp.get_tools.return_value = {
            'find_function': {
                'name': 'find_function',
                'description': 'Find a function',
                'inputSchema': {
                    'type': 'object',
                    'properties': {'name': {'type': 'string'}},
                    'required': ['name']
                }
            }
        }
        mock_mcp.invoke_tool.return_value = {
            'content': [{'type': 'text', 'text': 'static void __schedule(void) { ... }'}],
            'isError': False
        }

        # Get and convert tools
        mcp_tools = mock_mcp.get_tools()
        ollama_tools = convert_mcp_to_ollama_tools(mcp_tools)

        assert len(ollama_tools) == 1
        assert ollama_tools[0]['function']['name'] == 'find_function'

        # Simulate LLM making a tool call
        tool_call = ToolCall(
            id='call_1',
            name='find_function',
            arguments={'name': '__schedule'}
        )

        # Execute tool call
        result = execute_tool_call(tool_call, mock_mcp)

        assert not result.is_error
        assert '__schedule' in result.result

        # Verify MCP client was called correctly
        mock_mcp.invoke_tool.assert_called_once_with(
            'find_function',
            {'name': '__schedule'}
        )

    def test_tool_conversion_consistency(self):
        """Test that tool conversion preserves schema information."""
        mcp_tools = {
            'find_callchain': {
                'name': 'find_callchain',
                'description': 'Show call chain for a function',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'name': {
                            'type': 'string',
                            'description': 'Function name'
                        },
                        'up_levels': {
                            'type': 'integer',
                            'default': 2
                        },
                        'down_levels': {
                            'type': 'integer',
                            'default': 3
                        }
                    },
                    'required': ['name']
                }
            }
        }

        ollama_tools = convert_mcp_to_ollama_tools(mcp_tools)

        # Verify structure is preserved
        func_def = ollama_tools[0]['function']
        assert func_def['name'] == 'find_callchain'
        assert 'call chain' in func_def['description'].lower()

        params = func_def['parameters']
        assert params['type'] == 'object'
        assert 'name' in params['properties']
        assert 'name' in params['required']
        assert 'up_levels' in params['properties']
        assert params['properties']['up_levels']['type'] == 'integer'
