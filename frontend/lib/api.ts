// Typed client for the PartWatch FastAPI backend.
//
// Pages fetch on the server (React Server Components), so the browser never
// talks to the API directly: no CORS setup, and the API URL can stay private.

export type PriceStatus = "deal" | "normal" | "above_average" | "unknown";

export interface Part {
  id: number;
  sku: string;
  name: string;
  category: string;
  active: boolean;
  target_price: number | null;
  created_at: string;
  current_price: number | null;
  regular_price: number | null;
  in_stock: boolean | null;
  last_checked_at: string | null;
  avg_30d: number | null;
  percent_vs_avg: number | null; // positive = below average (cheaper than usual)
  price_status: PriceStatus;
}

export interface PricePoint {
  fetched_at: string;
  price: number;
  regular_price: number | null;
  on_sale: boolean;
  in_stock: boolean;
}

export interface Deal {
  id: number;
  part_id: number;
  part_name: string;
  sku: string;
  price: number;
  baseline_avg: number;
  percent_below: number;
  reason: "below_average" | "below_target";
  detected_at: string;
  alerted_at: string | null;
}

export interface JobRun {
  id: number;
  task_name: string;
  status: "running" | "success" | "partial" | "failed" | "stale";
  started_at: string;
  finished_at: string | null;
  parts_total: number;
  parts_checked: number;
  failures: number;
  last_error: string | null;
  duration_seconds: number | null;
}

export interface Status {
  demo_mode: boolean;
  alert_channel: "email" | "log";
  check_interval_hours: number;
  parts_tracked: number;
  snapshots_last_24h: number;
  deals_total: number;
  runs_last_7d: number;
  success_rate_7d: number | null;
  last_successful_run_at: string | null;
  recent_runs: JobRun[];
  recent_errors: string[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}

// Server-side base URL (e.g. http://api:8000 inside Docker Compose), falling back
// to the public URL.
const API_URL = (
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000"
).replace(/\/$/, "");

// Render's free tier sleeps idle services; the first request can take ~1 minute.
const TIMEOUT_MS = 90_000;

async function get<T>(path: string): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new ApiError("The PartWatch API is unreachable right now.");
  }
  if (!resp.ok) {
    throw new ApiError(`API returned ${resp.status} for ${path}`, resp.status);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  parts: () => get<Part[]>("/parts"),
  part: (id: number) => get<Part>(`/parts/${id}`),
  prices: (id: number, days: number) => get<PricePoint[]>(`/parts/${id}/prices?days=${days}`),
  deals: (opts: { limit?: number; partId?: number } = {}) => {
    const q = new URLSearchParams({ limit: String(opts.limit ?? 50) });
    if (opts.partId !== undefined) q.set("part_id", String(opts.partId));
    return get<Deal[]>(`/deals?${q}`);
  },
  status: () => get<Status>("/status"),
};

export const PUBLIC_API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);
