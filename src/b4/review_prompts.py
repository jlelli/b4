#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Review prompts loader for AI-assisted patch review."""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ReviewPromptsError(Exception):
    """Error loading or processing review prompts."""
    pass


class ReviewPromptsLoader:
    """
    Loads and manages review prompts from the review-prompts repository.

    The review-prompts repository contains:
    - review-core.md: Main review protocol
    - technical-patterns.md: Pattern reference
    - Subsystem files: scheduler.md, mm.md, networking.md, etc.
    """

    # Subsystem file mapping based on code/function patterns
    SUBSYSTEM_MAP = {
        'networking': {
            'paths': ['net/', 'drivers/net/'],
            'patterns': ['skb_', 'socket', 'netdev_'],
        },
        'mm': {
            'paths': ['mm/'],
            'patterns': ['page_', 'folio_', 'alloc', 'kfree', 'kmalloc'],
        },
        'vfs': {
            'paths': ['fs/'],
            'patterns': ['inode', 'dentry', 'vfs_'],
        },
        'locking': {
            'patterns': ['spin_lock', 'mutex_', 'semaphore', 'rwlock'],
        },
        'scheduler': {
            'paths': ['kernel/sched/'],
            'patterns': ['sched_', 'schedule', 'runqueue', 'wake_up'],
        },
        'bpf': {
            'paths': ['kernel/bpf/'],
            'patterns': ['bpf_', 'verifier'],
        },
        'rcu': {
            'patterns': ['rcu_', 'call_rcu'],
        },
        'fscrypt': {
            'patterns': ['crypto_', 'fscrypt_'],
        },
        'tracing': {
            'patterns': ['trace_', 'tracepoint'],
        },
        'workqueue': {
            'paths': ['kernel/workqueue.c'],
            'patterns': ['workqueue', 'work_struct'],
        },
        'syscall': {
            'patterns': ['SYSCALL_DEFINE', 'sys_'],
        },
        'btrfs': {
            'paths': ['fs/btrfs/'],
        },
        'dax': {
            'patterns': ['dax_'],
        },
        'block': {
            'paths': ['block/', 'drivers/nvme/'],
            'patterns': ['nvme_', 'blk_'],
        },
    }

    def __init__(self, prompts_dir: Optional[str] = None):
        """
        Initialize review prompts loader.

        Args:
            prompts_dir: Path to review-prompts directory.
                        If None, tries to find it automatically.

        Raises:
            ReviewPromptsError: If prompts directory not found
        """
        if prompts_dir:
            self.prompts_dir = Path(prompts_dir)
        else:
            self.prompts_dir = self._find_prompts_dir()

        if not self.prompts_dir.exists():
            raise ReviewPromptsError(f'Review prompts directory not found: {self.prompts_dir}')

        logger.info(f'Loaded review prompts from: {self.prompts_dir}')
        self._cache: Dict[str, str] = {}

    def _find_prompts_dir(self) -> Path:
        """
        Find review-prompts directory automatically.

        Checks in order:
        1. REVIEW_PROMPTS_DIR environment variable
        2. b4.review-prompts-dir git config
        3. ~/Work/kernel/review-prompts (default location)

        Returns:
            Path to prompts directory
        """
        # Try environment variable
        env_dir = os.environ.get('REVIEW_PROMPTS_DIR')
        if env_dir:
            return Path(env_dir)

        # Try git config (TODO: implement config reading)
        # For now, just use default location

        # Default location
        default_dir = Path.home() / 'Work' / 'kernel' / 'review-prompts'
        return default_dir

    def load_core_protocol(self) -> str:
        """
        Load the core review protocol.

        Returns:
            Content of review-core.md
        """
        return self._load_file('review-core.md')

    def load_technical_patterns(self) -> str:
        """
        Load technical patterns reference.

        Returns:
            Content of technical-patterns.md
        """
        return self._load_file('technical-patterns.md')

    def detect_subsystems(self, patch_diff: str) -> List[str]:
        """
        Detect which subsystems are touched by a patch.

        Analyzes the patch diff to determine which subsystem-specific
        prompts should be loaded.

        Args:
            patch_diff: Unified diff text

        Returns:
            List of subsystem names (e.g., ['scheduler', 'mm'])
        """
        subsystems: Set[str] = set()

        # Extract modified file paths from diff
        file_paths = self._extract_file_paths(patch_diff)

        # Extract function/symbol names from diff
        symbols = self._extract_symbols(patch_diff)

        # Check each subsystem
        for subsystem, rules in self.SUBSYSTEM_MAP.items():
            # Check path patterns
            if 'paths' in rules:
                for path_pattern in rules['paths']:
                    if any(path_pattern in fp for fp in file_paths):
                        subsystems.add(subsystem)
                        break

            # Check symbol patterns
            if 'patterns' in rules and subsystem not in subsystems:
                for pattern in rules['patterns']:
                    if any(pattern in sym for sym in symbols):
                        subsystems.add(subsystem)
                        break

        detected = sorted(list(subsystems))
        logger.debug(f'Detected subsystems: {detected}')
        return detected

    def load_subsystem_prompts(self, subsystems: List[str]) -> Dict[str, str]:
        """
        Load prompts for specific subsystems.

        Args:
            subsystems: List of subsystem names

        Returns:
            Dictionary mapping subsystem name to prompt content
        """
        prompts = {}
        for subsystem in subsystems:
            try:
                content = self._load_file(f'{subsystem}.md')
                prompts[subsystem] = content
            except ReviewPromptsError as e:
                logger.warning(f'Failed to load {subsystem}.md: {e}')
                # Continue with other subsystems
        return prompts

    def load_patterns(self, pattern_ids: List[str]) -> Dict[str, str]:
        """
        Load specific technical patterns by ID.

        Args:
            pattern_ids: List of pattern IDs (e.g., ['P001', 'P015'])

        Returns:
            Dictionary mapping pattern ID to pattern content
        """
        # For now, return empty dict - patterns are in technical-patterns.md
        # In the future, we might extract individual patterns
        logger.warning('load_patterns() not fully implemented yet')
        return {}

    def _load_file(self, filename: str) -> str:
        """
        Load a file from the prompts directory.

        Args:
            filename: Name of file to load

        Returns:
            File content as string

        Raises:
            ReviewPromptsError: If file cannot be read
        """
        # Check cache first
        if filename in self._cache:
            return self._cache[filename]

        file_path = self.prompts_dir / filename

        if not file_path.exists():
            raise ReviewPromptsError(f'Prompt file not found: {file_path}')

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Cache for future use
            self._cache[filename] = content
            logger.debug(f'Loaded prompt file: {filename} ({len(content)} chars)')
            return content

        except Exception as e:
            raise ReviewPromptsError(f'Failed to read {filename}: {e}') from e

    def _extract_file_paths(self, diff: str) -> List[str]:
        """Extract modified file paths from diff."""
        paths = []
        for line in diff.split('\n'):
            # Match diff headers: +++ b/path/to/file
            if line.startswith('+++') or line.startswith('---'):
                match = re.search(r'[ab]/(.*?)(\s|$)', line)
                if match:
                    paths.append(match.group(1))
        return paths

    def _extract_symbols(self, diff: str) -> List[str]:
        """Extract function/symbol names from diff."""
        symbols = []

        # Extract from function signatures in diff context
        # Looking for patterns like: function_name(
        func_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        for match in re.finditer(func_pattern, diff):
            symbols.append(match.group(1))

        # Extract from struct/type references
        # Looking for patterns like: struct name { or type_name variable
        type_pattern = r'\b(?:struct|enum|union)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        for match in re.finditer(type_pattern, diff):
            symbols.append(match.group(1))

        return symbols
