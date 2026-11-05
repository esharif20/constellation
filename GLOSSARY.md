# Constellation

A tool that maps a developer's AI coding-agent setup as an explorable graph, so they can see what is installed, what overlaps, what it costs in context, and what could go wrong.

## Language

**Item**:
Any single capability found in an agent setup: a skill, plugin, MCP server, MCP tool, hook, or agent.
_Avoid_: Component, extension, asset, entry

**Source adapter**:
The part that reads one agent harness's setup (Claude Code first, Codex later) and reports its Items in a harness-neutral shape.
_Avoid_: Scanner, parser, loader, provider

**Provider**:
The model or embedder a scan calls out to. Every call goes through the redaction guard, and a failed call becomes a warning, not an aborted scan. Not a Source adapter.
_Avoid_: Backend, client, service

**Constellation**:
The full map of one setup: its Items, the relations between them, their groupings, and their context costs.
_Avoid_: Graph (when meaning the whole map), report, inventory

**Relation**:
A labelled link between two Items, such as "contains", "triggers", "duplicates" or "wraps".
_Avoid_: Edge, connection, dependency

**Overlap**:
A pair of Items that do the same or a similar job. Each Overlap carries a verdict: duplicate, wrapper, overlap, or distinct.
_Avoid_: Conflict, clash, similarity

**Lens**:
A read-only view computed from the saved scan at request time (like the cleanup brief), with no provider call and nothing added to the public Snapshot. Served together by `GET /api/lenses`.
_Avoid_: Report, dashboard, panel

**Session-start receipt**:
The Lens listing what loads before the first prompt: hooks, CLAUDE.md, always-on descriptions and MCP tool schemas, with tokens, bytes or unknown for each and a total of the known tokens.
_Avoid_: Invoice, bill, budget

**Expansion**:
Opening one Item to fetch its detail on demand, for example listing the tools behind an MCP server.
_Avoid_: Drill-down, zoom, details view

**Context cost**:
The tokens an Item adds to an agent's context window, split into always-on and on-use.
_Avoid_: Token usage, size, weight

**Always-on cost**:
The part of an Item's Context cost paid in every session, such as its name and description in the skill list.
_Avoid_: Base cost, fixed cost

**On-use cost**:
The part of an Item's Context cost paid only when the Item is invoked, such as a skill's full instructions.
_Avoid_: Runtime cost, invocation cost

**Suggestion**:
A proposed clean-up of a setup, such as removing a duplicate. A Suggestion is only ever a proposal; the user approves or skips it.
_Avoid_: Fix, recommendation, action

**Snapshot**:
A sanitised, read-only copy of a Constellation that is safe to publish.
_Avoid_: Export (when meaning the artefact), dump, backup
