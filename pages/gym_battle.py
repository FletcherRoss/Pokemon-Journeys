import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import random
import streamlit as st
from utils.pokemon_api import get_gym_leader_team, fetch_moves, type_badge_html
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.game_state import hp_percent, hp_bar_color, damage_calc, level_up_check

GYM_INFO = [
    {"name": "Brock",    "title": "Rock Gym",     "type": "rock",     "emoji": "🪨", "badge": "Boulder Badge",   "badge_key": "badge_rock"},
    {"name": "Erika",    "title": "Grass Gym",    "type": "grass",    "emoji": "🌿", "badge": "Rainbow Badge",   "badge_key": "badge_grass"},
    {"name": "Misty",    "title": "Water Gym",    "type": "water",    "emoji": "💧", "badge": "Cascade Badge",   "badge_key": "badge_water"},
    {"name": "Blaine",   "title": "Fire Gym",     "type": "fire",     "emoji": "🔥", "badge": "Volcano Badge",   "badge_key": "badge_fire"},
    {"name": "Sabrina",  "title": "Psychic Gym",  "type": "psychic",  "emoji": "🔮", "badge": "Marsh Badge",     "badge_key": "badge_psychic"},
    {"name": "Whitney",  "title": "Normal Gym",   "type": "normal",   "emoji": "⭐", "badge": "Plain Badge",     "badge_key": "badge_normal"},
    {"name": "Pryce",    "title": "Ice Gym",      "type": "ice",      "emoji": "❄️", "badge": "Glacier Badge",   "badge_key": "badge_ice"},
    {"name": "Lance",    "title": "Elite Four",   "type": "dragon",   "emoji": "🐉", "badge": "Champion Badge",  "badge_key": "badge_elite"},
]


def _guard() -> bool:
    if not st.session_state.trainer_name:
        st.warning("⚠️ Choose a trainer on the Home page first!")
        return False
    if not st.session_state.my_pokemon:
        st.warning("⚠️ Choose your starter Pokémon on the Home page first!")
        return False
    return True


def _hp_bar(label, current, maximum):
    pct   = hp_percent(current, maximum)
    color = hp_bar_color(pct)
    st.markdown(f"""
    <div style="margin-bottom:4px">
        <small>{label}: <b>{current}</b>/{maximum}</small>
        <div class="hp-bar-wrap">
            <div class="hp-bar-fill" style="width:{pct}%;background:{color};"></div>
        </div>
    </div>""", unsafe_allow_html=True)


def _show_gym_map(row):
    st.markdown("### 🗺️ Open World Gym Map")
    cols = st.columns(4)
    for i, gym in enumerate(GYM_INFO):
        badge_key = gym["badge_key"]
        earned    = int(row.get(badge_key, 0)) == 1
        with cols[i % 4]:
            css = "gym-badge-earned" if earned else "gym-badge-locked"
            st.markdown(f'<div class="{css}">{gym["emoji"]}</div>', unsafe_allow_html=True)
            st.markdown(f"<small><b>{gym['name']}</b><br>{gym['title']}</small>", unsafe_allow_html=True)
            if not earned:
                if st.button(f"Challenge!", key=f"gym_{i}"):
                    _start_gym_battle(i)
                    st.rerun()
            else:
                st.markdown("✅ _Beaten_")
        st.markdown("")


def _start_gym_battle(gym_index: int):
    team = get_gym_leader_team(gym_index)
    move_lists = [fetch_moves(p["id"]) for p in team]
    st.session_state.gym_index        = gym_index
    st.session_state.gym_leader_team  = team
    st.session_state.gym_leader_moves = move_lists
    st.session_state.gym_leader_hp    = [p["hp"] for p in team]
    st.session_state.gym_leader_index = 0
    st.session_state.battle_active    = True
    st.session_state.battle_result    = None
    st.session_state.battle_log       = [
        f"Gym Leader {GYM_INFO[gym_index]['name']} wants to battle!"
    ]


