#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2025 by Juri Lelli <juri.lelli@redhat.com>
#
"""MCP (Model Context Protocol) client for semcode integration."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPConnectionError(Exception):
    """Failed to connect to MCP server."""
    pass


class MCPToolError(Exception):
    """Error executing MCP tool."""
    pass


class SemcodeMCPClient:
    """
    MCP client for semcode-mcp server.

    Manages connection to semcode-mcp via stdio transport and provides
    tool discovery and invocation capabilities.
    """

    def __init__(
        self,
        semcode_binary: Optional[str] = None,
        kernel_dir: Optional[str] = None,
        semcode_db: Optional[str] = None
    ):
        """
        Initialize semcode MCP client.

        Args:
            semcode_binary: Path to semcode-mcp binary
            kernel_dir: Path to Linux kernel source directory
            semcode_db: Path to .semcode.db directory (default: kernel_dir/.semcode.db)
        """
        # Find semcode-mcp binary
        if not semcode_binary:
            semcode_binary = self._find_semcode_binary()

        self.semcode_binary = Path(semcode_binary)
        if not self.semcode_binary.exists():
            raise MCPConnectionError(f'semcode-mcp binary not found: {semcode_binary}')

        # Find kernel directory
        if not kernel_dir:
            kernel_dir = self._find_kernel_dir()

        self.kernel_dir = Path(kernel_dir)
        if not self.kernel_dir.exists():
            raise MCPConnectionError(f'Kernel directory not found: {kernel_dir}')

        # Set semcode database path
        if semcode_db:
            self.semcode_db = Path(semcode_db)
        else:
            self.semcode_db = self.kernel_dir / '.semcode.db'

        if not self.semcode_db.exists():
            logger.warning(f'semcode database not found: {self.semcode_db}')
            logger.warning('You may need to run: semcode-index in the kernel directory')

        self._process: Optional[subprocess.Popen] = None
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._connected = False

    def _find_semcode_binary(self) -> str:
        """Find semcode-mcp binary in common locations."""
        # Check config (will implement config loading later)
        # For now, check common paths
        common_paths = [
            Path.home() / 'Work' / 'kernel' / 'semcode' / 'target' / 'release' / 'semcode-mcp',
            Path('/usr/local/bin/semcode-mcp'),
            Path('/usr/bin/semcode-mcp'),
        ]

        for path in common_paths:
            if path.exists():
                return str(path)

        # Try PATH
        try:
            result = subprocess.run(['which', 'semcode-mcp'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        raise MCPConnectionError(
            'semcode-mcp binary not found. Please specify path via config or --semcode-binary'
        )

    def _find_kernel_dir(self) -> str:
        """Find Linux kernel directory."""
        # Start from current directory and walk up
        current = Path.cwd()
        while current != current.parent:
            # Check if this looks like a kernel directory
            if (current / 'MAINTAINERS').exists() and (current / 'Kconfig').exists():
                return str(current)
            current = current.parent

        # Fall back to common location
        common_path = Path.home() / 'Work' / 'kernel' / 'linux'
        if common_path.exists():
            return str(common_path)

        raise MCPConnectionError(
            'Linux kernel directory not found. Please run from kernel tree or specify via config'
        )

    def connect(self) -> None:
        """
        Start semcode-mcp subprocess and establish connection.

        Raises:
            MCPConnectionError: If connection fails
        """
        if self._connected:
            logger.debug('Already connected to semcode-mcp')
            return

        logger.info(f'Starting semcode-mcp from {self.semcode_binary}')
        logger.debug(f'Kernel dir: {self.kernel_dir}')
        logger.debug(f'Database: {self.semcode_db}')

        try:
            # Start semcode-mcp as subprocess with stdio transport
            self._process = subprocess.Popen(
                [str(self.semcode_binary)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.kernel_dir),
                env={**os.environ, 'SEMCODE_DB': str(self.semcode_db)}
            )

            # Discover available tools
            self._discover_tools()
            self._connected = True
            logger.info(f'Connected to semcode-mcp, {len(self._tools)} tools available')

        except Exception as e:
            self._cleanup()
            raise MCPConnectionError(f'Failed to start semcode-mcp: {e}') from e

    def _discover_tools(self) -> None:
        """
        Discover available tools from semcode-mcp.

        Uses MCP protocol to query available tools and their schemas.
        """
        # Send tools/list request via MCP protocol
        request = {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'tools/list',
            'params': {}
        }

        response = self._send_request(request)

        if 'error' in response:
            raise MCPConnectionError(f"Tool discovery failed: {response['error']}")

        # Parse tools from response
        tools = response.get('result', {}).get('tools', [])
        for tool in tools:
            tool_name = tool.get('name')
            if tool_name:
                self._tools[tool_name] = tool
                logger.debug(f'Discovered tool: {tool_name}')

        if not self._tools:
            logger.warning('No tools discovered from semcode-mcp')

    def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send JSON-RPC request to semcode-mcp and get response.

        Args:
            request: JSON-RPC request dict

        Returns:
            JSON-RPC response dict

        Raises:
            MCPConnectionError: If communication fails
        """
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise MCPConnectionError('Not connected to semcode-mcp')

        try:
            # Send request
            request_json = json.dumps(request) + '\n'
            self._process.stdin.write(request_json)
            self._process.stdin.flush()

            # Read response
            response_line = self._process.stdout.readline()
            if not response_line:
                raise MCPConnectionError('No response from semcode-mcp')

            response = json.loads(response_line)
            return response

        except json.JSONDecodeError as e:
            raise MCPConnectionError(f'Invalid JSON from semcode-mcp: {e}') from e
        except Exception as e:
            raise MCPConnectionError(f'Communication error: {e}') from e

    def get_tools(self) -> Dict[str, Dict[str, Any]]:
        """
        Get available tools and their schemas.

        Returns:
            Dictionary mapping tool names to their schema definitions
        """
        if not self._connected:
            self.connect()
        return self._tools.copy()

    def invoke_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke a tool via MCP protocol.

        Args:
            name: Tool name
            arguments: Tool arguments as dict

        Returns:
            Tool result as dict

        Raises:
            MCPToolError: If tool invocation fails
        """
        if not self._connected:
            self.connect()

        if name not in self._tools:
            raise MCPToolError(f'Unknown tool: {name}')

        logger.debug(f'Invoking tool: {name} with args: {arguments}')

        # Send tools/call request
        request = {
            'jsonrpc': '2.0',
            'id': self._get_next_id(),
            'method': 'tools/call',
            'params': {
                'name': name,
                'arguments': arguments
            }
        }

        response = self._send_request(request)

        if 'error' in response:
            error = response['error']
            raise MCPToolError(f"Tool {name} failed: {error.get('message', error)}")

        result = response.get('result', {})
        logger.debug(f'Tool {name} completed successfully')

        return result

    def _get_next_id(self) -> int:
        """Get next request ID."""
        if not hasattr(self, '_request_id'):
            self._request_id = 1
        else:
            self._request_id += 1
        return self._request_id

    def disconnect(self) -> None:
        """Disconnect from semcode-mcp server."""
        self._cleanup()
        self._connected = False
        logger.info('Disconnected from semcode-mcp')

    def _cleanup(self) -> None:
        """Clean up subprocess resources."""
        if self._process:
            try:
                self._process.stdin.close()  # type: ignore
                self._process.stdout.close()  # type: ignore
                self._process.stderr.close()  # type: ignore
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception as e:
                logger.warning(f'Error cleaning up semcode-mcp process: {e}')
                try:
                    self._process.kill()
                except Exception:
                    pass
            finally:
                self._process = None

    def __enter__(self) -> 'SemcodeMCPClient':
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.disconnect()

    def __del__(self) -> None:
        """Cleanup on deletion."""
        if hasattr(self, '_process'):
            self._cleanup()
