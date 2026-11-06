"""Real stdio MCP server: three tools, one slow, one noisy on stderr, junk on stdout before the protocol starts."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import _pid  # noqa: E402,F401
from mcp.server.mcpserver import MCPServer  # noqa: E402

server = MCPServer("fixture-good")
print("junk line on stdout, not JSON-RPC", flush=True)  # a careless server; the client must not choke on it


@server.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@server.tool()
def slow_echo(text: str) -> str:
    """Echo text after a pause."""
    time.sleep(2)
    return text


@server.tool()
def noisy(text: str) -> str:
    """Write junk to stderr, then echo."""
    sys.stderr.write("stderr junk /private/raw/path\n" * 50)
    return text


if __name__ == "__main__":
    sys.stderr.write("stderr junk at start /private/raw/path\n")
    server.run("stdio")
