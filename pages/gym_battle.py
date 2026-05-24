import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import random
import streamlit as st
from utils.pokemon_api import get_gym_leader_team, fetch_moves, type_badge_html, fetch_pokemon
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.game_state import hp_percent, hp_bar_color, damage_calc, speed_order, level_up_check
from utils.captures_manager import load_captures, get_active_captures, init_captures_csv
from utils.movesets_manager import get_moveset, init_movesets_csv

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

TYPE_COLORS = {
    "fire":"#F08030","water":"#6890F0","grass":"#78C850","electric":"#F8D030",
    "psychic":"#F85888","ice":"#98D8D8","dragon":"#7038F8","dark":"#705848",
    "normal":"#A8A878","fighting":"#C03028","poison":"#A040A0","ground":"#E0C068",
    "flying":"#A890F0","bug":"#A8B820","rock":"#B8A038","ghost":"#705898",
    "steel":"#B8B8D0","fairy":"#EE99AC",
}


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
    for key in [
        "battle_active", "battle_result", "battle_log",
        "gym_leader_team", "gym_leader_moves", "gym_leader_hp",
        "gym_leader_index", "gym_index",
        # 2v2 keys
        "gym_my_team", "gym_my_hp", "gym_my_moves_list",
        "gym_my_active", "gym_leader_active",
        "gym_picking_team",
    ]:
        if key in ["battle_active", "gym_picking_team"]:
            st.session_state[key] = False
        elif key in ["battle_log"]:
            st.session_state[key] = []
        elif key in ["gym_leader_hp", "gym_my_hp"]:
            st.session_state[key] = []
        elif key in ["gym_leader_index", "gym_index", "gym_my_active", "gym_leader_active"]:
            st.session_state[key] = 0
        else:
            st.session_state[key] = None


def _hp_bar(label, current, maximum):
    pct   = hp_percent(current, maximum)
    color = hp_bar_color(pct)
    st.markdown(
        f'<div style="margin-bottom:4px"><small>{label}: <b>{current}</b>/{maximum}</small>'
        f'<div class="hp-bar-wrap"><div class="hp-bar-fill" style="width:{pct}%;background:{color};"></div></div></div>',
        unsafe_allow_html=True
    )


def _poke_card(poke, current_hp, label, fainted=False):
    sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{poke['id']}.png"
    types_html = " ".join(type_badge_html(t) for t in poke["types"])
    spd   = poke.get("speed", "?")
    opacity = "0.35" if fainted else "1"
    faint_badge = '<div style="color:#F44336;font-size:0.7rem;font-weight:700;">💀 FAINTED</div>' if fainted else ""
    st.markdown(
        f'<div class="pokemon-card" style="cursor:default;opacity:{opacity};">'
        f'<div style="font-size:0.7rem;color:var(--text-muted);">{label}</div>'
        f'<img src="{sprite}" width="90" style="image-rendering:pixelated"/>'
        f'<div style="font-weight:700;font-size:0.85rem;margin:3px 0;">{poke["name"]}</div>'
        f'{types_html}'
        f'<div style="font-size:0.65rem;color:var(--text-muted);margin-top:3px;">⚡ Spd:{spd}</div>'
        f'{faint_badge}'
        f'</div>',
        unsafe_allow_html=True
    )
    if not fainted:
        _hp_bar("HP", current_hp, poke["hp"])


# ── Roster builder ────────────────────────────────────────────────────────────

