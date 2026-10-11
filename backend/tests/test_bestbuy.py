"""Best Buy client tests. All HTTP is mocked with httpx.MockTransport: no real calls."""

from decimal import Decimal

import httpx
import pytest

from app.services.bestbuy import (
    BestBuyClient,
    BestBuyError,
    ProductNotFound,
    RetryableBestBuyError,
)

API_KEY = "test-key-secret"

PRODUCT = {
    "sku": 6521430,
    "name": "NVIDIA GeForce RTX 4070",
    "salePrice": 479.99,
    "regularPrice": 549.99,
    "onSale": True,
    "onlineAvailability": True,
}


def client_returning(handler) -> BestBuyClient:
    return BestBuyClient(API_KEY, transport=httpx.MockTransport(handler))


def respond(status=200, json=None, text=None):
    def handler(request):
        if json is not None:
            return httpx.Response(status, json=json)
        return httpx.Response(status, text=text or "")

    return handler


def test_parses_product():
    product = client_returning(respond(json=PRODUCT)).get_product("6521430")

    assert product.sku == "6521430"
    assert product.name == "NVIDIA GeForce RTX 4070"
    assert product.price == Decimal("479.99")
    assert product.regular_price == Decimal("549.99")
    assert product.on_sale is True
    assert product.in_stock is True


def test_sends_key_and_limits_fields():
    seen = {}

    def handler(request):
        seen["url"] = request.url
        return httpx.Response(200, json=PRODUCT)

    client_returning(handler).get_product("6521430")

    assert seen["url"].path == "/v1/products/6521430.json"
    assert seen["url"].params["apiKey"] == API_KEY
    assert "salePrice" in seen["url"].params["show"]


def test_missing_regular_price_is_none():
    data = {**PRODUCT, "regularPrice": None}
    assert client_returning(respond(json=data)).get_product("1").regular_price is None


def test_404_is_not_found():
    with pytest.raises(ProductNotFound):
        client_returning(respond(404)).get_product("1")


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_rate_limit_and_server_errors_are_retryable(status):
    with pytest.raises(RetryableBestBuyError):
        client_returning(respond(status)).get_product("1")


def test_403_over_quota_is_retryable():
    with pytest.raises(RetryableBestBuyError):
        client_returning(respond(403, text="<h1>Over Quota</h1>")).get_product("1")


def test_403_bad_key_is_permanent():
    with pytest.raises(BestBuyError) as exc_info:
        client_returning(respond(403, text="<h1>Developer Inactive</h1>")).get_product("1")
    assert not isinstance(exc_info.value, RetryableBestBuyError)


def test_timeout_is_retryable_and_does_not_leak_key():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(RetryableBestBuyError) as exc_info:
        client_returning(handler).get_product("1")
    assert API_KEY not in str(exc_info.value)


def test_connection_error_is_retryable_and_does_not_leak_key():
    def handler(request):
        raise httpx.ConnectError(f"failed {request.url}", request=request)

    with pytest.raises(RetryableBestBuyError) as exc_info:
        client_returning(handler).get_product("1")
    assert API_KEY not in str(exc_info.value)


def test_malformed_response_is_permanent():
    with pytest.raises(BestBuyError):
        client_returning(respond(json={"name": "no price"})).get_product("1")
    with pytest.raises(BestBuyError):
        client_returning(respond(text="not json")).get_product("1")


def test_rejects_non_numeric_sku_without_calling_api():
    def handler(request):
        raise AssertionError("should not be called")

    with pytest.raises(BestBuyError):
        client_returning(handler).get_product("../admin")


def test_timeouts_are_configured():
    client = BestBuyClient(API_KEY)
    assert client._http.timeout.read == 10.0
    assert client._http.timeout.connect == 5.0


def test_requires_api_key():
    with pytest.raises(BestBuyError):
        BestBuyClient("")
