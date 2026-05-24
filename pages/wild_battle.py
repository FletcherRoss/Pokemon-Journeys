import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import random
import streamlit as st
from utils.pokemon_api import get_random_wild, fetch_moves, fetch_pokemon, type_badge_html
from utils.csv_manager import load_teams, save_teams, update_trainer
from utils.captures_manager import (
    add_capture, get_capture_count, load_captures, init_captures_csv, level_up_team
)
from utils.game_state import (
    hp_percent, hp_bar_color, damage_calc, speed_order, reset_battle, level_up_check
)

CAPTURE_THRESHOLD = 10

TYPE_COLORS = {
    "fire":"#F08030","water":"#6890F0","grass":"#78C850","electric":"#F8D030",
    "psychic":"#F85888","ice":"#98D8D8","dragon":"#7038F8","dark":"#705848",
    "normal":"#A8A878","fighting":"#C03028","poison":"#A040A0","ground":"#E0C068",
    "flying":"#A890F0","bug":"#A8B820","rock":"#B8A038","ghost":"#705898",
    "steel":"#B8B8D0","fairy":"#EE99AC",
}


# ── Guards & helpers ──────────────────────────────────────────────────────────

def _guard() -> bool:
    if not st.session_state.trainer_name:
        st.warning("⚠️ Choose a trainer on the Home page first!")
        return False
    if not st.session_state.get("my_pokemon"):
        st.warning("⚠️ Choose your starter Pokémon on the Home page first!")
        return False
    return True


def _hp_bar(label: str, current: int, maximum: int):
    pct   = hp_percent(current, maximum)
    color = hp_bar_color(pct)
    st.markdown(f"""
    <div style="margin-bottom:4px">
        <small>{label}: <b>{current}</b>/{maximum}</small>
        <div class="hp-bar-wrap">
            <div class="hp-bar-fill" style="width:{pct}%;background:{color};"></div>
        </div>
    </div>""", unsafe_allow_html=True)


def _show_pokemon_card(poke: dict, current_hp: int, label: str, animated: bool = False):
    sprite     = poke.get("sprite_anim") if animated else poke.get("sprite")
    types_html = " ".join(type_badge_html(t) for t in poke["types"])
    spd = poke.get("speed", "?")
    st.markdown(f"""
    <div class="pokemon-card" style="cursor:default;">
        <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:4px">{label}</div>
        <img src="{sprite}" width="120" style="image-rendering:pixelated"/>
        <div style="font-weight:700;margin:4px 0;">{poke['name']}</div>
        {types_html}
        <div style="font-size:0.72rem;color:var(--text-muted);margin-top:5px;">
            ⚡ Speed: <b style="color:#F8D030;">{spd}</b>
        </div>
    </div>""", unsafe_allow_html=True)
    _hp_bar("HP", current_hp, poke["hp"])


# ── Team switcher ─────────────────────────────────────────────────────────────

def _build_team_roster(trainer: str) -> list[dict]:
    """Return list of {label, poke_dict, moves} for starter + all captures."""
    roster = []

    # Starter
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
            moves = fetch_moves(sid)
            roster.append({
                "label":   f"⭐ {poke['name']} (Starter, Lv.{slv})",
                "poke":    poke,
                "moves":   moves,
                "is_starter": True,
                "cap_idx": None,
            })

    # Captured Pokémon
    trainer_caps = get_active_captures(trainer)
    for idx, cap in trainer_caps.iterrows():
        try:
            pid = int(float(cap["pokemon_id"]))
            lv  = int(float(cap.get("current_level") or cap.get("level_caught") or 5))
        except (ValueError, TypeError):
            continue
        poke = fetch_pokemon(pid)
        poke["level"] = lv
        moves = fetch_moves(pid)
        roster.append({
            "label":      f"⚾ {poke['name']} (Lv.{lv})",
            "poke":       poke,
            "moves":      moves,
            "is_starter": False,
            "cap_idx":    idx,
        })

    return roster


