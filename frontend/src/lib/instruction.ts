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
const NAME_MAX = 80;
// A third-party name made safe to paste: one line, no control characters, at most NAME_MAX characters; mirrors clean_name() in answer.py.
export const cleanName = (s: string) => {
  const t = s.replace(/[\s\p{C}]+/gu, " ").trim(), chars = Array.from(t);
  return chars.length <= NAME_MAX ? t : `${chars.slice(0, NAME_MAX - 1).join("")}…`;
};
const quote = (s: string) => `\`${cleanName(s).replaceAll("`", "'")}\``;
const cut = (t: string) => (t.length <= LIMIT ? t : `${t.slice(0, Math.max(t.lastIndexOf(" ", LIMIT), LIMIT - 1)).trimEnd()}…`);

export function instructionFor(item: GNode, model: Pick<Model, "overlapsOf"> & Partial<Pick<Model, "nodes">>, verdict: Verdict): string {
  const name = quote(item.name), label = item.kind === "mcp_server" ? "MCP server" : item.kind.replace(/_/g, " ");
  const os = (model.overlapsOf.get(item) ?? []);
  const rank = ["duplicate", "wrapper", "overlap"];
  const o = [...os].sort((x, y) => rank.indexOf(x.verdict) - rank.indexOf(y.verdict))[0];
  const twin = verdict.twin ? model.nodes?.find((n) => n.id === verdict.twin) : undefined; // the Item the engine compared, not the shown Overlap
  const other = twin ? quote(twin.name) : o ? quote((o.a === item ? o.b : o.a).name) : "";
  const remove = () => {
    let r = (DO[item.kind] ?? `Review the ${label} {n} and tell me how to remove it.`).replace("{n}", name);
    if (item.origin && ["skill", "agent", "mcp_server"].includes(item.kind)) r += ` It came from ${quote(item.origin)}: if that is a plugin or pack, change it there, not inside its folder.`;
    return r;
  };
  let t: string;
  // The server's action decides (smarter-verdict.md 4.4); the Overlap only names the other Item.
  if (verdict.action === "use_underlying" && other) t = `The ${label} ${name} only calls ${other}. Show me how to use ${other} directly, then remove ${name}.`;
  else if (verdict.action === "remove_twin" && other) t = `${remove()} It does the same job as ${other}, which stays.`;
  else if (verdict.action === "move_to_project") t = `Move the ${label} ${name} out of my global setup into the one project that uses it. Leave every other project as it is.`;
  else if (verdict.action === "fix_description") t = `Rewrite the description of the ${label} ${name} so Claude knows when to pick it: say what it does and when to use it. Keep the rest unchanged.`;
  else if (["remove", "disable_plugin", "remove_twin"].includes(verdict.action)) t = remove();
  else t = `Review the ${label} ${name}: tell me what it does and whether I still need it. Change nothing.`;
  if (!t.endsWith("Change nothing.")) t += " Show me exactly what will change and wait for my OK.";
  return cut(t);
}
