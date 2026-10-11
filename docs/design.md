# PartWatch design notes

Decisions, the alternatives considered, and what each one costs.

## 1. Fan-out: one task per part

`check_all_prices` doesn't fetch prices itself. It queues one `check_part_price` task per active part.

- **Why:** failure isolation (one bad SKU fails one task, not the run), per-part retries with their own backoff, and horizontal scaling (any number of workers can pull from the queue).
- **Cost:** more queue messages, and a run's completion has to be tracked across tasks (see section 6).

## 2. Idempotency through the database

Running a check twice must not create duplicate data. Three guards, all enforced by Postgres rather than application checks, so they hold under races between workers:

| Guard | Mechanism |
|---|---|
| One snapshot per part per check window | `UNIQUE (part_id, window_start)` + `INSERT ... ON CONFLICT DO NOTHING` |
| One deal per snapshot | `UNIQUE (deals.snapshot_id)` |
| One alert per deal | `send_deal_alert` exits if `alerted_at` is set |

**Check windows** are aligned to the Unix epoch (with a 3h interval: 00:00, 03:00, ... UTC). The window is fixed once, when the fan-out starts, and passed to every part task, so a task that runs after a window boundary still lands in its run's window.

This is what makes `task_acks_late` safe. A message is acknowledged only after its task finishes, so if a worker dies mid-task, the message is redelivered and the re-run does no harm.

## 3. Deal rules

Two rules, either one is enough:
- **Below average:** `price <= avg_30d × (1 − threshold)`, with at least `MIN_SNAPSHOTS_FOR_DEAL` prior snapshots.
- **Below target:** `price <= target_price` (optional, per part).

The threshold comparison uses exact decimals, not the rounded percentage. A test caught 9.998% being rounded to 10.00% and counted as a deal.

**Re-alerting.** "Don't re-alert unless the price drops further", taken literally, would block every future sale at the same price forever. Instead, a deal stays *active* until the price **recovers**: back to the average it was compared against (below-average deals) or back above the target (target deals). While a deal is active, only a lower price alerts again. Once it re-arms, the next sale alerts normally.

The rules are pure functions in `services/deals.py`. The database side (`deal_finder.py`) only loads history and saves results.

## 4. Provider interface and demo mode

Tasks depend on a `PriceProvider` interface, not on the Best Buy client. `get_provider()` returns the real client when `BESTBUY_API_KEY` is set and `MockBestBuyProvider` otherwise.

The mock is built to exercise real code paths:
- It produces Products API JSON and runs it through the same `parse_product` as production.
- Prices are deterministic per (SKU, 3-hour window), so retries and tests are reproducible.
- Prices drift ±3%, and roughly 1 day in 7 a part goes 12–22% off, so deals actually happen.

**Guarding real data:** the mock history backfill and placeholder-SKU seeding both refuse to run once a real key is set, so fake prices never mix into a real price history.

## 5. Reliability against the Best Buy API

- **Limits** (Best Buy developer terms): 5 calls/sec and 50,000/day per key. The terms say going over returns **403**, while Best Buy's own SDK mentions 429. A 403 is treated as retryable only if the body mentions "quota". Otherwise it's a bad key and fails fast. This heuristic still needs checking against a real key.
- **Throttling:** Celery `rate_limit="4/s"` on `check_part_price`. Celery enforces this **per worker**, so with N workers it should be set to about 4/N (`BESTBUY_RATE_LIMIT`). A shared Redis token bucket would enforce one global limit, but it isn't worth the complexity at this scale.
- **Retries:** retryable errors back off 5s, 10s, 20s, 40s, 80s (capped at 5 min) with up to 25% jitter, then fail. Jitter keeps many failed tasks from retrying in lockstep.
- **Daily budget:** 8 parts × 8 checks/day = 64 calls/day, far below 50,000.
- **Secrets:** httpx exception messages include the request URL, which contains the API key, so the client raises its own messages instead.

## 6. Job run tracking

`check_all_prices` inserts a `job_runs` row with `parts_total`. Each part task, on final success or failure (not on intermediate retries), atomically increments `parts_checked` or `failures`. The task that brings the count to `parts_total` closes the run as `success`, `partial`, or `failed`. The `finished_at IS NULL` condition makes sure only one task closes it.

- **Stale runs:** if tasks are lost (e.g. the free Key Value instance restarts and drops its in-memory queue), a run never completes. `/status` reports runs still "running" after 1 hour as `stale`, so the problem is visible instead of silently looking healthy.
- **Known imprecision:** if a task is redelivered after it already counted itself (crash between commit and ack), the counters can over-count by one. Snapshots stay correct because they're deduplicated. Only the bookkeeping is off, which is acceptable for a status page.

## 7. Free-tier deployment

Render's free tier has free web services, Postgres, and Key Value, but **no background workers, no cron jobs, and blocks outbound SMTP**. Free web services sleep after 15 idle minutes.

| Need | Free-tier workaround | Tradeoff |
|---|---|---|
| Celery worker | Runs in the API container (`start.sh`: worker + uvicorn; if either dies, the container exits and Render restarts it) | API and worker share 512 MB and can't scale separately. Moving to a paid background worker is a config change, not a code change |
| Celery Beat | GitHub Actions cron calls `POST /run-checks` every 3h | Beat in a sleeping container wouldn't fire. GitHub cron can be delayed under load and is disabled after 60 days without repo activity |
| Waking the service | The cron's request wakes it, and tasks finish in seconds | Cold start adds ~1 minute; retries with long backoff could outlive the 15-minute idle window |
| Redis | Free Key Value, `noeviction` | In-memory only: a restart drops queued tasks (shows up as a stale run) |
| Postgres | Free Render Postgres | **Deleted after 30 days.** History resets monthly, and demo mode re-backfills automatically on start |
| Email | Alerts go to logs and the deals page | Email works locally or on a paid instance (set the SMTP vars) |

The one-container setup trades isolation for cost. On paid Render: separate background worker with Beat embedded (`celery worker --beat`), a paid Postgres, SMTP enabled, and the GitHub cron removed.

## 8. Testing strategy

- **Pure unit tests:** deal rules, check windows, backoff schedule, response parsing.
- **Integration tests against real Postgres:** the test database is migrated with Alembic (so migrations are tested too), and each test runs in a transaction that's rolled back.
- **Task tests:** Best Buy is replaced with `httpx.MockTransport`, and tasks run through Celery's `apply()` so retries happen for real (with backoff set to 0).
- **No real external calls in CI:** no API key, no SMTP credentials, and SMTP is faked in the alert tests.
