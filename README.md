# Market correlation matrices

Per-market equity correlation matrices for India, the US, Japan, Korea, China and Europe,
computed from the owner's unified OHLCV warehouse (`global-market-data/warehouse/warehouse.duckdb`,
the deduplicated successor to the retired LFS monolith panels). For quant/market researchers
who want pairwise return correlations without rebuilding a price panel. It produces, per market,
a float16 dense matrix (`.npz`), a long-format table of strongly correlated pairs (`.parquet`)
and a JSON summary — all tracked as regular git objects, no LFS.

> Status: maintained snapshot (windows ending Jun/Jul 2026). Descriptive statistics only; not a
> trading signal and not investment advice.

<!-- how-to-use-with-ai -->
> **New here?** See [How to use this repo with AI (Claude, Gemini, ChatGPT)](HOW_TO_USE_WITH_AI.md) — clone it, paste it into an AI tool, and ask in plain English.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herrrickshaw/market-correlation-matrices/blob/main/notebooks/colab_test.ipynb)

## What it does
- `compute_correlations.py` builds, for each of IN/US/JP/KR/CN/EU, the pairwise-complete Pearson
  correlation of daily log returns over the market's last 252 trading days.
- Universe per market: top 3,000 symbols by traded value (close × volume) in-window, keeping only
  symbols with ≥ 200 return observations.
- Writes `data/<MARKET>/corr_dense.npz` (float16 matrix + symbol list), `corr_pairs.parquet`
  (upper-triangle pairs with |r| ≥ 0.6, zstd) and `summary.json` (window, universe size,
  mean/median r, top-10 pairs); `data/summary_all.json` concatenates the six summaries.
- Also ships broader-universe N×N float16 parquet matrices for EU/IN/JP/KR
  (`data/<MARKET>/*_correlation_matrix.parquet`), produced separately — see Limitations.
- Replaces the old ad-hoc dense CSVs (up to 837 MB each, uncommitted, in wipe-prone
  `~/Downloads/data/*_scan/`) with the same information at a fraction of the size.

## Quick start
```bash
git clone https://github.com/herrrickshaw/market-correlation-matrices.git
cd market-correlation-matrices
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # duckdb, numpy, pandas
python compute_correlations.py           # ~2 min; needs the warehouse (see Configuration)
```
To read the tracked artefacts without rebuilding:
```python
import numpy as np, pandas as pd
d = np.load("data/IN/corr_dense.npz", allow_pickle=True)
corr, symbols = d["corr"], d["symbols"]               # float16 (N, N), object (N,)
pairs = pd.read_parquet("data/IN/corr_pairs.parquet")  # sym1, sym2, corr
```

## How it works
| Stage | Code | Output |
|---|---|---|
| Last 252 distinct dates per market from view `ohlcv` | `one_market()` | window `[d0, d1]` |
| Pull Symbol/Date/Close/traded value, keep top `N_MAX=3000` by traded value | `one_market()` | price pivot |
| `log(px).diff()`, drop symbols with < `MIN_OBS=200` returns | `one_market()` | returns frame |
| `rets.corr(min_periods=200)` (pairwise-complete Pearson) | `one_market()` | float32 matrix |
| Save float16 `.npz`, pairs with \|r\| ≥ `PAIR_THRESHOLD=0.6` as zstd parquet, summary JSON | `one_market()` | `data/<MARKET>/` |
| Loop over `MARKETS`, write `summary_all.json` | `main()` | `data/summary_all.json` |

Design decisions: float16 dense storage keeps the whole set (~132 MB) under GitHub's regular-object
limits so no LFS is needed; the pairs file is the human-readable view; the warehouse is opened
read-only.

Snapshot (windows ending Jun/Jul 2026, from `data/summary_all.json`):

