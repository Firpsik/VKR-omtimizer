from sqlalchemy import text

from src.core.demand_estimation import MIN_N_OBS, fit_linear_demand
from src.db import get_engine

_LOG_PREFIX = "[optimize]"

def optimize_all() -> dict:
    engine = get_engine()
    n_pairs = 0
    n_feasible = 0
    n_skipped = 0
    n_infeasible = 0

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE mp.optimization_results"))
        conn.execute(text("TRUNCATE mp.unit_economics"))
        conn.execute(text("TRUNCATE mp.demand_params"))

        product_mp_pairs = conn.execute(text("""
            SELECT DISTINCT product_id, marketplace_id
              FROM mp.v_unit_economics
        """)).fetchall()
        demand_cache: dict[tuple[int, int], dict] = {}
        for pid, mid in product_mp_pairs:
            sales = conn.execute(text("""
                SELECT price_rub, qty, is_promo, stock_qty
                  FROM mp.sales_history
                 WHERE product_id = :pid AND marketplace_id = :mid
                 ORDER BY obs_date
            """), {"pid": pid, "mid": mid}).fetchall()
            if len(sales) < MIN_N_OBS:
                continue
            est = fit_linear_demand(
                prices=[float(s[0]) for s in sales],
                quantities=[float(s[1]) for s in sales],
                is_promo=[bool(s[2]) for s in sales],
                stock_qty=[float(s[3]) for s in sales],
            )
            if est is None or est.b <= 0 or est.a <= 0:
                continue
            demand_cache[(pid, mid)] = est
            conn.execute(text("""
                INSERT INTO mp.demand_params
                    (product_id, marketplace_id, a_coef, b_coef,
                     a_low, a_high, b_low, b_high, r2, n_obs,
                     source, reliable, message)
                VALUES (:pid, :mid, :a, :b, :al, :ah, :bl, :bh,
                        :r2, :n, :src, :rel, :msg)
                ON CONFLICT (product_id, marketplace_id) DO UPDATE
                    SET a_coef = EXCLUDED.a_coef,
                        b_coef = EXCLUDED.b_coef,
                        a_low = EXCLUDED.a_low,
                        a_high = EXCLUDED.a_high,
                        b_low = EXCLUDED.b_low,
                        b_high = EXCLUDED.b_high,
                        r2 = EXCLUDED.r2,
                        n_obs = EXCLUDED.n_obs,
                        source = EXCLUDED.source,
                        reliable = EXCLUDED.reliable,
                        message = EXCLUDED.message,
                        computed_at = now()
            """), {
                "pid": pid, "mid": mid,
                "a": est.a, "b": est.b,
                "al": est.a_low, "ah": est.a_high,
                "bl": est.b_low, "bh": est.b_high,
                "r2": est.r2, "n": est.n_obs,
                "src": est.source, "rel": est.reliable,
                "msg": est.message,
            })

        rows = conn.execute(text("""
            SELECT tariff_rule_id, marketplace_id, product_id, scheme,
                   m, fixed_costs, alpha_total, commission_pct
              FROM mp.v_unit_economics
             ORDER BY product_id, marketplace_id, scheme
        """)).fetchall()

        per_product: dict[int, list[dict]] = {}

        for r in rows:
            n_pairs += 1
            (tariff_rule_id, mid, pid, scheme,
             m, c, alpha_total, commission_pct) = r
            m, c = float(m), float(c)
            alpha_total = float(alpha_total)
            commission_pct = float(commission_pct)

            est = demand_cache.get((pid, mid))
            if est is None:
                n_skipped += 1
                continue
            a, b = est.a, est.b

            conn.execute(text("""
                INSERT INTO mp.unit_economics
                    (product_id, marketplace_id, scheme, tariff_rule_id,
                     m_coef, c_total_rub, alpha_total, alpha_commission)
                VALUES (:pid, :mid, :sch, :trid, :m, :c, :a, :ac)
            """), {"pid": pid, "mid": mid, "sch": scheme,
                    "trid": tariff_rule_id,
                    "m": m, "c": c,
                    "a": alpha_total, "ac": commission_pct})

            feasible = (m > 0) and (a / b > c / m)
            if not feasible:
                n_infeasible += 1
                conn.execute(text("""
                    INSERT INTO mp.optimization_results
                        (product_id, marketplace_id, scheme,
                         p_min, p_max, s_opt, q_opt, profit_opt,
                         feasible, is_best)
                    VALUES (:pid, :mid, :sch,
                            :pmin, :pmax, NULL, NULL, NULL,
                            FALSE, FALSE)
                """), {
                    "pid": pid, "mid": mid, "sch": scheme,
                    "pmin": c / m if m > 0 else None,
                    "pmax": a / b,
                })
                continue

            s_star = 0.5 * (a / b + c / m)
            q_star = max(0.0, a - b * s_star)
            profit = (m * s_star - c) * q_star

            conn.execute(text("""
                INSERT INTO mp.optimization_results
                    (product_id, marketplace_id, scheme,
                     p_min, p_max, s_opt, q_opt, profit_opt,
                     feasible, is_best)
                VALUES (:pid, :mid, :sch,
                        :pmin, :pmax, :s, :q, :p,
                        TRUE, FALSE)
            """), {
                "pid": pid, "mid": mid, "sch": scheme,
                "pmin": c / m, "pmax": a / b,
                "s": s_star, "q": q_star, "p": profit,
            })

            n_feasible += 1
            per_product.setdefault(pid, []).append({
                "mid": mid, "scheme": scheme, "profit": profit,
            })

        for pid, results in per_product.items():
            best = max(results, key=lambda x: x["profit"])
            conn.execute(text("""
                UPDATE mp.optimization_results
                   SET is_best = TRUE
                 WHERE product_id = :pid
                   AND marketplace_id = :mid
                   AND scheme = :sch
            """), {"pid": pid, "mid": best["mid"], "sch": best["scheme"]})

    summary = {
        "n_pairs": n_pairs,
        "n_feasible": n_feasible,
        "n_infeasible": n_infeasible,
        "n_skipped_no_demand": n_skipped,
    }
    print(f"{_LOG_PREFIX} {summary}")
    return summary

if __name__ == "__main__":
    optimize_all()
