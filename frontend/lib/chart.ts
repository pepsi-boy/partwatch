import type { ChartPoint } from "@/components/PriceChart";
import type { Deal, PricePoint } from "@/lib/api";

// A deal is detected right after its snapshot is saved, so its detected_at is
// within moments of that snapshot's fetched_at.
const DEAL_MATCH_MS = 60 * 60 * 1000;

/** Turn API price points into chart points, flagging the snapshots that were deals. */
export function toChartPoints(prices: PricePoint[], deals: Deal[]): ChartPoint[] {
  const points = prices.map((p) => ({
    t: new Date(p.fetched_at).getTime(),
    price: p.price,
    onSale: p.on_sale,
    deal: false,
  }));
  for (const deal of deals) {
    const t = new Date(deal.detected_at).getTime();
    let best = -1;
    let bestGap = Infinity;
    points.forEach((p, i) => {
      const gap = Math.abs(p.t - t);
      if (gap < bestGap && p.price === deal.price) {
        best = i;
        bestGap = gap;
      }
    });
    if (best >= 0 && bestGap <= DEAL_MATCH_MS) points[best].deal = true;
  }
  return points;
}
