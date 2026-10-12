import Link from "next/link";
import { notFound } from "next/navigation";

import { PriceBadge } from "@/components/Badge";
import { DemoBanner } from "@/components/DemoBanner";
import { PriceChart } from "@/components/PriceChart";
import { ApiError, api } from "@/lib/api";
import { toChartPoints } from "@/lib/chart";
import { ago, money, vsAverage, when } from "@/lib/format";

export const dynamic = "force-dynamic";

const RANGES = [7, 30, 90] as const;

export default async function PartPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ days?: string }>;
}) {
  const { id: rawId } = await params;
  const id = Number(rawId);
  if (!Number.isInteger(id) || id <= 0) notFound();
  const requested = Number((await searchParams).days);
  const days = RANGES.find((r) => r === requested) ?? 30;

  const part = await api.part(id).catch((e) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  const [prices, deals] = await Promise.all([
    api.prices(id, days),
    api.deals({ partId: id, limit: 100 }),
  ]);
  const points = toChartPoints(prices, deals);

  return (
    <>
      <DemoBanner />
      <p>
        <Link href="/">← All parts</Link>
      </p>

      <div className="detail-head">
        <div>
          <h1>{part.name}</h1>
          <div className="facts">
            <span>{part.category.toUpperCase()}</span>
            <span>SKU {part.sku}</span>
            <span>{part.active ? `Checked ${ago(part.last_checked_at)}` : "Tracking paused"}</span>
            {part.in_stock === false && <span>Out of stock online</span>}
          </div>
        </div>
        <div className="price-side">
          <div className="hero-price">{money(part.current_price)}</div>
          <div className="facts">
            <PriceBadge status={part.price_status} />
            <span>{vsAverage(part.percent_vs_avg)} the 30-day average</span>
          </div>
        </div>
      </div>

      <div className="tiles">
        <div className="tile">
          <span className="value">{money(part.avg_30d)}</span>
          <span className="label">30-day average</span>
        </div>
        <div className="tile">
          <span className="value">{money(part.regular_price)}</span>
          <span className="label">Best Buy regular price</span>
        </div>
        <div className="tile">
          <span className="value">{money(part.target_price)}</span>
          <span className="label">your target price</span>
        </div>
        <div className="tile">
          <span className="value">{deals.length}</span>
          <span className="label">deals detected</span>
        </div>
      </div>

      <div className="chart-toolbar">
        <h2 style={{ margin: 0 }}>Price history</h2>
        <nav className="range" aria-label="Time range">
          {RANGES.map((r) => (
            <Link key={r} href={`/parts/${id}?days=${r}`} aria-current={r === days}>
              {r} days
            </Link>
          ))}
        </nav>
      </div>
      <div className="chart-keys" style={{ marginBottom: 8 }}>
        <span className="key">
          <span className="key-line" /> Price
        </span>
        <span className="key">
          <span className="key-dash" /> 30-day average
        </span>
        {part.target_price != null && (
          <span className="key">
            <span className="key-target" /> Target
          </span>
        )}
        <span className="key">
          <span className="key-dot" /> Deal
        </span>
      </div>
      <div className="chart-card">
        <PriceChart points={points} average={part.avg_30d} target={part.target_price} />
      </div>

      <details className="table-view">
        <summary>Show as a table ({prices.length} checks)</summary>
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Checked</th>
                <th className="num">Price</th>
                <th className="num">Regular</th>
                <th>On sale</th>
                <th>In stock</th>
              </tr>
            </thead>
            <tbody>
              {[...prices].reverse().map((p) => (
                <tr key={p.fetched_at}>
                  <td>{when(p.fetched_at)}</td>
                  <td className="num">{money(p.price)}</td>
                  <td className="num">{money(p.regular_price)}</td>
                  <td>{p.on_sale ? "Yes" : "No"}</td>
                  <td>{p.in_stock ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <h2>Deals for this part</h2>
      <div className="card">
        {deals.length === 0 ? (
          <div className="empty">No deals detected yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Detected</th>
                <th className="num">Price</th>
                <th className="num">30-day avg</th>
                <th className="num">Below avg</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {deals.map((d) => (
                <tr key={d.id}>
                  <td>{when(d.detected_at)}</td>
                  <td className="num">{money(d.price)}</td>
                  <td className="num">{money(d.baseline_avg)}</td>
                  <td className="num">{d.percent_below.toFixed(1)}%</td>
                  <td>{d.reason === "below_target" ? "At or below target" : "Below average"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
