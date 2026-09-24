"""Configuration for reproducible AlphaCast research runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

SUPPORTED_MODELS = (
    "momentum", "ridge", "elastic_net", "random_forest", "gradient_boosting", "ensemble",
)

MODEL_LABELS = {
    "momentum": "Momentum 12-1",
    "ridge": "Ridge",
    "elastic_net": "Elastic Net",
    "random_forest": "Random Forest",
    "gradient_boosting": "Gradient Boosting",
    "ensemble": "Ensemble",
}


@dataclass(frozen=True)
class ResearchConfig:
    """Parameters that materially affect an AlphaCast research conclusion."""

    start: str = "2014-01-01"
    end: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    horizon_sessions: int = 20
    minimum_train_sessions: int = 504
    embargo_sessions: int = 20
    # Consecutive 20-session labels overlap by 19 sessions, so daily rows are mostly
    # duplicates of each other. Training keeps every fifth session, counted back from
    # the embargo boundary, which is faster and closer to independent observations.
    train_stride_sessions: int = 5
    # Models are refitted every third monthly fold and score every month in between with
    # the most recent fit. A stale fit only uses older data, so it cannot leak.
    refit_every_folds: int = 3
    rebalance: str = "monthly"
    # Trade the sleeve every Nth monthly fold and hold it in between (1 = monthly).
    rebalance_every_folds: int = 1
    top_n: int = 15
    # Optional cap on names per sector in the top-ranked sleeve; None means no cap.
    max_per_sector: int | None = None
    # Keep a held name while it ranks within this many places; None trades to the top N.
    hold_buffer: int | None = None
    transaction_cost_bps: float = 10.0
    monitoring_window: int = 6
    models: tuple[str, ...] = SUPPORTED_MODELS
    random_seed: int = 17

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
