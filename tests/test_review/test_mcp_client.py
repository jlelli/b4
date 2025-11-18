#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""Tests for MCP client."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from b4.mcp_client import SemcodeMCPClient, MCPConnectionError, MCPToolError


class TestSemcodeMCPClient:
    """Test SemcodeMCPClient class."""

    def test_init_with_explicit_paths(self):
        """Test initialization with explicit paths."""
        with patch.object(Path, 'exists', return_value=True):
            client = SemcodeMCPClient(
                semcode_binary='/usr/bin/semcode-mcp',
                kernel_dir='/home/user/linux',
                semcode_db='/home/user/linux/.semcode.db'
            )
            assert client.semcode_binary == Path('/usr/bin/semcode-mcp')
            assert client.kernel_dir == Path('/home/user/linux')
            assert client.semcode_db == Path('/home/user/linux/.semcode.db')

    def test_init_binary_not_found(self):
        """Test initialization fails if binary not found."""
        with patch.object(Path, 'exists', return_value=False):
            with pytest.raises(MCPConnectionError, match='binary not found'):
                SemcodeMCPClient(
                    semcode_binary='/nonexistent/semcode-mcp',
                    kernel_dir='/tmp'
                )

    def test_find_semcode_binary_common_path(self):
        """Test finding semcode-mcp in common locations."""
        client = SemcodeMCPClient.__new__(SemcodeMCPClient)

        def mock_exists(self):
            return str(self) == str(Path.home() / 'Work/kernel/semcode/target/release/semcode-mcp')

        with patch.object(Path, 'exists', mock_exists):
            binary = client._find_semcode_binary()
            assert 'semcode-mcp' in binary

    def test_find_kernel_dir_from_cwd(self):
        """Test finding kernel directory from current directory."""
        client = SemcodeMCPClient.__new__(SemcodeMCPClient)

        mock_path = Mock(spec=Path)
        mock_path.__truediv__ = lambda self, other: mock_path
        mock_path.exists.return_value = True
        mock_path.parent = mock_path
        mock_path.__ne__ = lambda self, other: False
        mock_path.__str__ = lambda self: '/home/user/linux'

        with patch('b4.mcp_client.Path') as mock_path_class:
            mock_path_class.cwd.return_value = mock_path
            kernel_dir = client._find_kernel_dir()
            assert kernel_dir

    def test_get_tools_before_connect(self):
        """Test get_tools() connects automatically."""
        with patch.object(Path, 'exists', return_value=True):
            client = SemcodeMCPClient(
                semcode_binary='/usr/bin/semcode-mcp',
                kernel_dir='/tmp'
            )

        with patch.object(client, 'connect') as mock_connect:
            client._connected = False
            client._tools = {'test_tool': {}}
            client.get_tools()
            mock_connect.assert_called_once()

    def test_context_manager(self):
        """Test using client as context manager."""
        with patch.object(Path, 'exists', return_value=True):
            client = SemcodeMCPClient(
                semcode_binary='/usr/bin/semcode-mcp',
                kernel_dir='/tmp'
            )

        with patch.object(client, 'connect') as mock_connect, \
             patch.object(client, 'disconnect') as mock_disconnect:

            with client:
                pass

            mock_connect.assert_called_once()
            mock_disconnect.assert_called_once()