| Market | Window | Symbols | Mean pairwise r | Pairs \|r\|≥0.6 |
|---|---|---|---|---|
| IN | 2025-07-10 → 2026-07-21 | 2,001 | 0.225 | 20,658 |
| KR | 2025-06-23 → 2026-07-02 | 2,570 | 0.227 | 7,370 |
| CN | 2025-06-18 → 2026-07-01 | 2,978 | 0.171 | 7,376 |
| JP | 2025-06-19 → 2026-07-01 | 2,998 | 0.170 | 5,223 |
| US | 2025-07-18 → 2026-07-20 | 2,945 | 0.115 | 14,503 |
| EU | 2025-07-04 → 2026-06-29 | 842 | 0.052 | 403 |

IN/KR trade the most "as one market"; EU's low mean is partly asynchronous exchange calendars
across 17 venues.

## Repository layout
| Path | Purpose |
|---|---|
| `compute_correlations.py` | the whole pipeline (one module, ~100 lines) |
| `requirements.txt` | duckdb, numpy, pandas |
| `data/<MARKET>/corr_dense.npz` | float16 dense matrix + symbols (tracked, generated) |
| `data/<MARKET>/corr_pairs.parquet` | pairs with \|r\| ≥ 0.6 (tracked, generated) |
| `data/<MARKET>/summary.json`, `data/summary_all.json` | per-market and combined summaries |
| `data/{EU,IN,JP,KR}/*_correlation_matrix.parquet` | broader-universe N×N matrices: EU 927, IN 2,234, JP 3,544, KR 2,726 symbols (`Symbol` column + one float column per symbol) |
| `notebooks/colab_test.ipynb` | Colab smoke test: clone, install, byte-compile |
| `graphify-out/` | generated knowledge-graph output |
| `.github/workflows/quality-gates.yml` | gitleaks secret scan on push/PR |

## Data sources
| Source | What is taken | Access route | Licence / caveat |
|---|---|---|---|
| `global-market-data/warehouse/warehouse.duckdb`, view `ohlcv` (same account) | Symbol, Date, Close, Volume per market | local DuckDB file, read-only | Not in this repo; derived from the owner's OHLCV collectors |

## Configuration
No environment variables. Constants at the top of `compute_correlations.py`:

| Name | Default | Meaning |
|---|---|---|
| `WAREHOUSE` | `~/repos/global-market-data/warehouse/warehouse.duckdb` | source DuckDB |
| `MARKETS` | `IN US JP KR CN EU` | markets processed |
| `WINDOW` | 252 | trading days |
| `N_MAX` | 3000 | liquidity cap per market |
| `MIN_OBS` | 200 | min return observations per symbol |
| `PAIR_THRESHOLD` | 0.6 | \|r\| floor for `corr_pairs.parquet` |

No secrets are needed or committed.

## Testing
```bash
python -m py_compile compute_correlations.py
```
No unit tests; CI runs only a gitleaks secret scan. The Colab notebook byte-compiles the module.

## Limitations and known issues
- **IN universe contains ETFs/index funds** — the warehouse NSE panel is not ISIN-filtered, so the
  top pairs are fund-on-fund (e.g. CONS↔NV20 r=0.999). Filter by ISIN prefix `INE` (equity) before
  treating top pairs as stock-pair signals.
- US top pairs are likewise dominated by crypto ETFs (BITB/GBTC/BTCO …) and dual-listed shells.
- Pairwise-complete correlation on thin symbols can be noisy even with the ≥200-observation floor;
  `corr_pairs.parquet` is descriptive, not a trading signal.
- float16 quantises r to ~3 decimal places — fine for screening; recompute from the warehouse for
  full precision.
- The `*_correlation_matrix.parquet` files are **not** produced by `compute_correlations.py`; they
  were added by hand (commit `3c1f269`) and cover a wider universe than the `.npz` files. The US
  matrix (6,446 × 6,446, 113 MB) exceeds GitHub's 100 MB object limit and is kept in the owner's
  Dropbox `market-data-archive` instead.
- Rebuilding requires the private warehouse file; without it only the tracked artefacts are usable.

## Related repositories
- `global-market-data` (same account) — source warehouse.
- `market-data-artifacts` (same account) — backup home for oversized artefacts.

## Licence
No licence file yet — all rights reserved.
