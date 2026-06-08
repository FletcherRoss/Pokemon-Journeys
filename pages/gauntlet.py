import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import random
import streamlit as st
from utils.pokemon_api import fetch_pokemon, fetch_moves, type_badge_html
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.story_mode_utils import use_master_ball, get_master_balls
from utils.captures_manager import add_capture, init_captures_csv, level_up_team
from utils.game_state import hp_percent, hp_bar_color, damage_calc

def _get_trainers():
    """Always read live from CSV so new players are included."""
    try:
        from utils.csv_manager import get_all_trainers
        return get_all_trainers()
    except Exception:
        return ["Addy", "Oakley", "Raelynn"]
TRAINER_COLORS = {"Addy": "#F06292", "Oakley": "#64B5F6", "Raelynn": "#FFB74D"}
TRAINER_EMOJI  = {"Addy": "🌸", "Oakley": "⚡", "Raelynn": "🔥"}

TYPE_COLORS = {
    "fire":"#F08030","water":"#6890F0","grass":"#78C850","electric":"#F8D030",
    "psychic":"#F85888","ice":"#98D8D8","dragon":"#7038F8","dark":"#705848",
    "normal":"#A8A878","fighting":"#C03028","poison":"#A040A0","ground":"#E0C068",
    "flying":"#A890F0","bug":"#A8B820","rock":"#B8A038","ghost":"#705898",
    "steel":"#B8B8D0","fairy":"#EE99AC",
}

LEGENDARY_IDS = {
    # Gen 1
    144,145,146,150,151,
    # Gen 2
    243,244,245,249,250,251,
    # Gen 3
    377,378,379,380,381,382,383,384,385,386,
    # Gen 4
    480,481,482,483,484,485,486,487,488,489,490,491,492,493,
    # Gen 5
    638,639,640,641,642,643,644,645,646,647,648,649,
    # Gen 6
    716,717,718,719,720,721,
    # Gen 7
    785,786,787,788,789,790,791,792,793,794,795,796,797,798,799,800,
    801,802,803,804,805,806,807,
    # Gen 8
    888,889,890,891,892,893,894,895,896,897,898,
    # Gen 9
    1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,
    1011,1012,1013,1014,1015,1016,1017,1018,1019,1020,
    1021,1022,1023,1024,1025,
}
ALL_NORMAL_IDS    = [i for i in range(1, 1026) if i not in LEGENDARY_IDS]
ALL_LEGENDARY_IDS = sorted(LEGENDARY_IDS)

GAUNTLET_SIZE        = 4

# ── Bonus cards ───────────────────────────────────────────────────────────────
CARDS = [
    {
        "id":    "heal",
        "emoji": "💊",
        "name":  "Full Heal",
        "desc":  "Restore all trainers to full HP before the next battle.",
        "color": "#4CAF50",
    },
    {
        "id":    "nothing",
        "emoji": "💨",
        "name":  "Nothing Happens",
        "desc":  "The winds are quiet. No bonus, no penalty.",
        "color": "#888",
    },
    {
        "id":    "skip",
        "emoji": "⏭️",
        "name":  "Skip Next Battle",
        "desc":  "Automatically win the next enemy battle and move on.",
        "color": "#64B5F6",
    },
    {
        "id":    "damage",
        "emoji": "💥",
        "name":  "25% Penalty",
        "desc":  "Each trainer takes 25% of their max HP as damage to start the next battle.",
        "color": "#E3350D",
    },
    {
        "id":    "revive",
        "emoji": "✨",
        "name":  "Revive",
        "desc":  "Any fainted trainers are revived to 50% HP.",
        "color": "#FFCB05",
    },
    {
        "id":    "double",
        "emoji": "⚡",
        "name":  "Double Damage",
        "desc":  "Your attacks deal double damage in the next battle.",
        "color": "#F8D030",
    },
    {
        "id":    "half",
        "emoji": "🛡️",
        "name":  "Half Damage",
        "desc":  "Your attacks only deal half damage in the next battle.",
        "color": "#A890F0",
    },
]
CARD_BACK_COLOR = "#1e2a4a"
CAPTURE_THRESHOLD    = 11   # roll > 10  → need 11+
LEGENDARY_THRESHOLD  = 16   # roll > 15  → need 16+


# ── Session state ─────────────────────────────────────────────────────────────

def _init():
    defaults = {
        "gt_phase":            "setup",
        "gt_trainers":         [],
        "gt_trainer_hp":       {},
        "gt_trainer_max":      {},
        "gt_trainer_poke":     {},
        "gt_trainer_moves":    {},
        "gt_enemy_pool":       [],
        "gt_enemy_idx":        0,
        "gt_enemy_hp":         [],
        "gt_legendary":        None,
        "gt_legendary_hp":     0,
        "gt_log":              [],
        "gt_defeated":         [],
        "gt_capture_queue":    [],
        "gt_capture_idx":      0,
        "gt_capture_results":  {},
        "gt_card_phase":       False,   # True when showing card pick screen
        "gt_card_pool":        [],      # 4 shuffled cards to show
        "gt_picked_card":      None,    # card dict that was chosen
        "gt_active_modifier":  None,    # active modifier id for next battle
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    for k in list(st.session_state.keys()):
        if k.startswith("gt_"):
            del st.session_state[k]


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


# ── Pokemon fetchers ──────────────────────────────────────────────────────────

def _fetch_enemy(player_count: int = 1) -> dict:
    pid  = random.choice(ALL_NORMAL_IDS)
    poke = fetch_pokemon(pid)
    poke["level"] = random.randint(30, 60)
    poke["moves"] = fetch_moves(pid)
    # Scale HP by number of players
    poke["hp"]    = poke["hp"] * max(1, player_count)
    return poke


def _fetch_legendary() -> dict:
    lid  = random.choice(ALL_LEGENDARY_IDS)
    poke = fetch_pokemon(lid)
    poke["level"] = 70
    poke["moves"] = fetch_moves(lid)
    return poke


def _load_trainer_poke(trainer: str):
    df  = load_teams()
    row = df[df["trainer"] == trainer]
    if not len(row):
        return None, []
    r = row.iloc[0]
    try:
        pid = int(float(r.get("starter_id", 0) or 0))
        lv  = int(float(r.get("level", 5) or 5))
    except (ValueError, TypeError):
        return None, []
    if pid <= 0:
        return None, []
    poke = fetch_pokemon(pid)
    poke["level"] = lv
    from utils.movesets_manager import get_moveset, init_movesets_csv
    init_movesets_csv()
    custom = get_moveset(trainer, pid)
    moves  = custom if custom else fetch_moves(pid)
    return poke, moves


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


def _enemy_card(poke, hp, max_hp, is_active=False):
    sprite = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master"
              f"/sprites/pokemon/other/official-artwork/{poke['id']}.png")
    types  = " ".join(type_badge_html(t) for t in poke["types"])
    fainted = hp <= 0
    opacity = "1" if hp > 0 else "0.3"
    border  = "2px solid #F44336" if is_active else "2px solid #555"
    if is_active:
        tag = '<div style="font-size:0.62rem;color:#F44336;font-weight:700;">⚔️ ACTIVE</div>'
    elif fainted:
        tag = '<div style="font-size:0.62rem;color:#4CAF50;">✅ DEFEATED</div>'
    else:
        tag = '<div style="font-size:0.62rem;color:#555;">⏳ WAITING</div>'
    st.markdown(
        f'<div class="pokemon-card" style="cursor:default;opacity:{opacity};border:{border};">'
        f'{tag}'
        f'<img src="{sprite}" width="72" style="image-rendering:pixelated"/>'
        f'<div style="font-size:0.75rem;font-weight:700;margin:3px 0;">{poke["name"]}</div>'
        f'{types}'
        f'<div style="font-size:0.6rem;color:var(--text-muted);">Lv.{poke.get("level","?")}</div>'
        f'</div>',
        unsafe_allow_html=True
    )
    if is_active and hp > 0:
        _hp_bar("HP", hp, max_hp)


