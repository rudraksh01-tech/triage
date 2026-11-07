"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { QueueStats, ServerEvent, Ticket } from "./types";

export type FeedStatus = "connecting" | "live" | "offline";

const MAX_TICKETS = 200;
const HISTORY = 90; // seconds of queue depth kept for the sparkline

export interface Feed {
  status: FeedStatus;
  tickets: Ticket[];
  queue: QueueStats | null;
  depthHistory: number[];
}

/**
 * Subscribes to the realtime gateway. Falls back to the bundled sample when
 * no gateway is configured or it can't be reached, so the page never renders empty.
 */
export function useFeed(url: string | undefined, sample: Ticket[]): Feed {
  const [status, setStatus] = useState<FeedStatus>(url ? "connecting" : "offline");
  const [tickets, setTickets] = useState<Ticket[]>(sample);
  const [queue, setQueue] = useState<QueueStats | null>(null);
  const [depthHistory, setDepth] = useState<number[]>([]);
  const gotData = useRef(false);

  useEffect(() => {
    if (!url) return;
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout>;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(url);
      ws.onopen = () => {
        retry = 0;
        setStatus("live");
      };
      ws.onmessage = (msg) => {
        const ev = JSON.parse(msg.data) as ServerEvent;
        if (ev.type === "snapshot") {
          gotData.current = true;
          setTickets(ev.tickets);
          setQueue(ev.queue);
        } else if (ev.type === "ticket") {
          setTickets((prev) => [ev.ticket, ...prev].slice(0, MAX_TICKETS));
        } else {
          setQueue(ev.queue);
          setDepth((h) => [...h, ev.queue.waiting + ev.queue.active].slice(-HISTORY));
        }
      };
      ws.onclose = () => {
        if (closed) return;
        setStatus(gotData.current ? "connecting" : "offline");
        // 1s, 2s, 4s ... capped at 30s
        timer = setTimeout(connect, Math.min(30_000, 1000 * 2 ** retry++));
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [url]);

  return { status, tickets, queue, depthHistory };
}

// One shared clock for every relative timestamp on the page.
let clock = 0;
const clockListeners = new Set<() => void>();
let clockTimer: ReturnType<typeof setInterval> | undefined;

function subscribeClock(onChange: () => void) {
  clockListeners.add(onChange);
  if (!clockTimer) {
    clockTimer = setInterval(() => {
      clock = Date.now();
      clockListeners.forEach((l) => l());
    }, 5000);
  }
  return () => {
    clockListeners.delete(onChange);
    if (!clockListeners.size) {
      clearInterval(clockTimer);
      clockTimer = undefined;
    }
  };
}

function readClock() {
  if (!clock) clock = Date.now();
  return clock;
}

/**
 * Current time, refreshed every 5s. Null during prerender, where "now" isn't
 * knowable; callers fall back to the newest ticket's timestamp.
 */
export function useNow(): number | null {
  return useSyncExternalStore(subscribeClock, readClock, () => null);
}
