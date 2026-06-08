"""
utils/story_mode.py — shared Master Ball helpers importable from any battle page.
The actual story mode UI lives in pages/story_mode.py.
"""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.csv_manager import load_teams, save_teams, update_trainer


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def award_master_ball(trainer: str, amount: int = 1):
    """Add master balls to a trainer's total."""
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        cur = _safe_int(row.iloc[0].get("master_balls", 0))
        df = update_trainer(df, trainer, master_balls=cur + amount)
        save_teams(df)


def get_master_balls(trainer: str) -> int:
    """Return current master ball count for a trainer."""
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        return _safe_int(row.iloc[0].get("master_balls", 0))
    return 0


def use_master_ball(trainer: str) -> bool:
    """Spend one master ball. Returns True if successful."""
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        cur = _safe_int(row.iloc[0].get("master_balls", 0))
        if cur > 0:
            df = update_trainer(df, trainer, master_balls=cur - 1)
            save_teams(df)
            return True
    return False
