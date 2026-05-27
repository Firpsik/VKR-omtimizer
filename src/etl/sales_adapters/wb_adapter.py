from __future__ import annotations

from src.etl.sales_adapters.base import (
    AdapterError,
    CanonicalSale,
    SalesAdapter,
    iter_rows,
    parse_date,
    parse_float,
    parse_int,
    register,
)

@register
class WbReportAdapter(SalesAdapter):
    marketplace_code = "wb"
    display_name = "Wildberries — финансовый отчёт реализации"
    accepted_column_set = {
        "Дата продажи",
        "Артикул продавца",
        "Цена розничная",
        "Кол-во",
    }

    def parse(self, csv_text: str) -> list[CanonicalSale]:
        out: list[CanonicalSale] = []
        for row_n, row in iter_rows(csv_text):
            try:
                price = parse_float(
                    row.get("Цена розничная со скидкой") or row.get("Цена розничная"),
                    row_n,
                )
                if price <= 0:
                    continue
                qty = parse_int(row.get("Кол-во"), row_n)
                if qty <= 0:
                    continue
                discount_pct = parse_float(row.get("Скидка постоянного покупателя СПП, %", 0), row_n)
                promo_type = (row.get("Тип скидки") or "").lower()
                is_promo = discount_pct > 0 or "акци" in promo_type or "распродажа" in promo_type
                stock_str = row.get("Остаток") or row.get("Доступно к продаже")
                stock_qty = parse_int(stock_str, row_n) if stock_str else None
                out.append(CanonicalSale(
                    obs_date=parse_date(row.get("Дата продажи", ""), row_n),
                    sku=(row.get("Артикул продавца") or "").strip(),
                    price_rub=price,
                    qty=qty,
                    is_promo=is_promo,
                    stock_qty=stock_qty,
                    source_row=row_n,
                ))
            except AdapterError:
                raise
            except Exception as e:
                raise AdapterError(f"строка {row_n}: {e}") from e
        return out
