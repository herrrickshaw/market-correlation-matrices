#!/usr/bin/env python3
"""Per-market equity correlation matrices from the unified OHLCV warehouse.

Source: ~/repos/global-market-data/warehouse/warehouse.duckdb (view `ohlcv`) —
the deduplicated, year-partitioned successor to the retired LFS monoliths.

Per market:
  - window: last 252 trading days of that market
  - universe: top N_MAX symbols by traded value (close*volume) in the window,
    keeping only symbols with >= MIN_OBS return observations
  - Pearson correlation of daily log returns (pairwise-complete)

Artifacts under data/<MARKET>/ (all regular git objects, no LFS):
  corr_dense.npz         float16 dense matrix + symbol list (np.load; keys: corr, symbols)
  corr_pairs.parquet     upper-triangle pairs with |r| >= PAIR_THRESHOLD (zstd)
  summary.json           window, universe size, mean/median pairwise corr, top pairs

Storing giant dense CSVs (the old ~/Downloads/data/*_scan files, up to 837 MB)
is the anti-pattern this repo replaces: same information, ~50x smaller,
rebuildable with one command.
"""
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

WAREHOUSE = Path.home() / "repos/global-market-data/warehouse/warehouse.duckdb"
OUT = Path(__file__).resolve().parent / "data"
MARKETS = ["IN", "US", "JP", "KR", "CN", "EU"]
WINDOW = 252          # trading days
N_MAX = 3000          # liquidity cap per market
MIN_OBS = 200         # min return observations per symbol
PAIR_THRESHOLD = 0.6  # |r| floor for the long-format pairs file


def one_market(con, mkt):
    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT Date FROM ohlcv WHERE market=? ORDER BY Date DESC LIMIT ?",
        [mkt, WINDOW]).fetchall()]
    d0 = min(dates)
    df = con.execute(
        """SELECT Symbol, Date, Close, Close*Volume AS tv
           FROM ohlcv WHERE market=? AND Date>=? AND Close>0""",
        [mkt, d0]).df()
    # liquidity cap
    top = (df.groupby("Symbol")["tv"].sum().sort_values(ascending=False)
             .head(N_MAX).index)
    px = (df[df["Symbol"].isin(top)]
          .pivot_table(index="Date", columns="Symbol", values="Close", aggfunc="last")
          .sort_index())
    rets = np.log(px).diff()
    rets = rets.loc[:, rets.notna().sum() >= MIN_OBS]
    corr = rets.corr(min_periods=MIN_OBS)          # pairwise-complete Pearson
    syms = corr.columns.to_numpy()
    m = corr.to_numpy(dtype=np.float32)

    mdir = OUT / mkt
    mdir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(mdir / "corr_dense.npz",
                        corr=m.astype(np.float16), symbols=syms)

    iu = np.triu_indices(len(syms), k=1)
    r = m[iu]
    keep = np.abs(r) >= PAIR_THRESHOLD
    pairs = pd.DataFrame({"sym1": syms[iu[0][keep]], "sym2": syms[iu[1][keep]],
                          "corr": r[keep].astype(np.float32)})
    duckdb.from_df(pairs).write_parquet(str(mdir / "corr_pairs.parquet"),
                                        compression="zstd")

    finite = r[np.isfinite(r)]
    order = np.argsort(-np.abs(pairs["corr"].to_numpy()))[:10]
    summary = dict(
        market=mkt, window_days=WINDOW,
        window=[str(pd.Timestamp(d0).date()), str(pd.Timestamp(max(dates)).date())],
        symbols=int(len(syms)), pairs_stored=int(keep.sum()),
        mean_pairwise_corr=round(float(np.nanmean(finite)), 4),
        median_pairwise_corr=round(float(np.nanmedian(finite)), 4),
        top_pairs=[[str(pairs.iloc[i]["sym1"]), str(pairs.iloc[i]["sym2"]),
                    round(float(pairs.iloc[i]["corr"]), 4)] for i in order],
    )
    (mdir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(f"{mkt}: {len(syms)} syms, mean r={summary['mean_pairwise_corr']}, "
          f"pairs|r|>={PAIR_THRESHOLD}: {keep.sum():,}")
    return summary


def main():
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    summaries = [one_market(con, m) for m in MARKETS]
    (OUT / "summary_all.json").write_text(json.dumps(summaries, indent=1))
    con.close()


if __name__ == "__main__":
    main()
