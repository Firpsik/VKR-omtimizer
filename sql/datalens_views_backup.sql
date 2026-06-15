-- v_sales_enriched
CREATE OR REPLACE VIEW mp.v_sales_enriched AS
 SELECT p.user_id,
    sh.sale_id,
    sh.obs_date,
    p.product_id,
    p.sku,
    p.name AS product_name,
    m.marketplace_id,
    m.code AS marketplace_code,
    m.name AS marketplace_name,
    sh.price_rub,
    sh.qty,
    sh.is_promo,
    sh.stock_qty
   FROM mp.sales_history sh
     JOIN mp.products p ON p.product_id = sh.product_id
     JOIN mp.marketplaces m ON m.marketplace_id = sh.marketplace_id;;

-- v_demand_curves
CREATE OR REPLACE VIEW mp.v_demand_curves AS
 SELECT d.user_id,
    d.sku,
    d.product_name,
    d.marketplace_code,
    d.marketplace_name,
    d.scheme,
    d.a_coef,
    d.b_coef,
    d.r2,
    d.m_coef,
    d.c_total_rub,
    d.s_opt,
    d.q_opt,
    d.profit_opt,
    d.p_min,
    d.p_max,
    d.is_best,
    round(d.p_min + (d.p_max - d.p_min) * gs.i::numeric / 20.0, 2) AS price,
    round(GREATEST(d.a_coef - d.b_coef * (d.p_min + (d.p_max - d.p_min) * gs.i::numeric / 20.0), 0::numeric), 2) AS demand,
    round(d.m_coef * GREATEST(d.a_coef - d.b_coef * (d.p_min + (d.p_max - d.p_min) * gs.i::numeric / 20.0), 0::numeric) * (d.p_min + (d.p_max - d.p_min) * gs.i::numeric / 20.0 - d.c_total_rub / d.m_coef), 2) AS profit_at_price
   FROM mp.v_dashboard d
     CROSS JOIN generate_series(0, 20) gs(i)
  WHERE d.feasible = true;;

-- v_dashboard
CREATE OR REPLACE VIEW mp.v_dashboard AS
 SELECT p.user_id,
    p.product_id,
    p.sku,
    p.name AS product_name,
    p.weight_kg,
    p.volume_l,
    p.cost_rub,
    cc.code AS category_code,
    cc.name AS category_name,
    cg.code AS group_code,
    cg.name AS group_name,
    m.marketplace_id,
    m.code AS marketplace_code,
    m.name AS marketplace_name,
    ue.scheme,
    ue.tariff_rule_id,
    ue.m_coef,
    ue.c_total_rub,
    ue.alpha_total,
    ue.alpha_commission,
    dp.a_coef,
    dp.b_coef,
    dp.a_low,
    dp.a_high,
    dp.b_low,
    dp.b_high,
    dp.r2,
    dp.n_obs,
    dp.source AS demand_source,
    dp.reliable AS demand_reliable,
    dp.message AS demand_message,
    opt.p_min,
    opt.p_max,
    opt.s_opt,
    opt.q_opt,
    opt.profit_opt,
    opt.feasible,
    opt.is_best,
    opt.computed_at
   FROM mp.products p
     JOIN mp.canonical_categories cc ON cc.canonical_category_id = p.canonical_category_id
     JOIN mp.canonical_groups cg ON cg.canonical_group_id = cc.canonical_group_id
     JOIN mp.unit_economics ue ON ue.product_id = p.product_id
     JOIN mp.marketplaces m ON m.marketplace_id = ue.marketplace_id
     LEFT JOIN mp.demand_params dp ON dp.product_id = p.product_id AND dp.marketplace_id = ue.marketplace_id
     LEFT JOIN mp.optimization_results opt ON opt.product_id = p.product_id AND opt.marketplace_id = ue.marketplace_id AND opt.scheme::text = ue.scheme::text;;

-- v_price_structure_long
CREATE OR REPLACE VIEW mp.v_price_structure_long AS
 SELECT v_price_structure_rub.user_id,
    v_price_structure_rub.sku,
    v_price_structure_rub.product_name,
    v_price_structure_rub.marketplace_code,
    v_price_structure_rub.marketplace_name,
    v_price_structure_rub.scheme,
    v_price_structure_rub.s_opt,
    'Себестоимость'::text AS component,
    v_price_structure_rub.unit_cost AS amount_rub,
    1 AS component_sort
   FROM mp.v_price_structure_rub
UNION ALL
 SELECT v_price_structure_rub.user_id,
    v_price_structure_rub.sku,
    v_price_structure_rub.product_name,
    v_price_structure_rub.marketplace_code,
    v_price_structure_rub.marketplace_name,
    v_price_structure_rub.scheme,
    v_price_structure_rub.s_opt,
    'Комиссия маркетплейса'::text AS component,
    v_price_structure_rub.commission_rub AS amount_rub,
    2 AS component_sort
   FROM mp.v_price_structure_rub
UNION ALL
 SELECT v_price_structure_rub.user_id,
    v_price_structure_rub.sku,
    v_price_structure_rub.product_name,
    v_price_structure_rub.marketplace_code,
    v_price_structure_rub.marketplace_name,
    v_price_structure_rub.scheme,
    v_price_structure_rub.s_opt,
    'Другие проценты'::text AS component,
    v_price_structure_rub.other_percent_rub AS amount_rub,
    3 AS component_sort
   FROM mp.v_price_structure_rub
UNION ALL
 SELECT v_price_structure_rub.user_id,
    v_price_structure_rub.sku,
    v_price_structure_rub.product_name,
    v_price_structure_rub.marketplace_code,
    v_price_structure_rub.marketplace_name,
    v_price_structure_rub.scheme,
    v_price_structure_rub.s_opt,
    'Фиксированные доплаты'::text AS component,
    v_price_structure_rub.fixed_extras_rub AS amount_rub,
    4 AS component_sort
   FROM mp.v_price_structure_rub
UNION ALL
 SELECT v_price_structure_rub.user_id,
    v_price_structure_rub.sku,
    v_price_structure_rub.product_name,
    v_price_structure_rub.marketplace_code,
    v_price_structure_rub.marketplace_name,
    v_price_structure_rub.scheme,
    v_price_structure_rub.s_opt,
    'Прибыль'::text AS component,
    v_price_structure_rub.profit_per_unit AS amount_rub,
    5 AS component_sort
   FROM mp.v_price_structure_rub;;

-- v_sensitivity_delta
CREATE OR REPLACE VIEW mp.v_sensitivity_delta AS
 WITH base AS (
         SELECT v_sensitivity.user_id,
            v_sensitivity.sku,
            v_sensitivity.marketplace_code,
            v_sensitivity.scheme,
            v_sensitivity.profit AS baseline_profit
           FROM mp.v_sensitivity
          WHERE v_sensitivity.scenario = 'baseline'::text
        )
 SELECT s.user_id,
    s.sku,
    s.product_name,
    s.marketplace_code,
    s.scheme,
    s.is_best,
    s.scenario,
    s.profit,
    s.profit - b.baseline_profit AS profit_delta
   FROM mp.v_sensitivity s
     JOIN base b USING (user_id, sku, marketplace_code, scheme);;
