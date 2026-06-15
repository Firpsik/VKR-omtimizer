BEGIN;
SET search_path TO mp, public;

DROP TABLE IF EXISTS mp.tariff_rule_ozon_logistics_tier;
DROP TABLE IF EXISTS mp.tariff_rule_ym_logistics_tier;

CREATE TABLE IF NOT EXISTS mp.wb_logistics (
    marketplace_id INT NOT NULL REFERENCES mp.marketplaces,
    scheme         VARCHAR(16) NOT NULL,
    base_rub       NUMERIC(8,2) NOT NULL,
    per_liter_rub  NUMERIC(8,2) NOT NULL,
    valid_from     DATE NOT NULL,
    valid_to       DATE,
    source_url     TEXT,
    PRIMARY KEY (marketplace_id, scheme, valid_from)
);
COMMENT ON TABLE mp.wb_logistics IS 'Базовый тариф WB: ставка за 1-й литр + за каждый дополнительный. Категория влияет через КТР в tariff_rule_wb.';

CREATE TABLE IF NOT EXISTS mp.ozon_logistics_tier (
    marketplace_id      INT NOT NULL REFERENCES mp.marketplaces,
    scheme              VARCHAR(16) NOT NULL,
    volume_max_l        NUMERIC(8,3) NOT NULL,
    base_rub            NUMERIC(8,2) NOT NULL,
    per_liter_above_rub NUMERIC(8,2) NOT NULL DEFAULT 0,
    valid_from          DATE NOT NULL,
    valid_to            DATE,
    source_url          TEXT,
    PRIMARY KEY (marketplace_id, scheme, volume_max_l, valid_from)
);
COMMENT ON TABLE mp.ozon_logistics_tier IS 'Ступенчатая логистика Ozon: на каждый объёмный диапазон своя ставка.';

CREATE TABLE IF NOT EXISTS mp.ym_logistics_tier (
    marketplace_id INT NOT NULL REFERENCES mp.marketplaces,
    scheme         VARCHAR(16) NOT NULL,
    volume_max_l   NUMERIC(8,3) NOT NULL,
    base_rub       NUMERIC(8,2) NOT NULL,
    valid_from     DATE NOT NULL,
    valid_to       DATE,
    source_url     TEXT,
    PRIMARY KEY (marketplace_id, scheme, volume_max_l, valid_from)
);
COMMENT ON TABLE mp.ym_logistics_tier IS 'Ступенчатая логистика Яндекс.Маркета.';

ALTER TABLE mp.tariff_rule_wb DROP COLUMN IF EXISTS logistics_base_rub;
ALTER TABLE mp.tariff_rule_wb DROP COLUMN IF EXISTS logistics_per_liter_rub;

COMMIT;
