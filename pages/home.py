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


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _switch_trainer(new_trainer: str):
    """Clear battle/pokemon state and switch active trainer."""
    keys_to_clear = [
        "my_pokemon", "my_moves", "my_current_hp", "my_max_hp",
        "my_level", "my_xp", "starter_options", "starter_chosen",
        "battle_active", "battle_log", "battle_turn", "battle_result",
        "opponent_pokemon", "opponent_moves", "opponent_current_hp", "opponent_max_hp",
        "gym_leader_team", "gym_leader_moves", "gym_leader_hp", "gym_leader_index",
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]
    st.session_state.trainer_name = new_trainer


def _trainer_switcher(current: str, df):
    """Render the always-visible trainer switcher strip."""
    st.markdown("### 👤 Active Trainer")
    cols = st.columns(3)
    for i, trainer in enumerate(TRAINERS):
        emoji = TRAINER_EMOJI[trainer]
        row   = df[df["trainer"] == trainer]
        badges = _safe_int(row.iloc[0]["badges"]) if len(row) else 0
        wins   = _safe_int(row.iloc[0]["wins"])   if len(row) else 0
        is_active = trainer == current

        border = "2px solid var(--poke-yellow)" if is_active else "2px solid var(--poke-blue)"
        bg     = "linear-gradient(145deg,#2a3a1a,#1a2a0f)" if is_active else "linear-gradient(145deg,#1e2a4a,#0f1a35)"
        shadow = "0 0 18px rgba(255,203,5,0.45)" if is_active else "none"

        with cols[i]:
            st.markdown(f"""
            <div style="
                background:{bg};
                border:{border};
                border-radius:14px;
                padding:0.9rem 0.5rem;
                text-align:center;
                box-shadow:{shadow};
                margin-bottom:4px;
            ">
                <div style="font-size:2rem">{emoji}</div>
                <div style="font-weight:700;font-size:1rem;margin:2px 0">{trainer}</div>
                <div style="font-size:0.75rem;color:var(--text-muted)">🏅{badges} &nbsp;W:{wins}</div>
                {'<div style="font-size:0.65rem;color:var(--poke-yellow);margin-top:4px">▶ ACTIVE</div>' if is_active else ''}
            </div>""", unsafe_allow_html=True)

            if not is_active:
                if st.button(f"Switch to {trainer}", key=f"switch_{trainer}", use_container_width=True):
                    _switch_trainer(trainer)
                    st.rerun()
            else:
                st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)

    st.markdown("---")


def render():
    st.markdown('<div class="pokeball-header">⚡ POKÉMON JOURNEYS ⚡</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    df = load_teams()

    # ── Step 1: First-time trainer pick (no trainer set yet) ────────────────
    if not st.session_state.trainer_name:
        st.markdown("### 🎮 Who's playing first?")
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

    # ── Always-visible trainer switcher ────────────────────────────────────
    _trainer_switcher(trainer, df)

    # ── Current trainer data ────────────────────────────────────────────────
    row = df[df["trainer"] == trainer]
    starter_id_val = row.iloc[0]["starter_id"] if len(row) > 0 else ""
    has_starter = (
        len(row) > 0
        and str(row.iloc[0]["starter"]).strip() not in ("", "nan")
        and _safe_int(starter_id_val) > 0
    )

    if has_starter:
        poke_name = row.iloc[0]["starter"]
        poke_id   = _safe_int(row.iloc[0]["starter_id"])
        level     = _safe_int(row.iloc[0].get("level", 5), 5)
        wins      = _safe_int(row.iloc[0].get("wins", 0))
        losses    = _safe_int(row.iloc[0].get("losses", 0))
        badges_n  = _safe_int(row.iloc[0].get("badges", 0))

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
        if not st.session_state.get("my_pokemon") or st.session_state.my_pokemon["name"] != poke_name:
            from utils.pokemon_api import fetch_pokemon
            poke = fetch_pokemon(poke_id)
            poke["level"] = level
            st.session_state.my_pokemon    = poke
            st.session_state.my_max_hp     = poke["hp"]
            st.session_state.my_current_hp = poke["hp"]
            st.session_state.my_level      = level
            if not st.session_state.get("my_moves"):
                # Use custom moveset from movesets.csv if saved, else fetch default
                try:
                    from utils.movesets_manager import get_moveset, init_movesets_csv
                    init_movesets_csv()
                    custom = get_moveset(trainer, poke_id)
                    st.session_state.my_moves = custom if custom else fetch_moves(poke_id)
                except Exception:
                    st.session_state.my_moves = fetch_moves(poke_id)
        return

    # ── Step 2: Choose starter ──────────────────────────────────────────────
    st.markdown(f"## {emoji} {trainer}'s Journey Begins!")
    st.markdown("Professor Oak has 3 Pokémon waiting for you. Choose your partner:")

    if not st.session_state.get("starter_options"):
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
    moves = fetch_moves(poke["id"])
    st.session_state.my_pokemon     = poke
    st.session_state.my_moves       = moves
    st.session_state.my_max_hp      = poke["hp"]
    st.session_state.my_current_hp  = poke["hp"]
    st.session_state.my_level       = 5
    st.session_state.starter_chosen = True

    df = update_trainer(df, trainer,
        starter=poke["name"],
        starter_id=poke["id"],
        level=5,
        wins=0, losses=0, badges=0,
    )
    save_teams(df)
    st.success(f"You chose {poke['name']}! Let the journey begin!")
