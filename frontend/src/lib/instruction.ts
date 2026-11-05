// The copyable Claude Code instruction for an Item. Mirrors handoff() in src/constellation/answer.py (the Ask card's hand-off):
// keep the wording in step with it; inspector:check pins the strings. Pure, nothing is sent anywhere.
import type { GNode, Model } from "@/graph/model";
import type { Verdict } from "@/lib/verdict";

const DO: Record<string, string> = {
  skill: "Remove the skill {n}: find its folder (under ~/.claude/skills) and delete only that folder.",
  agent: "Remove the agent {n}: find its file (under ~/.claude/agents) and delete only that file.",
  command: "Remove the command {n}: find its file (under ~/.claude/commands) and delete only that file.",
  mcp_server: "Remove the MCP server {n} from my Claude Code config, in the scope where it is defined.",
  plugin: "Disable the plugin {n} in my user settings.json enabledPlugins; do not delete files.",
  hook: "Remove the hook {n} from the hooks section of my settings.json.",
  connector: "Disconnect the connector {n}. It is managed in claude.ai, so tell me where to click.",
};
const LIMIT = 400;
const quote = (s: string) => `"${s.replaceAll('"', "'")}"`;
const cut = (t: string) => (t.length <= LIMIT ? t : `${t.slice(0, Math.max(t.lastIndexOf(" ", LIMIT), LIMIT - 1)).trimEnd()}…`);

export function instructionFor(item: GNode, model: Pick<Model, "overlapsOf">, verdict: Verdict): string {
  const name = quote(item.name), label = item.kind === "mcp_server" ? "MCP server" : item.kind.replace(/_/g, " ");
  const os = (model.overlapsOf.get(item) ?? []);
  const rank = ["duplicate", "wrapper", "overlap"];
  const o = [...os].sort((x, y) => rank.indexOf(x.verdict) - rank.indexOf(y.verdict))[0];
  const other = o ? quote((o.a === item ? o.b : o.a).name) : "";
  let t: string;
  if (verdict.tone === "keep" || (verdict.label === "Not enough data" && item.kind !== "plugin")) t = `Review the ${label} ${name}: tell me what it does and whether I still need it. Change nothing.`;
  else if (o?.verdict === "duplicate") t = `The ${label} ${name} and ${other} do the same job. Compare them and recommend which to remove; remove nothing until I choose.`;
  else if (o?.verdict === "wrapper" && o.a === item) t = `The ${label} ${name} only calls ${other}. Show me how to use ${other} directly, then remove ${name}.`;
  else if (o) t = `Keep the ${label} ${name}; ${other} calls it. Change nothing.`;
  else {
    t = (DO[item.kind] ?? `Review the ${label} {n} and tell me how to remove it.`).replace("{n}", name);
    if (item.origin && ["skill", "agent", "command", "hook", "mcp_server"].includes(item.kind)) t += ` It came from ${quote(item.origin)}: if that is a plugin or pack, change it there, not inside its folder.`;
  }
  if (!t.endsWith("Change nothing.")) t += " Show me exactly what will change and wait for my OK.";
  return cut(t);
}
