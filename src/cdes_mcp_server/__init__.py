"""CDES MCP Server — Public Model Context Protocol server for Cannabis Data Exchange Standard.

Exposes all CDES v1 JSON schemas, reference data (terpene/cannabinoid libraries),
and validation tools via the MCP protocol (stdio transport).

Version: 1.0.0
License: Apache-2.0
Website: https://cdes.world
"""

from cdes_mcp_server.server import main

__all__ = ["main"]
__version__ = "1.0.0"
