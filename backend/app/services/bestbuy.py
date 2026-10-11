"""Best Buy Products API client.

Limits (Best Buy developer terms): 5 calls/second and 50,000 calls/day per key.
Going over the limit returns 403 (the terms) or 429 (Best Buy's own SDK docs),
so both are treated as retryable rate limiting. Throttling itself happens in the
Celery task layer, where every worker shares the rate limit.

Errors are split into retryable (timeouts, 429, 5xx, over-quota 403) and permanent
(bad key, unknown SKU, malformed data), so callers can retry only what will succeed.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

BASE_URL = "https://api.bestbuy.com/v1"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
FIELDS = "sku,name,salePrice,regularPrice,onSale,onlineAvailability"


class BestBuyError(Exception):
    """Permanent failure. Retrying won't help."""


class RetryableBestBuyError(BestBuyError):
    """Transient failure (timeout, rate limit, server error). Safe to retry."""


class ProductNotFound(BestBuyError):
    pass


@dataclass(frozen=True)
class ProductPrice:
    sku: str
    name: str
    price: Decimal
    regular_price: Decimal | None
    on_sale: bool
    in_stock: bool


class BestBuyClient:
    name = "bestbuy"

    def __init__(
        self,
        api_key: str,
        timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise BestBuyError("BESTBUY_API_KEY is not set")
        self._api_key = api_key
        # `transport` lets tests swap in httpx.MockTransport so no real calls are made.
        self._http = httpx.Client(base_url=BASE_URL, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "BestBuyClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def get_product(self, sku: str) -> ProductPrice:
        if not sku.isdigit():
            raise BestBuyError(f"Invalid SKU {sku!r}: must be digits only")

        try:
            resp = self._http.get(
                f"/products/{sku}.json",
                params={"apiKey": self._api_key, "show": FIELDS, "format": "json"},
            )
        # Exception messages are written by hand: httpx's own messages include the
        # request URL, which contains the API key.
        except httpx.TimeoutException:
            raise RetryableBestBuyError(f"Timed out fetching SKU {sku}") from None
        except httpx.TransportError as exc:
            raise RetryableBestBuyError(
                f"Network error fetching SKU {sku}: {type(exc).__name__}"
            ) from None

        _raise_for_status(resp, sku)
        return _parse_product(resp, sku)


def _raise_for_status(resp: httpx.Response, sku: str) -> None:
    code = resp.status_code
    if code == 200:
        return
    if code == 404:
        raise ProductNotFound(f"SKU {sku} not found")
    if code == 429 or code >= 500:
        raise RetryableBestBuyError(f"HTTP {code} fetching SKU {sku}")
    if code == 403:
        # 403 means either "over quota" (transient) or a bad/inactive key (permanent).
        # Only the body tells them apart.
        if "quota" in resp.text.lower():
            raise RetryableBestBuyError(f"Rate limit (403 over quota) fetching SKU {sku}")
        raise BestBuyError(f"HTTP 403 fetching SKU {sku}: check BESTBUY_API_KEY")
    raise BestBuyError(f"HTTP {code} fetching SKU {sku}")


def _parse_product(resp: httpx.Response, sku: str) -> ProductPrice:
    try:
        data = resp.json()
    except ValueError:
        raise BestBuyError(f"Unexpected response for SKU {sku}: not JSON") from None
    return parse_product(data, sku)


def parse_product(data: dict, sku: str) -> ProductPrice:
    """Turn a Products API JSON object into a ProductPrice.

    Shared by the real client and the mock provider, so demo mode runs the same
    parsing code as production.
    """
    try:
        sale_price = data["salePrice"]
        if sale_price is None:
            raise KeyError("salePrice")
        regular = data.get("regularPrice")
        return ProductPrice(
            # Keep the requested SKU: the API returns it as an int, which drops leading zeros.
            sku=sku,
            name=data.get("name") or "",
            price=_to_money(sale_price),
            regular_price=_to_money(regular) if regular is not None else None,
            on_sale=bool(data.get("onSale", False)),
            in_stock=bool(data.get("onlineAvailability", False)),
        )
    except (KeyError, TypeError, AttributeError, InvalidOperation) as exc:
        raise BestBuyError(f"Unexpected response for SKU {sku}: {exc!r}") from None


def _to_money(value) -> Decimal:
    # str() first: Decimal(479.99) would carry float rounding error.
    return Decimal(str(value)).quantize(Decimal("0.01"))
