import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from utils.pokemon_api import get_random_starters, fetch_moves, type_badge_html
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.game_state import init_session_state

TRAINERS = ["Addy", "Oakley", "Raelynn"]
TRAINER_EMOJI = {"Addy": "🌸", "Oakley": "⚡", "Raelynn": "🔥"}


def render():
    st.markdown('<div class="pokeball-header">⚡ POKÉMON JOURNEYS ⚡</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Step 1: Choose trainer ──────────────────────────────────────────────
    if not st.session_state.trainer_name:
        st.markdown("### 🎮 Who's playing?")
        st.markdown("Select your trainer to begin your journey.")
        cols = st.columns(3)
        for i, trainer in enumerate(TRAINERS):
            with cols[i]:
                emoji = TRAINER_EMOJI[trainer]
                st.markdown(f"""
                <div class="pokemon-card" style="padding:2rem 1rem;">
                    <div style="font-size:3rem">{emoji}</div>
                    <h3 style="margin:0.5rem 0;">{trainer}</h3>
                </div>""", unsafe_allow_html=True)
                if st.button(f"Play as {trainer}", key=f"trainer_{trainer}"):
                    st.session_state.trainer_name = trainer
                    st.rerun()
        return

    trainer = st.session_state.trainer_name
    emoji   = TRAINER_EMOJI[trainer]

    # Check if already has a starter (from CSV)
    df = load_teams()
    row = df[df["trainer"] == trainer]

    def _safe_int(val, default=0):
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    starter_id_val = row.iloc[0]["starter_id"] if len(row) > 0 else ""
    has_starter = (
        len(row) > 0
        and str(row.iloc[0]["starter"]).strip() not in ("", "nan")
        and _safe_int(starter_id_val) > 0
    )

    if has_starter:
        # ── Already has a starter: show status ─────────────────────────────
        poke_name  = row.iloc[0]["starter"]
        poke_id    = _safe_int(row.iloc[0]["starter_id"])
        level      = _safe_int(row.iloc[0].get("level", 5), 5)
        wins       = _safe_int(row.iloc[0].get("wins", 0))
        losses     = _safe_int(row.iloc[0].get("losses", 0))
        badges_n   = _safe_int(row.iloc[0].get("badges", 0))

        sprite_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{poke_id}.png"

        st.markdown(f"## {emoji} Welcome back, {trainer}!")
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(sprite_url, width=200)
        with c2:
            st.markdown(f"### {poke_name}")
            st.markdown(f"**Level:** {level} &nbsp;|&nbsp; **Wins:** {wins} &nbsp;|&nbsp; **Losses:** {losses}")
            st.markdown(f"**Gym Badges:** {'🏅' * badges_n if badges_n > 0 else '_None yet_'}")
            st.markdown("---")
            st.markdown("Use the sidebar to head into battle or challenge a gym!")

        # Restore session pokemon if cleared
        if not st.session_state.my_pokemon or st.session_state.my_pokemon["name"] != poke_name:
            from utils.pokemon_api import fetch_pokemon
            poke = fetch_pokemon(poke_id)
            poke["level"] = level
            st.session_state.my_pokemon     = poke
            st.session_state.my_max_hp      = poke["hp"]
            st.session_state.my_current_hp  = poke["hp"]
            st.session_state.my_level       = level
            if not st.session_state.my_moves:
                st.session_state.my_moves = fetch_moves(poke_id)
        return

    # ── Step 2: Choose starter ──────────────────────────────────────────────
    st.markdown(f"## {emoji} {trainer}'s Journey Begins!")
    st.markdown("Professor Oak has 3 Pokémon waiting for you. Choose your partner:")

    if not st.session_state.starter_options:
        with st.spinner("Professor Oak is preparing your choices..."):
            st.session_state.starter_options = get_random_starters(3)

    options = st.session_state.starter_options
    cols    = st.columns(3)

    for i, poke in enumerate(options):
        with cols[i]:
            types_html = " ".join(type_badge_html(t) for t in poke["types"])
            st.markdown(f"""
            <div class="pokemon-card">
                <img src="{poke['sprite']}" width="140" style="image-rendering:pixelated"/>
                <h3 style="margin:0.3rem 0;">#{poke['id']:03d} {poke['name']}</h3>
                {types_html}
                <div style="margin-top:0.8rem; font-size:0.8rem; color:var(--text-muted);">
                    ❤️ HP:{poke['hp']} &nbsp;⚔️ ATK:{poke['attack']} &nbsp;🛡️ DEF:{poke['defense']}
                </div>
            </div>""", unsafe_allow_html=True)
            if st.button(f"Choose {poke['name']}!", key=f"starter_{i}"):
                _choose_starter(trainer, poke, df)
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔀 Show me different Pokémon"):
        st.session_state.starter_options = None
        st.rerun()


def _choose_starter(trainer: str, poke: dict, df):
    from utils.pokemon_api import fetch_moves
    moves = fetch_moves(poke["id"])

    st.session_state.my_pokemon    = poke
    st.session_state.my_moves      = moves
    st.session_state.my_max_hp     = poke["hp"]
    st.session_state.my_current_hp = poke["hp"]
    st.session_state.my_level      = 5
    st.session_state.starter_chosen = True

    df = update_trainer(df, trainer,
        starter=poke["name"],
        starter_id=poke["id"],
        level=5,
        wins=0, losses=0, badges=0,
    )
    save_teams(df)
    st.success(f"You chose {poke['name']}! Let the journey begin!")
