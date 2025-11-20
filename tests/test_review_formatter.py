#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for review output formatters."""

import json
import pytest
from datetime import datetime

from b4.review import ReviewResult
from b4.review_formatter import (
    format_inline,
    format_markdown,
    format_json,
    format_review,
)


@pytest.fixture
def sample_review_result():
    """Create a sample review result for testing."""
    return ReviewResult(
        patch_info={
            'subject': 'sched/deadline: Fix bandwidth reclaim issue',
            'commit': 'e0367ffa5955',
            'author': 'Juri Lelli <juri.lelli@redhat.com>',
            'date': '2024-11-15 10:30:00',
        },
        regressions_found=1,
        patterns_triggered=['CL-001', 'EH-003'],
        review_text="""# Analysis Results

## Pattern CL-001: Missing Lock Protection

The function `dl_reclaim_bandwidth()` accesses shared state without
proper locking. This could lead to race conditions.

## Recommendation

Add proper locking around the bandwidth reclaim logic.""",
        tokens_used=2500,
        analysis_time=45.3,
    )


@pytest.fixture
def minimal_review_result():
    """Create a minimal review result with no issues found."""
    return ReviewResult(
        patch_info={'subject': 'Simple fix'},
        regressions_found=0,
        patterns_triggered=[],
        review_text='No issues found.',
        tokens_used=100,
        analysis_time=5.0,
    )


class TestFormatInline:
    """Tests for inline (email-style) formatting."""

    def test_inline_format_structure(self, sample_review_result):
        """Test that inline format has expected structure."""
        output = format_inline(sample_review_result)

        # Check for header
        assert 'AI-ASSISTED PATCH REVIEW' in output
        assert '=' in output  # Header separators

        # Check for patch metadata
        assert 'sched/deadline: Fix bandwidth reclaim issue' in output
        assert 'e0367ffa5955' in output
        assert 'Juri Lelli' in output

        # Check for review summary
        assert 'Review Summary:' in output
        assert 'Regressions Found: 1' in output
        assert 'CL-001' in output
        assert 'EH-003' in output
        assert 'Tokens Used:' in output
        assert 'Analysis Time:' in output

        # Check for detailed review section
        assert 'DETAILED REVIEW' in output
        assert 'dl_reclaim_bandwidth()' in output

        # Check for footer
        assert 'AI-assisted analysis' in output
        assert 'Generated:' in output

    def test_inline_format_no_regressions(self, minimal_review_result):
        """Test inline format with no regressions found."""
        output = format_inline(minimal_review_result)

        assert 'Regressions Found: 0' in output
        assert 'Patterns Triggered: none' in output
        assert 'No issues found.' in output

    def test_inline_format_text_wrapping(self):
        """Test that inline format wraps long lines."""
        long_text = ' '.join(['word'] * 50)  # Very long line
        result = ReviewResult(
            patch_info={},
            review_text=long_text,
            tokens_used=100,
            analysis_time=1.0,
        )

        output = format_inline(result, wrap_width=72)
        lines = output.split('\n')

        # Check that lines in the review section are wrapped
        review_section_started = False
        for line in lines:
            if 'DETAILED REVIEW' in line:
                review_section_started = True
                continue
            if review_section_started and line.strip() and not line.startswith('-'):
                # Normal text lines should be wrapped
                assert len(line) <= 72, f"Line too long ({len(line)} chars): {line[:80]}..."

    def test_inline_format_preserves_code_blocks(self):
        """Test that code blocks and lists are not wrapped."""
        result = ReviewResult(
            patch_info={},
            review_text="""Some text.

    if (condition) {
        very_long_function_call_that_should_not_be_wrapped(arg1, arg2, arg3);
    }

* Bullet point one
* Another bullet point that is very long and should not be wrapped inappropriately
""",
            tokens_used=100,
            analysis_time=1.0,
        )

        output = format_inline(result)

        # Code blocks with indentation should be preserved
        assert 'very_long_function_call_that_should_not_be_wrapped' in output

        # Bullet points should be preserved
        assert '* Bullet point one' in output
        assert '* Another bullet point' in output


