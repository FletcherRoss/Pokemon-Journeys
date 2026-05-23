import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.captures_manager import load_captures, save_captures, init_captures_csv, level_up_captured
from utils.pokemon_api import type_badge_html

GYM_INFO = [
    {"name": "Brock",   "emoji": "🪨", "badge_key": "badge_rock"},
    {"name": "Erika",   "emoji": "🌿", "badge_key": "badge_grass"},
    {"name": "Misty",   "emoji": "💧", "badge_key": "badge_water"},
    {"name": "Blaine",  "emoji": "🔥", "badge_key": "badge_fire"},
    {"name": "Sabrina", "emoji": "🔮", "badge_key": "badge_psychic"},
    {"name": "Whitney", "emoji": "⭐", "badge_key": "badge_normal"},
    {"name": "Pryce",   "emoji": "❄️", "badge_key": "badge_ice"},
    {"name": "Lance",   "emoji": "🐉", "badge_key": "badge_elite"},
]

TRAINER_COLORS = {
    "Addy":    "#F06292",
    "Oakley":  "#64B5F6",
    "Raelynn": "#FFB74D",
}

TYPE_COLORS = {
    "fire":"#F08030","water":"#6890F0","grass":"#78C850","electric":"#F8D030",
    "psychic":"#F85888","ice":"#98D8D8","dragon":"#7038F8","dark":"#705848",
    "fairy":"#EE99AC","fighting":"#C03028","poison":"#A040A0","ground":"#E0C068",
    "flying":"#A890F0","bug":"#A8B820","rock":"#B8A038","ghost":"#705898",
    "steel":"#B8B8D0","normal":"#A8A878",
}


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _sprite(pokemon_id) -> str:
    try:
        pid = int(float(pokemon_id))
        return f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pid}.png"
    except Exception:
        return ""


def _type_pills(types_str: str) -> str:
    html = ""
    for t in str(types_str).split("/"):
        t = t.strip()
        tc = TYPE_COLORS.get(t, "#888")
        html += f'<span class="type-badge" style="background:{tc};font-size:0.6rem;">{t}</span>'
    return html


# ── Starter level-up card ─────────────────────────────────────────────────────

def _starter_levelup_card(trainer: str, teams_df: pd.DataFrame):
    row = teams_df[teams_df["trainer"] == trainer]
    if row.empty:
        return
    r = row.iloc[0]
    starter    = str(r.get("starter", "")).strip()
    starter_id = _safe_int(r.get("starter_id", 0))
    level      = _safe_int(r.get("level", 5), 5)

    if not starter or starter in ("", "nan") or starter_id == 0:
        st.markdown("_No starter chosen yet._")
        return

    color  = TRAINER_COLORS.get(trainer, "#888")
    sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{starter_id}.png"

    col_img, col_info, col_btn = st.columns([1, 2, 1])
    with col_img:
        st.image(sprite, width=90)
    with col_info:
        st.markdown(f"""
        <div style="padding:4px 0">
            <div style="font-weight:700;font-size:1rem;color:{color};">{starter}</div>
            <div style="font-size:0.8rem;color:var(--text-muted);">Starter Pokémon</div>
            <div style="margin-top:6px;">
                <span style="
                    background:var(--poke-accent);border:1px solid {color};
                    border-radius:20px;padding:3px 12px;font-size:0.85rem;font-weight:700;
                ">Lv. {level}</span>
            </div>
        </div>""", unsafe_allow_html=True)
    with col_btn:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("⬆️ Level Up", key=f"lvlup_starter_{trainer}", use_container_width=True):
            new_level = level + 1
            updated = update_trainer(teams_df, trainer, level=new_level)
            save_teams(updated)
            # Also update active session if this is the current trainer
            if st.session_state.get("trainer_name") == trainer:
                st.session_state.my_level = new_level
            st.toast(f"⬆️ {starter} is now Lv. {new_level}!", icon="⬆️")
            st.rerun()


