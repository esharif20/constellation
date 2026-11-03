# Run locally against real config; publish only a sanitised Snapshot

The live app is a local FastAPI server because it must read the user's real agent config, call MCP servers and run LangGraph agents, none of which belong on a public host. For portfolio use, a separate export step produces a sanitised, read-only Snapshot that deploys as a static site on Vercel. We rejected a hosted multi-user version: it would require uploading people's configs, which contain secrets-adjacent data. The Snapshot export reuses the same redaction as the LLM-bound path, so there is one privacy rule, not two.
