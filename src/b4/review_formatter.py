#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Output formatters for review results."""

import json
import textwrap
from datetime import datetime
from typing import Any, Dict

from .review import ReviewResult


def format_inline(review_result: ReviewResult, wrap_width: int = 72) -> str:
    """
    Format review result as email-style inline review.

    This format is designed to be easy to copy-paste into email replies
    or mailing list responses, following kernel development conventions.

    Args:
        review_result: The review result to format
        wrap_width: Width for text wrapping (default: 72 chars for email)

    Returns:
        Formatted review text suitable for email
    """
    lines = []
    metadata = review_result.patch_info

    # Header with patch information
    lines.append("=" * wrap_width)
    lines.append("AI-ASSISTED PATCH REVIEW")
    lines.append("=" * wrap_width)
    lines.append("")

    # Patch metadata
    if 'subject' in metadata:
        lines.append(f"Patch: {metadata['subject']}")
    if 'commit' in metadata:
        lines.append(f"Commit: {metadata['commit']}")
    if 'author' in metadata:
        lines.append(f"Author: {metadata['author']}")
    if 'date' in metadata:
        lines.append(f"Date: {metadata['date']}")
    lines.append("")

    # Review summary
    lines.append(f"Review Summary:")
    lines.append(f"  Regressions Found: {review_result.regressions_found}")

    if review_result.patterns_triggered:
        lines.append(f"  Patterns Triggered: {', '.join(review_result.patterns_triggered)}")
    else:
        lines.append(f"  Patterns Triggered: none")

    lines.append(f"  Analysis Time: {review_result.analysis_time:.1f}s")
    lines.append(f"  Tokens Used: {review_result.tokens_used:,}")
    lines.append("")

    # Main review content
    lines.append("-" * wrap_width)
    lines.append("DETAILED REVIEW")
    lines.append("-" * wrap_width)
    lines.append("")

    # Wrap the review text to fit email width
    review_lines = review_result.review_text.split('\n')
    for line in review_lines:
        if line.strip():
            # Preserve indentation for code blocks and lists
            indent = len(line) - len(line.lstrip())
            if indent > 0 or line.lstrip().startswith(('*', '-', '>', '```', '|')):
                # Don't wrap code blocks, lists, quotes, or tables
                lines.append(line)
            else:
                # Wrap normal text
                wrapped = textwrap.fill(
                    line,
                    width=wrap_width,
                    break_long_words=False,
                    break_on_hyphens=False
                )
                lines.append(wrapped)
        else:
            lines.append('')

    lines.append("")
    lines.append("-" * wrap_width)

    # Footer
    lines.append("")
    lines.append("This review was generated using AI-assisted analysis with")
    lines.append("kernel-specific review prompts and semantic code search.")
    lines.append("")
    lines.append("Please use this review as a starting point for manual")
    lines.append("verification. AI analysis may miss context or produce")
    lines.append("false positives.")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * wrap_width)

    return '\n'.join(lines)


def format_markdown(review_result: ReviewResult) -> str:
    """
    Format review result as markdown report.

    This format is suitable for documentation, GitHub/GitLab issues,
    or generating HTML reports.

    Args:
        review_result: The review result to format

    Returns:
        Formatted review in markdown
    """
    lines = []
    metadata = review_result.patch_info

    # Title
    lines.append("# AI-Assisted Patch Review")
    lines.append("")

    # Patch information table
    lines.append("## Patch Information")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")

    if 'subject' in metadata:
        lines.append(f"| Subject | {metadata['subject']} |")
    if 'commit' in metadata:
        lines.append(f"| Commit | `{metadata['commit']}` |")
    if 'author' in metadata:
        lines.append(f"| Author | {metadata['author']} |")
    if 'date' in metadata:
        lines.append(f"| Date | {metadata['date']} |")

    lines.append("")

    # Review summary with badges/indicators
    lines.append("## Review Summary")
    lines.append("")

    # Add visual indicator for regressions
    if review_result.regressions_found > 0:
        lines.append(f"🔴 **Regressions Found:** {review_result.regressions_found}")
    else:
        lines.append(f"✅ **Regressions Found:** {review_result.regressions_found}")

    lines.append("")

    if review_result.patterns_triggered:
        lines.append(f"**Patterns Triggered:** {', '.join(f'`{p}`' for p in review_result.patterns_triggered)}")
    else:
        lines.append(f"**Patterns Triggered:** none")

    lines.append("")
    lines.append(f"**Analysis Time:** {review_result.analysis_time:.1f}s")
    lines.append(f"**Tokens Used:** {review_result.tokens_used:,}")
    lines.append("")

    # Detailed review
    lines.append("## Detailed Review")
    lines.append("")
    lines.append(review_result.review_text)
    lines.append("")

    # Metadata footer
    lines.append("---")
    lines.append("")
    lines.append("### Review Metadata")
    lines.append("")
    lines.append(f"- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("- **Tool:** b4 review (AI-assisted)")
    lines.append("")
    lines.append("> **Note:** This review was generated using AI-assisted analysis with")
    lines.append("> kernel-specific review prompts and semantic code search. Please use")
    lines.append("> this review as a starting point for manual verification. AI analysis")
    lines.append("> may miss context or produce false positives.")

    return '\n'.join(lines)


def format_json(review_result: ReviewResult, pretty: bool = True) -> str:
    """
    Format review result as JSON.

    This format is suitable for CI/CD pipelines, automation,
    and machine parsing.

    Args:
        review_result: The review result to format
        pretty: Whether to pretty-print the JSON (default: True)

    Returns:
        JSON-formatted review result
    """
    # Build the output structure
    output: Dict[str, Any] = {
        'review': {
            'regressions_found': review_result.regressions_found,
            'patterns_triggered': review_result.patterns_triggered,
            'review_text': review_result.review_text,
            'analysis_time_seconds': review_result.analysis_time,
            'tokens_used': review_result.tokens_used,
        },
        'patch_info': review_result.patch_info,
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'tool': 'b4-review',
            'version': '1.0.0',
        }
    }

    if pretty:
        return json.dumps(output, indent=2, ensure_ascii=False)
    else:
        return json.dumps(output, ensure_ascii=False)


# Convenience function for automatic format selection
def format_review(
    review_result: ReviewResult,
    output_format: str = 'inline',
    **kwargs: Any
) -> str:
    """
    Format review result using specified format.

    Args:
        review_result: The review result to format
        output_format: Output format ('inline', 'markdown', or 'json')
        **kwargs: Additional arguments for specific formatters

    Returns:
        Formatted review text

    Raises:
        ValueError: If output_format is not recognized
    """
    formatters = {
        'inline': format_inline,
        'markdown': format_markdown,
        'json': format_json,
    }

    formatter = formatters.get(output_format.lower())
    if not formatter:
        valid = ', '.join(formatters.keys())
        raise ValueError(f"Unknown output format '{output_format}'. Valid formats: {valid}")

    return formatter(review_result, **kwargs)
