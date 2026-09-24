"""Run the first reproducible AlphaCast study; generated values are not market evidence."""

from alphacast import run_study


def main() -> None:
    for model in ("momentum", "ridge"):
        result = run_study(model)
        print(f"{model.title()} | {result.observations} monthly folds")
        print(f"  Mean rank IC: {result.mean_rank_ic:.3f}")
        print(f"  Positive IC months: {result.positive_ic_rate:.1%}")
        print(f"  Mean Q1-Q5 spread: {result.mean_q1_q5_spread:.2%}\n")


if __name__ == "__main__":
    main()
