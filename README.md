# Daily equity sector and international index panel (2005–2024)

Anonymous public compilation of daily equity series for replication of sector-level and cross-market dependence studies. Official S&P GICS sector total-return indices are proprietary, so this package uses publicly quoted sector ETFs as GICS-style proxies, together with major international equity indices and the Ken French 12 industry daily portfolios. A single zip archive of this release is attached on the repository Releases page.

## Coverage

| Panel | Series | Frequency | Sample | Aligned observations |
| --- | --- | --- | --- | --- |
| US sector ETFs | 11 GICS-style sectors | Daily | 2005-01-03 to 2024-12-31 | 5,033 price days; 5,032 return days |
| Sector + S&P 500 | 11 sectors + SPX | Daily | 2005-01-04 to 2024-12-31 | 5,032 return days |
| International indices | SPX, FTSE 100, DAX, Nikkei 225, Hang Seng, CAC 40 | Daily | 2005–2024 | 4,458 common trading days (inner join) |
| Fama–French 12 industries | 12 value-weighted industry portfolios | Daily | 2005-01-03 to 2024-12-31 | 5,033 return days |

## Files

```
series_map.csv
metadata.json
LICENSE
processed/
  sector_adj_close.csv
  sector_simple_returns.csv
  sector_with_spx_simple_returns.csv
  international_adj_close.csv
  international_simple_returns.csv
  ff12_industry_daily_returns.csv
raw/
  sector_etf_prices.csv
  international_index_prices.csv
  12_Industry_Portfolios_daily_CSV.zip
  12_Industry_Portfolios_Daily.csv
```

Processed return files are simple close-to-close returns from split- and dividend-adjusted prices (decimal, not percent). Dates are ISO `YYYY-MM-DD`.

## Ticker choices

Select Sector SPDRs (`XLF`, `XLE`, `XLK`, `XLV`, `XLI`, `XLY`, `XLP`, `XLB`, `XLU`) cover nine GICS sectors from 2005. Real Estate uses `IYR` rather than `XLRE` (inception 2015). Communication Services uses `VOX` rather than `XLC` (inception 2018). International series use Yahoo Finance index tickers `^GSPC`, `^FTSE`, `^GDAXI`, `^N225`, `^HSI`, and `^FCHI`. See `series_map.csv`.

## Sources

- Public daily quotes via the Yahoo Finance chart API
- Ken French Data Library, 12 Industry Portfolios (Daily)

This is a research convenience compilation, not a substitute for licensed index data from S&P Dow Jones Indices or the exchanges.

## License

CC BY 4.0 for the compilation. Cite the Ken French Data Library when using the industry-portfolio files.
