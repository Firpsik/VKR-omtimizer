BEGIN;
SET search_path TO mp, public;

DROP VIEW IF EXISTS mp.v_sensitivity         CASCADE;
DROP VIEW IF EXISTS mp.v_price_structure_rub CASCADE;
DROP VIEW IF EXISTS mp.v_demand_curves       CASCADE;
DROP VIEW IF EXISTS mp.v_best                CASCADE;
DROP VIEW IF EXISTS mp.v_dashboard           CASCADE;

CREATE VIEW mp.v_dashboard AS
SELECT
    p.product_id,
    p.sku,
    p.name              AS product_name,
    p.weight_kg,
    p.volume_l,
    p.cost_rub,
    cc.code             AS category_code,
    cc.name             AS category_name,
    cg.code             AS group_code,
    cg.name             AS group_name,
    m.marketplace_id,
    m.code              AS marketplace_code,
    m.name              AS marketplace_name,
    ue.scheme,
    ue.tariff_rule_id,
    ue.m_coef,
    ue.c_total_rub,
    ue.alpha_total,
    ue.alpha_commission,
    dp.a_coef, dp.b_coef,
    dp.a_low, dp.a_high, dp.b_low, dp.b_high,
    dp.r2, dp.n_obs,
    dp.source           AS demand_source,
    dp.reliable         AS demand_reliable,
    dp.message          AS demand_message,
    opt.p_min, opt.p_max,
    opt.s_opt, opt.q_opt, opt.profit_opt,
    opt.feasible, opt.is_best,
    opt.computed_at
FROM mp.products p
JOIN mp.canonical_categories cc ON cc.canonical_category_id = p.canonical_category_id
JOIN mp.canonical_groups cg     ON cg.canonical_group_id = cc.canonical_group_id
JOIN mp.unit_economics ue       ON ue.product_id = p.product_id
JOIN mp.marketplaces m          ON m.marketplace_id = ue.marketplace_id
LEFT JOIN mp.demand_params dp   ON dp.product_id = p.product_id
                               AND dp.marketplace_id = ue.marketplace_id
LEFT JOIN mp.optimization_results opt
       ON opt.product_id = p.product_id
      AND opt.marketplace_id = ue.marketplace_id
      AND opt.scheme = ue.scheme;
COMMENT ON VIEW mp.v_dashboard IS
'Главная плоская витрина: товар × МП × схема с экономикой, спросом и оптимумом.';

CREATE VIEW mp.v_best AS
SELECT * FROM mp.v_dashboard WHERE is_best = TRUE;
COMMENT ON VIEW mp.v_best IS
'Подмножество v_dashboard: только победившие пары (товар × МП × схема).';

CREATE VIEW mp.v_demand_curves AS
SELECT
    d.sku,
    d.product_name,
    d.marketplace_code,
    d.marketplace_name,
    d.scheme,
    d.a_coef, d.b_coef, d.r2,
    d.m_coef, d.c_total_rub,
    d.s_opt, d.q_opt, d.profit_opt,
    d.p_min, d.p_max,
    d.is_best,
    ROUND((d.p_min + (d.p_max - d.p_min) * gs.i / 20.0)::numeric, 2)
                        AS price,
    ROUND(GREATEST(
        d.a_coef - d.b_coef * (d.p_min + (d.p_max - d.p_min) * gs.i / 20.0),
        0)::numeric, 2)  AS demand,
    ROUND((
        d.m_coef
        * GREATEST(d.a_coef - d.b_coef * (d.p_min + (d.p_max - d.p_min) * gs.i / 20.0), 0)
        * ((d.p_min + (d.p_max - d.p_min) * gs.i / 20.0) - d.c_total_rub / d.m_coef)
    )::numeric, 2)       AS profit_at_price
FROM mp.v_dashboard d
CROSS JOIN generate_series(0, 20) AS gs(i)
WHERE d.feasible = TRUE;
COMMENT ON VIEW mp.v_demand_curves IS
'21 точка кривой спроса и прибыли для line-chart в DataLens.';

CREATE VIEW mp.v_price_structure_rub AS
SELECT
    d.sku, d.product_name,
    d.marketplace_code, d.marketplace_name, d.scheme,
    d.s_opt,
    d.cost_rub                                       AS unit_cost,
    ROUND((d.alpha_commission * d.s_opt)::numeric, 2) AS commission_rub,
    ROUND(((d.alpha_total - d.alpha_commission) * d.s_opt)::numeric, 2)
                                                     AS other_percent_rub,
    ROUND((d.c_total_rub - d.cost_rub)::numeric, 2)  AS fixed_extras_rub,
    ROUND((d.m_coef * d.s_opt - d.c_total_rub)::numeric, 2)
                                                     AS profit_per_unit
FROM mp.v_dashboard d
WHERE d.feasible = TRUE;
COMMENT ON VIEW mp.v_price_structure_rub IS
'Структура цены при s* — для столбчатой диаграммы. Колонки: себестоимость, комиссия, прочие %, фиксированные, прибыль.';

CREATE VIEW mp.v_sensitivity AS
WITH base AS (
    SELECT sku, product_name, marketplace_code, scheme,
           a_coef, b_coef, m_coef, c_total_rub, profit_opt, is_best
      FROM mp.v_dashboard
     WHERE feasible = TRUE
)
SELECT
    sku, product_name, marketplace_code, scheme, is_best,
    'baseline'           AS scenario,
    profit_opt           AS profit
FROM base
UNION ALL
SELECT
    sku, product_name, marketplace_code, scheme, is_best,
    'a +10%' AS scenario,
    ROUND(((m_coef * b_coef) / 4.0
        * POWER((a_coef * 1.1) / b_coef - c_total_rub / m_coef, 2))::numeric, 2)
FROM base
UNION ALL
SELECT
    sku, product_name, marketplace_code, scheme, is_best,
    'a -10%',
    ROUND(((m_coef * b_coef) / 4.0
        * POWER((a_coef * 0.9) / b_coef - c_total_rub / m_coef, 2))::numeric, 2)
FROM base
UNION ALL
SELECT
    sku, product_name, marketplace_code, scheme, is_best,
    'b +10%',
    ROUND(((m_coef * (b_coef * 1.1)) / 4.0
        * POWER(a_coef / (b_coef * 1.1) - c_total_rub / m_coef, 2))::numeric, 2)
FROM base
UNION ALL
SELECT
    sku, product_name, marketplace_code, scheme, is_best,
    'b -10%',
    ROUND(((m_coef * (b_coef * 0.9)) / 4.0
        * POWER(a_coef / (b_coef * 0.9) - c_total_rub / m_coef, 2))::numeric, 2)
FROM base;
COMMENT ON VIEW mp.v_sensitivity IS
'Чувствительность П* к возмущениям параметров спроса (±10%).';

COMMIT;
