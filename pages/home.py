import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from utils.pokemon_api import get_random_starters, fetch_moves, type_badge_html
from utils.csv_manager import (
    load_teams, save_teams, update_trainer,
    get_all_trainers, trainer_exists, add_trainer,
)
from utils.game_state import init_session_state

# Emoji pool for new trainers
TRAINER_EMOJI = {
    "Addy": "🌸", "Oakley": "⚡", "Raelynn": "🔥",
}
DEFAULT_EMOJI_POOL = ["🎮","🌟","🔮","🎯","💫","🌈","🦋","🐉","🌙","☀️","⚡","🔥","💧","🌿","❄️"]


def _trainer_emoji(name: str) -> str:
    return TRAINER_EMOJI.get(name, DEFAULT_EMOJI_POOL[hash(name) % len(DEFAULT_EMOJI_POOL)])


def _trainer_color(name: str) -> str:
    colors = ["#F06292","#64B5F6","#FFB74D","#81C784","#CE93D8","#80DEEA","#FFCC02","#FF8A65"]
    preset = {"Addy": "#F06292", "Oakley": "#64B5F6", "Raelynn": "#FFB74D"}
    return preset.get(name, colors[hash(name) % len(colors)])


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _switch_trainer(new_trainer: str):
    keys_to_clear = [
        "my_pokemon","my_moves","my_current_hp","my_max_hp",
        "my_level","my_xp","starter_options","starter_chosen",
        "battle_active","battle_log","battle_turn","battle_result",
        "opponent_pokemon","opponent_moves","opponent_current_hp","opponent_max_hp",
        "gym_leader_team","gym_leader_moves","gym_leader_hp","gym_leader_index",
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]
    st.session_state.trainer_name = new_trainer


def _trainer_switcher(current: str, df):
    all_trainers = get_all_trainers()
    st.markdown("### 👤 Active Trainer")

    cols_per_row = 3
    for row_start in range(0, len(all_trainers), cols_per_row):
        chunk = all_trainers[row_start:row_start + cols_per_row]
        cols  = st.columns(cols_per_row)
        for i, trainer in enumerate(chunk):
            emoji  = _trainer_emoji(trainer)
            color  = _trainer_color(trainer)
            row    = df[df["trainer"] == trainer]
            badges = _safe_int(row.iloc[0]["badges"]) if len(row) else 0
            wins   = _safe_int(row.iloc[0]["wins"])   if len(row) else 0
            is_active = trainer == current

            border = "2px solid var(--poke-yellow)" if is_active else f"2px solid {color}"
            bg     = "linear-gradient(145deg,#2a3a1a,#1a2a0f)" if is_active else "linear-gradient(145deg,#1e2a4a,#0f1a35)"
            shadow = "0 0 18px rgba(255,203,5,0.45)" if is_active else "none"

            with cols[i]:
                st.markdown(
                    f'<div style="background:{bg};border:{border};border-radius:14px;'
                    f'padding:0.9rem 0.5rem;text-align:center;box-shadow:{shadow};margin-bottom:4px;">'
                    f'<div style="font-size:2rem">{emoji}</div>'
                    f'<div style="font-weight:700;font-size:1rem;margin:2px 0">{trainer}</div>'
                    f'<div style="font-size:0.75rem;color:var(--text-muted)">🏅{badges} &nbsp;W:{wins}</div>'
                    + ('<div style="font-size:0.65rem;color:var(--poke-yellow);margin-top:4px">▶ ACTIVE</div>' if is_active else '')
                    + '</div>',
                    unsafe_allow_html=True
                )
                if not is_active:
                    if st.button(f"Switch to {trainer}", key=f"switch_{trainer}", use_container_width=True):
                        _switch_trainer(trainer)
                        st.rerun()
                else:
                    st.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)

    st.markdown("---")


# ── Create new player flow ─────────────────────────────────────────────────────

def _create_player_button():
    """Small ➕ New Player button rendered in top-right corner."""
    if st.session_state.get("show_new_player_form"):
        # Inline form
        st.markdown(
            '<div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);'
            'border:2px solid var(--poke-blue);border-radius:12px;padding:1rem;margin-bottom:0.5rem;">'
            '<b style="color:var(--poke-yellow);">➕ New Player</b>'
            '</div>',
            unsafe_allow_html=True
        )
        new_name = st.text_input(
            "Player name:", key="new_trainer_name_input",
            placeholder="Unique name…", max_chars=20,
            label_visibility="collapsed"
        ).strip()

        existing = [t.lower() for t in get_all_trainers()]
        name_ok  = bool(new_name) and len(new_name) >= 2 and new_name.lower() not in existing

        if new_name:
            if new_name.lower() in existing:
                st.error(f"❌ '{new_name}' already taken.")
            elif len(new_name) < 2:
                st.warning("Min 2 characters.")
            else:
                st.success(f"✅ '{new_name}' available!")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🎮 Create & Pick Starter", use_container_width=True,
                         key="create_player_btn", disabled=not name_ok):
                ok = add_trainer(new_name)
                if ok:
                    st.session_state.new_player_name  = new_name
                    st.session_state.new_player_phase = "pick_starter"
                    st.session_state.starter_options  = None
                    st.session_state.show_new_player_form = False
                    st.rerun()
                else:
                    st.error("Name already exists.")
        with c2:
            if st.button("✖ Cancel", use_container_width=True, key="cancel_new_player"):
                st.session_state.show_new_player_form = False
                st.rerun()
    else:
        if st.button("➕ New Player", key="show_new_player_btn", use_container_width=True):
            st.session_state.show_new_player_form = True
            st.rerun()



