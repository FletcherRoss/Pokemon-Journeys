import sys, os, random
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.captures_manager import init_captures_csv, level_up_team

TRAINERS       = ["Addy", "Oakley", "Raelynn"]
TRAINER_COLORS = {"Addy": "#F06292", "Oakley": "#64B5F6", "Raelynn": "#FFB74D"}
TRAINER_EMOJI  = {"Addy": "🌸", "Oakley": "⚡", "Raelynn": "🔥"}

TOTAL_ROUNDS   = 5
CARDS_PER_TURN = 3

BATTLE_EVENTS = [
    {"id": "wild",     "emoji": "🌿", "name": "Wild Battle",    "desc": "Battle a wild Pokemon. Win = 2 pts.",     "points": 2, "color": "#78C850"},
    {"id": "gym",      "emoji": "🏟", "name": "Gym Battle",     "desc": "Challenge a gym leader. Win = 4 pts.",    "points": 4, "color": "#3D7DCA"},
    {"id": "trainer",  "emoji": "🤝", "name": "Trainer Battle", "desc": "Face another trainer. Win = 3 pts.",      "points": 3, "color": "#F06292"},
    {"id": "random",   "emoji": "🎲", "name": "Random Battle",  "desc": "Mystery battle. Win = 3 pts.",            "points": 3, "color": "#FFCB05"},
    {"id": "gauntlet", "emoji": "⚔", "name": "Gauntlet",       "desc": "Beat the Gauntlet. Win = 6 pts.",         "points": 6, "color": "#E3350D"},
]

CHANCE_EVENTS = [
    {"id": "heal",    "emoji": "💊", "name": "Pokemon Center",  "desc": "Team fully healed! +1 pt.",           "points": 1,  "effect": "heal",        "color": "#4CAF50"},
    {"id": "levelup", "emoji": "⬆", "name": "Level Up!",       "desc": "Whole team levels up x1. +2 pts.",    "points": 2,  "effect": "levelup",     "color": "#FFCB05"},
    {"id": "rocket",  "emoji": "🚀", "name": "Team Rocket!",   "desc": "Ambushed! Lose 1 pt.",                "points": -1, "effect": "rocket",      "color": "#E3350D"},
    {"id": "bonus",   "emoji": "⭐", "name": "Bonus Points",   "desc": "Found a rare item! +2 pts.",           "points": 2,  "effect": "none",        "color": "#FFCB05"},
    {"id": "nothing", "emoji": "💨", "name": "Nothing Happens","desc": "Quiet day. 0 pts.",                    "points": 0,  "effect": "none",        "color": "#888888"},
    {"id": "double",  "emoji": "🔥", "name": "Hot Streak",     "desc": "Double pts next battle card. +0 now.","points": 0,  "effect": "double_next", "color": "#F08030"},
    {"id": "swap",    "emoji": "🃏", "name": "Point Swap",     "desc": "Swap points with the leader!",         "points": 0,  "effect": "swap",        "color": "#A040A0"},
    {"id": "warp",    "emoji": "🌀", "name": "Wild Warp",      "desc": "Random +/-2 pts from the chaos zone.", "points": 0,  "effect": "random_pts",  "color": "#6890F0"},
]


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


# Master Ball helpers

def award_master_ball(trainer: str, amount: int = 1):
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        cur = _safe_int(row.iloc[0].get("master_balls", 0))
        df = update_trainer(df, trainer, master_balls=cur + amount)
        save_teams(df)


def get_master_balls(trainer: str) -> int:
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        return _safe_int(row.iloc[0].get("master_balls", 0))
    return 0


def use_master_ball(trainer: str) -> bool:
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        cur = _safe_int(row.iloc[0].get("master_balls", 0))
        if cur > 0:
            df = update_trainer(df, trainer, master_balls=cur - 1)
            save_teams(df)
            return True
    return False


# Session state