class TestFormatMarkdown:
    """Tests for markdown formatting."""

    def test_markdown_format_structure(self, sample_review_result):
        """Test that markdown format has expected structure."""
        output = format_markdown(sample_review_result)

        # Check for markdown headers
        assert '# AI-Assisted Patch Review' in output
        assert '## Patch Information' in output
        assert '## Review Summary' in output
        assert '## Detailed Review' in output

        # Check for table formatting
        assert '| Field | Value |' in output
        assert '|-------|-------|' in output

        # Check for metadata
        assert 'sched/deadline: Fix bandwidth reclaim issue' in output
        assert '`e0367ffa5955`' in output  # Code formatting for commit

        # Check for emoji indicators
        assert '🔴' in output  # Red indicator for regressions

        # Check for pattern formatting
        assert '`CL-001`' in output  # Code formatting for patterns
        assert '`EH-003`' in output

        # Check for footer metadata
        assert '### Review Metadata' in output
        assert '> **Note:**' in output

    def test_markdown_format_no_regressions(self, minimal_review_result):
        """Test markdown format with no regressions."""
        output = format_markdown(minimal_review_result)

        # Should have green indicator for no regressions
        assert '✅' in output
        assert 'Regressions Found:** 0' in output
        assert 'Patterns Triggered:** none' in output

    def test_markdown_format_preserves_review_text(self, sample_review_result):
        """Test that markdown preserves the review text formatting."""
        output = format_markdown(sample_review_result)

        # Review text should be included as-is
        assert 'Pattern CL-001: Missing Lock Protection' in output
        assert 'dl_reclaim_bandwidth()' in output
        assert 'Recommendation' in output

    def test_markdown_format_metadata_footer(self, sample_review_result):
        """Test that markdown includes proper footer metadata."""
        output = format_markdown(sample_review_result)

        # Check for horizontal rule separator
        assert '---' in output

        # Check for metadata section
        assert 'Generated:' in output
        assert 'Tool:** b4 review' in output

        # Check for note about AI-assisted review
        assert 'AI-assisted analysis' in output
        assert 'manual verification' in output


class TestFormatJSON:
    """Tests for JSON formatting."""

    def test_json_format_structure(self, sample_review_result):
        """Test that JSON format has expected structure."""
        output = format_json(sample_review_result)
        data = json.loads(output)

        # Check top-level structure
        assert 'review' in data
        assert 'patch_info' in data
        assert 'metadata' in data

        # Check review section
        review = data['review']
        assert review['regressions_found'] == 1
        assert review['patterns_triggered'] == ['CL-001', 'EH-003']
        assert 'dl_reclaim_bandwidth()' in review['review_text']
        assert review['tokens_used'] == 2500
        assert review['analysis_time_seconds'] == 45.3

        # Check patch_info section
        patch_info = data['patch_info']
        assert patch_info['subject'] == 'sched/deadline: Fix bandwidth reclaim issue'
        assert patch_info['commit'] == 'e0367ffa5955'

        # Check metadata section
        metadata = data['metadata']
        assert 'generated_at' in metadata
        assert metadata['tool'] == 'b4-review'
        assert 'version' in metadata

    def test_json_format_pretty_print(self, sample_review_result):
        """Test that pretty printing works."""
        output = format_json(sample_review_result, pretty=True)

        # Pretty printed JSON should have indentation
        assert '\n' in output
        assert '  ' in output  # Indentation

        # Should still be valid JSON
        data = json.loads(output)
        assert data['review']['regressions_found'] == 1

    def test_json_format_compact(self, sample_review_result):
        """Test that compact formatting works."""
        output = format_json(sample_review_result, pretty=False)

        # Compact JSON should be single line (or minimal lines)
        lines = output.split('\n')
        assert len(lines) <= 2  # At most one newline at end

        # Should still be valid JSON
        data = json.loads(output)
        assert data['review']['regressions_found'] == 1

    def test_json_format_unicode(self):
        """Test that JSON handles unicode properly."""
        result = ReviewResult(
            patch_info={'author': 'José María Álvarez'},
            review_text='Function with emoji: 🔒 lock required',
            tokens_used=100,
            analysis_time=1.0,
        )

        output = format_json(result)
        data = json.loads(output)

        # Unicode should be preserved
        assert data['patch_info']['author'] == 'José María Álvarez'
        assert '🔒' in data['review']['review_text']

    def test_json_format_empty_patterns(self, minimal_review_result):
        """Test JSON format with empty patterns list."""
        output = format_json(minimal_review_result)
        data = json.loads(output)

        assert data['review']['patterns_triggered'] == []
        assert data['review']['regressions_found'] == 0


