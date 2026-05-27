# Запуск

## Окружение

Требуется Python 3.12 и доступ к PostgreSQL.

```bash
python -m venv .venv
. .venv/bin/activate          # Linux / macOS
.\.venv\Scripts\Activate.ps1  # Windows PowerShell
pip install -r requirements.txt
```

Скопировать `.env.example` в `.env` и заполнить параметры подключения.
`AUTH_SECRET_KEY` сгенерировать самостоятельно (`python -c "import secrets; print(secrets.token_hex(32))"`).

```bash
python test_connection.py
```

## Первичная инициализация

Применяет все миграции из `sql/migrations/` и загружает справочники
канонических категорий и тарифов из `data/`.

```bash
python -m src.etl.setup_db
```

Скрипт идемпотентный — повторный запуск ничего не ломает.

## Локально

```bash
uvicorn src.api.app:app --reload --port 8000
```

## Сценарные тесты

```bash
python tests/e2e_pipeline.py
python tests/e2e_auth.py
```

## Деплой в Yandex Serverless Containers

Требуется Docker и `yc` CLI.

```powershell
$env:DB_PASSWORD = '<пароль БД>'
$env:AUTH_SECRET_KEY = '<секрет для cookies>'
.\redeploy.ps1
```

Скрипт собирает образ, пушит в Container Registry, разворачивает
новую ревизию контейнера.
