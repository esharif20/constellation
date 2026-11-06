// Lenses: read-only views the server computes from the saved scan (GET /api/lenses). Each ticket adds its own key.
export type ReceiptGroup = { kind: string; count: number; tokens: number | null; bytes: number; unknown: number };
export type ReceiptRow = { id: string | null; kind: string; name: string; tokens: number | null; bytes: number | null };
export type Receipt = { total_tokens: number | null; uncounted_bytes: number; unknown: number; groups: ReceiptGroup[]; rows: ReceiptRow[] };
export type HookRow = { id: string; name: string; event: string; matcher: string | null; phase: string; can_block: boolean; runs: string; bytes: number | null; tokens: number | null };
export type Lenses = { receipt: Receipt; hooks?: HookRow[]; triggers?: Triggers; conflicts?: Conflict[] };
export type TriggerRow = { id: string; name: string; count: number; last_used: string | null; flags: ("never" | "vague" | "greedy")[] };
export type Triggers = { files: number; rows: TriggerRow[] };
export type Conflict = { kind: "hook" | "mcp_name" | "trigger"; key: string; item_ids: string[]; reason: string };

// GET /api/removal?id=: the safe-removal preview for one Item (read-only; nothing is deleted).
export type RemovalRow = { id: string; name: string; kind: string; why: string; verdict?: string };
export type Removal = {
  id: string; name: string; kind: string; safe: boolean; verdict: string; reasons: string[]; loses_coverage: boolean;
  covered_by: RemovalRow[]; cluster: { name: string; others: string[]; more: number } | null;
  referenced_by: RemovalRow[]; hooks: RemovalRow[]; contains: RemovalRow[]; used: number | null; last_used: string | null;
};
