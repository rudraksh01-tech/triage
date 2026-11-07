const env = (k: string, d: string) => process.env[k] ?? d;
const num = (k: string, d: number) => Number(process.env[k] ?? d);

export const config = {
  redisUrl: env("REDIS_URL", "redis://127.0.0.1:6379"),
  apiUrl: env("TRIAGE_API_URL", "http://127.0.0.1:8000"),
  port: num("PORT", 8080),
  queue: "tickets",
  // calm baseline: one ticket every ~2s keeps LLM escalations under the free tier
  ratePerSec: num("REPLAY_RATE", 0.5),
  burstSize: num("BURST_SIZE", 300),
  burstCooldownMs: num("BURST_COOLDOWN_MS", 60_000),
  concurrency: num("WORKER_CONCURRENCY", 8),
  recentLimit: 200,
  allowedOrigins: env("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
};
