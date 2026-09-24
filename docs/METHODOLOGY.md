# Methodology: first research foundation

## Target

For security `i` observed after close on day `t`, the first-version target is its compounded return over the next 20 sessions less the equally weighted return of its sector over the same period:

```text
y(i, t) = R(i, t+1:t+20) - mean(R(j, t+1:t+20) for j in sector(i))
```

Using a relative target means the score is intended to rank comparable securities, not forecast an exact price.

## Features

Every feature is trailing-only: 21-, 63-, and 126-session returns, 20-session volatility, 63-session maximum drawdown, and 63-session market-relative return. The 21-session return is excluded from the 12-1-style feature, leaving `return_126 - return_21`.

## Validation

The evaluation date moves forward in monthly steps. For each fold, AlphaCast fits only completed observations before the test date. The latest 20 eligible labelled sessions are embargoed from training because their targets overlap the test horizon. Predictions are evaluated cross-sectionally on one date at a time.

## Metrics

- **Rank IC**: Spearman correlation between predicted scores and realized targets on each test date.
- **Q1 minus Q5 spread**: equal-weight average target return among the highest-scored quintile less the lowest-scored quintile.
- **Turnover and cost**: represented in the portfolio interface now; realistic execution assumptions are a required future data milestone.

## Limits

This first release contains synthetic data only. Its result is a software and research-design check, not evidence that a strategy works in markets. Real work requires point-in-time universe membership, corporate-action handling, survivorship controls, a trading calendar, liquidity-aware costs, and separate held-out periods.
