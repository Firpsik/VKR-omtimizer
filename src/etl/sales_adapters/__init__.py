from src.etl.sales_adapters.base import (
    AdapterError,
    CanonicalSale,
    SalesAdapter,
    detect_adapter,
    parse_report,
)

__all__ = [
    "AdapterError",
    "CanonicalSale",
    "SalesAdapter",
    "detect_adapter",
    "parse_report",
]

from src.etl.sales_adapters import wb_adapter, ozon_adapter, ym_adapter  # noqa: E402,F401
