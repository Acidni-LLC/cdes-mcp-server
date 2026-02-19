"""CDES MCP Server — Public Model Context Protocol server for Cannabis Data Exchange Standard.

Publicly hosted at cdes-mcp.acidni.net.  Exposes all CDES v1 JSON schemas,
reference data (terpene/cannabinoid libraries), and validation tools via SSE
transport.  Auto-syncs with upstream cdes-spec and cdes-reference-data repos.

Version: 1.1.0
License: Apache-2.0
Website: https://cdes.world
"""

from cdes_mcp_server.server import main

__all__ = ["main"]
__version__ = "1.1.0"
