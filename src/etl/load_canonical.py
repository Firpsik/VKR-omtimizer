import csv
from pathlib import Path

from sqlalchemy import text

from src.db import get_engine

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_GROUPS_CSV = _PROJECT_ROOT / "data" / "canonical_groups.csv"
_CATEGORIES_CSV = _PROJECT_ROOT / "data" / "canonical_categories.csv"

def load_groups() -> int:
    rows = []
    with _GROUPS_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "code": r["group_code"],
                "name": r["group_name"],
                "sort_order": int(r["sort_order"]),
            })

    engine = get_engine()
    with engine.begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO mp.canonical_groups (code, name, sort_order)
                VALUES (:code, :name, :sort_order)
                ON CONFLICT (code) DO UPDATE
                SET name       = EXCLUDED.name,
                    sort_order = EXCLUDED.sort_order
            """), r)
    print(f"[groups] Загружено групп: {len(rows)}")
    return len(rows)

def load_categories() -> int:
    rows = []
    with _CATEGORIES_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "code": r["category_code"],
                "name": r["category_name"],
                "group_code": r["group_code"],
                "sort_order": int(r["sort_order"]),
                "requires_marking": r["requires_marking"].lower() == "true",
                "marking_cost": float(r["marking_cost_per_unit_rub"] or 0),
            })

    engine = get_engine()
    with engine.begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO mp.canonical_categories
                    (canonical_group_id, code, name, sort_order,
                     requires_marking, marking_cost_per_unit_rub, is_custom)
                SELECT g.canonical_group_id, :code, :name, :sort_order,
                       :req, :cost, FALSE
                FROM mp.canonical_groups g
                WHERE g.code = :gcode
                ON CONFLICT (code) DO UPDATE
                SET name                      = EXCLUDED.name,
                    canonical_group_id        = EXCLUDED.canonical_group_id,
                    sort_order                = EXCLUDED.sort_order,
                    requires_marking          = EXCLUDED.requires_marking,
                    marking_cost_per_unit_rub = EXCLUDED.marking_cost_per_unit_rub
            """), {
                "code": r["code"],
                "name": r["name"],
                "gcode": r["group_code"],
                "sort_order": r["sort_order"],
                "req": r["requires_marking"],
                "cost": r["marking_cost"],
            })
    print(f"[categories] Загружено категорий: {len(rows)}")
    return len(rows)

def summary() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        grp_n = conn.execute(text("SELECT COUNT(*) FROM mp.canonical_groups")).scalar()
        cat_n = conn.execute(text("SELECT COUNT(*) FROM mp.canonical_categories")).scalar()
        marked = conn.execute(text(
            "SELECT COUNT(*) FROM mp.canonical_categories WHERE requires_marking"
        )).scalar()
    print()
    print("=" * 60)
    print(f"Итого в БД: групп = {grp_n}, категорий = {cat_n}")
    print(f"  из них требуют маркировки 'Честный знак': {marked}")
    print("=" * 60)

def main() -> None:
    load_groups()
    load_categories()
    summary()

if __name__ == "__main__":
    main()
