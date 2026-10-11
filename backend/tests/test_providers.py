from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import Settings
from app.seed_data import PLACEHOLDER_PREFIX, STARTER_PARTS
from app.services.bestbuy import BestBuyClient, BestBuyError
from app.services.providers import MockBestBuyProvider, get_provider, is_demo_mode

T0 = datetime(2026, 10, 11, 12, tzinfo=UTC)


def test_real_provider_used_when_api_key_set():
    provider = get_provider(Settings(bestbuy_api_key="abc"))
    assert isinstance(provider, BestBuyClient)
    assert not is_demo_mode(Settings(bestbuy_api_key="abc"))


def test_mock_provider_used_without_api_key():
    provider = get_provider(Settings(bestbuy_api_key=""))
    assert isinstance(provider, MockBestBuyProvider)
    assert is_demo_mode(Settings(bestbuy_api_key=""))


def test_mock_json_matches_best_buy_products_format():
    data = MockBestBuyProvider().product_json("0000001", T0)

    assert set(data) == {
        "sku",
        "name",
        "salePrice",
        "regularPrice",
        "onSale",
        "onlineAvailability",
    }
    assert isinstance(data["sku"], int)
    assert isinstance(data["salePrice"], float)
    assert isinstance(data["onSale"], bool)


def test_mock_product_parses_through_shared_parser():
    product = MockBestBuyProvider(now=lambda: T0).get_product("0000001")

    assert product.sku == "0000001"
    assert product.name == "NVIDIA GeForce RTX 5070 12GB"
    assert product.regular_price == Decimal("549.99")
    assert product.price <= product.regular_price
    assert str(product.price).endswith(".99")


def test_mock_is_deterministic_within_a_window():
    mock = MockBestBuyProvider()
    assert mock.get_product("0000001", T0) == mock.get_product("0000001", T0 + timedelta(hours=1))


def test_mock_prices_change_over_time():
    mock = MockBestBuyProvider()
    prices = {mock.get_product("0000001", T0 + timedelta(hours=3 * i)).price for i in range(40)}
    assert len(prices) > 5


@pytest.mark.parametrize("part", STARTER_PARTS, ids=lambda p: p["category"] + p["sku"])
def test_mock_produces_deal_sized_drops(part):
    """Over 60 days every starter part should have at least one sale >= 10% off."""
    mock = MockBestBuyProvider()
    days = [mock.get_product(part["sku"], T0 + timedelta(days=d)) for d in range(60)]
    regular = part["base_price"]
    assert any(p.on_sale and p.price <= regular * Decimal("0.90") for p in days)
    assert all(p.price <= regular for p in days)


def test_mock_handles_unknown_sku_with_stable_price():
    mock = MockBestBuyProvider()
    first = mock.get_product("6521430", T0)
    assert first.name == "Demo Product 6521430"
    assert Decimal("50") <= first.regular_price <= Decimal("1000")
    assert mock.get_product("6521430", T0).regular_price == first.regular_price


def test_mock_rejects_invalid_sku():
    with pytest.raises(BestBuyError):
        MockBestBuyProvider().get_product("abc")


def test_starter_parts_cover_categories_and_use_placeholder_skus():
    assert {p["category"] for p in STARTER_PARTS} == {"gpu", "cpu", "ram", "ssd", "psu"}
    assert all(p["sku"].startswith(PLACEHOLDER_PREFIX) for p in STARTER_PARTS)
    assert len({p["sku"] for p in STARTER_PARTS}) == len(STARTER_PARTS)
