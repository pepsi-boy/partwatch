# Changelog

All notable changes to this project are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/), versioning follows [SemVer](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-11

First release. Runs in demo mode (mock Best Buy provider) until a Best Buy API key is configured.

### Added
- Next.js dashboard with Recharts: tracked parts with deal badges, per-part price history chart (7/30/90 days) with average and target lines and deal markers, deals feed, and system status page.
- Dashboard in Docker Compose, CI (lint, build, typecheck), and on Render's free tier.
- `DB_SCHEMA` setting so PartWatch can share a Postgres database in its own schema.
- Scheduled fan-out price checks: Celery Beat queues one task per tracked part.
- Price provider interface. Real Best Buy Products API client when `BESTBUY_API_KEY` is set, mock provider (demo mode) otherwise.
- Best Buy client with timeouts, and retryable vs. permanent error classification.
- Retries with exponential backoff and jitter, per-worker rate limiting, idempotent snapshots and alerts.
- Deal detection: 30-day average rule and per-part target price, with no repeat alerts while a deal is active.
- Deal alerts via SMTP email, or logs when SMTP isn't configured. Failed sends retry without losing the deal.
- Job run tracking (`job_runs`) and structured JSON logs.
- REST API: parts CRUD, price history, deals, status, health, manual trigger. Admin routes protected by token.
- Status page at `/` and Swagger docs at `/docs`.
- Starter parts with placeholder SKUs and a demo-mode price history backfill.
- GitHub Actions CI (ruff + pytest with Postgres and Redis).
- Render free-tier blueprint with CI-gated deploys and a GitHub Actions cron trigger.

### Fixed
- Celery Beat now fires at check window boundaries instead of counting from its start time.

[Unreleased]: https://github.com/pepsi-boy/partwatch/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/pepsi-boy/partwatch/releases/tag/v1.0.0
