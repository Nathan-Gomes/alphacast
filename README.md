# AlphaCast

**Systematic equity research application for testing cross-sectional stock rankings.**

AlphaCast asks one focused question:

> Can information available at a rebalance date rank securities by their sector-relative performance over the next 20 trading sessions?

It is not a price-target tool, an automated trading system, or investment advice. It is a reproducible research application that makes the data, timing rules, model comparisons, portfolio accounting, and limitations visible together.

## What is implemented

```text
Yahoo Finance or deterministic synthetic panel
-> data-quality checks
-> trailing price / volume features
-> sector-relative 20-session forward target
-> expanding walk-forward folds with a 20-session embargo
-> Momentum / Ridge / Elastic Net / Random Forest rankings
-> quintile diagnostics and a cost-aware top-ranked portfolio
-> API, local dashboard, exportable JSON run record
```

- **Data:** Yahoo Finance adjusted close and volume history for a transparent starter universe, or a deterministic synthetic panel for repeatable demonstration and test runs.
- **Features:** 1-, 3-, and 6-month return; 12-1 momentum; realized and downside volatility; drawdown; distance from 52-week high; moving-average relationship; dollar volume; volume change; market-relative and sector-relative momentum.
- **Validation:** monthly expanding-window evaluation; every target begins after its decision date; the final 20 labelled sessions of training are embargoed to prevent overlap with test labels.
- **Models:** a declared momentum baseline, Ridge, Elastic Net, and Random Forest. Every model sees the identical train/test sequence; the slower tree model is opt-in in the dashboard.
- **Evaluation:** mean Rank IC, IC information ratio, percentage of positive IC periods, Q1-minus-Q5 spread, gross/net portfolio return, turnover, cost drag, and historical net growth.
- **Portfolio:** equal-weight top-ranked long-only sleeve, with one-way turnover and declared basis-point transaction costs. Results are compared to the equal-weight universe over the same realised holding periods.
- **Dashboard:** configuration form, run metadata, model table, recent model-health monitoring, train-only regime diagnostics, equity-path comparison, feature importance, and the last evaluated historical ranking.

## Run locally

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m uvicorn alphacast.app:app --reload
```

Open `http://127.0.0.1:8000`.

The dashboard defaults to deterministic synthetic data so the first click is reproducible. Choose **Yahoo Finance history** to run the same workflow against supplied symbols. Yahoo requests need at least ten tickers; the prefilled starter universe has a documented sector mapping, and custom symbols attempt Yahoo sector resolution with an explicit `Unclassified` fallback.

## Command-line runs

```bash
# A deterministic, reviewable output record
.venv/bin/alphacast --source synthetic --output output/synthetic-run.json

# A live-data study using the transparent default universe
.venv/bin/alphacast --source yahoo --start 2017-01-01 --models momentum,ridge \
  --output output/yahoo-run.json
```

`output/` is intentionally ignored by Git. A run record depends on its download date, universe, source availability, and declared configuration; it should be generated rather than committed as permanent evidence.

## Research safeguards

At decision date `t`, every feature uses observations through `t`. The evaluated target is the compounded return from `t + 1` through `t + 20`, less the equal-weight return of that security's sector over the same sessions. The training boundary is moved back by 20 sessions, so its final target cannot overlap the test target.

The model score is evaluated as a **rank**, not an exact-return forecast. A model only earns a stronger conclusion if it improves out-of-sample ranking diagnostics and remains useful after turnover and transaction costs compared with the momentum baseline.

The dashboard also compares each model's latest six folds with its complete run, and breaks results into expansion/contraction and high/low-volatility regimes. Regimes use only trailing market information available before each evaluated date; they are diagnostics for investigation, not an invitation to tune a model after seeing results.

## Limits

- Yahoo Finance is convenient public history, not an institutional point-in-time data source.
- The starter universe is manually declared and can carry selection and survivorship bias.
- There are no point-in-time fundamentals, delisting returns, borrow costs, taxes, bid/ask spreads, or execution-quality estimates in this release.
- The top-ranked sleeve is a transparent research construction, not a production portfolio optimizer.
- Historical results do not establish future returns.

These are research limitations to address, not qualifications to hide. See [the methodology](docs/METHODOLOGY.md) for the equations and design decisions.

## Deploy

The repository includes a `Dockerfile` and `render.yaml` for a Render web service. The health endpoint is `/api/health`. The application has no authentication by design for a public portfolio demonstration; do not use it with proprietary data or credentials.
