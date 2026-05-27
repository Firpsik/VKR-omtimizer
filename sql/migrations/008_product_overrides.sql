BEGIN;
SET search_path TO mp, public;

CREATE TABLE IF NOT EXISTS mp.product_overrides (
    product_id     INT PRIMARY KEY REFERENCES mp.products ON DELETE CASCADE,
    return_rate    NUMERIC(5,3),
    storage_days   INT,
    ktr            NUMERIC(6,3),
    warehouse_coef NUMERIC(6,3),
    promo_pct      NUMERIC(5,3),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE mp.product_overrides IS
'Пользовательские переопределения параметров расчёта на уровне товара. NULL — взять значение по умолчанию из тарифа.';

CREATE OR REPLACE FUNCTION mp.fn_unit_economics_wb(
    p_product_id     INT,
    p_tariff_rule_id BIGINT,
    p_avg_days       INT DEFAULT 30
) RETURNS TABLE (m NUMERIC, c NUMERIC, alpha_total NUMERIC) AS $$
DECLARE
    v_volume        NUMERIC;
    v_cost          NUMERIC;
    v_marking       NUMERIC;
    v_commission    NUMERIC;
    v_return_fee    NUMERIC;
    v_disposal_fee  NUMERIC;
    v_return_rate   NUMERIC;
    v_ktr           NUMERIC;
    v_wh_coef       NUMERIC;
    v_storage_rate  NUMERIC;
    v_promo         NUMERIC;
    v_log_base      NUMERIC;
    v_log_per_l     NUMERIC;
    v_logistics     NUMERIC;
    v_storage       NUMERIC;
    v_marketplace   INT;
    v_scheme        TEXT;
    v_valid_from    DATE;
    v_days          INT;
BEGIN
    SELECT p.volume_l, p.cost_rub, COALESCE(cc.marking_cost_per_unit_rub, 0)
      INTO v_volume, v_cost, v_marking
      FROM mp.products p
      JOIN mp.canonical_categories cc
        ON cc.canonical_category_id = p.canonical_category_id
     WHERE p.product_id = p_product_id;

    SELECT tr.commission_pct, tr.return_fee_rub, tr.disposal_fee_rub,
           tr.default_return_rate, tr.marketplace_id, tr.scheme, tr.valid_from
      INTO v_commission, v_return_fee, v_disposal_fee,
           v_return_rate, v_marketplace, v_scheme, v_valid_from
      FROM mp.tariff_rule tr
     WHERE tr.tariff_rule_id = p_tariff_rule_id;

    SELECT twb.ktr, twb.warehouse_coef_default,
           twb.storage_per_liter_day_rub, twb.default_promo_pct
      INTO v_ktr, v_wh_coef, v_storage_rate, v_promo
      FROM mp.tariff_rule_wb twb
     WHERE twb.tariff_rule_id = p_tariff_rule_id;

    SELECT COALESCE(po.return_rate,    v_return_rate),
           COALESCE(po.storage_days,   p_avg_days),
           COALESCE(po.ktr,            v_ktr),
           COALESCE(po.warehouse_coef, v_wh_coef),
           COALESCE(po.promo_pct,      v_promo)
      INTO v_return_rate, v_days, v_ktr, v_wh_coef, v_promo
      FROM (SELECT p_product_id AS pid) src
      LEFT JOIN mp.product_overrides po ON po.product_id = src.pid;

    SELECT wl.base_rub, wl.per_liter_rub
      INTO v_log_base, v_log_per_l
      FROM mp.wb_logistics wl
     WHERE wl.marketplace_id = v_marketplace
       AND wl.scheme = v_scheme
       AND wl.valid_from <= v_valid_from
     ORDER BY wl.valid_from DESC
     LIMIT 1;

    v_logistics := (v_log_base + v_log_per_l * GREATEST(v_volume - 1, 0))
                   * v_ktr * v_wh_coef;
    v_storage   := v_storage_rate * v_volume * v_days;

    alpha_total := v_commission + v_promo;
    m           := 1 - alpha_total;
    c           := v_cost
                 + v_logistics
                 + v_storage
                 + v_return_fee   * v_return_rate
                 + v_disposal_fee * v_return_rate
                 + v_marking;
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION mp.fn_unit_economics_ozon(
    p_product_id     INT,
    p_tariff_rule_id BIGINT,
    p_avg_days       INT DEFAULT 30
) RETURNS TABLE (m NUMERIC, c NUMERIC, alpha_total NUMERIC) AS $$
DECLARE
    v_volume       NUMERIC; v_cost NUMERIC; v_marking NUMERIC;
    v_commission   NUMERIC; v_return_fee NUMERIC; v_disposal_fee NUMERIC;
    v_return_rate  NUMERIC; v_marketplace INT; v_scheme TEXT; v_valid_from DATE;
    v_last_mile    NUMERIC; v_lm_min NUMERIC; v_lm_max NUMERIC;
    v_acquiring    NUMERIC; v_proc NUMERIC; v_free_days INT;
    v_storage_rate NUMERIC; v_loc_idx NUMERIC; v_promo NUMERIC; v_bonus NUMERIC;
    v_log_base     NUMERIC;
    v_logistics    NUMERIC; v_storage NUMERIC; v_days INT;
BEGIN
    SELECT p.volume_l, p.cost_rub, COALESCE(cc.marking_cost_per_unit_rub, 0)
      INTO v_volume, v_cost, v_marking
      FROM mp.products p
      JOIN mp.canonical_categories cc ON cc.canonical_category_id = p.canonical_category_id
     WHERE p.product_id = p_product_id;

    SELECT tr.commission_pct, tr.return_fee_rub, tr.disposal_fee_rub,
           tr.default_return_rate, tr.marketplace_id, tr.scheme, tr.valid_from
      INTO v_commission, v_return_fee, v_disposal_fee,
           v_return_rate, v_marketplace, v_scheme, v_valid_from
      FROM mp.tariff_rule tr
     WHERE tr.tariff_rule_id = p_tariff_rule_id;

    SELECT toz.last_mile_pct, toz.last_mile_min_rub, toz.last_mile_max_rub,
           toz.acquiring_pct, toz.processing_fee_rub, toz.storage_free_days,
           toz.storage_per_liter_day_rub, toz.locality_index_pct,
           toz.default_promo_pct, toz.default_seller_bonus_pct
      INTO v_last_mile, v_lm_min, v_lm_max,
           v_acquiring, v_proc, v_free_days,
           v_storage_rate, v_loc_idx,
           v_promo, v_bonus
      FROM mp.tariff_rule_ozon toz
     WHERE toz.tariff_rule_id = p_tariff_rule_id;

    SELECT COALESCE(po.return_rate, v_return_rate),
           COALESCE(po.storage_days, p_avg_days),
           COALESCE(po.promo_pct,    v_promo)
      INTO v_return_rate, v_days, v_promo
      FROM (SELECT p_product_id AS pid) src
      LEFT JOIN mp.product_overrides po ON po.product_id = src.pid;

    SELECT olt.base_rub
      INTO v_log_base
      FROM mp.ozon_logistics_tier olt
     WHERE olt.marketplace_id = v_marketplace
       AND olt.scheme = v_scheme
       AND olt.volume_max_l >= v_volume
       AND olt.valid_from <= v_valid_from
     ORDER BY olt.volume_max_l ASC, olt.valid_from DESC
     LIMIT 1;

    IF v_log_base IS NULL THEN
        SELECT olt.base_rub INTO v_log_base
          FROM mp.ozon_logistics_tier olt
         WHERE olt.marketplace_id = v_marketplace
           AND olt.scheme = v_scheme
           AND olt.valid_from <= v_valid_from
         ORDER BY olt.volume_max_l DESC, olt.valid_from DESC
         LIMIT 1;
    END IF;
    v_logistics := COALESCE(v_log_base, 0);

    v_storage := v_storage_rate * v_volume * GREATEST(v_days - v_free_days, 0);

    alpha_total := v_commission + v_last_mile + v_acquiring + v_promo + v_bonus + v_loc_idx;
    m           := 1 - alpha_total;
    c           := v_cost
                 + v_logistics
                 + v_proc
                 + v_storage
                 + v_return_fee   * v_return_rate
                 + v_disposal_fee * v_return_rate
                 + v_marking;
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION mp.fn_unit_economics_ym(
    p_product_id     INT,
    p_tariff_rule_id BIGINT,
    p_avg_days       INT DEFAULT 30
) RETURNS TABLE (m NUMERIC, c NUMERIC, alpha_total NUMERIC) AS $$
DECLARE
    v_volume       NUMERIC; v_cost NUMERIC; v_marking NUMERIC;
    v_commission   NUMERIC; v_return_fee NUMERIC; v_disposal_fee NUMERIC;
    v_return_rate  NUMERIC; v_marketplace INT; v_scheme TEXT; v_valid_from DATE;
    v_last_mile    NUMERIC; v_lm_max NUMERIC; v_acquiring NUMERIC;
    v_packaging    NUMERIC; v_free_days INT; v_storage_rate NUMERIC;
    v_cofin        NUMERIC; v_promo NUMERIC;
    v_log_base     NUMERIC;
    v_logistics    NUMERIC; v_storage NUMERIC; v_days INT;
BEGIN
    SELECT p.volume_l, p.cost_rub, COALESCE(cc.marking_cost_per_unit_rub, 0)
      INTO v_volume, v_cost, v_marking
      FROM mp.products p
      JOIN mp.canonical_categories cc ON cc.canonical_category_id = p.canonical_category_id
     WHERE p.product_id = p_product_id;

    SELECT tr.commission_pct, tr.return_fee_rub, tr.disposal_fee_rub,
           tr.default_return_rate, tr.marketplace_id, tr.scheme, tr.valid_from
      INTO v_commission, v_return_fee, v_disposal_fee,
           v_return_rate, v_marketplace, v_scheme, v_valid_from
      FROM mp.tariff_rule tr
     WHERE tr.tariff_rule_id = p_tariff_rule_id;

    SELECT tym.last_mile_pct, tym.last_mile_max_rub, tym.acquiring_pct,
           tym.packaging_fee_rub, tym.storage_free_days, tym.storage_per_liter_day_rub,
           tym.cofinance_pct, tym.default_promo_pct
      INTO v_last_mile, v_lm_max, v_acquiring,
           v_packaging, v_free_days, v_storage_rate,
           v_cofin, v_promo
      FROM mp.tariff_rule_ym tym
     WHERE tym.tariff_rule_id = p_tariff_rule_id;

    SELECT COALESCE(po.return_rate, v_return_rate),
           COALESCE(po.storage_days, p_avg_days),
           COALESCE(po.promo_pct,    v_promo)
      INTO v_return_rate, v_days, v_promo
      FROM (SELECT p_product_id AS pid) src
      LEFT JOIN mp.product_overrides po ON po.product_id = src.pid;

    SELECT ylt.base_rub
      INTO v_log_base
      FROM mp.ym_logistics_tier ylt
     WHERE ylt.marketplace_id = v_marketplace
       AND ylt.scheme = v_scheme
       AND ylt.volume_max_l >= v_volume
       AND ylt.valid_from <= v_valid_from
     ORDER BY ylt.volume_max_l ASC, ylt.valid_from DESC
     LIMIT 1;

    IF v_log_base IS NULL THEN
        SELECT ylt.base_rub INTO v_log_base
          FROM mp.ym_logistics_tier ylt
         WHERE ylt.marketplace_id = v_marketplace
           AND ylt.scheme = v_scheme
           AND ylt.valid_from <= v_valid_from
         ORDER BY ylt.volume_max_l DESC, ylt.valid_from DESC
         LIMIT 1;
    END IF;
    v_logistics := COALESCE(v_log_base, 0);

    v_storage := v_storage_rate * v_volume * GREATEST(v_days - v_free_days, 0);

    alpha_total := v_commission + v_last_mile + v_acquiring + v_promo + v_cofin;
    m           := 1 - alpha_total;
    c           := v_cost
                 + v_logistics
                 + v_packaging
                 + v_storage
                 + v_return_fee   * v_return_rate
                 + v_disposal_fee * v_return_rate
                 + v_marking;
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql STABLE;

COMMIT;
