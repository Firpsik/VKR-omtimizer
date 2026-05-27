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
class YmReportAdapter(SalesAdapter):
    marketplace_code = "ym"
    display_name = "Яндекс.Маркет — отчёт по продажам"
    accepted_column_set = {
        "Дата заказа",
        "Ваш SKU",
        "Цена за единицу, ₽",
        "Количество",
    }

    def parse(self, csv_text: str) -> list[CanonicalSale]:
        out: list[CanonicalSale] = []
        for row_n, row in iter_rows(csv_text):
            try:
                price = parse_float(row.get("Цена за единицу, ₽"), row_n)
                qty = parse_int(row.get("Количество"), row_n)
                if price <= 0 or qty <= 0:
                    continue
                promo_label = (row.get("Промо-акция") or "").strip()
                discount = parse_float(row.get("Скидка, %", 0), row_n)
                is_promo = bool(promo_label) or discount > 0
                stock_str = row.get("Остаток на складе")
                stock_qty = parse_int(stock_str, row_n) if stock_str else None
                out.append(CanonicalSale(
                    obs_date=parse_date(row.get("Дата заказа", ""), row_n),
                    sku=(row.get("Ваш SKU") or "").strip(),
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
