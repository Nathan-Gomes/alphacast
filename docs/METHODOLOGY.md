# AlphaCast methodology

## Research question

At each monthly rebalance, AlphaCast ranks securities rather than claiming an exact future price. The evaluated outcome for security `i` on date `t` is:

```text
y(i, t) = R(i, t+1:t+20) - mean(R(j, t+1:t+20) for j in sector(i))
```

This is a 20-session forward **sector-relative excess return**. The holding-period return is unknown at the point a score is generated.

## Inputs and quality gate

The public-data path downloads adjusted close and volume history from Yahoo Finance. Before feature engineering, AlphaCast rejects missing required fields, duplicate `(date, ticker)` observations, non-positive prices, negative volumes, universes with fewer than ten securities, and histories shorter than 300 sessions. The data-quality record reports accepted tickers, historical coverage, and missing ticker-date cells.

The default live universe is deliberately listed in source with a sector mapping. Custom symbols request Yahoo sector metadata when available and otherwise remain explicitly `Unclassified`. That makes the selection rule inspectable, but it is not a historical index-membership file. The repository also provides a deterministic synthetic panel for repeatable tests and dashboard demonstration.

## Feature library

All inputs are trailing-only:

- 21-, 63-, and 126-session returns;
- 12-1 momentum: `P(t-21) / P(t-252) - 1`;
- 20- and 60-session annualized volatility and 60-session downside volatility;
- 252-session drawdown and distance from the rolling high;
- 50/200 moving-average relationship;
- 20-session dollar volume and relative volume;
- 63-session market-relative and sector-relative return.

There are no point-in-time fundamental fields in this release. Those require a provider that can establish when a reported value was known.

## Chronological validation and leakage control

Folds are evaluated at the final available session of each month. Training expands over time. For a test decision date `t`, the latest training row is at most `t - 20` sessions, so its forward label ends before the test label begins. This 20-session embargo prevents overlapping target periods from crossing the training/test boundary.

The portfolio return for a scored row is constructed only from its forward return after the score date. Rebalances use the previous holding set to calculate one-way turnover. The initial position is treated as the study's starting allocation and does not receive an arbitrary turnover charge.

## Comparable model suite

1. **Momentum:** 12-1 momentum ranking baseline.
2. **Ridge:** standardized linear regression with L2 regularization.
3. **Elastic Net:** standardized linear regression with combined L1/L2 regularization.
4. **Random Forest:** deterministic ensemble with fixed seed, 40 trees, and a minimum leaf size of four.

Hyperparameters are declared in source; this release does not perform a separate nested hyperparameter search. The same fold sequence is used for every model.

## Diagnostics

- **Rank IC:** Spearman correlation between model score and realised sector-relative outcome for each test cross-section.
- **IC information ratio:** mean Rank IC divided by its time-series standard deviation.
- **Positive IC rate:** percentage of test dates with positive Rank IC.
- **Q1 − Q5:** average realised relative return of the highest-scored quintile minus the lowest-scored quintile.
- **Portfolio path:** gross and net return of an equal-weight top-ranked long-only sleeve versus the equal-weight universe.
- **Costs:** one-way turnover times the declared transaction-cost basis points.
- **Model monitoring:** the last six completed folds are compared with the full run to make deterioration visible rather than burying it in an average.
- **Regime diagnostics:** each test date is assigned using its trailing 63-session market return and 20-session market volatility. The high/low volatility cutoff is the median calculated from that fold's training history only.

## Interpretation

A positive result in one historical universe is only a prompt for more research. It does not establish alpha, capacity, implementability, or a forecast. The strongest practical test is whether a more complex model adds stable out-of-sample ranking information beyond momentum after realistic data, costs, constraints, and further held-out evaluation.
