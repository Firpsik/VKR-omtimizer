BEGIN;
SET search_path TO mp, public;

ALTER TABLE mp.product_overrides
    ADD COLUMN IF NOT EXISTS marketplace_id INT REFERENCES mp.marketplaces;

UPDATE mp.product_overrides po
   SET marketplace_id = m.marketplace_id
  FROM mp.marketplaces m
 WHERE po.marketplace_id IS NULL
   AND m.code = 'wb';

ALTER TABLE mp.product_overrides
    ALTER COLUMN marketplace_id SET NOT NULL;

ALTER TABLE mp.product_overrides
    DROP CONSTRAINT IF EXISTS product_overrides_pkey;

ALTER TABLE mp.product_overrides
    ADD CONSTRAINT product_overrides_pkey PRIMARY KEY (product_id, marketplace_id);

COMMIT;
