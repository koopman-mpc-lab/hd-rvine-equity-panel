"""Build an anonymous, analysis-ready public data release for the HD-RVine paper.

Sources (public market quotes and the Ken French Data Library):
  - GICS-style US sector ETFs with full 2005-2024 history
  - Major international equity indices (or country ETFs if an index feed fails)
  - Fama-French 12 industry daily portfolios as a same-type public panel
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data_release"
RAW = OUT / "raw"
PROC = OUT / "processed"
OUT.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)
PROC.mkdir(exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
PERIOD1 = int(datetime(2005, 1, 1, tzinfo=timezone.utc).timestamp())
PERIOD2 = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
START = date(2005, 1, 3)
END = date(2024, 12, 31)

SECTOR = [
    ("FIN", "XLF", "Financial Select Sector SPDR (GICS Financials proxy)"),
    ("EN", "XLE", "Energy Select Sector SPDR (GICS Energy proxy)"),
    ("IT", "XLK", "Technology Select Sector SPDR (GICS Information Technology proxy)"),
    ("HC", "XLV", "Health Care Select Sector SPDR (GICS Health Care proxy)"),
    ("IND", "XLI", "Industrial Select Sector SPDR (GICS Industrials proxy)"),
    ("CD", "XLY", "Consumer Discretionary Select Sector SPDR"),
    ("CS", "XLP", "Consumer Staples Select Sector SPDR"),
    ("MAT", "XLB", "Materials Select Sector SPDR"),
    ("UTIL", "XLU", "Utilities Select Sector SPDR"),
    ("RE", "IYR", "iShares U.S. Real Estate ETF (full-history GICS Real Estate proxy; XLRE starts 2015)"),
    ("TEL", "VOX", "Vanguard Communication Services ETF (full-history GICS Communication proxy; XLC starts 2018)"),
]
SECTOR_ALTS = {"RE": ["IYR", "XLRE"], "TEL": ["VOX", "IYZ", "XLC"]}
INTL = [
    ("SPX", "^GSPC", "S&P 500"),
    ("FTSE", "^FTSE", "FTSE 100"),
    ("DAX", "^GDAXI", "DAX"),
    ("N225", "^N225", "Nikkei 225"),
    ("HSI", "^HSI", "Hang Seng"),
    ("CAC", "^FCHI", "CAC 40"),
]
INTL_ALTS = {
    "SPX": ["^GSPC", "SPY"],
    "FTSE": ["^FTSE", "EWU", "ISF.L"],
    "DAX": ["^GDAXI", "EWG", "EXS1.DE"],
    "N225": ["^N225", "EWJ"],
    "HSI": ["^HSI", "EWH"],
    "CAC": ["^FCHI", "EWQ"],
}
FF_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/12_Industry_Portfolios_daily_CSV.zip"


def http_get(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def yahoo_chart(symbol: str) -> list[tuple[date, float, float]]:
    quoted = urllib.parse.quote(symbol, safe="")
    url = (
        "https://query2.finance.yahoo.com/v8/finance/chart/"
        f"{quoted}?period1={PERIOD1}&period2={PERIOD2}&interval=1d"
        "&events=div%7Csplit&includeAdjustedClose=true"
    )
    raw = http_get(url)
    payload = json.loads(raw.decode("utf-8"))
    err = payload.get("chart", {}).get("error")
    result = payload.get("chart", {}).get("result")
    if err or not result:
        raise RuntimeError(f"yahoo chart failed for {symbol}: {err}")
    node = result[0]
    ts = node.get("timestamp") or []
    quote = (node.get("indicators") or {}).get("quote") or [{}]
    adj = (node.get("indicators") or {}).get("adjclose") or [{}]
    closes = quote[0].get("close") or []
    adjc = adj[0].get("adjclose") or closes
    rows = []
    for t, c, a in zip(ts, closes, adjc):
        if c is None and a is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date()
        if d < START or d > END:
            continue
        px = float(a if a is not None else c)
        close = float(c if c is not None else a)
        if px <= 0:
            continue
        rows.append((d, close, px))
    return rows


def fetch_symbol(symbol: str, retries: int = 4) -> list[tuple[date, float, float]]:
    last = None
    for i in range(retries):
        try:
            rows = yahoo_chart(symbol)
            if len(rows) < 200:
                raise RuntimeError(f"too few rows for {symbol}: {len(rows)}")
            return rows
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"failed {symbol}: {last}")


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def simple_returns(dates: list[date], px: list[float]) -> list[list[object]]:
    out = []
    for i in range(1, len(dates)):
        if px[i - 1] > 0 and px[i] > 0:
            out.append([dates[i].isoformat(), px[i] / px[i - 1] - 1.0])
    return out


def align_panel(series: dict[str, list[tuple[date, float]]]) -> tuple[list[str], list[list[object]]]:
    names = list(series.keys())
    common = None
    maps = {}
    for name, rows in series.items():
        m = {d: v for d, v in rows}
        maps[name] = m
        keys = set(m)
        common = keys if common is None else common & keys
    dates = sorted(common or [])
    rows = []
    for d in dates:
        rows.append([d.isoformat()] + [maps[n][d] for n in names])
    return names, rows


def parse_ff12(blob: bytes) -> tuple[list[str], list[list[object]]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        name = zf.namelist()[0]
        text = zf.read(name).decode("latin-1")
    RAW.joinpath("12_Industry_Portfolios_Daily.csv").write_text(text, encoding="utf-8")
    lines = text.splitlines()
    header_idx = None
    names = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("date") or (
            "," in line and "NoDur" in line.replace(" ", "")
        ):
            parts = [p.strip() for p in line.replace("\t", " ").split() if p.strip()]
            if len(parts) >= 10:
                header_idx = i
                names = parts[1:]
                break
        if "NoDur" in line and "Durbl" in line:
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if len(parts) >= 10:
                header_idx = i
                names = parts[1:] if parts[0].lower().startswith("date") else parts
                break
    if header_idx is None:
        # Ken French files are space-delimited after a preamble
        for i, line in enumerate(lines):
            if line.strip()[:6].isdigit() and len(line.split()) >= 12:
                header_idx = i - 1
                names = lines[i - 1].split()
                break
    if not names:
        raise RuntimeError("could not parse Fama-French 12 industry header")
    rows = []
    value_start = header_idx + 1
    for line in lines[value_start:]:
        s = line.strip()
        if not s or s[0].isalpha() or s.startswith("Copyright") or s.startswith("Annual"):
            if rows:
                break
            continue
        parts = s.replace(",", " ").split()
        if len(parts) < 2:
            continue
        ds = parts[0]
        if len(ds) != 8 or not ds.isdigit():
            if rows:
                break
            continue
        d = date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
        if d < START or d > END:
            continue
        vals = []
        ok = True
        for p in parts[1 : 1 + len(names)]:
            try:
                v = float(p)
            except ValueError:
                ok = False
                break
            # missing code in FF files
            if v <= -99:
                ok = False
                break
            vals.append(v / 100.0)  # percent to decimal
        if ok and len(vals) == len(names):
            rows.append([d.isoformat()] + vals)
    return names, rows


def main() -> None:
    provenance = []
    sector_px: dict[str, list[tuple[date, float]]] = {}
    sector_raw_rows = [["date", "code", "symbol", "close", "adj_close"]]
    print("downloading sector ETFs")
    for code, symbol, label in SECTOR:
        candidates = [symbol] + [c for c in SECTOR_ALTS.get(code, []) if c != symbol]
        last_err = None
        got = None
        used = None
        for cand in candidates:
            try:
                print(" ", cand)
                rows = fetch_symbol(cand)
                time.sleep(1.2)
                got = rows
                used = cand
                break
            except Exception as exc:
                last_err = exc
                print("   fail", cand, exc)
                time.sleep(2.0)
        if not got:
            raise RuntimeError(f"sector {code} failed: {last_err}")
        sector_px[code] = [(d, a) for d, _, a in got]
        for d, c, a in got:
            sector_raw_rows.append([d.isoformat(), code, used, f"{c:.8f}", f"{a:.8f}"])
        provenance.append(
            {
                "panel": "sector",
                "code": code,
                "symbol": used,
                "label": label,
                "nobs": len(got),
                "start": got[0][0].isoformat(),
                "end": got[-1][0].isoformat(),
            }
        )

    print("downloading international indices")
    intl_px: dict[str, list[tuple[date, float]]] = {}
    intl_raw_rows = [["date", "code", "symbol", "close", "adj_close"]]
    for code, symbol, label in INTL:
        candidates = INTL_ALTS.get(code, [symbol])
        last_err = None
        got = None
        used = None
        for cand in candidates:
            try:
                print(" ", cand)
                rows = fetch_symbol(cand)
                time.sleep(1.2)
                got = rows
                used = cand
                break
            except Exception as exc:
                last_err = exc
                print("   fail", cand, exc)
                time.sleep(2.0)
        if not got:
            raise RuntimeError(f"intl {code} failed: {last_err}")
        intl_px[code] = [(d, a) for d, _, a in got]
        for d, c, a in got:
            intl_raw_rows.append([d.isoformat(), code, used, f"{c:.8f}", f"{a:.8f}"])
        provenance.append(
            {
                "panel": "international",
                "code": code,
                "symbol": used,
                "label": label,
                "nobs": len(got),
                "start": got[0][0].isoformat(),
                "end": got[-1][0].isoformat(),
            }
        )

    print("downloading Fama-French 12 industry daily")
    ff_blob = http_get(FF_URL)
    RAW.joinpath("12_Industry_Portfolios_daily_CSV.zip").write_bytes(ff_blob)
    ff_names, ff_rows = parse_ff12(ff_blob)

    write_csv(RAW / "sector_etf_prices.csv", sector_raw_rows[0], sector_raw_rows[1:])
    write_csv(RAW / "international_index_prices.csv", intl_raw_rows[0], intl_raw_rows[1:])

    sec_names, sec_px_rows = align_panel(sector_px)
    intl_names, intl_px_rows = align_panel(intl_px)
    write_csv(PROC / "sector_adj_close.csv", ["date"] + sec_names, sec_px_rows)
    write_csv(PROC / "international_adj_close.csv", ["date"] + intl_names, intl_px_rows)

    def px_to_ret(names, px_rows):
        out = []
        prev = None
        for row in px_rows:
            d, vals = row[0], [float(x) for x in row[1:]]
            if prev is None:
                prev = vals
                continue
            rets = []
            ok = True
            for a, b in zip(prev, vals):
                if a <= 0 or b <= 0:
                    ok = False
                    break
                rets.append(b / a - 1.0)
            if ok:
                out.append([d] + rets)
            prev = vals
        return out

    sec_ret = px_to_ret(sec_names, sec_px_rows)
    intl_ret = px_to_ret(intl_names, intl_px_rows)
    write_csv(
        PROC / "sector_simple_returns.csv",
        ["date"] + sec_names,
        [[r[0]] + [f"{x:.10f}" for x in r[1:]] for r in sec_ret],
    )
    write_csv(
        PROC / "international_simple_returns.csv",
        ["date"] + intl_names,
        [[r[0]] + [f"{x:.10f}" for x in r[1:]] for r in intl_ret],
    )
    write_csv(
        PROC / "ff12_industry_daily_returns.csv",
        ["date"] + ff_names,
        [[r[0]] + [f"{float(x):.10f}" for x in r[1:]] for r in ff_rows],
    )

    meta = {
        "title": "Daily equity sector and international index panel, 2005-2024",
        "version": "1.0.0",
        "coverage": {"start": START.isoformat(), "end": END.isoformat()},
        "panels": {
            "sector": {
                "description": "GICS-style US sector total-return proxies from publicly quoted ETFs.",
                "n_series": len(sec_names),
                "n_common_price_days": len(sec_px_rows),
                "n_return_days": len(sec_ret),
                "codes": sec_names,
            },
            "international": {
                "description": "Major international equity indices used for external validation.",
                "n_series": len(intl_names),
                "n_common_price_days": len(intl_px_rows),
                "n_return_days": len(intl_ret),
                "codes": intl_names,
            },
            "ff12": {
                "description": "Fama-French 12 industry daily value-weighted returns, same-type public database.",
                "n_series": len(ff_names),
                "n_return_days": len(ff_rows),
                "codes": ff_names,
            },
        },
        "provenance": provenance,
        "notes": [
            "Official S&P GICS sector total-return indices are proprietary; publicly quoted Select Sector / sector ETFs are used as research proxies.",
            "Real Estate uses IYR rather than XLRE to cover 2005-2015; Communication uses VOX rather than XLC to cover 2005-2018.",
            "Returns are simple close-to-close returns from split/dividend-adjusted prices where available.",
            "The Fama-French 12 industry file is redistributed from the Ken French Data Library for convenience; please cite that library in addition to this compilation.",
        ],
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta["panels"][k] for k in meta["panels"]}, indent=2))
    print("done")


if __name__ == "__main__":
    main()
