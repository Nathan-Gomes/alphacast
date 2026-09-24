# AlphaCast

**Machine-learning systematic equity research platform**

AlphaCast asks a deliberately narrow question: can information known at a rebalance date rank securities by their likely relative performance over the next 20 trading sessions?

It is not a price-target tool and it does not place trades. The research workflow is:

```text
point-in-time prices -> features -> cross-sectional ranks -> walk-forward tests
-> quintile portfolios -> costs, diagnostics, and monitoring
```

## First working foundation

This initial release uses a deterministic **synthetic** equity panel. That makes the timing rules, ranking metrics, and tests inspectable before external data is introduced. It does **not** claim historical alpha, investment performance, or live coverage.

Implemented now:

- trailing momentum, volatility, drawdown, and market-relative features;
- a 20-session forward, sector-relative excess-return target;
- expanding-window walk-forward folds with a 20-session embargo;
- momentum and Ridge regression ranking models;
- monthly rank IC and equal-weight Q1-minus-Q5 evaluation;
- a transaction-cost hook and tests that enforce the timing contract.

## Run it

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python scripts/run_synthetic_study.py
.venv/bin/python -m pytest -q
```

The study prints model diagnostics only. It never represents generated values as live investment research.

## Research controls

At date `t`, every feature is calculated from data through `t`. The target begins at `t + 1`, runs for 20 sessions, and is unknown when a score is made. Validation uses expanding history and purges the final 20 labelled sessions from each training window so overlapping target returns cannot cross the boundary.

The baseline ranking is deliberately simple: trailing 12-1-style momentum. A more complex model is only useful if it adds out-of-sample ranking information after costs and under the same timing controls.

## Next milestones

1. Add licensed or provider-approved point-in-time market and fundamental data.
2. Add linear, tree-based, and constrained portfolio models under the same validation gate.
3. Add sector neutrality, turnover constraints, attribution, and regime diagnostics.
4. Publish a research dashboard with run provenance and model-degradation monitoring.

See [the methodology](docs/METHODOLOGY.md) for the exact first-version definitions and the limits of this repository.
