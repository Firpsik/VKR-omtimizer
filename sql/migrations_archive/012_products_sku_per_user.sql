BEGIN;
SET search_path TO mp, public;

ALTER TABLE mp.products DROP CONSTRAINT IF EXISTS products_sku_key;
ALTER TABLE mp.products DROP CONSTRAINT IF EXISTS products_sku_user_key;
ALTER TABLE mp.products
    ADD CONSTRAINT products_sku_user_key UNIQUE (sku, user_id);

COMMIT;
