import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "marketplace")
DB_USER = os.getenv("DB_USER", "mp_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "mp_pass")
DB_SSLMODE = os.getenv("DB_SSLMODE", "disable")

DATABASE_URL = (
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

_engine = None

def get_engine():
    global _engine
    if _engine is None:
        connect_args = {"connect_timeout": 10}
        if DB_SSLMODE and DB_SSLMODE != "disable":
            connect_args["sslmode"] = DB_SSLMODE
            sslrootcert = os.getenv("DB_SSLROOTCERT")
            if sslrootcert:
                cert_path = Path(sslrootcert).expanduser()
                if not cert_path.is_absolute():
                    cert_path = (_PROJECT_ROOT / cert_path).resolve()
                connect_args["sslrootcert"] = str(cert_path)
        _engine = create_engine(
            DATABASE_URL,
            echo=False,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return _engine

def get_connection():
    return get_engine().connect()

def execute_sql(sql_text: str, params=None):
    with get_engine().begin() as conn:
        conn.execute(text(sql_text), params or {})
