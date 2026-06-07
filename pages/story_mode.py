import sys, os, random, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.captures_manager import init_captures_csv, level_up_team
from utils.pokemon_api import fetch_pokemon

TRAINERS       = ["Addy", "Oakley", "Raelynn"]
TRAINER_COLORS = {"Addy": "#F06292", "Oakley": "#64B5F6", "Raelynn": "#FFB74D"}
TRAINER_EMOJI  = {"Addy": "🌸", "Oakley": "⚡", "Raelynn": "🔥"}

# ── Board definition ──────────────────────────────────────────────────────────
# 28 outer squares (0-27) + 1 center square (28 = Gauntlet)
# Squares are arranged as a Pokéball:
#   Top half = squares 0-13 (red half)
#   Bottom half = squares 14-27 (white half)
#   Center = square 28 (the Gauntlet)

BOARD_SIZE = 28   # outer squares
CENTER_SQ  = 28   # index of center gauntlet square

SQUARE_TYPES = {
    # id: (label, emoji, color, description)
    "wild":     ("Wild Battle",    "🌿", "#78C850", "Battle a random wild Pokémon!"),
    "gym":      ("Gym Battle",     "🏟️", "#3D7DCA", "Challenge a gym leader!"),
    "trainer":  ("Trainer Battle", "🤝", "#F06292", "Face another trainer!"),
    "random":   ("Random Battle",  "🎲", "#FFCB05", "A mystery battle awaits!"),
    "heal":     ("Poké Center",    "💊", "#4CAF50", "Restore your team to full HP!"),
    "nothing":  ("Rest Stop",      "😴", "#888",    "Nothing happens. Catch your breath."),
    "secret":   ("Secret Square",  "❓", "#A040A0", "Something unexpected happens…"),
    "gauntlet": ("THE GAUNTLET",   "⚔️", "#E3350D", "Enter the Gauntlet — the ultimate challenge!"),
}

SECRET_EVENTS = [
    {"id": "levelup",    "emoji": "⬆️", "name": "Lucky Level Up!",    "desc": "Your whole team levels up by 1!", "rare": True},
    {"id": "rocket",     "emoji": "🚀", "name": "Team Rocket Attack!", "desc": "You were ambushed by Team Rocket! Lose your next turn.", "rare": False},
    {"id": "rocket",     "emoji": "🚀", "name": "Team Rocket Attack!", "desc": "You were ambushed by Team Rocket! Lose your next turn.", "rare": False},
    {"id": "heal_half",  "emoji": "🩹", "name": "Found a Potion!",     "desc": "Your active Pokémon recovers 50% HP.", "rare": False},
    {"id": "nothing",    "emoji": "💨", "name": "False Alarm",          "desc": "Nothing is here. Must have been the wind.", "rare": False},
    {"id": "warp",       "emoji": "🌀", "name": "Warp Tile!",           "desc": "You're warped to a random square on the board!", "rare": False},
    {"id": "levelup",    "emoji": "⬆️", "name": "Lucky Level Up!",    "desc": "Your whole team levels up by 1!", "rare": True},
    {"id": "rocket",     "emoji": "🚀", "name": "Team Rocket Attack!", "desc": "You were ambushed by Team Rocket! Lose your next turn.", "rare": False},
]

# Fixed board layout (repeating pattern around the ring)
OUTER_BOARD = [
    "wild", "nothing", "gym", "secret", "heal", "wild",
    "trainer", "nothing", "random", "wild", "nothing", "gym",
    "secret", "heal", "wild", "nothing", "trainer", "random",
    "wild", "secret", "nothing", "gym", "heal", "wild",
    "nothing", "trainer", "random", "secret",
]  # 28 squares

def _sq(i):
    if i == CENTER_SQ:
        return SQUARE_TYPES["gauntlet"]
    return SQUARE_TYPES[OUTER_BOARD[i % BOARD_SIZE]]


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


# ── Session state ─────────────────────────────────────────────────────────────

