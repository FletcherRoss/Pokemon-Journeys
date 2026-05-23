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
    {"name": "Brock",   "title": "Rock Gym",    "type": "rock",    "emoji": "🪨", "badge": "Boulder Badge",  "badge_key": "badge_rock"},
    {"name": "Erika",   "title": "Grass Gym",   "type": "grass",   "emoji": "🌿", "badge": "Rainbow Badge",  "badge_key": "badge_grass"},
    {"name": "Misty",   "title": "Water Gym",   "type": "water",   "emoji": "💧", "badge": "Cascade Badge",  "badge_key": "badge_water"},
    {"name": "Blaine",  "title": "Fire Gym",    "type": "fire",    "emoji": "🔥", "badge": "Volcano Badge",  "badge_key": "badge_fire"},
    {"name": "Sabrina", "title": "Psychic Gym", "type": "psychic", "emoji": "🔮", "badge": "Marsh Badge",    "badge_key": "badge_psychic"},
    {"name": "Whitney", "title": "Normal Gym",  "type": "normal",  "emoji": "⭐", "badge": "Plain Badge",    "badge_key": "badge_normal"},
    {"name": "Pryce",   "title": "Ice Gym",     "type": "ice",     "emoji": "❄️", "badge": "Glacier Badge",  "badge_key": "badge_ice"},
    {"name": "Lance",   "title": "Elite Four",  "type": "dragon",  "emoji": "🐉", "badge": "Champion Badge", "badge_key": "badge_elite"},
]


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _guard() -> bool:
    if not st.session_state.trainer_name:
        st.warning("⚠️ Choose a trainer on the Home page first!")
        return False
    if not st.session_state.get("my_pokemon"):
        st.warning("⚠️ Choose your starter Pokémon on the Home page first!")
        return False
    return True


def _reset_gym_state():
    """Fully clear gym battle state to avoid stale index errors."""
    st.session_state.battle_active     = False
    st.session_state.battle_result     = None
    st.session_state.battle_log        = []
    st.session_state.gym_leader_team   = None
    st.session_state.gym_leader_moves  = None
    st.session_state.gym_leader_hp     = []
    st.session_state.gym_leader_index  = 0
    st.session_state.gym_index         = 0


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
        earned = _safe_int(row.get(gym["badge_key"], 0)) == 1
        with cols[i % 4]:
            css = "gym-badge-earned" if earned else "gym-badge-locked"
            st.markdown(f'<div class="{css}">{gym["emoji"]}</div>', unsafe_allow_html=True)
            st.markdown(f"<small><b>{gym['name']}</b><br>{gym['title']}</small>", unsafe_allow_html=True)
            if not earned:
                if st.button("Challenge!", key=f"gym_{i}"):
                    _start_gym_battle(i)
                    st.rerun()
            else:
                st.markdown("✅ _Beaten_")


def _start_gym_battle(gym_index: int):
    team       = get_gym_leader_team(gym_index)
    move_lists = [fetch_moves(p["id"]) for p in team]
    st.session_state.gym_index        = gym_index
    st.session_state.gym_leader_team  = team
    st.session_state.gym_leader_moves = move_lists
    st.session_state.gym_leader_hp    = [p["hp"] for p in team]
    st.session_state.gym_leader_index = 0
    st.session_state.battle_active    = True
    st.session_state.battle_result    = None
    st.session_state.battle_log       = [f"Gym Leader {GYM_INFO[gym_index]['name']} wants to battle!"]


