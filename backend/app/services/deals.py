"""Deal detection rules. Pure functions only (no database, no I/O), so every
edge case can be unit tested directly.

A price is a deal when either:
- below_average: it's at least `threshold_percent` below the 30-day average, and
  there are at least `min_snapshots` prior prices (so new parts can't false-alarm), or
- below_target: it's at or below the part's target price, if one is set.

No repeat alerts: while a previous deal is still "active", a new deal only counts
if the price drops below that deal's price. A deal stops being active once the
price recovers (see `is_rearmed`), so the next sale alerts again.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

BELOW_AVERAGE = "below_average"
BELOW_TARGET = "below_target"

CENTS = Decimal("0.01")


@dataclass(frozen=True)
class DealDecision:
    is_deal: bool
    reason: str | None
    baseline_avg: Decimal
    percent_below: Decimal
    explanation: str


def baseline_average(history: Sequence[Decimal]) -> Decimal | None:
    if not history:
        return None
    return (sum(history, Decimal(0)) / len(history)).quantize(CENTS, ROUND_HALF_UP)


def percent_below(price: Decimal, baseline: Decimal) -> Decimal:
    if baseline <= 0:
        return Decimal("0.00")
    return ((baseline - price) / baseline * 100).quantize(CENTS, ROUND_HALF_UP)


def evaluate(
    price: Decimal,
    history: Sequence[Decimal],
    *,
    threshold_percent: Decimal,
    min_snapshots: int,
    target_price: Decimal | None = None,
    active_deal_price: Decimal | None = None,
) -> DealDecision:
    """Decide whether `price` is a deal.

    history: prior prices in the baseline window (excluding `price` itself).
    active_deal_price: price of the last deal if it's still active, else None.
    """
    avg = baseline_average(history)
    baseline = avg if avg is not None else price
    pct = percent_below(price, baseline)

    # Compare exact prices, not the rounded percentage: 9.998% must not round up to 10%.
    deal_line = baseline * (1 - threshold_percent / 100)
    reason = None
    if avg is not None and len(history) >= min_snapshots and price <= deal_line:
        reason = BELOW_AVERAGE
    elif target_price is not None and price <= target_price:
        reason = BELOW_TARGET

    if reason is None:
        if len(history) < min_snapshots:
            why = f"only {len(history)} of {min_snapshots} snapshots needed for a baseline"
        else:
            why = f"{pct}% below average, threshold is {threshold_percent}%"
        return DealDecision(False, None, baseline, pct, f"Not a deal: {why}")

    if active_deal_price is not None and price >= active_deal_price:
        return DealDecision(
            False,
            None,
            baseline,
            pct,
            f"Already alerted at ${active_deal_price}; no new alert unless it drops further",
        )

    return DealDecision(True, reason, baseline, pct, describe(reason, price, pct, target_price))


def is_rearmed(
    *,
    reason: str,
    deal_baseline: Decimal,
    target_price: Decimal | None,
    prices_since_deal: Sequence[Decimal],
) -> bool:
    """Has the price recovered since the last deal, so the next drop alerts again?

    below_average deals re-arm once the price gets back to the average it was
    compared against. below_target deals re-arm once the price goes back above target.
    """
    if reason == BELOW_TARGET and target_price is not None:
        rearm_at = target_price + CENTS
    else:
        rearm_at = deal_baseline
    return any(p >= rearm_at for p in prices_since_deal)


def describe(reason: str, price: Decimal, pct: Decimal, target_price: Decimal | None) -> str:
    if reason == BELOW_TARGET:
        return f"${price}, at or below your ${target_price} target"
    return f"${price}, {pct.normalize():f}% below its 30-day average"
