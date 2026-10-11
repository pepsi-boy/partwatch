# Changelog

All notable changes to this project are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/), versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added
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
