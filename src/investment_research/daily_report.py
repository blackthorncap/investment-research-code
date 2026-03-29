"""
Daily investment report generator.

Fetches market data via yfinance, generates charts, and produces a markdown report
saved to the reports repository under reports/YYYY/MM/DD/daily_report.md
"""

import os
import sys
import argparse
from datetime import datetime, date
from pathlib import Path

import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


# Tickers to track in the daily report
WATCHLIST = [
    "CSPX.L",   # iShares Core S&P 500 UCITS ETF (LSE) — was SPY
    "EQQQ.L",   # Invesco EQQQ Nasdaq-100 UCITS ETF (LSE) — was QQQ
    "IDVY.L",   # iShares Euro Dividend UCITS ETF (LSE) — was DIA
    "SGLN.L",   # iShares Physical Gold ETC (LSE) — was GLD
    "IDTL.L",   # iShares $ Treasury Bond 20+yr UCITS ETF (LSE) — was TLT
    "BTC-USD",  # Bitcoin (reference price, keep as-is)
]

SECTOR_ETFS = {
    "Technology": "EXV5.DE",          # iShares STOXX Europe 600 Technology
    "Healthcare": "EXV4.DE",          # iShares STOXX Europe 600 Health Care
    "Financials": "EXV1.DE",          # iShares STOXX Europe 600 Banks
    "Energy": "EXV2.DE",              # iShares STOXX Europe 600 Oil & Gas
    "Consumer Disc.": "EXH3.DE",      # iShares STOXX Europe 600 Retail
    "Utilities": "EXV3.DE",           # iShares STOXX Europe 600 Utilities
}


def fetch_market_data(tickers: list[str], period: str = "5d") -> dict:
    """Fetch market data for the given tickers."""
    data = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if not hist.empty:
                data[ticker] = hist
        except Exception as e:
            print(f"Warning: could not fetch {ticker}: {e}", file=sys.stderr)
    return data


def fetch_ticker_info(ticker: str) -> dict:
    """Fetch summary info for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "name": info.get("longName") or info.get("shortName") or ticker,
            "price": info.get("regularMarketPrice") or info.get("currentPrice"),
            "change_pct": info.get("regularMarketChangePercent"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        }
    except Exception as e:
        print(f"Warning: could not fetch info for {ticker}: {e}", file=sys.stderr)
        return {}


def generate_price_chart(data: dict, output_path: Path, title: str = "Market Overview") -> None:
    """Generate a normalized price chart for multiple tickers."""
    fig, ax = plt.subplots(figsize=(12, 6))

    for ticker, hist in data.items():
        if hist.empty:
            continue
        # Normalize to 100 at start
        normalized = (hist["Close"] / hist["Close"].iloc[0]) * 100
        ax.plot(hist.index, normalized, label=ticker, linewidth=1.5)

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel("Normalized Price (base=100)")
    ax.set_xlabel("Date")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def generate_sector_chart(sector_data: dict, output_path: Path, report_date: date) -> None:
    """Generate a bar chart of sector ETF daily returns."""
    returns = {}
    for sector, ticker in SECTOR_ETFS.items():
        if ticker in sector_data and not sector_data[ticker].empty:
            hist = sector_data[ticker]
            if len(hist) >= 2:
                ret = (hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100
                returns[sector] = ret

    if not returns:
        return

    sectors = list(returns.keys())
    values = list(returns.values())
    colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in values]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(sectors, values, color=colors, edgecolor="white", linewidth=0.5)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title(f"Sector Performance — {report_date.strftime('%B %d, %Y')}", fontsize=13, fontweight="bold")
    ax.set_ylabel("Daily Return (%)")
    ax.set_xlabel("")

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + (0.02 if val >= 0 else -0.06),
            f"{val:+.2f}%",
            ha="center", va="bottom", fontsize=8,
        )

    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def format_change(pct: float | None) -> str:
    if pct is None:
        return "N/A"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def build_report(
    report_date: date,
    market_data: dict,
    sector_data: dict,
    price_chart_path: str,
    sector_chart_path: str,
) -> str:
    """Build the markdown report."""
    lines = []
    lines.append(f"# Daily Investment Report — {report_date.strftime('%B %d, %Y')}")
    lines.append("")
    lines.append(f"*Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*")
    lines.append("")

    # Market summary table
    lines.append("## Market Summary")
    lines.append("")
    lines.append("| Ticker | Last Close | 5-Day Change |")
    lines.append("|--------|-----------|-------------|")

    for ticker in WATCHLIST:
        if ticker in market_data and not market_data[ticker].empty:
            hist = market_data[ticker]
            last = hist["Close"].iloc[-1]
            if len(hist) >= 5:
                change = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                change_str = format_change(change)
            else:
                change_str = "N/A"
            lines.append(f"| {ticker} | {last:,.2f} | {change_str} |")

    lines.append("")

    # Charts
    lines.append("## Price Performance (5-Day)")
    lines.append("")
    lines.append(f"![Market Overview]({price_chart_path})")
    lines.append("")

    lines.append("## Sector Performance")
    lines.append("")
    lines.append(f"![Sector Returns]({sector_chart_path})")
    lines.append("")

    # Sector detail
    lines.append("## Sector Detail")
    lines.append("")
    lines.append("| Sector | ETF | Daily Return |")
    lines.append("|--------|-----|-------------|")
    for sector, ticker in SECTOR_ETFS.items():
        if ticker in sector_data and not sector_data[ticker].empty:
            hist = sector_data[ticker]
            if len(hist) >= 2:
                ret = (hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100
                lines.append(f"| {sector} | {ticker} | {format_change(ret)} |")
    lines.append("")

    lines.append("---")
    lines.append("*Data sourced from Yahoo Finance via yfinance. Not financial advice.*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate daily investment report")
    parser.add_argument("--date", default=None, help="Report date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--reports-dir", default="../investment-research-reports", help="Path to reports repository")
    args = parser.parse_args()

    report_date = date.fromisoformat(args.date) if args.date else date.today()
    reports_dir = Path(args.reports_dir)

    # Create output directory
    out_dir = reports_dir / "reports" / report_date.strftime("%Y/%m/%d")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating daily report for {report_date}...")

    # Fetch data
    print("Fetching market data...")
    market_data = fetch_market_data(WATCHLIST)
    sector_tickers = list(SECTOR_ETFS.values())
    sector_data = fetch_market_data(sector_tickers)

    # Generate charts
    price_chart = out_dir / "market_overview.png"
    sector_chart = out_dir / "sector_performance.png"

    print("Generating charts...")
    generate_price_chart(market_data, price_chart)
    generate_sector_chart(sector_data, sector_chart, report_date)

    # Build report
    report_md = build_report(
        report_date,
        market_data,
        sector_data,
        price_chart_path="market_overview.png",
        sector_chart_path="sector_performance.png",
    )

    report_path = out_dir / "daily_report.md"
    report_path.write_text(report_md)
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
