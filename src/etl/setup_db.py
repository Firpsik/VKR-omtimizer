import os
from pathlib import Path

from sqlalchemy import text

from src.db import get_engine
from src.etl.load_canonical import load_categories, load_groups
from src.etl.load_tariffs import main as load_tariffs

_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS = _ROOT / "sql" / "migrations"


def apply_migrations() -> None:
    engine = get_engine()
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        with engine.connect() as conn:
            raw = conn.connection
            with raw.cursor() as cur:
                cur.execute(sql)
            raw.commit()
        print(f"  applied: {path.name}")


def show_state() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT 'marketplaces', COUNT(*) FROM mp.marketplaces UNION ALL "
            "SELECT 'canonical_groups', COUNT(*) FROM mp.canonical_groups UNION ALL "
            "SELECT 'canonical_categories', COUNT(*) FROM mp.canonical_categories UNION ALL "
            "SELECT 'tariff_rule', COUNT(*) FROM mp.tariff_rule"
        )).fetchall()
    for name, n in rows:
        print(f"  {name:<22} {n}")


def bootstrap_demo_user() -> None:
    from src.auth import reset_demo_password

    demo_password = os.getenv("DEMO_PASSWORD", "demo")
    reset_demo_password(demo_password)
    print("  demo-аккаунт: пароль установлен")


def main() -> None:
    print("migrations:")
    apply_migrations()
    print("\ncanonical:")
    load_groups()
    load_categories()
    print("\ntariffs:")
    load_tariffs()
    print("\ndemo:")
    bootstrap_demo_user()
    print("\nstate:")
    show_state()


if __name__ == "__main__":
    main()
