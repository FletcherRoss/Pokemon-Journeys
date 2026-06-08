import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
from utils.csv_manager import load_teams, save_teams, update_trainer, get_all_trainers
from utils.captures_manager import (
    load_captures, save_captures, init_captures_csv,
    level_up_captured, check_and_evolve_captured, level_up_and_check_evolve,
    get_active_captures, set_capture_active, MAX_ACTIVE,
)
from utils.pokemon_api import (
    get_evolution, fetch_pokemon, type_badge_html, fetch_all_learnable_moves
)
from utils.movesets_manager import (
    init_movesets_csv, load_movesets, save_moveset, get_moveset,
    delete_moveset, get_all_trainer_movesets
)

GYM_INFO = [
    {"name": "Brock",   "emoji": "🪨", "badge_key": "badge_rock"},
    {"name": "Erika",   "emoji": "🌿", "badge_key": "badge_grass"},
    {"name": "Misty",   "emoji": "💧", "badge_key": "badge_water"},
    {"name": "Blaine",  "emoji": "🔥", "badge_key": "badge_fire"},
    {"name": "Sabrina", "emoji": "🔮", "badge_key": "badge_psychic"},
    {"name": "Whitney", "emoji": "⭐", "badge_key": "badge_normal"},
    {"name": "Pryce",   "emoji": "❄️", "badge_key": "badge_ice"},
    {"name": "Lance",   "emoji": "🐉", "badge_key": "badge_elite"},
]

TRAINER_COLORS = {
    "Addy":    "#F06292",
    "Oakley":  "#64B5F6",
    "Raelynn": "#FFB74D",
}

TYPE_COLORS = {
    "fire":"#F08030","water":"#6890F0","grass":"#78C850","electric":"#F8D030",
    "psychic":"#F85888","ice":"#98D8D8","dragon":"#7038F8","dark":"#705848",
    "fairy":"#EE99AC","fighting":"#C03028","poison":"#A040A0","ground":"#E0C068",
    "flying":"#A890F0","bug":"#A8B820","rock":"#B8A038","ghost":"#705898",
    "steel":"#B8B8D0","normal":"#A8A878",
}


def _safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _sprite(pokemon_id, size="small") -> str:
    try:
        pid = int(float(pokemon_id))
        if size == "large":
            return f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{pid}.png"
        return f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pid}.png"
    except Exception:
        return ""


def _type_pills(types_str: str) -> str:
    html = ""
    for t in str(types_str).split("/"):
        t = t.strip()
        tc = TYPE_COLORS.get(t, "#888")
        html += f'<span class="type-badge" style="background:{tc};font-size:0.6rem;">{t}</span>'
    return html


# ── Evolution animation ───────────────────────────────────────────────────────

