import streamlit as st


def init_session_state():
    defaults = {
        # Trainer identity
        "trainer_name": None,       # "Addy" | "Oakley" | "Raelynn"

        # Current pokemon (in-battle copy with mutable HP)
        "my_pokemon": None,         # dict from pokemon_api
        "my_moves": None,           # list of move dicts
        "my_current_hp": 0,
        "my_max_hp": 0,
        "my_level": 5,
        "my_xp": 0,

        # Opponent
        "opponent_pokemon": None,
        "opponent_moves": None,
        "opponent_current_hp": 0,
        "opponent_max_hp": 0,

        # Starters shown on home page
        "starter_options": None,    # list of 3 pokemon dicts

        # Flow flags
        "starter_chosen": False,
        "battle_active": False,
        "battle_log": [],
        "battle_turn": 0,
        "battle_result": None,      # "win" | "lose" | None

        # Gym
        "gym_index": 0,
        "gym_leader_team": None,
        "gym_leader_hp": [],
        "gym_leader_index": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def level_up_check():
    """Check if player earns a level-up and apply stat boosts."""
    xp_threshold = st.session_state.my_level * 10
    if st.session_state.my_xp >= xp_threshold and st.session_state.my_pokemon:
        st.session_state.my_level += 1
        st.session_state.my_xp -= xp_threshold
        # Boost stats slightly
        p = st.session_state.my_pokemon
        p["attack"]   = int(p["attack"]   * 1.05)
        p["defense"]  = int(p["defense"]  * 1.05)
        p["hp"]       = int(p["hp"]       * 1.05)
        p["sp_attack"]= int(p["sp_attack"]* 1.05)
        st.session_state.my_pokemon = p
        # Heal a bit on level up
        new_max = p["hp"]
        st.session_state.my_max_hp = new_max
        st.session_state.my_current_hp = min(st.session_state.my_current_hp + 10, new_max)
        return True
    return False


def hp_percent(current, maximum) -> float:
    if maximum <= 0:
        return 0
    return max(0, min(100, (current / maximum) * 100))


def hp_bar_color(pct: float) -> str:
    if pct > 50:
        return "#4CAF50"
    elif pct > 25:
        return "#FFC107"
    else:
        return "#F44336"



# ── Type effectiveness chart ──────────────────────────────────────────────────
# TYPE_CHART[attacking_type][defending_type] = multiplier
# 2.0 = super effective, 0.5 = not very effective, 0.0 = immune, 1.0 = normal
TYPE_CHART: dict[str, dict[str, float]] = {
    "normal":   {"rock":0.5,"steel":0.5,"ghost":0.0},
    "fire":     {"fire":0.5,"water":0.5,"rock":0.5,"dragon":0.5,
                 "grass":2.0,"ice":2.0,"bug":2.0,"steel":2.0},
    "water":    {"water":0.5,"grass":0.5,"dragon":0.5,
                 "fire":2.0,"ground":2.0,"rock":2.0},
    "grass":    {"fire":0.5,"grass":0.5,"poison":0.5,"flying":0.5,"bug":0.5,"dragon":0.5,"steel":0.5,
                 "water":2.0,"ground":2.0,"rock":2.0},
    "electric": {"grass":0.5,"electric":0.5,"dragon":0.5,"ground":0.0,
                 "water":2.0,"flying":2.0},
    "ice":      {"water":0.5,"ice":0.5,"steel":0.5,
                 "grass":2.0,"ground":2.0,"flying":2.0,"dragon":2.0},
    "fighting": {"poison":0.5,"flying":0.5,"psychic":0.5,"bug":0.5,"fairy":0.5,"ghost":0.0,
                 "normal":2.0,"ice":2.0,"rock":2.0,"dark":2.0,"steel":2.0},
    "poison":   {"poison":0.5,"ground":0.5,"rock":0.5,"ghost":0.5,"steel":0.0,
                 "grass":2.0,"fairy":2.0},
    "ground":   {"grass":0.5,"bug":0.5,"flying":0.0,
                 "fire":2.0,"electric":2.0,"poison":2.0,"rock":2.0,"steel":2.0},
    "flying":   {"electric":0.5,"rock":0.5,"steel":0.5,
                 "grass":2.0,"fighting":2.0,"bug":2.0},
    "psychic":  {"psychic":0.5,"steel":0.5,"dark":0.0,
                 "fighting":2.0,"poison":2.0},
    "bug":      {"fire":0.5,"fighting":0.5,"flying":0.5,"ghost":0.5,"steel":0.5,"fairy":0.5,
                 "grass":2.0,"psychic":2.0,"dark":2.0},
    "rock":     {"fighting":0.5,"ground":0.5,"steel":0.5,
                 "fire":2.0,"ice":2.0,"flying":2.0,"bug":2.0},
    "ghost":    {"normal":0.0,"dark":0.5,
                 "ghost":2.0,"psychic":2.0},
    "dragon":   {"steel":0.5,"fairy":0.0,
                 "dragon":2.0},
    "dark":     {"fighting":0.5,"dark":0.5,"fairy":0.5,
                 "ghost":2.0,"psychic":2.0},
    "steel":    {"fire":0.5,"water":0.5,"electric":0.5,"steel":0.5,
                 "ice":2.0,"rock":2.0,"fairy":2.0},
    "fairy":    {"fire":0.5,"poison":0.5,"steel":0.5,
                 "fighting":2.0,"dragon":2.0,"dark":2.0},
}


def type_multiplier(move_type: str, defender_types: list[str]) -> float:
    """Return the combined type effectiveness multiplier."""
    chart  = TYPE_CHART.get(move_type.lower(), {})
    result = 1.0
    for dtype in defender_types:
        result *= chart.get(dtype.lower(), 1.0)
    return result


def damage_calc(attacker: dict, defender: dict, move: dict, attacker_level: int = 5) -> tuple[int, bool]:
    """
    Gen-style damage formula with type effectiveness.
    Returns (damage, hit) where hit=False means the move missed.
    Logs effectiveness to battle_log via session_state if available.
    """
    import random

    # Accuracy check
    accuracy = move.get("accuracy") or 100
    hit = random.randint(1, 100) <= accuracy
    if not hit:
        return 0, False

    power = move.get("power", 40) or 40
    atk   = attacker.get("attack", 49)
    df_   = defender.get("defense", 49)

    # STAB
    stab = 1.5 if move.get("type") in attacker.get("types", []) else 1.0

    # Type effectiveness
    move_type      = move.get("type", "normal")
    defender_types = defender.get("types", ["normal"])
    effectiveness  = type_multiplier(move_type, defender_types)

    # Random factor
    rand = random.uniform(0.85, 1.0)

    dmg = int(((2 * attacker_level / 5 + 2) * power * atk / df_ / 50 + 2) * stab * effectiveness * rand)

    return max(0 if effectiveness == 0.0 else 1, dmg), True


def effectiveness_label(move_type: str, defender_types: list[str]) -> str:
    """Return a log-friendly effectiveness string."""
    mult = type_multiplier(move_type, defender_types)
    if mult >= 4.0:
        return "⚡⚡ SUPER effective (×4)!"
    elif mult >= 2.0:
        return "⚡ Super effective! (×2)"
    elif mult == 0.0:
        return "❌ No effect."
    elif mult <= 0.25:
        return "🛡️🛡️ Not very effective (×0.25)..."
    elif mult < 1.0:
        return "🛡️ Not very effective (×0.5)..."
    return ""



def speed_order(my: dict, opp: dict) -> tuple[bool, int, int]:
    """Returns (player_goes_first, my_speed, opp_speed)."""
    import random
    my_spd  = my.get("speed", 45)
    opp_spd = opp.get("speed", 45)
    if my_spd == opp_spd:
        player_first = random.choice([True, False])
    else:
        player_first = my_spd > opp_spd
    return player_first, my_spd, opp_spd


def reset_battle():
    st.session_state.battle_active = False
    st.session_state.battle_log    = []
    st.session_state.battle_turn   = 0
    st.session_state.battle_result = None
    st.session_state.opponent_pokemon = None
    st.session_state.opponent_current_hp = 0
