BEGIN;
SET search_path TO mp, public;

DROP VIEW IF EXISTS mp.v_kpi                  CASCADE;
DROP VIEW IF EXISTS mp.v_marketplace_share    CASCADE;
DROP VIEW IF EXISTS mp.v_marketplace_compare  CASCADE;
DROP VIEW IF EXISTS mp.v_elasticity           CASCADE;
DROP VIEW IF EXISTS mp.v_sensitivity          CASCADE;
DROP VIEW IF EXISTS mp.v_price_structure_pct  CASCADE;
DROP VIEW IF EXISTS mp.v_price_structure_rub  CASCADE;
DROP VIEW IF EXISTS mp.v_demand_fit           CASCADE;
DROP VIEW IF EXISTS mp.v_demand_curves        CASCADE;
DROP VIEW IF EXISTS mp.v_best                 CASCADE;
DROP VIEW IF EXISTS mp.v_dashboard            CASCADE;

DROP TABLE IF EXISTS mp.optimization_results CASCADE;
DROP TABLE IF EXISTS mp.demand_params        CASCADE;
DROP TABLE IF EXISTS mp.unit_economics       CASCADE;

CREATE TABLE mp.unit_economics (
    product_id      INT      NOT NULL REFERENCES mp.products,
    marketplace_id  INT      NOT NULL REFERENCES mp.marketplaces,
    scheme          VARCHAR(16) NOT NULL,
    tariff_rule_id  BIGINT   NOT NULL REFERENCES mp.tariff_rule,
    m_coef          NUMERIC(8,5)  NOT NULL,
    c_total_rub     NUMERIC(14,2) NOT NULL,
    alpha_total     NUMERIC(8,5)  NOT NULL,
    alpha_commission NUMERIC(8,5) NOT NULL,
    computed_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, marketplace_id, scheme)
);
COMMENT ON TABLE mp.unit_economics IS
'Снэпшот юнит-экономики (товар × МП × схема). Заполняется оптимизатором из v_unit_economics.';

CREATE TABLE mp.demand_params (
    product_id      INT      NOT NULL REFERENCES mp.products,
    marketplace_id  INT      NOT NULL REFERENCES mp.marketplaces,
    a_coef          NUMERIC(14,4) NOT NULL,
    b_coef          NUMERIC(14,6) NOT NULL,
    a_low           NUMERIC(14,4),
    a_high          NUMERIC(14,4),
    b_low           NUMERIC(14,6),
    b_high          NUMERIC(14,6),
    r2              NUMERIC(6,4),
    n_obs           INT      NOT NULL,
    source          VARCHAR(32) NOT NULL DEFAULT 'ols',
    reliable        BOOLEAN  NOT NULL DEFAULT TRUE,
    message         TEXT,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, marketplace_id)
);
COMMENT ON TABLE mp.demand_params IS
'Параметры линейной модели спроса (МНК) для пары товар×МП. Схема не учитывается: спрос — свойство покупателя, не способа доставки.';

CREATE TABLE mp.optimization_results (
    product_id      INT      NOT NULL REFERENCES mp.products,
    marketplace_id  INT      NOT NULL REFERENCES mp.marketplaces,
    scheme          VARCHAR(16) NOT NULL,
    p_min           NUMERIC(12,2),
    p_max           NUMERIC(12,2),
    s_opt           NUMERIC(12,2),
    q_opt           NUMERIC(14,4),
    profit_opt      NUMERIC(14,2),
    feasible        BOOLEAN  NOT NULL DEFAULT TRUE,
    is_best         BOOLEAN  NOT NULL DEFAULT FALSE,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, marketplace_id, scheme)
);
COMMENT ON TABLE mp.optimization_results IS
'Результат оптимизации: s*, q*, П*, флаг лучшей площадки.';

COMMIT;
