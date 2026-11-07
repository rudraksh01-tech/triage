import { Worker } from "bullmq";
import type { Redis } from "ioredis";
import { config } from "./config.js";
import type { Classified, QueuedTicket, TriagedTicket } from "./types.js";

export const RECENT_KEY = "triage:recent";
export const EVENTS_CHANNEL = "triage:events";
export const DONE_KEY = "triage:done"; // sorted set of completion timestamps

async function classify(t: QueuedTicket): Promise<Classified> {
  const res = await fetch(`${config.apiUrl}/v1/classify`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text: t.text, brand: t.brand }),
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) throw new Error(`classify ${res.status}`);
  return (await res.json()) as Classified;
}

export function startWorker(redis: Redis) {
  return new Worker<QueuedTicket>(
    config.queue,
    async (job) => {
      const c = await classify(job.data);
      const ticket: TriagedTicket = {
        ...job.data,
        category: c.category,
        priority: c.priority,
        confidence: c.confidence,
        route: c.route,
        modelMs: c.model_ms,
        llmMs: c.llm_ms,
        student: c.student,
        probs: c.probs,
        doneAt: Date.now(),
      };
      const payload = JSON.stringify(ticket);
      await redis
        .multi()
        .lpush(RECENT_KEY, payload)
        .ltrim(RECENT_KEY, 0, config.recentLimit - 1)
        .zadd(DONE_KEY, ticket.doneAt, `${ticket.id}:${ticket.doneAt}`)
        .zremrangebyscore(DONE_KEY, 0, Date.now() - 60_000)
        .publish(EVENTS_CHANNEL, payload)
        .exec();
    },
    { connection: { url: config.redisUrl, maxRetriesPerRequest: null }, concurrency: config.concurrency },
  );
}
