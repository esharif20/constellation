# Plan tracker

The approved plan (decisions D1 to D17) lives outside the repo at `~/.claude/plans/pasted-content-id-d61b-i-think-modular-fog.md`.
This file is the in-repo copy of its status. Update it in every ticket (see "Plan alignment" in CLAUDE.md). A decision that changed is
recorded as a **deviation** with the reason, and the user approves it, instead of drifting silently.

| Decision | Plan | Status | Notes |
|---|---|---|---|
| D1 Source adapter seam | Claude Code only, adapter seam | Done (#2, #4) | ADR 0001 |
| D2 Expansion on demand | click or `expand` opens an Item | Open (#9) | ADR 0002 |
| D3 Overlaps | hash + wrapper, embeddings propose, Sonnet verifies, ~20 labelled pairs | Planned (#6) | plan in `docs/plans/overlaps.md` |
| D4 Privacy | redaction before every provider call, reused by the Snapshot | Done for scan (#3, #5); Snapshot export open (#13) | covers LLM, embedder and counter |
| D5 Suggestions | `interrupt()` per suggestion, approve or skip, writes `cleanup.md` | Open (#7) | never modifies user config |
| D6 Interface | chat on the left, graph on the right, served by FastAPI | Partly (#8 graph); chat open (#11) | |
| D7 CLI | **Typer** `scan, expand, open, export --public` | **Deviation**: `argparse` with `scan` and `open` | fine until `expand` and `export` exist; revisit at #9 or #13 |
| D8 Chat | tool-calling agent driving the graph | Open (#11) | |
| D10 Public demo | sanitised static Snapshot on Vercel | Open (#13, #14, #15) | |
| D11 Context cost | `always_on` and `on_use` tokens, node size = always_on | Counts done (#5); node size from cost open (#10) | |
| D12 Chat agent build | prebuilt `create_react_agent`, maybe rebuilt as a `StateGraph` | Open (#11) | |
| D13 Graph UI | `react-force-graph-2d`, d3-force on canvas, tuned physics, glow, fallback d3-force + PixiJS | In progress | first version used plain d3; being rebuilt |
| D14 Frontend | Vite + React + TS + Tailwind + shadcn/ui, served by FastAPI, static export | **Deviation, being corrected** | #8 first shipped vanilla JS with no build step; Opus design agent rebuilding on branch `ticket-8-design` |
| D15 Models | Haiku 5.5 for volume, Sonnet 5.5 verifier, via `langchain-anthropic` | **Deviation**: Anthropic SDK called directly | simpler and tested; switch only if a LangChain feature is needed |
| D16 Working mode | AI writes code, user stays in the loop, `/tdd` | Active | |
