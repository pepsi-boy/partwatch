#!/usr/bin/env bash
# Production entrypoint for Render's free tier: API and Celery worker in one container,
# because Render's background workers aren't free. See docs/design.md.
set -euo pipefail

alembic upgrade head

# Demo mode: seed placeholder parts and fill missing history with mock prices.
# Idempotent, and it skips both steps once BESTBUY_API_KEY is set.
python -m app.seed --backfill-days 30

# --pool=solo: one task at a time in the main process. Lowest memory use, which
# matters on a 512 MB instance. Throughput is still bounded by the API rate limit.
celery -A app.celery_app worker --loglevel=info --pool=solo &
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &

# If either process dies, exit so Render restarts the whole container instead of
# leaving the API up with no worker behind it.
wait -n
exit $?
