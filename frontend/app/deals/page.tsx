import Link from "next/link";

import { DemoBanner } from "@/components/DemoBanner";
import { api } from "@/lib/api";
import { money, when } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function DealsPage() {
  const deals = await api.deals({ limit: 100 });

  return (
    <>
      <DemoBanner />
      <h1>Deals</h1>
      <p className="subtle">
        Every price drop that met a deal rule, newest first. Each one triggers a single alert.
      </p>

      <div className="card" style={{ marginTop: 20 }}>
        {deals.length === 0 ? (
          <div className="empty">No deals yet. They show up here as soon as one is detected.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Detected</th>
                <th>Part</th>
                <th className="num">Price</th>
                <th className="num">30-day avg</th>
                <th className="num">Below avg</th>
                <th>Why</th>
                <th>Alert</th>
              </tr>
            </thead>
            <tbody>
              {deals.map((d) => (
                <tr key={d.id}>
                  <td>{when(d.detected_at)}</td>
                  <td className="wrap">
                    <Link href={`/parts/${d.part_id}`} className="part-link">
                      {d.part_name}
                    </Link>
                    <div className="sku">SKU {d.sku}</div>
                  </td>
                  <td className="num">{money(d.price)}</td>
                  <td className="num">{money(d.baseline_avg)}</td>
                  <td className="num">{d.percent_below.toFixed(1)}%</td>
                  <td>{d.reason === "below_target" ? "At or below target" : "Below average"}</td>
                  <td>{d.alerted_at ? `Sent ${when(d.alerted_at)}` : "Pending"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