def _render_team_switcher(trainer: str):
    """Expander shown during battle to swap the active Pokémon."""
    roster = _build_team_roster(trainer)
    if len(roster) <= 1:
        return  # nothing to switch to

    current_name = st.session_state.my_pokemon.get("name", "")

    with st.expander("🔄 Switch Pokémon"):
        st.markdown(
            "<small style='color:var(--text-muted)'>Choose a Pokémon from your team to send into battle.</small>",
            unsafe_allow_html=True,
        )
        cols_per_row = 3
        entries = [r for r in roster if r["poke"]["name"] != current_name]

        for row_start in range(0, len(entries), cols_per_row):
            chunk = entries[row_start:row_start + cols_per_row]
            cols  = st.columns(cols_per_row)
            for col, entry in zip(cols, chunk):
                poke = entry["poke"]
                lv   = poke.get("level", 5)
                sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{poke['id']}.png"
                type_badges = "".join(
                    f'<span class="type-badge" style="background:{TYPE_COLORS.get(t,"#888")};font-size:0.55rem;">{t}</span>'
                    for t in poke["types"]
                )
                with col:
                    st.markdown(f"""
                    <div class="pokemon-card" style="cursor:default;padding:0.6rem;">
                        <img src="{sprite}" width="60" style="image-rendering:pixelated"/>
                        <div style="font-size:0.75rem;font-weight:700;margin:2px 0;">{poke['name']}</div>
                        {type_badges}
                        <div style="font-size:0.65rem;color:var(--text-muted);margin-top:3px;">Lv.{lv}</div>
                    </div>""", unsafe_allow_html=True)
                    if st.button(f"Send out!", key=f"switch_{poke['id']}_{row_start}", use_container_width=True):
                        _switch_active_pokemon(entry)
                        st.rerun()


def _switch_active_pokemon(entry: dict):
    """Swap the active battler to the chosen roster entry."""
    poke  = entry["poke"]
    moves = entry["moves"]
    log   = st.session_state.battle_log

    # Save old pokemon HP back if needed — just swap, keep opp HP intact
    log.append(f"🔄 Go, {poke['name']}!")

    st.session_state.my_pokemon    = poke
    st.session_state.my_moves      = moves
    st.session_state.my_max_hp     = poke["hp"]
    st.session_state.my_current_hp = poke["hp"]
    st.session_state.my_level      = poke.get("level", 5)
    st.session_state.battle_log    = log[-20:]


# ── Battle logic ──────────────────────────────────────────────────────────────

def _start_encounter():
    wild  = get_random_wild()
    moves = fetch_moves(wild["id"])
    st.session_state.opponent_pokemon    = wild
    st.session_state.opponent_moves      = moves
    st.session_state.opponent_max_hp     = wild["hp"]
    st.session_state.opponent_current_hp = wild["hp"]
    st.session_state.battle_active       = True
    st.session_state.battle_result       = None
    st.session_state.battle_log          = [f"A wild {wild['name']} appeared!"]
    st.session_state.battle_turn         = 0
    st.session_state.capture_pending     = False
    st.session_state.capture_result      = None
    st.session_state.d20_roll            = None


def _player_attack(move: dict):
    my  = st.session_state.my_pokemon
    opp = st.session_state.opponent_pokemon
    log = st.session_state.battle_log

    # Determine turn order based on speed
    player_first, my_spd, opp_spd = speed_order(my, opp)
    if my_spd == opp_spd:
        log.append(f"⚡ Equal speed ({my_spd}) — turn order randomised!")
    elif player_first:
        log.append(f"⚡ {my['name']} is faster ({my_spd} vs {opp_spd}) — you go first!")
    else:
        log.append(f"⚡ {opp['name']} is faster ({opp_spd} vs {my_spd}) — opponent goes first!")

    def do_player_turn():
        dmg, hit = damage_calc(my, opp, move, st.session_state.my_level)
        if not hit:
            log.append(f"➤ {my['name']} used {move['name']}... but it missed! (Acc:{move.get('accuracy',100)}%)")
            return False
        st.session_state.opponent_current_hp = max(0, st.session_state.opponent_current_hp - dmg)
        log.append(f"➤ {my['name']} used {move['name']}! ({dmg} dmg, Acc:{move.get('accuracy',100)}%)")
        return st.session_state.opponent_current_hp <= 0

    def do_opp_turn():
        opp_move = random.choice(st.session_state.opponent_moves)
        opp_dmg, opp_hit = damage_calc(opp, my, opp_move)
        if not opp_hit:
            log.append(f"➤ {opp['name']} used {opp_move['name']}... but it missed! (Acc:{opp_move.get('accuracy',100)}%)")
            return False
        st.session_state.my_current_hp = max(0, st.session_state.my_current_hp - opp_dmg)
        log.append(f"➤ {opp['name']} used {opp_move['name']}! ({opp_dmg} dmg, Acc:{opp_move.get('accuracy',100)}%)")
        return st.session_state.my_current_hp <= 0

    if player_first:
        opp_fainted = do_player_turn()
        if opp_fainted:
            xp_gain = random.randint(15, 35)
            st.session_state.my_xp += xp_gain
            leveled = level_up_check()
            log.append(f"💥 Wild {opp['name']} fainted! +{xp_gain} XP")
            if leveled:
                log.append(f"⬆️ {my['name']} grew to level {st.session_state.my_level}!")
            st.session_state.battle_result = "win"
            st.session_state.battle_active = False
            _record_result("win")
            st.session_state.battle_log = log[-20:]
            return
        my_fainted = do_opp_turn()
    else:
        my_fainted = do_opp_turn()
        if not my_fainted:
            opp_fainted = do_player_turn()
            if opp_fainted:
                xp_gain = random.randint(15, 35)
                st.session_state.my_xp += xp_gain
                leveled = level_up_check()
                log.append(f"💥 Wild {opp['name']} fainted! +{xp_gain} XP")
                if leveled:
                    log.append(f"⬆️ {my['name']} grew to level {st.session_state.my_level}!")
                st.session_state.battle_result = "win"
                st.session_state.battle_active = False
                _record_result("win")
                st.session_state.battle_log = log[-20:]
                return
        else:
            my_fainted = True

    if my_fainted or st.session_state.my_current_hp <= 0:
        log.append(f"💀 {my['name']} fainted...")
        st.session_state.battle_result = "lose"
        st.session_state.battle_active = False
        _record_result("lose")

    st.session_state.battle_turn += 1
    st.session_state.battle_log = log[-20:]