def _build_roster(trainer: str) -> list[dict]:
    """Return all available Pokémon for the trainer with moves loaded."""
    roster = []
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        r = row.iloc[0]
        try:
            sid = int(float(r.get("starter_id", 0) or 0))
            slv = int(float(r.get("level", 5) or 5))
        except (ValueError, TypeError):
            sid, slv = 0, 5
        if sid > 0:
            poke = fetch_pokemon(sid)
            poke["level"] = slv
            custom = get_moveset(trainer, sid)
            moves  = custom if custom else fetch_moves(sid)
            roster.append({"poke": poke, "moves": moves, "label": f"⭐ {poke['name']} (Starter, Lv.{slv})"})

    for _, cap in get_active_captures(trainer).iterrows():
        try:
            pid = int(float(cap["pokemon_id"]))
            lv  = int(float(cap.get("current_level") or cap.get("level_caught") or 5))
        except (ValueError, TypeError):
            continue
        poke = fetch_pokemon(pid)
        poke["level"] = lv
        custom = get_moveset(trainer, pid)
        moves  = custom if custom else fetch_moves(pid)
        roster.append({"poke": poke, "moves": moves, "label": f"⚾ {poke['name']} (Lv.{lv})"})
    return roster


# ── Gym map ───────────────────────────────────────────────────────────────────

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
                    _init_team_pick(i)
                    st.rerun()
            else:
                st.markdown("✅ _Beaten_")


# ── Team picker (step before battle) ─────────────────────────────────────────

def _init_team_pick(gym_index: int):
    """Set up the 2 strongest gym Pokémon and enter team-pick mode."""
    full_team  = get_gym_leader_team(gym_index)
    # Pick 2 strongest by base stat total (hp+atk+def+speed+sp_atk+sp_def)
    def bst(p):
        return p.get("hp",0)+p.get("attack",0)+p.get("defense",0)+p.get("speed",0)+p.get("sp_attack",0)+p.get("sp_defense",0)
    top2 = sorted(full_team, key=bst, reverse=True)[:2]
    move_lists = [fetch_moves(p["id"]) for p in top2]

    st.session_state.gym_index         = gym_index
    st.session_state.gym_leader_team   = top2
    st.session_state.gym_leader_moves  = move_lists
    st.session_state.gym_leader_hp     = [p["hp"] for p in top2]
    st.session_state.gym_leader_active = 0
    st.session_state.gym_picking_team  = True
    st.session_state.battle_active     = False
    st.session_state.battle_result     = None
    st.session_state.battle_log        = []
    st.session_state.gym_my_team       = None
    st.session_state.gym_my_hp         = []
    st.session_state.gym_my_active     = 0


