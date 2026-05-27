BEGIN;
SET search_path TO mp, public;

ALTER TABLE mp.products ALTER COLUMN category_id DROP NOT NULL;

COMMIT;