def _show_evolution_animation(old_poke_id: int, old_name: str, new_poke: dict):
    old_sprite = _sprite(old_poke_id, "large")
    new_sprite = _sprite(new_poke["id"], "large")
    new_types  = "".join(
        f'<span class="type-badge" style="background:{TYPE_COLORS.get(t,"#888")};">{t}</span>'
        for t in new_poke.get("types", ["normal"])
    )
    st.markdown(f"""
    <style>
    @keyframes evo-flash  {{ 0%,40%,80%{{ filter:brightness(1); }} 20%,60%{{ filter:brightness(8) saturate(0); }} }}
    @keyframes evo-grow   {{ 0%{{ transform:scale(0.5) rotate(-5deg);opacity:0; }} 60%{{ transform:scale(1.15) rotate(2deg);opacity:1; }} 100%{{ transform:scale(1) rotate(0);opacity:1; }} }}
    @keyframes evo-shimmer{{ 0%,100%{{ box-shadow:0 0 10px rgba(255,203,5,0.4); }} 50%{{ box-shadow:0 0 50px rgba(255,203,5,1),0 0 80px rgba(255,255,255,0.6); }} }}
    @keyframes fade-out   {{ 0%{{ opacity:1;transform:scale(1); }} 100%{{ opacity:0;transform:scale(0.3); }} }}
    .evo-container{{ background:linear-gradient(135deg,#0a0a1a,#1a0a3a,#0a1a2a);border:3px solid var(--poke-yellow);border-radius:20px;padding:2rem 1rem;text-align:center;margin:1rem 0;animation:evo-shimmer 2s ease-in-out infinite; }}
    .evo-old{{ display:inline-block;animation:fade-out 1.2s ease-in forwards;animation-delay:0.5s; }}
    .evo-new{{ display:inline-block;animation:evo-grow 1.2s cubic-bezier(0.175,0.885,0.32,1.275) forwards;animation-delay:0.8s;opacity:0; }}
    .evo-title{{ font-family:'Press Start 2P',monospace;font-size:0.85rem;color:var(--poke-yellow);text-shadow:0 0 20px rgba(255,203,5,0.8);margin:1rem 0 0.5rem 0;animation:evo-flash 1.5s ease-in-out; }}
    </style>
    <div class="evo-container">
        <div class="evo-title">✨ WHAT?! {old_name.upper()} IS EVOLVING! ✨</div>
        <div style="display:flex;align-items:center;justify-content:center;gap:1rem;margin:1.5rem 0;">
            <div class="evo-old">
                <img src="{old_sprite}" width="130" style="image-rendering:pixelated;filter:drop-shadow(0 0 12px rgba(255,255,255,0.6))"/>
                <div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px;">{old_name}</div>
            </div>
            <div style="font-size:2.5rem;color:var(--poke-yellow);margin:0 1rem;">➜</div>
            <div class="evo-new">
                <img src="{new_sprite}" width="160" style="image-rendering:pixelated;filter:drop-shadow(0 0 20px rgba(255,203,5,0.9))"/>
                <div style="font-size:0.95rem;font-weight:700;color:#fff;margin-top:4px;">{new_poke['name']}</div>
                <div style="margin-top:4px;">{new_types}</div>
            </div>
        </div>
        <div style="font-size:0.8rem;color:var(--text-muted);">
            ❤️ HP:{new_poke['hp']} &nbsp;⚔️ ATK:{new_poke['attack']} &nbsp;🛡️ DEF:{new_poke['defense']} &nbsp;⚡ SPD:{new_poke['speed']}
        </div>
    </div>""", unsafe_allow_html=True)
    st.balloons()


# ── Move selector ─────────────────────────────────────────────────────────────