def _render_team_picker(trainer: str):
    gym_idx = st.session_state.gym_index
    gym     = GYM_INFO[gym_idx]
    leader_team = st.session_state.gym_leader_team

    st.markdown(f"## {gym['emoji']} {gym['title']} — Pick Your Team")
    st.markdown(
        f"<small style='color:var(--text-muted)'>Gym Leader <b>{gym['name']}</b> is sending out "
        f"their <b>2 strongest</b> Pokémon. Choose <b>2 Pokémon</b> from your team to battle!</small>",
        unsafe_allow_html=True
    )

    # Show gym leader's 2
    st.markdown("### 🏟️ Leader's Team")
    lc1, lc2 = st.columns(2)
    for i, (col, poke) in enumerate(zip([lc1, lc2], leader_team)):
        sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{poke['id']}.png"
        types_html = " ".join(type_badge_html(t) for t in poke["types"])
        def bst(p): return p.get("hp",0)+p.get("attack",0)+p.get("defense",0)+p.get("speed",0)
        with col:
            st.markdown(
                f'<div class="pokemon-card" style="cursor:default;">'
                f'<img src="{sprite}" width="100" style="image-rendering:pixelated"/>'
                f'<div style="font-weight:700;margin:4px 0;">{poke["name"]}</div>'
                f'{types_html}'
                f'<div style="font-size:0.7rem;color:var(--text-muted);margin-top:4px;">'
                f'❤️{poke["hp"]} ⚔️{poke["attack"]} 🛡️{poke["defense"]} ⚡{poke["speed"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

    st.markdown("---")
    st.markdown("### 🎒 Your Team — Pick 2")

    roster = _build_roster(trainer)
    if len(roster) < 2:
        st.warning("You need at least 2 Pokémon (starter + 1 captured) to challenge a gym!")
        if st.button("← Back"):
            _reset_gym_state()
            st.rerun()
        return

    # Multiselect via checkboxes — track in session state
    if "gym_pick_selected" not in st.session_state:
        st.session_state.gym_pick_selected = []

    selected = st.session_state.gym_pick_selected
    cols_per_row = 3
    for row_start in range(0, len(roster), cols_per_row):
        chunk = roster[row_start:row_start + cols_per_row]
        cols  = st.columns(cols_per_row)
        for col, entry in zip(cols, chunk):
            poke   = entry["poke"]
            lv     = poke.get("level", 5)
            sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{poke['id']}.png"
            types_html = " ".join(type_badge_html(t) for t in poke["types"])
            is_sel = poke["name"] in selected
            border = "2px solid #FFCB05" if is_sel else "2px solid var(--poke-blue)"
            bg     = "linear-gradient(145deg,#2a3a0f,#1a2a05)" if is_sel else "linear-gradient(145deg,#1e2a4a,#0f1a35)"
            with col:
                st.markdown(
                    f'<div style="background:{bg};border:{border};border-radius:14px;'
                    f'padding:0.7rem;text-align:center;margin-bottom:4px;">'
                    f'<img src="{sprite}" width="65" style="image-rendering:pixelated"/>'
                    f'<div style="font-size:0.75rem;font-weight:700;margin:3px 0;">{poke["name"]}</div>'
                    f'{types_html}'
                    f'<div style="font-size:0.65rem;color:var(--text-muted);margin-top:2px;">Lv.{lv} ⚡{poke.get("speed","?")}</div>'
                    f'{"✅" if is_sel else ""}'
                    f'</div>',
                    unsafe_allow_html=True
                )
                if is_sel:
                    if st.button("Deselect", key=f"desel_{poke['id']}", use_container_width=True):
                        st.session_state.gym_pick_selected = [n for n in selected if n != poke["name"]]
                        st.rerun()
                else:
                    disabled = len(selected) >= 2
                    if st.button("Select", key=f"sel_{poke['id']}", use_container_width=True, disabled=disabled):
                        st.session_state.gym_pick_selected = selected + [poke["name"]]
                        st.rerun()

    st.markdown("---")
    sel_count = len(selected)
    st.markdown(f"**Selected: {sel_count}/2** — {', '.join(selected) if selected else 'None'}")

    bc1, bc2 = st.columns(2)
    with bc1:
        if st.button("← Back to Gym Map", use_container_width=True):
            st.session_state.gym_pick_selected = []
            _reset_gym_state()
            st.rerun()
    with bc2:
        if st.button("⚔️ Start Battle!", use_container_width=True, disabled=sel_count < 2):
            # Build the chosen team
            chosen = [e for e in roster if e["poke"]["name"] in selected][:2]
            st.session_state.gym_my_team      = [e["poke"]  for e in chosen]
            st.session_state.gym_my_moves_list = [e["moves"] for e in chosen]
            st.session_state.gym_my_hp        = [e["poke"]["hp"] for e in chosen]
            st.session_state.gym_my_active    = 0
            st.session_state.gym_leader_active = 0
            st.session_state.gym_picking_team  = False
            st.session_state.battle_active     = True
            st.session_state.battle_log        = [
                f"Gym Leader {GYM_INFO[st.session_state.gym_index]['name']} wants to battle!",
                f"You sent out {chosen[0]['poke']['name']} and {chosen[1]['poke']['name']}!",
            ]
            st.session_state.gym_pick_selected = []
            st.rerun()


# ── Battle logic ──────────────────────────────────────────────────────────────

def _active_my(i=None):
    i = i if i is not None else st.session_state.get("gym_my_active", 0)
    team = st.session_state.gym_my_team
    return team[i] if team and i < len(team) else None

def _active_opp():
    i    = st.session_state.get("gym_leader_active", 0)
    team = st.session_state.gym_leader_team
    return team[i] if team and i < len(team) else None


def _gym_attack(move: dict, attacker_idx: int):
    """Handle one Pokémon's attack against the active gym Pokémon."""
    gym_idx   = st.session_state.gym_index
    gym       = GYM_INFO[gym_idx]
    my_team   = st.session_state.gym_my_team
    my_hps    = st.session_state.gym_my_hp
    opp_team  = st.session_state.gym_leader_team
    opp_hps   = st.session_state.gym_leader_hp
    opp_idx   = st.session_state.gym_leader_active
    log       = st.session_state.battle_log

    attacker  = my_team[attacker_idx]
    opp       = opp_team[opp_idx]
    lv        = attacker.get("level", 5)

    dmg, hit = damage_calc(attacker, opp, move, lv)
    if not hit:
        log.append(f"➤ {attacker['name']} used {move['name']}... but it missed!")
    else:
        opp_hps[opp_idx] = max(0, opp_hps[opp_idx] - dmg)
        log.append(f"➤ {attacker['name']} used {move['name']}! ({dmg} dmg)")
    st.session_state.gym_leader_hp = opp_hps

    # Check opp fainted
    if opp_hps[opp_idx] <= 0:
        log.append(f"💥 {opp['name']} fainted!")
        next_opp = opp_idx + 1
        if next_opp >= len(opp_team):
            # All gym Pokémon fainted — win
            xp_gain = random.randint(50, 100)
            st.session_state.my_xp = st.session_state.get("my_xp", 0) + xp_gain
            level_up_check()
            log.append(f"🏅 You defeated {gym['name']}! +{xp_gain} XP")
            st.session_state.battle_result = "win"
            st.session_state.battle_active = False
            _record_gym_win(gym_idx)
        else:
            st.session_state.gym_leader_active = next_opp
            log.append(f"🔄 {gym['name']} sent out {opp_team[next_opp]['name']}!")
        st.session_state.battle_log = log[-30:]
        return

    # Gym Pokémon counter-attacks the active trainer Pokémon
    opp_moves = st.session_state.gym_leader_moves[opp_idx]
    opp_move  = random.choice(opp_moves) if isinstance(opp_moves, list) else opp_moves
    target_idx = st.session_state.gym_my_active
    target    = my_team[target_idx]
    opp_dmg, opp_hit = damage_calc(opp, target, opp_move, 50)
    if not opp_hit:
        log.append(f"➤ {opp['name']} used {opp_move['name']}... but it missed!")
    else:
        my_hps[target_idx] = max(0, my_hps[target_idx] - opp_dmg)
        log.append(f"➤ {opp['name']} used {opp_move['name']} on {target['name']}! ({opp_dmg} dmg)")
    st.session_state.gym_my_hp = my_hps

    # Check if attacked Pokémon fainted
    if my_hps[target_idx] <= 0:
        log.append(f"💀 {target['name']} fainted!")
        # Check if all trainer Pokémon fainted
        if all(h <= 0 for h in my_hps):
            log.append("💀 All your Pokémon fainted! You blacked out...")
            st.session_state.battle_result = "lose"
            st.session_state.battle_active = False
        else:
            # Auto-switch to surviving Pokémon
            surviving = next(i for i, h in enumerate(my_hps) if h > 0)
            st.session_state.gym_my_active = surviving
            log.append(f"🔄 {my_team[surviving]['name']} is now in battle!")

    st.session_state.battle_log = log[-30:]


def _record_gym_win(gym_idx: int):
    trainer   = st.session_state.trainer_name
    badge_key = GYM_INFO[gym_idx]["badge_key"]
    df  = load_teams()
    row = df[df["trainer"] == trainer]
    wins   = _safe_int(row.iloc[0]["wins"])   + 1 if len(row) else 1
    badges = _safe_int(row.iloc[0]["badges"]) + 1 if len(row) else 1
    level  = st.session_state.my_level
    df = update_trainer(df, trainer, wins=wins, badges=badges, level=level, **{badge_key: 1})
    save_teams(df)


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    if not _guard():
        return

    init_captures_csv()
    init_movesets_csv()

    st.markdown("## 🏟️ Gym Battles")

    trainer = st.session_state.trainer_name
    df      = load_teams()
    trainer_rows = df[df["trainer"] == trainer]
    row = trainer_rows.iloc[0] if len(trainer_rows) else {}

    # Init keys
    for key, default in [
        ("gym_index", 0), ("gym_leader_team", None), ("gym_leader_moves", None),
        ("gym_leader_hp", []), ("gym_leader_active", 0),
        ("gym_my_team", None), ("gym_my_hp", []), ("gym_my_moves_list", None),
        ("gym_my_active", 0), ("gym_picking_team", False),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Validate active battle state
    if st.session_state.battle_active:
        team = st.session_state.gym_leader_team
        if not team or not isinstance(team, list) or len(team) == 0:
            st.warning("⚠️ Battle state was invalid and has been reset.")
            _reset_gym_state()
            st.rerun()

    # ── Team picker ───────────────────────────────────────────────────────────
    if st.session_state.gym_picking_team:
        _render_team_picker(trainer)
        return

    # ── Gym map (no active battle) ────────────────────────────────────────────
    if not st.session_state.battle_active and st.session_state.battle_result is None:
        _show_gym_map(row)

        with st.expander("🎮 Log a gym battle fought outside the app"):
            gym_options = [f"{g['emoji']} {g['name']} — {g['title']}" for g in GYM_INFO]
            chosen = st.selectbox("Which gym?", gym_options, key="irl_gym_select")
            irl_result = st.radio("Result:", ["Win", "Loss"], horizontal=True, key="irl_gym_result")
            if st.button("✅ Log gym battle", key="irl_gym_log", use_container_width=True):
                gym_idx = gym_options.index(chosen)
                if irl_result == "Win":
                    _record_gym_win(gym_idx)
                    st.success(f"🏅 {GYM_INFO[gym_idx]['badge']} recorded!")
                else:
                    df2  = load_teams()
                    r2   = df2[df2["trainer"] == trainer]
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
        if st.session_state.battle_result == "win":
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

    # ── Active 2v2 battle ─────────────────────────────────────────────────────
    gym_idx  = st.session_state.gym_index
    gym      = GYM_INFO[min(gym_idx, len(GYM_INFO) - 1)]
    my_team  = st.session_state.gym_my_team  or []
    my_hps   = st.session_state.gym_my_hp    or []
    opp_team = st.session_state.gym_leader_team or []
    opp_hps  = st.session_state.gym_leader_hp  or []
    my_active_idx  = st.session_state.gym_my_active
    opp_active_idx = st.session_state.gym_leader_active

    if not my_team or not opp_team:
        st.warning("Battle state missing — resetting.")
        _reset_gym_state()
        st.rerun()
        return

    st.markdown(f"### {gym['emoji']} vs. Gym Leader {gym['name']} ({gym['title']})")

    # ── 4-card battlefield: your 2 vs leader's 2 ─────────────────────────────
    st.markdown("#### 🏟️ Battlefield")
    col_y1, col_y2, col_sep, col_e1, col_e2 = st.columns([2,2,0.4,2,2])

    for i, (col, poke, hp) in enumerate(zip([col_y1, col_y2], my_team, my_hps)):
        with col:
            is_active = (i == my_active_idx)
            fainted   = hp <= 0
            lbl_extra = " 🟢 ACTIVE" if is_active and not fainted else ""
            _poke_card(poke, hp, f"{trainer}{lbl_extra}", fainted=fainted)

    with col_sep:
        st.markdown("<div style='text-align:center;font-size:1.5rem;padding-top:60px;'>⚔️</div>",
                    unsafe_allow_html=True)

    for i, (col, poke, hp) in enumerate(zip([col_e1, col_e2], opp_team, opp_hps)):
        with col:
            is_active = (i == opp_active_idx)
            fainted   = hp <= 0
            lbl_extra = " 🔴 ACTIVE" if is_active and not fainted else ""
            _poke_card(poke, hp, f"{gym['name']}{lbl_extra}", fainted=fainted)

    # ── Active switcher ───────────────────────────────────────────────────────
    alive_mine = [i for i, h in enumerate(my_hps) if h > 0]
    if len(alive_mine) > 1:
        other = next(i for i in alive_mine if i != my_active_idx)
        other_name = my_team[other]["name"]
        if st.button(f"🔄 Switch active to {other_name}", use_container_width=False):
            st.session_state.gym_my_active = other
            st.session_state.battle_log.append(f"🔄 Switched active Pokémon to {other_name}!")
            st.rerun()

    # ── Move table for active gym Pokémon ─────────────────────────────────────
    if opp_active_idx < len(opp_team):
        active_opp   = opp_team[opp_active_idx]
        active_opp_moves = st.session_state.gym_leader_moves[opp_active_idx]
        if isinstance(active_opp_moves, list) and active_opp_moves:
            move_rows = ""
            for m in active_opp_moves:
                tc    = TYPE_COLORS.get(m.get("type","normal"), "#888")
                pwr   = m.get("power") or 0
                pwr_s = f"{'💥 ' if pwr>=80 else ''}{pwr or '—'}"
                pwr_c = "#F44336" if pwr>=80 else "#FFC107" if pwr>=50 else "#aaa"
                acc   = m.get("accuracy") or 100
                acc_c = "#4CAF50" if acc>=90 else "#FFC107" if acc>=70 else "#F44336"
                move_rows += (
                    f'<tr><td style="padding:3px 10px;font-weight:600;">{m["name"]}</td>'
                    f'<td style="padding:3px 8px;"><span class="type-badge" style="background:{tc};">{m.get("type","normal")}</span></td>'
                    f'<td style="padding:3px 8px;color:{pwr_c};">{pwr_s} pwr</td>'
                    f'<td style="padding:3px 8px;color:{acc_c};">{acc}%</td>'
                    f'<td style="padding:3px 8px;color:var(--text-muted);">{m.get("pp","?")} PP</td></tr>'
                )
            st.markdown(
                f'<div style="margin:0.5rem 0 0.8rem 0;">'
                f'<div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:4px;'
                f'text-transform:uppercase;letter-spacing:1px;">{active_opp["name"]}\'s moves</div>'
                f'<table style="width:100%;border-collapse:collapse;background:rgba(0,0,0,0.25);'
                f'border:1px solid var(--poke-blue);border-radius:8px;font-size:0.8rem;">'
                f'<thead><tr style="color:var(--text-muted);font-size:0.7rem;border-bottom:1px solid rgba(255,255,255,0.08);">'
                f'<th style="padding:4px 10px;text-align:left;">Move</th>'
                f'<th style="padding:4px 8px;text-align:left;">Type</th>'
                f'<th style="padding:4px 8px;text-align:left;">Power</th>'
                f'<th style="padding:4px 8px;text-align:left;">Acc</th>'
                f'<th style="padding:4px 8px;text-align:left;">PP</th>'
                f'</tr></thead><tbody>{move_rows}</tbody></table></div>',
                unsafe_allow_html=True
            )

    # ── Move buttons — 2 sets (one per trainer Pokémon) ───────────────────────
    st.markdown("---")
    for pi in range(2):
        if pi >= len(my_team):
            break
        poke = my_team[pi]
        hp   = my_hps[pi]
        is_active = (pi == my_active_idx)
        if hp <= 0:
            st.markdown(f"~~{poke['name']}~~ 💀 fainted")
            continue
        active_label = " (active)" if is_active else ""
        st.markdown(f"**{poke['name']}{active_label} — choose move:**")
        moves = st.session_state.gym_my_moves_list[pi] if st.session_state.gym_my_moves_list else []
        mcols = st.columns(2)
        for mi, move in enumerate(moves):
            acc   = move.get("accuracy") or 100
            label = f"{move['name']} ({move['type'].upper()}, {move.get('power') or '—'} pwr, {acc}%)"
            with mcols[mi % 2]:
                if st.button(label, key=f"gym_move_{pi}_{mi}", use_container_width=True):
                    _gym_attack(move, pi)
                    # Set this Pokémon as active after it attacks
                    if my_hps[pi] > 0:
                        st.session_state.gym_my_active = pi
                    st.rerun()

    # ── Manual HP sliders ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🎛️ Manual HP Adjustment")

    st.markdown("**Your team:**")
    for pi, (poke, hp) in enumerate(zip(my_team, my_hps)):
        new_hp = st.slider(
            f"{poke['name']} HP",
            min_value=0, max_value=max(1, poke["hp"]),
            value=max(0, min(hp, poke["hp"])),
            key=f"gym_sl_my_{pi}",
        )
        if new_hp != hp:
            my_hps[pi] = new_hp
            st.session_state.gym_my_hp = my_hps
            if new_hp <= 0:
                st.session_state.battle_log.append(f"💀 {poke['name']} fainted!")
                if all(h <= 0 for h in my_hps):
                    st.session_state.battle_result = "lose"
                    st.session_state.battle_active = False
            st.rerun()

    st.markdown("**Gym leader's team:**")
    for oi, (poke, hp) in enumerate(zip(opp_team, opp_hps)):
        new_hp = st.slider(
            f"{poke['name']} HP",
            min_value=0, max_value=max(1, poke["hp"]),
            value=max(0, min(hp, poke["hp"])),
            key=f"gym_sl_opp_{oi}",
        )
        if new_hp != hp:
            opp_hps[oi] = new_hp
            st.session_state.gym_leader_hp = opp_hps
            if new_hp <= 0:
                log = st.session_state.battle_log
                log.append(f"💥 {poke['name']} fainted!")
                if all(h <= 0 for h in opp_hps):
                    xp_gain = random.randint(50, 100)
                    st.session_state.my_xp = st.session_state.get("my_xp", 0) + xp_gain
                    level_up_check()
                    log.append(f"🏅 You defeated {gym['name']}! +{xp_gain} XP")
                    st.session_state.battle_result = "win"
                    st.session_state.battle_active = False
                    _record_gym_win(gym_idx)
                else:
                    next_opp = next((i for i, h in enumerate(opp_hps) if h > 0), None)
                    if next_opp is not None:
                        st.session_state.gym_leader_active = next_opp
                        log.append(f"🔄 {gym['name']} sent out {opp_team[next_opp]['name']}!")
                st.session_state.battle_log = log[-30:]
            st.rerun()

    # ── Override buttons ──────────────────────────────────────────────────────
    st.markdown("---")
    win_col, lose_col = st.columns(2)
    with win_col:
        if st.button("🎮 Override — I won IRL!", use_container_width=True):
            xp_gain = random.randint(50, 100)
            st.session_state.my_xp = st.session_state.get("my_xp", 0) + xp_gain
            level_up_check()
            log = st.session_state.battle_log
            log.append(f"[OVERRIDE] Gym won outside the app! +{xp_gain} XP")
            st.session_state.battle_log = log[-30:]
            st.session_state.battle_result = "win"
            st.session_state.battle_active = False
            _record_gym_win(gym_idx)
            st.rerun()
    with lose_col:
        if st.button("💀 Override — I lost IRL!", use_container_width=True):
            log = st.session_state.battle_log
            log.append("[OVERRIDE] Gym lost outside the app.")
            st.session_state.battle_log = log[-30:]
            st.session_state.battle_result = "lose"
            st.session_state.battle_active = False
            df2 = load_teams()
            r2  = df2[df2["trainer"] == trainer]
            losses = _safe_int(r2.iloc[0]["losses"]) + 1 if len(r2) else 1
            df2 = update_trainer(df2, trainer, losses=losses)
            save_teams(df2)
            st.rerun()

    # ── Battle log ────────────────────────────────────────────────────────────
    if st.session_state.battle_log:
        st.markdown("#### Battle Log")
        log_text = "\n".join(st.session_state.battle_log[-15:])
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)
