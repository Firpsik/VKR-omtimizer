import sys
from src.db import get_engine
from sqlalchemy import text

try:
    engine = get_engine()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        print(f"✓ Подключение OK: {version[:60]}...")

        n_products = conn.execute(text("SELECT COUNT(*) FROM mp.products")).scalar()
        n_sales = conn.execute(text("SELECT COUNT(*) FROM mp.sales_history")).scalar()
        n_results = conn.execute(text("SELECT COUNT(*) FROM mp.optimization_results")).scalar()

        print(f"✓ Товаров в БД:           {n_products}")
        print(f"✓ Наблюдений о продажах:  {n_sales}")
        print(f"✓ Результатов оптимизации: {n_results}")

    print("\nВсё работает. Можно запускать веб-приложение.")
except Exception as e:
    print(f"✗ Ошибка подключения: {e}")
    sys.exit(1)
