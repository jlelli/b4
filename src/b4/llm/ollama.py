#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Ollama LLM provider implementation."""

import json
import logging
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from .base import (
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMTimeoutError,
    Message,
    ToolCall,
)

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """
    LLM provider for Ollama (local inference server).

    Ollama provides a local HTTP API compatible with OpenAI's format.
    Supports function/tool calling for MCP integration.
    """

    DEFAULT_URL = 'http://localhost:11434'
    DEFAULT_MODEL = 'qwen2.5-coder:7b'
    DEFAULT_TIMEOUT = 300.0  # 5 minutes
    DEFAULT_MAX_RETRIES = 3

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Ollama provider.

        Args:
            config: Configuration dictionary with keys:
                - url: Ollama API URL (default: http://localhost:11434)
                - model: Model name (default: qwen2.5-coder:7b)
                - timeout: Request timeout in seconds (default: 300)
                - max_retries: Maximum retry attempts (default: 3)
                - num_ctx: Context window size in tokens (default: 8192)
        """
        super().__init__(config)
        self._url = config.get('url', self.DEFAULT_URL).rstrip('/')
        self._model = config.get('model', self.DEFAULT_MODEL)
        self._timeout = config.get('timeout', self.DEFAULT_TIMEOUT)
        self._max_retries = config.get('max_retries', self.DEFAULT_MAX_RETRIES)
        self._num_ctx = config.get('num_ctx', 8192)  # Default to 8192 tokens

        # Create HTTP client
        self._client = httpx.Client(
            base_url=self._url,
            timeout=httpx.Timeout(self._timeout),
        )

        self.validate_config()

    @property
    def name(self) -> str:
        """Return provider name."""
        return 'ollama'

    @property
    def model(self) -> str:
        """Return current model name."""
        return self._model

    def validate_config(self) -> None:
        """
        Validate Ollama configuration and connectivity.

        Raises:
            LLMConnectionError: If cannot connect to Ollama
            LLMModelNotFoundError: If model is not available
        """
        try:
            # Check if Ollama is running
            response = self._client.get('/api/tags', timeout=5.0)
            response.raise_for_status()

            # Check if model is available
            models_data = response.json()
            available_models = [m['name'] for m in models_data.get('models', [])]

            if self._model not in available_models:
                logger.warning(f'Model {self._model} not found in Ollama. Available models: {available_models}')
                logger.warning(f'You may need to run: ollama pull {self._model}')

        except httpx.ConnectError as e:
            raise LLMConnectionError(
                f'Cannot connect to Ollama at {self._url}. '
                f'Is Ollama running? (systemctl status ollama)'
            ) from e
        except httpx.HTTPError as e:
            raise LLMConnectionError(f'Ollama API error: {e}') from e

    def generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Generate a response using Ollama's chat API.

        Args:
            messages: Conversation messages
            tools: Optional list of tools in Ollama function format
            **kwargs: Additional parameters (temperature, top_p, etc.)

        Returns:
            LLMResponse with generated content and/or tool calls

        Raises:
            LLMProviderError: If generation fails
        """
        payload = self._build_request_payload(messages, tools, stream=False, **kwargs)

        for attempt in range(self._max_retries):
            try:
                response = self._client.post('/api/chat', json=payload)
                response.raise_for_status()
                return self._parse_response(response.json())

            except httpx.TimeoutException as e:
                if attempt == self._max_retries - 1:
                    raise LLMTimeoutError(f'Ollama request timed out after {self._timeout}s') from e
                logger.warning(f'Request timed out, retrying... (attempt {attempt + 1}/{self._max_retries})')
                time.sleep(2 ** attempt)  # Exponential backoff

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise LLMModelNotFoundError(
                        f'Model {self._model} not found. Run: ollama pull {self._model}'
                    ) from e
                raise LLMProviderError(f'Ollama HTTP error: {e}') from e

            except httpx.HTTPError as e:
                raise LLMProviderError(f'Ollama request failed: {e}') from e

        raise LLMProviderError('Max retries exceeded')

    def stream_generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> Iterator[LLMResponse]:
        """
        Generate a streaming response using Ollama's chat API.

        Args:
            messages: Conversation messages
            tools: Optional list of tools
            **kwargs: Additional parameters

        Yields:
            LLMResponse chunks

        Raises:
            LLMProviderError: If generation fails
        """
        payload = self._build_request_payload(messages, tools, stream=True, **kwargs)

        try:
            with self._client.stream('POST', '/api/chat', json=payload) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            if not chunk.get('done', False):
                                yield self._parse_streaming_chunk(chunk)
                            else:
                                # Final chunk with metadata
                                final_response = self._parse_response(chunk)
                                if final_response.content or final_response.tool_calls:
                                    yield final_response
                        except json.JSONDecodeError:
                            logger.warning(f'Failed to parse streaming chunk: {line}')
                            continue

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f'Ollama streaming timed out after {self._timeout}s') from e
        except httpx.HTTPError as e:
            raise LLMProviderError(f'Ollama streaming failed: {e}') from e

    def _build_request_payload(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]],
        stream: bool = False,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Build request payload for Ollama API."""
        payload: Dict[str, Any] = {
            'model': self._model,
            'messages': [msg.to_dict() for msg in messages],
            'stream': stream,
        }

        # Add tools if provided
        if tools:
            payload['tools'] = tools

        # Initialize options dict
        payload['options'] = payload.get('options', {})

        # Set context window size from config or kwargs
        # This prevents prompt truncation warnings
        num_ctx = kwargs.get('num_ctx', self._num_ctx)
        payload['options']['num_ctx'] = num_ctx

        # Add optional parameters
        if 'temperature' in kwargs:
            payload['options']['temperature'] = kwargs['temperature']
        if 'top_p' in kwargs:
            payload['options']['top_p'] = kwargs['top_p']

        return payload

    def _parse_response(self, response_data: Dict[str, Any]) -> LLMResponse:
        """Parse Ollama API response into LLMResponse."""
        message = response_data.get('message', {})
        content = message.get('content', '')
        tool_calls_data = message.get('tool_calls', [])

        # Parse tool calls if present
        tool_calls = []
        if tool_calls_data:
            for tc in tool_calls_data:
                tool_calls.append(ToolCall(
                    id=tc.get('id', f"call_{len(tool_calls)}"),
                    name=tc['function']['name'],
                    arguments=tc['function'].get('arguments', {})
                ))
        elif content:
            # Fallback: Some models return tool calls as JSON in content
            # instead of using structured tool_calls format.
            # Handle both raw JSON and markdown-wrapped JSON

            # Strip markdown code blocks if present
            stripped_content = content.strip()
            if stripped_content.startswith('```'):
                # Extract content between code fences
                lines = stripped_content.split('\n')
                # Skip first line (```json or ```)
                lines = lines[1:]
                # Find closing fence
                try:
                    end_idx = lines.index('```')
                    stripped_content = '\n'.join(lines[:end_idx])
                except ValueError:
                    # No closing fence, use everything after first line
                    stripped_content = '\n'.join(lines)

            # Now try parsing if it looks like JSON
            if stripped_content.strip().startswith('{'):
                parsed_any = False

                # Strategy 1: Try parsing the entire content as one JSON object
                try:
                    tool_call_json = json.loads(stripped_content.strip())
                    if 'name' in tool_call_json and 'arguments' in tool_call_json:
                        tool_calls.append(ToolCall(
                            id=f"call_{len(tool_calls)}",
                            name=tool_call_json['name'],
                            arguments=tool_call_json['arguments']
                        ))
                        parsed_any = True
                        logger.debug(f'Parsed single tool call from JSON content: {tool_call_json["name"]}')
                except (json.JSONDecodeError, KeyError):
                    # Strategy 2: Try parsing each line separately
                    for line in stripped_content.strip().split('\n'):
                        line = line.strip()
                        if not line or not line.startswith('{'):
                            continue

                        try:
                            tool_call_json = json.loads(line)
                            if 'name' in tool_call_json and 'arguments' in tool_call_json:
                                tool_calls.append(ToolCall(
                                    id=f"call_{len(tool_calls)}",
                                    name=tool_call_json['name'],
                                    arguments=tool_call_json['arguments']
                                ))
                                parsed_any = True
                                logger.debug(f'Parsed tool call from JSON line: {tool_call_json["name"]}')
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.debug(f'Failed to parse line as tool call: {e}')

                # If we successfully parsed tool calls, clear the content
                if parsed_any:
                    content = ''

        # Determine finish reason
        finish_reason = 'stop'
        if tool_calls:
            finish_reason = 'tool_calls'
        elif response_data.get('done_reason') == 'length':
            finish_reason = 'length'

        return LLMResponse(
            content=content if content else None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            tokens_used=response_data.get('eval_count'),  # Ollama's token count field
            model=self._model,
        )

    def _parse_streaming_chunk(self, chunk: Dict[str, Any]) -> LLMResponse:
        """Parse a streaming chunk from Ollama."""
        message = chunk.get('message', {})
        content = message.get('content', '')

        return LLMResponse(
            content=content if content else None,
            tool_calls=[],
            finish_reason='',
            model=self._model,
        )

    def __del__(self) -> None:
        """Clean up HTTP client."""
        if hasattr(self, '_client'):
            self._client.close()
