export const CATEGORIES = [
  "billing",
  "delivery",
  "account",
  "technical",
  "travel",
  "service",
  "question",
  "other",
] as const;

export const PRIORITIES = ["high", "medium", "low"] as const;

export type Category = (typeof CATEGORIES)[number];
export type Priority = (typeof PRIORITIES)[number];
export type Route = "model" | "llm" | "deferred";

export interface Ticket {
  id: string;
  brand: string;
  text: string;
  receivedAt: number;
  doneAt: number;
  burst: boolean;
  category: Category;
  priority: Priority;
  confidence: number;
  route: Route;
  modelMs: number;
  llmMs: number | null;
  student: { category: Category; priority: Priority };
  probs: { category: Record<string, number>; priority: Record<string, number> };
}

export interface QueueStats {
  waiting: number;
  active: number;
  failed: number;
  doneLastMinute: number;
  ratePerSec: number;
  burstReadyInMs: number;
}

export type ServerEvent =
  | { type: "snapshot"; tickets: Ticket[]; queue: QueueStats }
  | { type: "ticket"; ticket: Ticket }
  | { type: "queue"; queue: QueueStats };

export interface DraftExample {
  brand: string;
  ticket: string;
  reply: string;
  similarity: number;
  rerank_score: number | null;
}

export interface Draft {
  draft: string | null;
  examples: DraftExample[];
  reason: string | null;
}
