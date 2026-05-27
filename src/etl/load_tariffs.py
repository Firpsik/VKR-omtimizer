import csv
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from src.db import get_engine

_DATA = Path(__file__).resolve().parents[2] / "data"

def _read_csv(name: str) -> list[dict]:
    with (_DATA / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _resolve_mp(conn) -> dict[str, int]:
    rows = conn.execute(text("SELECT code, marketplace_id FROM mp.marketplaces")).fetchall()
    return {code: mid for code, mid in rows}

def _resolve_canon(conn) -> dict[str, int]:
    rows = conn.execute(text(
        "SELECT code, canonical_category_id FROM mp.canonical_categories"
    )).fetchall()
    return {code: cid for code, cid in rows}

def _upsert_tariff_rule(conn, mp_id: int, cat_id: int, scheme: str,
                        commission: Decimal, return_fee: Decimal,
                        disposal_fee: Decimal, buyout: Decimal,
                        ret_rate: Decimal, valid_from: str,
                        source_url: str, comment: str) -> int:
    row = conn.execute(text("""
        INSERT INTO mp.tariff_rule
            (marketplace_id, canonical_category_id, scheme, commission_pct,
             return_fee_rub, disposal_fee_rub, default_buyout_rate,
             default_return_rate, valid_from, source_url, comment)
        VALUES (:mp, :cat, :sch, :com, :rf, :df, :br, :rr, :vf, :url, :cmt)
        ON CONFLICT (marketplace_id, canonical_category_id, scheme, valid_from)
        DO UPDATE SET
            commission_pct      = EXCLUDED.commission_pct,
            return_fee_rub      = EXCLUDED.return_fee_rub,
            disposal_fee_rub    = EXCLUDED.disposal_fee_rub,
            default_buyout_rate = EXCLUDED.default_buyout_rate,
            default_return_rate = EXCLUDED.default_return_rate,
            source_url          = EXCLUDED.source_url,
            comment             = EXCLUDED.comment
        RETURNING tariff_rule_id
    """), dict(mp=mp_id, cat=cat_id, sch=scheme, com=commission,
               rf=return_fee, df=disposal_fee, br=buyout, rr=ret_rate,
               vf=valid_from, url=source_url, cmt=comment)).fetchone()
    return int(row[0])

def load_wb_tariffs() -> int:
    rows = _read_csv("tariffs_wb.csv")
    engine = get_engine()
    n = 0
    with engine.begin() as conn:
        mp = _resolve_mp(conn)
        cats = _resolve_canon(conn)
        mp_id = mp["wb"]
        for r in rows:
            cat_id = cats[r["canonical_category_code"]]
            tariff_id = _upsert_tariff_rule(
                conn, mp_id, cat_id, r["scheme"],
                Decimal(r["commission_pct"]), Decimal(r["return_fee_rub"]),
                Decimal(r["disposal_fee_rub"]), Decimal(r["default_buyout_rate"]),
                Decimal(r["default_return_rate"]), r["valid_from"],
                r["source_url"], r["comment"],
            )
            conn.execute(text("""
                INSERT INTO mp.tariff_rule_wb
                    (tariff_rule_id, ktr, warehouse_coef_default,
                     storage_per_liter_day_rub, default_promo_pct)
                VALUES (:id, :ktr, :wh, :st, :promo)
                ON CONFLICT (tariff_rule_id) DO UPDATE SET
                    ktr                       = EXCLUDED.ktr,
                    warehouse_coef_default    = EXCLUDED.warehouse_coef_default,
                    storage_per_liter_day_rub = EXCLUDED.storage_per_liter_day_rub,
                    default_promo_pct         = EXCLUDED.default_promo_pct
            """), dict(id=tariff_id, ktr=Decimal(r["ktr"]),
                       wh=Decimal(r["warehouse_coef_default"]),
                       st=Decimal(r["storage_per_liter_day_rub"]),
                       promo=Decimal(r["default_promo_pct"])))
            n += 1
    return n

def load_ozon_tariffs() -> int:
    rows = _read_csv("tariffs_ozon.csv")
    engine = get_engine()
    n = 0
    with engine.begin() as conn:
        mp = _resolve_mp(conn)
        cats = _resolve_canon(conn)
        mp_id = mp["ozon"]
        for r in rows:
            cat_id = cats[r["canonical_category_code"]]
            tariff_id = _upsert_tariff_rule(
                conn, mp_id, cat_id, r["scheme"],
                Decimal(r["commission_pct"]), Decimal(r["return_fee_rub"]),
                Decimal(r["disposal_fee_rub"]), Decimal(r["default_buyout_rate"]),
                Decimal(r["default_return_rate"]), r["valid_from"],
                r["source_url"], r["comment"],
            )
            conn.execute(text("""
                INSERT INTO mp.tariff_rule_ozon
                    (tariff_rule_id, last_mile_pct, last_mile_min_rub,
                     last_mile_max_rub, acquiring_pct, processing_fee_rub,
                     storage_free_days, storage_per_liter_day_rub,
                     locality_index_pct, default_promo_pct, default_seller_bonus_pct)
                VALUES (:id, :lp, :lmi, :lma, :ac, :pf, :sfd, :spld, :loc, :pr, :sb)
                ON CONFLICT (tariff_rule_id) DO UPDATE SET
                    last_mile_pct             = EXCLUDED.last_mile_pct,
                    last_mile_min_rub         = EXCLUDED.last_mile_min_rub,
                    last_mile_max_rub         = EXCLUDED.last_mile_max_rub,
                    acquiring_pct             = EXCLUDED.acquiring_pct,
                    processing_fee_rub        = EXCLUDED.processing_fee_rub,
                    storage_free_days         = EXCLUDED.storage_free_days,
                    storage_per_liter_day_rub = EXCLUDED.storage_per_liter_day_rub,
                    locality_index_pct        = EXCLUDED.locality_index_pct,
                    default_promo_pct         = EXCLUDED.default_promo_pct,
                    default_seller_bonus_pct  = EXCLUDED.default_seller_bonus_pct
            """), dict(id=tariff_id,
                       lp=Decimal(r["last_mile_pct"]),
                       lmi=Decimal(r["last_mile_min_rub"]),
                       lma=Decimal(r["last_mile_max_rub"]),
                       ac=Decimal(r["acquiring_pct"]),
                       pf=Decimal(r["processing_fee_rub"]),
                       sfd=int(r["storage_free_days"]),
                       spld=Decimal(r["storage_per_liter_day_rub"]),
                       loc=Decimal(r["locality_index_pct"]),
                       pr=Decimal(r["default_promo_pct"]),
                       sb=Decimal(r["default_seller_bonus_pct"])))
            n += 1
    return n

def load_ym_tariffs() -> int:
    rows = _read_csv("tariffs_ym.csv")
    engine = get_engine()
    n = 0
    with engine.begin() as conn:
        mp = _resolve_mp(conn)
        cats = _resolve_canon(conn)
        mp_id = mp["ym"]
        for r in rows:
            cat_id = cats[r["canonical_category_code"]]
            tariff_id = _upsert_tariff_rule(
                conn, mp_id, cat_id, r["scheme"],
                Decimal(r["commission_pct"]), Decimal(r["return_fee_rub"]),
                Decimal(r["disposal_fee_rub"]), Decimal(r["default_buyout_rate"]),
                Decimal(r["default_return_rate"]), r["valid_from"],
                r["source_url"], r["comment"],
            )
            conn.execute(text("""
                INSERT INTO mp.tariff_rule_ym
                    (tariff_rule_id, last_mile_pct, last_mile_max_rub,
                     acquiring_pct, packaging_fee_rub, storage_free_days,
                     storage_per_liter_day_rub, cofinance_pct, default_promo_pct)
                VALUES (:id, :lp, :lma, :ac, :pf, :sfd, :spld, :cof, :pr)
                ON CONFLICT (tariff_rule_id) DO UPDATE SET
                    last_mile_pct             = EXCLUDED.last_mile_pct,
                    last_mile_max_rub         = EXCLUDED.last_mile_max_rub,
                    acquiring_pct             = EXCLUDED.acquiring_pct,
                    packaging_fee_rub         = EXCLUDED.packaging_fee_rub,
                    storage_free_days         = EXCLUDED.storage_free_days,
                    storage_per_liter_day_rub = EXCLUDED.storage_per_liter_day_rub,
                    cofinance_pct             = EXCLUDED.cofinance_pct,
                    default_promo_pct         = EXCLUDED.default_promo_pct
            """), dict(id=tariff_id,
                       lp=Decimal(r["last_mile_pct"]),
                       lma=Decimal(r["last_mile_max_rub"]),
                       ac=Decimal(r["acquiring_pct"]),
                       pf=Decimal(r["packaging_fee_rub"]),
                       sfd=int(r["storage_free_days"]),
                       spld=Decimal(r["storage_per_liter_day_rub"]),
                       cof=Decimal(r["cofinance_pct"]),
                       pr=Decimal(r["default_promo_pct"])))
            n += 1
    return n

def load_logistics() -> dict[str, int]:
    engine = get_engine()
    counts = {"wb": 0, "ozon": 0, "ym": 0}
    with engine.begin() as conn:
        mp = _resolve_mp(conn)
        for r in _read_csv("logistics_wb.csv"):
            conn.execute(text("""
                INSERT INTO mp.wb_logistics (marketplace_id, scheme, base_rub,
                       per_liter_rub, valid_from, source_url)
                VALUES (:mp, :sch, :base, :pl, :vf, :url)
                ON CONFLICT (marketplace_id, scheme, valid_from) DO UPDATE SET
                    base_rub      = EXCLUDED.base_rub,
                    per_liter_rub = EXCLUDED.per_liter_rub,
                    source_url    = EXCLUDED.source_url
            """), dict(mp=mp[r["marketplace_code"]], sch=r["scheme"],
                       base=Decimal(r["base_rub"]), pl=Decimal(r["per_liter_rub"]),
                       vf=r["valid_from"], url=r["source_url"]))
            counts["wb"] += 1
        for r in _read_csv("logistics_ozon.csv"):
            conn.execute(text("""
                INSERT INTO mp.ozon_logistics_tier (marketplace_id, scheme,
                       volume_max_l, base_rub, per_liter_above_rub, valid_from, source_url)
                VALUES (:mp, :sch, :vol, :base, :pla, :vf, :url)
                ON CONFLICT (marketplace_id, scheme, volume_max_l, valid_from)
                DO UPDATE SET base_rub = EXCLUDED.base_rub,
                              per_liter_above_rub = EXCLUDED.per_liter_above_rub,
                              source_url = EXCLUDED.source_url
            """), dict(mp=mp[r["marketplace_code"]], sch=r["scheme"],
                       vol=Decimal(r["volume_max_l"]),
                       base=Decimal(r["base_rub"]),
                       pla=Decimal(r["per_liter_above_rub"]),
                       vf=r["valid_from"], url=r["source_url"]))
            counts["ozon"] += 1
        for r in _read_csv("logistics_ym.csv"):
            conn.execute(text("""
                INSERT INTO mp.ym_logistics_tier (marketplace_id, scheme,
                       volume_max_l, base_rub, valid_from, source_url)
                VALUES (:mp, :sch, :vol, :base, :vf, :url)
                ON CONFLICT (marketplace_id, scheme, volume_max_l, valid_from)
                DO UPDATE SET base_rub = EXCLUDED.base_rub,
                              source_url = EXCLUDED.source_url
            """), dict(mp=mp[r["marketplace_code"]], sch=r["scheme"],
                       vol=Decimal(r["volume_max_l"]),
                       base=Decimal(r["base_rub"]),
                       vf=r["valid_from"], url=r["source_url"]))
            counts["ym"] += 1
    return counts

def main() -> None:
    wb = load_wb_tariffs()
    ozon = load_ozon_tariffs()
    ym = load_ym_tariffs()
    log = load_logistics()
    print()
    print("=" * 60)
    print(f"Тарифные правила: WB={wb}, Ozon={ozon}, ЯМ={ym} (всего {wb+ozon+ym})")
    print(f"Логистика: WB={log['wb']} строк, Ozon={log['ozon']} ступеней, ЯМ={log['ym']} ступеней")
    print("Срез: 2026-01-01.")
    print("=" * 60)

if __name__ == "__main__":
    main()
