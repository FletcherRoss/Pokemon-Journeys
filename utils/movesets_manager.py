"""
movesets_manager.py — reads/writes data/movesets.csv via GitHub API.

Schema (one row per move slot):
    trainer, pokemon_id, pokemon_name, slot, move_name, move_type, power, accuracy, pp

Each Pokémon has up to 4 rows (slot 1-4).
Identifying a Pokémon: trainer + pokemon_id.
For captured duplicates (same species caught twice) pokemon_id alone is ambiguous —
the CSV uses trainer+pokemon_id as the composite key and overwrites on save,
so the last-saved moveset wins for duplicates. This is acceptable for this game.
"""

import os
import io
import base64
import requests
import pandas as pd
import streamlit as st

REPO_OWNER = "FletcherRoss"
REPO_NAME  = "Pokemon-Journeys"
CSV_PATH   = "data/movesets.csv"
BRANCH     = "main"
API_BASE   = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{CSV_PATH}"
LOCAL_CSV  = os.path.join(os.path.dirname(__file__), "..", "data", "movesets.csv")

COLUMNS = ["trainer", "pokemon_id", "pokemon_name", "slot", "move_name", "move_type", "power", "accuracy", "pp"]


# ── GitHub helpers ────────────────────────────────────────────────────────────

def _token():
    try:
        return st.secrets.get("GITHUB_TOKEN", None)
    except Exception:
        return os.environ.get("GITHUB_TOKEN", None)


def _headers(write=False):
    h = {"Accept": "application/vnd.github+json"}
    tok = _token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _fetch_from_github() -> pd.DataFrame | None:
    try:
        r = requests.get(API_BASE, headers=_headers(), timeout=10)
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
    tok = _token()
    if not tok:
        return False
    headers = _headers()
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    encoded   = base64.b64encode(csv_bytes).decode("utf-8")
    sha = None
    r = requests.get(API_BASE, headers=headers, timeout=10)
    if r.status_code == 200:
        sha = r.json().get("sha")
    payload = {"message": "chore: update movesets [bot]", "content": encoded, "branch": BRANCH}
    if sha:
        payload["sha"] = sha
    resp = requests.put(API_BASE, headers=headers, json=payload, timeout=15)
    return resp.status_code in (200, 201)


# ── Public API ────────────────────────────────────────────────────────────────

def init_movesets_csv():
    os.makedirs(os.path.dirname(LOCAL_CSV), exist_ok=True)
    if not os.path.exists(LOCAL_CSV):
        pd.DataFrame(columns=COLUMNS).to_csv(LOCAL_CSV, index=False)


def load_movesets() -> pd.DataFrame:
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
    return pd.DataFrame(columns=COLUMNS)


def save_movesets(df: pd.DataFrame):
    os.makedirs(os.path.dirname(LOCAL_CSV), exist_ok=True)
    df.to_csv(LOCAL_CSV, index=False)
    pushed = _push_to_github(df)
    if not pushed:
        st.toast("⚠️ Moveset saved locally (add GITHUB_TOKEN to sync)", icon="⚠️")
    else:
        st.toast("✅ Moveset synced to GitHub!", icon="✅")


def get_moveset(trainer: str, pokemon_id: int) -> list[dict]:
    """Return up to 4 move dicts for this trainer+pokemon. Empty list if none saved."""
    df = load_movesets()
    mask = (df["trainer"] == trainer) & (df["pokemon_id"].astype(str) == str(pokemon_id))
    rows = df[mask].sort_values("slot")
    return [
        {
            "name":     str(r["move_name"]),
            "type":     str(r["move_type"]),
            "power":    int(r["power"])    if str(r["power"])    not in ("", "nan") else 0,
            "accuracy": int(r["accuracy"]) if str(r["accuracy"]) not in ("", "nan") else 100,
            "pp":       int(r["pp"])       if str(r["pp"])       not in ("", "nan") else 10,
        }
        for _, r in rows.iterrows()
    ]


def save_moveset(trainer: str, pokemon_id: int, pokemon_name: str, moves: list[dict]):
    """
    Save up to 4 moves for trainer+pokemon_id.
    Replaces any existing rows for that trainer+pokemon_id.
    """
    df = load_movesets()
    df = df.astype(object)

    # Drop existing rows for this trainer+pokemon
    mask = (df["trainer"] == trainer) & (df["pokemon_id"].astype(str) == str(pokemon_id))
    df   = df[~mask].reset_index(drop=True)

    # Append new rows
    new_rows = []
    for slot, move in enumerate(moves[:4], start=1):
        new_rows.append({
            "trainer":      trainer,
            "pokemon_id":   pokemon_id,
            "pokemon_name": pokemon_name,
            "slot":         slot,
            "move_name":    move.get("name", ""),
            "move_type":    move.get("type", "normal"),
            "power":        move.get("power", 0) or 0,
            "accuracy":     move.get("accuracy", 100) or 100,
            "pp":           move.get("pp", 10) or 10,
        })

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    save_movesets(df)


def delete_moveset(trainer: str, pokemon_id: int):
    """Remove all move rows for a trainer+pokemon."""
    df   = load_movesets()
    mask = (df["trainer"] == trainer) & (df["pokemon_id"].astype(str) == str(pokemon_id))
    df   = df[~mask].reset_index(drop=True)
    save_movesets(df)


def get_all_trainer_movesets(trainer: str) -> pd.DataFrame:
    """Return all moveset rows for a trainer, sorted by pokemon_name then slot."""
    df = load_movesets()
    return df[df["trainer"] == trainer].sort_values(["pokemon_name", "slot"]).reset_index(drop=True)
