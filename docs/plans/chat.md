# Plan: grounded chat (#11)

Status: started with a proposed contract; no chat implementation or paid calls yet.
Read alongside issue #11, ADR 0001/0003 and the privacy/cost rules in AGENTS.md.

## Contract and ownership

- Python owns retrieval, tool results and validated graph actions; React renders returned text/actions without inventing Item ids.
- Public seam: POST /api/chat with a question, returning answer text plus actions referencing known Item ids only. Use the localhost/origin guards added by #25.
- Tools: search Items, explain an Item, report top always-on costs, focus and filter. Expansion delegates to #9 when available; it never starts arbitrary client-supplied commands.
- Use the planned LangGraph tool-calling agent with an injected fake model in tests; verify the installed framework API before implementing an SDK adapter. No paid development/evaluation calls.
- Test the specified email query, explanations, top five costs, unknown costs, hallucinated/unknown ids, empty setup, provider failures and malicious instruction text in descriptions through the HTTP API. Responses must remain grounded in retrieved Items.
- Keep chat/module tests independently owned. One integration owner edits server.py, cli.py, model types and Atlas.tsx after #25. Write backend/public-seam tests first; UI follows DESIGN.md and demo-only visual checks.

## Privacy/cost decision to settle before enabling a real model

Current policy limits provider inputs to redacted Item kinds/names/descriptions and short local signals, and limits paid work to changed Items. A normal conversational agent would also transmit a redacted question and incur a call per interaction. Do not silently widen those rules. Prepare fixture-based tools and the API contract independently; confirm the intended chat input/billing policy before enabling a provider-backed endpoint. Never send transcripts or file bodies.

## Completion

Backend and UI must both meet issue #11 acceptance. Run all existing Python, mutation and frontend gates. Do not call a contract draft a completed chat feature. Static/canned operation for #13 must bypass model APIs entirely.
