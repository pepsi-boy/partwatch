import { RunBadge } from "@/components/Badge";
import { DemoBanner } from "@/components/DemoBanner";
import { StatTile } from "@/components/StatTile";
import { api } from "@/lib/api";
import { ago, when } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function StatusPage() {
  const s = await api.status();
  const rate = s.success_rate_7d;

  return (
    <>
      <DemoBanner />
      <h1>System status</h1>
      <p className="subtle">
        Each scheduled run checks every tracked part as its own background task. A run is
        &ldquo;partial&rdquo; if some parts failed after retries, and &ldquo;stale&rdquo; if it
        never finished.
      </p>

      <div className="tiles">
        <StatTile value={ago(s.last_successful_run_at)} label="last successful run" />
        <StatTile
          value={rate == null ? "—" : `${(rate * 100).toFixed(1)}%`}
          label="run success rate, 7 days"
        />
        <StatTile value={s.runs_last_7d} label="runs, 7 days" />
        <StatTile value={s.snapshots_last_24h} label="price checks, 24 hours" />
        <StatTile value={s.deals_total} label="deals detected" />
        <StatTile
          value={s.demo_mode ? "Demo" : "Live"}
          label={s.demo_mode ? "mock Best Buy data" : "real Best Buy data"}
        />
        <StatTile value={s.alert_channel === "email" ? "Email" : "Log"} label="alert channel" />
      </div>

      <h2>Recent runs</h2>
      <div className="card">
        {s.recent_runs.length === 0 ? (
          <div className="empty">No runs yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Started</th>
                <th>Status</th>
                <th className="num">Checked</th>
                <th className="num">Failed</th>
                <th className="num">Duration</th>
              </tr>
            </thead>
            <tbody>
              {s.recent_runs.map((r) => (
                <tr key={r.id}>
                  <td>{when(r.started_at)}</td>
                  <td>
                    <RunBadge status={r.status} />
                  </td>
                  <td className="num">
                    {r.parts_checked}/{r.parts_total}
                  </td>
                  <td className="num">{r.failures}</td>
                  <td className="num">
                    {r.duration_seconds == null ? "—" : `${r.duration_seconds.toFixed(1)}s`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>Recent errors</h2>
      <div className="card">
        {s.recent_errors.length === 0 ? (
          <div className="empty">No errors in recent runs.</div>
        ) : (
          <table>
            <tbody>
              {s.recent_errors.map((e, i) => (
                <tr key={i}>
                  <td className="wrap error-text">{e}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
