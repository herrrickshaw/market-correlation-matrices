import json

import duckdb
import numpy as np
import pandas as pd
import pytest

from conftest import DATES, market_rows, returns_panel, write_warehouse


def run_one(cc, rows, mkt="IN"):
    write_warehouse(cc.WAREHOUSE, rows)
    con = duckdb.connect(str(cc.WAREHOUSE), read_only=True)
    try:
        return cc.one_market(con, mkt)
    finally:
        con.close()


def load(cc, mkt="IN"):
    d = cc.OUT / mkt
    z = np.load(d / "corr_dense.npz", allow_pickle=True)
    pairs = duckdb.connect().execute(f"SELECT * FROM '{d / 'corr_pairs.parquet'}'").df()
    return z["corr"], z["symbols"], pairs, json.loads((d / "summary.json").read_text())


def oracle(rows, window=252):
    """Independent recomputation: last `window` full sessions, log returns, pairwise Pearson."""
    df = pd.DataFrame(rows, columns=["market", "Symbol", "Date", "Close", "Volume"])
    px = df.pivot(index="Date", columns="Symbol", values="Close").sort_index().iloc[-window:]
    return np.log(px).diff().corr(min_periods=200)


def test_matrix_matches_an_independent_pearson_and_is_symmetric(cc):
    rows = market_rows("IN")
    summary = run_one(cc, rows)
    corr, syms, pairs, _ = load(cc)
    assert list(syms) == list("ABCDEFGHIJ")                     # pivot columns are alphabetical
    assert corr.dtype == np.float16 and corr.shape == (10, 10)
    want = oracle(rows).to_numpy()
    np.testing.assert_allclose(corr.astype(np.float32), want, atol=2e-3)
    assert np.allclose(np.diag(corr.astype(np.float32)), 1.0, atol=1e-3)
    np.testing.assert_array_equal(corr, corr.T)
    assert summary["symbols"] == 10


def test_pairs_file_stores_each_strong_pair_once(cc):
    run_one(cc, market_rows("IN"))
    _, _, pairs, summary = load(cc)
    got = {(a, b): c for a, b, c in pairs.itertuples(index=False)}
    assert set(got) == {("A", "B"), ("A", "C"), ("B", "C")}      # upper triangle, i < j, |r| >= 0.6
    assert got[("A", "B")] == pytest.approx(1.0, abs=1e-4)
    assert got[("A", "C")] == pytest.approx(-1.0, abs=1e-4) and got[("B", "C")] == pytest.approx(-1.0, abs=1e-4)
    assert pairs["corr"].dtype == np.float32
    assert summary["pairs_stored"] == 3


def test_pair_threshold_is_inclusive_and_applies_to_absolute_correlation(cc, monkeypatch):
    rows = market_rows("IN")
    r_ab = np.float32(oracle(rows).loc["A", "B"])
    monkeypatch.setattr(cc, "PAIR_THRESHOLD", float(r_ab))          # exactly the pair's own correlation
    run_one(cc, rows)
    _, _, pairs, _ = load(cc)
    assert ("A", "B") in set(zip(pairs.sym1, pairs.sym2))           # >= keeps it
    monkeypatch.setattr(cc, "PAIR_THRESHOLD", float(np.nextafter(r_ab, np.float32(2.0))))
    run_one(cc, rows)
    assert ("A", "B") not in set(zip(load(cc)[2].sym1, load(cc)[2].sym2))
    # a lowered floor admits weaker pairs too, in both signs
    monkeypatch.setattr(cc, "PAIR_THRESHOLD", 0.0)
    run_one(cc, rows)
    assert len(load(cc)[2]) == 45                                    # all C(10,2) pairs


def test_summary_statistics_and_top_pairs(cc):
    rows = market_rows("IN")
    s = run_one(cc, rows)
    corr, _, pairs, on_disk = load(cc)
    assert s == on_disk
    full = oracle(rows).to_numpy()
    iu = np.triu_indices(10, k=1)
    finite = full[iu][np.isfinite(full[iu])]
    assert s["mean_pairwise_corr"] == pytest.approx(round(float(finite.mean()), 4), abs=2e-3)
    assert s["median_pairwise_corr"] == pytest.approx(round(float(np.median(finite)), 4), abs=2e-3)
    assert (s["market"], s["window_days"], s["symbols"]) == ("IN", 252, 10)
    top = s["top_pairs"]
    assert {tuple(sorted(t[:2])) for t in top} == {("A", "B"), ("A", "C"), ("B", "C")}
    assert len(top) == 3 and all(abs(t[2]) > 0.999 for t in top)       # only stored pairs are ranked
    assert [abs(t[2]) for t in top] == sorted((abs(t[2]) for t in top), reverse=True)


