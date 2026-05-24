"""
captures_manager.py – reads/writes data/captures.csv via GitHub API.

Schema: trainer, pokemon_name, pokemon_id, types, level_caught, caught_at
One row per captured Pokémon (duplicates allowed if caught twice).
"""

import os
import io
import base64
import requests
import pandas as pd
import streamlit as st
from datetime import datetime

REPO_OWNER  = "FletcherRoss"
REPO_NAME   = "Pokemon-Journeys"
CSV_PATH    = "data/captures.csv"
BRANCH      = "main"
API_BASE    = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{CSV_PATH}"
LOCAL_CSV   = os.path.join(os.path.dirname(__file__), "..", "data", "captures.csv")

COLUMNS = ["trainer", "pokemon_name", "pokemon_id", "types", "level_caught", "current_level", "caught_at", "selected_moves"]


def _github_token():
    try:
        return st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        return os.environ.get("GITHUB_TOKEN", None)


def _default_df() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


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
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = ""
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

    sha = None
    r = requests.get(API_BASE, headers=headers, timeout=10)
    if r.status_code == 200:
        sha = r.json().get("sha")

    payload = {
        "message": "chore: update captures [bot]",
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(API_BASE, headers=headers, json=payload, timeout=15)
    return resp.status_code in (200, 201)


def init_captures_csv():
    os.makedirs(os.path.dirname(LOCAL_CSV), exist_ok=True)
    if not os.path.exists(LOCAL_CSV):
        _default_df().to_csv(LOCAL_CSV, index=False)


def load_captures() -> pd.DataFrame:
    df = _fetch_from_github()
    if df is not None:
        os.makedirs(os.path.dirname(LOCAL_CSV), exist_ok=True)
        df.to_csv(LOCAL_CSV, index=False)
        return df
    if os.path.exists(LOCAL_CSV):
        df = pd.read_csv(LOCAL_CSV)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[COLUMNS]
    return _default_df()


def save_captures(df: pd.DataFrame):
    os.makedirs(os.path.dirname(LOCAL_CSV), exist_ok=True)
    df.to_csv(LOCAL_CSV, index=False)
    _push_to_github(df)


def add_capture(trainer: str, pokemon: dict, level_caught: int) -> pd.DataFrame:
    """Append a new capture row and save. Returns updated df."""
    df = load_captures()
    new_row = {
        "trainer":        trainer,
        "pokemon_name":   pokemon["name"],
        "pokemon_id":     pokemon["id"],
        "types":          "/".join(pokemon.get("types", ["normal"])),
        "level_caught":   level_caught,
        "current_level":  level_caught,
        "caught_at":      datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "selected_moves": "",
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_captures(df)
    return df


def level_up_captured(capture_index: int, amount: int = 1) -> pd.DataFrame:
    """Increment current_level for the row at capture_index (global df index). Saves and returns df."""
    df = load_captures()
    df = df.astype(object)
    if capture_index in df.index:
        current = int(float(df.at[capture_index, "current_level"] or df.at[capture_index, "level_caught"] or 5))
        df.at[capture_index, "current_level"] = current + amount
    save_captures(df)
    return df


def check_and_evolve_captured(capture_index: int) -> dict | None:
    """
    Check if the captured pokemon at capture_index can evolve.
    If so, updates the row in captures.csv and returns the new evolved pokemon dict.
    Returns None if no evolution available.
    """
    import sys, os
    from pathlib import Path
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from utils.pokemon_api import get_evolution, fetch_pokemon

    df = load_captures()
    df = df.astype(object)
    if capture_index not in df.index:
        return None

    row    = df.loc[capture_index]
    poke_id = int(float(row["pokemon_id"]))
    evolved = get_evolution(poke_id)
    if not evolved:
        return None

    # Update the row with the evolved pokemon's data
    df.at[capture_index, "pokemon_name"] = evolved["name"]
    df.at[capture_index, "pokemon_id"]   = evolved["id"]
    df.at[capture_index, "types"]        = "/".join(evolved.get("types", ["normal"]))
    save_captures(df)
    return evolved


def level_up_and_check_evolve(capture_index: int) -> tuple[pd.DataFrame, dict | None]:
    """Level up a captured pokemon and check for evolution. Returns (df, evolved_pokemon_or_None)."""
    df      = level_up_captured(capture_index)
    evolved = check_and_evolve_captured(capture_index)
    return df, evolved


def get_trainer_captures(trainer: str) -> pd.DataFrame:
    df = load_captures()
    return df[df["trainer"] == trainer].reset_index(drop=True)


def get_capture_count(trainer: str) -> int:
    return len(get_trainer_captures(trainer))
