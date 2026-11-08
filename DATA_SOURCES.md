
```markdown
# DATA_SOURCES.md - market-correlation-matrices

Status as of 2026-11-08. This repo publishes only derived statistics. It does not contain raw prices.
Research and education only; not investment advice.

## 1. Upstream inputs (not redistributed)

### 1.1 Daily adjusted/raw close and volume, six markets
- Publisher(s): Yahoo Finance (via yfinance) for US, JP, KR, CN, EU; NSE/BSE bhavcopy for IN. Stooq is a fallback in the upstream warehouse.
- Held in: private `global-market-data/warehouse/warehouse.duckdb` (view `ohlcv`). Not in this repo.
- Terms: Yahoo API terms prohibit sharing/sublicensing the API data (https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html). NSE permits research-oriented download within a 2 GB threshold and does not grant redistribution (https://www.nseindia.com/nse-disclaimer). Only derived correlation statistics are published here.
- Fields used: Symbol, Date, Close, Volume (Close*Volume as traded value for liquidity ranking).
- Coverage: IN, US, JP, KR, CN, EU; 252 trading days ending between 2026-06-29 and 2026-07-21 (see section 3).
- Refresh: manual rebuild via `compute_correlations.py` (about 2 minutes). Not scheduled.
- Caveats: raw vs split-adjusted close differs by market; ticker renames create duplicate series; ETFs and funds are included.

## 2. Published datasets (this repo)

### 2.1 `data/<MARKET>/corr_dense.npz`
- Pairwise-complete Pearson correlation of daily log returns, float16, with `symbols` array. Universe: top 3,000 symbols by traded value in window, >= 200 return observations.
- Known quirks: float16 quantisation (about 3 decimals); NaN where pairs have < 200 common observations (IN 1.28%, KR 2.32%, EU 1.95% of cells); includes ETFs/funds (IN, US) and duplicate listings.
- Licence: derived statistics; publish under CC BY 4.0 with the notice in section 4.

### 2.2 `data/<MARKET>/corr_pairs.parquet`
- Columns `sym1, sym2, corr`; upper triangle, |r| >= 0.6. Rows: IN 20,658; US 14,503; JP 5,223; KR 7,370; CN 7,376; EU 403.
- Caveat: r = 1.0 pairs are mostly same-issuer series (renamed tickers, twin ETFs); do not read as stock-pair signals.

### 2.3 `data/<MARKET>/summary.json`, `data/summary_all.json`
- window, universe size, mean/median pairwise r, top-10 pairs.

### 2.4 `data/{IN,JP,KR,EU}/*_correlation_matrix.parquet` (UNDOCUMENTED - resolve before publishing)
- Wide format (Symbol + one column per symbol). Universe larger than 2.1 (IN 2,234; JP 3,544; KR 2,726; EU 927). Generator and window unknown; either document or delete.

## 3. Data currency
| Market | Window start | Window end | Symbols |
|---|---|---|---|
| IN | 2025-07-10 | 2026-07-21 | 2,001 |
| US | 2025-07-18 | 2026-07-20 | 2,945 |
| JP | 2025-06-19 | 2026-07-01 | 2,998 |
| KR | 2025-06-23 | 2026-07-02 | 2,570 |
| CN | 2025-06-18 | 2026-07-01 | 2,978 |
| EU | 2025-07-04 | 2026-06-29 | 842 |
Windows are not aligned; none is current.

## 4. Attribution notice (proposed)
"Correlations computed by the repository owner from daily prices originally obtained from Yahoo Finance and NSE/BSE bhavcopy. The raw prices are not redistributed. Provided as is, for research."

## 5. Planned additions (open sources verified reachable 2026-11-08)
GLEIF ISIN-LEI (CC0) and Wikidata (CC0) for issuer de-duplication; Nasdaq Trader and NSE equity masters for ETF/bond filtering; OFR Financial Stress Index and ECB FX for regime-conditional and USD-converted matrices; TWSE OpenAPI to add Taiwan.
```
