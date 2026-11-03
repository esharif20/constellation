# Read each agent harness through a Source adapter

Constellation starts with Claude Code only, but Codex and others are planned. Each harness is read by its own Source adapter that emits harness-neutral Items, so the graph, overlap detection, cost counting and UI never see harness-specific formats. Adding Codex means writing one adapter. We accepted a little up-front abstraction (a shared Item shape) over parsing Claude Code files directly, which would have been quicker but would have leaked its layout into every later stage.
