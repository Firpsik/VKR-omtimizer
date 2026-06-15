BEGIN;
SET search_path TO mp, public;

ALTER TABLE mp.product_overrides
    ADD COLUMN IF NOT EXISTS packaging_fee_rub NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS cofinance_pct NUMERIC(6,4);

COMMIT;