def test_top_pairs_capped_at_ten_and_sorted_by_magnitude(cc, monkeypatch):
    monkeypatch.setattr(cc, "PAIR_THRESHOLD", 0.0)
    s = run_one(cc, market_rows("IN"))
    mags = [abs(t[2]) for t in s["top_pairs"]]
    assert len(mags) == 10 and mags == sorted(mags, reverse=True)
    assert s["pairs_stored"] == 45


def test_window_is_the_latest_252_full_sessions(cc):
    rows = market_rows("IN")
    s = run_one(cc, rows)
    assert s["window"] == [str(DATES[-252].date()), str(DATES[-1].date())]


def test_partial_scrape_days_are_not_sessions(cc):
    # ref = median symbols per day = 10. A day with 4 symbols (< 50%) is dropped; one with exactly 5 is kept.
    partial = {250: list("ABCD"), 251: list("ABCDE")}
    rows = market_rows("IN", partial=partial)
    s = run_one(cc, rows)
    qualified = [d for i, d in enumerate(DATES) if i != 250]
    assert s["window"] == [str(qualified[-252].date()), str(DATES[-1].date())]
    assert str(DATES[250].date()) not in s["window"]


def test_session_fraction_constants(cc):
    assert (cc.WINDOW, cc.N_MAX, cc.MIN_OBS, cc.PAIR_THRESHOLD, cc.MIN_SESSION_FRAC) == (252, 3000, 200, 0.6, 0.5)
    assert cc.MARKETS == ["IN", "US", "JP", "KR", "CN", "EU"]


def test_symbols_need_two_hundred_return_observations(cc):
    rets = returns_panel()
    rows = market_rows("IN", rets)
    # K: 201 consecutive prices in the window = 200 returns (kept); L: 200 prices = 199 returns (dropped)
    extra = []
    rng = np.random.RandomState(9)
    for name, n_px in (("K", 201), ("L", 200)):
        px = 50 * np.exp(np.cumsum(rng.normal(0, 0.01, n_px)))
        for d, p in zip(DATES[-n_px:], px):
            extra.append(("IN", name, d, float(p), 1000.0))
    # the extra names would shift the session median, so give the base names a constant count of 10 and keep K/L partial
    s = run_one(cc, rows + extra)
    _, syms, _, _ = load(cc)
    assert "K" in set(syms) and "L" not in set(syms)
    assert s["symbols"] == 11


def test_liquidity_cap_keeps_the_highest_traded_value(cc, monkeypatch):
    rets = returns_panel()
    rows = []
    vols = {"A": 5000.0, "B": 4000.0, "C": 3000.0, "D": 2000.0}
    for mkt_rows in (market_rows("IN", rets),):
        for r in mkt_rows:
            rows.append((r[0], r[1], r[2], r[3], vols.get(r[1], 10.0)))
    monkeypatch.setattr(cc, "N_MAX", 3)
    s = run_one(cc, rows)
    _, syms, _, _ = load(cc)
    assert list(syms) == ["A", "B", "C"] and s["symbols"] == 3


def test_zero_volume_and_nonpositive_close_rows_are_ignored(cc):
    rows = market_rows("IN")
    dates_d = {DATES[i] for i in (100, 150, 200)}
    mod = []
    for m, s_, d, c, v in rows:
        if s_ == "D" and d in dates_d:
            v = 0.0                                                   # three untraded days for D
        if s_ == "E":
            c = -1.0                                                  # E never has a usable close
        if s_ == "F" and d.day % 2 == 0:
            v = 0.0                                                   # F trades on alternate days only
        mod.append((m, s_, d, c, v))
    s = run_one(cc, mod)
    _, syms, _, _ = load(cc)
    assert "D" in set(syms)                                           # a few missing days still leave >= 200 returns
    assert "E" not in set(syms)
    assert "F" not in set(syms)                                       # gaps on alternate days leave no consecutive pairs
    assert s["symbols"] == len(syms) == 8


def test_other_markets_are_not_mixed_in(cc):
    rows = market_rows("IN") + market_rows("US", returns_panel(seed=5))
    s = run_one(cc, rows)
    assert s["symbols"] == 10
    s_us = run_one(cc, rows, "US")
    assert s_us["market"] == "US" and (cc.OUT / "US" / "summary.json").exists()


def test_output_directory_is_created_and_files_are_written(cc):
    run_one(cc, market_rows("JP"), "JP")
    assert sorted(p.name for p in (cc.OUT / "JP").iterdir()) == ["corr_dense.npz", "corr_pairs.parquet", "summary.json"]


