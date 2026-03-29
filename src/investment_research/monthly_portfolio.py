"""
Monthly portfolio recommendation generator.

Analyzes a universe of equities using yfinance, scores them on momentum,
valuation, and fundamentals, and produces a markdown portfolio report saved to
the reports repository under reports/YYYY/MM/portfolio.md
"""

import os
import sys
import argparse
import json
from datetime import datetime, date
from pathlib import Path
from calendar import monthrange

import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# Universe of tickers to analyse for monthly portfolio
UNIVERSE = {
    # European Large Cap
    "ASML.AS": "ASML",
    "NOVN.SW": "Novartis",
    "ROG.SW": "Roche",
    "SAP.DE": "SAP",
    "SHEL.L": "Shell",
    "TTE.PA": "TotalEnergies",
    "MC.PA": "LVMH",
    "BNP.PA": "BNP Paribas",
    "SIE.DE": "Siemens",
    "ALV.DE": "Allianz",
    # UCITS ETFs
    "CSPX.L": "S&P 500 UCITS",
    "EQQQ.L": "Nasdaq-100 UCITS",
    "SGLN.L": "Physical Gold",
    "IDTL.L": "US Treasury 20Y UCITS",
    "IPRP.L": "European Property UCITS",
}

PORTFOLIO_SIZE = 5  # Top picks


def fetch_monthly_data(tickers: list[str], months: int = 6) -> dict:
    """Fetch historical data for the past N months."""
    period = f"{months * 30}d"
    data = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if not hist.empty:
                data[ticker] = hist
        except Exception as e:
            print(f"Warning: {ticker}: {e}", file=sys.stderr)
    return data


def compute_momentum_score(hist: pd.DataFrame) -> float:
    """12-1 month momentum: return from start to one month ago."""
    if len(hist) < 20:
        return 0.0
    recent = hist["Close"].iloc[-1]
    one_month_ago = hist["Close"].iloc[-20]
    three_month_ago = hist["Close"].iloc[max(0, len(hist) - 60)]
    # Weight recent momentum higher
    m1 = (recent / one_month_ago - 1) * 100
    m3 = (recent / three_month_ago - 1) * 100
    return 0.6 * m1 + 0.4 * m3


def compute_volatility(hist: pd.DataFrame) -> float:
    """Annualised volatility from daily returns."""
    if len(hist) < 5:
        return 999.0
    returns = hist["Close"].pct_change().dropna()
    return returns.std() * (252 ** 0.5) * 100


