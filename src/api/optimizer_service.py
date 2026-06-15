from sqlalchemy import text

from src.core.demand_estimation import MIN_N_OBS, fit_linear_demand
from src.db import get_engine
from src.etl.sales_adapters import AdapterError, detect_adapter, parse_report


def get_references() -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        cats = conn.execute(text("""
            SELECT cc.code, cc.name, cg.name AS group_name
              FROM mp.canonical_categories cc
              JOIN mp.canonical_groups cg ON cg.canonical_group_id = cc.canonical_group_id
             ORDER BY cg.sort_order, cc.sort_order, cc.name
        """)).fetchall()
        mps = conn.execute(text("SELECT code, name FROM mp.marketplaces ORDER BY name")).fetchall()
    return {
        "categories": [{"code": r[0], "name": r[1], "group": r[2]} for r in cats],
        "marketplaces": [{"code": r[0], "name": r[1]} for r in mps],
    }


def list_canonical_groups() -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT g.code AS group_code, g.name AS group_name, g.sort_order,
                   COUNT(c.canonical_category_id) AS n_categories
              FROM mp.canonical_groups g
         LEFT JOIN mp.canonical_categories c ON c.canonical_group_id = g.canonical_group_id
          GROUP BY g.canonical_group_id
          ORDER BY g.sort_order, g.name
        """)).fetchall()
    return [{"group_code": r[0], "group_name": r[1], "sort_order": r[2], "n_categories": int(r[3])} for r in rows]


def list_canonical_categories_full() -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT c.code, c.name, g.code AS group_code, g.name AS group_name,
                   c.requires_marking, c.marking_cost_per_unit_rub, c.sort_order
              FROM mp.canonical_categories c
              JOIN mp.canonical_groups g ON g.canonical_group_id = c.canonical_group_id
          ORDER BY g.sort_order, c.sort_order, c.name
        """)).fetchall()
    return [{
        "code": r[0], "name": r[1],
        "group_code": r[2], "group_name": r[3],
        "requires_marking": bool(r[4]),
        "marking_cost_per_unit_rub": float(r[5] or 0),
        "sort_order": int(r[6] or 0),
    } for r in rows]


def get_all_results(user_id: int) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT sku, product_name, marketplace_name, scheme,
                   alpha_total, alpha_commission, m_coef, c_total_rub,
                   cost_rub,
                   s_opt, q_opt, profit_opt, is_best,
                   r2, n_obs, demand_source, demand_reliable, demand_message,
                   category_name, group_name
              FROM mp.v_dashboard
             WHERE feasible = TRUE AND user_id = :uid
             ORDER BY product_name, profit_opt DESC
        """), {"uid": user_id}).fetchall()
    return [
        {
            "sku": r[0], "product_name": r[1], "marketplace_name": r[2],
            "scheme": r[3],
            "alpha_total": _to_float(r[4]), "alpha_commission": _to_float(r[5]),
            "m_coef": _to_float(r[6]), "c_total_rub": _to_float(r[7]),
            "cost_rub": _to_float(r[8]),
            "s_opt": _to_float(r[9]), "q_opt": _to_float(r[10]),
            "profit_opt": _to_float(r[11]), "is_best": bool(r[12]),
            "r2": _to_float(r[13]),
            "n_obs": int(r[14]) if r[14] is not None else 0,
            "demand_source": r[15] or "ols",
            "demand_reliable": bool(r[16]) if r[16] is not None else False,
            "demand_message": r[17] or "",
            "category_name": r[18], "group_name": r[19],
        }
        for r in rows
    ]


def get_orphan_products(user_id: int) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.sku, p.name, cc.name AS cat_name
              FROM mp.products p
         LEFT JOIN mp.canonical_categories cc ON cc.canonical_category_id = p.canonical_category_id
         LEFT JOIN mp.optimization_results o ON o.product_id = p.product_id
             WHERE o.product_id IS NULL AND p.user_id = :uid
             ORDER BY p.product_id
        """), {"uid": user_id}).fetchall()
    return [{"sku": r[0], "product_name": r[1], "category_name": r[2]} for r in rows]


