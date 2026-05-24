import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import random
import streamlit as st
from utils.pokemon_api import fetch_pokemon, fetch_moves, type_badge_html
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.game_state import hp_percent, hp_bar_color, damage_calc

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

POOL_SIZE   = 6   # random pokemon shown to each trainer
PICK_COUNT  = 2   # how many each trainer picks
MIN_ATKS    = 2   # min moves with power >= 60
MIN_PWR     = 60


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _hp_bar(label, current, maximum):
    pct   = hp_percent(current, maximum)
    color = hp_bar_color(pct)
    st.markdown(
        f'<div style="margin-bottom:4px"><small>{label}: <b>{current}</b>/{maximum}</small>'
        f'<div class="hp-bar-wrap"><div class="hp-bar-fill" '
        f'style="width:{pct}%;background:{color};"></div></div></div>',
        unsafe_allow_html=True
    )


def _random_pool(size=POOL_SIZE) -> list[int]:
    """Return unique random Pokémon IDs from Gen 1–3 (1–386)."""
    return random.sample(range(1, 387), size)


def _balanced_moveset(pokemon_id: int) -> list[dict]:
    """
    Fetch moves for a Pokémon and return 4, guaranteeing at least MIN_ATKS
    have power >= MIN_PWR. Fills remaining slots with any available moves.
    """
    all_moves = fetch_moves(pokemon_id)
    if not all_moves:
        return [
            {"name": "Tackle",       "power": 40,  "type": "normal",   "accuracy": 100, "pp": 35},
            {"name": "Scratch",      "power": 40,  "type": "normal",   "accuracy": 100, "pp": 35},
            {"name": "Quick Attack", "power": 40,  "type": "normal",   "accuracy": 100, "pp": 30},
            {"name": "Leer",         "power": 0,   "type": "normal",   "accuracy": 100, "pp": 30},
        ]

    strong = [m for m in all_moves if (m.get("power") or 0) >= MIN_PWR]
    weak   = [m for m in all_moves if (m.get("power") or 0) <  MIN_PWR]

    random.shuffle(strong)
    random.shuffle(weak)

    # Guarantee MIN_ATKS strong moves, fill rest from weak
    chosen_strong = strong[:MIN_ATKS]
    needed_weak   = 4 - len(chosen_strong)
    # If not enough strong moves available, take what we can
    if len(strong) < MIN_ATKS:
        chosen_strong = strong[:]
        needed_weak   = 4 - len(chosen_strong)
    chosen_weak = weak[:needed_weak]

    moveset = chosen_strong + chosen_weak
    random.shuffle(moveset)
    return moveset[:4]


def _fetch_pool(ids: list[int]) -> list[dict]:
    """Fetch pokemon dicts for a list of IDs. Assigns level 50 for random battles."""
    pool = []
    for pid in ids:
        poke = fetch_pokemon(pid)
        poke["level"]  = 50
        poke["moves"]  = _balanced_moveset(pid)
        pool.append(poke)
    return pool


# ── Session state ─────────────────────────────────────────────────────────────

