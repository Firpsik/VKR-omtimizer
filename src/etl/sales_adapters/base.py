from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Iterator

class AdapterError(ValueError):
    pass

@dataclass(slots=True, frozen=True)
class CanonicalSale:

    obs_date: date
    sku: str
    price_rub: float
    qty: int
    is_promo: bool
    stock_qty: int | None
    source_row: int

_DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%d/%m/%Y")

def parse_date(s: str, row_n: int) -> date:
    s = (s or "").strip().split(" ")[0]  # отрезаем время если есть
    if not s:
        raise AdapterError(f"строка {row_n}: пустая дата")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise AdapterError(f"строка {row_n}: не распознан формат даты {s!r}")

def parse_float(s: str, row_n: int) -> float:
    if s is None or s == "":
        return 0.0
    cleaned = str(s).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        raise AdapterError(f"строка {row_n}: не число {s!r}")

def parse_int(s: str, row_n: int) -> int:
    if s is None or s == "":
        return 0
    cleaned = str(s).replace("\xa0", "").replace(" ", "")
    try:
        return int(float(cleaned))  # допускаем '1.0'
    except ValueError:
        raise AdapterError(f"строка {row_n}: не целое {s!r}")

def _sniff_delimiter(sample: str) -> str:
    head = sample.splitlines()[0] if sample else ""
    counts = {d: head.count(d) for d in (";", ",", "\t")}
    return max(counts, key=counts.get) if any(counts.values()) else ","

def iter_rows(csv_text: str) -> Iterator[tuple[int, dict]]:
    if csv_text.startswith("\ufeff"):
        csv_text = csv_text[1:]
    delim = _sniff_delimiter(csv_text[:2000])
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delim)
    for n, row in enumerate(reader, start=2):
        if not any(v and str(v).strip() for v in row.values()):
            continue  # пустая строка
        yield n, row

class SalesAdapter(ABC):
    marketplace_code: str = ""
    display_name: str = ""
    accepted_column_set: set[str] = set()

    @abstractmethod
    def parse(self, csv_text: str) -> list[CanonicalSale]: ...

_REGISTRY: list[type[SalesAdapter]] = []

def register(cls: type[SalesAdapter]) -> type[SalesAdapter]:
    _REGISTRY.append(cls)
    return cls

def _read_header(csv_text: str) -> set[str]:
    delim = _sniff_delimiter(csv_text[:2000])
    if csv_text.startswith("\ufeff"):
        csv_text = csv_text[1:]
    first = csv_text.splitlines()[0] if csv_text else ""
    return {h.strip() for h in next(csv.reader([first], delimiter=delim))}

def detect_adapter(csv_text: str) -> SalesAdapter | None:
    header = _read_header(csv_text)
    for cls in _REGISTRY:
        if cls.accepted_column_set and cls.accepted_column_set.issubset(header):
            return cls()
    return None

def parse_report(csv_text: str, marketplace_code: str | None = None) -> list[CanonicalSale]:
    if marketplace_code:
        for cls in _REGISTRY:
            if cls.marketplace_code == marketplace_code:
                return cls().parse(csv_text)
        raise AdapterError(f"Нет адаптера для маркетплейса {marketplace_code!r}")
    adapter = detect_adapter(csv_text)
    if adapter is None:
        raise AdapterError(
            "Не удалось определить формат отчёта по заголовкам. "
            f"Поддерживаемые: {[cls.marketplace_code for cls in _REGISTRY]}"
        )
    return adapter.parse(csv_text)
