from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Sequence

import numpy as np
from scipy import stats

MIN_N_OBS = 10
MIN_N_UNIQUE = 6
MIN_R2 = 0.7
OUTLIER_SIGMA = 2.5
CONF_LEVEL = 0.95

@dataclass
class DemandEstimate:
    a: float
    b: float
    a_low: float
    a_high: float
    b_low: float
    b_high: float
    r2: float
    n_obs: int
    source: str
    reliable: bool
    message: str

    def to_dict(self) -> dict:
        return asdict(self)

def clean_observations(
    prices: Sequence[float],
    quantities: Sequence[int],
    is_promo: Optional[Sequence[bool]] = None,
    stock_qty: Optional[Sequence[int]] = None,
) -> tuple[np.ndarray, np.ndarray]:
    p = np.asarray(prices, dtype=float)
    q = np.asarray(quantities, dtype=float)

    mask = np.ones(len(p), dtype=bool)
    if is_promo is not None:
        promo_arr = np.asarray(is_promo, dtype=bool)
        mask &= ~promo_arr
    if stock_qty is not None:
        stock_arr = np.asarray(stock_qty, dtype=float)
        not_null = ~np.isnan(stock_arr)
        mask &= ~(not_null & (stock_arr == 0) & (q == 0))

    return p[mask], q[mask]

def aggregate_by_price(
    prices: np.ndarray,
    quantities: np.ndarray,
    round_to: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if len(prices) == 0:
        return np.array([]), np.array([])

    if round_to is None:
        mean_p = float(np.mean(prices))
        round_to = max(1.0, mean_p * 0.01)

    rounded = np.round(prices / round_to) * round_to
    unique_p = np.unique(rounded)
    mean_q = np.array([
        quantities[rounded == p].mean() for p in unique_p
    ])
    return unique_p, mean_q

def _drop_residual_outliers(
    p: np.ndarray, q: np.ndarray, threshold: float = OUTLIER_SIGMA,
) -> tuple[np.ndarray, np.ndarray, int]:
    if len(p) < 4:
        return p, q, 0
    res = stats.linregress(p, q)
    pred = res.intercept + res.slope * p
    resid = q - pred
    sigma = np.std(resid, ddof=1) if len(resid) > 1 else 0.0
    if sigma == 0:
        return p, q, 0
    keep = np.abs(resid) <= threshold * sigma
    n_dropped = int((~keep).sum())
    return p[keep], q[keep], n_dropped

def fit_linear_demand(
    prices: Sequence[float],
    quantities: Sequence[int],
    is_promo: Optional[Sequence[bool]] = None,
    stock_qty: Optional[Sequence[int]] = None,
    aggregate: bool = True,
) -> DemandEstimate:
    p_clean, q_clean = clean_observations(prices, quantities, is_promo, stock_qty)
    n_clean = len(p_clean)
    if aggregate:
        p_arr, q_arr = aggregate_by_price(p_clean, q_clean)
    else:
        p_arr, q_arr = p_clean, q_clean

    n = len(p_arr)
    dropped = 0

    if n < MIN_N_UNIQUE:
        return DemandEstimate(
            a=1.0, b=0.0001,
            a_low=0.0, a_high=0.0,
            b_low=0.0, b_high=0.0,
            r2=0.0, n_obs=n_clean, source="fit",
            reliable=False,
            message=(
                f"Слабый сигнал: {n} уникальных ценовых точек < {MIN_N_UNIQUE}"
                if n_clean >= MIN_N_OBS
                else f"Недостаточно наблюдений: n={n_clean} < {MIN_N_OBS}"
            ),
        )

    p_arr, q_arr, dropped = _drop_residual_outliers(p_arr, q_arr)
    n = len(p_arr)

    if n < MIN_N_UNIQUE:
        return DemandEstimate(
            a=1.0, b=0.0001,
            a_low=0.0, a_high=0.0,
            b_low=0.0, b_high=0.0,
            r2=0.0, n_obs=n_clean, source="fit",
            reliable=False,
            message=f"После отбраковки выбросов осталось {n} точек < {MIN_N_UNIQUE}",
        )

    res = stats.linregress(p_arr, q_arr)
    slope = res.slope
    intercept = res.intercept
    r_value = res.rvalue
    stderr_slope = res.stderr
    stderr_intercept = getattr(res, "intercept_stderr", float("nan"))

    a = intercept
    b = -slope
    r2 = r_value ** 2

    if n > 2 and not np.isnan(stderr_slope):
        t_crit = stats.t.ppf((1 + CONF_LEVEL) / 2.0, df=n - 2)
        if not np.isnan(stderr_intercept):
            a_low = intercept - t_crit * stderr_intercept
            a_high = intercept + t_crit * stderr_intercept
        else:
            a_low = a_high = a
        slope_low = slope - t_crit * stderr_slope
        slope_high = slope + t_crit * stderr_slope
        b_low = -slope_high
        b_high = -slope_low
    else:
        a_low = a_high = a
        b_low = b_high = b

    reliable = (a > 0 and b > 0 and n_clean >= MIN_N_OBS and n >= MIN_N_UNIQUE and r2 >= MIN_R2)

    parts = [f"R²={r2:.3f}, n={n_clean}, уник.точек={n}"]
    if dropped:
        parts.append(f"отброшено выбросов: {dropped}")
    if a <= 0 or b <= 0:
        parts.append(f"некорректные знаки (a={a:.1f}, b={b:.4f})")
    elif n_clean < MIN_N_OBS:
        parts.append(f"ниже порога надёжности (n<{MIN_N_OBS})")
    msg = "; ".join(parts)

    a_safe = max(a, 1.0)
    b_safe = max(b, 0.0001)

    return DemandEstimate(
        a=a_safe, b=b_safe,
        a_low=max(a_low, 0.0), a_high=max(a_high, a_safe),
        b_low=max(b_low, 0.0), b_high=max(b_high, b_safe),
        r2=r2, n_obs=n_clean, source="fit",
        reliable=reliable,
        message=msg,
    )
