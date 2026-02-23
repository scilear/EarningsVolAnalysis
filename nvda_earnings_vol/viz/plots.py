"""Plot generation for reports."""

from __future__ import annotations

import base64
from io import BytesIO

import matplotlib
import matplotlib.pyplot as plt


matplotlib.use("Agg")


def plot_move_comparison(implied_move: float, historical_p75: float) -> str:
    """Return base64 PNG for implied vs historical move."""
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(["Implied", "Hist P75"], [implied_move, historical_p75])
    ax.set_ylabel("Move (pct)")
    ax.set_title("Implied vs Historical Move")
    return _encode(fig)


def plot_pnl_distribution(pnls, title: str) -> str:
    """Return base64 PNG for P&L distribution."""
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.hist(pnls, bins=50, color="#2f6f7e")
    ax.set_title(title)
    ax.set_xlabel("P&L")
    ax.set_ylabel("Count")
    return _encode(fig)


def _encode(fig) -> str:
    buffer = BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("ascii")
