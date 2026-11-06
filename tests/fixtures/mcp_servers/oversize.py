"""Answers the protocol correctly but with a tool description over the size limit."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import _pid  # noqa: E402,F401
from mcp.server.mcpserver import MCPServer  # noqa: E402

server = MCPServer("fixture-oversize")


def big() -> str:
    return "x"


big.__doc__ = "y" * 100_000
server.tool()(big)

if __name__ == "__main__":
    server.run("stdio")
