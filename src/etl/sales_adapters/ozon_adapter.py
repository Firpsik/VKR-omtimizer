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
class OzonReportAdapter(SalesAdapter):
    marketplace_code = "ozon"
    display_name = "Ozon — отчёт о реализации товаров"
    accepted_column_set = {
        "Дата отгрузки",
        "Артикул",
        "Цена продажи (₽)",
        "Кол-во",
    }

    def parse(self, csv_text: str) -> list[CanonicalSale]:
        out: list[CanonicalSale] = []
        for row_n, row in iter_rows(csv_text):
            try:
                price = parse_float(row.get("Цена продажи (₽)"), row_n)
                qty = parse_int(row.get("Кол-во"), row_n)
                if price <= 0 or qty <= 0:
                    continue
                action = (row.get("Тип акции") or "").strip()
                discount = parse_float(row.get("Скидка, %", 0), row_n)
                is_promo = bool(action) or discount > 0
                stock_str = row.get("Остаток на складе")
                stock_qty = parse_int(stock_str, row_n) if stock_str else None
                out.append(CanonicalSale(
                    obs_date=parse_date(row.get("Дата отгрузки", ""), row_n),
                    sku=(row.get("Артикул") or "").strip(),
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