# ── Captured Pokémon level-up grid ────────────────────────────────────────────

def _captures_levelup_grid(trainer: str, captures_df: pd.DataFrame):
    trainer_caps = captures_df[captures_df["trainer"] == trainer]

    if trainer_caps.empty:
        st.markdown("_No Pokémon captured yet._")
        return

    st.markdown(f"**{len(trainer_caps)} Pokémon caught**")

    cols_per_row = 3
    indices = list(trainer_caps.index)

    for row_start in range(0, len(indices), cols_per_row):
        chunk_idx = indices[row_start:row_start + cols_per_row]
        cols = st.columns(cols_per_row)

        for col, cap_idx in zip(cols, chunk_idx):
            cap    = captures_df.loc[cap_idx]
            sprite = _sprite(cap["pokemon_id"])
            types  = _type_pills(cap.get("types", "normal"))
            cur_lv = _safe_int(
                cap.get("current_level") or cap.get("level_caught"), 5
            )
            name   = cap["pokemon_name"]
            color  = TRAINER_COLORS.get(trainer, "#888")

            with col:
                st.markdown(f"""
                <div class="pokemon-card" style="cursor:default;padding:0.9rem 0.6rem;margin-bottom:4px;">
                    <img src="{sprite}" width="75" style="image-rendering:pixelated"/>
                    <div style="font-size:0.8rem;font-weight:700;margin:4px 0;">{name}</div>
                    <div style="margin-bottom:4px;">{types}</div>
                    <span style="
                        background:var(--poke-accent);border:1px solid {color};
                        border-radius:20px;padding:2px 10px;font-size:0.8rem;font-weight:700;
                    ">Lv. {cur_lv}</span>
                </div>""", unsafe_allow_html=True)

                if st.button("⬆️", key=f"lvlup_cap_{cap_idx}", use_container_width=True,
                             help=f"Level up {name}"):
                    level_up_captured(cap_idx)
                    st.toast(f"⬆️ {name} is now Lv. {cur_lv + 1}!", icon="⬆️")
                    st.rerun()


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    init_captures_csv()

    st.markdown("## 📊 Team Stats & Leaderboard")

    teams_df    = load_teams()
    captures_df = load_captures()

    # Backfill current_level for older rows that didn't have it
    if "current_level" not in captures_df.columns:
        captures_df["current_level"] = captures_df.get("level_caught", 5)
    captures_df["current_level"] = captures_df.apply(
        lambda r: r["level_caught"] if str(r.get("current_level", "")).strip() in ("", "nan")
        else r["current_level"], axis=1
    )

    if teams_df.empty:
        st.info("No journey data yet. Head to Home and choose a trainer!")
        return

    # ── Leaderboard ──────────────────────────────────────────────────────────
    st.markdown("### 🏆 Trainer Leaderboard")
    df_sorted = teams_df.sort_values(["badges", "wins"], ascending=False).reset_index(drop=True)

    for rank, (_, row) in enumerate(df_sorted.iterrows()):
        trainer = row["trainer"]
        color   = TRAINER_COLORS.get(trainer, "#888")
        badges  = _safe_int(row.get("badges", 0))
        wins    = _safe_int(row.get("wins", 0))
        losses  = _safe_int(row.get("losses", 0))
        level   = _safe_int(row.get("level", 5), 5)
        starter = row.get("starter", "—")
        evos    = _safe_int(row.get("evolutions", 0))
        caught  = len(captures_df[captures_df["trainer"] == trainer])
        medal   = ["🥇", "🥈", "🥉"][rank] if rank < 3 else "🎖️"

        badge_html = "".join(
            f'<span class="{"gym-badge-earned" if _safe_int(row.get(g["badge_key"],0))==1 else "gym-badge-locked"}"'
            f' style="width:32px;height:32px;font-size:1rem;">{g["emoji"]}</span>'
            for g in GYM_INFO
        )
        total    = wins + losses
        win_rate = f"{(wins/total*100):.0f}%" if total > 0 else "—"

        st.markdown(f"""
        <div style="
            background:linear-gradient(135deg,rgba(30,40,70,0.9),rgba(15,25,50,0.9));
            border:2px solid {color};border-radius:16px;
            padding:1.2rem 1.5rem;margin:0.8rem 0;
            box-shadow:0 4px 16px rgba(0,0,0,0.3);
        ">
            <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap;">
                <span style="font-size:2rem">{medal}</span>
                <div>
                    <div style="font-size:1.2rem;font-weight:700;color:{color};">{trainer}</div>
                    <div style="font-size:0.85rem;color:#a0a8c0;">
                        🐾 {starter} &nbsp;|&nbsp; Lv.{level} &nbsp;|&nbsp;
                        ✨ {evos} evo{'s' if evos!=1 else ''} &nbsp;|&nbsp;
                        ⚾ {caught} caught
                    </div>
                </div>
                <div style="margin-left:auto;text-align:right;">
                    <div style="font-size:1.1rem;font-weight:700;">W:{wins} / L:{losses}</div>
                    <div style="font-size:0.8rem;color:#a0a8c0;">Win rate: {win_rate}</div>
                </div>
            </div>
            <div style="margin-top:0.8rem;">
                <small style="color:#a0a8c0;">Gym Badges:</small><br>{badge_html}
            </div>
        </div>""", unsafe_allow_html=True)

    # ── Level-up section ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ⬆️ Level Up Pokémon")
    st.markdown(
        "<small style='color:var(--text-muted)'>Use these buttons to level up your starter "
        "and captured Pokémon after real-world battles.</small>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    trainer_tabs = st.tabs(["🌸 Addy", "⚡ Oakley", "🔥 Raelynn"])
    for tab, trainer in zip(trainer_tabs, ["Addy", "Oakley", "Raelynn"]):
        with tab:
            color = TRAINER_COLORS[trainer]
            st.markdown(f"#### Starter")
            _starter_levelup_card(trainer, teams_df)

            st.markdown("---")
            st.markdown(f"#### Captured Pokémon")
            _captures_levelup_grid(trainer, captures_df)

    # ── Charts ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📈 Win / Loss Comparison")
    chart_df = pd.DataFrame([
        {"Trainer": r["trainer"],
         "Wins":    _safe_int(r.get("wins", 0)),
         "Losses":  _safe_int(r.get("losses", 0))}
        for _, r in teams_df.iterrows()
    ]).set_index("Trainer")
    st.bar_chart(chart_df, color=["#4CAF50", "#F44336"])

    st.markdown("---")
    st.markdown("### ⚾ Pokémon Captured per Trainer")
    cap_df = pd.DataFrame(
        {t: [len(captures_df[captures_df["trainer"] == t])] for t in ["Addy", "Oakley", "Raelynn"]},
        index=["Caught"]
    ).T
    st.bar_chart(cap_df, color=["#FFCB05"])

    st.markdown("---")
    st.markdown("### 🏅 Badge Progress")
    badge_df = pd.DataFrame([
        {"Trainer": r["trainer"],
         "Badges Earned": sum(_safe_int(r.get(g["badge_key"],0)) for g in GYM_INFO),
         "Remaining": 8 - sum(_safe_int(r.get(g["badge_key"],0)) for g in GYM_INFO)}
        for _, r in teams_df.iterrows()
    ]).set_index("Trainer")
    st.bar_chart(badge_df, color=["#FFCB05", "#333355"])

    # ── Raw data ─────────────────────────────────────────────────────────────
    with st.expander("📋 Raw Data"):
        st.markdown("**teams.csv**")
        st.dataframe(teams_df, use_container_width=True)
        st.markdown("**captures.csv**")
        st.dataframe(captures_df, use_container_width=True)
        st.download_button("⬇️ Download captures.csv",
            data=captures_df.to_csv(index=False),
            file_name="captures.csv", mime="text/csv")
