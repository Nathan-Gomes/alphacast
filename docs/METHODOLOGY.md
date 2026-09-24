# AlphaCast methodology

## Research question

At each month-end AlphaCast ranks securities. It does not claim an exact future price. The evaluated outcome for security `i` on decision date `t` is

```text
y(i, t) = R(i, t+1 : t+20) - mean over j in sector(i) of R(j, t+1 : t+20)
```

the 20-session forward return in excess of the equal-weight return of the security's sector. It is unknown when the score is generated.

## Data and quality gate

The default workspace uses a frozen Yahoo Finance snapshot of adjusted close and volume for 98 US large caps across all 11 GICS sectors, January 2014 to September 2026 (`scripts/refresh_snapshot.py` regenerates it). Runs can also download live Yahoo history for either declared universe or up to 150 custom tickers, or use a deterministic synthetic panel for method checks.

Before any feature is built, AlphaCast:

- rejects missing columns, duplicate `(date, ticker)` rows, non-positive prices, negative volume, fewer than ten securities, and fewer than 300 sessions;
- drops any session where fewer than 90% of securities have a price. Yahoo occasionally publishes a day for part of a universe, and a partial cross-section would distort every within-date rank and sector average. The count of dropped sessions is reported.

The universe is a hand-written list of today's large caps, not historical index membership. Every result therefore carries survivorship bias.

## Features

All 14 inputs use data through the decision close only:

| Group | Features |
|---|---|
| Momentum | 1-, 3-, 6-month return; 12-1 momentum `P(t-21) / P(t-252) - 1`; 50/200-day moving-average spread |
| Risk | 20- and 60-session annualised volatility; 60-session downside volatility; 12-month drawdown; distance from the 52-week high |
| Liquidity | 20-session average dollar volume; volume relative to its 60-session average |
| Relative | 3-month return minus the universe mean; 3-month return minus the sector mean |

Models receive each feature as its **percentile rank within the date**, centred on zero. Raw levels drift over a decade (dollar volume grows; volatility regimes change), and a cross-sectional model can only use the ordering anyway.

There are no fundamental features. They need a source that records when each value became public.

## Validation and leakage control

- **Folds.** One fold per calendar month-end with a realised label, taken from the full trading calendar. The final month in the sample, cut short because its labels are not yet realised, never becomes a fold.
- **Expanding window with embargo.** For test date `t`, training uses labelled rows dated at most `t - 20` sessions, so no training label overlaps the test label. At least 504 sessions of training history are required before the first fold.
- **Training sample.** Consecutive 20-session labels overlap by 19 sessions, so daily rows are close duplicates. Training keeps every fifth session, counted back from the embargo boundary. This is faster and nearer to independent observations.
- **Refit cadence.** Models refit every third monthly fold and score the months in between with the most recent fit. A stale fit only uses older data, so it cannot leak.
- **Label winsorisation.** Training labels are clipped at each date's 2.5th and 97.5th percentiles, so one takeover or earnings gap cannot dominate a squared-error fit. Evaluation always uses the unclipped outcome.
- **Live signal.** After the walk-forward, each model is fitted on every label already realised and scores the latest complete session, whose outcome is unknown. No embargo is needed because no test label exists yet.

## Model suite

All models see the same folds, features, and portfolio rule. Hyperparameters are declared in source; there is no search on test folds.

1. **Momentum 12-1:** ranks by 12-1 momentum. Nothing is fitted. This is the baseline every model must beat.
2. **Ridge:** standardised linear regression, L2 penalty `alpha = 10`.
3. **Elastic Net:** standardised, `alpha = 0.0005`, `l1_ratio = 0.5`.
4. **Random Forest:** 80 trees, depth 6, minimum leaf 100, half the features and half the rows per tree, fixed seed.
5. **Gradient Boosting:** scikit-learn histogram gradient boosting, 150 iterations, learning rate 0.05, 15 leaves, minimum leaf 200, L2 = 1, fixed seed.
6. **Ensemble:** the equal-weight average of the selected machine-learning models' within-date rank percentiles. The weights are fixed in advance, so nothing is fitted to test folds; it needs at least two members. Its attribution averages each member's contributions scaled by that member's score dispersion.