def score_tickers(data: dict) -> pd.DataFrame:
    """Score each ticker on momentum and risk-adjusted momentum."""
    rows = []
    for ticker, hist in data.items():
        mom = compute_momentum_score(hist)
        vol = compute_volatility(hist)
        sharpe_proxy = mom / vol if vol > 0 else 0
        last_price = hist["Close"].iloc[-1]
        mtd = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100

        rows.append({
            "ticker": ticker,
            "name": UNIVERSE.get(ticker, ticker),
            "last_price": last_price,
            "momentum": mom,
            "volatility": vol,
            "sharpe_proxy": sharpe_proxy,
            "mtd_return": mtd,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Rank by sharpe_proxy (momentum/vol)
    df = df.sort_values("sharpe_proxy", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df


HOLDINGS_FILENAME = "holdings.json"


def load_previous_holdings(reports_dir: Path, report_date: date) -> dict | None:
    """Load holdings from the previous month's report, if it exists."""
    # Compute previous month
    if report_date.month == 1:
        prev_year, prev_month = report_date.year - 1, 12
    else:
        prev_year, prev_month = report_date.year, report_date.month - 1

    prev_holdings_path = (
        reports_dir / "reports" / f"{prev_year:04d}" / f"{prev_month:02d}" / HOLDINGS_FILENAME
    )
    if not prev_holdings_path.exists():
        return None
    try:
        with open(prev_holdings_path) as f:
            data = json.load(f)
        return data.get("holdings", {})
    except Exception as e:
        print(f"Warning: could not load previous holdings: {e}", file=sys.stderr)
        return None


def save_holdings(top_df: pd.DataFrame, report_date: date, out_dir: Path) -> None:
    """Persist this month's portfolio holdings as JSON for future comparison."""
    n = len(top_df)
    weight = round(1.0 / n, 6) if n > 0 else 0.0
    holdings = {row.ticker: weight for row in top_df.itertuples()}
    data = {
        "date": report_date.strftime("%Y-%m"),
        "holdings": holdings,
    }
    holdings_path = out_dir / HOLDINGS_FILENAME
    with open(holdings_path, "w") as f:
        json.dump(data, f, indent=2)


def compute_portfolio_changes(
    prev_holdings: dict | None,
    top_df: pd.DataFrame,
) -> dict:
    """
    Compare previous holdings with current top picks.

    Returns a dict with keys:
      - buy: list of (ticker, name, weight)
      - sell: list of (ticker, weight_was)
      - hold: list of (ticker, name, weight_was, weight_now, weight_delta)
    """
    n = len(top_df)
    weight_now = round(1.0 / n, 6) if n > 0 else 0.0
    current = {row.ticker: (row.name, weight_now) for row in top_df.itertuples()}

    if prev_holdings is None:
        # First run — everything is a buy
        return {
            "buy": [(t, name, w) for t, (name, w) in current.items()],
            "sell": [],
            "hold": [],
            "first_run": True,
        }

    prev_set = set(prev_holdings.keys())
    curr_set = set(current.keys())

    buys = []
    for t in sorted(curr_set - prev_set):
        name, w = current[t]
        buys.append((t, name, w))

    sells = []
    for t in sorted(prev_set - curr_set):
        sells.append((t, prev_holdings[t]))

    holds = []
    for t in sorted(curr_set & prev_set):
        name, w_now = current[t]
        w_was = prev_holdings[t]
        holds.append((t, name, w_was, w_now, w_now - w_was))

    return {"buy": buys, "sell": sells, "hold": holds, "first_run": False}


def generate_allocation_chart(top_df: pd.DataFrame, output_path: Path) -> None:
    """Equal-weight allocation pie chart."""
    n = len(top_df)
    labels = [f"{row.ticker}\n({row.name})" for row in top_df.itertuples()]
    sizes = [1 / n] * n

    colors = plt.cm.Set3.colors[:n]  # type: ignore
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.pie(sizes, labels=labels, colors=colors, autopct="%1.0f%%", startangle=90,
           textprops={"fontsize": 9})
    ax.set_title("Recommended Portfolio Allocation (Equal Weight)", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def generate_momentum_chart(df: pd.DataFrame, output_path: Path) -> None:
    """Bar chart of momentum scores for the full universe."""
    df_sorted = df.sort_values("momentum", ascending=True)
    colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in df_sorted["momentum"]]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(df_sorted["ticker"], df_sorted["momentum"], color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Momentum Score (%)")
    ax.set_title("Universe Momentum Scores", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def build_portfolio_changes_section(changes: dict) -> list[str]:
    """Render the Portfolio Changes section as markdown lines."""
    lines = []
    lines.append("## Portfolio Changes")
    lines.append("")

    if changes.get("first_run"):
        lines.append(
            "_No previous portfolio data found. This is the first run — all positions are new entries._"
        )
        lines.append("")

    buys = changes.get("buy", [])
    sells = changes.get("sell", [])
    holds = changes.get("hold", [])

    if buys:
        lines.append("### Buy (new positions)")
        lines.append("")
        lines.append("| Ticker | Name | Weight |")
        lines.append("|--------|------|--------|")
        for ticker, name, weight in buys:
            lines.append(f"| {ticker} | {name} | {weight * 100:.1f}% |")
        lines.append("")

    if sells:
        lines.append("### Sell (exiting positions)")
        lines.append("")
        lines.append("| Ticker | Previous Weight |")
        lines.append("|--------|----------------|")
        for ticker, weight_was in sells:
            lines.append(f"| {ticker} | {weight_was * 100:.1f}% |")
        lines.append("")

    if holds:
        lines.append("### Hold (continuing positions)")
        lines.append("")
        lines.append("| Ticker | Name | Previous Weight | New Weight | Change |")
        lines.append("|--------|------|----------------|-----------|--------|")
        for ticker, name, w_was, w_now, delta in holds:
            delta_str = f"{delta * 100:+.1f}%"
            lines.append(
                f"| {ticker} | {name} | {w_was * 100:.1f}% | {w_now * 100:.1f}% | {delta_str} |"
            )
        lines.append("")

    if not buys and not sells and not holds:
        lines.append("_No changes — portfolio is identical to last month._")
        lines.append("")

    return lines


def build_portfolio_report(
    report_date: date,
    scored_df: pd.DataFrame,
    top_df: pd.DataFrame,
    alloc_chart: str,
    momentum_chart: str,
    portfolio_changes: dict | None = None,
) -> str:
    lines = []
    month_str = report_date.strftime("%B %Y")
    lines.append(f"# Monthly Portfolio Recommendation — {month_str}")
    lines.append("")
    lines.append(f"*Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        f"This month's portfolio selects the top {PORTFOLIO_SIZE} securities from our "
        f"universe of {len(scored_df)} assets, ranked by risk-adjusted momentum. "
        "All positions are equal-weighted."
    )
    lines.append("")

    if portfolio_changes is not None:
        lines.extend(build_portfolio_changes_section(portfolio_changes))

    lines.append("## Recommended Portfolio")
    lines.append("")
    lines.append(f"![Allocation]({alloc_chart})")
    lines.append("")
    lines.append("| Rank | Ticker | Name | Last Price | Momentum | Volatility |")
    lines.append("|------|--------|------|-----------|----------|-----------|")
    for row in top_df.itertuples():
        lines.append(
            f"| {row.rank} | {row.ticker} | {row.name} | "
            f"${row.last_price:,.2f} | {row.momentum:+.1f}% | {row.volatility:.1f}% |"
        )
    lines.append("")

    lines.append("## Full Universe Ranking")
    lines.append("")
    lines.append(f"![Momentum Chart]({momentum_chart})")
    lines.append("")
    lines.append("| Rank | Ticker | Name | Momentum | Volatility | Sharpe Proxy |")
    lines.append("|------|--------|------|----------|-----------|-------------|")
    for row in scored_df.itertuples():
        lines.append(
            f"| {row.rank} | {row.ticker} | {row.name} | "
            f"{row.momentum:+.1f}% | {row.volatility:.1f}% | {row.sharpe_proxy:.2f} |"
        )
    lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append("- **Momentum score**: weighted average of 1-month (60%) and 3-month (40%) price returns.")
    lines.append("- **Volatility**: annualised standard deviation of daily returns.")
    lines.append("- **Risk-adjusted momentum (Sharpe proxy)**: momentum ÷ volatility.")
    lines.append("- Portfolio = top N securities by Sharpe proxy, equal-weighted.")
    lines.append("")
    lines.append("---")
    lines.append("*Data sourced from Yahoo Finance via yfinance. Not financial advice.*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate monthly portfolio report")
    parser.add_argument("--date", default=None, help="Report month (YYYY-MM), defaults to current month")
    parser.add_argument("--reports-dir", default="../investment-research-reports", help="Path to reports repository")
    parser.add_argument("--portfolio-size", type=int, default=PORTFOLIO_SIZE, help="Number of holdings")
    args = parser.parse_args()

    if args.date:
        year, month = map(int, args.date.split("-"))
        _, last_day = monthrange(year, month)
        report_date = date(year, month, last_day)
    else:
        today = date.today()
        _, last_day = monthrange(today.year, today.month)
        report_date = date(today.year, today.month, last_day)

    reports_dir = Path(args.reports_dir)
    out_dir = reports_dir / "reports" / report_date.strftime("%Y/%m")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating monthly portfolio for {report_date.strftime('%B %Y')}...")

    print("Loading previous holdings for continuity comparison...")
    prev_holdings = load_previous_holdings(reports_dir, report_date)
    if prev_holdings:
        print(f"  Found previous holdings: {list(prev_holdings.keys())}")
    else:
        print("  No previous holdings found — first-run mode.")

    print("Fetching 6-month market data...")
    data = fetch_monthly_data(list(UNIVERSE.keys()), months=6)

    print("Scoring universe...")
    scored_df = score_tickers(data)
    if scored_df.empty:
        print("No data fetched — aborting.", file=sys.stderr)
        sys.exit(1)

    top_df = scored_df.head(args.portfolio_size)

    portfolio_changes = compute_portfolio_changes(prev_holdings, top_df)

    alloc_chart = out_dir / "portfolio_allocation.png"
    momentum_chart = out_dir / "momentum_scores.png"

    print("Generating charts...")
    generate_allocation_chart(top_df, alloc_chart)
    generate_momentum_chart(scored_df, momentum_chart)

    report_md = build_portfolio_report(
        report_date,
        scored_df,
        top_df,
        alloc_chart="portfolio_allocation.png",
        momentum_chart="momentum_scores.png",
        portfolio_changes=portfolio_changes,
    )

    report_path = out_dir / "portfolio.md"
    report_path.write_text(report_md)
    print(f"Report written to {report_path}")

    print("Saving holdings for next month's comparison...")
    save_holdings(top_df, report_date, out_dir)
    print(f"  Holdings saved to {out_dir / HOLDINGS_FILENAME}")


if __name__ == "__main__":
    main()
