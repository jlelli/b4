#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Bridge between MCP tools and LLM provider-specific formats."""

import logging
from typing import Any, Dict, List

from .llm.base import ToolCall, ToolResult
from .mcp_client import SemcodeMCPClient, MCPToolError

logger = logging.getLogger(__name__)


def convert_mcp_to_ollama_tools(mcp_tools: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert MCP tool schemas to Ollama function calling format.

    Args:
        mcp_tools: Dictionary of MCP tool schemas

    Returns:
        List of tools in Ollama format
    """
    ollama_tools = []

    for tool_name, tool_schema in mcp_tools.items():
        # Ollama uses OpenAI-compatible function calling format
        ollama_tool = {
            'type': 'function',
            'function': {
                'name': tool_name,
                'description': tool_schema.get('description', ''),
                'parameters': _convert_mcp_params_to_json_schema(
                    tool_schema.get('inputSchema', {})
                )
            }
        }
        ollama_tools.append(ollama_tool)

    logger.debug(f'Converted {len(ollama_tools)} MCP tools to Ollama format')
    return ollama_tools


def convert_mcp_to_anthropic_tools(mcp_tools: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert MCP tool schemas to Anthropic Claude tool format.

    Args:
        mcp_tools: Dictionary of MCP tool schemas

    Returns:
        List of tools in Anthropic format
    """
    anthropic_tools = []

    for tool_name, tool_schema in mcp_tools.items():
        # Anthropic uses a similar format but with slight differences
        anthropic_tool = {
            'name': tool_name,
            'description': tool_schema.get('description', ''),
            'input_schema': _convert_mcp_params_to_json_schema(
                tool_schema.get('inputSchema', {})
            )
        }
        anthropic_tools.append(anthropic_tool)

    logger.debug(f'Converted {len(anthropic_tools)} MCP tools to Anthropic format')
    return anthropic_tools


def convert_mcp_to_gemini_tools(mcp_tools: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert MCP tool schemas to Google Gemini function calling format.

    Args:
        mcp_tools: Dictionary of MCP tool schemas

    Returns:
        List of tools in Gemini format
    """
    gemini_tools = []

    for tool_name, tool_schema in mcp_tools.items():
        # Gemini uses function declarations
        gemini_tool = {
            'name': tool_name,
            'description': tool_schema.get('description', ''),
            'parameters': _convert_mcp_params_to_json_schema(
                tool_schema.get('inputSchema', {})
            )
        }
        gemini_tools.append(gemini_tool)

    logger.debug(f'Converted {len(gemini_tools)} MCP tools to Gemini format')
    return gemini_tools


def _convert_mcp_params_to_json_schema(input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert MCP input schema to JSON Schema format.

    MCP uses JSON Schema natively, but we may need to normalize it
    for different LLM providers.

    Args:
        input_schema: MCP input schema

    Returns:
        JSON Schema dict
    """
    # MCP already uses JSON Schema, so mostly pass-through
    # But ensure we have required fields
    if not input_schema:
        return {
            'type': 'object',
            'properties': {},
            'required': []
        }

    # Ensure type is set
    if 'type' not in input_schema:
        input_schema['type'] = 'object'

    # Ensure properties exists
    if 'properties' not in input_schema:
        input_schema['properties'] = {}

    return input_schema


def execute_tool_call(
    tool_call: ToolCall,
    mcp_client: SemcodeMCPClient
) -> ToolResult:
    """
    Execute a tool call from an LLM via MCP client.

    Args:
        tool_call: ToolCall from LLM
        mcp_client: Connected MCP client

    Returns:
        ToolResult with execution results
    """
    logger.info(f'Executing tool: {tool_call.name}')
    logger.debug(f'Arguments: {tool_call.arguments}')

    try:
        # Invoke tool via MCP
        result = mcp_client.invoke_tool(tool_call.name, tool_call.arguments)

        # Extract content from MCP result
        # MCP tools/call response format:
        # {
        #   "content": [...],  // Array of content items
        #   "isError": false
        # }
        content_items = result.get('content', [])

        # Combine all text content
        text_parts = []
        for item in content_items:
            if item.get('type') == 'text':
                text_parts.append(item.get('text', ''))

        result_text = '\n'.join(text_parts)
        is_error = result.get('isError', False)

        logger.debug(f'Tool {tool_call.name} result length: {len(result_text)} chars')

        return ToolResult(
            tool_call_id=tool_call.id,
            result=result_text,
            is_error=is_error
        )

    except MCPToolError as e:
        logger.error(f'Tool execution failed: {e}')
        return ToolResult(
            tool_call_id=tool_call.id,
            result=f'Error: {str(e)}',
            is_error=True
        )
    except Exception as e:
        logger.error(f'Unexpected error executing tool: {e}')
        return ToolResult(
            tool_call_id=tool_call.id,
            result=f'Unexpected error: {str(e)}',
            is_error=True
        )


def execute_tool_calls(
    tool_calls: List[ToolCall],
    mcp_client: SemcodeMCPClient
) -> List[ToolResult]:
    """
    Execute multiple tool calls.

    Args:
        tool_calls: List of tool calls from LLM
        mcp_client: Connected MCP client

    Returns:
        List of tool results in same order as tool_calls
    """
    results = []
    for tool_call in tool_calls:
        result = execute_tool_call(tool_call, mcp_client)
        results.append(result)
    return results
