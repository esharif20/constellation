// Lenses: read-only views the server computes from the saved scan (GET /api/lenses). Each ticket adds its own key.
export type ReceiptGroup = { kind: string; count: number; tokens: number | null; bytes: number; unknown: number };
export type ReceiptRow = { id: string | null; kind: string; name: string; tokens: number | null; bytes: number | null };
export type Receipt = { total_tokens: number | null; uncounted_bytes: number; unknown: number; groups: ReceiptGroup[]; rows: ReceiptRow[] };
export type Lenses = { receipt: Receipt; triggers?: Triggers };
export type TriggerRow = { id: string; name: string; count: number; last_used: string | null; flags: ("never" | "vague" | "greedy")[] };
export type Triggers = { files: number; rows: TriggerRow[] };