def _trainer_card(trainer, poke, hp, max_hp):
    color  = TRAINER_COLORS.get(trainer, "#888")
    emoji  = TRAINER_EMOJI.get(trainer, "🎮")
    sprite = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master"
              f"/sprites/pokemon/{poke['id']}.png")
    types  = " ".join(type_badge_html(t) for t in poke["types"])
    fainted = hp <= 0
    opacity = "0.3" if fainted else "1"
    faint_t = '<div style="color:#F44336;font-size:0.62rem;font-weight:700;">💀 FAINTED</div>' if fainted else ""
    st.markdown(
        f'<div class="pokemon-card" style="cursor:default;opacity:{opacity};border-color:{color};">'
        f'<div style="font-size:0.62rem;font-weight:700;color:{color};">{emoji} {trainer}</div>'
        f'<img src="{sprite}" width="70" style="image-rendering:pixelated"/>'
        f'<div style="font-size:0.75rem;font-weight:700;margin:3px 0;">{poke["name"]}</div>'
        f'{types}{faint_t}</div>',
        unsafe_allow_html=True
    )
    if not fainted:
        _hp_bar("HP", hp, max_hp)


def _capture_ui(poke, threshold, cap_key, trainer=None):
    """
    Show capture UI. Returns 'caught'|'escaped'|'skipped'|None.
    Manages its own roll state via cap_key.
    """
    is_leg  = poke["id"] in LEGENDARY_IDS
    sprite  = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master"
               f"/sprites/pokemon/other/official-artwork/{poke['id']}.png")
    types   = " ".join(type_badge_html(t) for t in poke["types"])
    bc      = "#7038F8" if is_leg else "#FFCB05"
    glow    = "rgba(112,56,248,0.5)" if is_leg else "rgba(255,203,5,0.35)"
    leg_tag = '<div style="font-family:\'Press Start 2P\',monospace;font-size:0.6rem;color:#7038F8;margin-bottom:6px;">✨ LEGENDARY ✨</div>' if is_leg else ""

    st.markdown(
        f'<div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);'
        f'border:2px solid {bc};border-radius:16px;padding:1.2rem;'
        f'text-align:center;box-shadow:0 0 18px {glow};margin-bottom:1rem;">'
        f'{leg_tag}'
        f'<img src="{sprite}" width="110" style="image-rendering:pixelated;margin:4px 0;"/>'
        f'<div style="font-weight:700;font-size:1rem;">{poke["name"]}</div>'
        f'<div style="margin:4px 0;">{types}</div>'
        f'<div style="font-size:0.8rem;color:var(--text-muted);margin-top:6px;">'
        f'Roll d20 — need <b style="color:{bc}">{threshold}+</b> to catch</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    roll_res = st.session_state.get(f"{cap_key}_result")
    roll_val = st.session_state.get(f"{cap_key}_roll")

    if roll_res is None:
        mb_count = get_master_balls(trainer) if trainer else 0
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button("🎲 Roll d20!", key=f"{cap_key}_btn", use_container_width=True):
                roll = random.randint(1, 20)
                st.session_state[f"{cap_key}_roll"]   = roll
                st.session_state[f"{cap_key}_result"] = "caught" if roll >= threshold else "escaped"
                st.rerun()
        with c2:
            if st.button("✅ Caught IRL!", key=f"{cap_key}_irl", use_container_width=True):
                st.session_state[f"{cap_key}_roll"]   = 20
                st.session_state[f"{cap_key}_result"] = "caught"
                st.rerun()
        with c3:
            mb_label    = f"⚪ Master Ball ({mb_count})" if mb_count > 0 else "⚪ No Master Balls"
            mb_disabled = mb_count <= 0
            if st.button(mb_label, key=f"{cap_key}_mb", use_container_width=True,
                         disabled=mb_disabled, help="Auto-catch! Uses 1 Master Ball."):
                if trainer:
                    use_master_ball(trainer)
                st.session_state[f"{cap_key}_roll"]   = 20
                st.session_state[f"{cap_key}_result"] = "caught"
                st.rerun()
        with c4:
            if st.button("⏭️ Skip", key=f"{cap_key}_skip", use_container_width=True):
                st.session_state[f"{cap_key}_result"] = "skipped"
                st.rerun()
        return None

    # Show result
    if roll_res == "caught":
        roll_line = f"Rolled <b style='color:#FFCB05'>{roll_val}</b> — success!" if roll_val and roll_val < 20 else "Caught in real life!"
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a3a1a,#0f2a0f);'
            f'border:2px solid #4CAF50;border-radius:12px;padding:1rem;text-align:center;">'
            f'<div style="font-size:1.5rem">🎉</div>'
            f'<div style="font-family:\'Press Start 2P\',monospace;font-size:0.6rem;color:#4CAF50;">'
            f'{poke["name"]} was caught!</div>'
            f'<div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px;">{roll_line}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    elif roll_res == "escaped":
        st.markdown(
            f'<div style="background:rgba(227,53,13,0.1);border:2px solid #E3350D;'
            f'border-radius:12px;padding:1rem;text-align:center;">'
            f'<div style="font-size:1.5rem">💨</div>'
            f'<div style="font-size:0.85rem;color:#E3350D;font-weight:700;">{poke["name"]} broke free!</div>'
            f'<div style="font-size:0.8rem;color:var(--text-muted);">Rolled <b style="color:#FFCB05">{roll_val}</b> — needed {threshold}+</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    elif roll_res == "skipped":
        st.info("Capture skipped.")

    return roll_res


def _enemy_move_table(enemy):
    moves = enemy.get("moves", [])
    if not moves:
        return
    rows = ""
    for m in moves:
        tc    = TYPE_COLORS.get(m.get("type","normal"), "#888")
        pwr   = m.get("power") or 0
        pwr_c = "#F44336" if pwr>=80 else "#FFC107" if pwr>=50 else "#aaa"
        acc   = m.get("accuracy") or 100
        acc_c = "#4CAF50" if acc>=90 else "#FFC107" if acc>=70 else "#F44336"
        rows += (
            f'<tr>'
            f'<td style="padding:2px 8px;font-size:0.73rem;font-weight:600;">{m["name"]}</td>'
            f'<td><span class="type-badge" style="background:{tc};font-size:0.55rem;">{m.get("type","?")}</span></td>'
            f'<td style="font-size:0.73rem;color:{pwr_c};padding:2px 5px;">{pwr or "—"}</td>'
            f'<td style="font-size:0.73rem;color:{acc_c};padding:2px 5px;">{acc}%</td>'
            f'</tr>'
        )
    st.markdown(
        f'<div style="margin:0.5rem 0 0.8rem 0;">'
        f'<div style="font-size:0.62rem;color:var(--text-muted);text-transform:uppercase;'
        f'letter-spacing:1px;margin-bottom:3px;">{enemy["name"]}\'s moves</div>'
        f'<table style="width:100%;border-collapse:collapse;background:rgba(0,0,0,0.2);'
        f'border:1px solid var(--poke-blue);border-radius:8px;">'
        f'<thead><tr style="color:var(--text-muted);font-size:0.62rem;">'
        f'<th style="padding:3px 8px;text-align:left;">Move</th>'
        f'<th>Type</th><th>Pwr</th><th>Acc</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>',
        unsafe_allow_html=True
    )


def _record_result(trainers, win):
    df = load_teams()
    for t in trainers:
        row = df[df["trainer"] == t]
        if len(row):
            wins   = _safe_int(row.iloc[0]["wins"])   + (1 if win else 0)
            losses = _safe_int(row.iloc[0]["losses"]) + (0 if win else 1)
            df = update_trainer(df, t, wins=wins, losses=losses)
    save_teams(df)


# ── Phase: setup ──────────────────────────────────────────────────────────────

def _phase_setup():
    st.markdown("### ⚔️ Enter the Gauntlet")
    st.markdown("""
    <div style="background:rgba(0,0,0,0.3);border:1px solid var(--poke-blue);
        border-radius:10px;padding:1rem;font-size:0.82rem;color:var(--text-muted);margin-bottom:1.2rem;">
        🏟️ <b>Rules:</b><br>
        • 1–3 trainers team up to face <b>4 random wild Pokémon</b><br>
        • Defeat all 4 → face a <b>Legendary Pokémon</b><br>
        • After the run: capture defeated Pokémon (roll <b>11+</b>) or the Legendary (roll <b>16+</b>)<br>
        • If the whole team faints → gauntlet fails (can still capture defeated enemies)<br>
        • Win: all trainers level up <b>×2</b>
    </div>""", unsafe_allow_html=True)

    selected = st.multiselect("Choose trainers (1–3):", _get_trainers(),
                              default=[_get_trainers()[0]], key="gt_trainer_sel",
                              max_selections=3)
    if not selected:
        st.warning("Select at least 1 trainer.")
        return

    # Preview
    cols = st.columns(len(selected))
    for col, t in zip(cols, selected):
        color = TRAINER_COLORS.get(t, "#888")
        emoji = TRAINER_EMOJI.get(t, "🎮")
        with col:
            st.markdown(
                f'<div style="text-align:center;border:2px solid {color};'
                f'border-radius:12px;padding:0.8rem;">'
                f'<div style="font-size:2rem">{emoji}</div>'
                f'<div style="font-weight:700;color:{color};">{t}</div></div>',
                unsafe_allow_html=True
            )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("⚔️ Enter the Gauntlet!", use_container_width=True):
        with st.spinner("Rolling enemies & loading teams..."):
            pokes_d, moves_d, hp_d, max_d = {}, {}, {}, {}
            missing = []
            for t in selected:
                poke, moves = _load_trainer_poke(t)
                if not poke:
                    missing.append(t)
                    continue
                pokes_d[t]  = poke
                moves_d[t]  = moves
                hp_d[t]     = poke["hp"]
                max_d[t]    = poke["hp"]
            if missing:
                st.error(f"{', '.join(missing)} need a starter (go to Home first).")
                return

            pool = [_fetch_enemy(len(selected)) for _ in range(GAUNTLET_SIZE)]

        st.session_state.gt_trainers      = selected
        st.session_state.gt_trainer_poke  = pokes_d
        st.session_state.gt_trainer_moves = moves_d
        st.session_state.gt_trainer_hp    = hp_d
        st.session_state.gt_trainer_max   = max_d
        st.session_state.gt_enemy_pool    = pool
        st.session_state.gt_enemy_hp      = [p["hp"] for p in pool]
        st.session_state.gt_enemy_idx     = 0
        st.session_state.gt_defeated      = []
        st.session_state.gt_log           = [
            "⚔️ The Gauntlet begins!",
            f"Enemy 1: A wild {pool[0]['name']} (Lv.{pool[0]['level']}) appears!",
        ]
        st.session_state.gt_phase = "battle"
        st.rerun()


# ── Phase: card pick ─────────────────────────────────────────────────────────

def _phase_cards():
    """Show 4 face-down cards; player picks one for a bonus/malus next battle."""
    trainers  = st.session_state.gt_trainers
    enemy_idx = st.session_state.gt_enemy_idx   # next enemy index
    pool      = st.session_state.gt_enemy_pool
    log       = st.session_state.gt_log

    st.markdown("### 🃏 Pick a Bonus Card!")
    st.markdown(
        f"<small style='color:var(--text-muted)'>Choose one card — "
        f"it will affect your battle against "
        f"<b>{pool[enemy_idx]['name']}</b> next.</small>",
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)

    # Build card pool on first render
    if not st.session_state.gt_card_pool:
        pool_sample = random.sample(CARDS, 4)
        st.session_state.gt_card_pool = pool_sample

    cards  = st.session_state.gt_card_pool
    picked = st.session_state.gt_picked_card

    if picked:
        # Show result
        c = picked
        st.markdown(f"""
        <div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);
            border:2px solid {c['color']};border-radius:16px;padding:1.5rem;
            text-align:center;box-shadow:0 0 20px {c['color']}44;margin:1rem 0;">
            <div style="font-size:3rem">{c['emoji']}</div>
            <div style="font-family:monospace;font-size:0.7rem;
                color:{c['color']};margin:0.5rem 0;">{c['name'].upper()}</div>
            <div style="font-size:0.85rem;color:var(--text-muted);">{c['desc']}</div>
        </div>""", unsafe_allow_html=True)

        if st.button("⚔️ Continue to next battle!", use_container_width=True):
            _apply_card(picked, trainers)
            st.session_state.gt_active_modifier = picked["id"]
            st.session_state.gt_card_phase  = False
            st.session_state.gt_card_pool   = []
            st.session_state.gt_picked_card = None
            st.session_state.gt_phase       = "battle"   # ← must set explicitly
            log.append(f"🃏 Card drawn: {picked['emoji']} {picked['name']} — {picked['desc']}")
            st.session_state.gt_log = log[-40:]
            st.rerun()
        return

    # Show 4 face-down cards
    cols = st.columns(4)
    for i, (col, card) in enumerate(zip(cols, cards)):
        with col:
            st.markdown(f"""
            <div style="background:linear-gradient(145deg,#1a2a4a,#0f1835);
                border:2px solid var(--poke-blue);border-radius:14px;
                padding:1.5rem 0.5rem;text-align:center;cursor:pointer;
                min-height:130px;display:flex;align-items:center;justify-content:center;">
                <div>
                    <div style="font-size:2.5rem">🂠</div>
                    <div style="font-size:0.7rem;color:var(--text-muted);margin-top:6px;">Card {i+1}</div>
                </div>
            </div>""", unsafe_allow_html=True)
            if st.button(f"Flip Card {i+1}", key=f"gt_card_{i}", use_container_width=True):
                st.session_state.gt_picked_card = card
                st.rerun()


def _apply_card(card, trainers):
    """Apply immediate card effects to session state."""
    cid = card["id"]
    hp_map  = st.session_state.gt_trainer_hp
    max_map = st.session_state.gt_trainer_max
    pokes   = st.session_state.gt_trainer_poke

    if cid == "heal":
        for t in trainers:
            hp_map[t] = max_map[t]
        st.session_state.gt_trainer_hp = hp_map

    elif cid == "revive":
        for t in trainers:
            if hp_map[t] <= 0:
                hp_map[t] = max(1, max_map[t] // 2)
        st.session_state.gt_trainer_hp = hp_map

    elif cid == "damage":
        for t in trainers:
            penalty = max(1, max_map[t] // 4)
            hp_map[t] = max(1, hp_map[t] - penalty)
        st.session_state.gt_trainer_hp = hp_map

    # skip / double / half / nothing are applied during battle via gt_active_modifier


# ── Phase: battle ─────────────────────────────────────────────────────────────

def _phase_battle():
    trainers   = st.session_state.gt_trainers
    pokes      = st.session_state.gt_trainer_poke
    moves_map  = st.session_state.gt_trainer_moves
    hp_map     = st.session_state.gt_trainer_hp
    max_map    = st.session_state.gt_trainer_max
    pool       = st.session_state.gt_enemy_pool
    enemy_hps  = st.session_state.gt_enemy_hp
    enemy_idx  = st.session_state.gt_enemy_idx
    log        = st.session_state.gt_log
    enemy      = pool[enemy_idx]

    st.markdown(f"### ⚔️ Gauntlet — Round {enemy_idx+1} of {GAUNTLET_SIZE}")

    # Show active modifier banner
    modifier = st.session_state.get("gt_active_modifier")
    if modifier:
        card = next((c for c in CARDS if c["id"] == modifier), None)
        if card:
            st.markdown(
                f'<div style="background:rgba(0,0,0,0.25);border:1px solid {card["color"]};'
                f'border-radius:8px;padding:6px 12px;font-size:0.8rem;margin-bottom:6px;">'
                f'Active bonus: {card["emoji"]} <b>{card["name"]}</b> — {card["desc"]}</div>',
                unsafe_allow_html=True
            )

    # Handle "skip" modifier — auto-win this battle
    if modifier == "skip":
        st.info(f"⏭️ **Battle Skipped!** Your card skips this {enemy['name']} battle automatically.")
        if st.button("▶️ Continue to next round", use_container_width=True):
            enemy_hps[enemy_idx] = 0
            st.session_state.gt_enemy_hp        = enemy_hps
            st.session_state.gt_active_modifier = None
            log.append(f"⏭️ [SKIP CARD] {enemy['name']} battle skipped!")
            if enemy_idx not in st.session_state.gt_defeated:
                st.session_state.gt_defeated.append(enemy_idx)
            _on_enemy_faint(enemy_idx, enemy, pool, enemy_hps, log, trainers)
            st.session_state.gt_log = log[-40:]
            st.rerun()
        return

    # ── 4-enemy progress strip ────────────────────────────────────────────────
    prog_cols = st.columns(GAUNTLET_SIZE)
    for i, (col, ep) in enumerate(zip(prog_cols, pool)):
        with col:
            _enemy_card(ep, enemy_hps[i], ep["hp"], is_active=(i == enemy_idx))

    st.markdown("---")

    # ── Team row ──────────────────────────────────────────────────────────────
    st.markdown("#### 👥 Your Team")
    t_cols = st.columns(max(len(trainers), 1))
    for col, t in zip(t_cols, trainers):
        with col:
            _trainer_card(t, pokes[t], hp_map[t], max_map[t])

    # ── Enemy move table ──────────────────────────────────────────────────────
    _enemy_move_table(enemy)

    # ── Attack buttons ────────────────────────────────────────────────────────
    st.markdown("---")
    alive = [t for t in trainers if hp_map[t] > 0]

    if not alive:
        log.append("💀 All trainers fainted! Gauntlet failed.")
        st.session_state.gt_log   = log[-40:]
        st.session_state.gt_phase = "result"
        st.rerun()
        return

    for trainer in alive:
        poke   = pokes[trainer]
        moves  = moves_map[trainer]
        color  = TRAINER_COLORS.get(trainer, "#888")
        emoji  = TRAINER_EMOJI.get(trainer, "🎮")
        st.markdown(
            f'<div style="border-left:4px solid {color};padding-left:10px;margin:4px 0;">'
            f'<b>{emoji} {trainer} — {poke["name"]}</b></div>',
            unsafe_allow_html=True
        )
        mcols = st.columns(2)
        for mi, move in enumerate(moves):
            acc = move.get("accuracy") or 100
            pwr = move.get("power") or "—"
            with mcols[mi % 2]:
                if st.button(
                    f"{move['name']} ({move['type'].upper()}, {pwr} pwr, {acc}%)",
                    key=f"gt_atk_{trainer}_{mi}", use_container_width=True
                ):
                    _do_attack(trainer, poke, move, enemy, enemy_idx,
                               enemy_hps, hp_map, alive, pool, log, trainers)
                    st.rerun()

    # ── HP sliders ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🎛️ Manual HP")
    sl1, sl2 = st.columns(2)
    with sl1:
        st.markdown("**Enemy:**")
        new_e = st.slider(
            enemy["name"], 0, max(1, enemy["hp"]),
            max(0, min(enemy_hps[enemy_idx], enemy["hp"])),
            key=f"gt_sl_e_{enemy_idx}"
        )
        if new_e != enemy_hps[enemy_idx]:
            enemy_hps[enemy_idx] = new_e
            st.session_state.gt_enemy_hp = enemy_hps
            if new_e <= 0:
                _on_enemy_faint(enemy_idx, enemy, pool, enemy_hps, log, trainers)
            st.rerun()
    with sl2:
        st.markdown("**Team:**")
        for t in trainers:
            p      = pokes[t]
            new_hp = st.slider(
                f"{t} — {p['name']}", 0, max(1, p["hp"]),
                max(0, min(hp_map[t], p["hp"])), key=f"gt_sl_t_{t}"
            )
            if new_hp != hp_map[t]:
                hp_map[t] = new_hp
                st.session_state.gt_trainer_hp = hp_map
                if new_hp <= 0:
                    log.append(f"💀 {t}'s {p['name']} fainted!")
                if all(hp_map[x] <= 0 for x in trainers):
                    log.append("💀 All trainers fainted! Gauntlet failed.")
                    st.session_state.gt_phase = "result"
                st.session_state.gt_log = log[-40:]
                st.rerun()

    # ── Overrides ─────────────────────────────────────────────────────────────
    st.markdown("---")
    ov1, ov2 = st.columns(2)
    with ov1:
        if st.button("🏆 Defeated enemy IRL!", use_container_width=True):
            enemy_hps[enemy_idx] = 0
            st.session_state.gt_enemy_hp = enemy_hps
            log.append(f"[OVERRIDE] {enemy['name']} defeated IRL!")
            _on_enemy_faint(enemy_idx, enemy, pool, enemy_hps, log, trainers)
            st.rerun()
    with ov2:
        if st.button("💀 Team fainted IRL — end gauntlet", use_container_width=True):
            log.append("[OVERRIDE] Team fainted in real life.")
            st.session_state.gt_phase = "result"
            st.session_state.gt_log   = log[-40:]
            st.rerun()

    # ── Log ───────────────────────────────────────────────────────────────────
    if log:
        st.markdown("#### Battle Log")
        st.markdown(f'<div class="battle-log">{chr(10).join(log[-15:])}</div>',
                    unsafe_allow_html=True)


def _do_attack(trainer, poke, move, enemy, enemy_idx,
               enemy_hps, hp_map, alive, pool, log, trainers):
    dmg, hit = damage_calc(poke, enemy, move, poke.get("level", 5))
    mod = st.session_state.get("gt_active_modifier")
    if hit:
        if mod == "double":
            dmg = dmg * 2
        elif mod == "half":
            dmg = max(1, dmg // 2)
    if not hit:
        log.append(f"➤ {poke['name']} used {move['name']}... missed!")
    else:
        enemy_hps[enemy_idx] = max(0, enemy_hps[enemy_idx] - dmg)
        mod_tag = " ⚡×2" if mod == "double" else " 🛡️×½" if mod == "half" else ""
        log.append(f"➤ {poke['name']} used {move['name']}! ({dmg} dmg{mod_tag})")
    st.session_state.gt_enemy_hp = enemy_hps

    if enemy_hps[enemy_idx] > 0:
        # Counter-attack random alive trainer
        emoves = enemy.get("moves") or [{"name":"Tackle","power":40,"type":"normal","accuracy":100,"pp":35}]
        target   = random.choice(alive)
        opp_move = random.choice(emoves)
        opp_dmg, opp_hit = damage_calc(enemy, st.session_state.gt_trainer_poke[target], opp_move, enemy.get("level",40))
        if not opp_hit:
            log.append(f"➤ {enemy['name']} used {opp_move['name']}... missed!")
        else:
            hp_map[target] = max(0, hp_map[target] - opp_dmg)
            log.append(f"➤ {enemy['name']} hit {target}'s {st.session_state.gt_trainer_poke[target]['name']}! ({opp_dmg} dmg)")
            if hp_map[target] <= 0:
                log.append(f"💀 {target}'s {st.session_state.gt_trainer_poke[target]['name']} fainted!")
        st.session_state.gt_trainer_hp = hp_map

    if enemy_hps[enemy_idx] <= 0:
        st.session_state.gt_active_modifier = None
        _on_enemy_faint(enemy_idx, enemy, pool, enemy_hps, log, trainers)

    if all(hp_map[t] <= 0 for t in trainers):
        log.append("💀 All trainers fainted! Gauntlet failed.")
        st.session_state.gt_phase = "result"

    st.session_state.gt_log = log[-40:]


def _on_enemy_faint(enemy_idx, enemy, pool, enemy_hps, log, trainers):
    if enemy_idx not in st.session_state.gt_defeated:
        st.session_state.gt_defeated.append(enemy_idx)
    log.append(f"💥 {enemy['name']} was defeated!")
    next_idx = enemy_idx + 1
    if next_idx >= GAUNTLET_SIZE:
        log.append("🏆 All 4 enemies defeated! Summoning a Legendary...")
        with st.spinner("Summoning the Legendary..."):
            legendary = _fetch_legendary()
        st.session_state.gt_legendary    = legendary
        st.session_state.gt_legendary_hp = legendary["hp"]
        st.session_state.gt_phase        = "legendary"
        for t in trainers:
            msgs = level_up_team(t, amount=2)
            log.extend(msgs)
        _record_result(trainers, win=True)
    else:
        st.session_state.gt_enemy_idx = next_idx
        log.append(f"💥 {enemy['name']} defeated! Pick a bonus card before the next battle.")
        # Trigger card pick phase
        st.session_state.gt_card_phase  = True
        st.session_state.gt_card_pool   = []
        st.session_state.gt_picked_card = None
        st.session_state.gt_phase       = "cards"
    st.session_state.gt_log = log[-40:]


# ── Phase: legendary ─────────────────────────────────────────────────────────

def _phase_legendary():
    legendary = st.session_state.gt_legendary
    leg_hp    = st.session_state.gt_legendary_hp
    trainers  = st.session_state.gt_trainers
    pokes     = st.session_state.gt_trainer_poke
    hp_map    = st.session_state.gt_trainer_hp
    max_map   = st.session_state.gt_trainer_max
    moves_map = st.session_state.gt_trainer_moves
    log       = st.session_state.gt_log
    alive     = [t for t in trainers if hp_map[t] > 0]

    sprite = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master"
              f"/sprites/pokemon/other/official-artwork/{legendary['id']}.png")
    types  = " ".join(type_badge_html(t) for t in legendary["types"])

    st.markdown(f"""
    <div style="text-align:center;padding:1.2rem;
        background:linear-gradient(135deg,rgba(112,56,248,0.15),rgba(112,56,248,0.05));
        border:2px solid #7038F8;border-radius:16px;margin-bottom:1rem;">
        <div style="font-family:monospace;font-size:0.7rem;color:#7038F8;margin-bottom:8px;">
            ✨ LEGENDARY POKÉMON APPEARS! ✨
        </div>
        <img src="{sprite}" width="150" style="image-rendering:pixelated;
            filter:drop-shadow(0 0 18px rgba(112,56,248,0.8));"/>
        <div style="font-size:1.1rem;font-weight:700;margin:6px 0;">{legendary['name']}</div>
        <div>{types}</div>
        <div style="font-size:0.72rem;color:var(--text-muted);margin-top:4px;">
            Lv.{legendary.get('level',70)} ❤️{legendary['hp']} ⚔️{legendary['attack']} ⚡{legendary['speed']}
        </div>
    </div>""", unsafe_allow_html=True)

    _hp_bar(f"{legendary['name']} HP", leg_hp, legendary["hp"])

    # Team
    st.markdown("#### 👥 Your Team")
    t_cols = st.columns(max(len(trainers), 1))
    for col, t in zip(t_cols, trainers):
        with col:
            _trainer_card(t, pokes[t], hp_map[t], max_map[t])

    # Legendary fainted → go capture
    if leg_hp <= 0:
        st.markdown('<div class="win-banner">🏆 LEGENDARY BROUGHT DOWN! 🏆</div>',
                    unsafe_allow_html=True)
        if st.button("⚾ Attempt capture!", use_container_width=True):
            _enter_capture(include_legendary=True)
            st.rerun()
        return

    # All trainers fainted
    if not alive:
        st.markdown('<div class="lose-banner">💀 Team fainted against the Legendary!</div>',
                    unsafe_allow_html=True)
        if st.button("⚾ Capture the enemies you defeated", use_container_width=True):
            _enter_capture(include_legendary=False)
            st.rerun()
        return

    # Move table
    _enemy_move_table(legendary)

    # Attack buttons
    st.markdown("---")
    for trainer in alive:
        poke  = pokes[trainer]
        moves = moves_map[trainer]
        color = TRAINER_COLORS.get(trainer, "#888")
        emoji = TRAINER_EMOJI.get(trainer, "🎮")
        st.markdown(
            f'<div style="border-left:4px solid {color};padding-left:10px;margin:4px 0;">'
            f'<b>{emoji} {trainer} — {poke["name"]}</b></div>',
            unsafe_allow_html=True
        )
        mcols = st.columns(2)
        for mi, move in enumerate(moves):
            acc = move.get("accuracy") or 100
            pwr = move.get("power") or "—"
            with mcols[mi % 2]:
                if st.button(
                    f"{move['name']} ({pwr} pwr, {acc}%)",
                    key=f"gt_leg_{trainer}_{mi}", use_container_width=True
                ):
                    dmg, hit = damage_calc(poke, legendary, move, poke.get("level",5))
                    if not hit:
                        log.append(f"➤ {poke['name']} used {move['name']}... missed!")
                    else:
                        st.session_state.gt_legendary_hp = max(0, leg_hp - dmg)
                        log.append(f"➤ {poke['name']} used {move['name']}! ({dmg} dmg)")
                    # Counter
                    leg_moves = legendary.get("moves") or []
                    if st.session_state.gt_legendary_hp > 0 and leg_moves:
                        target   = random.choice(alive)
                        opp_move = random.choice(leg_moves)
                        opp_dmg, opp_hit = damage_calc(legendary, pokes[target], opp_move, 70)
                        if not opp_hit:
                            log.append(f"➤ {legendary['name']} used {opp_move['name']}... missed!")
                        else:
                            hp_map[target] = max(0, hp_map[target] - opp_dmg)
                            log.append(f"➤ {legendary['name']} hit {target}! ({opp_dmg} dmg)")
                            if hp_map[target] <= 0:
                                log.append(f"💀 {target}'s {pokes[target]['name']} fainted!")
                        st.session_state.gt_trainer_hp = hp_map
                    st.session_state.gt_log = log[-40:]
                    st.rerun()

    # HP slider
    st.markdown("---")
    new_lhp = st.slider(
        f"{legendary['name']} HP", 0, max(1, legendary["hp"]),
        max(0, leg_hp), key="gt_sl_leg"
    )
    if new_lhp != leg_hp:
        st.session_state.gt_legendary_hp = new_lhp
        if new_lhp <= 0:
            log.append(f"💥 {legendary['name']} brought down!")
            st.session_state.gt_log = log[-40:]
        st.rerun()

    # Overrides
    ov1, ov2 = st.columns(2)
    with ov1:
        if st.button("🏆 Defeated Legendary IRL!", use_container_width=True):
            st.session_state.gt_legendary_hp = 0
            log.append("[OVERRIDE] Legendary defeated IRL!")
            st.session_state.gt_log = log[-40:]
            st.rerun()
    with ov2:
        if st.button("💀 Fainted against Legendary", use_container_width=True):
            log.append("[OVERRIDE] Team fainted. Moving to captures.")
            st.session_state.gt_log = log[-40:]
            _enter_capture(include_legendary=False)
            st.rerun()

    if log:
        st.markdown("#### Battle Log")
        st.markdown(f'<div class="battle-log">{chr(10).join(log[-12:])}</div>',
                    unsafe_allow_html=True)


def _enter_capture(include_legendary: bool):
    """Build the capture queue and available pool, then go to selection screen."""
    available = []
    if include_legendary and st.session_state.gt_legendary:
        leg = st.session_state.gt_legendary
        available.append({"poke": leg, "threshold": LEGENDARY_THRESHOLD, "is_leg": True})
    for i in st.session_state.gt_defeated:
        ep = st.session_state.gt_enemy_pool[i]
        available.append({"poke": ep, "threshold": CAPTURE_THRESHOLD, "is_leg": False})

    # Each trainer gets exactly one attempt — store per-trainer roll state
    trainers = st.session_state.gt_trainers
    st.session_state.gt_capture_available = available   # pool to choose from
    st.session_state.gt_capture_queue     = []          # chosen order (one per trainer)
    st.session_state.gt_capture_results   = {}
    st.session_state.gt_capture_trainer_idx = 0         # which trainer is currently picking/rolling
    # Per-trainer selected pokemon name
    st.session_state.gt_capture_selections = {t: None for t in trainers}
    st.session_state.gt_phase = "capture"


# ── Phase: capture ────────────────────────────────────────────────────────────

def _phase_capture():
    trainers   = st.session_state.gt_trainers
    available  = st.session_state.get("gt_capture_available", [])
    results    = st.session_state.gt_capture_results
    trainer_idx = st.session_state.get("gt_capture_trainer_idx", 0)
    selections  = st.session_state.get("gt_capture_selections", {t: None for t in trainers})

    if not available:
        st.info("No Pokémon available to capture.")
        if st.button("🏁 Finish"):
            st.session_state.gt_phase = "result"
            st.rerun()
        return

    # All trainers done
    if trainer_idx >= len(trainers):
        caught = [n for n, r in results.items() if r == "caught"]
        st.markdown("### 🎉 Capture Summary")
        if caught:
            st.success(f"Caught: **{', '.join(caught)}**!")
            for entry in available:
                poke = entry["poke"]
                if results.get(poke["name"]) == "caught":
                    for t in trainers:
                        add_capture(t, poke, poke.get("level", 5))
        else:
            st.info("No Pokémon were caught this run.")
        if st.button("🏁 Finish Gauntlet", use_container_width=True):
            st.session_state.gt_phase = "result"
            st.rerun()
        return

    trainer   = trainers[trainer_idx]
    color     = TRAINER_COLORS.get(trainer, "#888")
    emoji     = TRAINER_EMOJI.get(trainer, "🎮")
    cap_key   = f"gt_cap_{trainer}"
    chosen_name = selections.get(trainer)

    st.markdown(f"### ⚾ {emoji} {trainer}'s Capture Attempt ({trainer_idx+1}/{len(trainers)})")
    st.markdown(
        f"<small style='color:var(--text-muted)'>Each trainer gets <b>one roll</b>. "
        f"Choose a Pokémon to attempt to capture.</small>",
        unsafe_allow_html=True
    )

    # ── Step 1: Choose which pokemon to attempt ────────────────────────────────
    if not chosen_name:
        st.markdown("#### Which Pokémon do you want to try to catch?")
        cols_per_row = 3
        for row_start in range(0, len(available), cols_per_row):
            chunk = available[row_start:row_start + cols_per_row]
            cols  = st.columns(cols_per_row)
            for col, entry in zip(cols, chunk):
                poke   = entry["poke"]
                is_leg = entry.get("is_leg", False)
                thresh = entry["threshold"]
                sprite = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master"
                          f"/sprites/pokemon/other/official-artwork/{poke['id']}.png")
                types_html = " ".join(type_badge_html(t) for t in poke["types"])
                border = "2px solid #7038F8" if is_leg else "2px solid var(--poke-blue)"
                leg_tag = '<div style="font-size:0.6rem;color:#7038F8;font-weight:700;">✨ LEGENDARY</div>' if is_leg else ""
                already_caught = results.get(poke["name"]) == "caught"
                with col:
                    caught_tag = '<div style="font-size:0.65rem;color:#4CAF50;">✅ Already caught!</div>' if already_caught else ""
                    st.markdown(
                        '<div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);'
                        f'border:{border};border-radius:14px;padding:0.8rem;text-align:center;">'
                        f'{leg_tag}'
                        f'<img src="{sprite}" width="80" style="image-rendering:pixelated"/>'
                        f'<div style="font-size:0.78rem;font-weight:700;margin:3px 0;">{poke["name"]}</div>'
                        f'{types_html}'
                        f'<div style="font-size:0.62rem;color:var(--text-muted);margin-top:3px;">'
                        f'Need {thresh}+ to catch</div>'
                        + caught_tag +
                        '</div>',
                        unsafe_allow_html=True
                    )
                    if st.button(f"Choose {poke['name']}", key=f"gt_choose_{trainer}_{poke['id']}",
                                 use_container_width=True):
                        selections[trainer] = poke["name"]
                        st.session_state.gt_capture_selections = selections
                        st.rerun()

        st.markdown("---")
        if st.button("⏭️ Skip my turn", key=f"gt_skip_turn_{trainer}", use_container_width=True):
            results[trainer + "_turn"] = "skipped"
            st.session_state.gt_capture_results    = results
            st.session_state.gt_capture_trainer_idx = trainer_idx + 1
            st.rerun()
        return

    # ── Step 2: Roll for chosen pokemon ───────────────────────────────────────
    entry = next((e for e in available if e["poke"]["name"] == chosen_name), None)
    if not entry:
        # Invalid selection — reset
        selections[trainer] = None
        st.session_state.gt_capture_selections = selections
        st.rerun()
        return

    poke      = entry["poke"]
    threshold = entry["threshold"]
    roll_res  = st.session_state.get(f"{cap_key}_result")
    roll_val  = st.session_state.get(f"{cap_key}_roll")

    sprite = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master"
              f"/sprites/pokemon/other/official-artwork/{poke['id']}.png")
    types_html = " ".join(type_badge_html(t) for t in poke["types"])
    is_leg  = entry.get("is_leg", False)
    bc      = "#7038F8" if is_leg else "#FFCB05"
    leg_tag = '<div style="font-family:monospace;font-size:0.6rem;color:#7038F8;margin-bottom:6px;">✨ LEGENDARY ✨</div>' if is_leg else ""

    st.markdown(
        f'<div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);'
        f'border:2px solid {bc};border-radius:16px;padding:1.2rem;'
        f'text-align:center;box-shadow:0 0 18px {bc}44;margin-bottom:1rem;">'
        f'{leg_tag}'
        f'<img src="{sprite}" width="110" style="image-rendering:pixelated;margin:4px 0;"/>'
        f'<div style="font-weight:700;font-size:1rem;">{poke["name"]}</div>'
        f'<div style="margin:4px 0;">{types_html}</div>'
        f'<div style="font-size:0.8rem;color:var(--text-muted);margin-top:6px;">'
        f'Roll d20 — need <b style="color:{bc}">{threshold}+</b> to catch</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    if roll_res is None:
        # Show roll buttons (one chance only)
        mb_count    = get_master_balls(trainer) if trainer else 0
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button("🎲 Roll d20!", key=f"{cap_key}_btn", use_container_width=True):
                roll = random.randint(1, 20)
                st.session_state[f"{cap_key}_roll"]   = roll
                st.session_state[f"{cap_key}_result"] = "caught" if roll >= threshold else "escaped"
                st.rerun()
        with c2:
            if st.button("✅ Caught IRL!", key=f"{cap_key}_irl", use_container_width=True):
                st.session_state[f"{cap_key}_roll"]   = 20
                st.session_state[f"{cap_key}_result"] = "caught"
                st.rerun()
        with c3:
            mb_label    = f"⚪ Master Ball ({mb_count})" if mb_count > 0 else "⚪ No Master Balls"
            mb_disabled = mb_count <= 0
            if st.button(mb_label, key=f"{cap_key}_mb", use_container_width=True,
                         disabled=mb_disabled, help="Auto-catch! Uses 1 Master Ball."):
                if trainer:
                    use_master_ball(trainer)
                st.session_state[f"{cap_key}_roll"]   = 20
                st.session_state[f"{cap_key}_result"] = "caught"
                st.rerun()
        with c4:
            if st.button("⏭️ Skip", key=f"{cap_key}_skip", use_container_width=True):
                st.session_state[f"{cap_key}_result"] = "skipped"
                st.rerun()
        # Also allow going back to repick
        if st.button("← Change selection", key=f"gt_back_{trainer}", use_container_width=False):
            selections[trainer] = None
            st.session_state.gt_capture_selections = selections
            st.rerun()
        return

    # Result is in — show outcome, then auto-advance to next trainer
    results[poke["name"]] = roll_res
    st.session_state.gt_capture_results = results

    if roll_res == "caught":
        roll_line = f"Rolled <b style='color:#FFCB05'>{roll_val}</b> — success!" if roll_val and roll_val < 20 else "Caught in real life!"
        st.markdown(
            f'<div style="background:linear-gradient(145deg,#1a3a1a,#0f2a0f);'
            f'border:2px solid #4CAF50;border-radius:12px;padding:1rem;text-align:center;">'
            f'<div style="font-size:1.5rem">🎉</div>'
            f'<div style="font-family:monospace;font-size:0.6rem;color:#4CAF50;">'
            f'{poke["name"]} was caught!</div>'
            f'<div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px;">{roll_line}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    elif roll_res == "escaped":
        st.markdown(
            f'<div style="background:rgba(227,53,13,0.1);border:2px solid #E3350D;'
            f'border-radius:12px;padding:1rem;text-align:center;">'
            f'<div style="font-size:1.5rem">💨</div>'
            f'<div style="font-size:0.85rem;color:#E3350D;font-weight:700;">{poke["name"]} broke free!</div>'
            f'<div style="font-size:0.8rem;color:var(--text-muted);">'
            f'Rolled <b style="color:#FFCB05">{roll_val}</b> — needed {threshold}+</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        st.info("Capture skipped.")

    st.markdown("<br>", unsafe_allow_html=True)
    next_label = f"➡️ {trainers[trainer_idx+1]}'s turn" if trainer_idx + 1 < len(trainers) else "➡️ See results"
    if st.button(next_label, key=f"gt_next_trainer_{trainer}", use_container_width=True):
        # Clear roll state for this trainer
        for k in [f"{cap_key}_roll", f"{cap_key}_result"]:
            st.session_state.pop(k, None)
        st.session_state.gt_capture_trainer_idx = trainer_idx + 1
        st.rerun()


# ── Phase: result ─────────────────────────────────────────────────────────────

def _phase_result():
    trainers = st.session_state.gt_trainers
    defeated = st.session_state.gt_defeated
    log      = st.session_state.gt_log
    success  = len(defeated) == GAUNTLET_SIZE

    if success:
        st.markdown(f"""
        <div style="text-align:center;padding:2rem;
            background:linear-gradient(135deg,rgba(255,203,5,0.1),rgba(255,203,5,0.05));
            border:3px solid #FFCB05;border-radius:20px;margin-bottom:1rem;
            animation:pulse 1.5s infinite;">
            <div style="font-size:3rem">🏆</div>
            <div style="font-family:monospace;font-size:0.85rem;
                color:#FFCB05;text-shadow:0 0 20px rgba(255,203,5,0.8);margin:0.5rem 0;">
                GAUNTLET CLEARED!
            </div>
            <div style="font-size:0.85rem;color:var(--text-muted);">
                {' & '.join(trainers)} defeated all {GAUNTLET_SIZE} enemies!<br>
                All trainers levelled up ×2!
            </div>
        </div>""", unsafe_allow_html=True)
        st.balloons()
    else:
        st.markdown(
            f'<div class="lose-banner">💀 GAUNTLET FAILED — '
            f'{len(defeated)}/{GAUNTLET_SIZE} enemies defeated</div>',
            unsafe_allow_html=True
        )
        # Offer capture if not already done
        if defeated and not st.session_state.get("gt_capture_results"):
            if st.button("⚾ Capture defeated Pokémon", use_container_width=True):
                _enter_capture(include_legendary=False)
                st.rerun()

    if log:
        st.markdown("#### Battle Log")
        st.markdown(f'<div class="battle-log">{chr(10).join(log[-15:])}</div>',
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Run Another Gauntlet", use_container_width=True):
        _reset()
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────

def render():
    init_captures_csv()
    _init()
    st.markdown("## ⚔️ Gauntlet")

    phase = st.session_state.gt_phase
    if   phase == "setup":     _phase_setup()
    elif phase == "battle":    _phase_battle()
    elif phase == "cards":     _phase_cards()
    elif phase == "legendary": _phase_legendary()
    elif phase == "capture":   _phase_capture()
    elif phase == "result":    _phase_result()
