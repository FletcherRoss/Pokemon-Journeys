import sys, random
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from utils.pokemon_api import fetch_pokemon, fetch_moves, type_badge_html
from utils.csv_manager import (
    load_teams, save_teams, update_trainer,
    get_all_trainers, get_champion, set_champion,
)
from utils.captures_manager import load_captures, get_active_captures, level_up_team
from utils.movesets_manager import get_moveset, init_movesets_csv
from utils.game_state import hp_percent, hp_bar_color, damage_calc, effectiveness_label

BADGES_REQUIRED = 8

# ── Elite Four trainers (type-themed, final-evolution Pokemon) ────────────────
ELITE_FOUR = [
    {
        "name": "Lord Arren",
        "title": "Master of Fire",
        "emoji": "🔥",
        "color": "#F08030",
        "team_ids": [6, 59, 38],   # Charizard, Arcanine, Ninetales
    },
    {
        "name": "Lady Vex",
        "title": "Mistress of Psychic",
        "emoji": "🔮",
        "color": "#F85888",
        "team_ids": [65, 196, 121],  # Alakazam, Espeon, Starmie
    },
    {
        "name": "Duke Krag",
        "title": "Warlord of Rock",
        "emoji": "🪨",
        "color": "#B8A038",
        "team_ids": [248, 219, 141],  # Tyranitar, Magcargo, Kabutops
    },
    {
        "name": "Sage Mira",
        "title": "Keeper of Dragons",
        "emoji": "🐉",
        "color": "#7038F8",
        "team_ids": [149, 230, 373],  # Dragonite, Kingdra, Salamence
    },
]

# Between-round bonus cards (no skip option)
E4_CARDS = [
    {"id": "heal",    "emoji": "💊", "name": "Full Heal",     "desc": "Restore all your Pokémon to full HP!",            "color": "#4CAF50"},
    {"id": "levelup", "emoji": "⬆️", "name": "Level Up!",    "desc": "Your whole team levels up ×1.",                   "color": "#FFCB05"},
    {"id": "attack",  "emoji": "⚔️", "name": "Power Surge",  "desc": "Your attacks deal ×1.5 damage next battle.",      "color": "#F08030"},
    {"id": "nothing", "emoji": "💨", "name": "Catch Your Breath", "desc": "No bonus — but you're still in this!",       "color": "#888"},
    {"id": "revive",  "emoji": "✨", "name": "Revive",        "desc": "Fainted Pokémon are restored to 50% HP.",         "color": "#64B5F6"},
    {"id": "shield",  "emoji": "🛡️", "name": "Iron Defense",  "desc": "Incoming damage reduced by half next battle.",    "color": "#B8B8D0"},
]


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _load_trainer_roster(trainer: str) -> list[dict]:
    """Starter + active captures with moves."""
    roster = []
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        r = row.iloc[0]
        try:
            pid = int(float(r.get("starter_id", 0) or 0))
            lv  = int(float(r.get("level", 5) or 5))
        except (ValueError, TypeError):
            pid, lv = 0, 5
        if pid > 0:
            poke = fetch_pokemon(pid)
            poke["level"] = lv
            custom = get_moveset(trainer, pid)
            moves  = custom if custom else fetch_moves(pid)
            roster.append({"poke": poke, "moves": moves})
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
        roster.append({"poke": poke, "moves": moves})
    return roster


def _load_elite_team(e4_idx: int) -> list[dict]:
    e4 = ELITE_FOUR[e4_idx]
    team = []
    for pid in e4["team_ids"]:
        poke = fetch_pokemon(pid)
        poke["level"] = 60 + e4_idx * 5  # 60 / 65 / 70 / 75
        moves = fetch_moves(pid)
        team.append({"poke": poke, "moves": moves})
    return team


def _load_champion_team(champion: str) -> list[dict]:
    """Load the champion's current active team."""
    return _load_trainer_roster(champion)[:3]


# ── Session init/reset ────────────────────────────────────────────────────────

