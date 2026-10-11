"""Price providers.

Everything that fetches prices goes through the PriceProvider interface, so the
rest of the system doesn't care where prices come from. With BESTBUY_API_KEY set,
the real Best Buy client is used. Without it, the app runs in demo mode on
MockBestBuyProvider.
"""

import hashlib
import random
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from app.config import Settings, get_settings
from app.seed_data import STARTER_PARTS
from app.services.bestbuy import BestBuyClient, BestBuyError, ProductPrice, parse_product


class PriceProvider(Protocol):
    name: str

    def get_product(self, sku: str) -> ProductPrice: ...

    def close(self) -> None: ...

    def __enter__(self) -> "PriceProvider": ...

    def __exit__(self, *exc) -> None: ...


class MockBestBuyProvider:
    """Fake Best Buy that behaves like the real thing, so demo mode exercises real code.

    - Responses use the Products API JSON shape and go through the same parser.
    - Prices are deterministic per (SKU, time): the same check window always gets
      the same price, so retries and tests are reproducible.
    - Prices move: +/-3% noise every 3 hours, and on roughly 1 day in 7 a part goes
      on sale for 12-22% off, which is enough to trigger deal alerts.
    """

    name = "mock"
    SALE_CHANCE_PER_DAY = 0.15
    NOISE = 0.03

    def __init__(self, now=lambda: datetime.now(UTC)):
        self._now = now
        self._catalog = {p["sku"]: p for p in STARTER_PARTS}

    def close(self) -> None:
        pass

    def __enter__(self) -> "MockBestBuyProvider":
        return self

    def __exit__(self, *exc) -> None:
        pass

    def get_product(self, sku: str, at: datetime | None = None) -> ProductPrice:
        if not sku.isdigit():
            raise BestBuyError(f"Invalid SKU {sku!r}: must be digits only")
        return parse_product(self.product_json(sku, at or self._now()), sku)

    def product_json(self, sku: str, at: datetime) -> dict:
        """What Best Buy's /v1/products/{sku}.json returns for our `show` fields."""
        entry = self._catalog.get(sku)
        regular = entry["base_price"] if entry else _fallback_price(sku)
        name = entry["name"] if entry else f"Demo Product {sku}"

        day_rng = random.Random(f"{sku}:{at.date().isoformat()}")
        on_sale = day_rng.random() < self.SALE_CHANCE_PER_DAY
        discount = day_rng.uniform(0.12, 0.22) if on_sale else 0.0
        in_stock = day_rng.random() < 0.95

        window_rng = random.Random(f"{sku}:{at.date().isoformat()}:{at.hour // 3}")
        noise = window_rng.uniform(-self.NOISE, self.NOISE)

        price = float(regular) * (1 - discount) * (1 + noise)
        sale_price = min(_ends_in_99(price), float(regular))

        return {
            "sku": int(sku),
            "name": name,
            "salePrice": sale_price,
            "regularPrice": float(regular),
            "onSale": on_sale,
            "onlineAvailability": in_stock,
        }


def _fallback_price(sku: str) -> Decimal:
    """Stable made-up price for SKUs not in the starter catalog ($50-$1000)."""
    n = int(hashlib.sha256(sku.encode()).hexdigest(), 16)
    return Decimal(str(_ends_in_99(50 + n % 950))).quantize(Decimal("0.01"))


def _ends_in_99(price: float) -> float:
    return max(round(price), 1) - 0.01


def get_provider(settings: Settings | None = None) -> PriceProvider:
    settings = settings or get_settings()
    if settings.bestbuy_api_key:
        return BestBuyClient(settings.bestbuy_api_key)
    return MockBestBuyProvider()


def is_demo_mode(settings: Settings | None = None) -> bool:
    return not (settings or get_settings()).bestbuy_api_key
