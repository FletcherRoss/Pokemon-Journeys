import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import random
import streamlit as st
from utils.pokemon_api import get_random_wild, fetch_moves, type_badge_html
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.game_state import (
    hp_percent, hp_bar_color, damage_calc, reset_battle, level_up_check
)


def _guard() -> bool:
    if not st.session_state.trainer_name:
        st.warning("⚠️ Choose a trainer on the Home page first!")
        return False
    if not st.session_state.my_pokemon:
        st.warning("⚠️ Choose your starter Pokémon on the Home page first!")
        return False
    return True


def _hp_bar(label: str, current: int, maximum: int):
    pct   = hp_percent(current, maximum)
    color = hp_bar_color(pct)
    st.markdown(f"""
    <div style="margin-bottom:4px">
        <small>{label}: <b>{current}</b>/{maximum}</small>
        <div class="hp-bar-wrap">
            <div class="hp-bar-fill" style="width:{pct}%;background:{color};"></div>
        </div>
    </div>""", unsafe_allow_html=True)


def _show_pokemon_card(poke: dict, current_hp: int, label: str, animated: bool = False):
    sprite = poke.get("sprite_anim") if animated else poke.get("sprite")
    types_html = " ".join(type_badge_html(t) for t in poke["types"])
    st.markdown(f"""
    <div class="pokemon-card" style="cursor:default;">
        <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:4px">{label}</div>
        <img src="{sprite}" width="120" style="image-rendering:pixelated"/>
        <div style="font-weight:700;margin:4px 0;">{poke['name']}</div>
        {types_html}
    </div>""", unsafe_allow_html=True)
    _hp_bar("HP", current_hp, poke["hp"])


def _start_encounter():
    wild = get_random_wild()
    moves = fetch_moves(wild["id"])
    st.session_state.opponent_pokemon    = wild
    st.session_state.opponent_moves      = moves
    st.session_state.opponent_max_hp     = wild["hp"]
    st.session_state.opponent_current_hp = wild["hp"]
    st.session_state.battle_active       = True
    st.session_state.battle_result       = None
    st.session_state.battle_log          = [f"A wild {wild['name']} appeared!"]
    st.session_state.battle_turn         = 0


def _player_attack(move: dict):
    my   = st.session_state.my_pokemon
    opp  = st.session_state.opponent_pokemon
    log  = st.session_state.battle_log

    # Player hits opponent
    dmg = damage_calc(my, opp, move, st.session_state.my_level)
    st.session_state.opponent_current_hp = max(0, st.session_state.opponent_current_hp - dmg)
    log.append(f"➤ {my['name']} used {move['name']}! ({dmg} dmg)")

    # Check faint
    if st.session_state.opponent_current_hp <= 0:
        xp_gain = random.randint(15, 35)
        st.session_state.my_xp += xp_gain
        leveled = level_up_check()
        log.append(f"🏆 Wild {opp['name']} fainted! +{xp_gain} XP")
        if leveled:
            log.append(f"⬆️ {my['name']} grew to level {st.session_state.my_level}!")
        st.session_state.battle_result = "win"
        st.session_state.battle_active = False
        _record_result("win")
        return

    # Opponent attacks back
    opp_move = random.choice(st.session_state.opponent_moves)
    opp_dmg  = damage_calc(opp, my, opp_move)
    st.session_state.my_current_hp = max(0, st.session_state.my_current_hp - opp_dmg)
    log.append(f"➤ {opp['name']} used {opp_move['name']}! ({opp_dmg} dmg)")

    if st.session_state.my_current_hp <= 0:
        log.append(f"💀 {my['name']} fainted...")
        st.session_state.battle_result = "lose"
        st.session_state.battle_active = False
        _record_result("lose")

    st.session_state.battle_turn += 1
    st.session_state.battle_log = log[-20:]  # keep last 20 lines


