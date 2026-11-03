# Fetch Item detail by Expansion, not during the scan

A full scan shows one node per skill, plugin, MCP server and hook. Detail such as an MCP server's tool list is fetched only when the user opens that node (an Expansion). This keeps scans fast and cheap, avoids connecting to every MCP server on every run (some are unreachable or behind authentication), and keeps the default map readable. The trade-off is that totals like "how many tools do I have" are incomplete until servers have been expanded.
