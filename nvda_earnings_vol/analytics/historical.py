"""Historical realized move analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd


def historical_p75(history: pd.DataFrame) -> float:
    """Return 75th percentile of absolute daily returns."""
    history = history.copy()
    history["return"] = history["Close"].pct_change()
    history = history.dropna()
    abs_returns = history["return"].abs().to_numpy()
    if abs_returns.size == 0:
        raise ValueError("Insufficient historical returns.")
    return float(np.percentile(abs_returns, 75))
