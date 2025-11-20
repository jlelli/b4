#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Google Gemini LLM provider implementation."""

import logging
import os
from typing import Any, Dict, Iterator, List, Optional

import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmBlockThreshold, HarmCategory

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


class GeminiProvider(LLMProvider):
    """
    LLM provider for Google Gemini.

    Uses the Google Generative AI SDK for API access.
    Supports function calling for MCP integration.
    """

    DEFAULT_MODEL = 'gemini-2.5-flash'
    DEFAULT_TIMEOUT = 300.0  # 5 minutes
    DEFAULT_MAX_RETRIES = 3

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Gemini provider.

        Args:
            config: Configuration dictionary with keys:
                - api_key: Gemini API key (or from GEMINI_API_KEY env var)
                - model: Model name (default: gemini-2.5-flash)
                - timeout: Request timeout in seconds (default: 300)
                - max_retries: Maximum retry attempts (default: 3)
                - temperature: Sampling temperature (default: 0.1)
                - top_p: Nucleus sampling parameter (default: 0.95)
        """
        super().__init__(config)

        # Get API key from config or environment
        self._api_key = config.get('api_key') or os.getenv('GEMINI_API_KEY')
        if not self._api_key:
            raise LLMConnectionError(
                'Gemini API key not found. Set GEMINI_API_KEY environment variable '
                'or configure b4-review-gemini.api-key in git config.'
            )

        self._model = config.get('model', self.DEFAULT_MODEL)
        self._timeout = config.get('timeout', self.DEFAULT_TIMEOUT)
        self._max_retries = config.get('max_retries', self.DEFAULT_MAX_RETRIES)
        self._temperature = config.get('temperature', 0.1)
        self._top_p = config.get('top_p', 0.95)

        # Configure API
        genai.configure(api_key=self._api_key)

        # Create model instance
        try:
            self._client = genai.GenerativeModel(
                model_name=self._model,
                generation_config=GenerationConfig(
                    temperature=self._temperature,
                    top_p=self._top_p,
                ),
                # Disable safety filters for code review (we need to see all code)
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
        except Exception as e:
            raise LLMConnectionError(f'Failed to initialize Gemini model: {e}') from e

        self.validate_config()

    @property
    def name(self) -> str:
        """Return provider name."""
        return 'gemini'

    @property
    def model(self) -> str:
        """Return current model name."""
        return self._model

    def validate_config(self) -> None:
        """
        Validate Gemini configuration.

        Raises:
            LLMConnectionError: If cannot connect to Gemini
            LLMModelNotFoundError: If model is not available
        """
        try:
            # Test API connection by listing models
            models = genai.list_models()
            available_model_names = [m.name for m in models]

            # Model names are in format "models/gemini-..."
            full_model_name = f'models/{self._model}'
            if full_model_name not in available_model_names:
                logger.warning(f'Model {self._model} may not be available. Available models: {available_model_names}')

        except Exception as e:
            raise LLMConnectionError(f'Cannot connect to Gemini API: {e}') from e

    def generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Generate a response using Gemini's API.

        Args:
            messages: Conversation messages
            tools: Optional list of tools in Gemini function format
            **kwargs: Additional parameters (temperature, top_p, etc.)

        Returns:
            LLMResponse with generated content and/or tool calls

        Raises:
            LLMProviderError: If generation fails
        """
        # Convert messages to Gemini format
        chat_history, last_message = self._build_gemini_messages(messages)

        # Build tools if provided
        gemini_tools = None
        if tools:
            gemini_tools = self._convert_to_gemini_tools(tools)

        try:
            # Start chat session
            chat = self._client.start_chat(history=chat_history)

            # Send message with tools
            response = chat.send_message(
                last_message,
                tools=gemini_tools,
            )

            return self._parse_response(response)

        except Exception as e:
            raise LLMProviderError(f'Gemini generation failed: {e}') from e

    def stream_generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> Iterator[LLMResponse]:
        """
        Generate a streaming response using Gemini's API.

        Args:
            messages: Conversation messages
            tools: Optional list of tools
            **kwargs: Additional parameters

        Yields:
            LLMResponse chunks

        Raises:
            LLMProviderError: If generation fails
        """
        # Convert messages to Gemini format
        chat_history, last_message = self._build_gemini_messages(messages)

        # Build tools if provided
        gemini_tools = None
        if tools:
            gemini_tools = self._convert_to_gemini_tools(tools)

        try:
            # Start chat session
            chat = self._client.start_chat(history=chat_history)

            # Send message with streaming
            response_stream = chat.send_message(
                last_message,
                tools=gemini_tools,
                stream=True,
            )

            for chunk in response_stream:
                yield self._parse_streaming_chunk(chunk)

        except Exception as e:
            raise LLMProviderError(f'Gemini streaming failed: {e}') from e

    def _build_gemini_messages(self, messages: List[Message]) -> tuple[List[Dict[str, Any]], str]:
        """
        Convert our Message format to Gemini chat format.

        Gemini uses a chat history format with alternating user/model messages.
        System messages are handled separately.

        Args:
            messages: Our message format

        Returns:
            (chat_history, last_user_message) tuple
        """
        chat_history = []
        system_instruction = None

        for i, msg in enumerate(messages):
            if msg.role == 'system':
                # Gemini handles system messages as "system_instruction"
                # We'll prepend it to the first user message
                system_instruction = msg.content

            elif msg.role == 'user':
                content = msg.content
                # Prepend system instruction to first user message
                if system_instruction:
                    content = f"{system_instruction}\n\n{content}"
                    system_instruction = None

                # Last message is sent separately, not in history
                if i == len(messages) - 1:
                    return chat_history, content

                chat_history.append({
                    'role': 'user',
                    'parts': [content]
                })

            elif msg.role == 'assistant':
                parts = []

                # Add text content if present
                if msg.content:
                    parts.append(msg.content)

                # Add tool calls if present
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        parts.append({
                            'function_call': {
                                'name': tc.name,
                                'args': tc.arguments
                            }
                        })

                chat_history.append({
                    'role': 'model',
                    'parts': parts
                })

            elif msg.role == 'tool':
                # Tool results
                chat_history.append({
                    'role': 'function',
                    'parts': [{
                        'function_response': {
                            'name': msg.tool_call_id or 'unknown',
                            'response': {'result': msg.content}
                        }
                    }]
                })

        # If we get here, last message wasn't a user message (likely tool results)
        # For Gemini, tool results are in history, and we need to prompt continuation
        # Send a minimal continuation prompt
        return chat_history, "Please continue based on the tool results above."

    def _convert_proto_to_dict(self, obj: Any) -> Any:
        """
        Convert protobuf objects to plain Python types.

        Gemini returns function arguments as protobuf objects (RepeatedComposite,
        MapComposite) which aren't JSON serializable. Convert them recursively.
        """
        if isinstance(obj, dict):
            return {k: self._convert_proto_to_dict(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._convert_proto_to_dict(item) for item in obj]
        elif hasattr(obj, 'items'):  # dict-like (protobuf MapComposite)
            return {k: self._convert_proto_to_dict(v) for k, v in obj.items()}
        elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):  # list-like (protobuf RepeatedComposite)
            return [self._convert_proto_to_dict(item) for item in obj]
        else:
            return obj

    def _convert_to_gemini_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert tool format to Gemini function declarations.

        Our tools are already in Gemini-compatible format from tool_bridge.py.

        Args:
            tools: Tools in our format

        Returns:
            Gemini function declarations
        """
        function_declarations = []

        for tool in tools:
            # Our tools from convert_mcp_to_gemini_tools already have the right format
            function_declarations.append({
                'name': tool['name'],
                'description': tool['description'],
                'parameters': tool['parameters']
            })

        return [{'function_declarations': function_declarations}]

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse Gemini response into LLMResponse."""
        content = ''
        tool_calls = []

        # Extract text content (only if no function_call)
        # response.text throws ValueError if there's a function_call
        try:
            if response.text:
                content = response.text
        except ValueError:
            # This happens when response contains function_call
            pass

        # Extract function calls
        for part in response.parts:
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                # Convert protobuf args to plain dict (handles RepeatedComposite, etc.)
                args_dict = self._convert_proto_to_dict(dict(fc.args))
                tool_calls.append(ToolCall(
                    id=fc.name,  # Gemini doesn't provide IDs, use name
                    name=fc.name,
                    arguments=args_dict
                ))

        # Determine finish reason
        finish_reason = 'stop'
        if tool_calls:
            finish_reason = 'tool_calls'
        elif hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'finish_reason'):
                # Map Gemini finish reasons to our format
                gemini_reason = str(candidate.finish_reason)
                if 'MAX_TOKENS' in gemini_reason or 'LENGTH' in gemini_reason:
                    finish_reason = 'length'

        # Token usage (Gemini provides this in usage_metadata)
        tokens_used = 0
        if hasattr(response, 'usage_metadata'):
            tokens_used = response.usage_metadata.total_token_count

        return LLMResponse(
            content=content if content else None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            tokens_used=tokens_used,
            model=self._model,
        )

    def _parse_streaming_chunk(self, chunk: Any) -> LLMResponse:
        """Parse a streaming chunk from Gemini."""
        content = ''
        tool_calls = []

        # Extract text content (only if no function calls)
        # chunk.text throws ValueError if there's a function_call
        try:
            if chunk.text:
                content = chunk.text
        except ValueError:
            # This happens when chunk contains function_call
            pass

        # Extract function calls (may be present in chunks)
        for part in chunk.parts:
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                # Convert protobuf args to plain dict (handles RepeatedComposite, etc.)
                args_dict = self._convert_proto_to_dict(dict(fc.args))
                tool_calls.append(ToolCall(
                    id=fc.name,
                    name=fc.name,
                    arguments=args_dict
                ))

        return LLMResponse(
            content=content if content else None,
            tool_calls=tool_calls,
            finish_reason='',
            model=self._model,
        )
