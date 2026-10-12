"use client";

// Price history for one part: the price as a step line (a price holds until the
// next check), the 30-day average and target price as labeled dashed reference
// lines, and deals as green markers. Hover anywhere for a crosshair readout.

import { useLayoutEffect, useRef, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";

export interface ChartPoint {
  t: number; // epoch ms
  price: number;
  onSale: boolean;
  deal: boolean;
}

const usd = (v: number) => `$${v.toFixed(2)}`;
const usdShort = (v: number) => `$${Math.round(v)}`;
const day = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const full = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const DAY_MS = 24 * 60 * 60 * 1000;
const HEIGHT = 320;

/** Up to `maxTicks` ticks at midnight boundaries, whatever the range (7, 30, or 90 days). */
export function dateTicks(start: number, end: number, maxTicks = 7): number[] {
  const spanDays = Math.max(1, (end - start) / DAY_MS);
  const step = Math.max(1, Math.ceil(spanDays / maxTicks)) * DAY_MS;
  const first = new Date(start);
  first.setHours(0, 0, 0, 0);
  const ticks: number[] = [];
  for (let t = first.getTime() + DAY_MS; t <= end; t += step) ticks.push(t);
  return ticks;
}

function ChartTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as ChartPoint;
  return (
    <div className="tooltip">
      <strong>{usd(p.price)}</strong>
      <div className="muted">{full.format(p.t)}</div>
      {p.deal && <div style={{ color: "var(--good-ink)" }}>↓ Deal detected</div>}
      {!p.deal && p.onSale && <div className="subtle">On sale</div>}
    </div>
  );
}

interface DotProps {
  cx?: number;
  cy?: number;
  payload?: ChartPoint;
}

function DealDot({ cx, cy, payload }: DotProps) {
  if (!payload?.deal || cx == null || cy == null) return null;
  // 2px surface ring keeps the marker readable where it overlaps the line.
  return (
    <circle cx={cx} cy={cy} r={5} fill="var(--good)" stroke="var(--surface)" strokeWidth={2} />
  );
}

/** Container width: measured once on mount, then kept in sync with a ResizeObserver. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export function PriceChart({
  points,
  average,
  target,
}: {
  points: ChartPoint[];
  average: number | null;
  target: number | null;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();

  if (points.length < 2) {
    return <div className="empty">Not enough price history yet for a chart.</div>;
  }

  const values = points.map((p) => p.price);
  if (average != null) values.push(average);
  if (target != null) values.push(target);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = Math.max((hi - lo) * 0.12, hi * 0.01);
  // Roughly one date label per 90px so labels never collide on narrow screens.
  const maxTicks = Math.max(2, Math.min(7, Math.floor((width - 180) / 90)));
  const ticks = dateTicks(points[0].t, points[points.length - 1].t, maxTicks);
  // Nudge the two right-edge labels apart when the lines are close together.
  const labelsCollide =
    average != null && target != null && Math.abs(average - target) < (hi - lo + 2 * pad) * 0.08;
  const nudge = labelsCollide ? (target! < average! ? 9 : -9) : 0;

  return (
    <div ref={ref} style={{ width: "100%", height: HEIGHT }}>
      {width > 0 && (
        <LineChart
          width={width}
          height={HEIGHT}
          data={points}
          margin={{ top: 12, right: 112, bottom: 4, left: 8 }}
        >
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            ticks={ticks}
            tickFormatter={(t: number) => day.format(t)}
            tick={{ fill: "var(--muted)", fontSize: 12 }}
            stroke="var(--axis)"
          />
          <YAxis
            domain={[Math.floor(lo - pad), Math.ceil(hi + pad)]}
            tickFormatter={usdShort}
            tick={{ fill: "var(--muted)", fontSize: 12 }}
            stroke="var(--axis)"
            width={56}
            axisLine={false}
            tickLine={false}
          />
          {average != null && (
            <ReferenceLine
              y={average}
              stroke="var(--muted)"
              strokeDasharray="4 4"
              label={{
                value: `Avg ${usd(average)}`,
                position: "right",
                dy: -nudge,
                fill: "var(--ink-2)",
                fontSize: 12,
              }}
            />
          )}
          {target != null && (
            <ReferenceLine
              y={target}
              stroke="var(--good)"
              strokeDasharray="4 4"
              label={{
                value: `Target ${usd(target)}`,
                position: "right",
                dy: nudge,
                fill: "var(--good-ink)",
                fontSize: 12,
              }}
            />
          )}
          <Tooltip
            content={<ChartTooltip />}
            cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
            isAnimationActive={false}
          />
          <Line
            type="stepAfter"
            dataKey="price"
            stroke="var(--accent)"
            strokeWidth={2}
            dot={<DealDot />}
            activeDot={{ r: 5, fill: "var(--accent)", stroke: "var(--surface)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      )}
    </div>
  );
}
