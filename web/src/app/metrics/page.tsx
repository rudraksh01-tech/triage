import type { Metadata } from "next";
import Link from "next/link";
import { CascadeChart } from "@/components/CascadeChart";
import { pct } from "@/lib/format";
import { FALLBACK_LLM, results as r } from "@/lib/results";

export const metadata: Metadata = {
  title: "Triage · Results",
  description: "How the cascade was trained, calibrated and measured.",
};

const RETRIEVAL_METHODS = [
  ["random", "Random past reply"],
  ["embedding", "Embedding search"],
  ["embedding_brand", "Embedding + same-brand boost (deployed)"],
  ["rerank", "Cross-encoder rerank"],
  ["rerank_brand", "Rerank + same-brand boost"],
] as const;

const fmt = (n: number) => n.toLocaleString("en-US");
const ms = (n: number) => (n < 100 ? `${n.toFixed(1)} ms` : `${(n / 1000).toFixed(2)} s`);

function Section({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: string;
  lead?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="border-t border-line py-10">
      <h2 className="text-[17px] font-semibold tracking-[-0.01em]">{title}</h2>
      {lead && <p className="mt-2 max-w-[68ch] text-ink-2">{lead}</p>}
      <div className="mt-6">{children}</div>
    </section>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-4">
      <div className="text-2xs text-ink-3">{label}</div>
      <div className="tnum mt-1 font-mono text-[26px] leading-8 tracking-[-0.02em] text-ink">{value}</div>
      <div className="mt-1 text-2xs text-ink-3">{note}</div>
    </div>
  );
}

