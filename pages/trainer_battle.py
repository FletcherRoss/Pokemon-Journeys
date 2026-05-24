import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import random
import streamlit as st
from utils.pokemon_api import fetch_pokemon, fetch_moves, type_badge_html
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.captures_manager import load_captures, get_active_captures, init_captures_csv
from utils.movesets_manager import get_moveset, init_movesets_csv
from utils.game_state import hp_percent, hp_bar_color, damage_calc, speed_order, level_up_check

TRAINERS = ["Addy", "Oakley", "Raelynn"]
TRAINER_COLORS = {"Addy": "#F06292", "Oakley": "#64B5F6", "Raelynn": "#FFB74D"}
TRAINER_EMOJI  = {"Addy": "🌸", "Oakley": "⚡", "Raelynn": "🔥"}

TYPE_COLORS = {
    "fire":"#F08030","water":"#6890F0","grass":"#78C850","electric":"#F8D030",
    "psychic":"#F85888","ice":"#98D8D8","dragon":"#7038F8","dark":"#705848",
    "normal":"#A8A878","fighting":"#C03028","poison":"#A040A0","ground":"#E0C068",
    "flying":"#A890F0","bug":"#A8B820","rock":"#B8A038","ghost":"#705898",
    "steel":"#B8B8D0","fairy":"#EE99AC",
}

# ── Session state keys ────────────────────────────────────────────────────────
# tb_phase:  "setup" | "pick_a" | "pick_b" | "reveal" | "battle" | "result"
# tb_trainer_a, tb_trainer_b: trainer names
# tb_team_a, tb_team_b: list of 2 {poke, moves} each
# tb_hp_a, tb_hp_b: list of 2 hp ints
# tb_active_a, tb_active_b: int index of active pokemon
# tb_log: list of str
# tb_winner: trainer name or None


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _reset():
    for k in [
        "tb_phase","tb_trainer_a","tb_trainer_b",
        "tb_team_a","tb_team_b","tb_hp_a","tb_hp_b",
        "tb_active_a","tb_active_b","tb_log","tb_winner",
        "tb_pick_a_sel","tb_pick_b_sel",
    ]:
        if k in st.session_state:
            del st.session_state[k]