def list_all_products(user_id: int) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.sku, p.name AS product_name,
                   EXISTS(SELECT 1 FROM mp.sales_history sh WHERE sh.product_id = p.product_id) AS has_history
              FROM mp.products p
             WHERE p.user_id = :uid
             ORDER BY has_history ASC, p.name ASC
        """), {"uid": user_id}).fetchall()
    return [{"sku": r[0], "product_name": r[1], "has_history": bool(r[2])} for r in rows]


def delete_product(sku: str, user_id: int) -> dict:
    engine = get_engine()
    with engine.begin() as conn:
        pid = _resolve_product_id(conn, sku, user_id, raise_=False)
        if pid is None:
            return {"deleted": False, "reason": "not_found"}
        conn.execute(text("DELETE FROM mp.optimization_results WHERE product_id=:p"), {"p": pid})
        conn.execute(text("DELETE FROM mp.demand_params        WHERE product_id=:p"), {"p": pid})
        conn.execute(text("DELETE FROM mp.unit_economics       WHERE product_id=:p"), {"p": pid})
        conn.execute(text("DELETE FROM mp.sales_history        WHERE product_id=:p"), {"p": pid})
        conn.execute(text("DELETE FROM mp.products             WHERE product_id=:p"), {"p": pid})
    return {"deleted": True}


def optimize_single_product(
    sku: str, name: str, category_code: str,
    weight_kg: float, volume_l: float, cost_rub: float, promo_rub: float,
    user_id: int,
    overrides: dict | None = None,
    override_marketplace_code: str = "wb",
    stock_qty_limit: int | None = None,
) -> dict:
    engine = get_engine()
    with engine.begin() as conn:
        ccid = conn.execute(text(
            "SELECT canonical_category_id FROM mp.canonical_categories WHERE code=:c"
        ), {"c": category_code}).fetchone()
        if ccid is None:
            raise ValueError(f"Канонической категории '{category_code}' нет")
        ccid = ccid[0]

        row = conn.execute(text("""
            INSERT INTO mp.products (sku, name, canonical_category_id,
                                     weight_kg, volume_l, cost_rub, promo_rub, user_id)
            VALUES (:sku, :n, :c, :w, :v, :cost, :promo, :uid)
            ON CONFLICT (sku, user_id) DO UPDATE SET
                name = EXCLUDED.name,
                canonical_category_id = EXCLUDED.canonical_category_id,
                weight_kg = EXCLUDED.weight_kg,
                volume_l = EXCLUDED.volume_l,
                cost_rub = EXCLUDED.cost_rub,
                promo_rub = EXCLUDED.promo_rub
            RETURNING product_id
        """), {"sku": sku, "n": name, "c": ccid, "w": weight_kg, "v": volume_l,
                "cost": cost_rub, "promo": promo_rub, "uid": user_id}).fetchone()
        pid = int(row[0])

        if overrides:
            mapped: dict = {}
            if overrides.get("return_rate") not in (None, ""):
                mapped["return_rate"] = float(overrides["return_rate"])
            if overrides.get("storage_days") not in (None, ""):
                mapped["storage_days"] = int(overrides["storage_days"])
            if overrides.get("ktr") not in (None, ""):
                mapped["ktr"] = float(overrides["ktr"])
            if overrides.get("kwh") not in (None, ""):
                mapped["warehouse_coef"] = float(overrides["kwh"])
            if overrides.get("promo_pct") not in (None, ""):
                mapped["promo_pct"] = float(overrides["promo_pct"])
            if overrides.get("packaging_fee_rub") not in (None, ""):
                mapped["packaging_fee_rub"] = float(overrides["packaging_fee_rub"])
            if overrides.get("cofinance_pct") not in (None, ""):
                mapped["cofinance_pct"] = float(overrides["cofinance_pct"])
            if mapped:
                cols = ", ".join(mapped.keys())
                placeholders = ", ".join(f":{k}" for k in mapped.keys())
                updates = ", ".join(f"{k}=EXCLUDED.{k}" for k in mapped.keys())
                marketplace_id = conn.execute(text(
                    "SELECT marketplace_id FROM mp.marketplaces WHERE code = :c"
                ), {"c": override_marketplace_code}).scalar_one()
                conn.execute(text(f"""
                    INSERT INTO mp.product_overrides (product_id, marketplace_id, {cols}, updated_at)
                    VALUES (:pid, :mid, {placeholders}, now())
                    ON CONFLICT (product_id, marketplace_id) DO UPDATE SET {updates}, updated_at = now()
                """), {"pid": pid, "mid": marketplace_id, **mapped})

    return _recompute_for_product(pid, stock_qty_limit=stock_qty_limit)


def recompute_optimization(sku: str, user_id: int) -> dict:
    engine = get_engine()
    with engine.begin() as conn:
        pid = _resolve_product_id(conn, sku, user_id)
    return _recompute_for_product(pid)


def _recompute_for_product(pid: int, stock_qty_limit: int | None = None) -> dict:
    engine = get_engine()
    n_pairs = 0
    n_feasible = 0
    per_results = []

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mp.optimization_results WHERE product_id=:p"), {"p": pid})
        conn.execute(text("DELETE FROM mp.demand_params        WHERE product_id=:p"), {"p": pid})
        conn.execute(text("DELETE FROM mp.unit_economics       WHERE product_id=:p"), {"p": pid})

        mp_pairs = conn.execute(text("""
            SELECT DISTINCT marketplace_id FROM mp.v_unit_economics WHERE product_id=:p
        """), {"p": pid}).fetchall()
        demand_cache: dict[int, object] = {}
        for (mid,) in mp_pairs:
            sales = conn.execute(text("""
                SELECT price_rub, qty, is_promo, stock_qty
                  FROM mp.sales_history
                 WHERE product_id=:pid AND marketplace_id=:mid
                 ORDER BY obs_date
            """), {"pid": pid, "mid": mid}).fetchall()
            if len(sales) < MIN_N_OBS:
                continue
            est = fit_linear_demand(
                prices=[float(s[0]) for s in sales],
                quantities=[float(s[1]) for s in sales],
                is_promo=[bool(s[2]) for s in sales],
                stock_qty=[float(s[3]) if s[3] is not None else None for s in sales],
            )
            if est is None or est.b <= 0 or est.a <= 0:
                continue
            demand_cache[mid] = est
            conn.execute(text("""
                INSERT INTO mp.demand_params
                    (product_id, marketplace_id, a_coef, b_coef,
                     a_low, a_high, b_low, b_high, r2, n_obs,
                     source, reliable, message)
                VALUES (:pid, :mid, :a, :b, :al, :ah, :bl, :bh, :r2, :n, :src, :rel, :msg)
            """), {"pid": pid, "mid": mid, "a": est.a, "b": est.b,
                    "al": est.a_low, "ah": est.a_high,
                    "bl": est.b_low, "bh": est.b_high,
                    "r2": est.r2, "n": est.n_obs,
                    "src": est.source, "rel": est.reliable, "msg": est.message})

        rows = conn.execute(text("""
            SELECT tariff_rule_id, marketplace_id, scheme, m, fixed_costs, alpha_total, commission_pct
              FROM mp.v_unit_economics WHERE product_id=:p
        """), {"p": pid}).fetchall()

        for r in rows:
            n_pairs += 1
            (trid, mid, scheme, m, c, alpha_total, comm) = r
            m, c, alpha_total, comm = float(m), float(c), float(alpha_total), float(comm)
            conn.execute(text("""
                INSERT INTO mp.unit_economics
                    (product_id, marketplace_id, scheme, tariff_rule_id,
                     m_coef, c_total_rub, alpha_total, alpha_commission)
                VALUES (:p, :m, :s, :t, :mc, :c, :a, :ac)
            """), {"p": pid, "m": mid, "s": scheme, "t": trid,
                    "mc": m, "c": c, "a": alpha_total, "ac": comm})

            est = demand_cache.get(mid)
            if est is None:
                continue
            a, b = est.a, est.b
            feasible = (m > 0) and (a / b > c / m)
            if not feasible:
                conn.execute(text("""
                    INSERT INTO mp.optimization_results
                        (product_id, marketplace_id, scheme, p_min, p_max, feasible, is_best)
                    VALUES (:p, :m, :s, :pmin, :pmax, FALSE, FALSE)
                """), {"p": pid, "m": mid, "s": scheme,
                        "pmin": c / m if m > 0 else None, "pmax": a / b})
                continue
            s_star = 0.5 * (a / b + c / m)
            q_star = max(0.0, a - b * s_star)
            q_used = min(q_star, float(stock_qty_limit)) if stock_qty_limit is not None and stock_qty_limit >= 0 else q_star
            profit = (m * s_star - c) * q_used
            conn.execute(text("""
                INSERT INTO mp.optimization_results
                    (product_id, marketplace_id, scheme,
                     p_min, p_max, s_opt, q_opt, profit_opt, feasible, is_best)
                VALUES (:p, :m, :s, :pmin, :pmax, :ss, :qs, :ps, TRUE, FALSE)
            """), {"p": pid, "m": mid, "s": scheme,
                    "pmin": c / m, "pmax": a / b,
                    "ss": s_star, "qs": q_used, "ps": profit})
            n_feasible += 1
            per_results.append({"mid": mid, "scheme": scheme, "profit": profit})

        if per_results:
            best = max(per_results, key=lambda x: x["profit"])
            conn.execute(text("""
                UPDATE mp.optimization_results SET is_best = TRUE
                 WHERE product_id=:p AND marketplace_id=:m AND scheme=:s
            """), {"p": pid, "m": best["mid"], "s": best["scheme"]})
            best_mp_name = conn.execute(text(
                "SELECT name FROM mp.marketplaces WHERE marketplace_id=:m"
            ), {"m": best["mid"]}).scalar()
            best_profit = best["profit"]
        else:
            best_mp_name = "нет подходящей"
            best_profit = 0.0

    return {
        "product_id": pid, "n_pairs": n_pairs, "n_feasible": n_feasible,
        "best_marketplace": best_mp_name, "best_profit": best_profit,
    }


def upload_marketplace_report(
    csv_text: str, user_id: int,
    marketplace_code: str | None = None,
    sku_override: str | None = None,
    replace: bool = False,
) -> dict:
    if marketplace_code is None:
        adapter = detect_adapter(csv_text)
        if not adapter:
            raise AdapterError("Не удалось определить маркетплейс по структуре CSV")
        mp_code = adapter.marketplace_code
    else:
        mp_code = marketplace_code

    sales = parse_report(csv_text, marketplace_code=mp_code)
    if not sales:
        raise AdapterError("CSV не содержит ни одной валидной строки")
    detected_mp = None
    if marketplace_code is None:
        detected_mp = detect_adapter(csv_text)
        if detected_mp:
            mp_code = detected_mp.marketplace_code

    engine = get_engine()
    inserted, skipped_unknown = 0, 0
    by_sku: dict[str, int] = {}

    with engine.begin() as conn:
        mid = _resolve_marketplace_id(conn, mp_code)
        for obs in sales:
            sku = sku_override or obs.sku
            pid = _resolve_product_id(conn, sku, user_id, raise_=False)
            if pid is None:
                skipped_unknown += 1
                continue
            if replace:
                conn.execute(text("""
                    DELETE FROM mp.sales_history
                     WHERE product_id=:p AND marketplace_id=:m AND obs_date=:d
                """), {"p": pid, "m": mid, "d": obs.obs_date})
            conn.execute(text("""
                INSERT INTO mp.sales_history (product_id, marketplace_id, obs_date,
                                              price_rub, qty, is_promo, stock_qty)
                VALUES (:p, :m, :d, :pr, :q, :ip, :st)
            """), {"p": pid, "m": mid, "d": obs.obs_date,
                    "pr": obs.price_rub, "q": obs.qty,
                    "ip": obs.is_promo, "st": obs.stock_qty})
            inserted += 1
            by_sku[sku] = by_sku.get(sku, 0) + 1

    recomputed = []
    for sku in by_sku:
        try:
            r = recompute_optimization(sku, user_id)
            recomputed.append({"sku": sku, "best": r["best_marketplace"], "profit": r["best_profit"]})
        except Exception:
            pass

    return {
        "marketplace_code": mp_code, "parsed": len(sales),
        "inserted": inserted, "skipped_unknown_sku": skipped_unknown,
        "n_loaded": inserted, "n_skipped": skipped_unknown,
        "by_sku": by_sku, "recomputed_skus": recomputed,
    }


def add_sales_observations(
    sku: str, marketplace_code: str, observations: list[dict],
    user_id: int, replace: bool = False,
) -> dict:
    engine = get_engine()
    inserted, deleted = 0, 0
    with engine.begin() as conn:
        pid = _resolve_product_id(conn, sku, user_id)
        mid = _resolve_marketplace_id(conn, marketplace_code)
        if replace:
            deleted = conn.execute(text("""
                DELETE FROM mp.sales_history WHERE product_id=:p AND marketplace_id=:m
            """), {"p": pid, "m": mid}).rowcount or 0
        for obs in observations:
            d = obs.get("date") or obs.get("obs_date")
            conn.execute(text("""
                INSERT INTO mp.sales_history (product_id, marketplace_id, obs_date,
                                              price_rub, qty, is_promo, stock_qty)
                VALUES (:p, :m, :d, :pr, :q, :ip, :st)
            """), {"p": pid, "m": mid, "d": d,
                    "pr": obs["price_rub"], "q": obs["qty"],
                    "ip": obs.get("is_promo", False),
                    "st": obs.get("stock_qty")})
            inserted += 1
    return {"inserted": inserted, "deleted": deleted, "n_loaded": inserted, "n_skipped": 0}


def delete_sales(sku: str, user_id: int, marketplace_code: str | None = None) -> dict:
    engine = get_engine()
    with engine.begin() as conn:
        pid = _resolve_product_id(conn, sku, user_id)
        if pid is None:
            return {"deleted": 0, "reason": "not_found"}
        if marketplace_code:
            mid = _resolve_marketplace_id(conn, marketplace_code)
            res = conn.execute(text(
                "DELETE FROM mp.sales_history WHERE product_id=:p AND marketplace_id=:m"
            ), {"p": pid, "m": mid})
        else:
            res = conn.execute(text(
                "DELETE FROM mp.sales_history WHERE product_id=:p"
            ), {"p": pid})
        deleted = res.rowcount or 0
    rec = _recompute_for_product(pid)
    return {"deleted": deleted, "recompute": rec}


def get_sales_history(sku: str, user_id: int, marketplace_code: str | None = None) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        pid = _resolve_product_id(conn, sku, user_id)
        query = """
            SELECT s.obs_date, s.price_rub, s.qty, s.is_promo, s.stock_qty, m.code
              FROM mp.sales_history s
              JOIN mp.marketplaces m ON m.marketplace_id = s.marketplace_id
             WHERE s.product_id = :p
        """
        params: dict = {"p": pid}
        if marketplace_code:
            query += " AND m.code = :mc"
            params["mc"] = marketplace_code
        query += " ORDER BY s.obs_date"
        rows = conn.execute(text(query), params).fetchall()
    return [
        {"obs_date": r[0].isoformat(), "price_rub": float(r[1]), "qty": int(r[2]),
         "is_promo": bool(r[3]),
         "stock_qty": int(r[4]) if r[4] is not None else None,
         "marketplace_code": r[5]}
        for r in rows
    ]


def _to_float(value) -> float:
    return float(value) if value is not None else 0.0


def _resolve_marketplace_id(conn, code: str) -> int:
    row = conn.execute(text("SELECT marketplace_id FROM mp.marketplaces WHERE code=:c"), {"c": code}).fetchone()
    if row is None:
        raise ValueError(f"Маркетплейс '{code}' не найден")
    return int(row[0])


def _resolve_product_id(conn, sku: str, user_id: int, raise_: bool = True) -> int | None:
    row = conn.execute(text(
        "SELECT product_id FROM mp.products WHERE sku=:s AND user_id=:u"
    ), {"s": sku, "u": user_id}).fetchone()
    if row is None:
        if raise_:
            raise ValueError(f"Товар '{sku}' не найден")
        return None
    return int(row[0])
