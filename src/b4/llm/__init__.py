#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""LLM provider implementations for b4 AI review."""

from .base import (
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    Message,
    ToolCall,
    ToolResult,
)
from .ollama import OllamaProvider

__all__ = [
    # Base classes
    'LLMProvider',
    'Message',
    'ToolCall',
    'ToolResult',
    'LLMResponse',
    # Exceptions
    'LLMProviderError',
    'LLMConnectionError',
    'LLMTimeoutError',
    'LLMRateLimitError',
    'LLMModelNotFoundError',
    # Providers
    'OllamaProvider',
]
