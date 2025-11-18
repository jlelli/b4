#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Tests for tool bridge."""

import pytest
from unittest.mock import Mock, MagicMock

from b4.tool_bridge import (
    convert_mcp_to_ollama_tools,
    convert_mcp_to_anthropic_tools,
    convert_mcp_to_gemini_tools,
    execute_tool_call,
)
from b4.llm.base import ToolCall, ToolResult


class TestToolBridge:
    """Test tool conversion and execution."""

    def test_convert_mcp_to_ollama(self):
        """Test converting MCP tools to Ollama format."""
        mcp_tools = {
            'find_function': {
                'name': 'find_function',
                'description': 'Find a function definition',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'name': {'type': 'string', 'description': 'Function name'}
                    },
                    'required': ['name']
                }
            }
        }

        ollama_tools = convert_mcp_to_ollama_tools(mcp_tools)

        assert len(ollama_tools) == 1
        assert ollama_tools[0]['type'] == 'function'
        assert ollama_tools[0]['function']['name'] == 'find_function'
        assert 'parameters' in ollama_tools[0]['function']
        assert ollama_tools[0]['function']['parameters']['type'] == 'object'

    def test_convert_mcp_to_anthropic(self):
        """Test converting MCP tools to Anthropic format."""
        mcp_tools = {
            'find_callers': {
                'name': 'find_callers',
                'description': 'Find functions that call a specific function',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'name': {'type': 'string'}
                    }
                }
            }
        }

        anthropic_tools = convert_mcp_to_anthropic_tools(mcp_tools)

        assert len(anthropic_tools) == 1
        assert anthropic_tools[0]['name'] == 'find_callers'
        assert 'input_schema' in anthropic_tools[0]
        assert anthropic_tools[0]['input_schema']['type'] == 'object'

    def test_convert_mcp_to_gemini(self):
        """Test converting MCP tools to Gemini format."""
        mcp_tools = {
            'grep_functions': {
                'name': 'grep_functions',
                'description': 'Search function bodies',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'pattern': {'type': 'string'}
                    }
                }
            }
        }

        gemini_tools = convert_mcp_to_gemini_tools(mcp_tools)

        assert len(gemini_tools) == 1
        assert gemini_tools[0]['name'] == 'grep_functions'
        assert 'parameters' in gemini_tools[0]

    def test_execute_tool_call_success(self):
        """Test successful tool execution."""
        tool_call = ToolCall(
            id='call_123',
            name='find_function',
            arguments={'name': '__schedule'}
        )

        mock_client = Mock()
        mock_client.invoke_tool.return_value = {
            'content': [
                {'type': 'text', 'text': 'Function definition here'}
            ],
            'isError': False
        }

        result = execute_tool_call(tool_call, mock_client)

        assert isinstance(result, ToolResult)
        assert result.tool_call_id == 'call_123'
        assert 'Function definition' in result.result
        assert not result.is_error

    def test_execute_tool_call_error(self):
        """Test tool execution with error."""
        tool_call = ToolCall(
            id='call_456',
            name='invalid_tool',
            arguments={}
        )

        mock_client = Mock()
        mock_client.invoke_tool.side_effect = Exception('Tool not found')

        result = execute_tool_call(tool_call, mock_client)

        assert isinstance(result, ToolResult)
        assert result.is_error
        assert 'error' in result.result.lower()
