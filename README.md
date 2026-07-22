# market-correlation-matrices

Per-market equity **correlation matrices** computed from the unified OHLCV
warehouse (`global-market-data/warehouse/` — the deduplicated successor to the
retired LFS monolith panels). Six markets: IN, US, JP, KR, CN, EU.

Replaces the old ad-hoc dense CSVs (up to 837 MB each, uncommitted, wipe-prone
`~/Downloads/data/*_scan/`): same information, ~24× smaller, one-command rebuild,
all regular git objects — no LFS anywhere.

## Method

- **Window**: last 252 trading days per market (dates in each `summary.json`)
- **Universe**: top 3,000 symbols by traded value in-window, ≥200 return observations
- **Measure**: pairwise-complete Pearson correlation of daily **log returns**

## Artifacts (`data/<MARKET>/`)

| File | Contents |
|---|---|
| `corr_dense.npz` | full dense matrix, float16 + symbol list — `np.load(...)['corr']`, `['symbols']` |
| `corr_pairs.parquet` | upper-triangle pairs with \|r\| ≥ 0.6, zstd |
| `summary.json` | window, universe size, mean/median pairwise r, top-10 pairs |

Snapshot (window ending Jul 2026):

| Market | Symbols | Mean pairwise r | Pairs \|r\|≥0.6 |
|---|---|---|---|
| IN | 2,001 | 0.225 | 20,658 |
| KR | 2,570 | 0.227 | 7,370 |
| CN | 2,978 | 0.171 | 7,376 |
| JP | 2,998 | 0.170 | 5,223 |
| US | 2,945 | 0.115 | 14,503 |
| EU | 842 | 0.052 | 403 |

(IN/KR trade the most "as one market"; EU's low mean is partly asynchronous
exchange calendars across 17 venues.)

## Rebuild

```bash
/usr/bin/python3 compute_correlations.py   # needs duckdb+numpy+pandas; ~2 min
```

## Caveats

- **IN universe contains ETFs/index funds** — the warehouse NSE panel is not
  ISIN-filtered, so top pairs are dominated by fund-on-fund correlations
  (e.g. CONS↔NV20 r=0.999). Filter by ISIN prefix INE (equity) before treating
  top pairs as stock-pair signals — see the exchange-universe SOP note.
- Pairwise-complete correlation on thin symbols can be noisy even with the
  ≥200-observation floor; `corr_pairs.parquet` is descriptive, not a trading
  signal by itself.
- float16 dense storage quantises r to ~3 decimal places — fine for screening;
  recompute from the warehouse if you need full precision.
