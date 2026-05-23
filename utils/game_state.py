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


def damage_calc(attacker: dict, defender: dict, move: dict, attacker_level: int = 5) -> int:
    """Gen-1-inspired damage formula."""
    power = move.get("power", 40) or 40
    atk   = attacker.get("attack", 49)
    df_   = defender.get("defense", 49)
    # STAB
    stab = 1.5 if move.get("type") in attacker.get("types", []) else 1.0
    # Random factor
    import random
    rand = random.uniform(0.85, 1.0)
    dmg  = int(((2 * attacker_level / 5 + 2) * power * atk / df_ / 50 + 2) * stab * rand)
    return max(1, dmg)


def reset_battle():
    st.session_state.battle_active = False
    st.session_state.battle_log    = []
    st.session_state.battle_turn   = 0
    st.session_state.battle_result = None
    st.session_state.opponent_pokemon = None
    st.session_state.opponent_current_hp = 0
