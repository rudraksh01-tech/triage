import { fileURLToPath } from "node:url";
import { Queue } from "bullmq";
import { Redis } from "ioredis";
import { config } from "./config.js";
import { startGateway } from "./gateway.js";
import { Replayer } from "./replay.js";
import type { QueuedTicket } from "./types.js";
import { startWorker } from "./worker.js";

const connection = { url: config.redisUrl, maxRetriesPerRequest: null };
const redis = new Redis(config.redisUrl);
const subscriber = new Redis(config.redisUrl); // a subscribed connection can't run other commands

const queue = new Queue<QueuedTicket>(config.queue, { connection });
const replayer = new Replayer(queue, fileURLToPath(new URL("../data/stream.jsonl", import.meta.url)));
const worker = startWorker(redis);
const stopGateway = startGateway({ redis, subscriber, queue, replayer });

worker.on("failed", (job, err) => console.warn(`job ${job?.id} failed: ${err.message}`));
replayer.start();

async function shutdown() {
  replayer.stop();
  stopGateway();
  await worker.close();
  await queue.close();
  redis.disconnect();
  subscriber.disconnect();
  process.exit(0);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
