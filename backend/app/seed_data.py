"""Starter parts to track.

PLACEHOLDER SKUs: every SKU below is fake (they start with 000000 so they can never
match a real Best Buy product). Replace them with real Best Buy SKUs before adding
an API key. In demo mode the mock provider uses `base_price` as the part's
typical price.
"""

from decimal import Decimal

PLACEHOLDER_PREFIX = "000000"

STARTER_PARTS = [
    {"sku": "0000001", "category": "gpu", "name": "NVIDIA GeForce RTX 5070 12GB",
     "base_price": Decimal("549.99"), "target_price": Decimal("499.99")},
    {"sku": "0000002", "category": "gpu", "name": "AMD Radeon RX 9070 XT 16GB",
     "base_price": Decimal("599.99"), "target_price": Decimal("529.99")},
    {"sku": "0000003", "category": "cpu", "name": "AMD Ryzen 7 9800X3D",
     "base_price": Decimal("479.99"), "target_price": Decimal("429.99")},
    {"sku": "0000004", "category": "cpu", "name": "Intel Core Ultra 7 265K",
     "base_price": Decimal("299.99"), "target_price": None},
    {"sku": "0000005", "category": "ram", "name": "Corsair Vengeance 32GB DDR5-6000",
     "base_price": Decimal("109.99"), "target_price": Decimal("89.99")},
    {"sku": "0000006", "category": "ssd", "name": "Samsung 990 PRO 2TB NVMe",
     "base_price": Decimal("169.99"), "target_price": Decimal("149.99")},
    {"sku": "0000007", "category": "ssd", "name": "WD_BLACK SN850X 1TB NVMe",
     "base_price": Decimal("89.99"), "target_price": None},
    {"sku": "0000008", "category": "psu", "name": "Corsair RM850e 850W 80+ Gold",
     "base_price": Decimal("119.99"), "target_price": Decimal("99.99")},
]  # fmt: skip