def _init():
    defaults = {
        "tb_phase":     "setup",
        "tb_trainer_a": None,
        "tb_trainer_b": None,
        "tb_team_a":    None,
        "tb_team_b":    None,
        "tb_hp_a":      [],
        "tb_hp_b":      [],
        "tb_active_a":  0,
        "tb_active_b":  0,
        "tb_log":       [],
        "tb_winner":    None,
        "tb_pick_a_sel": [],
        "tb_pick_b_sel": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _hp_bar(label, current, maximum):
    pct   = hp_percent(current, maximum)
    color = hp_bar_color(pct)
    st.markdown(
        f'<div style="margin-bottom:4px"><small>{label}: <b>{current}</b>/{maximum}</small>'
        f'<div class="hp-bar-wrap"><div class="hp-bar-fill" '
        f'style="width:{pct}%;background:{color};"></div></div></div>',
        unsafe_allow_html=True
    )


def _build_roster(trainer: str) -> list[dict]:
    """Return full roster for trainer: starter + captures with moves."""
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
            poke  = fetch_pokemon(sid)
            poke["level"] = slv
            custom = get_moveset(trainer, sid)
            moves  = custom if custom else fetch_moves(sid)
            roster.append({"poke": poke, "moves": moves,
                           "label": f"⭐ {poke['name']} (Starter Lv.{slv})"})

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
        roster.append({"poke": poke, "moves": moves,
                       "label": f"⚾ {poke['name']} (Lv.{lv})"})
    return roster


def _poke_mini_card(poke, hp, label, fainted=False, color="#3D7DCA"):
    sprite  = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{poke['id']}.png"
    types   = " ".join(type_badge_html(t) for t in poke["types"])
    opacity = "0.3" if fainted else "1"
    faint   = '<div style="font-size:0.65rem;color:#F44336;font-weight:700;">💀 FAINTED</div>' if fainted else ""
    spd     = poke.get("speed", "?")
    st.markdown(
        f'<div class="pokemon-card" style="cursor:default;opacity:{opacity};border-color:{color};">'
        f'<div style="font-size:0.65rem;color:var(--text-muted);">{label}</div>'
        f'<img src="{sprite}" width="80" style="image-rendering:pixelated"/>'
        f'<div style="font-size:0.8rem;font-weight:700;margin:3px 0;">{poke["name"]}</div>'
        f'{types}'
        f'<div style="font-size:0.62rem;color:var(--text-muted);margin-top:3px;">Lv.{poke.get("level","?")} ⚡{spd}</div>'
        f'{faint}</div>',
        unsafe_allow_html=True
    )
    if not fainted:
        _hp_bar("HP", hp, poke["hp"])


def _pick_screen(trainer: str, sel_key: str, other_trainer: str):
    """Blind pick screen for one trainer. Other trainer's picks hidden."""
    color  = TRAINER_COLORS.get(trainer, "#888")
    emoji  = TRAINER_EMOJI.get(trainer, "🎮")

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,rgba(30,40,70,0.95),rgba(15,25,50,0.95));
        border:2px solid {color};border-radius:16px;padding:1.5rem;margin-bottom:1rem;text-align:center;">
        <div style="font-size:2.5rem">{emoji}</div>
        <div style="font-family:'Press Start 2P',monospace;font-size:0.8rem;color:{color};margin:6px 0;">
            {trainer.upper()}'S TURN
        </div>
        <div style="font-size:0.8rem;color:var(--text-muted);">
            📵 Pass the device to <b>{trainer}</b>. {other_trainer}'s picks are hidden.
        </div>
    </div>""", unsafe_allow_html=True)

    # Blur overlay warning
    st.info(f"🔒 Only {trainer} should be looking at this screen right now!")

    roster = _build_roster(trainer)
    if len(roster) < 2:
        st.warning(f"{trainer} needs at least 2 Pokémon to battle!")
        return

    selected = st.session_state[sel_key]
    st.markdown(f"### Pick 2 Pokémon — {len(selected)}/2 selected")

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
            border = f"2px solid {color}" if is_sel else "2px solid var(--poke-blue)"
            bg     = "linear-gradient(145deg,#2a3a0f,#1a2a05)" if is_sel else "linear-gradient(145deg,#1e2a4a,#0f1a35)"

            with col:
                st.markdown(
                    f'<div style="background:{bg};border:{border};border-radius:14px;'
                    f'padding:0.7rem;text-align:center;margin-bottom:4px;">'
                    f'<img src="{sprite}" width="65" style="image-rendering:pixelated"/>'
                    f'<div style="font-size:0.75rem;font-weight:700;margin:3px 0;">{poke["name"]}</div>'
                    f'{types_html}'
                    f'<div style="font-size:0.62rem;color:var(--text-muted);margin-top:2px;">'
                    f'Lv.{lv} ⚡{poke.get("speed","?")} ❤️{poke["hp"]}</div>'
                    f'{"✅" if is_sel else ""}</div>',
                    unsafe_allow_html=True
                )
                if is_sel:
                    if st.button("Deselect", key=f"{sel_key}_desel_{poke['id']}", use_container_width=True):
                        st.session_state[sel_key] = [n for n in selected if n != poke["name"]]
                        st.rerun()
                else:
                    disabled = len(selected) >= 2
                    if st.button("Select", key=f"{sel_key}_sel_{poke['id']}", use_container_width=True, disabled=disabled):
                        st.session_state[sel_key] = selected + [poke["name"]]
                        st.rerun()

    st.markdown(f"**Selected:** {', '.join(selected) if selected else 'None'}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Cancel Battle", use_container_width=True):
            _reset()
            st.rerun()
    with c2:
        if st.button(f"✅ Lock In {trainer}'s Team", use_container_width=True,
                     disabled=len(selected) < 2):
            # Build the team entry
            chosen = [e for e in roster if e["poke"]["name"] in selected][:2]
            return chosen  # caller stores it
    return None


def _attack(attacker_poke, attacker_move, attacker_lv,
            defender_poke, defender_hp_list, defender_idx,
            log, attacker_name, defender_name):
    """Execute one attack. Returns updated defender_hp_list."""
    dmg, hit = damage_calc(attacker_poke, defender_poke, attacker_move, attacker_lv)
    if not hit:
        log.append(f"➤ {attacker_poke['name']} used {attacker_move['name']}... missed! (Acc:{attacker_move.get('accuracy',100)}%)")
    else:
        defender_hp_list[defender_idx] = max(0, defender_hp_list[defender_idx] - dmg)
        log.append(f"➤ {attacker_poke['name']} used {attacker_move['name']}! ({dmg} dmg, Acc:{attacker_move.get('accuracy',100)}%)")
        if defender_hp_list[defender_idx] <= 0:
            log.append(f"💥 {defender_poke['name']} fainted!")
    return defender_hp_list


def _check_winner():
    """Return winning trainer name if battle over, else None."""
    if all(h <= 0 for h in st.session_state.tb_hp_a):
        return st.session_state.tb_trainer_b
    if all(h <= 0 for h in st.session_state.tb_hp_b):
        return st.session_state.tb_trainer_a
    return None


def _auto_switch(hp_list, active_idx):
    """If active is fainted, find next alive. Returns new index."""
    if hp_list[active_idx] <= 0:
        for i, h in enumerate(hp_list):
            if h > 0:
                return i
    return active_idx


def _record_result(winner: str, loser: str):
    df = load_teams()
    for trainer, result in [(winner, "win"), (loser, "loss")]:
        row = df[df["trainer"] == trainer]
        if len(row):
            wins   = _safe_int(row.iloc[0]["wins"])   + (1 if result == "win" else 0)
            losses = _safe_int(row.iloc[0]["losses"]) + (1 if result == "loss" else 0)
            df = update_trainer(df, trainer, wins=wins, losses=losses)
    save_teams(df)


# ── Phase renderers ───────────────────────────────────────────────────────────

def _phase_setup():
    st.markdown("### 🤝 Set Up Trainer Battle")
    st.markdown("Choose two trainers to face off in a 2v2 battle. Each trainer picks their team secretly!")

    col1, col2 = st.columns(2)
    with col1:
        trainer_a = st.selectbox("Trainer 1", TRAINERS, key="tb_sel_a")
    with col2:
        remaining = [t for t in TRAINERS if t != trainer_a]
        trainer_b = st.selectbox("Trainer 2", remaining, key="tb_sel_b")

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;gap:1rem;justify-content:center;margin:1rem 0;">
        <div style="text-align:center;padding:1rem 2rem;
            background:linear-gradient(145deg,#1e2a4a,#0f1a35);
            border:2px solid {TRAINER_COLORS.get(trainer_a,'#888')};border-radius:12px;">
            <div style="font-size:2rem">{TRAINER_EMOJI.get(trainer_a,'🎮')}</div>
            <div style="font-weight:700;color:{TRAINER_COLORS.get(trainer_a,'#888')};">{trainer_a}</div>
        </div>
        <div style="font-size:2rem;display:flex;align-items:center;">VS</div>
        <div style="text-align:center;padding:1rem 2rem;
            background:linear-gradient(145deg,#1e2a4a,#0f1a35);
            border:2px solid {TRAINER_COLORS.get(trainer_b,'#888')};border-radius:12px;">
            <div style="font-size:2rem">{TRAINER_EMOJI.get(trainer_b,'🎮')}</div>
            <div style="font-weight:700;color:{TRAINER_COLORS.get(trainer_b,'#888')};">{trainer_b}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("""
    <div style="background:rgba(0,0,0,0.3);border:1px solid var(--poke-blue);
        border-radius:10px;padding:1rem;font-size:0.82rem;color:var(--text-muted);">
        📋 <b>How it works:</b><br>
        1. Trainer 1 picks their 2 Pokémon in secret<br>
        2. Pass the device to Trainer 2 to pick theirs<br>
        3. Both teams are revealed and the battle begins!
    </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 Start — Trainer 1 picks first!", use_container_width=True):
        st.session_state.tb_trainer_a = trainer_a
        st.session_state.tb_trainer_b = trainer_b
        st.session_state.tb_phase     = "pick_a"
        st.session_state.tb_pick_a_sel = []
        st.session_state.tb_pick_b_sel = []
        st.rerun()