## Attribution

For a scored cross-section, the contribution of feature `k` to security `i` is the change in score when `k` is set to zero (the date median) and everything else is held fixed:

```text
c(i, k) = f(x_i) - f(x_i with x_ik = 0)
```

For the linear models this is exactly coefficient times centred rank. For the tree models it is a local approximation that ignores interactions. A model's **reliance** on a feature is its mean absolute contribution as a share of the total, which puts every model on the same scale. Reliance describes the model, not causality.

## Diagnostics

- **Rank IC:** Spearman correlation between score and realised outcome in each fold. Reported as a mean, volatility, information ratio, t-statistic (`mean / (sd / sqrt(n))`), and share of positive months.
- **Quintiles:** the average realised outcome of each score quintile; Q1 − Q5 spread; how often all five are in order.
- **Portfolio:** an equal-weight long-only sleeve of the top 15 names, held for 20 sessions. One-way turnover times the declared basis-point cost is subtracted. Benchmark: the equal-weight universe over the same periods. The first period is treated as the starting allocation and is not charged.
- **Regimes:** each test date is labelled with trailing information only. The 63-session universe return sets expansion or contraction. 20-session universe volatility above the training window's median sets high volatility.

## Costs, sectors and consensus

- **Cost sensitivity:** each period stores gross return and one-way turnover, so net returns at any cost `c` are `gross - turnover x c`. The app reports the cost at which net Sharpe falls to the universe's, and the cost at which the mean gross edge over the universe is used up.
- **Rebalance cadence:** runs can trade the sleeve every one, two or three months. Between rebalances the book is held with no turnover or cost, and each month still earns the next 20 sessions of the held names. Quarterly trading more than halved turnover for Random Forest but lowered its net Sharpe, so monthly is the default.
- **Holding buffer:** a held stock is kept while it still ranks inside a wider band (for example the top 23 when holding 15), and vacancies are filled from the top. For Random Forest a 1.5x buffer cut average monthly turnover from about 41% to 28% with a similar net Sharpe; the difference in Sharpe is within noise, the saving in turnover is not.
- **Sector cap:** an optional limit on names per sector. The sleeve takes the highest-ranked names, skipping one when its sector is already full, so it still holds the declared number of names. The cap applies to every walk-forward fold and to the live book.
- **Within-sector skill:** for each model and sector, the Spearman correlation between score and realised outcome among that sector's names in each fold (at least four names), averaged across folds. Active weight is the sleeve's sector share minus the universe's, averaged across folds.
- **Consensus and agreement:** consensus counts the models that place a stock in their top quintile today; agreement is the Spearman correlation between two models' live rankings.

## Monitoring

- **Model health:** the mean Rank IC of the last six folds against the full sample. **Degraded** if the recent mean is negative; **watch** if it sits more than one standard error (full-sample IC s.d. / sqrt(6)) below the full-sample mean; otherwise **healthy**.
- **Reliance drift:** the share of attribution per feature over the last six folds against the full history.
- **Feature drift:** population stability index of raw feature values, last 63 sessions against all earlier history, using deciles of the reference. Under 0.10 stable, 0.10 to 0.25 moderate, above 0.25 shifted. Models see within-date ranks, so raw drift does not reach them directly, but it signals a market unlike most of the training data.

## Interpretation

A positive result in one historical universe prompts more research; it does not establish alpha, capacity, or a forecast. The meaningful test is whether a model adds stable out-of-sample ranking information beyond momentum after costs. That test should be repeated on point-in-time constituents, with fundamentals and a realistic execution model, before any stronger claim.