def _record_result(result: str):
    trainer = st.session_state.trainer_name
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        wins   = int(row.iloc[0]["wins"]) + (1 if result == "win" else 0)
        losses = int(row.iloc[0]["losses"]) + (1 if result == "lose" else 0)
        level  = st.session_state.my_level
        df = update_trainer(df, trainer, wins=wins, losses=losses, level=level)
        save_teams(df)
    if result == "lose":
        # Restore HP to 20%
        st.session_state.my_current_hp = max(1, st.session_state.my_max_hp // 5)


def _try_evolve():
    from utils.pokemon_api import get_evolution, fetch_moves
    poke = st.session_state.my_pokemon
    evolved = get_evolution(poke["id"])
    if evolved:
        st.session_state.my_pokemon = evolved
        st.session_state.my_max_hp  = evolved["hp"]
        st.session_state.my_current_hp = evolved["hp"]
        st.session_state.my_moves = fetch_moves(evolved["id"])
        # Update CSV
        trainer = st.session_state.trainer_name
        df = load_teams()
        row = df[df["trainer"] == trainer]
        evos = int(row.iloc[0].get("evolutions", 0)) + 1 if len(row) else 1
        df = update_trainer(df, trainer,
            starter=evolved["name"],
            starter_id=evolved["id"],
            evolutions=evos,
        )
        save_teams(df)
        return evolved["name"]
    return None


def render():
    if not _guard():
        return

    st.markdown("## ⚔️ Wild Battle")

    my   = st.session_state.my_pokemon
    trainer = st.session_state.trainer_name

    # ── Not in battle ───────────────────────────────────────────────────────
    if not st.session_state.battle_active and st.session_state.battle_result is None:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(my.get("sprite_anim") or my["sprite"], width=160)
        with col2:
            st.markdown(f"### {my['name']} (Lv.{st.session_state.my_level})")
            _hp_bar("HP", st.session_state.my_current_hp, st.session_state.my_max_hp)
            st.markdown(f"**XP:** {st.session_state.my_xp} / {st.session_state.my_level * 10}")

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🌿 Walk into the tall grass!", use_container_width=True):
                _start_encounter()
                st.rerun()
        with c2:
            # Evolution check
            wins = 0
            df = load_teams()
            row = df[df["trainer"] == trainer]
            if len(row):
                wins = int(row.iloc[0]["wins"])
            if wins > 0 and wins % 5 == 0:
                if st.button("✨ Check for Evolution!", use_container_width=True):
                    evolved_name = _try_evolve()
                    if evolved_name:
                        st.success(f"🎉 {my['name']} evolved into {evolved_name}!")
                        st.rerun()
                    else:
                        st.info(f"{my['name']} can't evolve further right now.")
        return

    # ── Battle result ───────────────────────────────────────────────────────
    if st.session_state.battle_result:
        result = st.session_state.battle_result
        if result == "win":
            st.markdown('<div class="win-banner">🏆 YOU WIN! 🏆</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="lose-banner">💀 YOUR POKÉMON FAINTED!</div>', unsafe_allow_html=True)

        st.markdown("#### Battle Log")
        log_text = "\n".join(st.session_state.battle_log)
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🌿 Find another battle!", use_container_width=True):
                reset_battle()
                st.rerun()
        with c2:
            if st.button("🏠 Rest at Pokémon Center", use_container_width=True):
                st.session_state.my_current_hp = st.session_state.my_max_hp
                reset_battle()
                st.success(f"{my['name']} was fully healed!")
                st.rerun()
        return

    # ── Active battle ────────────────────────────────────────────────────────
    opp = st.session_state.opponent_pokemon

    col1, col2 = st.columns(2)
    with col1:
        _show_pokemon_card(my, st.session_state.my_current_hp, f"Lv.{st.session_state.my_level} – {trainer}", animated=True)
    with col2:
        _show_pokemon_card(opp, st.session_state.opponent_current_hp, "Wild Pokémon", animated=True)

    st.markdown("---")
    st.markdown("#### Choose your move:")
    move_cols = st.columns(2)
    moves = st.session_state.my_moves or []
    for i, move in enumerate(moves):
        col = move_cols[i % 2]
        type_color = {"fire":"#F08030","water":"#6890F0","grass":"#78C850",
                      "normal":"#A8A878","electric":"#F8D030"}.get(move["type"], "#888")
        with col:
            label = f"{move['name']} ({move['type'].upper()}, {move['power']} pwr)"
            if st.button(label, key=f"move_{i}", use_container_width=True):
                _player_attack(move)
                st.rerun()

    st.markdown("---")
    if st.button("🏃 Run away!", use_container_width=False):
        st.session_state.battle_log.append("Got away safely!")
        reset_battle()
        st.rerun()

    # Battle log
    if st.session_state.battle_log:
        st.markdown("#### Battle Log")
        log_text = "\n".join(st.session_state.battle_log[-10:])
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)