def _phase_pick_a():
    trainer_a = st.session_state.tb_trainer_a
    trainer_b = st.session_state.tb_trainer_b
    result = _pick_screen(trainer_a, "tb_pick_a_sel", trainer_b)
    if result is not None:
        st.session_state.tb_team_a = result
        st.session_state.tb_hp_a   = [e["poke"]["hp"] for e in result]
        st.session_state.tb_phase  = "pick_b"
        st.session_state.tb_pick_b_sel = []
        st.rerun()


def _phase_pick_b():
    trainer_a = st.session_state.tb_trainer_a
    trainer_b = st.session_state.tb_trainer_b

    # Handoff screen — shown briefly before Trainer B looks
    st.markdown(f"""
    <div style="background:rgba(0,0,0,0.6);border:2px solid #FFCB05;
        border-radius:16px;padding:2rem;text-align:center;margin-bottom:1rem;">
        <div style="font-size:2rem">🔒</div>
        <div style="font-family:'Press Start 2P',monospace;font-size:0.75rem;color:#FFCB05;margin:8px 0;">
            {trainer_a.upper()} HAS LOCKED IN!
        </div>
        <div style="font-size:0.85rem;color:var(--text-muted);">
            Pass the device to <b style="color:{TRAINER_COLORS.get(trainer_b,'#888')}">{trainer_b}</b> now.<br>
            Don't show {trainer_b} what {trainer_a} picked!
        </div>
    </div>""", unsafe_allow_html=True)

    result = _pick_screen(trainer_b, "tb_pick_b_sel", trainer_a)
    if result is not None:
        st.session_state.tb_team_b  = result
        st.session_state.tb_hp_b    = [e["poke"]["hp"] for e in result]
        st.session_state.tb_active_a = 0
        st.session_state.tb_active_b = 0
        st.session_state.tb_phase   = "reveal"
        st.rerun()