def _new_player_starter_pick():
    """Full-screen starter pick for a newly created player."""
    name = st.session_state.new_player_name
    color = _trainer_color(name)
    emoji = _trainer_emoji(name)

    st.markdown(f"## {emoji} Welcome, {name}!")
    st.markdown("Professor Oak has 3 Pokémon waiting. Choose your starter:")

    if not st.session_state.get("starter_options"):
        with st.spinner("Professor Oak is preparing your choices..."):
            st.session_state.starter_options = get_random_starters(3)

    options = st.session_state.starter_options

    # Confirm step
    confirming = st.session_state.get("new_player_confirm_poke")

    if confirming:
        poke = confirming
        sprite = poke.get("sprite") or f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{poke['id']}.png"
        types_html = " ".join(type_badge_html(t) for t in poke["types"])
        st.markdown(f"""
        <div style="background:linear-gradient(145deg,#1e3a1e,#0f2a0f);
            border:2px solid {color};border-radius:16px;padding:1.5rem;
            text-align:center;max-width:320px;margin:0 auto;">
            <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:6px;">You chose:</div>
            <img src="{sprite}" width="140" style="image-rendering:pixelated"/>
            <h3 style="margin:0.3rem 0;">#{poke['id']:03d} {poke['name']}</h3>
            {types_html}
            <div style="margin-top:0.8rem;font-size:0.8rem;color:var(--text-muted);">
                ❤️ HP:{poke['hp']} &nbsp;⚔️ ATK:{poke['attack']} &nbsp;🛡️ DEF:{poke['defense']}
            </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            if st.button(f"✅ Confirm {poke['name']}!", use_container_width=True, key="confirm_starter_yes"):
                _finalise_new_player(name, poke)
                st.rerun()
        with c2:
            if st.button("← Go back", use_container_width=True, key="confirm_starter_no"):
                st.session_state.new_player_confirm_poke = None
                st.rerun()
        return

    # Show 3 options
    cols = st.columns(3)
    for i, poke in enumerate(options):
        with cols[i]:
            types_html = " ".join(type_badge_html(t) for t in poke["types"])
            st.markdown(
                f'<div class="pokemon-card">'
                f'<img src="{poke["sprite"]}" width="140" style="image-rendering:pixelated"/>'
                f'<h3 style="margin:0.3rem 0;">#{poke["id"]:03d} {poke["name"]}</h3>'
                f'{types_html}'
                f'<div style="margin-top:0.8rem;font-size:0.8rem;color:var(--text-muted);">'
                f'❤️ HP:{poke["hp"]} &nbsp;⚔️ ATK:{poke["attack"]} &nbsp;🛡️ DEF:{poke["defense"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            if st.button(f"Choose {poke['name']}!", key=f"new_starter_{i}"):
                st.session_state.new_player_confirm_poke = poke
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔀 Show different Pokémon", use_container_width=True):
            st.session_state.starter_options = None
            st.rerun()
    with col2:
        if st.button("❌ Cancel — delete this player", use_container_width=True):
            # Remove the blank trainer row we added
            df = load_teams()
            df = df[df["trainer"] != name].reset_index(drop=True)
            save_teams(df)
            for k in ["new_player_name","new_player_phase","new_player_confirm_poke"]:
                st.session_state.pop(k, None)
            st.rerun()


def _finalise_new_player(name: str, poke: dict):
    """Save starter choice and activate the new trainer."""
    from utils.csv_manager import load_teams, update_trainer, save_teams
    moves = fetch_moves(poke["id"])

    # Save to CSV
    df  = load_teams()
    df  = update_trainer(df, name,
        starter=poke["name"], starter_id=poke["id"], level=5,
        wins=0, losses=0, badges=0,
    )
    save_teams(df)

    # Load into session
    st.session_state.my_pokemon    = poke
    st.session_state.my_moves      = moves
    st.session_state.my_max_hp     = poke["hp"]
    st.session_state.my_current_hp = poke["hp"]
    st.session_state.my_level      = 5
    st.session_state.trainer_name  = name

    # Clear creation state
    for k in ["new_player_name","new_player_phase","new_player_confirm_poke","starter_options"]:
        st.session_state.pop(k, None)

    st.success(f"🎉 {name} joined with {poke['name']}! Welcome to Pokémon Journeys!")
    st.balloons()


# ── Main render ────────────────────────────────────────────────────────────────

def render():
    st.markdown('<div class="pokeball-header">⚡ POKÉMON JOURNEYS ⚡</div>', unsafe_allow_html=True)

    # ── New Player button — always visible at top ─────────────────────────────
    _create_player_button()
    st.markdown("---")

    df = load_teams()

    # ── New player starter pick (full screen flow) ────────────────────────────
    if st.session_state.get("new_player_phase") == "pick_starter":
        _new_player_starter_pick()
        return

    # ── First visit — no trainer selected ────────────────────────────────────
    if not st.session_state.get("trainer_name"):
        st.markdown("### 🎮 Who's playing first?")
        st.markdown("Select your trainer to begin your journey.")
        all_trainers = get_all_trainers()
        cols = st.columns(min(len(all_trainers), 3))
        for i, trainer in enumerate(all_trainers):
            with cols[i % 3]:
                emoji = _trainer_emoji(trainer)
                color = _trainer_color(trainer)
                st.markdown(
                    f'<div class="pokemon-card" style="padding:2rem 1rem;">'
                    f'<div style="font-size:3rem">{emoji}</div>'
                    f'<h3 style="margin:0.5rem 0;color:{color};">{trainer}</h3>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                if st.button(f"Play as {trainer}", key=f"trainer_{trainer}"):
                    st.session_state.trainer_name = trainer
                    st.rerun()

        return

    trainer = st.session_state.trainer_name
    emoji   = _trainer_emoji(trainer)
    color   = _trainer_color(trainer)

    # ── Trainer switcher ──────────────────────────────────────────────────────
    _trainer_switcher(trainer, df)

    # ── Current trainer data ──────────────────────────────────────────────────
    row = df[df["trainer"] == trainer]

    def _safe_val(r, key, default=""):
        try:
            return r.iloc[0][key]
        except Exception:
            return default

    starter_id_val = _safe_val(row, "starter_id", "")
    has_starter = (
        len(row) > 0
        and str(_safe_val(row, "starter", "")).strip() not in ("", "nan")
        and _safe_int(starter_id_val) > 0
    )

    if has_starter:
        poke_name  = _safe_val(row, "starter", "")
        poke_id    = _safe_int(_safe_val(row, "starter_id", 0))
        level      = _safe_int(_safe_val(row, "level", 5), 5)
        wins       = _safe_int(_safe_val(row, "wins", 0))
        losses     = _safe_int(_safe_val(row, "losses", 0))
        badges_n   = _safe_int(_safe_val(row, "badges", 0))

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
        if not st.session_state.get("my_pokemon") or st.session_state.my_pokemon.get("name") != poke_name:
            from utils.pokemon_api import fetch_pokemon
            poke = fetch_pokemon(poke_id)
            poke["level"] = level
            st.session_state.my_pokemon    = poke
            st.session_state.my_max_hp     = poke["hp"]
            st.session_state.my_current_hp = poke["hp"]
            st.session_state.my_level      = level
            if not st.session_state.get("my_moves"):
                from utils.movesets_manager import get_moveset, init_movesets_csv
                init_movesets_csv()
                custom = get_moveset(trainer, poke_id)
                st.session_state.my_moves = custom if custom else fetch_moves(poke_id)

        # ── Always visible at bottom ──────────────────────────────────────────
        return
        poke_name  = _safe_val(row, "starter", "")
        poke_id    = _safe_int(_safe_val(row, "starter_id", 0))
        level      = _safe_int(_safe_val(row, "level", 5), 5)
        wins       = _safe_int(_safe_val(row, "wins", 0))
        losses     = _safe_int(_safe_val(row, "losses", 0))
        badges_n   = _safe_int(_safe_val(row, "badges", 0))

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
        if not st.session_state.get("my_pokemon") or st.session_state.my_pokemon.get("name") != poke_name:
            from utils.pokemon_api import fetch_pokemon
            poke = fetch_pokemon(poke_id)
            poke["level"] = level
            st.session_state.my_pokemon    = poke
            st.session_state.my_max_hp     = poke["hp"]
            st.session_state.my_current_hp = poke["hp"]
            st.session_state.my_level      = level
            if not st.session_state.get("my_moves"):
                from utils.movesets_manager import get_moveset, init_movesets_csv
                init_movesets_csv()
                custom = get_moveset(trainer, poke_id)
                st.session_state.my_moves = custom if custom else fetch_moves(poke_id)
        return

    # ── Step 2: Choose starter ────────────────────────────────────────────────
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
            st.markdown(
                f'<div class="pokemon-card">'
                f'<img src="{poke["sprite"]}" width="140" style="image-rendering:pixelated"/>'
                f'<h3 style="margin:0.3rem 0;">#{poke["id"]:03d} {poke["name"]}</h3>'
                f'{types_html}'
                f'<div style="margin-top:0.8rem;font-size:0.8rem;color:var(--text-muted);">'
                f'❤️ HP:{poke["hp"]} &nbsp;⚔️ ATK:{poke["attack"]} &nbsp;🛡️ DEF:{poke["defense"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
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
        starter=poke["name"], starter_id=poke["id"],
        level=5, wins=0, losses=0, badges=0,
    )
    save_teams(df)
    st.success(f"You chose {poke['name']}! Let the journey begin!")
