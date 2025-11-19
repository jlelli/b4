#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Tests for review prompts loader."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from b4.review_prompts import ReviewPromptsLoader, ReviewPromptsError


class TestReviewPromptsLoader:
    """Test ReviewPromptsLoader class."""

    @pytest.fixture
    def mock_prompts_dir(self, tmp_path):
        """Create a mock prompts directory with test files."""
        prompts_dir = tmp_path / "review-prompts"
        prompts_dir.mkdir()

        # Create mock prompt files
        (prompts_dir / "review-core.md").write_text(
            "# Review Protocol\nCore review instructions..."
        )
        (prompts_dir / "technical-patterns.md").write_text(
            "# Technical Patterns\nPattern P001: Memory safety..."
        )
        (prompts_dir / "scheduler.md").write_text(
            "# Scheduler Subsystem\nScheduler-specific checks..."
        )
        (prompts_dir / "mm.md").write_text(
            "# Memory Management\nMM subsystem checks..."
        )
        (prompts_dir / "locking.md").write_text(
            "# Locking\nLocking pattern checks..."
        )

        return prompts_dir

    def test_init_with_explicit_dir(self, mock_prompts_dir):
        """Test initialization with explicit directory."""
        loader = ReviewPromptsLoader(str(mock_prompts_dir))
        assert loader.prompts_dir == mock_prompts_dir

    def test_init_with_nonexistent_dir(self):
        """Test initialization fails with nonexistent directory."""
        with pytest.raises(ReviewPromptsError, match='not found'):
            ReviewPromptsLoader('/nonexistent/path')

    def test_load_core_protocol(self, mock_prompts_dir):
        """Test loading core protocol file."""
        loader = ReviewPromptsLoader(str(mock_prompts_dir))
        content = loader.load_core_protocol()

        assert "Review Protocol" in content
        assert "Core review instructions" in content

    def test_load_technical_patterns(self, mock_prompts_dir):
        """Test loading technical patterns file."""
        loader = ReviewPromptsLoader(str(mock_prompts_dir))
        content = loader.load_technical_patterns()

        assert "Technical Patterns" in content
        assert "P001" in content

    def test_file_caching(self, mock_prompts_dir):
        """Test that files are cached after first load."""
        loader = ReviewPromptsLoader(str(mock_prompts_dir))

        # Load file twice
        content1 = loader.load_core_protocol()
        content2 = loader.load_core_protocol()

        # Should return same cached content
        assert content1 == content2
        assert 'review-core.md' in loader._cache

    def test_load_missing_file(self, mock_prompts_dir):
        """Test loading a file that doesn't exist."""
        loader = ReviewPromptsLoader(str(mock_prompts_dir))

        with pytest.raises(ReviewPromptsError, match='not found'):
            loader._load_file('nonexistent.md')

    def test_detect_subsystems_scheduler(self):
        """Test subsystem detection for scheduler patches."""
        loader = ReviewPromptsLoader.__new__(ReviewPromptsLoader)

        diff = """
diff --git a/kernel/sched/core.c b/kernel/sched/core.c
--- a/kernel/sched/core.c
+++ b/kernel/sched/core.c
@@ -100,7 +100,7 @@ static void __schedule(void)
     struct rq *rq = this_rq();
-    schedule_debug(prev);
+    schedule_debug(prev, false);
"""

        subsystems = loader.detect_subsystems(diff)
        assert 'scheduler' in subsystems

    def test_detect_subsystems_mm(self):
        """Test subsystem detection for memory management patches."""
        loader = ReviewPromptsLoader.__new__(ReviewPromptsLoader)

        diff = """
diff --git a/mm/page_alloc.c b/mm/page_alloc.c
--- a/mm/page_alloc.c
+++ b/mm/page_alloc.c
@@ -100,7 +100,7 @@ static struct page *alloc_page(gfp_t gfp)
-    page = __alloc_pages(gfp, 0, node);
+    page = __alloc_pages_node(node, gfp, 0);
"""

        subsystems = loader.detect_subsystems(diff)
        assert 'mm' in subsystems

    def test_detect_subsystems_locking(self):
        """Test subsystem detection based on function patterns."""
        loader = ReviewPromptsLoader.__new__(ReviewPromptsLoader)

        diff = """
diff --git a/fs/inode.c b/fs/inode.c
--- a/fs/inode.c
+++ b/fs/inode.c
@@ -100,7 +100,7 @@ void inode_lock(struct inode *inode)
-    mutex_lock(&inode->i_mutex);
+    spin_lock(&inode->i_lock);
"""

        subsystems = loader.detect_subsystems(diff)
        # Should detect both locking (spin_lock) and vfs (fs/ path)
        assert 'locking' in subsystems
        assert 'vfs' in subsystems

    def test_detect_subsystems_multiple(self):
        """Test detecting multiple subsystems."""
        loader = ReviewPromptsLoader.__new__(ReviewPromptsLoader)

        diff = """
diff --git a/kernel/sched/core.c b/kernel/sched/core.c
--- a/kernel/sched/core.c
+++ b/kernel/sched/core.c
@@ -100,7 +100,7 @@ static void __schedule(void)
-    spin_lock(&rq->lock);
+    spin_lock_irqsave(&rq->lock, flags);

diff --git a/mm/slab.c b/mm/slab.c
--- a/mm/slab.c
+++ b/mm/slab.c
@@ -50,7 +50,7 @@ void *kmalloc(size_t size, gfp_t flags)
-    return __kmalloc(size, flags);
+    return __do_kmalloc(size, flags);
"""

        subsystems = loader.detect_subsystems(diff)
        assert 'scheduler' in subsystems
        assert 'locking' in subsystems
        assert 'mm' in subsystems

    def test_load_subsystem_prompts(self, mock_prompts_dir):
        """Test loading subsystem-specific prompts."""
        loader = ReviewPromptsLoader(str(mock_prompts_dir))

        prompts = loader.load_subsystem_prompts(['scheduler', 'mm'])

        assert 'scheduler' in prompts
        assert 'mm' in prompts
        assert 'Scheduler Subsystem' in prompts['scheduler']
        assert 'Memory Management' in prompts['mm']

    def test_load_subsystem_prompts_missing(self, mock_prompts_dir):
        """Test loading subsystem prompt that doesn't exist."""
        loader = ReviewPromptsLoader(str(mock_prompts_dir))

        # Should log warning but not raise exception
        prompts = loader.load_subsystem_prompts(['nonexistent'])

        # Missing subsystem should not be in result
        assert 'nonexistent' not in prompts

    def test_load_subsystem_prompts_partial(self, mock_prompts_dir):
        """Test loading mix of existing and non-existing subsystems."""
        loader = ReviewPromptsLoader(str(mock_prompts_dir))

        prompts = loader.load_subsystem_prompts(['scheduler', 'nonexistent', 'mm'])

        # Should load existing ones
        assert 'scheduler' in prompts
        assert 'mm' in prompts
        # Should skip missing one
        assert 'nonexistent' not in prompts

    def test_extract_file_paths(self):
        """Test file path extraction from diff."""
        loader = ReviewPromptsLoader.__new__(ReviewPromptsLoader)

        diff = """
diff --git a/kernel/sched/core.c b/kernel/sched/core.c
--- a/kernel/sched/core.c
+++ b/kernel/sched/core.c
diff --git a/mm/page_alloc.c b/mm/page_alloc.c
--- a/mm/page_alloc.c
+++ b/mm/page_alloc.c
"""

        paths = loader._extract_file_paths(diff)
        assert 'kernel/sched/core.c' in paths
        assert 'mm/page_alloc.c' in paths

    def test_extract_symbols(self):
        """Test symbol extraction from diff."""
        loader = ReviewPromptsLoader.__new__(ReviewPromptsLoader)

        diff = """
@@ -100,7 +100,7 @@ static void __schedule(void)
     struct rq *rq = this_rq();
     spin_lock_irqsave(&rq->lock, flags);
     page = alloc_page(gfp);
"""

        symbols = loader._extract_symbols(diff)
        # Should find function calls
        assert '__schedule' in symbols or 'this_rq' in symbols or 'spin_lock_irqsave' in symbols
        # Should find struct references
        assert 'rq' in symbols

    def test_find_prompts_dir_env_var(self, mock_prompts_dir):
        """Test finding prompts dir from environment variable."""
        loader = ReviewPromptsLoader.__new__(ReviewPromptsLoader)

        with patch.dict('os.environ', {'REVIEW_PROMPTS_DIR': str(mock_prompts_dir)}):
            prompts_dir = loader._find_prompts_dir()
            assert prompts_dir == mock_prompts_dir

    def test_find_prompts_dir_default(self):
        """Test finding prompts dir uses default location."""
        loader = ReviewPromptsLoader.__new__(ReviewPromptsLoader)

        with patch.dict('os.environ', {}, clear=True):
            prompts_dir = loader._find_prompts_dir()
            expected = Path.home() / 'Work' / 'kernel' / 'review-prompts'
            assert prompts_dir == expected
