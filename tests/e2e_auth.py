from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.app import app
from src.db import get_engine


engine = get_engine()
ALICE = ("alice@asop.test", "alice_pwd_123", "Алиса Тестовая")
BOB = ("bob@asop.test", "bob_pwd_456", "Боб Тестовый")


def _cleanup_users():
    with engine.connect() as c:
        ids = [r[0] for r in c.execute(text(
            "SELECT product_id FROM mp.products p JOIN mp.users u USING (user_id) "
            "WHERE u.email IN ('alice@asop.test','bob@asop.test')"
        )).fetchall()]
        for pid in ids:
            for t in ('sales_history','optimization_results','demand_params','unit_economics','product_overrides'):
                c.execute(text(f"DELETE FROM mp.{t} WHERE product_id = :p"), {"p": pid})
        c.execute(text("DELETE FROM mp.products WHERE product_id = ANY(:p)"), {"p": ids})
        c.execute(text("DELETE FROM mp.users WHERE email IN ('alice@asop.test','bob@asop.test')"))
        c.commit()


def _step(num: str, name: str, ok: bool, extra: str = ""):
    mark = "✓" if ok else "✗"
    print(f"  [{mark}] Шаг {num}. {name}{('  (' + extra + ')') if extra else ''}")
    if not ok:
        sys.exit(1)


