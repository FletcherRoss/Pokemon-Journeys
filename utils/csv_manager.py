"""
CSV manager – reads/writes teams.csv via GitHub API.

The file lives at:
  https://github.com/FletcherRoss/Pokemon-Journeys/blob/main/data/teams.csv

Set the GITHUB_TOKEN secret in Streamlit Cloud to enable writes.
Reads always fall back to local copy so the app works offline / in dev.
"""

import os
import io
import base64
import json
import requests
import pandas as pd
import streamlit as st

# ── Config ────────────────────────────────────────────────────────────────────
REPO_OWNER   = "FletcherRoss"
REPO_NAME    = "Pokemon-Journeys"
CSV_PATH     = "data/teams.csv"
BRANCH       = "main"
API_BASE     = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{CSV_PATH}"

TRAINERS = ["Addy", "Oakley", "Raelynn"]

COLUMNS = [
    "trainer", "starter", "starter_id", "level",
    "wins", "losses", "badges",
    "badge_rock", "badge_grass", "badge_water", "badge_fire",
    "badge_psychic", "badge_normal", "badge_ice", "badge_elite",
    "evolutions", "selected_moves",
]

LOCAL_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "teams.csv")


def _default_df() -> pd.DataFrame:
    rows = []
    for trainer in TRAINERS:
        rows.append({
            "trainer": trainer, "starter": "", "starter_id": 0, "level": 5,
            "wins": 0, "losses": 0, "badges": 0,
            "badge_rock": 0, "badge_grass": 0, "badge_water": 0, "badge_fire": 0,
            "badge_psychic": 0, "badge_normal": 0, "badge_ice": 0, "badge_elite": 0,
            "evolutions": 0, "selected_moves": "",
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def _github_token() -> str | None:
    try:
        return st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        return os.environ.get("GITHUB_TOKEN", None)


def _fetch_from_github() -> pd.DataFrame | None:
    token = _github_token()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(API_BASE, headers=headers, timeout=10)
        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode("utf-8")
            df = pd.read_csv(io.StringIO(content))
            # Ensure all columns exist (forward-compat)
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = 0
            return df[COLUMNS]
    except Exception:
        pass
    return None


def _push_to_github(df: pd.DataFrame) -> bool:
    token = _github_token()
    if not token:
        return False
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    encoded   = base64.b64encode(csv_bytes).decode("utf-8")

    # Need current SHA to update
    sha = None
    r = requests.get(API_BASE, headers=headers, timeout=10)
    if r.status_code == 200:
        sha = r.json().get("sha")

    payload = {
        "message": "chore: update team standings [bot]",
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(API_BASE, headers=headers, json=payload, timeout=15)
    return resp.status_code in (200, 201)


def init_csv():
    """Ensure local fallback CSV exists."""
    os.makedirs(os.path.dirname(LOCAL_CSV), exist_ok=True)
    if not os.path.exists(LOCAL_CSV):
        _default_df().to_csv(LOCAL_CSV, index=False)


def load_teams() -> pd.DataFrame:
    """Load teams: try GitHub first, fall back to local, fall back to defaults."""
    df = _fetch_from_github()
    if df is not None:
        # Cache locally
        os.makedirs(os.path.dirname(LOCAL_CSV), exist_ok=True)
        df.to_csv(LOCAL_CSV, index=False)
        return df
    if os.path.exists(LOCAL_CSV):
        df = pd.read_csv(LOCAL_CSV)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = 0
        return df[COLUMNS]
    return _default_df()


def save_teams(df: pd.DataFrame):
    """Save teams to local CSV and attempt GitHub push."""
    os.makedirs(os.path.dirname(LOCAL_CSV), exist_ok=True)
    df.to_csv(LOCAL_CSV, index=False)
    pushed = _push_to_github(df)
    if not pushed:
        st.toast("⚠️ Saved locally (no GitHub token – add GITHUB_TOKEN to Streamlit secrets to sync)", icon="⚠️")
    else:
        st.toast("✅ Team standings synced to GitHub!", icon="✅")


def get_trainer_row(df: pd.DataFrame, trainer: str) -> pd.Series:
    mask = df["trainer"] == trainer
    if mask.any():
        return df[mask].iloc[0]
    default = _default_df()
    return default[default["trainer"] == trainer].iloc[0]


def update_trainer(df: pd.DataFrame, trainer: str, **kwargs) -> pd.DataFrame:
    """Update fields for a given trainer and return modified df."""
    idx = df.index[df["trainer"] == trainer]
    if len(idx) == 0:
        return df
    # Cast to object dtype first to avoid pandas dtype coercion errors
    # (e.g. writing a string into an int column or vice versa)
    df = df.astype(object)
    for k, v in kwargs.items():
        if k in df.columns:
            df.at[idx[0], k] = v
    return df
