# market-correlation-matrices

<!-- how-to-use-with-ai -->
> **New here?** See [How to use this repo with AI (Claude, Gemini, ChatGPT)](HOW_TO_USE_WITH_AI.md) — clone it, paste it into an AI tool, and ask in plain English.


[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/herrrickshaw/market-correlation-matrices/blob/main/notebooks/colab_test.ipynb)

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

## Data currency

Read from each `data/<MARKET>/summary.json` (252-trading-day windows; matrices are a
static snapshot, not auto-refreshed):

| Market | Window start | Window end | Symbols |
|---|---|---|---|
| IN | 2025-07-10 | 2026-07-21 | 2,001 |
| US | 2025-07-18 | 2026-07-20 | 2,945 |
| JP | 2025-06-19 | 2026-07-01 | 2,998 |
| KR | 2025-06-23 | 2026-07-02 | 2,570 |
| CN | 2025-06-18 | 2026-07-01 | 2,978 |
| EU | 2025-07-04 | 2026-06-29 | 842 |

Windows end between 2026-06-29 and 2026-07-21, so the markets are not aligned to a common
end date (about three weeks of spread) and none is current as of 2026-10-17.

TODO (markets / coverage missing):
- Rebuild all six with `compute_correlations.py` once the warehouse has data past July 2026.
- Align the windows to a common end date, or document per-market end dates in cross-market comparisons.
- Add markets in the wider pipeline universe that are not covered here (the pipeline's
  per-market tiers include more than these six; none has a matrix in this repo yet).
- Re-run IN with an ISIN-prefix INE filter (see Caveats) before using top pairs as stock signals.

## Literature context

Relevant entries from the research register (`market-pipeline/research/LITERATURE_REGISTER.md`,
read 2026-10-17). Grades are the register's own wording; where the register gives no explicit
grade, that is stated rather than inferred.

| arXiv id | Title | Register's grade / verdict |
|---|---|---|
| 2604.17251 | ORCA: Online Regime Correlation Analyzer (Kriuk & Kriuk, 2026) | EVIDENCE-GRADE: strong |
| 2608.09641 | Lower Spectrum of Financial Correlation Matrices (Grassi, Pastorino, Uberti, 2026) | EVIDENCE-GRADE: medium |
| 2111.05072 | The Evolving Causal Structure of Equity Risk Factors (D'Acunto et al., 2021) | EVIDENCE-GRADE: medium |
| 2607.19005 | Observable Matrix Dynamics of Stocks (Halperin) | Filed under "Strong evidence, high relevance"; no separate grade line |
| 2309.17219 | Covariance matrix filtering and portfolio optimisation: the Average Oracle vs Non-Linear Shrinkage (Bongiorno & Challet, 2023) | Passes triage (Sharpe, 5 bps costs applied, US 2000-2021); no explicit grade label |
| 2601.06090 | Nordic correlation regime shifts (Girnyk) | Passes on rigor, but 3 indices only; logged, not deep-read |
| 2507.14325 | Multiscale RMT eigenvalue distribution | Discarded: no trading evaluation |

What the register says matters for this repo: the correlation matrix is a regime descriptor.
The upper spectrum (absorption ratio, effective rank = exp(eigenvalue entropy), spectral gap,
Marchenko-Pastur excess) and the lower spectrum (m-minus, eigenvalues below the lower
Marchenko-Pastur bound) both come from one eigendecomposition. The register logs a 2026-08-23
measurement in the pipeline's own NSE data in which the five lowest participation-ratio
windows in 10.5 years all fell in Mar-May 2020. This repo currently stores only the matrix,
pairs and mean/median r, with no spectral summary.

## Open questions from literature

Drawn from `BACKTEST_QUEUE.md` items 9, 13, 18 and 29 and the entries above. Nothing here
has been run in this repo.

1. Do the per-market spectral descriptors (AR_1/3/5, effective rank, lambda1/lambda2,
   Marchenko-Pastur excess, m-minus) separate the six markets, and does the low EU mean r
   (0.052) reflect asynchronous calendars or genuinely higher effective dimension?
2. With n up to about 3,000 and T = 252, n/T is well above 1, so most of the spectrum is noise
   by the Marchenko-Pastur bound. What cleaning (linear shrinkage, frozen-eigenvalue
   "Average Oracle") is appropriate before `corr_pairs.parquet` is read as signal?
3. Is a single 252-day snapshot an average over calm and stress sub-periods (the
   2111.05072 densification result)? A rolling variant would test this.
4. Does the pairs file's |r| >= 0.6 cut hold up once IN ETFs/funds are removed?