function Table({ head, rows, highlight }: { head: string[]; rows: (string | number)[][]; highlight?: number }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-surface">
      <table className="w-full min-w-[560px] text-left">
        <thead>
          <tr className="border-b border-line text-2xs text-ink-3">
            {head.map((h, i) => (
              <th key={h} className={`px-4 py-2.5 font-medium ${i ? "text-right" : ""}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row, ri) => (
            <tr key={ri} className={ri === highlight ? "bg-accent-soft/50" : ""}>
              {row.map((c, i) => (
                <td key={i} className={`px-4 py-2.5 ${i ? "tnum text-right font-mono text-[12px]" : "text-ink"}`}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Metrics() {
  const curve = r.cascade?.curves[FALLBACK_LLM];
  const llmOnly = r.cascade?.llm_only[FALLBACK_LLM];
  const at = curve?.find((p) => p.threshold === r.threshold);
  const int8 = r.export?.latency.onnx_int8;

  return (
    <div className="min-h-dvh">
      <header className="flex h-14 items-center gap-3 border-b border-line bg-surface px-4">
        <Link href="/" className="text-ink-2 hover:text-ink">
          ← Inbox
        </Link>
        <span className="text-ink-3">/</span>
        <span className="font-medium">Results</span>
      </header>

      <main className="mx-auto max-w-[920px] px-4 pb-24 sm:px-6">
        <div className="py-10">
          <h1 className="text-[24px] font-semibold tracking-[-0.02em]">How the cascade was measured</h1>
          <p className="mt-3 max-w-[68ch] text-[14px] leading-6 text-ink-2">
            Every ticket goes to a small fine-tuned model first. Only the ones it isn&apos;t sure about are sent to an
            LLM. The question is how much LLM work that saves, and what it costs in accuracy. All numbers below come
            from {r.data ? fmt(r.data.gold) : "the"} held-out tickets that were never used for training or for choosing
            the threshold.
          </p>
        </div>

        {at && llmOnly && int8 && (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="Handled without the LLM" value={pct(1 - at.escalated)} note={`threshold ${r.threshold.toFixed(2)}`} />
            <Tile
              label="Category accuracy"
              value={pct(at.category_accuracy, 1)}
              note={`LLM on everything: ${pct(llmOnly.category.accuracy, 1)}`}
            />
            <Tile
              label="Priority accuracy"
              value={pct(at.priority_accuracy, 1)}
              note={`LLM on everything: ${pct(llmOnly.priority.accuracy, 1)}`}
            />
            <Tile label="Model latency, p50" value={ms(int8.p50_ms)} note={`p95 ${ms(int8.p95_ms)} · 1 CPU thread`} />
          </div>
        )}

        {curve && llmOnly && (
          <Section
            id="cascade"
            title="Accuracy vs. LLM share"
            lead={`Each point is one confidence threshold. Moving right sends more tickets to ${FALLBACK_LLM}. The threshold was picked on the validation split as the lowest escalation rate that keeps 92% agreement with the teacher, then frozen.`}
          >
            <div className="grid gap-8 md:grid-cols-2">
              <CascadeChart
                title="Category"
                points={curve}
                metric="category_accuracy"
                llmOnly={llmOnly.category.accuracy}
                threshold={r.threshold}
              />
              <CascadeChart
                title="Priority"
                points={curve}
                metric="priority_accuracy"
                llmOnly={llmOnly.priority.accuracy}
                threshold={r.threshold}
              />
            </div>
            <details className="mt-6">
              <summary className="cursor-pointer text-2xs text-ink-3 hover:text-ink">Show as a table</summary>
              <div className="mt-3">
                <Table
                  head={["Threshold", "Escalated", "Category acc.", "Category F1", "Priority acc.", "Priority F1"]}
                  rows={curve
                    .filter((_, i) => i % 5 === 0)
                    .map((p) => [
                      p.threshold.toFixed(2),
                      pct(p.escalated, 1),
                      pct(p.category_accuracy, 1),
                      p.category_macro_f1.toFixed(3),
                      pct(p.priority_accuracy, 1),
                      p.priority_macro_f1.toFixed(3),
                    ])}
                />
              </div>
            </details>
          </Section>
        )}

        {r.baseline && r.students?.full && (
          <Section
            id="models"
            title="Models on the gold set"
            lead="The student learns from the teacher's labels, so the teacher's own score is roughly its ceiling. Gold labels come from a separate, stronger LLM, independent of both Gemini models (not from a person)."
          >
            <Table
              head={["Model", "Category acc.", "Category F1", "Priority acc.", "Priority F1", "Trainable params"]}
              highlight={1}
              rows={[
                [
                  "TF-IDF + logistic regression",
                  pct(r.baseline.student.category.gold.accuracy, 1),
                  r.baseline.student.category.gold.macro_f1.toFixed(3),
                  pct(r.baseline.student.priority.gold.accuracy, 1),
                  r.baseline.student.priority.gold.macro_f1.toFixed(3),
                  "–",
                ],
                ...(["full", "lora"] as const)
                  .map((k) => r.students?.[k])
                  .filter((s) => s?.student_only)
                  .map((s) => [
                    `MiniLM-L6, ${s!.lora ? "LoRA r=8" : "full fine-tune"}`,
                    pct(s!.student_only.category.accuracy, 1),
                    s!.student_only.category.macro_f1.toFixed(3),
                    pct(s!.student_only.priority.accuracy, 1),
                    s!.student_only.priority.macro_f1.toFixed(3),
                    fmt(s!.trainable_params),
                  ]),
                ...Object.entries(r.cascade?.llm_only ?? {}).map(([name, s]) => [
                  `${name}${name === FALLBACK_LLM ? " (teacher)" : ""}`,
                  pct(s.category.accuracy, 1),
                  s.category.macro_f1.toFixed(3),
                  pct(s.priority.accuracy, 1),
                  s.priority.macro_f1.toFixed(3),
                  "–",
                ]),
              ]}
            />
          </Section>
        )}

        {r.calibration && (
          <Section
            id="calibration"
            title="Calibration"
            lead="The routing rule trusts the model's confidence, so confidence has to mean something. One temperature per head, fitted on validation; ECE is measured on gold (lower is better)."
          >
            <Table
              head={["Head", "Temperature", "ECE before", "ECE after"]}
              rows={Object.entries(r.calibration).map(([t, c]) => [
                t,
                c.temperature.toFixed(2),
                c.gold_ece_before.toFixed(3),
                c.gold_ece_after.toFixed(3),
              ])}
            />
          </Section>
        )}

        {r.export && (
          <Section
            id="serving"
            title="Serving"
            lead="Exported to ONNX and quantized to int8 with dynamic quantization. Agreement is the share of gold tickets where the served model picks the same label as the PyTorch model."
          >
            <Table
              head={["Runtime", "Size", "Same label as PyTorch", "p50", "p95"]}
              rows={Object.entries(r.export.latency).map(([name, l]) => [
                name.replace("_", " "),
                r.export!.size_mb[name] ? `${r.export!.size_mb[name]} MB` : "–",
                r.export!.agreement_with_torch[name]
                  ? pct(Math.min(...Object.values(r.export!.agreement_with_torch[name])), 1)
                  : "reference",
                ms(l.p50_ms),
                ms(l.p95_ms),
              ])}
            />
          </Section>
        )}

        {r.retrieval && (
          <Section
            id="retrieval"
            title="Reply drafting: does reranking help?"
            lead={
              <>
                For {r.retrieval.n} held-out tickets with a known brand reply, the top retrieved past reply is compared
                to the real one (cosine similarity, bge-small). A proxy, not a human rating, but identical for every
                method. The cross-encoder was 33× slower and no better, so it&apos;s off; a small boost for replies from
                the same brand did more.
              </>
            }
          >
            <Table
              head={["Method", "Similarity to real reply", "Same brand @1", "Time / query"]}
              highlight={2}
              rows={RETRIEVAL_METHODS.filter(([k]) => r.retrieval?.[k]).map(([k, label]) => [
                label,
                r.retrieval![k].reply_similarity_mean.toFixed(3),
                pct(r.retrieval![k].same_brand_at_1, 1),
                ms(r.retrieval![k].ms_per_query),
              ])}
            />
          </Section>
        )}

        {r.loadtest && (
          <Section
            id="load"
            title="Load test"
            lead={
              <>
                Open-loop load (requests fired on a fixed schedule) against the classify endpoint with LLM escalation
                off, on a {r.loadtest.machine}. Capacity tops out near 90 requests a second; past that, requests queue
                and latency climbs into seconds, which is what the BullMQ queue in front of the API absorbs. Dynamic
                micro-batching was tried and made it worse here (batches averaged 1.3 tickets and only one ran at a
                time), so it ships switched off.
              </>
            }
          >
            <Table
              head={["Server", "Target", "Achieved req/s", "Failed", "p50", "p95", "p99"]}
              rows={Object.entries(r.loadtest.runs).flatMap(([variant, runs]) =>
                runs.map((s) => [
                  `${variant === "unbatched" ? "One request per inference (deployed)" : "Micro-batching"} · ${s.name}`,
                  s.name === "steady" ? "20/s" : s.name === "busy" ? "50/s" : s.name === "outage spike" ? "100/s" : "200/s",
                  s.rps.toFixed(0),
                  fmt(s.failed),
                  ms(s.p50_ms),
                  ms(s.p95_ms),
                  ms(s.p99_ms),
                ]),
              )}
            />
          </Section>
        )}

        {r.data && (
          <Section id="data" title="Data">
            <ul className="max-w-[68ch] list-disc space-y-1.5 pl-5 text-ink-2">
              <li>
                {fmt(r.data.tickets)} customer opening tweets that got a brand reply, from {r.data.brands} support accounts
                in the public Customer Support on Twitter dataset (2017). Capped at 1,500 per brand.
              </li>
              <li>Phone numbers, emails, links and long account numbers masked before anything else touched the text.</li>
              <li>
                {fmt(r.data.train + r.data.val)} tickets labelled by {r.data.teacher}; {fmt(r.data.gold)} held out and
                labelled independently for evaluation (non-English tickets skipped).
              </li>
              <li>The teacher agrees with the gold labels about 4 times in 5, so every number here inherits that noise.</li>
            </ul>
          </Section>
        )}
      </main>
    </div>
  );
}
