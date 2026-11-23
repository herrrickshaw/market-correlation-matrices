import importlib
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

N_DATES = 300
DATES = pd.bdate_range("2023-01-02", periods=N_DATES)


@pytest.fixture
def cc(tmp_path, monkeypatch):
    sys.modules.pop("compute_correlations", None)
    m = importlib.import_module("compute_correlations")
    monkeypatch.setattr(m, "OUT", tmp_path / "data")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(m, "WAREHOUSE", tmp_path / "wh.duckdb")
    yield m
    sys.modules.pop("compute_correlations", None)


def returns_panel(seed=0, n=N_DATES):
    """Log-return paths with known structure: B == A, C == -A, D..J independent."""
    rng = np.random.RandomState(seed)
    base = rng.normal(0, 0.01, n)
    rets = {"A": base, "B": base.copy(), "C": -base}
    for s in "DEFGHIJ":
        rets[s] = rng.normal(0, 0.01, n)
    return rets


def market_rows(mkt, rets=None, volume=1000.0, partial=None, start_px=None, dates=DATES):
    """Long OHLCV rows. `partial`: {date_index: [symbols present]} overrides who trades that day."""
    rets = rets or returns_panel()
    rows = []
    for k, (s, r) in enumerate(sorted(rets.items())):
        px = (start_px or {}).get(s, 100.0 + 10 * k) * np.exp(np.cumsum(r))
        for i, d in enumerate(dates):
            if partial and i in partial and s not in partial[i]:
                continue
            rows.append((mkt, s, d, float(px[i]), volume))
    return rows


def write_warehouse(path, rows):
    df = pd.DataFrame(rows, columns=["market", "Symbol", "Date", "Close", "Volume"])
    con = duckdb.connect(str(path))
    con.execute("CREATE OR REPLACE TABLE ohlcv AS SELECT * FROM df")
    con.close()
