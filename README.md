# investment-research-code

Python codebase for the investment research platform. Fetches market data, generates charts, and produces daily and monthly reports.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager

## Setup

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Or install in a virtual environment
uv venv
source .venv/bin/activate  # Linux/Mac
uv pip install -e .
```

## Usage

### Daily Report

Fetches market data for the watchlist, generates price and sector charts, and saves a markdown report.

```bash
# Run for today
uv run daily-report --reports-dir ../investment-research-reports

# Run for a specific date
uv run daily-report --date 2026-03-29 --reports-dir ../investment-research-reports
```

Output: `../investment-research-reports/reports/YYYY/MM/DD/daily_report.md`

### Monthly Portfolio

Scores a universe of securities on risk-adjusted momentum and recommends a portfolio.

```bash
# Run for current month
uv run monthly-portfolio --reports-dir ../investment-research-reports

# Run for a specific month
uv run monthly-portfolio --date 2026-03 --reports-dir ../investment-research-reports
```

Output: `../investment-research-reports/reports/YYYY/MM/portfolio.md`

## Project Structure

```
investment-research-code/
├── pyproject.toml                        # uv/hatch project definition
└── src/
    └── investment_research/
        ├── __init__.py
        ├── daily_report.py               # Daily market report generator
        └── monthly_portfolio.py          # Monthly portfolio recommendation generator
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `yfinance` | Yahoo Finance market data |
| `pandas` | Data manipulation |
| `matplotlib` | Static charts |
| `plotly` | Interactive charts |
| `kaleido` | Static export for plotly |

## Report Outputs

All reports are written to the **investment-research-reports** repository:

- Daily: `reports/YYYY/MM/DD/daily_report.md` + PNG charts
- Monthly: `reports/YYYY/MM/portfolio.md` + PNG charts

---
*Not financial advice.*
