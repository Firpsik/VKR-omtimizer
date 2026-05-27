from __future__ import annotations

import sys
import secrets

from fastapi.testclient import TestClient
from sqlalchemy import text

from src.api.app import app
from src.db import get_engine

client = TestClient(app)
_test_email = f"e2e_pipeline_{secrets.token_hex(4)}@asop.test"
client.post("/register", data={
    "email": _test_email,
    "password": "e2e_pipeline_pwd",
    "password2": "e2e_pipeline_pwd",
    "display_name": "E2E Pipeline",
})
engine = get_engine()

TEST_CATEGORY = "food-healthy"
TEST_SKU      = "E2E-TEA-001"

def _cleanup() -> None:
    with engine.connect() as c:
        pids = [r[0] for r in c.execute(text(
            "SELECT product_id FROM mp.products WHERE sku LIKE 'E2E-%'"
        )).fetchall()]
        for pid in pids:
            for tbl in ("sales_history", "optimization_results", "demand_params",
                        "unit_economics", "product_overrides"):
                c.execute(text(f"DELETE FROM mp.{tbl} WHERE product_id=:p"), {"p": pid})
        c.execute(text("DELETE FROM mp.products WHERE sku LIKE 'E2E-%'"))

def _step(n: str, title: str, ok: bool, extra: str = ""):
    mark = "✓" if ok else "✗"
    print(f"  [{mark}] Шаг {n}. {title}" + (f"  ({extra})" if extra else ""))
    if not ok:
        sys.exit(1)

def _count(table: str) -> int:
    with engine.connect() as c:
        return c.execute(text(f"SELECT COUNT(*) FROM mp.{table}")).scalar()

def _c_total_for_product(pid: int, marketplace_code: str = "wb",
                          scheme: str = "FBO") -> float | None:
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT ue.c_total_rub
              FROM mp.unit_economics ue
              JOIN mp.marketplaces m ON m.marketplace_id = ue.marketplace_id
             WHERE ue.product_id=:p AND m.code=:mc AND ue.scheme=:s
        """), {"p": pid, "mc": marketplace_code, "s": scheme}).fetchone()
    return float(row[0]) if row else None

def _create_product(overrides: dict | None = None) -> int:
    data = {
        "sku": TEST_SKU,
        "name": "Чай зелёный пакетированный 100шт",
        "category_code": TEST_CATEGORY,
        "weight_kg": "0.3",
        "volume_l": "1.5",
        "cost_rub": "300",
        "promo_rub": "0",
    }
    if overrides:
        data.update(overrides)
    r = client.post("/optimize", data=data)
    assert r.status_code == 200, r.text[:300]
    with engine.connect() as c:
        return c.execute(text(
            "SELECT product_id FROM mp.products WHERE sku=:s"
        ), {"s": TEST_SKU}).scalar()

def run() -> None:
    print("=" * 70)
    print("E2E pipeline test — АСОП-Маркет")
    print("=" * 70)
    _cleanup()

    snap_before = {
        "products":              _count("products"),
        "sales_history":         _count("sales_history"),
        "optimization_results":  _count("optimization_results"),
        "product_overrides":     _count("product_overrides"),
        "canonical_categories":  _count("canonical_categories"),
    }
    _step("0", "Снапшот «было»", True, str(snap_before))

    pid = _create_product()
    _step("2", "POST /optimize (baseline без overrides)", pid is not None,
          f"product_id={pid}")

    csv_text = (
        "Дата продажи;Артикул продавца;Категория;Бренд;Предмет;Размер;"
        "Цена розничная;Цена розничная со скидкой;Кол-во;"
        "Скидка постоянного покупателя СПП, %;Тип скидки;Остаток\n"
        + "\n".join(
            f"{day:02d}.03.2026;{TEST_SKU};Продукты;NoName;Чай зелёный;-;"
            f"590;{price};{qty};5,0;Акция;{120 - day * 5}"
            for day, price, qty in [
                (1, 490, 5), (2, 390, 8), (3, 590, 3), (4, 490, 6),
                (5, 390, 9), (6, 590, 2), (7, 490, 5), (8, 390, 10),
                (9, 590, 3), (10, 490, 7),
            ]
        )
        + "\n"
    )
    r = client.post(
        "/sales/upload-mp-report",
        files={"files": ("wb.csv", csv_text.encode("utf-8"), "text/csv")},
        data={"replace": "false"},
    )
    _step("3", "POST /sales/upload-mp-report (WB)",
          r.status_code == 200,
          f"sales_history стало {_count('sales_history')}")

    r = client.post("/sales/add", json={
        "sku": TEST_SKU, "marketplace_code": "wb",
        "observations": [{
            "obs_date": "2026-03-11", "price_rub": 490, "qty": 8,
            "is_promo": True, "stock_qty": 60,
        }],
    })
    _step("4", "POST /sales/add", r.status_code == 200, str(r.json()))

    c_baseline = _c_total_for_product(pid)
    _step("4a", "Базовое c_total_rub зафиксировано",
          c_baseline is not None and c_baseline > 0, f"C={c_baseline:.2f}")

    pid_o = _create_product({
        "return_rate_override": "0.15",
        "storage_days_override": "60",
        "promo_pct_override": "0.10",
    })
    _step("5", "POST /optimize с overrides", pid_o == pid,
          "return_rate=0.15, storage_days=60, promo_pct=0.10")

    c_override = _c_total_for_product(pid)
    _step("5a", "С overrides c_total_rub изменилось",
          c_override is not None and abs(c_override - c_baseline) > 1.0,
          f"baseline={c_baseline:.2f} → override={c_override:.2f} "
          f"(Δ={c_override - c_baseline:+.2f}₽)")

    with engine.connect() as c:
        ov = c.execute(text("""
            SELECT return_rate, storage_days, promo_pct
              FROM mp.product_overrides WHERE product_id=:p
        """), {"p": pid}).fetchone()
    _step("6", "mp.product_overrides обновлены",
          ov is not None
          and abs(float(ov[0]) - 0.15) < 1e-6
          and int(ov[1]) == 60
          and abs(float(ov[2]) - 0.10) < 1e-6,
          f"row={ov}")

    r = client.post("/delete", data={"sku": TEST_SKU})
    _step("7", "POST /delete", r.status_code == 200)
    with engine.connect() as c:
        n_sales = c.execute(text(
            "SELECT COUNT(*) FROM mp.sales_history WHERE product_id=:p"
        ), {"p": pid}).scalar()
        n_ov = c.execute(text(
            "SELECT COUNT(*) FROM mp.product_overrides WHERE product_id=:p"
        ), {"p": pid}).scalar()
        n_opt = c.execute(text(
            "SELECT COUNT(*) FROM mp.optimization_results WHERE product_id=:p"
        ), {"p": pid}).scalar()
    _step("7a", "Каскад удалил связанные строки",
          n_sales == 0 and n_ov == 0 and n_opt == 0,
          f"sales={n_sales}, overrides={n_ov}, results={n_opt}")

    snap_after = {
        "products":              _count("products"),
        "sales_history":         _count("sales_history"),
        "optimization_results":  _count("optimization_results"),
        "product_overrides":     _count("product_overrides"),
        "canonical_categories":  _count("canonical_categories"),
    }
    _step("9", "Снапшот «стало» совпал с «было»",
          snap_after == snap_before,
          f"\n          BEFORE: {snap_before}"
          f"\n          AFTER:  {snap_after}")

    print()
    print("=" * 70)
    print("✓ Все 13 шагов пайплайна прошли успешно.")
    print("=" * 70)

if __name__ == "__main__":
    run()
