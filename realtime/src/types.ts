export interface Incoming {
  id: string;
  brand: string;
  text: string;
}

export interface QueuedTicket extends Incoming {
  receivedAt: number;
  burst: boolean;
}

export interface Classified {
  category: string;
  priority: string;
  confidence: number;
  route: "model" | "llm" | "deferred";
  model_ms: number;
  llm_ms: number | null;
  student: { category: string; priority: string };
  probs: Record<string, Record<string, number>>;
}

export interface TriagedTicket extends QueuedTicket {
  category: string;
  priority: string;
  confidence: number;
  route: Classified["route"];
  modelMs: number;
  llmMs: number | null;
  student: Classified["student"];
  probs: Classified["probs"];
  doneAt: number;
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
  | { type: "snapshot"; tickets: TriagedTicket[]; queue: QueueStats }
  | { type: "ticket"; ticket: TriagedTicket }
  | { type: "queue"; queue: QueueStats };
