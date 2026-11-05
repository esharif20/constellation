// Per-kind facts for the Inspector (docs/design/inspector.md section 4). Pure; nothing here reads files or calls a provider.
import type { GNode } from "@/graph/model";

const PROMPT_TIME = ["SessionStart", "UserPromptSubmit"];
const CAN_BLOCK = ["PreToolUse", "PermissionRequest", "UserPromptSubmit", "Stop", "SubagentStop"];

// A hook is named "Event:matcher"; a name without a colon carries no event, which stays unknown rather than guessed.
export function hookInfo(item: GNode) {
  const i = item.name.indexOf(":");
  const event = i < 0 ? null : item.name.slice(0, i), matcher = i < 0 ? null : item.name.slice(i + 1);
  return { event, matcher: event ? matcher || "all tools" : null, promptTime: !!event && PROMPT_TIME.includes(event), canBlock: !!event && CAN_BLOCK.includes(event) };
}

// Always-on total of a plugin's contents: the sum of the known costs and how many are unknown (never counted as 0).
export function pluginInfo(children: GNode[]) {
  const known = children.flatMap((c) => c.cost?.always_on ?? []);
  const counts = new Map<string, number>();
  for (const c of children) counts.set(c.kind, (counts.get(c.kind) ?? 0) + 1);
  const tracked = children.filter((c) => c.usage);
  return { counts: [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])), total: known.length ? known.reduce((a, b) => a + b, 0) : null, unknown: children.length - known.length, tracked: tracked.length, unseen: tracked.filter((c) => c.usage!.count === 0).length };
}
