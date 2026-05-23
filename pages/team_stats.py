import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
from utils.csv_manager import load_teams
from utils.captures_manager import load_captures, init_captures_csv
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


def _pokemon_sprite(pokemon_id) -> str:
    try:
        pid = int(float(pokemon_id))
        return f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pid}.png"
    except Exception:
        return ""


def render():
    init_captures_csv()

    st.markdown("## 📊 Team Stats & Leaderboard")

    teams_df    = load_teams()
    captures_df = load_captures()

    if teams_df.empty:
        st.info("No journey data yet. Head to Home and choose a trainer!")
        return

    # ── Leaderboard ─────────────────────────────────────────────────────────
    st.markdown("### 🏆 Trainer Leaderboard")
    df_sorted = teams_df.sort_values(["badges", "wins"], ascending=False).reset_index(drop=True)

    for rank, (_, row) in enumerate(df_sorted.iterrows()):
        trainer  = row["trainer"]
        color    = TRAINER_COLORS.get(trainer, "#888")
        badges   = _safe_int(row.get("badges", 0))
        wins     = _safe_int(row.get("wins", 0))
        losses   = _safe_int(row.get("losses", 0))
        level    = _safe_int(row.get("level", 5), 5)
        starter  = row.get("starter", "—")
        evos     = _safe_int(row.get("evolutions", 0))
        caught   = len(captures_df[captures_df["trainer"] == trainer])
        medal    = ["🥇", "🥈", "🥉"][rank] if rank < 3 else "🎖️"

        badge_html = ""
        for gym in GYM_INFO:
            earned = _safe_int(row.get(gym["badge_key"], 0)) == 1
            css    = "gym-badge-earned" if earned else "gym-badge-locked"
            badge_html += f'<span class="{css}" style="width:32px;height:32px;font-size:1rem;">{gym["emoji"]}</span>'

        total    = wins + losses
        win_rate = f"{(wins/total*100):.0f}%" if total > 0 else "—"

        st.markdown(f"""
        <div style="
            background:linear-gradient(135deg,rgba(30,40,70,0.9),rgba(15,25,50,0.9));
            border:2px solid {color}; border-radius:16px;
            padding:1.2rem 1.5rem; margin:0.8rem 0;
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

    # ── Captured Pokémon section ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ⚾ Captured Pokémon")

    if captures_df.empty:
        st.info("No Pokémon captured yet — win wild battles and roll that d20!")
    else:
        tabs = st.tabs([f"{TRAINER_COLORS.get(t,'')[:1] and ''}{t}" for t in ["Addy", "Oakley", "Raelynn"]])
        for tab, trainer in zip(tabs, ["Addy", "Oakley", "Raelynn"]):
            with tab:
                trainer_caps = captures_df[captures_df["trainer"] == trainer].reset_index(drop=True)
                if trainer_caps.empty:
                    st.markdown(f"*{trainer} hasn't caught any Pokémon yet.*")
                    continue

                st.markdown(f"**{len(trainer_caps)} Pokémon caught**")

                # Grid: 4 per row
                cols_per_row = 4
                for row_start in range(0, len(trainer_caps), cols_per_row):
                    chunk = trainer_caps.iloc[row_start:row_start + cols_per_row]
                    cols  = st.columns(cols_per_row)
                    for col, (_, cap) in zip(cols, chunk.iterrows()):
                        sprite = _pokemon_sprite(cap["pokemon_id"])
                        types  = str(cap.get("types", "normal")).split("/")
                        type_badges = ""
                        for t in types:
                            tc = TYPE_COLORS.get(t.strip(), "#888")
                            type_badges += f'<span class="type-badge" style="background:{tc};font-size:0.6rem;">{t.strip()}</span>'
                        with col:
                            st.markdown(f"""
                            <div class="pokemon-card" style="cursor:default;padding:0.8rem;">
                                <img src="{sprite}" width="70" style="image-rendering:pixelated"/>
                                <div style="font-size:0.75rem;font-weight:700;margin:3px 0;">
                                    {cap['pokemon_name']}
                                </div>
                                {type_badges}
                                <div style="font-size:0.65rem;color:var(--text-muted);margin-top:4px;">
                                    Lv.{cap.get('level_caught','?')} caught
                                </div>
                            </div>""", unsafe_allow_html=True)

    # ── Charts ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📈 Win / Loss Comparison")
    chart_data = []
    for _, row in teams_df.iterrows():
        chart_data.append({
            "Trainer": row["trainer"],
            "Wins":    _safe_int(row.get("wins", 0)),
            "Losses":  _safe_int(row.get("losses", 0)),
        })
    chart_df = pd.DataFrame(chart_data).set_index("Trainer")
    st.bar_chart(chart_df, color=["#4CAF50", "#F44336"])

    st.markdown("---")
    st.markdown("### ⚾ Pokémon Captured per Trainer")
    cap_counts = {t: len(captures_df[captures_df["trainer"] == t]) for t in ["Addy", "Oakley", "Raelynn"]}
    cap_df = pd.DataFrame(cap_counts, index=["Caught"]).T
    st.bar_chart(cap_df, color=["#FFCB05"])

    st.markdown("---")
    st.markdown("### 🏅 Badge Progress")
    badge_data = []
    for _, row in teams_df.iterrows():
        earned = sum(_safe_int(row.get(g["badge_key"], 0)) for g in GYM_INFO)
        badge_data.append({"Trainer": row["trainer"], "Badges Earned": earned, "Remaining": 8 - earned})
    badge_df = pd.DataFrame(badge_data).set_index("Trainer")
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
