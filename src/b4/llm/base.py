#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Base classes and interfaces for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class Message:
    """Represents a single message in a conversation."""
    role: str  # 'system', 'user', 'assistant'
    content: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary format."""
        return {'role': self.role, 'content': self.content}


@dataclass
class ToolCall:
    """Represents a tool/function call from the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'id': self.id,
            'name': self.name,
            'arguments': self.arguments
        }


@dataclass
class ToolResult:
    """Represents the result of a tool execution."""
    tool_call_id: str
    result: str
    is_error: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'tool_call_id': self.tool_call_id,
            'result': self.result,
            'is_error': self.is_error
        }


@dataclass
class LLMResponse:
    """Represents a response from an LLM provider."""
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = 'stop'  # 'stop', 'tool_calls', 'length', 'error'
    tokens_used: Optional[int] = None
    model: Optional[str] = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All LLM providers (Ollama, Anthropic, Gemini, etc.) must implement this interface.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the provider with configuration.

        Args:
            config: Provider-specific configuration dictionary
        """
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name (e.g., 'ollama', 'anthropic')."""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the current model name."""
        pass

    @abstractmethod
    def generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools/functions
            **kwargs: Provider-specific additional arguments

        Returns:
            LLMResponse containing the generated content and/or tool calls

        Raises:
            LLMProviderError: If generation fails
        """
        pass

    @abstractmethod
    def stream_generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any
    ) -> Iterator[LLMResponse]:
        """
        Generate a streaming response from the LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools/functions
            **kwargs: Provider-specific additional arguments

        Yields:
            LLMResponse chunks as they are generated

        Raises:
            LLMProviderError: If generation fails
        """
        pass

    def supports_tools(self) -> bool:
        """
        Check if this provider supports tool/function calling.

        Returns:
            True if tools are supported, False otherwise
        """
        return True  # Most modern providers support this

    def validate_config(self) -> None:
        """
        Validate provider configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        pass


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    pass


class LLMConnectionError(LLMProviderError):
    """Failed to connect to LLM provider."""
    pass


class LLMTimeoutError(LLMProviderError):
    """LLM request timed out."""
    pass


class LLMRateLimitError(LLMProviderError):
    """LLM provider rate limit exceeded."""
    pass


class LLMModelNotFoundError(LLMProviderError):
    """Requested model not found."""
    pass
