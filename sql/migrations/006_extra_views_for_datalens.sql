BEGIN;
SET search_path TO mp, public;

DROP VIEW IF EXISTS mp.v_price_structure_long      CASCADE;
DROP VIEW IF EXISTS mp.v_sensitivity_delta         CASCADE;

CREATE VIEW mp.v_price_structure_long AS
SELECT sku, product_name, marketplace_code, marketplace_name, scheme, s_opt,
       'Себестоимость'                AS component, unit_cost          AS amount_rub, 1 AS component_sort
  FROM mp.v_price_structure_rub
UNION ALL
SELECT sku, product_name, marketplace_code, marketplace_name, scheme, s_opt,
       'Комиссия маркетплейса'         AS component, commission_rub    AS amount_rub, 2 AS component_sort
  FROM mp.v_price_structure_rub
UNION ALL
SELECT sku, product_name, marketplace_code, marketplace_name, scheme, s_opt,
       'Другие проценты'              AS component, other_percent_rub  AS amount_rub, 3 AS component_sort
  FROM mp.v_price_structure_rub
UNION ALL
SELECT sku, product_name, marketplace_code, marketplace_name, scheme, s_opt,
       'Фиксированные доплаты'        AS component, fixed_extras_rub   AS amount_rub, 4 AS component_sort
  FROM mp.v_price_structure_rub
UNION ALL
SELECT sku, product_name, marketplace_code, marketplace_name, scheme, s_opt,
       'Прибыль'                      AS component, profit_per_unit    AS amount_rub, 5 AS component_sort
  FROM mp.v_price_structure_rub;

CREATE VIEW mp.v_sensitivity_delta AS
WITH base AS (
    SELECT sku, marketplace_code, scheme, profit AS baseline_profit
      FROM mp.v_sensitivity
     WHERE scenario = 'baseline'
)
SELECT s.sku, s.product_name, s.marketplace_code, s.scheme, s.is_best,
       s.scenario, s.profit,
       s.profit - b.baseline_profit AS profit_delta
  FROM mp.v_sensitivity s
  JOIN base b USING (sku, marketplace_code, scheme);

COMMIT;