def _phase_reveal():
    trainer_a = st.session_state.tb_trainer_a
    trainer_b = st.session_state.tb_trainer_b
    team_a    = st.session_state.tb_team_a
    team_b    = st.session_state.tb_team_b
    col_a     = TRAINER_COLORS.get(trainer_a, "#888")
    col_b     = TRAINER_COLORS.get(trainer_b, "#888")

    st.markdown('<div class="pokeball-header">⚡ TEAMS REVEALED! ⚡</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    ca, mid, cb = st.columns([5, 1, 5])

    for col, trainer, team, color in [(ca, trainer_a, team_a, col_a), (cb, trainer_b, team_b, col_b)]:
        with col:
            emoji = TRAINER_EMOJI.get(trainer, "🎮")
            st.markdown(
                f'<div style="text-align:center;border:2px solid {color};border-radius:12px;'
                f'padding:0.8rem;margin-bottom:0.5rem;">'
                f'<span style="font-size:1.8rem">{emoji}</span>'
                f'<div style="font-weight:700;color:{color};font-size:1rem;">{trainer}</div></div>',
                unsafe_allow_html=True
            )
            for entry in team:
                poke   = entry["poke"]
                sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{poke['id']}.png"
                types  = " ".join(type_badge_html(t) for t in poke["types"])
                lv     = poke.get("level","?")
                st.markdown(
                    f'<div class="pokemon-card" style="cursor:default;border-color:{color};margin-bottom:6px;">'
                    f'<img src="{sprite}" width="90" style="image-rendering:pixelated"/>'
                    f'<div style="font-weight:700;margin:4px 0;">{poke["name"]}</div>'
                    f'{types}'
                    f'<div style="font-size:0.7rem;color:var(--text-muted);margin-top:3px;">'
                    f'Lv.{lv} ❤️{poke["hp"]} ⚔️{poke["attack"]} ⚡{poke["speed"]}</div></div>',
                    unsafe_allow_html=True
                )

    with mid:
        st.markdown("<div style='text-align:center;font-size:2rem;padding-top:80px;'>VS</div>",
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Repick Teams", use_container_width=True):
            _reset()
            st.rerun()
    with c2:
        if st.button("⚔️ Begin Battle!", use_container_width=True):
            a1, a2 = team_a[0]["poke"]["name"], team_a[1]["poke"]["name"]
            b1, b2 = team_b[0]["poke"]["name"], team_b[1]["poke"]["name"]
            st.session_state.tb_phase = "battle"
            st.session_state.tb_log   = [
                f"🤝 {trainer_a} vs {trainer_b}!",
                f"{trainer_a} sent out {a1} & {a2}!",
                f"{trainer_b} sent out {b1} & {b2}!",
            ]
            st.rerun()


def _phase_battle():
    trainer_a = st.session_state.tb_trainer_a
    trainer_b = st.session_state.tb_trainer_b
    team_a    = st.session_state.tb_team_a
    team_b    = st.session_state.tb_team_b
    hp_a      = st.session_state.tb_hp_a
    hp_b      = st.session_state.tb_hp_b
    active_a  = st.session_state.tb_active_a
    active_b  = st.session_state.tb_active_b
    col_a     = TRAINER_COLORS.get(trainer_a, "#888")
    col_b     = TRAINER_COLORS.get(trainer_b, "#888")
    log       = st.session_state.tb_log

    st.markdown(f"### 🤝 {trainer_a} vs {trainer_b}")

    # ── 4-card battlefield ────────────────────────────────────────────────────
    st.markdown("#### 🏟️ Battlefield")
    ca1, ca2, mid, cb1, cb2 = st.columns([2,2,0.4,2,2])

    for i, (col, entry, hp) in enumerate(zip([ca1, ca2], team_a, hp_a)):
        with col:
            poke = entry["poke"]
            is_active = (i == active_a)
            fainted   = hp <= 0
            lbl = f"{trainer_a}" + (" 🟢" if is_active and not fainted else "")
            _poke_mini_card(poke, hp, lbl, fainted=fainted, color=col_a)

    with mid:
        st.markdown("<div style='text-align:center;font-size:1.5rem;padding-top:50px;'>⚔️</div>",
                    unsafe_allow_html=True)

    for i, (col, entry, hp) in enumerate(zip([cb1, cb2], team_b, hp_b)):
        with col:
            poke = entry["poke"]
            is_active = (i == active_b)
            fainted   = hp <= 0
            lbl = f"{trainer_b}" + (" 🔴" if is_active and not fainted else "")
            _poke_mini_card(poke, hp, lbl, fainted=fainted, color=col_b)

    # ── Switch active buttons ─────────────────────────────────────────────────
    sw1, sw2 = st.columns(2)
    alive_a = [i for i, h in enumerate(hp_a) if h > 0]
    alive_b = [i for i, h in enumerate(hp_b) if h > 0]
    with sw1:
        if len(alive_a) > 1:
            other_a = next(i for i in alive_a if i != active_a)
            if st.button(f"🔄 {trainer_a}: switch to {team_a[other_a]['poke']['name']}",
                         use_container_width=True):
                st.session_state.tb_active_a = other_a
                log.append(f"🔄 {trainer_a} switched to {team_a[other_a]['poke']['name']}!")
                st.rerun()
    with sw2:
        if len(alive_b) > 1:
            other_b = next(i for i in alive_b if i != active_b)
            if st.button(f"🔄 {trainer_b}: switch to {team_b[other_b]['poke']['name']}",
                         use_container_width=True):
                st.session_state.tb_active_b = other_b
                log.append(f"🔄 {trainer_b} switched to {team_b[other_b]['poke']['name']}!")
                st.rerun()

    st.markdown("---")

    # ── Move buttons — each trainer's 2 Pokémon ───────────────────────────────
    for trainer, team, hp_list, active_idx, opp_team, opp_hp, opp_active, hp_key, active_key, side \
        in [
            (trainer_a, team_a, hp_a, active_a, team_b, hp_b, active_b,
             "tb_hp_b", "tb_active_b", "a"),
            (trainer_b, team_b, hp_b, active_b, team_a, hp_a, active_a,
             "tb_hp_a", "tb_active_a", "b"),
        ]:
        color = TRAINER_COLORS.get(trainer, "#888")
        emoji = TRAINER_EMOJI.get(trainer, "🎮")
        st.markdown(
            f'<div style="border-left:4px solid {color};padding-left:10px;margin-bottom:4px;">'
            f'<b>{emoji} {trainer}\'s attacks</b></div>',
            unsafe_allow_html=True
        )

        for pi, (entry, hp) in enumerate(zip(team, hp_list)):
            poke = entry["poke"]
            if hp <= 0:
                st.markdown(f"~~{poke['name']}~~ 💀")
                continue
            is_active = (pi == active_idx)
            active_tag = " (active)" if is_active else ""
            st.markdown(f"**{poke['name']}{active_tag}:**")
            moves = entry["moves"] or []
            mcols = st.columns(2)
            for mi, move in enumerate(moves):
                acc   = move.get("accuracy") or 100
                pwr   = move.get("power") or "—"
                lbl   = f"{move['name']} ({move['type'].upper()}, {pwr} pwr, {acc}%)"
                with mcols[mi % 2]:
                    if st.button(lbl, key=f"tb_{side}_{pi}_{mi}", use_container_width=True):
                        opp_poke = opp_team[opp_active]["poke"]
                        cur_opp_hp = list(opp_hp)
                        cur_opp_hp = _attack(
                            poke, move, poke.get("level", 5),
                            opp_poke, cur_opp_hp, opp_active,
                            log, trainer, "opponent"
                        )
                        st.session_state[hp_key] = cur_opp_hp
                        # Auto-switch fainted active
                        new_active = _auto_switch(cur_opp_hp, opp_active)
                        if new_active != opp_active:
                            st.session_state[active_key] = new_active
                            opp_name = opp_team[new_active]["poke"]["name"]
                            log.append(f"🔄 {opp_team[opp_active]['poke']['name']} fainted — {opp_name} is up!")
                        # Set this Pokémon as active after attacking
                        if side == "a":
                            st.session_state.tb_active_a = pi
                        else:
                            st.session_state.tb_active_b = pi
                        # Check winner
                        winner = _check_winner()
                        if winner:
                            loser = trainer_b if winner == trainer_a else trainer_a
                            _record_result(winner, loser)
                            st.session_state.tb_winner = winner
                            st.session_state.tb_phase  = "result"
                        st.session_state.tb_log = log[-30:]
                        st.rerun()

    # ── Manual HP sliders ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🎛️ Manual HP Adjustment")
    sl_a, sl_b = st.columns(2)
    with sl_a:
        st.markdown(f"**{trainer_a}:**")
        for pi, (entry, hp) in enumerate(zip(team_a, hp_a)):
            poke = entry["poke"]
            new_hp = st.slider(poke["name"], 0, max(1, poke["hp"]),
                                max(0, min(hp, poke["hp"])), key=f"tb_sl_a_{pi}")
            if new_hp != hp:
                hp_a[pi] = new_hp
                st.session_state.tb_hp_a = hp_a
                if new_hp <= 0:
                    log.append(f"💥 {poke['name']} fainted!")
                winner = _check_winner()
                if winner:
                    loser = trainer_b if winner == trainer_a else trainer_a
                    _record_result(winner, loser)
                    st.session_state.tb_winner = winner
                    st.session_state.tb_phase  = "result"
                st.session_state.tb_log = log[-30:]
                st.rerun()
    with sl_b:
        st.markdown(f"**{trainer_b}:**")
        for pi, (entry, hp) in enumerate(zip(team_b, hp_b)):
            poke = entry["poke"]
            new_hp = st.slider(poke["name"], 0, max(1, poke["hp"]),
                                max(0, min(hp, poke["hp"])), key=f"tb_sl_b_{pi}")
            if new_hp != hp:
                hp_b[pi] = new_hp
                st.session_state.tb_hp_b = hp_b
                if new_hp <= 0:
                    log.append(f"💥 {poke['name']} fainted!")
                winner = _check_winner()
                if winner:
                    loser = trainer_b if winner == trainer_a else trainer_a
                    _record_result(winner, loser)
                    st.session_state.tb_winner = winner
                    st.session_state.tb_phase  = "result"
                st.session_state.tb_log = log[-30:]
                st.rerun()

    # ── Override buttons ──────────────────────────────────────────────────────
    st.markdown("---")
    ov1, ov2, ov3 = st.columns(3)
    with ov1:
        if st.button(f"🏆 {trainer_a} wins IRL!", use_container_width=True):
            _record_result(trainer_a, trainer_b)
            log.append(f"[OVERRIDE] {trainer_a} won!")
            st.session_state.tb_winner = trainer_a
            st.session_state.tb_phase  = "result"
            st.session_state.tb_log    = log[-30:]
            st.rerun()
    with ov2:
        if st.button(f"🏆 {trainer_b} wins IRL!", use_container_width=True):
            _record_result(trainer_b, trainer_a)
            log.append(f"[OVERRIDE] {trainer_b} won!")
            st.session_state.tb_winner = trainer_b
            st.session_state.tb_phase  = "result"
            st.session_state.tb_log    = log[-30:]
            st.rerun()
    with ov3:
        if st.button("❌ Cancel Battle", use_container_width=True):
            _reset()
            st.rerun()

    # ── Battle log ────────────────────────────────────────────────────────────
    if log:
        st.markdown("#### Battle Log")
        log_text = "\n".join(log[-15:])
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)


def _phase_result():
    winner    = st.session_state.tb_winner
    loser     = st.session_state.tb_trainer_b if winner == st.session_state.tb_trainer_a else st.session_state.tb_trainer_a
    col_w     = TRAINER_COLORS.get(winner, "#888")
    emoji_w   = TRAINER_EMOJI.get(winner, "🏆")

    st.markdown(f"""
    <div style="text-align:center;padding:2rem;
        background:linear-gradient(135deg,rgba(255,203,5,0.1),rgba(255,203,5,0.05));
        border:3px solid #FFCB05;border-radius:20px;margin-bottom:1rem;
        animation:pulse 1.5s infinite;">
        <div style="font-size:3rem">{emoji_w}</div>
        <div style="font-family:'Press Start 2P',monospace;font-size:1rem;
            color:#FFCB05;text-shadow:0 0 20px rgba(255,203,5,0.8);margin:0.5rem 0;">
            {winner.upper()} WINS!
        </div>
        <div style="font-size:0.85rem;color:var(--text-muted);">
            {loser} was defeated. Win recorded to standings!
        </div>
    </div>""", unsafe_allow_html=True)

    st.balloons()

    if st.session_state.tb_log:
        st.markdown("#### Battle Log")
        log_text = "\n".join(st.session_state.tb_log[-15:])
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 New Trainer Battle", use_container_width=True):
        _reset()
        st.rerun()


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    init_captures_csv()
    init_movesets_csv()
    _init()

    st.markdown("## 🤝 Trainer Battle")

    phase = st.session_state.tb_phase

    if phase == "setup":
        _phase_setup()
    elif phase == "pick_a":
        _phase_pick_a()
    elif phase == "pick_b":
        _phase_pick_b()
    elif phase == "reveal":
        _phase_reveal()
    elif phase == "battle":
        _phase_battle()
    elif phase == "result":
        _phase_result()