def _move_selector(trainer: str, pokemon_id: int, pokemon_name: str, current_moves: list[dict], key_prefix: str):
    """
    Renders a searchable move picker. Saves directly to movesets.csv.
    current_moves: list of move dicts (from get_moveset()).
    """
    st.markdown(f"""
    <div style="background:rgba(0,0,0,0.2);border:1px solid var(--poke-blue);
        border-radius:12px;padding:1rem;margin-bottom:0.5rem;">
        <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:0.5rem;
            text-transform:uppercase;letter-spacing:1px;">
            ⚔️ Move Set — pick up to 4
        </div>""", unsafe_allow_html=True)

    # Guard against invalid pokemon_id
    if not pokemon_id or pokemon_id <= 0:
        st.info("No Pokémon selected yet.")
        return

    # Load all learnable moves (cached)
    with st.spinner(f"Loading {pokemon_name}'s learnable moves..."):
        try:
            all_moves = fetch_all_learnable_moves(pokemon_id)
        except Exception as e:
            st.warning(f"Could not load moves: {e}")
            return

    if not all_moves:
        st.warning("Could not load moves from PokéAPI.")
        return

    # Build display options keyed by canonical name
    move_options = {
        f"{m['name']} [{m['type'].upper()}] {m['power'] or '—'} pwr · {m['accuracy']}% acc · {m['pp']} PP"
        : m['name']
        for m in all_moves
    }

    # name → label using full unfiltered dict; normalise both sides to lower for matching
    name_to_label = {v: k for k, v in move_options.items()}
    name_to_label_lower = {v.lower(): k for k, v in move_options.items()}
    def _find_label(move_name: str) -> str | None:
        try:
            if move_name in name_to_label:
                return name_to_label[move_name]
            return name_to_label_lower.get(str(move_name).lower())
        except Exception:
            return None
    # current_moves is a list of dicts from movesets.csv
    current_move_names = [m["name"] for m in current_moves if isinstance(m, dict)]
    current_labels = [lbl for n in current_move_names for lbl in [_find_label(n)] if lbl]

    # Type filter
    all_types = sorted({m["type"] for m in all_moves})
    type_filter = st.selectbox(
        "Filter by type:",
        ["All types"] + all_types,
        key=f"{key_prefix}_type_filter",
    )
    filtered_options = {
        label: name for label, name in move_options.items()
        if type_filter == "All types" or f"[{type_filter.upper()}]" in label
    }

    # Multiselect capped at 4
    selected_labels = st.multiselect(
        f"Select moves (max 4):",
        options=list(filtered_options.keys()),
        default=[l for l in current_labels if l in filtered_options],
        max_selections=4,
        key=f"{key_prefix}_move_select",
    )

    # Show current full selection (across filter)
    # Merge persisted labels + newly selected, deduplicated, capped at 4
    # Use move_options (label→name) to validate labels, not name_to_label (name→label)
    full_selection = list(dict.fromkeys(
        [l for l in selected_labels] +
        [l for l in current_labels if l not in selected_labels]
    ))
    full_selection = [l for l in full_selection if l in move_options][:4]

    # Preview current 4
    if full_selection:
        preview_html = ""
        for label in full_selection:
            name = move_options.get(label, "")
            move = next((m for m in all_moves if m["name"] == name), None)
            if move:
                tc       = TYPE_COLORS.get(move["type"], "#888")
                pwr      = move['power'] or '—'
                acc      = move['accuracy']
                acc_col  = '#4CAF50' if acc >= 90 else '#FFC107' if acc >= 70 else '#F44336'
                pp       = move['pp']
                mtype    = move['type']
                mname    = move['name']
                preview_html += (
                    f'<div style="display:flex;align-items:center;gap:8px;padding:3px 0;'
                    f'border-bottom:1px solid rgba(255,255,255,0.05);">'
                    f'<span class="type-badge" style="background:{tc};font-size:0.6rem;min-width:60px;text-align:center;">{mtype}</span>'
                    f'<span style="font-weight:600;font-size:0.85rem;flex:1;">{mname}</span>'
                    f'<span style="font-size:0.75rem;color:#aaa;">{pwr} pwr</span>'
                    f'<span style="font-size:0.75rem;color:{acc_col};">{acc}%</span>'
                    f'<span style="font-size:0.75rem;color:var(--text-muted);">{pp} PP</span>'
                    f'</div>'
                )
        st.markdown(f"""
        <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:0.6rem 0.8rem;margin:0.5rem 0;">
            <div style="font-size:0.65rem;color:var(--text-muted);margin-bottom:4px;text-transform:uppercase;">
                Current moveset ({len(full_selection)}/4)
            </div>
            {preview_html}
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("<small style='color:var(--text-muted);'>No moves selected yet.</small>",
                    unsafe_allow_html=True)

    col_save, col_clear = st.columns(2)
    with col_save:
        if st.button("💾 Save moveset", key=f"{key_prefix}_save", use_container_width=True):
            final_names = [move_options[l] for l in full_selection if l in move_options]
            # Build full move dicts from all_moves lookup
            move_map  = {m["name"]: m for m in all_moves}
            move_map_lower = {m["name"].lower(): m for m in all_moves}
            final_dicts = []
            for name in final_names:
                m = move_map.get(name) or move_map_lower.get(name.lower())
                if m:
                    final_dicts.append(m)
            save_moveset(trainer, pokemon_id, pokemon_name, final_dicts)
            # Sync active session moves if this is the current trainer's active pokemon
            if st.session_state.get("trainer_name") == trainer:
                active = st.session_state.get("my_pokemon", {})
                if active.get("id") == pokemon_id and final_dicts:
                    st.session_state.my_moves = final_dicts
            st.toast(f"✅ Moveset saved for {pokemon_name}!", icon="✅")
            st.rerun()
    with col_clear:
        if st.button("🗑️ Clear moves", key=f"{key_prefix}_clear", use_container_width=True):
            delete_moveset(trainer, pokemon_id)
            st.toast(f"Moveset cleared for {pokemon_name}.", icon="🗑️")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ── Team management card ─────────────────────────────────────────────────────

def _team_management_card(trainer: str, teams_df: pd.DataFrame, captures_df: pd.DataFrame):
    color  = TRAINER_COLORS.get(trainer, "#888")
    emoji  = {"Addy":"🌸","Oakley":"⚡","Raelynn":"🔥"}.get(trainer,"🎮")

    # ── Starter (always active, can't be removed) ─────────────────────────────
    row = teams_df[teams_df["trainer"] == trainer]
    starter_id   = _safe_int(row.iloc[0].get("starter_id", 0)) if len(row) else 0
    starter_name = str(row.iloc[0].get("starter", "")).strip() if len(row) else ""
    starter_lv   = _safe_int(row.iloc[0].get("level", 5), 5) if len(row) else 5

    # Get all captures for this trainer
    trainer_caps = captures_df[captures_df["trainer"] == trainer].copy()
    if trainer_caps.empty:
        trainer_caps["active"] = pd.Series(dtype=int)
    elif "active" not in trainer_caps.columns:
        trainer_caps["active"] = 1
    else:
        # Normalise to int — CSV may load as float or string
        def _ai(v):
            try: return int(float(v))
            except: return 1
        trainer_caps["active"] = trainer_caps["active"].apply(_ai)

    active_caps   = trainer_caps[trainer_caps["active"] == 1]
    inactive_caps = trainer_caps[trainer_caps["active"] != 1]
    total_active  = len(active_caps)

    # ── Team summary banner ───────────────────────────────────────────────────
    slots_used = 1 + total_active  # starter + active captures
    slots_total = 1 + MAX_ACTIVE
    bar_pct = int((slots_used / slots_total) * 100)
    bar_col = "#4CAF50" if slots_used < slots_total else "#FFCB05"

    team_label = f"{emoji} {trainer}'s Active Team"
    st.markdown(
        f'<div style="background:rgba(0,0,0,0.25);border:1px solid {color};'
        f'border-radius:12px;padding:0.8rem 1rem;margin-bottom:0.8rem;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
        f'<span style="font-weight:700;color:{color};">{team_label}</span>'
        f'<span style="font-size:0.85rem;color:var(--text-muted);">{slots_used}/{slots_total} slots</span>'
        f'</div>'
        f'<div class="hp-bar-wrap"><div class="hp-bar-fill" style="width:{bar_pct}%;background:{bar_col};"></div></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── Active roster display (starter + active captures) ─────────────────────
    st.markdown("**Active roster:**")
    active_entries = []

    # Starter slot (locked)
    if starter_id > 0:
        sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{starter_id}.png"
        active_entries.append(("starter", None, starter_name, sprite, starter_lv, True))

    # Active captures
    for idx, cap in active_caps.iterrows():
        pid    = _safe_int(cap["pokemon_id"])
        lv     = _safe_int(cap.get("current_level") or cap.get("level_caught"), 5)
        sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pid}.png"
        active_entries.append(("capture", idx, cap["pokemon_name"], sprite, lv, False))

    # Empty slots
    empty_slots = slots_total - len(active_entries)

    cols_per_row = 3
    all_slots = active_entries + [("empty", None, f"Empty slot", "", 0, False)] * empty_slots

    for row_start in range(0, len(all_slots), cols_per_row):
        chunk = all_slots[row_start:row_start + cols_per_row]
        cols  = st.columns(cols_per_row)
        for col, (kind, idx, name, sprite, lv, locked) in zip(cols, chunk):
            with col:
                if kind == "empty":
                    st.markdown(
                        '<div style="border:2px dashed #333;border-radius:12px;padding:0.8rem;'
                        'text-align:center;min-height:80px;display:flex;align-items:center;'
                        'justify-content:center;color:#555;font-size:0.75rem;">Empty slot</div>',
                        unsafe_allow_html=True
                    )
                else:
                    lock_badge = ' 🔒' if locked else ''
                    st.markdown(
                        f'<div style="background:linear-gradient(145deg,#1e3a1e,#0f2a0f);'
                        f'border:2px solid {color};border-radius:12px;padding:0.7rem;'
                        f'text-align:center;">'
                        f'<img src="{sprite}" width="55" style="image-rendering:pixelated"/>'
                        f'<div style="font-size:0.72rem;font-weight:700;margin:3px 0;">{name}{lock_badge}</div>'
                        f'<div style="font-size:0.62rem;color:var(--text-muted);">Lv.{lv}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    if not locked and kind == "capture":
                        if st.button("❌ Deactivate", key=f"deact_{trainer}_{idx}",
                                     use_container_width=True):
                            ok, msg = set_capture_active(idx, False)
                            if ok:
                                st.toast(f"{name} moved to bench.", icon="📦")
                            else:
                                st.error(msg)
                            st.rerun()

    # ── Bench (inactive captures) ─────────────────────────────────────────────
    if len(inactive_caps) > 0:
        st.markdown("**Bench (inactive):**")
        for row_start in range(0, len(inactive_caps), cols_per_row):
            chunk = list(inactive_caps.iloc[row_start:row_start + cols_per_row].iterrows())
            cols  = st.columns(cols_per_row)
            for col, (idx, cap) in zip(cols, chunk):
                pid    = _safe_int(cap["pokemon_id"])
                lv     = _safe_int(cap.get("current_level") or cap.get("level_caught"), 5)
                sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pid}.png"
                name   = cap["pokemon_name"]
                with col:
                    st.markdown(
                        f'<div style="background:linear-gradient(145deg,#1a1a2e,#0f0f1e);'
                        f'border:2px solid #333;border-radius:12px;padding:0.7rem;'
                        f'text-align:center;opacity:0.7;">'
                        f'<img src="{sprite}" width="55" style="image-rendering:pixelated"/>'
                        f'<div style="font-size:0.72rem;font-weight:700;margin:3px 0;">{name}</div>'
                        f'<div style="font-size:0.62rem;color:var(--text-muted);">Lv.{lv} — Benched</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    disabled = total_active >= MAX_ACTIVE
                    help_txt = f"Bench is full ({MAX_ACTIVE} active)" if disabled else f"Activate {name}"
                    if st.button("✅ Activate", key=f"act_{trainer}_{idx}",
                                 use_container_width=True, disabled=disabled,
                                 help=help_txt):
                        ok, msg = set_capture_active(idx, True)
                        if ok:
                            st.toast(f"{name} added to active team!", icon="✅")
                        else:
                            st.error(msg)
                        st.rerun()
    elif len(inactive_caps) == 0 and len(trainer_caps) > 0:
        st.markdown("<small style='color:var(--text-muted)'>All caught Pokémon are active.</small>",
                    unsafe_allow_html=True)
    else:
        st.markdown("<small style='color:var(--text-muted)'>No Pokémon caught yet.</small>",
                    unsafe_allow_html=True)


# ── Starter card ──────────────────────────────────────────────────────────────

def _starter_levelup_card(trainer: str, teams_df: pd.DataFrame):
    row = teams_df[teams_df["trainer"] == trainer]
    if row.empty:
        return
    r = row.iloc[0]
    starter    = str(r.get("starter", "")).strip()
    starter_id = _safe_int(r.get("starter_id", 0))
    level      = _safe_int(r.get("level", 5), 5)

    if not starter or starter in ("", "nan") or starter_id == 0:
        st.markdown("_No starter chosen yet._")
        return

    color  = TRAINER_COLORS.get(trainer, "#888")
    sprite = _sprite(starter_id, "large")
    current_moves = get_moveset(trainer, starter_id)

    col_img, col_info, col_btn = st.columns([1, 2, 1])
    with col_img:
        st.image(sprite, width=90)
    with col_info:
        moves_line = '⚔️ ' + ' · '.join(m['name'] for m in current_moves) if current_moves else '⚔️ No moves set'
        st.markdown(f"""
        <div style="padding:4px 0">
            <div style="font-weight:700;font-size:1rem;color:{color};">{starter}</div>
            <div style="font-size:0.8rem;color:var(--text-muted);">Starter Pokémon</div>
            <div style="margin-top:6px;">
                <span style="background:var(--poke-accent);border:1px solid {color};
                    border-radius:20px;padding:3px 12px;font-size:0.85rem;font-weight:700;">
                    Lv. {level}
                </span>
            </div>
            <div style="margin-top:4px;font-size:0.75rem;color:var(--text-muted);">
                {moves_line}
            </div>
        </div>""", unsafe_allow_html=True)
    with col_btn:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("⬆️ Level Up", key=f"lvlup_starter_{trainer}", use_container_width=True):
            new_level = level + 1
            updated   = update_trainer(teams_df, trainer, level=new_level)
            save_teams(updated)
            if st.session_state.get("trainer_name") == trainer:
                st.session_state.my_level = new_level
            evolved = get_evolution(starter_id)
            if evolved:
                updated2 = update_trainer(updated, trainer,
                    starter=evolved["name"], starter_id=evolved["id"])
                save_teams(updated2)
                if st.session_state.get("trainer_name") == trainer:
                    st.session_state.my_pokemon    = evolved
                    st.session_state.my_max_hp     = evolved["hp"]
                    st.session_state.my_current_hp = evolved["hp"]
                st.session_state["_evo_event"] = {
                    "old_id": starter_id, "old_name": starter, "new": evolved
                }
            else:
                st.toast(f"⬆️ {starter} is now Lv. {new_level}!", icon="⬆️")
            st.rerun()

    # Move selector expander
    with st.expander(f"⚔️ Edit {starter}'s moveset"):
        _move_selector(trainer, starter_id, starter, current_moves, f"starter_{trainer}")


# ── Captured Pokémon grid ─────────────────────────────────────────────────────

def _captures_levelup_grid(trainer: str, captures_df: pd.DataFrame):
    trainer_caps = captures_df[captures_df["trainer"] == trainer]

    if trainer_caps.empty:
        st.markdown("_No Pokémon captured yet._")
        return

    st.markdown(f"**{len(trainer_caps)} Pokémon caught**")

    cols_per_row = 3
    indices = list(trainer_caps.index)

    move_expanders = []  # collect (poke_id, name, current_moves, cap_idx) to render below grid

    for row_start in range(0, len(indices), cols_per_row):
        chunk_idx = indices[row_start:row_start + cols_per_row]
        cols = st.columns(cols_per_row)

        for col, cap_idx in zip(cols, chunk_idx):
            cap    = captures_df.loc[cap_idx]
            cur_lv = _safe_int(cap.get("current_level") or cap.get("level_caught"), 5)
            poke_id = _safe_int(cap["pokemon_id"])
            name    = cap["pokemon_name"]
            sprite  = _sprite(poke_id)
            types   = _type_pills(cap.get("types", "normal"))
            color   = TRAINER_COLORS.get(trainer, "#888")
            current_moves = get_moveset(trainer, poke_id)
            evo_available = get_evolution(poke_id) is not None

            with col:
                evo_badge = (
                    '<div style="font-size:0.65rem;color:#FFCB05;margin-top:2px;">&#10024; Can evolve!</div>'
                    if evo_available else ""
                )
                moves_names = ' &middot; '.join(m['name'] for m in current_moves) if current_moves else 'No moves set'
                moves_line  = f'<div style="font-size:0.6rem;color:#a0a8c0;margin-top:3px;">&#9876; {moves_names}</div>'

                st.markdown(
                    '<div class="pokemon-card" style="cursor:default;padding:0.9rem 0.6rem;margin-bottom:4px;">'
                    f'<img src="{sprite}" width="75" style="image-rendering:pixelated"/>'
                    f'<div style="font-size:0.8rem;font-weight:700;margin:4px 0;">{name}</div>'
                    f'<div style="margin-bottom:4px;">{types}</div>'
                    f'<span style="background:#0f3460;border:1px solid {color};'
                    f'border-radius:20px;padding:2px 10px;font-size:0.8rem;font-weight:700;">Lv. {cur_lv}</span>'
                    + evo_badge + moves_line +
                    '</div>',
                    unsafe_allow_html=True
                )

                if st.button("⬆️", key=f"lvlup_cap_{cap_idx}",
                             use_container_width=True, help=f"Level up {name}"):
                    _, evolved = level_up_and_check_evolve(cap_idx)
                    if evolved:
                        st.session_state["_evo_event"] = {
                            "old_id": poke_id, "old_name": name, "new": evolved
                        }
                    else:
                        st.toast(f"⬆️ {name} is now Lv. {cur_lv + 1}!", icon="⬆️")
                    st.rerun()

            move_expanders.append((poke_id, name, current_moves, cap_idx))

    # Render move selectors outside the columns context to avoid HTML rendering issues
    st.markdown("##### ⚔️ Edit Movesets")
    for poke_id, name, current_moves, cap_idx in move_expanders:
        with st.expander(f"⚔️ {name}'s moves", expanded=False):
            _move_selector(trainer, poke_id, name, current_moves, f"cap_{cap_idx}")


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    init_captures_csv()
    init_movesets_csv()

    # Evolution animation
    if "_evo_event" in st.session_state:
        ev = st.session_state.pop("_evo_event")
        _show_evolution_animation(ev["old_id"], ev["old_name"], ev["new"])
        if st.button("🎉 Continue", use_container_width=False):
            st.rerun()
        return

    st.markdown("## 📊 Team Stats & Leaderboard")

    teams_df    = load_teams()
    captures_df = load_captures()

    # Backfill captures columns robustly
    for col, default in [("current_level", None), ("selected_moves", ""), ("active", 1)]:
        if col not in captures_df.columns:
            captures_df[col] = default

    # Fix current_level empty/nan values
    if not captures_df.empty:
        captures_df["current_level"] = captures_df.apply(
            lambda r: r["level_caught"] if str(r.get("current_level", "")).strip() in ("", "nan")
            else r["current_level"], axis=1
        )

    # Normalise active to int (may be stored as string "1"/"0" from CSV)
    def _to_active_int(v):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 1  # default active if unparseable
    if not captures_df.empty:
        captures_df["active"] = captures_df["active"].apply(_to_active_int)

    # Backfill teams selected_moves column if missing
    if "selected_moves" not in teams_df.columns:
        teams_df["selected_moves"] = ""
    if "level" not in teams_df.columns:
        teams_df["level"] = 5

    if teams_df.empty:
        st.info("No journey data yet. Head to Home and choose a trainer!")
        return

    # ── Leaderboard ──────────────────────────────────────────────────────────
    st.markdown("### 🏆 Trainer Leaderboard")
    df_sorted = teams_df.sort_values(["badges", "wins"], ascending=False).reset_index(drop=True)

    for rank, (_, row) in enumerate(df_sorted.iterrows()):
        trainer = row["trainer"]
        color   = TRAINER_COLORS.get(trainer, "#888")
        badges  = _safe_int(row.get("badges", 0))
        wins    = _safe_int(row.get("wins", 0))
        losses  = _safe_int(row.get("losses", 0))
        level   = _safe_int(row.get("level", 5), 5)
        starter = row.get("starter", "—")
        evos    = _safe_int(row.get("evolutions", 0))
        caught  = len(captures_df[captures_df["trainer"] == trainer])
        medal   = ["🥇", "🥈", "🥉"][rank] if rank < 3 else "🎖️"

        badge_html = "".join(
            f'<span class="{"gym-badge-earned" if _safe_int(row.get(g["badge_key"],0))==1 else "gym-badge-locked"}"'
            f' style="width:32px;height:32px;font-size:1rem;">{g["emoji"]}</span>'
            for g in GYM_INFO
        )
        total    = wins + losses
        win_rate = f"{(wins/total*100):.0f}%" if total > 0 else "—"

        st.markdown(f"""
        <div style="background:linear-gradient(135deg,rgba(30,40,70,0.9),rgba(15,25,50,0.9));
            border:2px solid {color};border-radius:16px;
            padding:1.2rem 1.5rem;margin:0.8rem 0;
            box-shadow:0 4px 16px rgba(0,0,0,0.3);">
            <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap;">
                <span style="font-size:2rem">{medal}</span>
                <div>
                    <div style="font-size:1.2rem;font-weight:700;color:{color};">{trainer}</div>
                    <div style="font-size:0.85rem;color:#a0a8c0;">
                        🐾 {starter} &nbsp;|&nbsp; Lv.{level} &nbsp;|&nbsp;
                        ✨ {evos} evo{'s' if evos!=1 else ''} &nbsp;|&nbsp;
                        ⚾ {caught} caught
                    </div>
                </div>
                <div style="margin-left:auto;text-align:right;">
                    <div style="font-size:1.1rem;font-weight:700;">W:{wins} / L:{losses}</div>
                    <div style="font-size:0.8rem;color:#a0a8c0;">Win rate: {win_rate}</div>
                </div>
            </div>
            <div style="margin-top:0.8rem;">
                <small style="color:#a0a8c0;">Gym Badges:</small><br>{badge_html}
            </div>
        </div>""", unsafe_allow_html=True)

    # ── Team management ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎒 Active Team Management")
    st.markdown(
        f"<small style='color:var(--text-muted)'>Each trainer can have <b>1 starter + {MAX_ACTIVE} captured Pokémon</b> "
        f"active (6 total). Swap which caught Pokémon are in your active roster here.</small>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    all_trainers = get_all_trainers()
    def _tab_label(t):
        emojis = {"Addy":"🌸","Oakley":"⚡","Raelynn":"🔥"}
        return f"{emojis.get(t, '🎮')} {t}"
    team_tabs = st.tabs([_tab_label(t) for t in all_trainers])
    for tab, tab_trainer in zip(team_tabs, all_trainers):
        with tab:
            _team_management_card(tab_trainer, teams_df, captures_df)

    # ── Level-up + move selection ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ⬆️ Level Up & Movesets")
    st.markdown(
        "<small style='color:var(--text-muted)'>Level up Pokémon and customise their move sets. "
        "Each Pokémon can know up to <b>4 moves</b>. "
        "A <span style='color:#FFCB05'>✨ Can evolve!</span> badge appears when evolution is available.</small>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    trainer_tabs = st.tabs([_tab_label(t) for t in all_trainers])
    for tab, tab_trainer in zip(trainer_tabs, all_trainers):
        with tab:
            st.markdown("#### Starter")
            _starter_levelup_card(tab_trainer, teams_df)
            st.markdown("---")
            st.markdown("#### Captured Pokémon")
            _captures_levelup_grid(tab_trainer, captures_df)

    # ── Charts ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📈 Win / Loss Comparison")
    chart_df = pd.DataFrame([
        {"Trainer": r["trainer"],
         "Wins":    _safe_int(r.get("wins", 0)),
         "Losses":  _safe_int(r.get("losses", 0))}
        for _, r in teams_df.iterrows()
    ]).set_index("Trainer")
    st.bar_chart(chart_df, color=["#4CAF50", "#F44336"])

    st.markdown("---")
    st.markdown("### ⚾ Pokémon Captured per Trainer")
    cap_df = pd.DataFrame(
        {t: [len(captures_df[captures_df["trainer"] == t])] for t in all_trainers},
        index=["Caught"]
    ).T
    st.bar_chart(cap_df, color=["#FFCB05"])

    st.markdown("---")
    st.markdown("### 🏅 Badge Progress")
    badge_df = pd.DataFrame([
        {"Trainer": r["trainer"],
         "Badges Earned": sum(_safe_int(r.get(g["badge_key"],0)) for g in GYM_INFO),
         "Remaining": 8 - sum(_safe_int(r.get(g["badge_key"],0)) for g in GYM_INFO)}
        for _, r in teams_df.iterrows()
    ]).set_index("Trainer")
    st.bar_chart(badge_df, color=["#FFCB05", "#333355"])

    with st.expander("📋 Raw Data"):
        st.markdown("**teams.csv**")
        st.dataframe(teams_df, use_container_width=True)
        st.markdown("**captures.csv**")
        st.dataframe(captures_df, use_container_width=True)
        st.download_button("⬇️ Download captures.csv",
            data=captures_df.to_csv(index=False),
            file_name="captures.csv", mime="text/csv")
