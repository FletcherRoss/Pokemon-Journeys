import sys
import os
from pathlib import Path

# Ensure repo root is always on the path regardless of working directory
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import random
from utils.pokemon_api import get_random_starters, get_pokemon_sprite
from utils.game_state import init_session_state
from utils.csv_manager import load_teams, save_teams, init_csv
from utils.captures_manager import init_captures_csv
from utils.movesets_manager import init_movesets_csv

st.set_page_config(
    page_title="Pokémon Journeys",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323:wght@400&family=Nunito:wght@400;600;700&display=swap');

:root {
    --poke-red: #E3350D;
    --poke-yellow: #FFCB05;
    --poke-blue: #3D7DCA;
    --poke-dark: #1a1a2e;
    --poke-panel: #16213e;
    --poke-accent: #0f3460;
    --text-main: #f0f0f0;
    --text-muted: #a0a8c0;
}

html, body, [class*="css"] {
    font-family: 'Nunito', sans-serif;
    background-color: var(--poke-dark);
    color: var(--text-main);
}

h1, h2 { font-family: 'Press Start 2P', monospace; }
h3, h4 { font-family: 'VT323', monospace; font-size: 1.6rem; letter-spacing: 1px; }

.stApp { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); }

.pokeball-header {
    text-align: center;
    padding: 2rem 0 1rem 0;
    font-family: 'Press Start 2P', monospace;
    font-size: 1.1rem;
    color: var(--poke-yellow);
    text-shadow: 2px 2px 0px var(--poke-red), 4px 4px 0px rgba(0,0,0,0.5);
    letter-spacing: 2px;
}

