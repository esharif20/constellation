// "What it's for": one plain sentence per Item, derived locally from its kind and description. Pure; no provider, no files.
import { splitDescription } from "@/lib/describe";
import { hookInfo } from "@/lib/details";
import { cleanName } from "@/lib/instruction";
import type { GNode, Model } from "@/graph/model";

const MAX = 140;
// First sentence, trimmed at a word boundary so it never ends mid-word.
export function firstSentence(text: string): string {
  const flat = text.replace(/\s+/g, " ").trim();
  const m = flat.match(/^.*?[.!?](?=\s|$)/);
  const s = m ? m[0] : flat;
  if (s.length <= MAX) return s;
  return `${s.slice(0, Math.max(s.lastIndexOf(" ", MAX - 1), 40)).replace(/[\s,;:.]+$/, "")}…`;
}

const EVENT: Record<string, string> = {
  SessionStart: "a Claude Code session starts", UserPromptSubmit: "you send a prompt", PreToolUse: "Claude is about to use a tool", PostToolUse: "Claude has just used a tool",
  Stop: "Claude finishes a reply", SubagentStop: "a helper agent finishes", Notification: "Claude needs your attention", PreCompact: "the conversation is about to be compacted", SessionEnd: "a session ends",
};
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

export function whatFor(item: GNode, model: Pick<Model, "links">): string {
  if (item.kind === "hook") {
    const h = hookInfo(item);
    if (!h.event) return "A hook: a command that runs automatically. Its event is not named, so Constellation cannot say when.";
    const when = EVENT[h.event] ?? `the ${cleanName(h.event)} event fires`, on = h.matcher && h.matcher !== "all tools" ? ` (for ${cleanName(h.matcher)})` : "";
    return `Runs automatically when ${when}${on}. ${h.canBlock ? "It can stop the action." : "It cannot stop the action."}`;
  }
  if (item.kind === "plugin") {
    const parts = model.links.filter((l) => l.source === item && l.kind === "contains");
    if (!parts.length) return "A plugin that bundles skills, agents or hooks. This one lists no parts.";
    const by = new Map<string, number>();
    for (const l of parts) by.set(l.target.kind, (by.get(l.target.kind) ?? 0) + 1);
    return `Bundles ${[...by].map(([k, n]) => plural(n, k.replace(/_/g, " "))).join(", ")}. Turning it off turns all of them off.`;
  }
  if (item.kind === "mcp_server") {
    const shape = /^(stdio|http|sse)\b/i.exec(item.description)?.[1]?.toLowerCase();
    return `Connects Claude Code to the ${cleanName(item.name)} server${shape ? ` over ${shape}` : ""}, which adds its tools to every session.`;
  }
  if (item.kind === "connector") return "A claude.ai connector. Constellation only sees it in transcripts, so it cannot say what it offers.";
  const { does, when } = splitDescription(item.description, item.label);
  const text = does || when;
  return text ? firstSentence(text) : "No description, so Claude has little to go on when choosing it.";
}