def _init():
    defaults = {
        "e4_phase":           "setup",  # setup|pick_team|card|battle|champion_battle|result
        "e4_trainer":         None,
        "e4_battle_idx":      0,        # 0-3 = elite four, 4 = champion
        "e4_my_team":         None,     # list of 3 {poke, moves}
        "e4_my_hp":           [],
        "e4_my_active":       0,
        "e4_enemy_team":      None,     # list of 3 {poke, moves}
        "e4_enemy_hp":        [],
        "e4_enemy_active":    0,
        "e4_log":             [],
        "e4_card_pool":       [],
        "e4_picked_card":     None,
        "e4_modifier":        None,     # "attack" | "shield" | None
        "e4_pick_sel":        [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    for k in list(st.session_state.keys()):
        if k.startswith("e4_"):
            del st.session_state[k]


# ── UI helpers ────────────────────────────────────────────────────────────────

def _hp_bar(label, current, maximum):
    pct   = hp_percent(current, maximum)
    color = hp_bar_color(pct)
    st.markdown(
        f'<div style="margin-bottom:4px"><small>{label}: <b>{current}</b>/{maximum}</small>'
        f'<div class="hp-bar-wrap"><div class="hp-bar-fill" '
        f'style="width:{pct}%;background:{color};"></div></div></div>',
        unsafe_allow_html=True
    )


def _poke_card(poke, hp, label, color="#3D7DCA", fainted=False):
    sprite  = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{poke['id']}.png"
    types   = " ".join(type_badge_html(t) for t in poke["types"])
    opacity = "0.3" if fainted else "1"
    faint_t = '<div style="color:#F44336;font-size:0.65rem;font-weight:700;">💀 FAINTED</div>' if fainted else ""
    spd     = poke.get("speed", "?")
    st.markdown(
        f'<div class="pokemon-card" style="cursor:default;opacity:{opacity};border-color:{color};">'
        f'<div style="font-size:0.65rem;color:var(--text-muted);">{label}</div>'
        f'<img src="{sprite}" width="80" style="image-rendering:pixelated"/>'
        f'<div style="font-size:0.8rem;font-weight:700;margin:3px 0;">{poke["name"]}</div>'
        f'{types}'
        f'<div style="font-size:0.62rem;color:var(--text-muted);margin-top:3px;">Lv.{poke.get("level","?")} ⚡{spd}</div>'
        f'{faint_t}</div>',
        unsafe_allow_html=True
    )
    if not fainted:
        _hp_bar("HP", hp, poke["hp"])


# ── Phases ────────────────────────────────────────────────────────────────────

def _phase_setup():
    trainer = st.session_state.get("trainer_name")
    if not trainer:
        st.warning("Choose a trainer on the Home page first.")
        return

    df  = load_teams()
    row = df[df["trainer"] == trainer]
    if not len(row):
        st.warning("Trainer not found. Go to Home page first.")
        return

    badges = _safe_int(row.iloc[0].get("badges", 0))
    champion = get_champion()

    st.markdown("## 🏆 Elite Four Challenge")

    if badges < BADGES_REQUIRED:
        st.markdown(f"""
        <div style="background:rgba(0,0,0,0.3);border:2px solid #555;border-radius:14px;
            padding:1.5rem;text-align:center;">
            <div style="font-size:2rem">🔒</div>
            <div style="font-weight:700;font-size:1rem;margin:6px 0;">Not Yet!</div>
            <div style="color:var(--text-muted);">You need all <b>8 gym badges</b> to challenge the Elite Four.<br>
            You have <b style="color:#FFCB05;">{badges}/8</b> badges.</div>
        </div>""", unsafe_allow_html=True)
        return

    # Champion display
    if champion:
        ccolor = "#FFCB05"
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,rgba(255,203,5,0.1),rgba(255,203,5,0.05));
            border:2px solid #FFCB05;border-radius:14px;padding:1rem;margin-bottom:1rem;text-align:center;">
            <div style="font-size:1.5rem">👑</div>
            <div style="font-size:0.9rem;font-weight:700;color:#FFCB05;">Current Champion: {champion}</div>
            <div style="font-size:0.8rem;color:var(--text-muted);">Defeat the Elite Four AND {champion} to claim the title!</div>
        </div>""", unsafe_allow_html=True)

    # Elite Four preview
    st.markdown("### The Elite Four")
    cols = st.columns(4)
    for col, e4 in zip(cols, ELITE_FOUR):
        with col:
            st.markdown(
                f'<div style="border:2px solid {e4["color"]};border-radius:12px;'
                f'padding:0.7rem;text-align:center;">'
                f'<div style="font-size:1.8rem">{e4["emoji"]}</div>'
                f'<div style="font-weight:700;color:{e4["color"]};font-size:0.85rem;">{e4["name"]}</div>'
                f'<div style="font-size:0.7rem;color:var(--text-muted);">{e4["title"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
    if champion:
        st.markdown(
            f'<div style="border:2px solid #FFCB05;border-radius:12px;'
            f'padding:0.7rem;text-align:center;margin-top:6px;">'
            f'<div style="font-size:1.8rem">👑</div>'
            f'<div style="font-weight:700;color:#FFCB05;font-size:0.85rem;">Champion {champion}</div>'
            f'<div style="font-size:0.7rem;color:var(--text-muted);">Final battle — their best 3!</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")
    st.markdown("""
    <div style="background:rgba(0,0,0,0.3);border:1px solid var(--poke-blue);
        border-radius:10px;padding:1rem;font-size:0.82rem;color:var(--text-muted);margin-bottom:1rem;">
        📋 <b>Rules:</b><br>
        • Pick <b>3 Pokémon</b> from your active team to carry through all battles<br>
        • Defeat all 4 Elite trainers in order — no skipping!<br>
        • Between each battle, draw a <b>bonus card</b> to help your team<br>
        • Defeat all 4 (and the Champion if one exists) to become <b>Champion</b>!
    </div>""", unsafe_allow_html=True)

    if st.button("⚔️ Challenge the Elite Four!", use_container_width=True):
        st.session_state.e4_trainer      = trainer
        st.session_state.e4_battle_idx   = 0
        st.session_state.e4_log          = ["🏆 The Elite Four challenge begins!"]
        st.session_state.e4_modifier     = None
        st.session_state.e4_pick_sel     = []
        st.session_state.e4_phase        = "pick_team"
        st.rerun()


def _phase_pick_team():
    trainer = st.session_state.e4_trainer
    roster  = _load_trainer_roster(trainer)
    selected = st.session_state.e4_pick_sel

    st.markdown("## ⚔️ Pick Your Team of 3")
    st.markdown("<small style='color:var(--text-muted)'>Choose 3 Pokémon to carry through all Elite Four battles.</small>",
                unsafe_allow_html=True)

    if len(roster) < 3:
        st.warning("You need at least 3 active Pokémon to challenge the Elite Four!")
        if st.button("← Back"):
            _reset()
            st.rerun()
        return

    cols_per_row = 3
    for row_start in range(0, len(roster), cols_per_row):
        chunk = roster[row_start:row_start + cols_per_row]
        cols  = st.columns(cols_per_row)
        for col, entry in zip(cols, chunk):
            poke   = entry["poke"]
            is_sel = poke["name"] in selected
            border = "2px solid #FFCB05" if is_sel else "2px solid var(--poke-blue)"
            bg     = "linear-gradient(145deg,#2a3a0f,#1a2a05)" if is_sel else "linear-gradient(145deg,#1e2a4a,#0f1a35)"
            sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{poke['id']}.png"
            types  = " ".join(type_badge_html(t) for t in poke["types"])
            sel_badge = "✅" if is_sel else ""
            with col:
                st.markdown(
                    f'<div style="background:{bg};border:{border};border-radius:14px;'
                    f'padding:0.7rem;text-align:center;margin-bottom:4px;">'
                    f'<img src="{sprite}" width="65" style="image-rendering:pixelated"/>'
                    f'<div style="font-size:0.75rem;font-weight:700;margin:3px 0;">{poke["name"]}</div>'
                    f'{types}'
                    f'<div style="font-size:0.62rem;color:var(--text-muted);">Lv.{poke.get("level","?")} ⚡{poke.get("speed","?")}</div>'
                    f'<div>{sel_badge}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                if is_sel:
                    if st.button("Deselect", key=f"e4_desel_{poke['id']}", use_container_width=True):
                        st.session_state.e4_pick_sel = [n for n in selected if n != poke["name"]]
                        st.rerun()
                else:
                    if st.button("Select", key=f"e4_sel_{poke['id']}", use_container_width=True,
                                 disabled=len(selected) >= 3):
                        st.session_state.e4_pick_sel = selected + [poke["name"]]
                        st.rerun()

    st.markdown(f"**Selected {len(selected)}/3:** {', '.join(selected) if selected else 'None'}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Back", use_container_width=True):
            _reset()
            st.rerun()
    with c2:
        if st.button("⚔️ Enter the Elite Four!", use_container_width=True, disabled=len(selected) < 3):
            chosen = [e for e in roster if e["poke"]["name"] in selected][:3]
            st.session_state.e4_my_team  = chosen
            st.session_state.e4_my_hp    = [e["poke"]["hp"] for e in chosen]
            st.session_state.e4_my_active = 0
            _load_next_enemy()
            st.session_state.e4_phase = "battle"
            st.rerun()


def _load_next_enemy():
    idx = st.session_state.e4_battle_idx
    champion = get_champion()
    trainer  = st.session_state.e4_trainer

    if idx < 4:
        e4 = ELITE_FOUR[idx]
        with st.spinner(f"Preparing {e4['name']}'s team..."):
            team = _load_elite_team(idx)
        st.session_state.e4_log.append(f"⚔️ {e4['emoji']} {e4['name']} ({e4['title']}) steps forward!")
    else:
        # Champion battle
        with st.spinner(f"Loading Champion {champion}'s team..."):
            team = _load_champion_team(champion)
        st.session_state.e4_log.append(f"👑 Champion {champion} stands before you!")

    st.session_state.e4_enemy_team   = team
    st.session_state.e4_enemy_hp     = [e["poke"]["hp"] for e in team]
    st.session_state.e4_enemy_active = 0


def _phase_card():
    """Between-battle bonus card pick (no skip option)."""
    idx = st.session_state.e4_battle_idx
    trainer = st.session_state.e4_trainer
    log = st.session_state.e4_log

    e4 = ELITE_FOUR[min(idx, 3)]
    next_name = ELITE_FOUR[idx]["name"] if idx < 4 else f"Champion {get_champion()}"

    st.markdown(f"### 🃏 Victory Bonus — Pick a Card!")
    st.markdown(f"<small style='color:var(--text-muted)'>Prepare for your next battle against <b>{next_name}</b>.</small>",
                unsafe_allow_html=True)

    if not st.session_state.e4_card_pool:
        st.session_state.e4_card_pool = random.sample(E4_CARDS, min(4, len(E4_CARDS)))

    cards  = st.session_state.e4_card_pool
    picked = st.session_state.e4_picked_card

    if picked:
        c = picked
        st.markdown(f"""
        <div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);
            border:2px solid {c['color']};border-radius:16px;padding:1.5rem;
            text-align:center;box-shadow:0 0 16px {c['color']}44;margin:1rem 0;">
            <div style="font-size:3rem">{c['emoji']}</div>
            <div style="font-weight:700;font-size:0.9rem;color:{c['color']};margin:6px 0;">{c['name']}</div>
            <div style="font-size:0.82rem;color:var(--text-muted);">{c['desc']}</div>
        </div>""", unsafe_allow_html=True)

        if st.button("⚔️ Continue to next battle!", use_container_width=True):
            _apply_e4_card(picked, trainer, log)
            st.session_state.e4_modifier  = picked["id"] if picked["id"] in ("attack","shield") else None
            st.session_state.e4_card_pool = []
            st.session_state.e4_picked_card = None
            _load_next_enemy()
            st.session_state.e4_phase = "battle"
            st.rerun()
        return

    cols = st.columns(4)
    for i, (col, card) in enumerate(zip(cols, cards)):
        with col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1a2a4a,#0f1835);'
                f'border:2px solid var(--poke-blue);border-radius:14px;'
                f'padding:1.2rem 0.5rem;text-align:center;min-height:120px;">'
                f'<div style="font-size:2.5rem">🂠</div>'
                f'<div style="font-size:0.7rem;color:var(--text-muted);margin-top:6px;">Card {i+1}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            if st.button(f"Flip {i+1}", key=f"e4_card_{i}", use_container_width=True):
                st.session_state.e4_picked_card = card
                st.rerun()


def _apply_e4_card(card, trainer, log):
    cid    = card["id"]
    hp_list = st.session_state.e4_my_hp
    team    = st.session_state.e4_my_team
    if cid == "heal":
        for i, entry in enumerate(team):
            hp_list[i] = entry["poke"]["hp"]
        st.session_state.e4_my_hp = hp_list
        log.append("💊 Full Heal! All Pokémon restored to full HP!")
    elif cid == "revive":
        for i, (entry, hp) in enumerate(zip(team, hp_list)):
            if hp <= 0:
                hp_list[i] = max(1, entry["poke"]["hp"] // 2)
        st.session_state.e4_my_hp = hp_list
        log.append("✨ Revive! Fainted Pokémon restored to 50% HP!")
    elif cid == "levelup":
        msgs = level_up_team(trainer, amount=1)
        log.extend(msgs)
    elif cid == "nothing":
        log.append("💨 Caught your breath...")
    elif cid in ("attack", "shield"):
        log.append(f"{'⚔️' if cid == 'attack' else '🛡️'} {card['name']} activated for next battle!")


def _phase_battle():
    trainer     = st.session_state.e4_trainer
    battle_idx  = st.session_state.e4_battle_idx
    my_team     = st.session_state.e4_my_team
    my_hps      = st.session_state.e4_my_hp
    my_active   = st.session_state.e4_my_active
    enemy_team  = st.session_state.e4_enemy_team
    enemy_hps   = st.session_state.e4_enemy_hp
    enemy_active = st.session_state.e4_enemy_active
    log         = st.session_state.e4_log
    modifier    = st.session_state.e4_modifier
    champion    = get_champion()

    is_champion_battle = (battle_idx >= 4)

    if is_champion_battle:
        e4_info = {"name": f"Champion {champion}", "emoji": "👑", "color": "#FFCB05", "title": "The Champion"}
    else:
        e4_info = ELITE_FOUR[battle_idx]

    st.markdown(f"### {e4_info['emoji']} vs {e4_info['name']} — {e4_info['title']}")
    st.markdown(f"**Battle {battle_idx + 1} of {'5' if champion and champion != trainer else '4'}**")

    if modifier:
        card = next((c for c in E4_CARDS if c["id"] == modifier), None)
        if card:
            st.markdown(
                f'<div style="background:rgba(0,0,0,0.2);border:1px solid {card["color"]};'
                f'border-radius:8px;padding:5px 12px;font-size:0.78rem;margin-bottom:6px;">'
                f'{card["emoji"]} <b>{card["name"]}</b> active this battle</div>',
                unsafe_allow_html=True
            )

    # ── Battlefield ───────────────────────────────────────────────────────────
    st.markdown("#### 🏟️ Battlefield")
    my_cols   = st.columns(3)
    opp_cols  = st.columns(3)

    st.markdown("**Your team:**")
    my_cols = st.columns(3)
    for i, (col, entry, hp) in enumerate(zip(my_cols, my_team, my_hps)):
        with col:
            is_act = (i == my_active)
            lbl    = f"{trainer}" + (" 🟢" if is_act and hp > 0 else "")
            _poke_card(entry["poke"], hp, lbl, fainted=hp <= 0)

    st.markdown(f"**{e4_info['name']}'s team:**")
    opp_cols = st.columns(3)
    for i, (col, entry, hp) in enumerate(zip(opp_cols, enemy_team, enemy_hps)):
        with col:
            is_act = (i == enemy_active)
            lbl    = e4_info["name"] + (" 🔴" if is_act and hp > 0 else "")
            _poke_card(entry["poke"], hp, lbl, color=e4_info["color"], fainted=hp <= 0)

    # ── Switch active ─────────────────────────────────────────────────────────
    alive_mine = [i for i, h in enumerate(my_hps) if h > 0]
    if len(alive_mine) > 1 and my_active in alive_mine:
        others = [i for i in alive_mine if i != my_active]
        sw_cols = st.columns(len(others))
        for col, oi in zip(sw_cols, others):
            with col:
                if st.button(f"🔄 Switch to {my_team[oi]['poke']['name']}",
                             key=f"e4_sw_{oi}", use_container_width=True):
                    st.session_state.e4_my_active = oi
                    log.append(f"🔄 Switched to {my_team[oi]['poke']['name']}!")
                    st.rerun()

    # ── Speed banner ──────────────────────────────────────────────────────────
    if my_active < len(my_team) and enemy_active < len(enemy_team) and my_hps[my_active] > 0 and enemy_hps[enemy_active] > 0:
        my_poke  = my_team[my_active]["poke"]
        opp_poke = enemy_team[enemy_active]["poke"]
        ms, os   = my_poke.get("speed",0), opp_poke.get("speed",0)
        mc       = "#4CAF50" if ms >= os else "#F44336"
        oc       = "#4CAF50" if os > ms  else "#F44336"
        st.markdown(
            f'<div style="background:rgba(0,0,0,0.2);border:1px solid #333;'
            f'border-radius:8px;padding:5px 12px;font-size:0.78rem;margin:6px 0;">'
            f'⚡ <b style="color:{mc};">{my_poke["name"]} ({ms})</b> vs '
            f'<b style="color:{oc};">{opp_poke["name"]} ({os})</b> — '
            f'<b>{"You" if ms >= os else e4_info["name"]}</b> go first!</div>',
            unsafe_allow_html=True
        )

    # ── Your move buttons ─────────────────────────────────────────────────────
    st.markdown("---")
    if my_active < len(my_team) and my_hps[my_active] > 0:
        my_poke  = my_team[my_active]["poke"]
        my_moves = my_team[my_active]["moves"]
        opp_poke = enemy_team[enemy_active]["poke"] if enemy_active < len(enemy_team) else None
        spd_lbl  = f" ⚡{my_poke.get('speed','?')}"
        st.markdown(f"**{my_poke['name']}{spd_lbl} — choose move:**")
        mcols = st.columns(2)
        for mi, move in enumerate(my_moves):
            acc = move.get("accuracy") or 100
            pwr = move.get("power") or "—"
            with mcols[mi % 2]:
                if st.button(f"{move['name']} ({move['type'].upper()}, {pwr} pwr, {acc}%)",
                             key=f"e4_my_move_{mi}", use_container_width=True):
                    if opp_poke:
                        dmg, hit = damage_calc(my_poke, opp_poke, move, my_poke.get("level", 5))
                        if modifier == "attack":
                            dmg = int(dmg * 1.5)
                            st.session_state.e4_modifier = None
                        if not hit:
                            log.append(f"➤ {my_poke['name']} used {move['name']}... missed!")
                        else:
                            enemy_hps[enemy_active] = max(0, enemy_hps[enemy_active] - dmg)
                            st.session_state.e4_enemy_hp = enemy_hps
                            eff = effectiveness_label(move.get("type","normal"), opp_poke.get("types",["normal"]))
                            log.append(f"➤ {my_poke['name']} used {move['name']}! ({dmg} dmg)" + (f" {eff}" if eff else ""))
                            if enemy_hps[enemy_active] <= 0:
                                log.append(f"💥 {opp_poke['name']} fainted!")
                                nxt = next((i for i, h in enumerate(enemy_hps) if h > 0), None)
                                if nxt is None:
                                    _on_enemy_team_defeated(trainer, battle_idx, champion, log)
                                else:
                                    st.session_state.e4_enemy_active = nxt
                                    log.append(f"🔄 {e4_info['name']} sent out {enemy_team[nxt]['poke']['name']}!")
                    st.session_state.e4_log = log[-40:]
                    st.rerun()
    else:
        # All my pokemon fainted
        if all(h <= 0 for h in my_hps):
            log.append("💀 All your Pokémon fainted! Challenge failed.")
            st.session_state.e4_log    = log[-40:]
            st.session_state.e4_phase  = "result"
            st.rerun()

    # ── Enemy move buttons ────────────────────────────────────────────────────
    if enemy_active < len(enemy_team) and enemy_hps[enemy_active] > 0:
        opp_entry  = enemy_team[enemy_active]
        opp_poke   = opp_entry["poke"]
        opp_moves  = opp_entry["moves"]
        spd_lbl    = f" ⚡{opp_poke.get('speed','?')}"
        st.markdown(f"**{opp_poke['name']}{spd_lbl} ({e4_info['name']}) — select their move:**")
        emcols = st.columns(2)
        for mi, move in enumerate(opp_moves):
            acc = move.get("accuracy") or 100
            pwr = move.get("power") or "—"
            with emcols[mi % 2]:
                if st.button(f"{move['name']} ({move['type'].upper()}, {pwr} pwr, {acc}%)",
                             key=f"e4_opp_move_{mi}", use_container_width=True):
                    target = my_team[my_active]["poke"] if my_active < len(my_team) else None
                    if target and my_hps[my_active] > 0:
                        dmg, hit = damage_calc(opp_poke, target, move, opp_poke.get("level", 60))
                        if modifier == "shield":
                            dmg = max(1, dmg // 2)
                            st.session_state.e4_modifier = None
                        if not hit:
                            log.append(f"➤ {opp_poke['name']} used {move['name']}... missed!")
                        else:
                            my_hps[my_active] = max(0, my_hps[my_active] - dmg)
                            st.session_state.e4_my_hp = my_hps
                            eff = effectiveness_label(move.get("type","normal"), target.get("types",["normal"]))
                            log.append(f"➤ {opp_poke['name']} used {move['name']} on {target['name']}! ({dmg} dmg)" + (f" {eff}" if eff else ""))
                            if my_hps[my_active] <= 0:
                                log.append(f"💀 {target['name']} fainted!")
                                nxt = next((i for i, h in enumerate(my_hps) if h > 0), None)
                                if nxt is None:
                                    log.append("💀 All your Pokémon fainted! Challenge failed.")
                                    st.session_state.e4_log    = log[-40:]
                                    st.session_state.e4_phase  = "result"
                                else:
                                    st.session_state.e4_my_active = nxt
                                    log.append(f"🔄 {my_team[nxt]['poke']['name']} is now active!")
                    st.session_state.e4_log = log[-40:]
                    st.rerun()

    # ── HP Sliders ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🎛️ Manual HP")
    sl1, sl2 = st.columns(2)
    with sl1:
        st.markdown("**Your team:**")
        for i, (entry, hp) in enumerate(zip(my_team, my_hps)):
            poke   = entry["poke"]
            new_hp = st.slider(poke["name"], 0, max(1, poke["hp"]),
                               max(0, min(hp, poke["hp"])), key=f"e4_sl_my_{i}")
            if new_hp != hp:
                my_hps[i] = new_hp
                st.session_state.e4_my_hp = my_hps
                if new_hp <= 0:
                    log.append(f"💀 {poke['name']} fainted!")
                    if all(h <= 0 for h in my_hps):
                        log.append("💀 All Pokémon fainted! Challenge failed.")
                        st.session_state.e4_phase = "result"
                st.session_state.e4_log = log[-40:]
                st.rerun()
    with sl2:
        st.markdown(f"**{e4_info['name']}'s team:**")
        for i, (entry, hp) in enumerate(zip(enemy_team, enemy_hps)):
            poke   = entry["poke"]
            new_hp = st.slider(poke["name"], 0, max(1, poke["hp"]),
                               max(0, min(hp, poke["hp"])), key=f"e4_sl_opp_{i}")
            if new_hp != hp:
                enemy_hps[i] = new_hp
                st.session_state.e4_enemy_hp = enemy_hps
                if new_hp <= 0:
                    log.append(f"💥 {poke['name']} fainted!")
                    if all(h <= 0 for h in enemy_hps):
                        _on_enemy_team_defeated(trainer, battle_idx, champion, log)
                    else:
                        nxt = next((j for j, h in enumerate(enemy_hps) if h > 0), None)
                        if nxt is not None:
                            st.session_state.e4_enemy_active = nxt
                st.session_state.e4_log = log[-40:]
                st.rerun()

    # ── Overrides ─────────────────────────────────────────────────────────────
    st.markdown("---")
    ov1, ov2 = st.columns(2)
    with ov1:
        if st.button("🏆 Won IRL!", use_container_width=True):
            log.append(f"[OVERRIDE] Defeated {e4_info['name']} IRL!")
            _on_enemy_team_defeated(trainer, battle_idx, champion, log)
            st.rerun()
    with ov2:
        if st.button("💀 Lost IRL!", use_container_width=True):
            log.append("[OVERRIDE] Team fainted in real life.")
            st.session_state.e4_phase = "result"
            st.session_state.e4_log   = log[-40:]
            st.rerun()

    # ── Log ───────────────────────────────────────────────────────────────────
    if log:
        st.markdown("#### Battle Log")
        st.markdown(f'<div class="battle-log">{chr(10).join(log[-15:])}</div>',
                    unsafe_allow_html=True)


def _on_enemy_team_defeated(trainer, battle_idx, champion, log):
    """Handle beating one Elite Four trainer or the Champion."""
    total = 5 if (champion and champion != trainer) else 4
    log.append(f"🎉 Battle {battle_idx + 1} of {total} won!")

    if battle_idx >= 4 or (battle_idx >= 3 and (not champion or champion == trainer)):
        # All done — become champion!
        set_champion(trainer)
        df = load_teams()
        row = df[df["trainer"] == trainer]
        wins = _safe_int(row.iloc[0]["wins"]) + 1 if len(row) else 1
        df = update_trainer(df, trainer, wins=wins)
        save_teams(df)
        level_up_team(trainer, amount=3)
        log.append(f"👑 {trainer} is the new Champion! +3 levels for the whole team!")
        st.session_state.e4_log   = log[-40:]
        st.session_state.e4_phase = "result"
        st.session_state.e4_winner = True
    else:
        # Move to card phase before next battle
        st.session_state.e4_battle_idx = battle_idx + 1
        st.session_state.e4_card_pool  = []
        st.session_state.e4_picked_card = None
        st.session_state.e4_log        = log[-40:]
        st.session_state.e4_phase      = "card"


def _phase_result():
    trainer = st.session_state.e4_trainer
    winner  = st.session_state.get("e4_winner", False)
    log     = st.session_state.e4_log

    if winner:
        st.markdown(f"""
        <div style="text-align:center;padding:2rem;
            background:linear-gradient(135deg,rgba(255,203,5,0.1),rgba(255,203,5,0.05));
            border:3px solid #FFCB05;border-radius:20px;margin-bottom:1rem;
            animation:pulse 1.5s infinite;">
            <div style="font-size:3rem">👑</div>
            <div style="font-family:monospace;font-size:1rem;
                color:#FFCB05;text-shadow:0 0 20px rgba(255,203,5,0.8);margin:0.5rem 0;">
                {trainer.upper()} IS CHAMPION!
            </div>
            <div style="font-size:0.85rem;color:var(--text-muted);">
                Defeated all Elite Four trainers — whole team levelled up ×3!
            </div>
        </div>""", unsafe_allow_html=True)
        st.balloons()
    else:
        st.markdown(
            f'<div class="lose-banner">💀 {trainer} was defeated by the Elite Four!</div>',
            unsafe_allow_html=True
        )
        st.markdown("<div style='font-size:0.85rem;color:var(--text-muted);text-align:center;'>Train harder and try again!</div>",
                    unsafe_allow_html=True)

    if log:
        st.markdown("#### Battle Log")
        st.markdown(f'<div class="battle-log">{chr(10).join(log[-20:])}</div>',
                    unsafe_allow_html=True)

    if st.button("🔄 Return to Gym Map", use_container_width=True):
        _reset()
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────

def render():
    init_movesets_csv()
    _init()

    phase = st.session_state.e4_phase
    if   phase == "setup":            _phase_setup()
    elif phase == "pick_team":        _phase_pick_team()
    elif phase == "card":             _phase_card()
    elif phase == "battle":           _phase_battle()
    elif phase == "result":           _phase_result()
