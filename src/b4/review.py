#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""AI-assisted patch review for b4."""

import argparse
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import b4
from .llm.base import LLMProvider, Message
from .mcp_client import SemcodeMCPClient
from .review_prompts import ReviewPromptsLoader
from .tool_bridge import convert_mcp_to_ollama_tools, execute_tool_calls

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    """Results from reviewing a patch."""
    patch_info: Dict[str, Any]
    regressions_found: int = 0
    patterns_triggered: List[str] = field(default_factory=list)
    review_text: str = ''
    tokens_used: int = 0
    analysis_time: float = 0.0

    def __str__(self) -> str:
        """String representation of review result."""
        return (
            f'Review completed:\n'
            f'  Regressions: {self.regressions_found}\n'
            f'  Patterns: {", ".join(self.patterns_triggered) if self.patterns_triggered else "none"}\n'
            f'  Tokens: {self.tokens_used}\n'
            f'  Time: {self.analysis_time:.1f}s'
        )


class ReviewEngine:
    """
    Core review engine that orchestrates LLM, MCP tools, and review prompts.

    The ReviewEngine:
    1. Loads review protocol and subsystem prompts
    2. Builds system prompt with protocol + technical patterns
    3. Executes review loop with LLM making autonomous tool calls
    4. Parses and validates review output
    """

    def __init__(
        self,
        provider: LLMProvider,
        mcp_client: SemcodeMCPClient,
        prompts_loader: ReviewPromptsLoader
    ):
        """
        Initialize review engine.

        Args:
            provider: LLM provider (Ollama, Anthropic, Gemini)
            mcp_client: Connected MCP client for semcode tools
            prompts_loader: Review prompts loader
        """
        self.provider = provider
        self.mcp_client = mcp_client
        self.prompts_loader = prompts_loader

        # Convert MCP tools to provider format
        mcp_tools = mcp_client.get_tools()
        # TODO: Support other providers
        self.tools = convert_mcp_to_ollama_tools(mcp_tools)

        logger.info(f'ReviewEngine initialized with {len(self.tools)} tools')

    def review_patch(
        self,
        patch_diff: str,
        metadata: Dict[str, Any]
    ) -> ReviewResult:
        """
        Review a patch for potential regressions.

        Args:
            patch_diff: Unified diff of the patch
            metadata: Patch metadata (commit message, author, etc.)

        Returns:
            ReviewResult with findings
        """
        start_time = time.time()

        logger.info(f'Reviewing patch: {metadata.get("subject", "unknown")}')

        # Build prompts
        system_prompt = self.build_system_prompt(patch_diff)
        user_prompt = self.build_user_prompt(patch_diff, metadata)

        # Execute review
        result = self.execute_review_protocol(system_prompt, user_prompt)

        # Calculate analysis time
        result.analysis_time = time.time() - start_time
        result.patch_info = metadata

        logger.info(f'Review complete: {result.regressions_found} regressions, '
                   f'{result.tokens_used} tokens, {result.analysis_time:.1f}s')

        return result

    def build_system_prompt(self, patch_diff: str) -> str:
        """
        Build system prompt with review protocol and relevant subsystem context.

        Args:
            patch_diff: Patch diff for subsystem detection

        Returns:
            Complete system prompt
        """
        parts = []

        # Load core protocol
        core_protocol = self.prompts_loader.load_core_protocol()
        parts.append(core_protocol)

        # Load technical patterns
        technical_patterns = self.prompts_loader.load_technical_patterns()
        parts.append('\n\n---\n\n')
        parts.append(technical_patterns)

        # Detect and load subsystem prompts
        subsystems = self.prompts_loader.detect_subsystems(patch_diff)
        if subsystems:
            logger.info(f'Detected subsystems: {subsystems}')
            subsystem_prompts = self.prompts_loader.load_subsystem_prompts(subsystems)

            for subsystem, content in subsystem_prompts.items():
                parts.append('\n\n---\n\n')
                parts.append(f'# Subsystem: {subsystem}\n\n')
                parts.append(content)

        system_prompt = ''.join(parts)
        logger.debug(f'System prompt: {len(system_prompt)} chars')

        return system_prompt

    def build_user_prompt(self, patch_diff: str, metadata: Dict[str, Any]) -> str:
        """
        Build user prompt with patch information.

        Args:
            patch_diff: Unified diff
            metadata: Patch metadata

        Returns:
            User prompt with patch to review
        """
        parts = []

        # Add metadata
        parts.append('# Patch to Review\n\n')

        if 'subject' in metadata:
            parts.append(f'**Subject**: {metadata["subject"]}\n\n')

        if 'commit_message' in metadata:
            parts.append(f'**Commit Message**:\n```\n{metadata["commit_message"]}\n```\n\n')

        # Add diff
        parts.append('**Diff**:\n```diff\n')
        parts.append(patch_diff)
        parts.append('\n```\n\n')

        parts.append('Please review this patch for potential regressions following the protocol.')

        return ''.join(parts)

    def execute_review_protocol(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> ReviewResult:
        """
        Execute the review protocol with LLM + MCP tools.

        The LLM autonomously:
        1. Analyzes the patch
        2. Calls semcode tools to gather context
        3. Checks technical patterns
        4. Reports findings

        Args:
            system_prompt: System instructions with protocol
            user_prompt: User message with patch

        Returns:
            Parsed ReviewResult
        """
        # Initialize conversation
        messages = [
            Message(role='system', content=system_prompt),
            Message(role='user', content=user_prompt)
        ]

        total_tokens = 0
        max_turns = 50  # Prevent infinite loops
        turn = 0

        while turn < max_turns:
            turn += 1
            logger.debug(f'Review turn {turn}/{max_turns}')

            # Get LLM response
            response = self.provider.generate(messages, tools=self.tools)

            if response.tokens_used:
                total_tokens += response.tokens_used

            # Check if review is complete
            if response.finish_reason == 'stop' and not response.has_tool_calls:
                # LLM finished without tool calls - review complete
                logger.info(f'Review completed in {turn} turns')
                return self.parse_review_response(response, total_tokens)

            # Execute tool calls if present
            if response.has_tool_calls:
                logger.info(f'Turn {turn}: Executing {len(response.tool_calls)} tool call(s)')

                # Add assistant message with tool calls
                messages.append(Message(
                    role='assistant',
                    content=response.content or '',
                    tool_calls=response.tool_calls
                ))

                # Execute tools and add results
                tool_results = execute_tool_calls(response.tool_calls, self.mcp_client)

                for result in tool_results:
                    messages.append(Message(
                        role='tool',
                        content=result.result,
                        tool_call_id=result.tool_call_id
                    ))

                # Continue loop to get next response
                continue

            # If we got content but no tool calls and finish_reason is not stop,
            # something unexpected happened
            if response.content:
                logger.warning(f'Unexpected finish_reason: {response.finish_reason}')
                return self.parse_review_response(response, total_tokens)

        # Hit max turns
        logger.warning(f'Review reached maximum turns ({max_turns})')

        # Try to parse whatever we have
        if messages:
            # Find last assistant message
            for msg in reversed(messages):
                if msg.role == 'assistant' and msg.content:
                    dummy_response = type('obj', (object,), {
                        'content': msg.content,
                        'tool_calls': [],
                        'finish_reason': 'length'
                    })()
                    return self.parse_review_response(dummy_response, total_tokens)

        # Fallback
        return ReviewResult(
            patch_info={},
            review_text='Review incomplete - reached maximum turns',
            tokens_used=total_tokens
        )

    def parse_review_response(self, response: Any, total_tokens: int) -> ReviewResult:
        """
        Parse the final review response from LLM.

        Extracts:
        - Number of regressions found
        - Patterns triggered
        - Review text

        Args:
            response: LLMResponse object
            total_tokens: Total tokens used

        Returns:
            Parsed ReviewResult
        """
        content = response.content or ''

        # Extract regressions count
        # Look for patterns like "Regressions found: 2" or "## Regressions (2)"
        regressions = 0
        regression_patterns = [
            r'regressions?\s*found[:\s]+(\d+)',
            r'##\s*regressions?\s*\((\d+)\)',
            r'total.*?regressions?[:\s]+(\d+)',
        ]

        for pattern in regression_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                regressions = int(match.group(1))
                break

        # Extract pattern IDs
        # Look for patterns like "P001", "P015", etc.
        patterns_triggered = []
        pattern_ids = re.findall(r'\bP\d{3}\b', content)
        if pattern_ids:
            patterns_triggered = sorted(list(set(pattern_ids)))

        return ReviewResult(
            patch_info={},  # Will be filled in by caller
            regressions_found=regressions,
            patterns_triggered=patterns_triggered,
            review_text=content,
            tokens_used=total_tokens
        )


def main(cmdargs: argparse.Namespace) -> None:
    """
    Main entry point for b4 review command.

    Args:
        cmdargs: Parsed command line arguments
    """
    logger.info('=== b4 AI Review ===')

    # Validate arguments
    if not cmdargs.msgid_or_commit:
        logger.critical('ERROR: Please specify a message ID, commit-ish, or commit range to review')
        sys.exit(1)

    # Determine review mode
    if '..' in str(cmdargs.msgid_or_commit):
        # Commit range - batch mode
        if not cmdargs.batch:
            logger.info('Commit range detected, enabling batch mode')
            cmdargs.batch = True
        review_result = review_from_range(cmdargs)
    elif '@' in str(cmdargs.msgid_or_commit) or '<' in str(cmdargs.msgid_or_commit):
        # Looks like a message ID
        review_result = review_from_msgid(cmdargs)
    else:
        # Assume it's a git commit-ish
        review_result = review_from_commit(cmdargs)

    if not review_result:
        logger.critical('ERROR: Review failed')
        sys.exit(1)

    logger.info(str(review_result))


def review_from_msgid(cmdargs: argparse.Namespace) -> Optional[ReviewResult]:
    """
    Review a patch from lore.kernel.org message ID.

    Args:
        cmdargs: Command arguments

    Returns:
        ReviewResult if successful, None otherwise
    """
    msgid = cmdargs.msgid_or_commit
    logger.info(f'Fetching patch series from lore: {msgid}')

    # TODO: Use b4's existing code to fetch patch
    # lmbx = b4.get_pi_thread_by_msgid(msgid)
    # lser = b4.LoreSeries(lmbx, ...)

    logger.error('Message ID review not yet implemented')
    return None


def review_from_commit(cmdargs: argparse.Namespace) -> Optional[ReviewResult]:
    """
    Review a git commit.

    Args:
        cmdargs: Command arguments

    Returns:
        ReviewResult if successful, None otherwise
    """
    commitish = cmdargs.msgid_or_commit
    logger.info(f'Reviewing git commit: {commitish}')

    # TODO: Get commit info and diff
    # commit_info = get_commit_info(commitish)
    # diff = get_commit_diff(commitish)

    logger.error('Git commit review not yet implemented')
    return None


def review_from_range(cmdargs: argparse.Namespace) -> Optional[ReviewResult]:
    """
    Review a range of commits (batch mode).

    Args:
        cmdargs: Command arguments

    Returns:
        Aggregated ReviewResult if successful, None otherwise
    """
    commit_range = cmdargs.msgid_or_commit
    logger.info(f'Reviewing commit range: {commit_range}')

    # TODO: Parse range, iterate commits, aggregate results

    logger.error('Batch review not yet implemented')
    return None
