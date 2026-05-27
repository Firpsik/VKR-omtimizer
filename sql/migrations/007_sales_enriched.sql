BEGIN;
SET search_path TO mp, public;

DROP VIEW IF EXISTS mp.v_sales_enriched CASCADE;

CREATE VIEW mp.v_sales_enriched AS
SELECT sh.sale_id,
       sh.obs_date,
       p.product_id, p.sku, p.name AS product_name,
       m.marketplace_id, m.code AS marketplace_code, m.name AS marketplace_name,
       sh.price_rub, sh.qty, sh.is_promo, sh.stock_qty
  FROM mp.sales_history sh
  JOIN mp.products    p ON p.product_id     = sh.product_id
  JOIN mp.marketplaces m ON m.marketplace_id = sh.marketplace_id;

COMMENT ON VIEW mp.v_sales_enriched IS
'sales_history + имена товара/МП — для удобного фильтра в DataLens.';

COMMIT;
