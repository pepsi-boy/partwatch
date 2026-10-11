# PartWatch

A self-running PC parts price tracker. It checks Best Buy prices on a schedule, builds a price history, detects real deals (well below the 30-day average), and emails an alert.

**Stack:** FastAPI · Celery + Celery Beat · Redis · PostgreSQL · SQLAlchemy/Alembic · Next.js · Docker Compose · GitHub Actions · Render

> Work in progress. Full docs land with v1.0.0.

## Run locally

```bash
cp .env.example .env      # fill in BESTBUY_API_KEY etc.
docker compose up --build
curl localhost:8000/health
```

## Tests and lint

```bash
docker compose exec api pytest
docker compose exec api ruff check .
```