def _init():
    defaults = {
        "rb_phase":       "setup",      # setup|pick_a|pick_b|reveal|battle|result
        "rb_trainer_a":   None,
        "rb_trainer_b":   None,
        "rb_pool_a":      None,         # list of 6 poke dicts
        "rb_pool_b":      None,
        "rb_pick_a_sel":  [],           # list of selected poke names
        "rb_pick_b_sel":  [],
        "rb_team_a":      None,         # list of 2 {poke, moves}
        "rb_team_b":      None,
        "rb_hp_a":        [],
        "rb_hp_b":        [],
        "rb_active_a":    0,
        "rb_active_b":    0,
        "rb_log":         [],
        "rb_winner":      None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    keys = [k for k in st.session_state if k.startswith("rb_")]
    for k in keys:
        del st.session_state[k]


# ── Battle logic ──────────────────────────────────────────────────────────────

def _attack(attacker, move, opp, opp_hp_list, opp_idx, log):
    dmg, hit = damage_calc(attacker, opp, move, attacker.get("level", 50))
    acc = move.get("accuracy") or 100
    if not hit:
        log.append(f"➤ {attacker['name']} used {move['name']}... missed! ({acc}% acc)")
    else:
        opp_hp_list[opp_idx] = max(0, opp_hp_list[opp_idx] - dmg)
        log.append(f"➤ {attacker['name']} used {move['name']}! ({dmg} dmg, {acc}% acc)")
        if opp_hp_list[opp_idx] <= 0:
            log.append(f"💥 {opp['name']} fainted!")
    return opp_hp_list


def _check_winner():
    if all(h <= 0 for h in st.session_state.rb_hp_a):
        return st.session_state.rb_trainer_b
    if all(h <= 0 for h in st.session_state.rb_hp_b):
        return st.session_state.rb_trainer_a
    return None


def _auto_switch(hp_list, active_idx):
    if hp_list[active_idx] <= 0:
        for i, h in enumerate(hp_list):
            if h > 0:
                return i
    return active_idx


def _record_result(winner, loser):
    df = load_teams()
    for trainer, result in [(winner, "win"), (loser, "loss")]:
        row = df[df["trainer"] == trainer]
        if len(row):
            wins   = _safe_int(row.iloc[0]["wins"])   + (1 if result == "win"  else 0)
            losses = _safe_int(row.iloc[0]["losses"]) + (1 if result == "loss" else 0)
            df = update_trainer(df, trainer, wins=wins, losses=losses)
    save_teams(df)


# ── Pokemon card ──────────────────────────────────────────────────────────────

def _poke_card(poke, hp, label, fainted=False, color="#3D7DCA", show_moves=False):
    sprite  = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master/"
               f"sprites/pokemon/{poke['id']}.png")
    types   = " ".join(type_badge_html(t) for t in poke["types"])
    opacity = "0.3" if fainted else "1"
    faint_b = '<div style="color:#F44336;font-size:0.65rem;font-weight:700;">💀 FAINTED</div>' if fainted else ""
    spd     = poke.get("speed", "?")

    st.markdown(
        f'<div class="pokemon-card" style="cursor:default;opacity:{opacity};border-color:{color};">'
        f'<div style="font-size:0.65rem;color:var(--text-muted);">{label}</div>'
        f'<img src="{sprite}" width="80" style="image-rendering:pixelated"/>'
        f'<div style="font-size:0.8rem;font-weight:700;margin:3px 0;">#{poke["id"]} {poke["name"]}</div>'
        f'{types}'
        f'<div style="font-size:0.62rem;color:var(--text-muted);margin-top:3px;">'
        f'Lv.50 ❤️{poke["hp"]} ⚔️{poke["attack"]} 🛡️{poke["defense"]} ⚡{spd}</div>'
        f'{faint_b}</div>',
        unsafe_allow_html=True
    )
    if not fainted:
        _hp_bar("HP", hp, poke["hp"])


# ── Phase: setup ──────────────────────────────────────────────────────────────

