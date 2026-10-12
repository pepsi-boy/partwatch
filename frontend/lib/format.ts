const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export const money = (v: number | null | undefined) => (v == null ? "—" : usd.format(v));

// Fixed time zone so server-rendered HTML is deterministic.
const dateTime = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "America/Chicago",
  timeZoneName: "short",
});

export const when = (iso: string | null | undefined) =>
  iso ? dateTime.format(new Date(iso)) : "—";

export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const minutes = Math.round((now - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

/** "12.7% below" / "3.1% above" for a percent_vs_avg value (positive = cheaper). */
export function vsAverage(pct: number | null | undefined): string {
  if (pct == null) return "—";
  if (Math.abs(pct) < 0.05) return "at average";
  return `${Math.abs(pct).toFixed(1)}% ${pct > 0 ? "below" : "above"}`;
}