def _init():
    defaults = {
        "sm_phase":       "setup",
        "sm_players":     [],
        "sm_round":       1,
        "sm_turn_idx":    0,
        "sm_scores":      {},
        "sm_double_next": {},
        "sm_round_cards": {},
        "sm_picked_card": {},
        "sm_log":         [],
        "sm_awarded":     False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    for k in list(st.session_state.keys()):
        if k.startswith("sm_"):
            del st.session_state[k]


def _random_card():
    if random.random() < 0.60:
        return dict(random.choice(BATTLE_EVENTS), category="battle")
    else:
        return dict(random.choice(CHANCE_EVENTS), category="chance")


def _deal_cards(players):
    dealt = {}
    for t in players:
        cards = []
        seen  = set()
        while len(cards) < CARDS_PER_TURN:
            c = _random_card()
            if c["id"] not in seen:
                seen.add(c["id"])
                cards.append(c)
        dealt[t] = cards
    return dealt


# Setup phase

def _phase_setup():
    st.markdown("### Pick Your Players")
    st.markdown(
        '<div style="background:rgba(0,0,0,0.3);border:1px solid var(--poke-blue);'
        'border-radius:10px;padding:1rem;font-size:0.82rem;color:var(--text-muted);margin-bottom:1.2rem;">'
        '🏆 <b>How Story Mode works:</b><br>'
        '• <b>5 rounds</b> — each player picks 1 of 3 random event cards per round<br>'
        '• <b>Battle cards:</b> fight in the matching page, report back, earn points<br>'
        '• <b>Chance cards:</b> instant effects — heals, level-ups, chaos, penalties<br>'
        '• Most points after 5 rounds wins a <b>⚪ Master Ball</b><br>'
        '• Master Balls auto-catch any Pokemon — usable in all battle modes!'
        '</div>',
        unsafe_allow_html=True
    )

    selected = st.multiselect("Choose players (1-3):", TRAINERS,
                              default=[TRAINERS[0]], key="sm_player_sel", max_selections=3)
    if not selected:
        st.warning("Select at least 1 player.")
        return

    cols = st.columns(len(selected))
    for col, t in zip(cols, selected):
        color = TRAINER_COLORS.get(t, "#888")
        emoji = TRAINER_EMOJI.get(t, "🎮")
        mb    = get_master_balls(t)
        with col:
            st.markdown(
                f'<div style="text-align:center;border:2px solid {color};'
                f'border-radius:12px;padding:0.8rem;">'
                f'<div style="font-size:2rem">{emoji}</div>'
                f'<div style="font-weight:700;color:{color};">{t}</div>'
                f'<div style="font-size:0.75rem;color:var(--text-muted);">⚪ {mb} Master Ball{"s" if mb != 1 else ""}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🎲 Start Story Mode!", use_container_width=True):
        st.session_state.sm_players     = selected
        st.session_state.sm_scores      = {t: 0 for t in selected}
        st.session_state.sm_double_next = {t: False for t in selected}
        st.session_state.sm_round       = 1
        st.session_state.sm_turn_idx    = 0
        st.session_state.sm_log         = ["Story Mode begins! 5 rounds, best score wins a Master Ball."]
        st.session_state.sm_round_cards = _deal_cards(selected)
        st.session_state.sm_picked_card = {t: None for t in selected}
        st.session_state.sm_phase       = "pick"
        st.rerun()


# Scoreboard

def _scoreboard(players, scores, current_round, current_trainer=None):
    sorted_p = sorted(players, key=lambda t: scores.get(t, 0), reverse=True)
    cols = st.columns(len(players))
    for col, t in zip(cols, sorted_p):
        color  = TRAINER_COLORS.get(t, "#888")
        emoji  = TRAINER_EMOJI.get(t, "🎮")
        pts    = scores.get(t, 0)
        is_cur = (t == current_trainer)
        ring   = f"box-shadow:0 0 14px {color}45;" if is_cur else ""
        act    = f'<div style="font-size:0.6rem;color:{color};">▶ ACTIVE</div>' if is_cur else ""
        with col:
            st.markdown(
                f'<div style="border:2px solid {color};border-radius:12px;'
                f'padding:0.6rem;text-align:center;{ring}">'
                f'<div style="font-size:1.4rem">{emoji}</div>'
                f'<div style="font-weight:700;color:{color};font-size:0.9rem;">{t}</div>'
                f'<div style="font-size:1.3rem;font-weight:700;">{pts} pts</div>'
                f'{act}</div>',
                unsafe_allow_html=True
            )
    st.markdown(
        f'<div style="text-align:center;font-size:0.75rem;color:var(--text-muted);margin-top:4px;">'
        f'Round {current_round} of {TOTAL_ROUNDS}</div>',
        unsafe_allow_html=True
    )


# Pick phase

def _phase_pick():
    players    = st.session_state.sm_players
    scores     = st.session_state.sm_scores
    cur_round  = st.session_state.sm_round
    turn_idx   = st.session_state.sm_turn_idx
    cards_map  = st.session_state.sm_round_cards
    picked_map = st.session_state.sm_picked_card
    log        = st.session_state.sm_log

    st.markdown(f"### Round {cur_round} of {TOTAL_ROUNDS} — Pick Your Event Card")
    _scoreboard(players, scores, cur_round,
                current_trainer=players[turn_idx] if turn_idx < len(players) else None)
    st.markdown("---")

    if all(picked_map.get(t) is not None for t in players):
        st.session_state.sm_phase = "resolve"
        st.rerun()
        return

    trainer = players[turn_idx]
    color   = TRAINER_COLORS.get(trainer, "#888")
    emoji   = TRAINER_EMOJI.get(trainer, "🎮")

    trainer_label = f"{trainer}'s turn"
    st.markdown(
        f'<div style="background:linear-gradient(135deg,rgba(30,40,70,0.9),rgba(15,25,50,0.9));'
        f'border:2px solid {color};border-radius:14px;padding:1rem;text-align:center;margin-bottom:0.8rem;">'
        f'<div style="font-size:1.8rem">{emoji}</div>'
        f'<div style="font-family:monospace;font-size:0.75rem;color:{color};">{trainer_label.upper()}</div>'
        f'<div style="font-size:0.8rem;color:var(--text-muted);">Pick one of your 3 event cards</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    if turn_idx > 0:
        st.info(f"📱 Pass the device to **{trainer}** now!")

    cards = cards_map.get(trainer, [])
    card_cols = st.columns(CARDS_PER_TURN)
    for col, card in zip(card_cols, cards):
        cat    = card.get("category", "battle")
        ccolor = card["color"]
        pts    = card.get("points", 0)
        double = st.session_state.sm_double_next.get(trainer, False)
        pts_display = pts * 2 if (cat == "battle" and double and pts > 0) else pts
        if pts_display > 0:
            pts_label = f"+{pts_display} pts"
        elif pts_display < 0:
            pts_label = f"{pts_display} pts"
        else:
            pts_label = "0 pts"
        double_tag = '<div style="font-size:0.6rem;color:#FFCB05;">DOUBLED!</div>' if (double and cat == "battle" and pts > 0) else ""
        cat_label  = "Battle" if cat == "battle" else "Chance"

        with col:
            st.markdown(
                f'<div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);'
                f'border:2px solid {ccolor};border-radius:14px;padding:1rem;'
                f'text-align:center;min-height:160px;">'
                f'<div style="font-size:0.6rem;color:#aaa;text-transform:uppercase;letter-spacing:1px;">{cat_label}</div>'
                f'<div style="font-size:2rem;margin:6px 0;">{card["emoji"]}</div>'
                f'<div style="font-weight:700;font-size:0.85rem;margin:4px 0;">{card["name"]}</div>'
                f'<div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:6px;">{card["desc"]}</div>'
                f'<div style="font-size:1rem;font-weight:700;color:{ccolor};">{pts_label}</div>'
                f'{double_tag}'
                f'</div>',
                unsafe_allow_html=True
            )
            if st.button(f"Choose {card['name']}", key=f"sm_pick_{trainer}_{card['id']}_{cur_round}",
                         use_container_width=True):
                picked_map[trainer] = card
                st.session_state.sm_picked_card = picked_map
                st.session_state.sm_turn_idx    = turn_idx + 1
                log.append(f"  {trainer} chose: {card['emoji']} {card['name']}")
                st.session_state.sm_log = log[-60:]
                st.rerun()


# Resolve phase

def _phase_resolve():
    players    = st.session_state.sm_players
    scores     = st.session_state.sm_scores
    cur_round  = st.session_state.sm_round
    picked_map = st.session_state.sm_picked_card
    double_map = st.session_state.sm_double_next
    log        = st.session_state.sm_log

    st.markdown(f"### Round {cur_round} — Resolve Events")
    _scoreboard(players, scores, cur_round)
    st.markdown("---")

    resolve_key = f"sm_resolved_r{cur_round}"
    resolved    = st.session_state.get(resolve_key, set())

    page_map = {
        "wild": "Wild Battle", "gym": "Gym Battle",
        "trainer": "Trainer Battle", "random": "Random Battle",
        "gauntlet": "Gauntlet",
    }

    for trainer in players:
        card  = picked_map.get(trainer)
        if not card:
            continue
        color = TRAINER_COLORS.get(trainer, "#888")
        emoji = TRAINER_EMOJI.get(trainer, "🎮")
        cat   = card.get("category", "battle")
        done  = trainer in resolved

        st.markdown(
            f'<div style="border-left:4px solid {color};padding:6px 12px;margin:4px 0;">'
            f'<b style="color:{color};">{emoji} {trainer}</b>: '
            f'{card["emoji"]} <b>{card["name"]}</b>'
            + (" — Done" if done else "")
            + '</div>',
            unsafe_allow_html=True
        )

        if done:
            continue

        if cat == "chance":
            if st.button(f"Apply: {card['name']} for {trainer}",
                         key=f"sm_apply_{cur_round}_{trainer}", use_container_width=False):
                pts = _apply_chance(trainer, card, scores, players, double_map, log)
                scores[trainer] = scores.get(trainer, 0) + pts
                st.session_state.sm_scores = scores
                resolved.add(trainer)
                st.session_state[resolve_key] = resolved
                st.rerun()
        else:
            pts     = card.get("points", 0)
            double  = double_map.get(trainer, False)
            pts_win = pts * 2 if double and pts > 0 else pts
            page    = page_map.get(card["id"], card["name"])
            st.markdown(
                f'<small style="color:var(--text-muted);">Go to <b>{page}</b> page, '
                f'fight, then report result below.</small>',
                unsafe_allow_html=True
            )
            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button(f"Won! +{pts_win} pts", key=f"sm_won_{cur_round}_{trainer}",
                             use_container_width=True):
                    scores[trainer] = scores.get(trainer, 0) + pts_win
                    st.session_state.sm_scores = scores
                    if double:
                        double_map[trainer] = False
                        st.session_state.sm_double_next = double_map
                    resolved.add(trainer)
                    st.session_state[resolve_key] = resolved
                    log.append(f"  {trainer} won {card['name']}! +{pts_win} pts")
                    st.session_state.sm_log = log[-60:]
                    st.rerun()
            with bc2:
                if st.button("Lost (0 pts)", key=f"sm_lost_{cur_round}_{trainer}",
                             use_container_width=True):
                    if double:
                        double_map[trainer] = False
                        st.session_state.sm_double_next = double_map
                    resolved.add(trainer)
                    st.session_state[resolve_key] = resolved
                    log.append(f"  {trainer} lost {card['name']}. 0 pts.")
                    st.session_state.sm_log = log[-60:]
                    st.rerun()

    st.markdown("---")
    all_done = len(resolved) >= len(players)
    if all_done:
        if cur_round >= TOTAL_ROUNDS:
            if st.button("🏁 See Final Results!", use_container_width=True):
                st.session_state.sm_phase = "result"
                st.rerun()
        else:
            if st.button(f"Start Round {cur_round + 1} ▶", use_container_width=True):
                nxt = cur_round + 1
                st.session_state.sm_round       = nxt
                st.session_state.sm_turn_idx    = 0
                st.session_state.sm_round_cards = _deal_cards(players)
                st.session_state.sm_picked_card = {t: None for t in players}
                st.session_state.sm_phase       = "pick"
                log.append(f"-- Round {nxt} begins --")
                st.session_state.sm_log = log[-60:]
                st.rerun()

    if log:
        with st.expander("Round Log"):
            st.markdown(
                f'<div class="battle-log">{chr(10).join(log[-20:])}</div>',
                unsafe_allow_html=True
            )

    _restart_button()


def _apply_chance(trainer, card, scores, players, double_map, log) -> int:
    effect = card.get("effect", "none")
    pts    = card.get("points", 0)

    if effect == "heal":
        st.session_state[f"sm_heal_{trainer}"] = "full"
        log.append(f"  {trainer} used a Pokemon Center!")
    elif effect == "levelup":
        msgs = level_up_team(trainer, amount=1)
        log.extend(msgs)
    elif effect == "rocket":
        log.append(f"  Team Rocket attacked {trainer}! {pts} pt.")
    elif effect == "double_next":
        double_map[trainer] = True
        st.session_state.sm_double_next = double_map
        log.append(f"  {trainer} has DOUBLE POINTS on their next battle!")
        pts = 0
    elif effect == "swap":
        leader = max(players, key=lambda t: scores.get(t, 0))
        if leader != trainer:
            scores[trainer], scores[leader] = scores.get(leader, 0), scores.get(trainer, 0)
            st.session_state.sm_scores = scores
            log.append(f"  {trainer} swapped points with leader {leader}!")
        else:
            log.append(f"  {trainer} is already the leader — no swap!")
        pts = 0
    elif effect == "random_pts":
        pts = random.choice([-2, -1, 0, 1, 2])
        sign = "+" if pts >= 0 else ""
        log.append(f"  Wild Warp gave {trainer} {sign}{pts} pts!")
    return pts


# Result phase

def _phase_result():
    players = st.session_state.sm_players
    scores  = st.session_state.sm_scores
    log     = st.session_state.sm_log

    sorted_players = sorted(players, key=lambda t: scores.get(t, 0), reverse=True)
    winner    = sorted_players[0]
    top_score = scores.get(winner, 0)
    tied      = [t for t in players if scores.get(t, 0) == top_score]
    is_tie    = len(tied) > 1

    if is_tie:
        tied_names = " & ".join(tied)
        st.markdown(
            f'<div style="text-align:center;padding:1.5rem;border:2px solid #FFCB05;'
            f'border-radius:20px;margin-bottom:1rem;">'
            f'<div style="font-size:2.5rem">🤝</div>'
            f'<div style="font-family:monospace;font-size:0.9rem;color:#FFCB05;margin:6px 0;">ITS A TIE!</div>'
            f'<div style="font-size:0.85rem;color:var(--text-muted);">'
            f'{tied_names} all scored {top_score} pts — Master Balls for everyone!</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        color = TRAINER_COLORS.get(winner, "#FFCB05")
        emoji = TRAINER_EMOJI.get(winner, "🏆")
        st.markdown(
            f'<div style="text-align:center;padding:2rem;'
            f'background:linear-gradient(135deg,rgba(255,203,5,0.1),rgba(255,203,5,0.05));'
            f'border:3px solid #FFCB05;border-radius:20px;margin-bottom:1rem;">'
            f'<div style="font-size:3rem">{emoji}</div>'
            f'<div style="font-family:monospace;font-size:1rem;color:#FFCB05;margin:0.5rem 0;">'
            f'{winner.upper()} WINS!</div>'
            f'<div style="font-size:0.85rem;color:var(--text-muted);">'
            f'{top_score} points — earns a Master Ball!</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.balloons()

    winners = tied if is_tie else [winner]
    if not st.session_state.get("sm_awarded", False):
        for w in winners:
            award_master_ball(w, 1)
            log.append(f"  {w} earned a Master Ball!")
        st.session_state.sm_awarded = True
        st.session_state.sm_log     = log[-60:]

    st.markdown("### Final Standings")
    for rank, t in enumerate(sorted_players):
        color  = TRAINER_COLORS.get(t, "#888")
        medal  = ["🥇", "🥈", "🥉"][rank] if rank < 3 else "🎖️"
        pts    = scores.get(t, 0)
        mb_now = get_master_balls(t)
        got_mb = " +1 Master Ball!" if t in winners else ""
        st.markdown(
            f'<div style="border-left:4px solid {color};padding:8px 14px;margin:6px 0;">'
            f'{medal} <b style="color:{color};">{TRAINER_EMOJI.get(t,"")}{t}</b> — '
            f'<b>{pts} pts</b>{got_mb} (Total: {mb_now} Master Ball{"s" if mb_now != 1 else ""})</div>',
            unsafe_allow_html=True
        )

    st.markdown(
        '<div style="background:rgba(255,203,5,0.08);border:1px solid #FFCB05;'
        'border-radius:10px;padding:0.8rem;font-size:0.82rem;color:var(--text-muted);margin-top:1rem;">'
        'Master Ball: in any wild, gym, trainer, or gauntlet capture screen, '
        'use "Use Master Ball" to automatically catch any Pokemon with no roll needed!'
        '</div>',
        unsafe_allow_html=True
    )

    if log:
        with st.expander("Full Game Log"):
            st.markdown(
                f'<div class="battle-log">{chr(10).join(log)}</div>',
                unsafe_allow_html=True
            )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Play Again", use_container_width=True):
        _reset()
        st.rerun()


def _restart_button():
    st.markdown("---")
    if st.session_state.get("sm_confirm_restart"):
        st.warning("Are you sure? This will reset Story Mode for all players.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Yes, restart", key="sm_confirm_yes", use_container_width=True):
                _reset()
                st.rerun()
        with c2:
            if st.button("Cancel", key="sm_confirm_no", use_container_width=True):
                st.session_state.sm_confirm_restart = False
                st.rerun()
    else:
        if st.button("Restart Story Mode", key="sm_restart_btn"):
            st.session_state.sm_confirm_restart = True
            st.rerun()


def render():
    init_captures_csv()
    _init()
    st.markdown("## Story Mode")

    if st.session_state.get("sm_players"):
        parts = []
        for t in st.session_state.sm_players:
            mb = get_master_balls(t)
            parts.append(f'{TRAINER_EMOJI.get(t,"")} {t}: {mb} MB')
        st.markdown(
            '<div style="background:rgba(255,203,5,0.07);border:1px solid #FFCB05;'
            'border-radius:8px;padding:4px 12px;font-size:0.78rem;margin-bottom:0.5rem;">'
            + " &nbsp;|&nbsp; ".join(parts) +
            '</div>',
            unsafe_allow_html=True
        )

    phase = st.session_state.sm_phase
    if   phase == "setup":   _phase_setup()
    elif phase == "pick":    _phase_pick()
    elif phase == "resolve": _phase_resolve()
    elif phase == "result":  _phase_result()