def _init():
    defaults = {
        "sm_phase":         "setup",    # setup|roll|event|result
        "sm_players":       [],         # list of trainer names
        "sm_positions":     {},         # {trainer: square_index}
        "sm_turn_order":    [],         # list of trainers in turn order
        "sm_turn_idx":      0,          # whose turn it is
        "sm_skip_next":     {},         # {trainer: True} if losing next turn
        "sm_event":         None,       # current event dict
        "sm_dice_rolled":   False,
        "sm_dice_result":   (0, 0),
        "sm_log":           [],
        "sm_winner":        None,
        "sm_laps":          {},         # {trainer: lap count}
        "sm_target_laps":   2,          # laps to win
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    for k in list(st.session_state.keys()):
        if k.startswith("sm_"):
            del st.session_state[k]


# ── Board renderer ────────────────────────────────────────────────────────────

def _render_board(positions, current_trainer):
    """Render a circular Pokéball board using SVG. 28 outer squares + center gauntlet."""
    import math

    cx, cy, r = 340, 310, 265   # center and radius of the ring

    # Build per-square data
    squares = []
    for i in range(BOARD_SIZE):
        angle_deg = -90 + (i / BOARD_SIZE) * 360   # start at top, go clockwise
        angle_rad = math.radians(angle_deg)
        sx = cx + r * math.cos(angle_rad)
        sy = cy + r * math.sin(angle_rad)
        label, emoji, color, _ = _sq(i)
        players_here = [t for t, pos in positions.items() if pos == i]
        squares.append({
            "idx": i, "x": sx, "y": sy,
            "label": label, "emoji": emoji, "color": color,
            "players": players_here,
            "is_active": any(t == current_trainer for t in players_here),
        })

    center_players = [t for t, pos in positions.items() if pos == CENTER_SQ]

    # Build SVG pieces
    # -- dividing line (horizontal band across center)
    divider_top = cy - 14
    divider_bot = cy + 14

    # -- outer ring squares
    sq_parts = []
    for sq in squares:
        x, y = sq["x"], sq["y"]
        color = sq["color"]
        ring_stroke = 2.5 if sq["is_active"] else 0.5
        ring_opacity = 1.0 if sq["is_active"] else 0.7
        glow = f'filter:drop-shadow(0 0 4px {color});' if sq["is_active"] else ""

        # player dots HTML
        player_text = ""
        for t in sq["players"]:
            tc = TRAINER_COLORS.get(t, "#fff")
            te = TRAINER_EMOJI.get(t, "●")
            player_text += f'<tspan fill="{tc}">{te}</tspan>'

        sq_parts.append(
            f'<g style="opacity:{ring_opacity};{glow}">'
            f'<rect x="{x-18}" y="{y-18}" width="36" height="36" rx="5" '
            f'fill="#1e2a4a" stroke="{color}" stroke-width="{ring_stroke}"/>'
            f'<text x="{x}" y="{y-3}" text-anchor="middle" '
            f'font-size="14" dominant-baseline="central">{sq["emoji"]}</text>'
            f'<text x="{x}" y="{y+11}" text-anchor="middle" '
            f'fill="#aaa" font-size="7" dominant-baseline="central">{sq["idx"]}</text>'
            + (f'<text x="{x}" y="{y+8}" text-anchor="middle" font-size="10">{player_text}</text>' if sq["players"] else "")
            + f'</g>'
        )

    # -- center Gauntlet
    center_dot_parts = "".join(
        f'<tspan fill="{TRAINER_COLORS.get(t,"#fff")}">{TRAINER_EMOJI.get(t,"●")}</tspan>'
        for t in center_players
    )
    center_player_line = f'<text x="{cx}" y="{cy+20}" text-anchor="middle" font-size="13">{center_dot_parts}</text>' if center_players else ""

    sq_svg   = "\n".join(sq_parts)
    svg_body = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 680 620"
         style="display:block;margin:0 auto;">
      <defs>
        <clipPath id="ball-clip">
          <circle cx="{cx}" cy="{cy}" r="{r+20}"/>
        </clipPath>
      </defs>

      <!-- Pokéball outer circle -->
      <circle cx="{cx}" cy="{cy}" r="{r+22}"
              fill="none" stroke="#E3350D" stroke-width="2" opacity="0.4"/>

      <!-- Red half (top) -->
      <path d="M {cx-r-22} {cy} A {r+22} {r+22} 0 0 1 {cx+r+22} {cy} Z"
            fill="#E3350D" opacity="0.06"/>

      <!-- White half (bottom) -->
      <path d="M {cx-r-22} {cy} A {r+22} {r+22} 0 0 0 {cx+r+22} {cy} Z"
            fill="#ffffff" opacity="0.03"/>

      <!-- Dividing band -->
      <rect x="{cx-r-22}" y="{divider_top}" width="{(r+22)*2}" height="28"
            fill="#333" opacity="0.5" clip-path="url(#ball-clip)"/>

      <!-- Center Pokéball button -->
      <circle cx="{cx}" cy="{cy}" r="52"
              fill="#1a0a0a" stroke="#E3350D" stroke-width="2"/>
      <circle cx="{cx}" cy="{cy}" r="48"
              fill="#2a0f0f" stroke="#c0280a" stroke-width="1"/>
      <text x="{cx}" y="{cy-8}" text-anchor="middle" fill="#E3350D"
            font-size="20" font-weight="bold">⚔️</text>
      <text x="{cx}" y="{cy+8}" text-anchor="middle" fill="#E3350D"
            font-size="8" font-family="monospace" font-weight="bold">GAUNTLET</text>
      {center_player_line}

      <!-- Board squares around the ring -->
      {sq_svg}
    </svg>
    """
    st.markdown(svg_body, unsafe_allow_html=True)



# ── Dice renderer ─────────────────────────────────────────────────────────────

def _dice_face(n):
    faces = {
        1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"
    }
    return faces.get(n, str(n))


# ── Phases ────────────────────────────────────────────────────────────────────

def _phase_setup():
    st.markdown("### 🎲 Story Mode — Pokéball Board Game")
    st.markdown("""
    <div style="background:rgba(0,0,0,0.3);border:1px solid var(--poke-blue);
        border-radius:10px;padding:1rem;font-size:0.82rem;color:var(--text-muted);margin-bottom:1.2rem;">
        🎮 <b>How Story Mode works:</b><br>
        • Players take turns rolling 2d6 to move around a Pokéball-shaped board<br>
        • Land on battle squares to fight — complete those battles in their respective pages<br>
        • Land on the <b>center Gauntlet square</b> to trigger the ultimate challenge<br>
        • Secret squares may level up your team or unleash Team Rocket!<br>
        • First trainer to complete <b>2 full laps</b> wins the story mode
    </div>""", unsafe_allow_html=True)

    selected = st.multiselect("Choose players (1–3):", TRAINERS,
                              default=[TRAINERS[0]], key="sm_player_sel", max_selections=3)
    if not selected:
        st.warning("Select at least 1 player.")
        return

    laps = st.number_input("Laps to win:", min_value=1, max_value=5, value=2, step=1)

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
    if st.button("🎲 Start Story Mode!", use_container_width=True):
        st.session_state.sm_players     = selected
        st.session_state.sm_turn_order  = selected[:]
        st.session_state.sm_positions   = {t: 0 for t in selected}
        st.session_state.sm_laps        = {t: 0 for t in selected}
        st.session_state.sm_skip_next   = {t: False for t in selected}
        st.session_state.sm_target_laps = int(laps)
        st.session_state.sm_turn_idx    = 0
        st.session_state.sm_log         = ["🎲 Story Mode begins! Everyone starts at Square 0."]
        st.session_state.sm_phase       = "roll"
        st.rerun()


def _phase_roll():
    players    = st.session_state.sm_players
    positions  = st.session_state.sm_positions
    laps       = st.session_state.sm_laps
    turn_order = st.session_state.sm_turn_order
    turn_idx   = st.session_state.sm_turn_idx
    skip_map   = st.session_state.sm_skip_next
    log        = st.session_state.sm_log
    target     = st.session_state.sm_target_laps

    trainer    = turn_order[turn_idx % len(turn_order)]
    color      = TRAINER_COLORS.get(trainer, "#888")
    emoji      = TRAINER_EMOJI.get(trainer, "🎮")

    # Board
    _render_board(positions, trainer)
    st.markdown("<br>", unsafe_allow_html=True)

    # Standings
    st.markdown("#### 📊 Standings")
    stand_cols = st.columns(len(players))
    for col, t in zip(stand_cols, players):
        tc = TRAINER_COLORS.get(t, "#888")
        pos = positions[t]
        lap = laps[t]
        sq_label, sq_emoji, _, _ = _sq(pos)
        skip = skip_map.get(t, False)
        with col:
            st.markdown(
                f'<div style="border:1px solid {tc};border-radius:10px;padding:6px;text-align:center;">'
                f'<b style="color:{tc};">{TRAINER_EMOJI.get(t,"")}{t}</b><br>'
                f'<small>Sq.{pos} | Lap {lap}/{target}</small><br>'
                f'<small>{sq_emoji} {sq_label}</small>'
                + ('<br><small style="color:#E3350D;">⏸️ Skipping</small>' if skip else '') +
                '</div>',
                unsafe_allow_html=True
            )

    st.markdown("---")
    st.markdown(f"### {emoji} {trainer}'s Turn")

    # Handle skip
    if skip_map.get(trainer, False):
        st.markdown(f"""
        <div style="background:rgba(227,53,13,0.1);border:2px solid #E3350D;
            border-radius:12px;padding:1rem;text-align:center;">
            <div style="font-size:1.5rem">🚀</div>
            <div style="font-weight:700;color:#E3350D;">Team Rocket strikes!</div>
            <div style="font-size:0.85rem;color:var(--text-muted);">{trainer} loses this turn!</div>
        </div>""", unsafe_allow_html=True)
        if st.button("⏭️ Skip Turn", use_container_width=True):
            skip_map[trainer] = False
            st.session_state.sm_skip_next = skip_map
            log.append(f"🚀 {trainer} lost their turn to Team Rocket!")
            st.session_state.sm_log       = log[-50:]
            st.session_state.sm_turn_idx  = turn_idx + 1
            st.rerun()
        return

    # Dice roll
    dice_rolled = st.session_state.sm_dice_rolled
    d1, d2      = st.session_state.sm_dice_result

    if not dice_rolled:
        st.markdown(f"Roll 2 dice to move from **Square {positions[trainer]}**!")
        rc1, rc2 = st.columns(2)
        with rc1:
            if st.button("🎲 Roll 2d6!", key="sm_roll_btn", use_container_width=True):
                d1 = random.randint(1, 6)
                d2 = random.randint(1, 6)
                st.session_state.sm_dice_result  = (d1, d2)
                st.session_state.sm_dice_rolled  = True
                st.rerun()
        with rc2:
            # Manual entry for IRL dice
            st.markdown("<small style='color:var(--text-muted)'>Or enter IRL roll:</small>",
                        unsafe_allow_html=True)
            irl1 = st.number_input("Die 1", 1, 6, 1, key="sm_irl1")
            irl2 = st.number_input("Die 2", 1, 6, 1, key="sm_irl2")
            if st.button("✅ Use IRL Roll", key="sm_irl_btn", use_container_width=True):
                st.session_state.sm_dice_result = (int(irl1), int(irl2))
                st.session_state.sm_dice_rolled  = True
                st.rerun()
        return

    # Dice result — show and confirm move
    total = d1 + d2
    cur_pos = positions[trainer]
    new_pos_raw = cur_pos + total

    # Check for lap completion
    new_laps = laps[trainer]
    if new_pos_raw >= BOARD_SIZE:
        new_laps += 1
        new_pos   = new_pos_raw % BOARD_SIZE
    else:
        new_pos = new_pos_raw

    # Special: if roll lands exactly on center band (via secret portal — 7 = center)
    # Actually: landing on square 7 or 21 (divider squares) teleports to center
    goes_center = (new_pos in [7, 21])

    sq_label, sq_emoji, sq_color, sq_desc = _sq(new_pos if not goes_center else CENTER_SQ)

    # Pre-compute all dynamic values before HTML assembly
    dest_label  = "CENTER" if goes_center else str(new_pos)
    lap_badge   = f"🆕 LAP {new_laps} COMPLETE! 🎉" if new_laps > laps[trainer] else ""
    d1_face     = _dice_face(d1)
    d2_face     = _dice_face(d2)
    sq_bg       = sq_color + "22"

    st.markdown(
        f'<div style="background:rgba(0,0,0,0.25);border:1px solid {color};'
        f'border-radius:12px;padding:1rem;margin-bottom:0.8rem;">'
        f'<div style="font-size:1.3rem;text-align:center;">{d1_face} + {d2_face} = <b>{total}</b></div>'
        f'<div style="text-align:center;margin-top:6px;font-size:0.85rem;">'
        f'Square {cur_pos} → <b>Square {dest_label}</b> {lap_badge}</div>'
        f'<div style="text-align:center;margin-top:6px;">'
        f'<span style="background:{sq_bg};border:1px solid {sq_color};'
        f'border-radius:8px;padding:3px 10px;font-size:0.85rem;">'
        f'{sq_emoji} {sq_label}</span></div>'
        f'<div style="text-align:center;font-size:0.8rem;color:var(--text-muted);margin-top:4px;">'
        f'{sq_desc}</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    if st.button(f"✅ Move to Square {'CENTER' if goes_center else new_pos}",
                 use_container_width=True):
        # Update position and laps
        final_pos = CENTER_SQ if goes_center else new_pos
        positions[trainer] = final_pos
        laps[trainer]      = new_laps
        st.session_state.sm_positions  = positions
        st.session_state.sm_laps       = laps
        st.session_state.sm_dice_rolled = False
        st.session_state.sm_dice_result = (0, 0)

        log_entry = (f"🎲 {trainer} rolled {d1}+{d2}={total} → "
                     f"Square {'CENTER (GAUNTLET!)' if goes_center else final_pos} "
                     f"({sq_label})")
        if new_laps > laps.get(trainer, 0):
            log_entry += f" 🏁 Lap {new_laps}!"
        log.append(log_entry)
        st.session_state.sm_log = log[-50:]

        # Check win condition
        if new_laps >= target:
            st.session_state.sm_winner = trainer
            st.session_state.sm_phase  = "result"
            st.rerun()

        # Trigger square event
        _trigger_event(trainer, final_pos, sq_label)
        st.rerun()


def _trigger_event(trainer, square, sq_label):
    """Set up the event for the landing square."""
    sq_type = OUTER_BOARD[square % BOARD_SIZE] if square != CENTER_SQ else "gauntlet"

    if sq_type == "nothing":
        # Just advance turn
        st.session_state.sm_turn_idx += 1
        return

    if sq_type == "heal":
        st.session_state.sm_event = {
            "type": "heal", "trainer": trainer,
            "title": "💊 Pokémon Center!",
            "desc":  f"{trainer}'s whole team is fully restored!",
            "action": "heal",
        }
        st.session_state.sm_phase = "event"
        return

    if sq_type == "secret":
        event = random.choice(SECRET_EVENTS)
        st.session_state.sm_event = {
            "type": "secret", "trainer": trainer,
            "title": f"{event['emoji']} {event['name']}",
            "desc":  event["desc"],
            "action": event["id"],
        }
        st.session_state.sm_phase = "event"
        return

    # Battle squares and gauntlet — just show the instruction
    battle_map = {
        "wild":     ("Wild Battle",    "Go to ⚔️ Wild Battle and fight!", "wild"),
        "gym":      ("Gym Battle",     "Head to 🏟️ Gym Battle and challenge a leader!", "gym"),
        "trainer":  ("Trainer Battle", "Go to 🤝 Trainer Battle for a duel!", "trainer"),
        "random":   ("Random Battle",  "Head to 🎲 Random Battle for a mystery fight!", "random"),
        "gauntlet": ("THE GAUNTLET",   "Enter ⚔️ Gauntlet mode — face 4 wild Pokémon and a legendary!", "gauntlet"),
    }
    if sq_type in battle_map:
        title, desc, btype = battle_map[sq_type]
        st.session_state.sm_event = {
            "type": "battle", "trainer": trainer,
            "title": f"⚔️ {title}",
            "desc":  desc,
            "battle_type": btype,
        }
        st.session_state.sm_phase = "event"


def _phase_event():
    event    = st.session_state.sm_event
    trainer  = event.get("trainer", "")
    color    = TRAINER_COLORS.get(trainer, "#888")
    emoji    = TRAINER_EMOJI.get(trainer, "🎮")
    log      = st.session_state.sm_log
    positions = st.session_state.sm_positions

    _render_board(positions, trainer)
    st.markdown("<br>", unsafe_allow_html=True)

    etype = event.get("type")

    # ── Instant effects (heal / secret) ──────────────────────────────────────
    if etype in ("heal", "secret"):
        action = event.get("action")

        st.markdown(f"""
        <div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);
            border:2px solid {color};border-radius:16px;padding:1.5rem;
            text-align:center;margin-bottom:1rem;">
            <div style="font-size:2.5rem">{event['title'].split()[0]}</div>
            <div style="font-size:1rem;font-weight:700;margin:0.5rem 0;">{event['title']}</div>
            <div style="font-size:0.85rem;color:var(--text-muted);">{event['desc']}</div>
        </div>""", unsafe_allow_html=True)

        if st.button("✅ Apply & Continue", use_container_width=True, key="sm_event_apply"):
            # Apply effect
            if action == "heal":
                _apply_heal(trainer)
                log.append(f"💊 {trainer} used a Pokémon Center — team fully healed!")
            elif action == "levelup":
                msgs = level_up_team(trainer, amount=1)
                log.extend(msgs)
                log.append(f"⬆️ {trainer}'s team levelled up!")
            elif action == "rocket":
                st.session_state.sm_skip_next[trainer] = True
                log.append(f"🚀 Team Rocket attacked {trainer}! They lose their next turn.")
            elif action == "heal_half":
                _apply_heal(trainer, half=True)
                log.append(f"🩹 {trainer} found a Potion — active Pokémon recovered 50% HP!")
            elif action == "warp":
                new_sq = random.randint(0, BOARD_SIZE - 1)
                st.session_state.sm_positions[trainer] = new_sq
                sq_label, sq_emoji, _, _ = _sq(new_sq)
                log.append(f"🌀 {trainer} warped to Square {new_sq} ({sq_emoji} {sq_label})!")
            elif action == "nothing":
                log.append(f"💨 {trainer} found nothing on the secret square.")

            st.session_state.sm_log      = log[-50:]
            st.session_state.sm_event    = None
            st.session_state.sm_turn_idx += 1
            st.session_state.sm_phase    = "roll"
            st.rerun()
        return

    # ── Battle instruction ────────────────────────────────────────────────────
    if etype == "battle":
        btype = event.get("battle_type", "wild")
        page_map = {
            "wild":     "⚔️ Wild Battle",
            "gym":      "🏟️ Gym Battle",
            "trainer":  "🤝 Trainer Battle",
            "random":   "🎲 Random Battle",
            "gauntlet": "⚔️ Gauntlet",
        }
        page_label = page_map.get(btype, "the battle page")

        result_won  = st.session_state.get("sm_battle_won")
        result_lost = st.session_state.get("sm_battle_lost")

        if result_won is None and result_lost is None:
            st.markdown(f"""
            <div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);
                border:2px solid {color};border-radius:16px;padding:1.5rem;
                text-align:center;margin-bottom:1rem;">
                <div style="font-size:2.5rem">⚔️</div>
                <div style="font-size:1rem;font-weight:700;margin:0.5rem 0;">{event['title']}</div>
                <div style="font-size:0.85rem;color:var(--text-muted);">{event['desc']}</div>
                <div style="margin-top:0.8rem;font-size:0.8rem;color:var(--text-muted);">
                    Navigate to <b style="color:{color};">{page_label}</b> in the sidebar,<br>
                    complete the battle, then come back and report the result!
                </div>
            </div>""", unsafe_allow_html=True)

            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("🏆 I Won!", key="sm_won_btn", use_container_width=True):
                    st.session_state.sm_battle_won = True
                    st.rerun()
            with bc2:
                if st.button("💀 I Lost / Skipped", key="sm_lost_btn", use_container_width=True):
                    st.session_state.sm_battle_lost = True
                    st.rerun()
            return

        # Result reported
        if result_won:
            st.success(f"🏆 {trainer} won the {event['title']}! Turn ends.")
            log.append(f"🏆 {trainer} won at {event['title']}!")
            # Bonus: heal 25% on battle win
            _apply_heal(trainer, quarter=True)
        else:
            st.warning(f"💀 {trainer} lost or skipped. Better luck next time!")
            log.append(f"💀 {trainer} lost at {event['title']}.")

        st.session_state.sm_log       = log[-50:]
        # Clear battle result flags
        for k in ["sm_battle_won", "sm_battle_lost"]:
            st.session_state.pop(k, None)

        if st.button("➡️ Next player's turn", use_container_width=True, key="sm_next_turn"):
            st.session_state.sm_event    = None
            st.session_state.sm_turn_idx += 1
            st.session_state.sm_phase    = "roll"
            st.rerun()

    # Log
    if log:
        st.markdown("#### 📜 Board Log")
        st.markdown(f'<div class="battle-log">{chr(10).join(log[-10:])}</div>',
                    unsafe_allow_html=True)


def _apply_heal(trainer, half=False, quarter=False):
    df  = load_teams()
    row = df[df["trainer"] == trainer]
    if not len(row):
        return
    # Just log it — actual session HP is in battle pages
    # We set a flag that the battle pages can check
    amount = "full"
    if half:
        amount = "50%"
    elif quarter:
        amount = "25%"
    st.session_state[f"sm_heal_{trainer}"] = amount


def _phase_result():
    winner = st.session_state.sm_winner
    players = st.session_state.sm_players
    laps   = st.session_state.sm_laps
    color  = TRAINER_COLORS.get(winner, "#FFCB05")
    emoji  = TRAINER_EMOJI.get(winner, "🏆")
    log    = st.session_state.sm_log

    positions = st.session_state.sm_positions
    _render_board(positions, winner)
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="text-align:center;padding:2rem;
        background:linear-gradient(135deg,rgba(255,203,5,0.1),rgba(255,203,5,0.05));
        border:3px solid #FFCB05;border-radius:20px;margin-bottom:1rem;
        animation:pulse 1.5s infinite;">
        <div style="font-size:3rem">{emoji}</div>
        <div style="font-family:monospace;font-size:1rem;
            color:#FFCB05;text-shadow:0 0 20px rgba(255,203,5,0.8);margin:0.5rem 0;">
            {winner.upper()} WINS STORY MODE!
        </div>
        <div style="font-size:0.85rem;color:var(--text-muted);">
            Completed {laps.get(winner,0)} laps around the Pokéball board!
        </div>
    </div>""", unsafe_allow_html=True)

    st.balloons()

    # Final standings
    st.markdown("#### Final Standings")
    for t in players:
        tc = TRAINER_COLORS.get(t, "#888")
        st.markdown(
            f'<div style="border-left:4px solid {tc};padding:6px 12px;margin:4px 0;">'
            f'<b style="color:{tc};">{TRAINER_EMOJI.get(t,"")}{t}</b> — '
            f'{laps.get(t,0)} laps | Square {positions.get(t,0)}</div>',
            unsafe_allow_html=True
        )

    if log:
        with st.expander("📜 Full Board Log"):
            st.markdown(f'<div class="battle-log">{chr(10).join(log)}</div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Play Again", use_container_width=True):
        _reset()
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────

def render():
    init_captures_csv()
    _init()
    st.markdown("## 🎲 Story Mode")

    phase = st.session_state.sm_phase
    if   phase == "setup":  _phase_setup()
    elif phase == "roll":   _phase_roll()
    elif phase == "event":  _phase_event()
    elif phase == "result": _phase_result()
