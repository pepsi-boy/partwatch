import Link from "next/link";

import { PriceBadge } from "@/components/Badge";
import { DemoBanner } from "@/components/DemoBanner";
import { StatTile } from "@/components/StatTile";
import { api } from "@/lib/api";
import { ago, money, vsAverage } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [parts, status] = await Promise.all([api.parts(), api.status()]);
  const dealsNow = parts.filter((p) => p.price_status === "deal").length;
  const rate = status.success_rate_7d;

  return (
    <>
      <DemoBanner />
      <h1>Tracked parts</h1>
      <p className="subtle">
        Prices are checked every {status.check_interval_hours} hours. A deal is a price well below
        its 30-day average, or at or below your target.
      </p>

      <div className="tiles">
        <StatTile value={status.parts_tracked} label="parts tracked" />
        <StatTile value={dealsNow} label="deals right now" />
        <StatTile value={ago(status.last_successful_run_at)} label="last successful check" />
        <StatTile
          value={rate == null ? "—" : `${(rate * 100).toFixed(1)}%`}
          label="run success rate, 7 days"
        />
      </div>

      <h2>All parts</h2>
      <div className="card">
        {parts.length === 0 ? (
          <div className="empty">
            No parts tracked yet. Add one with POST /parts in the API docs.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Part</th>
                <th>Type</th>
                <th className="num">Price</th>
                <th className="num">30-day avg</th>
                <th className="num">vs avg</th>
                <th>Status</th>
                <th>Checked</th>
              </tr>
            </thead>
            <tbody>
              {parts.map((p) => (
                <tr key={p.id}>
                  <td className="wrap">
                    <Link href={`/parts/${p.id}`} className="part-link">
                      {p.name}
                    </Link>
                    {!p.active && <span className="muted"> (paused)</span>}
                    <div className="sku">
                      SKU {p.sku}
                      {p.target_price != null && ` · target ${money(p.target_price)}`}
                    </div>
                  </td>
                  <td>{p.category.toUpperCase()}</td>
                  <td className="num">{money(p.current_price)}</td>
                  <td className="num">{money(p.avg_30d)}</td>
                  <td className="num">{vsAverage(p.percent_vs_avg)}</td>
                  <td>
                    <PriceBadge status={p.price_status} />
                  </td>
                  <td className="muted">{ago(p.last_checked_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