def _gym_attack(move: dict):
    gym_idx     = st.session_state.gym_index
    leader_idx  = st.session_state.gym_leader_index
    team        = st.session_state.gym_leader_team
    leader_hps  = st.session_state.gym_leader_hp
    leader_moves= st.session_state.gym_leader_moves
    my          = st.session_state.my_pokemon
    log         = st.session_state.battle_log

    opp      = team[leader_idx]
    opp_move = leader_moves[leader_idx]

    # Player attacks
    dmg = damage_calc(my, opp, move, st.session_state.my_level)
    leader_hps[leader_idx] = max(0, leader_hps[leader_idx] - dmg)
    log.append(f"➤ {my['name']} used {move['name']}! ({dmg} dmg)")
    st.session_state.gym_leader_hp = leader_hps

    if leader_hps[leader_idx] <= 0:
        log.append(f"💥 {opp['name']} fainted!")
        # Next pokemon?
        next_idx = leader_idx + 1
        if next_idx >= len(team):
            # Gym cleared!
            xp_gain = random.randint(50, 100)
            st.session_state.my_xp += xp_gain
            leveled = level_up_check()
            log.append(f"🏅 You defeated {GYM_INFO[gym_idx]['name']}! +{xp_gain} XP")
            if leveled:
                log.append(f"⬆️ {my['name']} grew to level {st.session_state.my_level}!")
            st.session_state.battle_result = "win"
            st.session_state.battle_active = False
            _record_gym_win(gym_idx)
        else:
            st.session_state.gym_leader_index = next_idx
            log.append(f"🔄 {GYM_INFO[gym_idx]['name']} sent out {team[next_idx]['name']}!")
        return

    # Opponent attacks
    opp_move_rand = random.choice(opp_move) if isinstance(opp_move, list) else opp_move
    opp_dmg = damage_calc(opp, my, opp_move_rand)
    st.session_state.my_current_hp = max(0, st.session_state.my_current_hp - opp_dmg)
    log.append(f"➤ {opp['name']} used {opp_move_rand['name']}! ({opp_dmg} dmg)")

    if st.session_state.my_current_hp <= 0:
        log.append(f"💀 {my['name']} fainted! You blacked out...")
        st.session_state.battle_result = "lose"
        st.session_state.battle_active = False
        st.session_state.my_current_hp = max(1, st.session_state.my_max_hp // 5)

    st.session_state.battle_log = log[-20:]


def _record_gym_win(gym_idx: int):
    trainer  = st.session_state.trainer_name
    badge_key= GYM_INFO[gym_idx]["badge_key"]
    df = load_teams()
    row = df[df["trainer"] == trainer]
    wins   = int(row.iloc[0]["wins"]) + 1 if len(row) else 1
    badges = int(row.iloc[0]["badges"]) + 1 if len(row) else 1
    level  = st.session_state.my_level
    df = update_trainer(df, trainer, wins=wins, badges=badges, level=level, **{badge_key: 1})
    save_teams(df)


def render():
    if not _guard():
        return

    st.markdown("## 🏟️ Gym Battles")

    trainer = st.session_state.trainer_name
    my      = st.session_state.my_pokemon
    df      = load_teams()
    row     = df[df["trainer"] == trainer].iloc[0] if len(df[df["trainer"] == trainer]) else {}

    # ── Not in gym battle ───────────────────────────────────────────────────
    if not st.session_state.battle_active and st.session_state.battle_result is None:
        _show_gym_map(row)
        return

    # ── Gym battle result ───────────────────────────────────────────────────
    if st.session_state.battle_result:
        gym  = GYM_INFO[st.session_state.gym_index]
        result = st.session_state.battle_result

        if result == "win":
            st.markdown(f'<div class="win-banner">🏅 {gym["badge"]} EARNED! 🏅</div>', unsafe_allow_html=True)
            st.balloons()
        else:
            st.markdown('<div class="lose-banner">💀 YOU BLACKED OUT!</div>', unsafe_allow_html=True)

        log_text = "\n".join(st.session_state.battle_log)
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)

        if st.button("← Back to Gym Map"):
            st.session_state.battle_active = False
            st.session_state.battle_result = None
            st.session_state.gym_leader_team = None
            st.session_state.battle_log = []
            st.rerun()
        return

    # ── Active gym battle ───────────────────────────────────────────────────
    gym      = GYM_INFO[st.session_state.gym_index]
    team     = st.session_state.gym_leader_team
    leader_i = st.session_state.gym_leader_index
    opp      = team[leader_i]
    opp_hp   = st.session_state.gym_leader_hp[leader_i]
    opp_max  = opp["hp"]

    st.markdown(f"### {gym['emoji']} vs. Gym Leader {gym['name']} ({gym['title']})")

    # Gym leader team preview
    team_icons = ""
    for ti, tp in enumerate(team):
        fainted = st.session_state.gym_leader_hp[ti] <= 0
        team_icons += f"<span style='opacity:{'0.3' if fainted else '1'};margin:2px;font-size:1.4rem'>{'💀' if fainted else '🔴'}</span>"
    st.markdown(f"<div>Leader's team: {team_icons}</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        sprite = my.get("sprite_anim") or my["sprite"]
        types_html = " ".join(type_badge_html(t) for t in my["types"])
        st.markdown(f"""
        <div class="pokemon-card" style="cursor:default;">
            <div style="font-size:0.75rem;color:var(--text-muted)">Lv.{st.session_state.my_level} – {trainer}</div>
            <img src="{sprite}" width="120" style="image-rendering:pixelated"/>
            <div style="font-weight:700;margin:4px 0;">{my['name']}</div>
            {types_html}
        </div>""", unsafe_allow_html=True)
        _hp_bar("HP", st.session_state.my_current_hp, st.session_state.my_max_hp)

    with c2:
        opp_sprite = opp.get("sprite_anim") or opp["sprite"]
        opp_types  = " ".join(type_badge_html(t) for t in opp["types"])
        st.markdown(f"""
        <div class="pokemon-card" style="cursor:default;">
            <div style="font-size:0.75rem;color:var(--text-muted)">Gym Leader {gym['name']}</div>
            <img src="{opp_sprite}" width="120" style="image-rendering:pixelated"/>
            <div style="font-weight:700;margin:4px 0;">{opp['name']}</div>
            {opp_types}
        </div>""", unsafe_allow_html=True)
        _hp_bar("HP", opp_hp, opp_max)

    st.markdown("---")
    st.markdown("#### Choose your move:")
    move_cols = st.columns(2)
    moves = st.session_state.my_moves or []
    for i, move in enumerate(moves):
        with move_cols[i % 2]:
            label = f"{move['name']} ({move['type'].upper()}, {move['power']} pwr)"
            if st.button(label, key=f"gym_move_{i}", use_container_width=True):
                _gym_attack(move)
                st.rerun()

    if st.session_state.battle_log:
        st.markdown("#### Battle Log")
        log_text = "\n".join(st.session_state.battle_log[-10:])
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)
