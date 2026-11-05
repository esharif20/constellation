// Splits an Item description into "What it does" and "When it triggers" (docs/design/inspector.md section 3). Pure, local.
const START = /^(?:use\s+(?:this\s+)?(?:when|whenever|for|if)\b|triggers?(?:ed)?\s+(?:when|on)\b|invoke\s+when\b|activates\s+(?:on|when)\b|TRIGGER\b)/i;
const WORD = /\b(?:when|whenever|if|triggers?|triggered|invoke[sd]?|activates?)\b/i;
const DOT = "\u0000"; // protects abbreviations from the sentence split
const ABBR = /\b(e\.g|i\.e|etc|vs|approx)\./gi;

export type Described = { does: string; when: string };

export function splitDescription(text: string | null | undefined, label = ""): Described {
  const flat = (text ?? "").replace(/\s+/g, " ").trim();
  if (!flat) return { does: "", when: "" };
  // URLs and decimals have no space after the dot, so they never split.
  const sentences = flat.replace(ABBR, (m) => m.replaceAll(".", DOT)).split(/(?<=[.!?])\s+/).map((s) => s.replaceAll(DOT, "."));
  const does: string[] = [], when: string[] = [];
  let trig = false;
  for (const s of sentences) {
    if (START.test(s) || (trig && WORD.test(s))) { when.push(s); trig = true; }
    else { does.push(s); trig = false; }
  }
  return { does: does.length ? does.join(" ") : when.length ? label : flat, when: when.join(" ") };
}