class TestFormatReview:
    """Tests for the generic format_review() function."""

    def test_format_review_inline(self, sample_review_result):
        """Test format_review with inline format."""
        output = format_review(sample_review_result, output_format='inline')

        # Should be same as format_inline()
        expected = format_inline(sample_review_result)
        assert output == expected

    def test_format_review_markdown(self, sample_review_result):
        """Test format_review with markdown format."""
        output = format_review(sample_review_result, output_format='markdown')

        # Should be same as format_markdown()
        expected = format_markdown(sample_review_result)
        assert output == expected

    def test_format_review_json(self, sample_review_result):
        """Test format_review with json format."""
        output = format_review(sample_review_result, output_format='json')

        # Parse and compare data (timestamps may differ by microseconds)
        output_data = json.loads(output)
        expected_data = json.loads(format_json(sample_review_result))

        # Compare review data (should be identical)
        assert output_data['review'] == expected_data['review']
        assert output_data['patch_info'] == expected_data['patch_info']

        # Compare metadata (except timestamp which will differ slightly)
        assert output_data['metadata']['tool'] == expected_data['metadata']['tool']
        assert output_data['metadata']['version'] == expected_data['metadata']['version']
        assert 'generated_at' in output_data['metadata']

    def test_format_review_case_insensitive(self, sample_review_result):
        """Test that format selection is case-insensitive."""
        output_lower = format_review(sample_review_result, output_format='inline')
        output_upper = format_review(sample_review_result, output_format='INLINE')
        output_mixed = format_review(sample_review_result, output_format='InLine')

        assert output_lower == output_upper == output_mixed

    def test_format_review_invalid_format(self, sample_review_result):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Unknown output format 'invalid'"):
            format_review(sample_review_result, output_format='invalid')

        with pytest.raises(ValueError, match="Valid formats:"):
            format_review(sample_review_result, output_format='xml')

    def test_format_review_kwargs_passthrough(self, sample_review_result):
        """Test that kwargs are passed through to formatters."""
        # Test wrap_width for inline format
        output = format_review(sample_review_result, output_format='inline', wrap_width=80)
        assert output  # Should not raise

        # Test pretty for JSON format
        output_pretty = format_review(sample_review_result, output_format='json', pretty=True)
        output_compact = format_review(sample_review_result, output_format='json', pretty=False)

        assert len(output_pretty) > len(output_compact)  # Pretty is longer


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_review_text(self):
        """Test formatting with empty review text."""
        result = ReviewResult(
            patch_info={'subject': 'Test'},
            review_text='',
            tokens_used=0,
            analysis_time=0.1,
        )

        # All formats should handle empty review text
        inline = format_inline(result)
        assert 'DETAILED REVIEW' in inline

        markdown = format_markdown(result)
        assert '## Detailed Review' in markdown

        json_output = format_json(result)
        data = json.loads(json_output)
        assert data['review']['review_text'] == ''

    def test_missing_patch_info_fields(self):
        """Test formatting with missing patch info fields."""
        result = ReviewResult(
            patch_info={},  # Empty patch info
            review_text='Test review',
            tokens_used=100,
            analysis_time=1.0,
        )

        # Formatters should handle missing fields gracefully
        inline = format_inline(result)
        assert 'AI-ASSISTED PATCH REVIEW' in inline

        markdown = format_markdown(result)
        assert '# AI-Assisted Patch Review' in markdown

        json_output = format_json(result)
        data = json.loads(json_output)
        assert data['patch_info'] == {}

    def test_very_large_review(self):
        """Test formatting with very large review text."""
        large_text = 'Line of review text.\n' * 1000  # 1000 lines
        result = ReviewResult(
            patch_info={'subject': 'Large review'},
            review_text=large_text,
            tokens_used=50000,
            analysis_time=300.5,
        )

        # All formatters should handle large reviews
        inline = format_inline(result)
        assert len(inline) > 10000

        markdown = format_markdown(result)
        assert len(markdown) > 10000

        json_output = format_json(result)
        data = json.loads(json_output)
        assert len(data['review']['review_text']) > 10000

    def test_special_characters_in_text(self):
        """Test formatting with special characters."""
        result = ReviewResult(
            patch_info={
                'subject': 'Fix <unsafe> & "quoted" text',
                'author': "O'Brien <user@example.com>",
            },
            review_text='Review with <brackets> & ampersands and "quotes"',
            tokens_used=100,
            analysis_time=1.0,
        )

        # Inline should preserve special characters
        inline = format_inline(result)
        assert '<unsafe>' in inline
        assert '&' in inline
        assert '"quoted"' in inline

        # Markdown should preserve special characters
        markdown = format_markdown(result)
        assert '<brackets>' in markdown

        # JSON should properly escape special characters
        json_output = format_json(result)
        data = json.loads(json_output)
        assert data['patch_info']['subject'] == 'Fix <unsafe> & "quoted" text'
