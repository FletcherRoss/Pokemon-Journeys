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
    """Render a Pokéball-shaped board using HTML/CSS grid."""

    # Build square data
    def sq_html(idx, is_center=False):
        if is_center:
            label, emoji, color, _ = SQUARE_TYPES["gauntlet"]
        else:
            label, emoji, color, _ = _sq(idx)

        # Find players on this square
        players_here = [t for t, pos in positions.items() if pos == idx]
        player_dots  = "".join(
            f'<span style="color:{TRAINER_COLORS.get(t,"#fff")};font-size:0.7rem;">'
            f'{TRAINER_EMOJI.get(t,"●")}</span>'
            for t in players_here
        )
        is_active = any(t == current_trainer for t in players_here)
        ring = f"box-shadow:0 0 8px {color};" if is_active else ""

        num = f'<span style="font-size:0.5rem;color:#666;position:absolute;top:2px;left:3px;">{idx}</span>'

        return (
            f'<div style="position:relative;background:linear-gradient(145deg,#1e2a4a,#0f1a35);'
            f'border:1px solid {color};border-radius:6px;padding:3px 2px;'
            f'text-align:center;font-size:0.7rem;min-height:52px;{ring}">'
            f'{num}'
            f'<div style="font-size:1rem;margin-top:4px;">{emoji}</div>'
            f'<div style="font-size:0.5rem;color:#aaa;line-height:1.1;">{label[:8]}</div>'
            f'<div style="margin-top:2px;">{player_dots}</div>'
            f'</div>'
        )

    # Top row: squares 0-13 (red pokeball top)
    top_squares = "".join(sq_html(i) for i in range(14))
    # Bottom row: squares 14-27 (white pokeball bottom)
    bot_squares = "".join(sq_html(i) for i in range(14, 28))

    # Pre-compute center player dots (avoids generator inside f-string)
    center_dots = "".join(
        f'<span style="color:{TRAINER_COLORS.get(t,"#fff")};font-size:0.8rem;">'
        f'{TRAINER_EMOJI.get(t,"●")}</span>'
        for t, pos in positions.items() if pos == CENTER_SQ
    )

    board_html = (
        '<style>'
        '.board-grid{display:grid;grid-template-columns:repeat(14,1fr);gap:3px;margin-bottom:4px;}'
        '.board-center{display:grid;grid-template-columns:3fr 8fr 3fr;gap:3px;margin-bottom:4px;}'
        '.center-sq{background:linear-gradient(145deg,#3a0a0a,#1a0505);border:2px solid #E3350D;'
        'border-radius:10px;text-align:center;padding:8px 4px;box-shadow:0 0 16px rgba(227,53,13,0.5);}'
        '.divider-line{background:rgba(255,255,255,0.15);border-radius:4px;display:flex;'
        'align-items:center;justify-content:center;font-size:0.6rem;color:#555;}'
        '</style>'
        '<div style="background:rgba(0,0,0,0.3);border:2px solid #E3350D;border-radius:16px;padding:8px;">'

        # Red top half
        '<div style="background:rgba(227,53,13,0.08);border-radius:10px 10px 0 0;padding:4px;margin-bottom:2px;">'
        '<div style="font-size:0.55rem;color:#E3350D;text-align:center;margin-bottom:3px;letter-spacing:2px;">── RED HALF ──</div>'
        f'<div class="board-grid">{top_squares}</div>'
        '</div>'

        # Center band
        '<div class="board-center" style="margin:4px 0;">'
        '<div class="divider-line" style="background:rgba(227,53,13,0.1);"><span>🔴</span></div>'
        '<div class="center-sq">'
        '<div style="font-size:1.6rem">⚔️</div>'
        '<div style="font-family:monospace;font-size:0.55rem;color:#E3350D;font-weight:700;margin:3px 0;">THE GAUNTLET</div>'
        '<div style="font-size:0.5rem;color:#aaa;">Land here to enter</div>'
        f'<div style="margin-top:4px;">{center_dots}</div>'
        '</div>'
        '<div class="divider-line" style="background:rgba(200,200,200,0.05);"><span>⚪</span></div>'
        '</div>'

        # White bottom half
        '<div style="background:rgba(200,200,200,0.03);border-radius:0 0 10px 10px;padding:4px;margin-top:2px;">'
        '<div style="font-size:0.55rem;color:#aaa;text-align:center;margin-bottom:3px;letter-spacing:2px;">── WHITE HALF ──</div>'
        f'<div class="board-grid">{bot_squares}</div>'
        '</div>'

        '</div>'
    )
    st.markdown(board_html, unsafe_allow_html=True)


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

    st.markdown(f"""
    <div style="background:rgba(0,0,0,0.25);border:1px solid {color};
        border-radius:12px;padding:1rem;margin-bottom:0.8rem;">
        <div style="font-size:1.3rem;text-align:center;">{_dice_face(d1)} + {_dice_face(d2)} = <b>{total}</b></div>
        <div style="text-align:center;margin-top:6px;font-size:0.85rem;">
            Square {cur_pos} → <b>Square {new_pos if not goes_center else "CENTER"}</b>
            {"🆕 LAP " + str(new_laps) + " COMPLETE! 🎉" if new_laps > laps[trainer] else ""}
        </div>
        <div style="text-align:center;margin-top:6px;">
            <span style="background:{sq_color}22;border:1px solid {sq_color};
                border-radius:8px;padding:3px 10px;font-size:0.85rem;">
                {sq_emoji} {sq_label}
            </span>
        </div>
        <div style="text-align:center;font-size:0.8rem;color:var(--text-muted);margin-top:4px;">
            {sq_desc}
        </div>
    </div>""", unsafe_allow_html=True)

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
