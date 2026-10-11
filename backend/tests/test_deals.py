"""Unit tests for the pure deal rules. No database."""

from decimal import Decimal as D

from app.services.deals import (
    BELOW_AVERAGE,
    BELOW_TARGET,
    baseline_average,
    evaluate,
    is_rearmed,
    percent_below,
)

RULES = {"threshold_percent": D("10"), "min_snapshots": 5}
HISTORY = [D("550.00")] * 10  # 30-day average: $550


def test_baseline_average_and_percent():
    assert baseline_average([D("500"), D("600")]) == D("550.00")
    assert baseline_average([]) is None
    assert percent_below(D("479.99"), D("550.00")) == D("12.73")
    assert percent_below(D("600"), D("550")) == D("-9.09")


def test_price_well_below_average_is_deal():
    decision = evaluate(D("479.99"), HISTORY, **RULES)
    assert decision.is_deal
    assert decision.reason == BELOW_AVERAGE
    assert decision.baseline_avg == D("550.00")
    assert decision.percent_below == D("12.73")


def test_exactly_at_threshold_is_deal():
    assert evaluate(D("495.00"), HISTORY, **RULES).is_deal  # exactly 10% below


def test_just_under_threshold_is_not_deal():
    decision = evaluate(D("495.01"), HISTORY, **RULES)
    assert not decision.is_deal
    assert "threshold" in decision.explanation


def test_not_enough_history_is_not_deal():
    decision = evaluate(D("300.00"), [D("550")] * 4, **RULES)
    assert not decision.is_deal
    assert "4 of 5" in decision.explanation


def test_no_history_at_all_is_not_deal():
    decision = evaluate(D("300.00"), [], **RULES)
    assert not decision.is_deal
    assert decision.baseline_avg == D("300.00")


def test_target_price_triggers_without_history():
    decision = evaluate(D("499.99"), [], target_price=D("499.99"), **RULES)
    assert decision.is_deal
    assert decision.reason == BELOW_TARGET


def test_above_target_and_near_average_is_not_deal():
    assert not evaluate(D("520.00"), HISTORY, target_price=D("499.99"), **RULES).is_deal


def test_average_rule_wins_when_both_match():
    decision = evaluate(D("450.00"), HISTORY, target_price=D("499.99"), **RULES)
    assert decision.reason == BELOW_AVERAGE


def test_repeated_same_price_does_not_realert():
    decision = evaluate(D("479.99"), HISTORY, active_deal_price=D("479.99"), **RULES)
    assert not decision.is_deal
    assert "Already alerted" in decision.explanation


def test_higher_price_during_active_deal_does_not_realert():
    assert not evaluate(D("489.99"), HISTORY, active_deal_price=D("479.99"), **RULES).is_deal


def test_further_drop_during_active_deal_alerts_again():
    decision = evaluate(D("449.99"), HISTORY, active_deal_price=D("479.99"), **RULES)
    assert decision.is_deal


def test_price_above_average_is_not_deal():
    decision = evaluate(D("600.00"), HISTORY, **RULES)
    assert not decision.is_deal
    assert decision.percent_below < 0


def test_rearms_when_price_recovers_to_average():
    kwargs = {"reason": BELOW_AVERAGE, "deal_baseline": D("550.00"), "target_price": None}
    assert not is_rearmed(prices_since_deal=[D("479.99"), D("520.00")], **kwargs)
    assert is_rearmed(prices_since_deal=[D("479.99"), D("550.00")], **kwargs)
    assert not is_rearmed(prices_since_deal=[], **kwargs)


def test_target_deal_rearms_when_price_goes_back_above_target():
    kwargs = {"reason": BELOW_TARGET, "deal_baseline": D("550"), "target_price": D("499.99")}
    assert not is_rearmed(prices_since_deal=[D("499.99")], **kwargs)
    assert is_rearmed(prices_since_deal=[D("500.00")], **kwargs)
