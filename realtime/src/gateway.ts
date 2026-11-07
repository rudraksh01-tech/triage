import { createServer } from "node:http";
import type { Queue } from "bullmq";
import type { Redis } from "ioredis";
import { WebSocket, WebSocketServer } from "ws";
import { config } from "./config.js";
import type { Replayer } from "./replay.js";
import type { QueuedTicket, QueueStats, ServerEvent, TriagedTicket } from "./types.js";
import { DONE_KEY, EVENTS_CHANNEL, RECENT_KEY } from "./worker.js";

export function startGateway(opts: {
  redis: Redis;
  subscriber: Redis;
  queue: Queue<QueuedTicket>;
  replayer: Replayer;
}) {
  const { redis, subscriber, queue, replayer } = opts;

  async function stats(): Promise<QueueStats> {
    const [counts, done] = await Promise.all([
      queue.getJobCounts("waiting", "active", "failed"),
      redis.zcount(DONE_KEY, Date.now() - 60_000, "+inf"),
    ]);
    return {
      waiting: counts.waiting ?? 0,
      active: counts.active ?? 0,
      failed: counts.failed ?? 0,
      doneLastMinute: done,
      ratePerSec: config.ratePerSec,
      burstReadyInMs: replayer.burstReadyInMs(),
    };
  }

  const cors = (origin: string | undefined) =>
    origin && config.allowedOrigins.includes(origin) ? origin : config.allowedOrigins[0];

  const server = createServer(async (req, res) => {
    res.setHeader("access-control-allow-origin", cors(req.headers.origin));
    res.setHeader("access-control-allow-methods", "GET, POST");
    if (req.method === "OPTIONS") return res.writeHead(204).end();

    if (req.method === "GET" && req.url === "/health") {
      return res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(await stats()));
    }
    if (req.method === "POST" && req.url === "/burst") {
      const ok = await replayer.burst();
      return res
        .writeHead(ok ? 202 : 429, { "content-type": "application/json" })
        .end(JSON.stringify({ ok, retryInMs: replayer.burstReadyInMs() }));
    }
    res.writeHead(404).end();
  });

  const wss = new WebSocketServer({ server, path: "/ws" });
  const send = (ws: WebSocket, ev: ServerEvent) => {
    // a slow client shouldn't make the server buffer forever
    if (ws.readyState === WebSocket.OPEN && ws.bufferedAmount < 1 << 20) ws.send(JSON.stringify(ev));
  };
  const broadcast = (ev: ServerEvent) => wss.clients.forEach((ws) => send(ws, ev));

  wss.on("connection", async (ws, req) => {
    const origin = req.headers.origin;
    if (origin && !config.allowedOrigins.includes(origin)) return ws.close(1008, "origin not allowed");
    const recent = await redis.lrange(RECENT_KEY, 0, config.recentLimit - 1);
    send(ws, {
      type: "snapshot",
      tickets: recent.map((r) => JSON.parse(r) as TriagedTicket),
      queue: await stats(),
    });
  });

  void subscriber.subscribe(EVENTS_CHANNEL);
  subscriber.on("message", (_channel, payload: string) => {
    broadcast({ type: "ticket", ticket: JSON.parse(payload) as TriagedTicket });
  });

  const statsTimer = setInterval(async () => {
    if (wss.clients.size) broadcast({ type: "queue", queue: await stats() });
  }, 1000);

  server.listen(config.port, () => console.log(`gateway on :${config.port}`));
  return () => {
    clearInterval(statsTimer);
    wss.close();
    server.close();
  };
}
