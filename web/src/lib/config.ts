import results from "@/data/results.json";

export const API_URL = process.env.NEXT_PUBLIC_API_URL;
export const REALTIME_URL = process.env.NEXT_PUBLIC_REALTIME_URL; // http(s) base of the gateway

export const wsUrl = REALTIME_URL ? REALTIME_URL.replace(/^http/, "ws") + "/ws" : undefined;

export const THRESHOLD: number = results.threshold;
