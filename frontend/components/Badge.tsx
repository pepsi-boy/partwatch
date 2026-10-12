import type { JobRun, PriceStatus } from "@/lib/api";

type Tone = "good" | "serious" | "warning" | "neutral";

// Status colors never carry meaning alone: every badge also has an icon and a label.
const PRICE: Record<PriceStatus, { tone: Tone; icon: string; label: string }> = {
  deal: { tone: "good", icon: "↓", label: "Deal" },
  normal: { tone: "neutral", icon: "–", label: "Normal" },
  above_average: { tone: "serious", icon: "↑", label: "Above average" },
  unknown: { tone: "neutral", icon: "?", label: "No data yet" },
};

const RUN: Record<JobRun["status"], { tone: Tone; icon: string; label: string }> = {
  success: { tone: "good", icon: "✓", label: "Success" },
  partial: { tone: "warning", icon: "!", label: "Partial" },
  failed: { tone: "serious", icon: "✕", label: "Failed" },
  stale: { tone: "serious", icon: "⏱", label: "Stale" },
  running: { tone: "neutral", icon: "…", label: "Running" },
};

function Pill({ tone, icon, label }: { tone: Tone; icon: string; label: string }) {
  return (
    <span className={`badge badge-${tone}`}>
      <span aria-hidden="true">{icon}</span>
      {label}
    </span>
  );
}

export function PriceBadge({ status }: { status: PriceStatus }) {
  return <Pill {...PRICE[status]} />;
}

export function RunBadge({ status }: { status: JobRun["status"] }) {
  return <Pill {...RUN[status]} />;
}