def _phase_setup():
    st.markdown("### 🎲 Random Battle Setup")
    st.markdown(
        "<small style='color:var(--text-muted)'>Each trainer receives **6 random Pokémon** at Lv.50 "
        "with balanced random movesets (at least 2 moves with 60+ power). "
        "Pick 2 to battle — picks are hidden from the other trainer!</small>",
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        trainer_a = st.selectbox("Trainer 1", TRAINERS, key="rb_sel_a")
    with col2:
        remaining = [t for t in TRAINERS if t != trainer_a]
        trainer_b = st.selectbox("Trainer 2", remaining, key="rb_sel_b")

    col_a = TRAINER_COLORS.get(trainer_a, "#888")
    col_b = TRAINER_COLORS.get(trainer_b, "#888")

    st.markdown(f"""
    <div style="display:flex;gap:1rem;justify-content:center;margin:1.2rem 0;">
        <div style="text-align:center;padding:1rem 2rem;background:linear-gradient(145deg,#1e2a4a,#0f1a35);
            border:2px solid {col_a};border-radius:12px;">
            <div style="font-size:2rem">{TRAINER_EMOJI.get(trainer_a,'🎮')}</div>
            <div style="font-weight:700;color:{col_a};">{trainer_a}</div>
        </div>
        <div style="font-size:2rem;display:flex;align-items:center;color:var(--poke-yellow);">VS</div>
        <div style="text-align:center;padding:1rem 2rem;background:linear-gradient(145deg,#1e2a4a,#0f1a35);
            border:2px solid {col_b};border-radius:12px;">
            <div style="font-size:2rem">{TRAINER_EMOJI.get(trainer_b,'🎮')}</div>
            <div style="font-weight:700;color:{col_b};">{trainer_b}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("""
    <div style="background:rgba(0,0,0,0.3);border:1px solid var(--poke-blue);
        border-radius:10px;padding:1rem;font-size:0.82rem;color:var(--text-muted);margin-bottom:1rem;">
        🎲 <b>How random battles work:</b><br>
        1. Each trainer gets 6 random Pokémon (different pools)<br>
        2. Each picks 2 of their 6 in secret<br>
        3. Teams are revealed — battle begins at Lv.50!
    </div>""", unsafe_allow_html=True)

    if st.button("🎲 Roll the Pokémon & Start!", use_container_width=True):
        with st.spinner("Rolling random Pokémon..."):
            pool_ids_a = _random_pool()
            pool_ids_b = _random_pool()
            pool_a = _fetch_pool(pool_ids_a)
            pool_b = _fetch_pool(pool_ids_b)

        st.session_state.rb_trainer_a  = trainer_a
        st.session_state.rb_trainer_b  = trainer_b
        st.session_state.rb_pool_a     = pool_a
        st.session_state.rb_pool_b     = pool_b
        st.session_state.rb_pick_a_sel = []
        st.session_state.rb_pick_b_sel = []
        st.session_state.rb_phase      = "pick_a"
        st.rerun()


# ── Phase: pick (shared for both trainers) ────────────────────────────────────

def _pick_screen(trainer: str, other: str, pool: list[dict], sel_key: str):
    color = TRAINER_COLORS.get(trainer, "#888")
    emoji = TRAINER_EMOJI.get(trainer, "🎮")
    selected = st.session_state[sel_key]

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,rgba(30,40,70,0.95),rgba(15,25,50,0.95));
        border:2px solid {color};border-radius:16px;padding:1.5rem;margin-bottom:1rem;text-align:center;">
        <div style="font-size:2.5rem">{emoji}</div>
        <div style="font-family:'Press Start 2P',monospace;font-size:0.75rem;color:{color};margin:6px 0;">
            {trainer.upper()}'S PICKS
        </div>
        <div style="font-size:0.8rem;color:var(--text-muted);">
            📵 Only <b>{trainer}</b> should be looking! {other}'s pool is hidden.
        </div>
    </div>""", unsafe_allow_html=True)

    st.info(f"🔒 Pass the device to **{trainer}** now. Choose 2 from your 6 random Pokémon!")

    st.markdown(f"### Your 6 Random Pokémon — pick {PICK_COUNT}")

    cols_per_row = 3
    for row_start in range(0, len(pool), cols_per_row):
        chunk = pool[row_start:row_start + cols_per_row]
        cols  = st.columns(cols_per_row)
        for col, poke in zip(cols, chunk):
            is_sel = poke["name"] in selected
            border = f"2px solid {color}" if is_sel else "2px solid var(--poke-blue)"
            bg     = "linear-gradient(145deg,#2a3a0f,#1a2a05)" if is_sel else "linear-gradient(145deg,#1e2a4a,#0f1a35)"
            sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{poke['id']}.png"
            types_html = " ".join(type_badge_html(t) for t in poke["types"])
            moves  = poke.get("moves", [])
            # Show move summary inline
            move_lines = ""
            for m in moves:
                pwr = m.get("power") or 0
                pwr_col = "#4CAF50" if pwr >= MIN_PWR else "#aaa"
                tc  = TYPE_COLORS.get(m.get("type","normal"), "#888")
                move_lines += (
                    f'<div style="display:flex;gap:4px;align-items:center;font-size:0.58rem;margin:1px 0;">'
                    f'<span style="background:{tc};border-radius:3px;padding:0 4px;color:#fff;">{m.get("type","?")}</span>'
                    f'<span>{m["name"]}</span>'
                    f'<span style="color:{pwr_col};margin-left:auto;">{pwr if pwr else "—"}pwr</span>'
                    f'</div>'
                )

            with col:
                sel_badge = '<div style="color:#FFCB05;font-size:0.7rem;margin-top:4px;">✅ Selected</div>' if is_sel else ''
                st.markdown(
                    f'<div style="background:{bg};border:{border};border-radius:14px;'
                    f'padding:0.7rem;text-align:center;margin-bottom:4px;">'
                    f'<img src="{sprite}" width="65" style="image-rendering:pixelated"/>'
                    f'<div style="font-size:0.75rem;font-weight:700;margin:3px 0;">#{poke["id"]} {poke["name"]}</div>'
                    f'{types_html}'
                    f'<div style="font-size:0.62rem;color:var(--text-muted);margin:3px 0;">'
                    f'❤️{poke["hp"]} ⚔️{poke["attack"]} ⚡{poke.get("speed","?")}</div>'
                    f'<div style="border-top:1px solid rgba(255,255,255,0.08);padding-top:4px;margin-top:4px;text-align:left;">'
                    f'{move_lines}</div>'
                    + sel_badge +
                    '</div>',
                    unsafe_allow_html=True
                )
                if is_sel:
                    if st.button("Deselect", key=f"{sel_key}_d_{poke['id']}", use_container_width=True):
                        st.session_state[sel_key] = [n for n in selected if n != poke["name"]]
                        st.rerun()
                else:
                    if st.button("Select", key=f"{sel_key}_s_{poke['id']}",
                                 use_container_width=True, disabled=len(selected) >= PICK_COUNT):
                        st.session_state[sel_key] = selected + [poke["name"]]
                        st.rerun()

    st.markdown(f"**Selected {len(selected)}/{PICK_COUNT}:** {', '.join(selected) if selected else 'None'}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Cancel", use_container_width=True):
            _reset()
            st.rerun()
    with c2:
        if st.button(f"✅ Lock In {trainer}'s Team",
                     use_container_width=True, disabled=len(selected) < PICK_COUNT):
            chosen = [p for p in pool if p["name"] in selected][:PICK_COUNT]
            return chosen
    return None


def _phase_pick_a():
    pool = st.session_state.rb_pool_a
    result = _pick_screen(
        st.session_state.rb_trainer_a,
        st.session_state.rb_trainer_b,
        pool, "rb_pick_a_sel"
    )
    if result is not None:
        st.session_state.rb_team_a = [{"poke": p, "moves": p["moves"]} for p in result]
        st.session_state.rb_hp_a   = [p["hp"] for p in result]
        st.session_state.rb_phase  = "pick_b"
        st.session_state.rb_pick_b_sel = []
        st.rerun()


def _phase_pick_b():
    trainer_a = st.session_state.rb_trainer_a
    trainer_b = st.session_state.rb_trainer_b
    col_b     = TRAINER_COLORS.get(trainer_b, "#888")

    st.markdown(f"""
    <div style="background:rgba(0,0,0,0.6);border:2px solid #FFCB05;
        border-radius:16px;padding:2rem;text-align:center;margin-bottom:1rem;">
        <div style="font-size:2rem">🔒</div>
        <div style="font-family:'Press Start 2P',monospace;font-size:0.7rem;color:#FFCB05;margin:8px 0;">
            {trainer_a.upper()} LOCKED IN!
        </div>
        <div style="font-size:0.85rem;color:var(--text-muted);">
            Pass the device to <b style="color:{col_b}">{trainer_b}</b>.<br>
            Don't let {trainer_b} see {trainer_a}'s picks!
        </div>
    </div>""", unsafe_allow_html=True)

    pool = st.session_state.rb_pool_b
    result = _pick_screen(trainer_b, trainer_a, pool, "rb_pick_b_sel")
    if result is not None:
        st.session_state.rb_team_b  = [{"poke": p, "moves": p["moves"]} for p in result]
        st.session_state.rb_hp_b    = [p["hp"] for p in result]
        st.session_state.rb_active_a = 0
        st.session_state.rb_active_b = 0
        st.session_state.rb_phase    = "reveal"
        st.rerun()


# ── Phase: reveal ─────────────────────────────────────────────────────────────

def _phase_reveal():
    trainer_a = st.session_state.rb_trainer_a
    trainer_b = st.session_state.rb_trainer_b
    team_a    = st.session_state.rb_team_a
    team_b    = st.session_state.rb_team_b
    col_a     = TRAINER_COLORS.get(trainer_a, "#888")
    col_b     = TRAINER_COLORS.get(trainer_b, "#888")

    st.markdown('<div class="pokeball-header">🎲 RANDOM BATTLE — TEAMS REVEALED! 🎲</div>',
                unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    ca, mid, cb = st.columns([5, 1, 5])

    for col, trainer, team, color in [
        (ca, trainer_a, team_a, col_a),
        (cb, trainer_b, team_b, col_b),
    ]:
        with col:
            emoji = TRAINER_EMOJI.get(trainer, "🎮")
            st.markdown(
                f'<div style="text-align:center;border:2px solid {color};'
                f'border-radius:12px;padding:0.8rem;margin-bottom:0.8rem;">'
                f'<span style="font-size:1.8rem">{emoji}</span>'
                f'<div style="font-weight:700;color:{color};font-size:1rem;">{trainer}</div></div>',
                unsafe_allow_html=True
            )
            for entry in team:
                poke   = entry["poke"]
                moves  = entry["moves"]
                sprite = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master/"
                          f"sprites/pokemon/other/official-artwork/{poke['id']}.png")
                types  = " ".join(type_badge_html(t) for t in poke["types"])
                move_rows = ""
                for m in moves:
                    pwr = m.get("power") or 0
                    tc  = TYPE_COLORS.get(m.get("type","normal"), "#888")
                    pwr_col = "#4CAF50" if pwr >= MIN_PWR else "#aaa"
                    move_rows += (
                        f'<tr>'
                        f'<td style="padding:2px 6px;font-size:0.7rem;font-weight:600;">{m["name"]}</td>'
                        f'<td><span class="type-badge" style="background:{tc};font-size:0.55rem;">{m.get("type","?")}</span></td>'
                        f'<td style="font-size:0.7rem;color:{pwr_col};padding:2px 4px;">{pwr if pwr else "—"}</td>'
                        f'<td style="font-size:0.7rem;color:var(--text-muted);padding:2px 4px;">{m.get("accuracy",100)}%</td>'
                        f'</tr>'
                    )
                st.markdown(
                    f'<div class="pokemon-card" style="cursor:default;border-color:{color};margin-bottom:8px;">'
                    f'<img src="{sprite}" width="90" style="image-rendering:pixelated"/>'
                    f'<div style="font-weight:700;margin:4px 0;">{poke["name"]}</div>'
                    f'{types}'
                    f'<div style="font-size:0.65rem;color:var(--text-muted);margin:3px 0;">'
                    f'Lv.50 ❤️{poke["hp"]} ⚔️{poke["attack"]} ⚡{poke.get("speed","?")}</div>'
                    f'<table style="width:100%;border-collapse:collapse;margin-top:4px;">'
                    f'<tbody>{move_rows}</tbody></table></div>',
                    unsafe_allow_html=True
                )

    with mid:
        st.markdown("<div style='text-align:center;font-size:2rem;padding-top:80px;'>VS</div>",
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Repick", use_container_width=True):
            _reset()
            st.rerun()
    with c2:
        if st.button("⚔️ Begin Random Battle!", use_container_width=True):
            a1 = team_a[0]["poke"]["name"]
            a2 = team_a[1]["poke"]["name"]
            b1 = team_b[0]["poke"]["name"]
            b2 = team_b[1]["poke"]["name"]
            st.session_state.rb_phase = "battle"
            st.session_state.rb_log   = [
                f"🎲 Random Battle: {trainer_a} vs {trainer_b}!",
                f"{trainer_a} sent out {a1} & {a2}!",
                f"{trainer_b} sent out {b1} & {b2}!",
            ]
            st.rerun()


# ── Phase: battle ─────────────────────────────────────────────────────────────

def _phase_battle():
    trainer_a = st.session_state.rb_trainer_a
    trainer_b = st.session_state.rb_trainer_b
    team_a    = st.session_state.rb_team_a
    team_b    = st.session_state.rb_team_b
    hp_a      = st.session_state.rb_hp_a
    hp_b      = st.session_state.rb_hp_b
    active_a  = st.session_state.rb_active_a
    active_b  = st.session_state.rb_active_b
    col_a     = TRAINER_COLORS.get(trainer_a, "#888")
    col_b     = TRAINER_COLORS.get(trainer_b, "#888")
    log       = st.session_state.rb_log

    st.markdown(f"### 🎲 {trainer_a} vs {trainer_b} — Random Battle")

    # ── Battlefield ───────────────────────────────────────────────────────────
    st.markdown("#### 🏟️ Battlefield")
    ca1, ca2, mid, cb1, cb2 = st.columns([2,2,0.4,2,2])

    for i, (col, entry, hp, color, trainer) in enumerate([
        (ca1, team_a[0], hp_a[0], col_a, trainer_a),
        (ca2, team_a[1], hp_a[1], col_a, trainer_a),
    ]):
        with col:
            poke = entry["poke"]
            is_active = (i == active_a)
            tag = f"{trainer}" + (" 🟢" if is_active and hp > 0 else "")
            _poke_card(poke, hp, tag, fainted=hp<=0, color=col_a)

    with mid:
        st.markdown("<div style='text-align:center;font-size:1.5rem;padding-top:50px;'>⚔️</div>",
                    unsafe_allow_html=True)

    for i, (col, entry, hp) in enumerate([
        (cb1, team_b[0], hp_b[0]),
        (cb2, team_b[1], hp_b[1]),
    ]):
        with col:
            poke = entry["poke"]
            is_active = (i == active_b)
            tag = f"{trainer_b}" + (" 🔴" if is_active and hp > 0 else "")
            _poke_card(poke, hp, tag, fainted=hp<=0, color=col_b)

    # ── Switch active ─────────────────────────────────────────────────────────
    sw1, sw2 = st.columns(2)
    alive_a = [i for i, h in enumerate(hp_a) if h > 0]
    alive_b = [i for i, h in enumerate(hp_b) if h > 0]
    with sw1:
        if len(alive_a) > 1:
            oa = next(i for i in alive_a if i != active_a)
            if st.button(f"🔄 {trainer_a}: switch to {team_a[oa]['poke']['name']}",
                         use_container_width=True):
                st.session_state.rb_active_a = oa
                log.append(f"🔄 {trainer_a} switched to {team_a[oa]['poke']['name']}!")
                st.rerun()
    with sw2:
        if len(alive_b) > 1:
            ob = next(i for i in alive_b if i != active_b)
            if st.button(f"🔄 {trainer_b}: switch to {team_b[ob]['poke']['name']}",
                         use_container_width=True):
                st.session_state.rb_active_b = ob
                log.append(f"🔄 {trainer_b} switched to {team_b[ob]['poke']['name']}!")
                st.rerun()

    st.markdown("---")

    # ── Move buttons ──────────────────────────────────────────────────────────
    for trainer, team, hp_list, active_idx, opp_team, opp_hp, opp_active, \
        hp_key, active_key, side in [
        (trainer_a, team_a, hp_a, active_a, team_b, hp_b, active_b,
         "rb_hp_b", "rb_active_b", "a"),
        (trainer_b, team_b, hp_b, active_b, team_a, hp_a, active_a,
         "rb_hp_a", "rb_active_a", "b"),
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
                acc = move.get("accuracy") or 100
                pwr = move.get("power") or "—"
                lbl = f"{move['name']} ({move['type'].upper()}, {pwr} pwr, {acc}%)"
                with mcols[mi % 2]:
                    if st.button(lbl, key=f"rb_{side}_{pi}_{mi}", use_container_width=True):
                        opp_poke   = opp_team[opp_active]["poke"]
                        cur_opp_hp = list(opp_hp)
                        cur_opp_hp = _attack(poke, move, opp_poke, cur_opp_hp, opp_active, log)
                        st.session_state[hp_key] = cur_opp_hp
                        new_opp_active = _auto_switch(cur_opp_hp, opp_active)
                        if new_opp_active != opp_active:
                            st.session_state[active_key] = new_opp_active
                            log.append(f"🔄 {opp_team[new_opp_active]['poke']['name']} is now up!")
                        if side == "a":
                            st.session_state.rb_active_a = pi
                        else:
                            st.session_state.rb_active_b = pi
                        winner = _check_winner()
                        if winner:
                            loser = trainer_b if winner == trainer_a else trainer_a
                            _record_result(winner, loser)
                            st.session_state.rb_winner = winner
                            st.session_state.rb_phase  = "result"
                        st.session_state.rb_log = log[-30:]
                        st.rerun()

    # ── HP sliders ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🎛️ Manual HP Adjustment")
    sl_a, sl_b = st.columns(2)
    for col, trainer, team, hp_list, hp_key in [
        (sl_a, trainer_a, team_a, hp_a, "rb_hp_a"),
        (sl_b, trainer_b, team_b, hp_b, "rb_hp_b"),
    ]:
        with col:
            st.markdown(f"**{trainer}:**")
            cur_hp = list(hp_list)
            changed = False
            for pi, (entry, hp) in enumerate(zip(team, cur_hp)):
                poke = entry["poke"]
                new_hp = st.slider(poke["name"], 0, max(1, poke["hp"]),
                                   max(0, min(hp, poke["hp"])),
                                   key=f"rb_sl_{hp_key}_{pi}")
                if new_hp != hp:
                    cur_hp[pi] = new_hp
                    changed = True
                    if new_hp <= 0:
                        log.append(f"💥 {poke['name']} fainted!")
            if changed:
                st.session_state[hp_key] = cur_hp
                winner = _check_winner()
                if winner:
                    loser = trainer_b if winner == trainer_a else trainer_a
                    _record_result(winner, loser)
                    st.session_state.rb_winner = winner
                    st.session_state.rb_phase  = "result"
                st.session_state.rb_log = log[-30:]
                st.rerun()

    # ── Override / cancel ─────────────────────────────────────────────────────
    st.markdown("---")
    ov1, ov2, ov3 = st.columns(3)
    with ov1:
        if st.button(f"🏆 {trainer_a} wins IRL!", use_container_width=True):
            _record_result(trainer_a, trainer_b)
            log.append(f"[OVERRIDE] {trainer_a} won!")
            st.session_state.rb_winner = trainer_a
            st.session_state.rb_phase  = "result"
            st.session_state.rb_log    = log[-30:]
            st.rerun()
    with ov2:
        if st.button(f"🏆 {trainer_b} wins IRL!", use_container_width=True):
            _record_result(trainer_b, trainer_a)
            log.append(f"[OVERRIDE] {trainer_b} won!")
            st.session_state.rb_winner = trainer_b
            st.session_state.rb_phase  = "result"
            st.session_state.rb_log    = log[-30:]
            st.rerun()
    with ov3:
        if st.button("❌ Cancel", use_container_width=True):
            _reset()
            st.rerun()

    if log:
        st.markdown("#### Battle Log")
        st.markdown(f'<div class="battle-log">{chr(10).join(log[-15:])}</div>',
                    unsafe_allow_html=True)


# ── Phase: result ─────────────────────────────────────────────────────────────

def _phase_result():
    winner  = st.session_state.rb_winner
    loser   = (st.session_state.rb_trainer_b
               if winner == st.session_state.rb_trainer_a
               else st.session_state.rb_trainer_a)
    emoji_w = TRAINER_EMOJI.get(winner, "🏆")
    col_w   = TRAINER_COLORS.get(winner, "#FFCB05")

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
            🎲 Random Battle complete! {loser} was defeated.
        </div>
    </div>""", unsafe_allow_html=True)

    st.balloons()

    if st.session_state.rb_log:
        st.markdown("#### Battle Log")
        st.markdown(
            f'<div class="battle-log">{chr(10).join(st.session_state.rb_log[-15:])}</div>',
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🎲 New Random Battle", use_container_width=True):
        _reset()
        st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────

def render():
    _init()
    st.markdown("## 🎲 Random Battle")

    phase = st.session_state.rb_phase

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
