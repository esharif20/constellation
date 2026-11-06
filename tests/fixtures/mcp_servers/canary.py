"""Real server that leaks its own env value and path in a tool description, to prove redaction."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import _pid  # noqa: E402,F401
from mcp.server.mcpserver import MCPServer  # noqa: E402

server = MCPServer("fixture-canary")


def leak() -> str:
    return "x"


leak.__doc__ = f"Uses key {os.environ['CANARY_SECRET']} from {os.path.abspath(__file__)}"
server.tool(name=f"tool_{os.environ['CANARY_SECRET']}")(leak)

if __name__ == "__main__":
    server.run("stdio")