def test_main_writes_every_market_and_a_combined_summary(cc, capsys):
    rows = []
    for k, m in enumerate(["IN", "US", "JP", "KR", "CN", "EU"]):
        rows += market_rows(m, returns_panel(seed=k))
    write_warehouse(cc.WAREHOUSE, rows)
    cc.main()
    allsum = json.loads((cc.OUT / "summary_all.json").read_text())
    assert [s["market"] for s in allsum] == ["IN", "US", "JP", "KR", "CN", "EU"]
    out = capsys.readouterr().out
    assert "IN: 10 syms, mean r=" in out and "pairs|r|>=0.6: 3" in out
    for m in ("IN", "US", "JP", "KR", "CN", "EU"):
        assert (cc.OUT / m / "corr_dense.npz").exists()


def test_main_opens_the_warehouse_read_only(cc, monkeypatch):
    rows = market_rows("IN")
    write_warehouse(cc.WAREHOUSE, rows)
    monkeypatch.setattr(cc, "MARKETS", ["IN"])
    seen = {}
    real = duckdb.connect

    def spy(path, read_only=False):
        seen.update(path=path, read_only=read_only)
        return real(path, read_only=read_only)

    monkeypatch.setattr(cc.duckdb, "connect", spy)
    cc.main()
    assert seen == {"path": str(cc.WAREHOUSE), "read_only": True}


def test_warehouse_path_comes_from_the_environment(monkeypatch):
    import importlib, sys
    monkeypatch.setenv("WAREHOUSE", "/some/where.duckdb")
    sys.modules.pop("compute_correlations", None)
    m = importlib.import_module("compute_correlations")
    assert str(m.WAREHOUSE) == "/some/where.duckdb"
    sys.modules.pop("compute_correlations", None)


# ── boundary cases found by mutation testing ─────────────────────────────────
def test_pairs_file_is_zstd_compressed(cc):
    run_one(cc, market_rows("IN"))
    con = duckdb.connect()
    comp = con.execute(f"SELECT DISTINCT compression FROM parquet_metadata('{cc.OUT / 'IN' / 'corr_pairs.parquet'}')").fetchall()
    assert comp == [("ZSTD",)]


def test_session_reference_is_the_median_not_the_mean(cc):
    # 40 one-off symbols appear on 30 days, lifting the MEAN daily count to ~14.8 while the MEDIAN stays 10.
    # A day with exactly 5 symbols is >= 50% of the median (kept) but < 50% of the mean (would be dropped).
    rows = market_rows("IN", partial={250: list("ABCDE")})
    for k in range(40):
        for i in range(60, 90):
            rows.append(("IN", f"X{k:02d}", DATES[i], 10.0, 1000.0))
    s = run_one(cc, rows)
    assert s["window"][0] == str(DATES[-252].date())          # the 5-symbol day (index 250) stayed a session


def test_days_whose_bars_have_no_volume_are_not_sessions(cc):
    rows = market_rows("IN")
    rows = [(m, s_, d, c, 0.0 if (d == DATES[260] and s_ not in "ABC") else v) for m, s_, d, c, v in rows]
    s = run_one(cc, rows)
    # all ten symbols have a row that day, but only three traded: below half of the usual ten
    qualified = [d for i, d in enumerate(DATES) if i != 260]
    assert s["window"][0] == str(qualified[-252].date())


def test_a_zero_close_is_dropped_not_turned_into_minus_infinity(cc):
    rows = [(m, s_, d, 0.0 if (s_ == "D" and d == DATES[200]) else c, v) for m, s_, d, c, v in market_rows("IN")]
    run_one(cc, rows)
    corr, syms, _, _ = load(cc)
    d_idx = list(syms).index("D")
    assert np.isfinite(corr[d_idx].astype(np.float32)).all()


def test_duplicate_bars_keep_the_last_one(cc):
    rows = market_rows("IN")
    a_row = [r for r in rows if r[1] == "A" and r[2] == DATES[200]][0]
    rows.append((a_row[0], "A", a_row[2], a_row[3] * 3.0, a_row[4]))        # a later, wildly different print
    run_one(cc, rows)
    corr, syms, pairs, _ = load(cc)
    ab = float(corr[list(syms).index("A"), list(syms).index("B")])
    assert ab < 0.9                                                      # the tripled close broke the perfect match


def test_pairs_with_too_little_overlap_are_nan(cc):
    rets = returns_panel()
    rows = market_rows("IN", rets)
    rng = np.random.RandomState(4)
    for name, sl in (("K", slice(-252, -252 + 205)), ("L", slice(-205, None))):
        px = 50 * np.exp(np.cumsum(rng.normal(0, 0.01, 205)))
        for d, p in zip(DATES[sl], px):
            rows.append(("IN", name, d, float(p), 1000.0))
    run_one(cc, rows)
    corr, syms, pairs, _ = load(cc)
    names = list(syms)
    assert "K" in names and "L" in names                                 # each has 204 returns
    assert np.isnan(corr[names.index("K"), names.index("L")])            # but they overlap on only ~158 days
    assert np.isfinite(corr[names.index("K"), names.index("A")])         # K vs a full-history name overlaps 204 days
