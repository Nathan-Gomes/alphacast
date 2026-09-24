"""Configuration for reproducible AlphaCast research runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class ResearchConfig:
    """Parameters that materially affect an AlphaCast research conclusion."""

    start: str = "2017-01-01"
    end: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    horizon_sessions: int = 20
    minimum_train_sessions: int = 504
    embargo_sessions: int = 20
    rebalance: str = "monthly"
    top_n: int = 10
    transaction_cost_bps: float = 10.0
    models: tuple[str, ...] = ("momentum", "ridge", "elastic_net", "random_forest")
    random_seed: int = 17

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


SUPPORTED_MODELS = ("momentum", "ridge", "elastic_net", "random_forest")
