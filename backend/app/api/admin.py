from fastapi import APIRouter, Depends, status

from app.api.deps import require_admin

router = APIRouter(tags=["admin"])


@router.post(
    "/run-checks", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)]
)
def run_checks() -> dict:
    """Queue a full price check now.

    In production on Render's free tier there's no always-on Beat process, so a
    GitHub Actions cron calls this on the schedule instead (see docs/design.md).
    Calling it twice in one check window is harmless: duplicates are skipped.
    """
    from app.tasks import check_all_prices

    check_all_prices.delay()
    return {"queued": "check_all_prices"}