.pokemon-card {
    background: linear-gradient(145deg, #1e2a4a, #0f1a35);
    border: 2px solid var(--poke-blue);
    border-radius: 16px;
    padding: 1.2rem;
    text-align: center;
    transition: all 0.3s ease;
    cursor: pointer;
    box-shadow: 0 4px 15px rgba(61,125,202,0.2);
}
.pokemon-card:hover {
    border-color: var(--poke-yellow);
    box-shadow: 0 6px 25px rgba(255,203,5,0.35);
    transform: translateY(-4px);
}

.hp-bar-wrap { background: #333; border-radius: 6px; height: 12px; margin: 4px 0; overflow: hidden; }
.hp-bar-fill  { height: 100%; border-radius: 6px; transition: width 0.5s ease; }

.type-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 2px;
    color: #fff;
}

.battle-log {
    background: rgba(0,0,0,0.4);
    border: 1px solid var(--poke-blue);
    border-radius: 10px;
    padding: 1rem;
    font-family: 'VT323', monospace;
    font-size: 1.1rem;
    color: var(--poke-yellow);
    max-height: 200px;
    overflow-y: auto;
    white-space: pre-wrap;
}

.team-badge {
    background: var(--poke-accent);
    border-left: 4px solid var(--poke-yellow);
    border-radius: 0 8px 8px 0;
    padding: 0.5rem 0.8rem;
    margin: 4px 0;
    font-size: 0.85rem;
}

.stButton > button {
    background: linear-gradient(135deg, var(--poke-red), #c0280a) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'Press Start 2P', monospace !important;
    font-size: 0.55rem !important;
    padding: 0.7rem 1.2rem !important;
    letter-spacing: 1px !important;
    transition: all 0.2s !important;
    box-shadow: 0 3px 8px rgba(0,0,0,0.4) !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #ff4522, var(--poke-red)) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 16px rgba(227,53,13,0.5) !important;
}

.gym-badge-earned {
    display: inline-flex; align-items: center; justify-content: center;
    width: 48px; height: 48px; border-radius: 50%;
    background: radial-gradient(circle, var(--poke-yellow), #c8960a);
    border: 2px solid white;
    font-size: 1.4rem;
    box-shadow: 0 0 12px rgba(255,203,5,0.6);
    margin: 3px;
}
.gym-badge-locked {
    display: inline-flex; align-items: center; justify-content: center;
    width: 48px; height: 48px; border-radius: 50%;
    background: #333;
    border: 2px solid #555;
    font-size: 1.4rem;
    opacity: 0.3;
    margin: 3px;
}

.win-banner  { text-align:center; font-family:'Press Start 2P',monospace; font-size:1.2rem;
               color:var(--poke-yellow); padding:1rem; background:rgba(255,203,5,0.1);
               border:2px solid var(--poke-yellow); border-radius:12px; animation: pulse 1.5s infinite; }
.lose-banner { text-align:center; font-family:'Press Start 2P',monospace; font-size:1.2rem;
               color:var(--poke-red); padding:1rem; background:rgba(227,53,13,0.1);
               border:2px solid var(--poke-red); border-radius:12px; }

@keyframes pulse { 0%,100%{ box-shadow:0 0 10px rgba(255,203,5,0.4); } 50%{ box-shadow:0 0 25px rgba(255,203,5,0.8); } }

/* Hide underlying button text for nav — label shown in custom HTML above */
div[data-testid="stSidebar"] div[data-testid="stButton"] > button {
    font-size: 0 !important;
    height: 0 !important;
    min-height: 0 !important;
    padding: 0 !important;
    margin: -8px 0 0 0 !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    opacity: 0 !important;
    position: absolute !important;
    width: 100% !important;
}

/* Sidebar nav buttons */
div[data-testid="stSidebar"] .nav-btn-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 4px;
}
div[data-testid="stSidebar"] .nav-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: linear-gradient(145deg, #1e2a4a, #0f1a35);
    border: 2px solid var(--poke-blue);
    border-radius: 10px;
    padding: 14px 8px;
    cursor: pointer;
    text-align: center;
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--text-main);
    transition: all 0.2s ease;
    line-height: 1.3;
    min-height: 72px;
    text-decoration: none;
}
div[data-testid="stSidebar"] .nav-btn:hover {
    border-color: var(--poke-yellow);
    box-shadow: 0 0 12px rgba(255,203,5,0.3);
    transform: translateY(-2px);
}
div[data-testid="stSidebar"] .nav-btn.active {
    border-color: var(--poke-yellow);
    background: linear-gradient(145deg, #2a3a1a, #1a2a0f);
    box-shadow: 0 0 16px rgba(255,203,5,0.45);
    color: var(--poke-yellow);
}
div[data-testid="stSidebar"] .nav-btn .nav-icon {
    font-size: 1.4rem;
    line-height: 1;
}
</style>
""", unsafe_allow_html=True)

# ── Init ──────────────────────────────────────────────────────────────────────
init_session_state()
init_csv()
init_captures_csv()
init_movesets_csv()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ Pokémon Journeys")
    st.markdown("---")

    teams_df = load_teams()
    st.markdown("### 👥 Team Standings")
    for _, row in teams_df.iterrows():
        badges_earned = int(row.get("badges", 0))
        wins = int(row.get("wins", 0))
        losses = int(row.get("losses", 0))
        st.markdown(f"""
        <div class="team-badge">
            <strong>{row['trainer']}</strong><br>
            🏅 {badges_earned} badges &nbsp;|&nbsp; W:{wins} L:{losses}
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🗺 Navigation")

    PAGES = [
        ("🏠", "Home"),
        ("⚔️", "Wild Battle"),
        ("🏟️", "Gym Battle"),
        ("📊", "Team Stats"),
        ("🤝", "Trainer Battle"),
        ("🎲", "Random Battle"),
    ]
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = "🏠 Home"

    # 2x2 grid of square nav buttons
    col1, col2 = st.columns(2)
    for i, (icon, label) in enumerate(PAGES):
        full = f"{icon} {label}"
        is_active = st.session_state.nav_page == full
        css = "nav-btn active" if is_active else "nav-btn"
        with (col1 if i % 2 == 0 else col2):
            st.markdown(
                f'<div class="{css}"><div class="nav-icon">{icon}</div>{label}</div>',
                unsafe_allow_html=True
            )
            if st.button(label, key=f"nav_{label}", use_container_width=True,
                         help=f"Go to {label}"):
                st.session_state.nav_page = full
                st.rerun()

    page = st.session_state.nav_page

# ── Page routing ──────────────────────────────────────────────────────────────
if page == "🏠 Home":
    from pages.home import render
    render()
elif page == "⚔️ Wild Battle":
    from pages.wild_battle import render
    render()
elif page == "🏟️ Gym Battle":
    from pages.gym_battle import render
    render()
elif page == "📊 Team Stats":
    from pages.team_stats import render
    render()
elif page == "🤝 Trainer Battle":
    from pages.trainer_battle import render
    render()
elif page == "🎲 Random Battle":
    from pages.random_battle import render
    render()