def _client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def run():
    print("=" * 70)
    print("E2E auth & multi-tenant test — АСОП-Маркет")
    print("=" * 70)

    _cleanup_users()

    # ── A. Гость не имеет доступа ────────────────────────────────────────
    guest = _client()
    r = guest.get("/")
    _step("A1", "Гость на / получает редирект на /login",
          r.status_code == 303 and r.headers.get("location", "").endswith("/login"))
    r = guest.get("/api/results")
    _step("A2", "Гость на /api/results получает редирект на /login",
          r.status_code == 303)
    r = guest.get("/login")
    _step("A3", "GET /login открывается без сессии", r.status_code == 200)

    # ── B. Демо-вход ─────────────────────────────────────────────────────
    demo = _client()
    r = demo.get("/demo")
    _step("B1", "GET /demo создаёт сессию", r.status_code == 303 and "asop_session" in demo.cookies)
    r = demo.get("/api/results")
    n_demo = len(r.json())
    _step("B2", "Демо видит свои данные", r.status_code == 200 and n_demo >= 7,
          f"results={n_demo}")
    r = demo.get("/")
    _step("B3", "Демо-главная рендерится с данными",
          r.status_code == 200 and "Демо" in r.text)

    # ── C. Регистрация Алисы ─────────────────────────────────────────────
    alice = _client()
    r = alice.post("/register", data={"email": ALICE[0], "password": ALICE[1], "password2": ALICE[1], "display_name": ALICE[2]})
    _step("C1", "Регистрация Алисы",
          r.status_code == 303 and "asop_session" in alice.cookies)
    r = alice.get("/api/results")
    _step("C2", "Алиса не видит чужих данных",
          r.status_code == 200 and len(r.json()) == 0,
          f"results={len(r.json())}")
    r = alice.get("/api/products")
    _step("C3", "У Алисы 0 товаров", r.status_code == 200 and len(r.json()) == 0)

    # ── D. Дубль email ───────────────────────────────────────────────────
    dup = _client()
    r = dup.post("/register", data={"email": ALICE[0], "password": "another_pwd_999", "password2": "another_pwd_999", "display_name": "X"})
    _step("D1", "Повторная регистрация на тот же email отклоняется",
          r.status_code == 400 and "уже существует" in r.text)

    # ── E. Выход и обратный вход ─────────────────────────────────────────
    r = alice.get("/logout")
    _step("E1", "Logout очищает сессию", r.status_code == 303)
    r = alice.get("/api/results")
    _step("E2", "После logout API недоступен", r.status_code == 303)

    relog = _client()
    r = relog.post("/login", data={"email": ALICE[0], "password": ALICE[1]})
    _step("E3", "Повторный логин с правильным паролем",
          r.status_code == 303 and "asop_session" in relog.cookies)

    wrong = _client()
    r = wrong.post("/login", data={"email": ALICE[0], "password": "wrong"})
    _step("E4", "Логин с неправильным паролем отклоняется",
          r.status_code == 401 and "неверный" in r.text.lower())

    # ── F. Алиса добавляет товар ─────────────────────────────────────────
    r = relog.post("/optimize", data={
        "sku": "SHARED-SKU-001", "name": "Тестовый коврик Алисы",
        "category_code": "sport-fitness",
        "weight_kg": "1.2", "volume_l": "8.0", "cost_rub": "650", "promo_rub": "0",
    })
    _step("F1", "Алиса создаёт товар", r.status_code == 200)
    r = relog.get("/api/products")
    alice_skus = {p["sku"] for p in r.json()}
    _step("F2", "Товар Алисы виден ей",
          r.status_code == 200 and "SHARED-SKU-001" in alice_skus)

    # ── G. Изоляция: Боб не видит товар Алисы ────────────────────────────
    bob = _client()
    r = bob.post("/register", data={"email": BOB[0], "password": BOB[1], "password2": BOB[1], "display_name": BOB[2]})
    _step("G1", "Регистрация Боба",
          r.status_code == 303 and "asop_session" in bob.cookies)
    r = bob.get("/api/products")
    bob_skus = {p["sku"] for p in r.json()}
    _step("G2", "Боб не видит товара Алисы",
          r.status_code == 200 and "SHARED-SKU-001" not in bob_skus,
          f"bob_skus={bob_skus}")

    # ── H. Боб создаёт товар с ТЕМ ЖЕ SKU — должно сработать ─────────────
    r = bob.post("/optimize", data={
        "sku": "SHARED-SKU-001", "name": "Тестовый коврик Боба",
        "category_code": "sport-fitness",
        "weight_kg": "0.9", "volume_l": "6.0", "cost_rub": "500", "promo_rub": "0",
    })
    _step("H1", "Боб создаёт свой товар с тем же SKU", r.status_code == 200)
    r = bob.get("/api/products")
    bob_products = [p for p in r.json() if p["sku"] == "SHARED-SKU-001"]
    _step("H2", "Боб видит СВОЙ SHARED-SKU-001 с его названием",
          len(bob_products) == 1 and "Боба" in bob_products[0]["product_name"],
          f"name={bob_products[0]['product_name'] if bob_products else '?'}")

    # ── I. Боб не может удалить товар Алисы ──────────────────────────────
    # Бобовский /delete удалит его собственный SHARED-SKU-001
    r = bob.post("/delete", data={"sku": "SHARED-SKU-001"})
    _step("I1", "Боб удаляет СВОЙ товар", r.status_code == 200)
    r = bob.get("/api/products")
    bob_after = [p for p in r.json() if p["sku"] == "SHARED-SKU-001"]
    _step("I2", "У Боба товара больше нет", len(bob_after) == 0)

    r = relog.get("/api/products")
    alice_after = [p for p in r.json() if p["sku"] == "SHARED-SKU-001"]
    _step("I3", "У Алисы товар всё ещё на месте",
          len(alice_after) == 1 and "Алисы" in alice_after[0]["product_name"])

    # ── J. Демо-данные не пострадали ─────────────────────────────────────
    r = demo.get("/api/results")
    _step("J1", "Демо-данные не пострадали",
          r.status_code == 200 and len(r.json()) == n_demo,
          f"было {n_demo}, стало {len(r.json())}")

    # ── K. Алиса видит ★ best на своём товаре (без истории — нет) ────────
    r = relog.get("/api/results")
    _step("K1", "Алиса видит свои результаты (0 без истории продаж)",
          r.status_code == 200 and len(r.json()) == 0,
          f"results={len(r.json())}")

    # ── Z. Финальная очистка ─────────────────────────────────────────────
    _cleanup_users()
    print()
    print("=" * 70)
    print("✓ Все шаги auth & isolation прошли успешно.")
    print("=" * 70)


if __name__ == "__main__":
    run()
