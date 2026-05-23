import streamlit as st
import pandas as pd
from utils.csv_manager import load_teams
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


def render():
    st.markdown("## 📊 Team Stats & Leaderboard")
    df = load_teams()

    if df.empty:
        st.info("No journey data yet. Head to Home and choose a trainer!")
        return

    # ── Leaderboard ─────────────────────────────────────────────────────────
    st.markdown("### 🏆 Trainer Leaderboard")

    # Sort by badges desc, then wins desc
    df_sorted = df.sort_values(["badges", "wins"], ascending=False).reset_index(drop=True)

    for rank, (_, row) in enumerate(df_sorted.iterrows()):
        trainer = row["trainer"]
        color   = TRAINER_COLORS.get(trainer, "#888")
        badges  = int(row.get("badges", 0))
        wins    = int(row.get("wins", 0))
        losses  = int(row.get("losses", 0))
        level   = int(row.get("level", 5))
        starter = row.get("starter", "—")
        evos    = int(row.get("evolutions", 0))
        medal   = ["🥇", "🥈", "🥉"][rank] if rank < 3 else "🎖️"

        # Badge icons
        badge_html = ""
        for gym in GYM_INFO:
            earned = int(row.get(gym["badge_key"], 0)) == 1
            if earned:
                badge_html += f'<span class="gym-badge-earned" style="width:32px;height:32px;font-size:1rem;">{gym["emoji"]}</span>'
            else:
                badge_html += f'<span class="gym-badge-locked" style="width:32px;height:32px;font-size:1rem;">{gym["emoji"]}</span>'

        total = wins + losses
        win_rate = f"{(wins / total * 100):.0f}%" if total > 0 else "—"

        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, rgba(30,40,70,0.9), rgba(15,25,50,0.9));
            border: 2px solid {color};
            border-radius: 16px;
            padding: 1.2rem 1.5rem;
            margin: 0.8rem 0;
            box-shadow: 0 4px 16px rgba(0,0,0,0.3);
        ">
            <div style="display:flex; align-items:center; gap:1rem; flex-wrap:wrap;">
                <span style="font-size:2rem">{medal}</span>
                <div>
                    <div style="font-size:1.2rem; font-weight:700; color:{color};">{trainer}</div>
                    <div style="font-size:0.85rem; color:#a0a8c0;">
                        🐾 {starter} &nbsp;|&nbsp; Lv.{level} &nbsp;|&nbsp; ✨ {evos} evolution{'s' if evos != 1 else ''}
                    </div>
                </div>
                <div style="margin-left:auto; text-align:right;">
                    <div style="font-size:1.1rem; font-weight:700;">W:{wins} / L:{losses}</div>
                    <div style="font-size:0.8rem; color:#a0a8c0;">Win rate: {win_rate}</div>
                </div>
            </div>
            <div style="margin-top:0.8rem;">
                <small style="color:#a0a8c0;">Gym Badges:</small><br>
                {badge_html}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Win rate bar chart ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📈 Win / Loss Comparison")

    chart_data = []
    for _, row in df.iterrows():
        wins   = int(row.get("wins", 0))
        losses = int(row.get("losses", 0))
        chart_data.append({"Trainer": row["trainer"], "Wins": wins, "Losses": losses})

    chart_df = pd.DataFrame(chart_data).set_index("Trainer")
    st.bar_chart(chart_df, color=["#4CAF50", "#F44336"])

    # ── Badge progress ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏅 Badge Progress")

    badge_data = []
    for _, row in df.iterrows():
        earned = sum(int(row.get(g["badge_key"], 0)) for g in GYM_INFO)
        badge_data.append({"Trainer": row["trainer"], "Badges Earned": earned, "Remaining": 8 - earned})

    badge_df = pd.DataFrame(badge_data).set_index("Trainer")
    st.bar_chart(badge_df, color=["#FFCB05", "#333355"])

    # ── Raw data expander ───────────────────────────────────────────────────
    with st.expander("📋 Raw CSV Data (teams.csv)"):
        st.dataframe(df, use_container_width=True)
        csv_str = df.to_csv(index=False)
        st.download_button(
            "⬇️ Download teams.csv",
            data=csv_str,
            file_name="teams.csv",
            mime="text/csv",
        )