def _record_result(result: str):
    trainer = st.session_state.trainer_name
    df = load_teams()
    row = df[df["trainer"] == trainer]
    if len(row):
        wins   = int(row.iloc[0]["wins"])   + (1 if result == "win"  else 0)
        losses = int(row.iloc[0]["losses"]) + (1 if result == "lose" else 0)
        level  = st.session_state.my_level
        df = update_trainer(df, trainer, wins=wins, losses=losses, level=level)
        save_teams(df)
    if result == "win":
        lv_msgs = level_up_team(trainer, amount=1)
        log = st.session_state.get("battle_log", [])
        log.extend(lv_msgs)
        st.session_state.battle_log = log[-20:]
        # Sync starter level to session
        from utils.csv_manager import load_teams as _lt
        r2 = _lt()[_lt()["trainer"] == trainer]
        if len(r2):
            st.session_state.my_level = int(float(r2.iloc[0].get("level", 5) or 5))
    if result == "lose":
        st.session_state.my_current_hp = max(1, st.session_state.my_max_hp // 5)


def _try_evolve():
    from utils.pokemon_api import get_evolution
    poke    = st.session_state.my_pokemon
    evolved = get_evolution(poke["id"])
    if evolved:
        st.session_state.my_pokemon    = evolved
        st.session_state.my_max_hp     = evolved["hp"]
        st.session_state.my_current_hp = evolved["hp"]
        st.session_state.my_moves      = fetch_moves(evolved["id"])
        trainer = st.session_state.trainer_name
        df  = load_teams()
        row = df[df["trainer"] == trainer]
        evos = int(row.iloc[0].get("evolutions", 0)) + 1 if len(row) else 1
        df = update_trainer(df, trainer,
            starter=evolved["name"], starter_id=evolved["id"], evolutions=evos)
        save_teams(df)
        return evolved["name"]
    return None


# ── d20 capture panel ─────────────────────────────────────────────────────────

def _render_d20_panel():
    opp     = st.session_state.opponent_pokemon
    trainer = st.session_state.trainer_name
    roll    = st.session_state.get("d20_roll")
    result  = st.session_state.get("capture_result")

    st.markdown("---")

    if result == "caught":
        caught_count = get_capture_count(trainer)
        sprite = opp.get("sprite_anim") or opp["sprite"]
        st.markdown(f"""
        <div style="background:linear-gradient(145deg,#1a3a1a,#0f2a0f);
            border:2px solid #4CAF50;border-radius:16px;padding:1.2rem;
            text-align:center;box-shadow:0 0 20px rgba(76,175,80,0.4);">
            <div style="font-size:2rem">🎉</div>
            <img src="{sprite}" width="90" style="image-rendering:pixelated"/>
            <div style="font-family:'Press Start 2P',monospace;font-size:0.7rem;
                        color:#4CAF50;margin:0.5rem 0;">{opp['name']} was caught!</div>
            <div style="font-size:0.8rem;color:var(--text-muted);">
                You rolled a <b style="color:#FFCB05">{roll}</b> 🎲 — success!<br>
                {trainer} now has <b>{caught_count}</b> captured Pokémon
            </div>
        </div>""", unsafe_allow_html=True)
        return

    if result == "escaped":
        st.markdown(f"""
        <div style="background:rgba(227,53,13,0.1);border:2px solid var(--poke-red);
            border-radius:16px;padding:1rem;text-align:center;">
            <div style="font-size:1.5rem">💨</div>
            <div style="font-family:'Press Start 2P',monospace;font-size:0.65rem;color:var(--poke-red);">
                {opp['name']} broke free!</div>
            <div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px;">
                You rolled a <b style="color:#FFCB05">{roll}</b> 🎲 — needed {CAPTURE_THRESHOLD}+
            </div>
        </div>""", unsafe_allow_html=True)
        return

    opp_types = " ".join(type_badge_html(t) for t in opp["types"])
    sprite    = opp.get("sprite_anim") or opp["sprite"]

    st.markdown(f"""
    <div style="background:linear-gradient(145deg,#1e2a4a,#0f1a35);
        border:2px solid var(--poke-yellow);border-radius:16px;padding:1.2rem;
        text-align:center;box-shadow:0 0 16px rgba(255,203,5,0.3);">
        <div style="font-size:1.5rem">⚾</div>
        <img src="{sprite}" width="100" style="image-rendering:pixelated;margin:4px 0;"/>
        <div style="font-weight:700;font-size:1rem;">{opp['name']}</div>
        <div style="margin:4px 0">{opp_types}</div>
        <div style="font-size:0.8rem;color:var(--text-muted);margin-top:6px;">
            Throw a Pokéball? Roll a d20 — you need
            <b style="color:var(--poke-yellow)">{CAPTURE_THRESHOLD}+</b> to catch it!
        </div>
    </div>""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🎲 Throw Pokéball! (Roll d20)", use_container_width=True):
            roll = random.randint(1, 20)
            st.session_state.d20_roll = roll
            if roll >= CAPTURE_THRESHOLD:
                st.session_state.capture_result = "caught"
                add_capture(trainer, opp, st.session_state.my_level)
            else:
                st.session_state.capture_result = "escaped"
            st.rerun()
    with c2:
        if st.button("✅ Caught it IRL!", use_container_width=True):
            st.session_state.d20_roll = 20
            st.session_state.capture_result = "caught"
            add_capture(trainer, opp, st.session_state.my_level)
            st.rerun()
    with c3:
        if st.button("⏭️ Skip capture", use_container_width=True):
            st.session_state.capture_result = "skipped"
            st.rerun()


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    if not _guard():
        return

    init_captures_csv()

    my      = st.session_state.my_pokemon
    trainer = st.session_state.trainer_name

    for key, default in [("capture_pending", False), ("capture_result", None), ("d20_roll", None)]:
        if key not in st.session_state:
            st.session_state[key] = default

    st.markdown("## ⚔️ Wild Battle")

    caught = get_capture_count(trainer)
    st.markdown(f"""
    <div style="display:inline-block;background:var(--poke-accent);
        border:1px solid var(--poke-blue);border-radius:20px;
        padding:3px 12px;font-size:0.8rem;margin-bottom:0.5rem;">
        ⚾ {trainer}'s Pokédex: <b>{caught}</b> caught
    </div>""", unsafe_allow_html=True)

    # ── Pre-battle lobby ─────────────────────────────────────────────────────
    if not st.session_state.battle_active and st.session_state.battle_result is None:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(my.get("sprite_anim") or my["sprite"], width=160)
        with col2:
            st.markdown(f"### {my['name']} (Lv.{st.session_state.my_level})")
            _hp_bar("HP", st.session_state.my_current_hp, st.session_state.my_max_hp)
            st.markdown(f"**XP:** {st.session_state.my_xp} / {st.session_state.my_level * 10}")

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🌿 Walk into the tall grass!", use_container_width=True):
                _start_encounter()
                st.rerun()
        with c2:
            df  = load_teams()
            row = df[df["trainer"] == trainer]
            wins = int(row.iloc[0]["wins"]) if len(row) else 0
            if wins > 0 and wins % 5 == 0:
                if st.button("✨ Check for Evolution!", use_container_width=True):
                    evolved_name = _try_evolve()
                    if evolved_name:
                        st.success(f"🎉 {my['name']} evolved into {evolved_name}!")
                        st.rerun()
                    else:
                        st.info(f"{my['name']} can't evolve further right now.")

        with st.expander("🎮 Log an outside battle"):
            st.markdown(
                "<small style='color:var(--text-muted)'>Battled outside the app? "
                "Record the result here to keep your stats up to date.</small>",
                unsafe_allow_html=True,
            )
            irl_result = st.radio("Result:", ["Win", "Loss"], horizontal=True, key="irl_result_radio")
            if st.button("✅ Log this battle", key="irl_log_btn", use_container_width=True):
                _record_result("win" if irl_result == "Win" else "lose")
                if irl_result == "Win":
                    import random as _r
                    st.session_state.my_xp += _r.randint(15, 35)
                    level_up_check()
                    st.success("🏆 Win recorded! Stats updated.")
                else:
                    st.warning("💀 Loss recorded. Better luck next time!")
                st.rerun()
        return

    # ── Post-battle result screen ─────────────────────────────────────────────
    if st.session_state.battle_result:
        result = st.session_state.battle_result

        if result == "win":
            st.markdown('<div class="win-banner">🏆 YOU WIN! 🏆</div>', unsafe_allow_html=True)
            st.markdown("#### Battle Log")
            log_text = "\n".join(st.session_state.battle_log)
            st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)

            if st.session_state.get("capture_result") not in ("skipped",):
                _render_d20_panel()

            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🌿 Find another battle!", use_container_width=True):
                    reset_battle()
                    st.session_state.capture_result = None
                    st.session_state.d20_roll = None
                    st.rerun()
            with c2:
                if st.button("🏠 Rest at Pokémon Center", use_container_width=True):
                    st.session_state.my_current_hp = st.session_state.my_max_hp
                    reset_battle()
                    st.session_state.capture_result = None
                    st.session_state.d20_roll = None
                    st.success(f"{my['name']} was fully healed!")
                    st.rerun()
        else:
            st.markdown('<div class="lose-banner">💀 YOUR POKÉMON FAINTED!</div>', unsafe_allow_html=True)
            st.markdown("#### Battle Log")
            log_text = "\n".join(st.session_state.battle_log)
            st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🌿 Try again!", use_container_width=True):
                    reset_battle()
                    st.rerun()
            with c2:
                if st.button("🏠 Rest at Pokémon Center", use_container_width=True):
                    st.session_state.my_current_hp = st.session_state.my_max_hp
                    reset_battle()
                    st.success(f"{my['name']} was fully healed!")
                    st.rerun()
        return

    # ── Active battle ─────────────────────────────────────────────────────────
    opp = st.session_state.opponent_pokemon

    col1, col2 = st.columns(2)
    with col1:
        _show_pokemon_card(my, st.session_state.my_current_hp,
                           f"Lv.{st.session_state.my_level} – {trainer}", animated=True)
    with col2:
        _show_pokemon_card(opp, st.session_state.opponent_current_hp,
                           "Wild Pokémon", animated=True)

    # ── Wild Pokémon move stats ───────────────────────────────────────────────
    opp_moves = st.session_state.opponent_moves or []
    if opp_moves:
        move_rows = "".join(
            f"""<tr>
                <td style="padding:3px 10px;font-weight:600;">{m['name']}</td>
                <td style="padding:3px 8px;">
                    <span class="type-badge" style="background:{TYPE_COLORS.get(m['type'],'#888')};">
                        {m['type']}</span></td>
                <td style="padding:3px 8px;color:{'#F44336' if (m['power'] or 0)>=80 else '#FFC107' if (m['power'] or 0)>=50 else '#aaa'};">
                    {'💥 ' if (m['power'] or 0)>=80 else ''}{m['power'] or '—'} pwr</td>
                <td style="padding:3px 8px;color:{'#4CAF50' if (m.get('accuracy') or 100)>=90 else '#FFC107' if (m.get('accuracy') or 100)>=70 else '#F44336'};">
                    {m.get('accuracy') or 100}%</td>
                <td style="padding:3px 8px;color:var(--text-muted);">{m['pp']} PP</td>
            </tr>"""
            for m in opp_moves
        )
        st.markdown(f"""
        <div style="margin:0.5rem 0 1rem 0;">
            <div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:4px;
                        letter-spacing:1px;text-transform:uppercase;">{opp['name']}'s moves</div>
            <table style="width:100%;border-collapse:collapse;background:rgba(0,0,0,0.25);
                          border:1px solid var(--poke-blue);border-radius:8px;font-size:0.8rem;">
                <thead><tr style="color:var(--text-muted);font-size:0.7rem;
                                   border-bottom:1px solid rgba(255,255,255,0.08);">
                    <th style="padding:4px 10px;text-align:left;">Move</th>
                    <th style="padding:4px 8px;text-align:left;">Type</th>
                    <th style="padding:4px 8px;text-align:left;">Power</th>
                    <th style="padding:4px 8px;text-align:left;">Acc</th>
                    <th style="padding:4px 8px;text-align:left;">PP</th>
                </tr></thead>
                <tbody>{move_rows}</tbody>
            </table>
        </div>""", unsafe_allow_html=True)

    # ── Your moves ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Choose your move:")
    move_cols = st.columns(2)
    moves = st.session_state.my_moves or []
    for i, move in enumerate(moves):
        with move_cols[i % 2]:
            acc   = move.get('accuracy') or 100
            label = f"{move['name']} ({move['type'].upper()}, {move['power']} pwr, {acc}% acc)"
            if st.button(label, key=f"move_{i}", use_container_width=True):
                _player_attack(move)
                st.rerun()

    # ── Switch Pokémon ────────────────────────────────────────────────────────
    _render_team_switcher(trainer)

    # ── Manual HP sliders ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🎛️ Manual HP Adjustment")
    sl1, sl2 = st.columns(2)
    with sl1:
        new_my_hp = st.slider(
            f"{my['name']} HP",
            min_value=0, max_value=st.session_state.my_max_hp,
            value=st.session_state.my_current_hp, key="slider_my_hp",
        )
        if new_my_hp != st.session_state.my_current_hp:
            st.session_state.my_current_hp = new_my_hp
            if new_my_hp <= 0:
                st.session_state.battle_log.append(f"💀 {my['name']} fainted...")
                st.session_state.battle_result = "lose"
                st.session_state.battle_active = False
                _record_result("lose")
            st.rerun()
    with sl2:
        new_opp_hp = st.slider(
            f"{opp['name']} HP",
            min_value=0, max_value=st.session_state.opponent_max_hp,
            value=st.session_state.opponent_current_hp, key="slider_opp_hp",
        )
        if new_opp_hp != st.session_state.opponent_current_hp:
            st.session_state.opponent_current_hp = new_opp_hp
            if new_opp_hp <= 0:
                import random as _r
                xp_gain = _r.randint(15, 35)
                st.session_state.my_xp += xp_gain
                leveled = level_up_check()
                log = st.session_state.battle_log
                log.append(f"💥 Wild {opp['name']} fainted! +{xp_gain} XP")
                if leveled:
                    log.append(f"⬆️ {my['name']} grew to level {st.session_state.my_level}!")
                st.session_state.battle_log = log[-20:]
                st.session_state.battle_result = "win"
                st.session_state.battle_active = False
                _record_result("win")
            st.rerun()

    # ── Override buttons ──────────────────────────────────────────────────────
    st.markdown("---")
    run_col, win_col, lose_col = st.columns(3)
    with run_col:
        if st.button("🏃 Run away!", use_container_width=True):
            st.session_state.battle_log.append("Got away safely!")
            reset_battle()
            st.rerun()
    with win_col:
        if st.button("🎮 Override — I won IRL!", use_container_width=True):
            import random as _r
            xp_gain = _r.randint(15, 35)
            st.session_state.my_xp += xp_gain
            leveled = level_up_check()
            log = st.session_state.battle_log
            log.append(f"[OVERRIDE] Battle won outside the app! +{xp_gain} XP")
            if leveled:
                log.append(f"⬆️ {st.session_state.my_pokemon['name']} grew to level {st.session_state.my_level}!")
            st.session_state.battle_log = log[-20:]
            st.session_state.battle_result = "win"
            st.session_state.battle_active = False
            _record_result("win")
            st.rerun()
    with lose_col:
        if st.button("💀 Override — I lost IRL!", use_container_width=True):
            log = st.session_state.battle_log
            log.append("[OVERRIDE] Battle lost outside the app.")
            st.session_state.battle_log = log[-20:]
            st.session_state.battle_result = "lose"
            st.session_state.battle_active = False
            _record_result("lose")
            st.rerun()

    if st.session_state.battle_log:
        st.markdown("#### Battle Log")
        log_text = "\n".join(st.session_state.battle_log[-10:])
        st.markdown(f'<div class="battle-log">{log_text}</div>', unsafe_allow_html=True)
