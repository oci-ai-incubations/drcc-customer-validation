"""Render summary charts to base64 PNG data URIs for embedding in HTML/PDF."""
from __future__ import annotations

import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_COLORS = {"pass": "#1e7e34", "error": "#c62828", "warning": "#e65100", "inc": "#cccccc"}


def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", transparent=True)
    plt.close(fig)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def doughnut_data_uri(passed: int, errors: int, warnings: int, incomplete: int) -> str:
    fig, ax = plt.subplots(figsize=(3.2, 3.2))
    data = [passed, errors, warnings, incomplete]
    labels = ["Pass", "Error", "Warning", "Incomplete"]
    colors = [_COLORS["pass"], _COLORS["error"], _COLORS["warning"], _COLORS["inc"]]
    plotted = [(d, l, c) for d, l, c in zip(data, labels, colors) if d > 0]
    if not plotted:
        plotted = [(1, "No data", "#cccccc")]
    vals, labs, cols = zip(*plotted)
    ax.pie(vals, labels=labs, colors=cols, wedgeprops={"width": 0.35},
           textprops={"fontsize": 8})
    ax.set_aspect("equal")
    return _fig_to_data_uri(fig)


def bar_data_uri(labels: list[str], errors: list[int], warnings: list[int]) -> str:
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    x = range(len(labels))
    ax.bar(x, errors, label="Errors", color=_COLORS["error"])
    ax.bar(x, warnings, bottom=errors, label="Warnings", color=_COLORS["warning"])
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.legend(fontsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return _fig_to_data_uri(fig)
