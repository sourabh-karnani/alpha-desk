from pathlib import Path

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
REPORTS_DIR = REPO_ROOT / "reports"
LOGS_DIR = REPO_ROOT / "logs"

BARS_DUCKDB_PATH = DATA_DIR / "bars.duckdb"
FUNDAMENTALS_DUCKDB_PATH = DATA_DIR / "fundamentals.duckdb"
STATE_SQLITE_PATH = DATA_DIR / "state.sqlite"


class RiskConfig(BaseModel):
    capital_inr: float = 100_000.0
    max_positions: int = 10
    atr_stop_multiple: float = 2.0
    reward_risk_ratio: float = 2.0
    sizing_mode: str = "equal_weight"  # "equal_weight" | "risk_based"
    risk_per_trade_pct: float = 0.01  # used by risk_based mode
    max_risk_per_trade_pct: float = 0.02  # safety ceiling for equal_weight mode
    max_position_pct: float = 0.20  # absolute per-position notional cap during spillover


def get_risk_config() -> RiskConfig:
    return RiskConfig()


def ensure_dirs() -> None:
    for d in (DATA_DIR, REPORTS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
