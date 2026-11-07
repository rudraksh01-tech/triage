import raw from "@/data/results.json";

type Scores = { accuracy: number; macro_f1: number };
type TaskScores = { category: Scores; priority: Scores };

export interface CurvePoint {
  threshold: number;
  escalated: number;
  category_accuracy: number;
  priority_accuracy: number;
  category_macro_f1: number;
  priority_macro_f1: number;
}

interface Student {
  base: string;
  lora: boolean;
  trainable_params: number;
  total_params: number;
  train_minutes: number;
  epochs: number;
  student_only: TaskScores;
}

export interface LoadScenario {
  name: string;
  rps: number;
  requests: number;
  failed: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
}

interface Latency {
  p50_ms: number;
  p95_ms: number;
}

export interface Results {
  threshold: number;
  data?: { tickets: number; brands: number; gold: number; train: number; val: number; teacher: string };
  baseline?: {
    teachers_vs_reference: Record<string, TaskScores>;
    student: Record<"category" | "priority", { gold: Scores; ms_per_ticket: number }>;
  };
  students?: { full?: Student; lora?: Student };
  calibration?: Record<string, { temperature: number; gold_ece_before: number; gold_ece_after: number }>;
  cascade?: {
    size: number;
    student_only: TaskScores;
    llm_only: Record<string, TaskScores>;
    curves: Record<string, CurvePoint[]>;
  };
  export?: {
    size_mb: Record<string, number>;
    agreement_with_torch: Record<string, Record<string, number>>;
    latency: Record<string, Latency>;
  };
  retrieval?: Record<string, { reply_similarity_mean: number; same_brand_at_1: number; ms_per_query: number }> & {
    n: number;
  };
  loadtest?: {
    runs: Record<string, LoadScenario[]>;
    machine: string;
  };
}

export const results = raw as unknown as Results;
export const FALLBACK_LLM = "gemini-3.5-flash-lite";
