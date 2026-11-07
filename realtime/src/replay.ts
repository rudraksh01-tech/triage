import { readFileSync } from "node:fs";
import { Queue } from "bullmq";
import { config } from "./config.js";
import type { Incoming, QueuedTicket } from "./types.js";

const JOB_OPTS = {
  attempts: 3,
  backoff: { type: "exponential", delay: 500 },
  removeOnComplete: 1000,
  removeOnFail: 1000,
};

export class Replayer {
  private tickets: Incoming[];
  private cursor = 0;
  private timer: NodeJS.Timeout | null = null;
  private lastBurst = 0;

  constructor(private queue: Queue<QueuedTicket>, file: string) {
    this.tickets = readFileSync(file, "utf8")
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Incoming);
  }

  private next(): Incoming {
    const t = this.tickets[this.cursor % this.tickets.length];
    this.cursor++;
    // ids repeat once the file loops, so suffix the lap number
    const lap = Math.floor((this.cursor - 1) / this.tickets.length);
    return lap ? { ...t, id: `${t.id}-${lap}` } : t;
  }

  start(): void {
    const tick = async () => {
      const t = this.next();
      await this.queue.add("triage", { ...t, receivedAt: Date.now(), burst: false }, JOB_OPTS);
      // jitter so arrivals don't look like a metronome
      const mean = 1000 / config.ratePerSec;
      this.timer = setTimeout(tick, mean * (0.4 + Math.random() * 1.2));
    };
    void tick();
  }

  stop(): void {
    if (this.timer) clearTimeout(this.timer);
  }

  burstReadyInMs(): number {
    return Math.max(0, this.lastBurst + config.burstCooldownMs - Date.now());
  }

  /** Simulate an outage: a few hundred tickets land at once. */
  async burst(): Promise<boolean> {
    if (this.burstReadyInMs() > 0) return false;
    this.lastBurst = Date.now();
    const now = Date.now();
    await this.queue.addBulk(
      Array.from({ length: config.burstSize }, () => ({
        name: "triage",
        data: { ...this.next(), receivedAt: now, burst: true },
        opts: JOB_OPTS,
      })),
    );
    return true;
  }
}
