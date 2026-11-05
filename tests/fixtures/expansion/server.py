"""Synthetic MCP peer: no external services, tools, credentials, or user config."""

import json
import os
import signal
import sys
import time
from pathlib import Path

mode, record = sys.argv[1:]
record = Path(record)
record.write_text(
    json.dumps(
        {
            "pid": os.getpid(),
            "cwd": str(Path.cwd()),
            "home": os.getenv("HOME"),
            "sentinel": os.getenv("EXPANSION_AMBIENT_SENTINEL"),
            "configured": os.getenv("FIXTURE_SECRET"),
            "environment": {name: os.getenv(name) for name in ("HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER")},
        }
    )
    + "\n"
)
print("FIXTURE_LEAK", file=sys.stderr, flush=True)
if mode in ("stubborn", "timeout"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
for line in sys.stdin:
    message = json.loads(line)
    with record.open("a") as output:
        output.write(json.dumps(message) + "\n")
    method = message.get("method")
    if "id" not in message:
        continue
    if mode == "slow" and method == "tools/list":
        time.sleep(1.0)
    if mode == "timeout":
        continue
    if mode == "malformed":
        print("invalid FIXTURE_LEAK", flush=True)
        continue
    if mode == "failure":
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32000, "message": "FIXTURE_LEAK"}}), flush=True)
        print("FIXTURE_LEAK", file=sys.stderr, flush=True)
        continue
    if method == "initialize":
        result = {
            "protocolVersion": message["params"]["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "synthetic", "version": "1"},
            "instructions": "FIXTURE_LEAK",
        }
    elif method == "tools/list":
        cursor = message.get("params", {}).get("cursor")
        if mode == "empty":
            result = {"tools": []}
        elif cursor:
            result = {
                "tools": [{"name": "alpha", "description": "First tool", "inputSchema": {"type": "object", "description": "FIXTURE_LEAK"}}]
            }
        else:
            result = {"tools": [{"name": "zeta", "inputSchema": {"type": "object"}}], "nextCursor": "page-two"}
        if mode in ("pages-limit", "pages-over"):
            page = int(cursor or "0") + 1
            result = {"tools": []}
            if page < (100 if mode == "pages-limit" else 101):
                result["nextCursor"] = str(page)
        if mode in ("tools-limit", "tools-over", "tools-pages-over"):
            count = 1 if cursor else (1001 if mode == "tools-over" else 1000)
            result = {"tools": [{"name": "safe", "inputSchema": {"type": "object"}}] * count}
            if mode != "tools-limit":
                result["nextCursor"] = "extra-page" if cursor else "page-two"
        if mode in ("text-limit", "text-over", "name-over"):
            name = "n" * 4097 if mode == "name-over" else "safe"
            description = "é" * (2048 if mode == "text-limit" else 2049)
            result = {"tools": [{"name": name, "description": description, "inputSchema": {"type": "object"}}]}
            if mode != "text-limit":
                result["nextCursor"] = "must-not-fetch"
        if mode == "repeated":
            result["nextCursor"] = "page-two"
        if mode == "late-failure" and cursor:
            print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32000, "message": "FIXTURE_LEAK"}}), flush=True)
            continue
    else:
        raise AssertionError("Expansion must only initialize and list tools")
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
if mode in ("stubborn", "timeout"):
    while True:
        time.sleep(0.1)
