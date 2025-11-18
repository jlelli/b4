#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""AI-assisted patch review for b4."""

import argparse
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import b4

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