def _gym_attack(move: dict):
    gym_idx    = st.session_state.gym_index
    leader_idx = st.session_state.gym_leader_index
    team       = st.session_state.gym_leader_team
    leader_hps = st.session_state.gym_leader_hp
    my         = st.session_state.my_pokemon
    log        = st.session_state.battle_log

    # Safety check
    if not team or leader_idx >= len(team):
        log.append("⚠️ Battle state error — resetting.")
        _reset_gym_state()
        st.session_state.battle_log = log
        return

    opp      = team[leader_idx]
    opp_move = st.session_state.gym_leader_moves[leader_idx]

    # Player attacks
    dmg = damage_calc(my, opp, move, st.session_state.my_level)
    leader_hps[leader_idx] = max(0, leader_hps[leader_idx] - dmg)
    log.append(f"➤ {my['name']} used {move['name']}! ({dmg} dmg)")
    st.session_state.gym_leader_hp = leader_hps

    if leader_hps[leader_idx] <= 0:
        log.append(f"💥 {opp['name']} fainted!")
        next_idx = leader_idx + 1
        if next_idx >= len(team):
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
        st.session_state.battle_log = log[-20:]
        return

    # Opponent attacks back
    opp_move_pick = random.choice(opp_move) if isinstance(opp_move, list) else opp_move
    opp_dmg = damage_calc(opp, my, opp_move_pick)
    st.session_state.my_current_hp = max(0, st.session_state.my_current_hp - opp_dmg)
    log.append(f"➤ {opp['name']} used {opp_move_pick['name']}! ({opp_dmg} dmg)")

    if st.session_state.my_current_hp <= 0:
        log.append(f"💀 {my['name']} fainted! You blacked out...")
        st.session_state.battle_result = "lose"
        st.session_state.battle_active = False
        st.session_state.my_current_hp = max(1, st.session_state.my_max_hp // 5)

    st.session_state.battle_log = log[-20:]


def _record_gym_win(gym_idx: int):
    trainer   = st.session_state.trainer_name
    badge_key = GYM_INFO[gym_idx]["badge_key"]
    df  = load_teams()
    row = df[df["trainer"] == trainer]
    wins   = _safe_int(row.iloc[0]["wins"]) + 1   if len(row) else 1
    badges = _safe_int(row.iloc[0]["badges"]) + 1 if len(row) else 1
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
    trainer_rows = df[df["trainer"] == trainer]
    row = trainer_rows.iloc[0] if len(trainer_rows) else {}

    # ── Ensure all gym session keys exist ────────────────────────────────────
    for key, default in [
        ("gym_index", 0), ("gym_leader_team", None), ("gym_leader_moves", None),
        ("gym_leader_hp", []), ("gym_leader_index", 0),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # ── Validate active battle state isn't stale ─────────────────────────────
    if st.session_state.battle_active:
        team     = st.session_state.gym_leader_team
        leader_i = st.session_state.gym_leader_index
        if (team is None
                or not isinstance(team, list)
                or len(team) == 0
                or leader_i >= len(team)
                or leader_i < 0):
            st.warning("⚠️ Battle state was invalid and has been reset.")
            _reset_gym_state()
            st.rerun()

    # ── Not in battle ─────────────────────────────────────────────────────────
    if not st.session_state.battle_active and st.session_state.battle_result is None:
        _show_gym_map(row)

        # Outside battle log
        with st.expander("🎮 Log a gym battle fought outside the app"):
            st.markdown(
                "<small style='color:var(--text-muted)'>Fought a gym leader in real life? Record it here.</small>",
                unsafe_allow_html=True,
            )
            gym_options = [f"{g['emoji']} {g['name']} — {g['title']}" for g in GYM_INFO]
            chosen = st.selectbox("Which gym?", gym_options, key="irl_gym_select")
            irl_result = st.radio("Result:", ["Win", "Loss"], horizontal=True, key="irl_gym_result")
            if st.button("✅ Log gym battle", key="irl_gym_log", use_container_width=True):
                gym_idx = gym_options.index(chosen)
                if irl_result == "Win":
                    _record_gym_win(gym_idx)
                    st.success(f"🏅 {GYM_INFO[gym_idx]['badge']} recorded!")
                else:
                    df2 = load_teams()
                    r2  = df2[df2["trainer"] == trainer]
                    losses = _safe_int(r2.iloc[0]["losses"]) + 1 if len(r2) else 1
                    df2 = update_trainer(df2, trainer, losses=losses)
                    save_teams(df2)
                    st.warning("💀 Loss recorded.")
                st.rerun()
        return

    # ── Battle result ─────────────────────────────────────────────────────────
    if st.session_state.battle_result:
        gym_idx = st.session_state.get("gym_index", 0)
        gym     = GYM_INFO[min(gym_idx, len(GYM_INFO) - 1)]
        result  = st.session_state.battle_result

        if result == "win":
            st.markdown(f'<div class="win-banner">🏅 {gym["badge"]} EARNED! 🏅</div>', unsafe_allow_html=True)
            st.balloons()
        else:
            st.markdown('<div class="lose-banner">💀 YOU BLACKED OUT!</div>', unsafe_allow_html=True)

        log_text = "\n".join(st.session_state.battle_log)
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)

        if st.button("← Back to Gym Map"):
            _reset_gym_state()
            st.rerun()
        return

    # ── Active gym battle ─────────────────────────────────────────────────────
    gym_idx  = st.session_state.gym_index
    gym      = GYM_INFO[min(gym_idx, len(GYM_INFO) - 1)]
    team     = st.session_state.gym_leader_team
    leader_i = st.session_state.gym_leader_index
    opp      = team[leader_i]
    opp_hp   = st.session_state.gym_leader_hp[leader_i]
    opp_max  = opp["hp"]

    st.markdown(f"### {gym['emoji']} vs. Gym Leader {gym['name']} ({gym['title']})")

    # Leader team status icons
    team_icons = "".join(
        f"<span style='opacity:{'0.3' if st.session_state.gym_leader_hp[ti] <= 0 else '1'};"
        f"margin:2px;font-size:1.4rem'>{'💀' if st.session_state.gym_leader_hp[ti] <= 0 else '🔴'}</span>"
        for ti in range(len(team))
    )
    st.markdown(f"<div>Leader's team: {team_icons}</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        sprite     = my.get("sprite_anim") or my["sprite"]
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

    # ── Moves ─────────────────────────────────────────────────────────────────
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

    # ── Manual HP sliders ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🎛️ Manual HP Adjustment")
    sl1, sl2 = st.columns(2)
    with sl1:
        new_my_hp = st.slider(
            f"{my['name']} HP",
            min_value=0, max_value=max(1, st.session_state.my_max_hp),
            value=max(0, min(st.session_state.my_current_hp, st.session_state.my_max_hp)),
            key="gym_slider_my_hp",
        )
        if new_my_hp != st.session_state.my_current_hp:
            st.session_state.my_current_hp = new_my_hp
            if new_my_hp <= 0:
                st.session_state.battle_log.append(f"💀 {my['name']} fainted! You blacked out...")
                st.session_state.battle_result = "lose"
                st.session_state.battle_active = False
                st.session_state.my_current_hp = max(1, st.session_state.my_max_hp // 5)
            st.rerun()
    with sl2:
        new_opp_hp = st.slider(
            f"{opp['name']} HP",
            min_value=0, max_value=max(1, opp_max),
            value=max(0, min(opp_hp, opp_max)),
            key="gym_slider_opp_hp",
        )
        if new_opp_hp != opp_hp:
            hps = st.session_state.gym_leader_hp
            hps[leader_i] = new_opp_hp
            st.session_state.gym_leader_hp = hps
            if new_opp_hp <= 0:
                log = st.session_state.battle_log
                log.append(f"💥 {opp['name']} fainted!")
                next_idx = leader_i + 1
                if next_idx >= len(team):
                    xp_gain = random.randint(50, 100)
                    st.session_state.my_xp += xp_gain
                    level_up_check()
                    log.append(f"🏅 You defeated {gym['name']}! +{xp_gain} XP")
                    st.session_state.battle_result = "win"
                    st.session_state.battle_active = False
                    _record_gym_win(gym_idx)
                else:
                    st.session_state.gym_leader_index = next_idx
                    log.append(f"🔄 {gym['name']} sent out {team[next_idx]['name']}!")
                st.session_state.battle_log = log[-20:]
            st.rerun()

    # ── Override buttons ──────────────────────────────────────────────────────
    st.markdown("---")
    win_col, lose_col = st.columns(2)
    with win_col:
        if st.button("🎮 Override — I won IRL!", use_container_width=True):
            xp_gain = random.randint(50, 100)
            st.session_state.my_xp += xp_gain
            level_up_check()
            log = st.session_state.battle_log
            log.append(f"[OVERRIDE] Gym won outside the app! +{xp_gain} XP")
            st.session_state.battle_log = log[-20:]
            st.session_state.battle_result = "win"
            st.session_state.battle_active = False
            _record_gym_win(gym_idx)
            st.rerun()
    with lose_col:
        if st.button("💀 Override — I lost IRL!", use_container_width=True):
            log = st.session_state.battle_log
            log.append("[OVERRIDE] Gym lost outside the app.")
            st.session_state.battle_log = log[-20:]
            st.session_state.battle_result = "lose"
            st.session_state.battle_active = False
            st.session_state.my_current_hp = max(1, st.session_state.my_max_hp // 5)
            df2 = load_teams()
            r2  = df2[df2["trainer"] == trainer]
            losses = _safe_int(r2.iloc[0]["losses"]) + 1 if len(r2) else 1
            df2 = update_trainer(df2, trainer, losses=losses)
            save_teams(df2)
            st.rerun()

    # ── Battle log ────────────────────────────────────────────────────────────
    if st.session_state.battle_log:
        st.markdown("#### Battle Log")
        log_text = "\n".join(st.session_state.battle_log[-10:])
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)
