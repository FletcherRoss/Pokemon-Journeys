import requests
import random
import streamlit as st

# All starters from Gen 1–9
ALL_STARTERS = [
    # Gen 1
    1,   # Bulbasaur
    4,   # Charmander
    7,   # Squirtle
    # Gen 2
    152, # Chikorita
    155, # Cyndaquil
    158, # Totodile
    # Gen 3
    252, # Treecko
    255, # Torchic
    258, # Mudkip
    # Gen 4
    387, # Turtwig
    390, # Chimchar
    393, # Piplup
    # Gen 5
    495, # Snivy
    498, # Tepig
    501, # Oshawott
    # Gen 6
    650, # Chespin
    653, # Fennekin
    656, # Froakie
    # Gen 7
    722, # Rowlet
    725, # Litten
    728, # Popplio
    # Gen 8
    810, # Grookey
    813, # Scorbunny
    816, # Sobble
    # Gen 9
    906, # Sprigatito
    909, # Fuecoco
    912, # Quaxly
]

# Type color map
TYPE_COLORS = {
    "fire": "#F08030", "water": "#6890F0", "grass": "#78C850",
    "electric": "#F8D030", "psychic": "#F85888", "ice": "#98D8D8",
    "dragon": "#7038F8", "dark": "#705848", "fairy": "#EE99AC",
    "fighting": "#C03028", "poison": "#A040A0", "ground": "#E0C068",
    "flying": "#A890F0", "bug": "#A8B820", "rock": "#B8A038",
    "ghost": "#705898", "steel": "#B8B8D0", "normal": "#A8A878",
}

BASE_URL = "https://pokeapi.co/api/v2"


@st.cache_data(ttl=3600)
def fetch_pokemon(pokemon_id: int) -> dict:
    """Fetch full pokemon data from PokeAPI, cached for 1 hour."""
    try:
        r = requests.get(f"{BASE_URL}/pokemon/{pokemon_id}", timeout=10)
        r.raise_for_status()
        data = r.json()

        name = data["name"].capitalize()
        types = [t["type"]["name"] for t in data["types"]]
        stats = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}

        sprite_front = (
            data["sprites"]["other"]["official-artwork"]["front_default"]
            or data["sprites"]["front_default"]
        )
        sprite_anim = (
            data["sprites"].get("versions", {})
            .get("generation-v", {})
            .get("black-white", {})
            .get("animated", {})
            .get("front_default")
        )

        return {
            "id": pokemon_id,
            "name": name,
            "types": types,
            "hp": stats.get("hp", 45),
            "attack": stats.get("attack", 49),
            "defense": stats.get("defense", 49),
            "speed": stats.get("speed", 45),
            "sp_attack": stats.get("special-attack", 65),
            "sp_defense": stats.get("special-defense", 65),
            "sprite": sprite_front,
            "sprite_anim": sprite_anim or sprite_front,
        }
    except Exception as e:
        # Fallback minimal pokemon
        return {
            "id": pokemon_id,
            "name": f"Pokemon#{pokemon_id}",
            "types": ["normal"],
            "hp": 45, "attack": 49, "defense": 49,
            "speed": 45, "sp_attack": 65, "sp_defense": 65,
            "sprite": f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon_id}.png",
            "sprite_anim": f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon_id}.png",
        }


@st.cache_data(ttl=3600)
def fetch_moves(pokemon_id: int) -> list[dict]:
    """Fetch up to 4 learnable moves for a pokemon."""
    try:
        r = requests.get(f"{BASE_URL}/pokemon/{pokemon_id}", timeout=10)
        r.raise_for_status()
        moves_raw = r.json()["moves"]
        # Pick moves learned by level-up
        levelup = [m for m in moves_raw if any(
            vd["move_learn_method"]["name"] == "level-up"
            for vd in m["version_group_details"]
        )]
        selected = random.sample(levelup, min(4, len(levelup)))
        moves = []
        for m in selected:
            move_name = m["move"]["name"].replace("-", " ").title()
            move_r = requests.get(m["move"]["url"], timeout=8)
            if move_r.ok:
                md = move_r.json()
                moves.append({
                    "name":     move_name,
                    "power":    md.get("power") or 40,
                    "type":     md.get("type", {}).get("name", "normal"),
                    "pp":       md.get("pp", 10),
                    "accuracy": md.get("accuracy") or 100,
                })
            else:
                moves.append({"name": move_name, "power": 40, "type": "normal", "pp": 10, "accuracy": 100})
        return moves
    except Exception:
        return [
            {"name": "Tackle",  "power": 40, "type": "normal", "pp": 35, "accuracy": 100},
            {"name": "Scratch", "power": 40, "type": "normal", "pp": 35, "accuracy": 100},
            {"name": "Growl",   "power": 0,  "type": "normal", "pp": 40, "accuracy": 100},
            {"name": "Leer",    "power": 0,  "type": "normal", "pp": 30, "accuracy": 100},
        ]


@st.cache_data(ttl=3600)
def fetch_all_learnable_moves(pokemon_id: int) -> list[dict]:
    """Fetch every move a pokemon can learn (level-up, TM, egg, tutor) with stats.
    Returns list of {name, power, type, accuracy, pp, learn_method}.
    """
    try:
        r = requests.get(f"{BASE_URL}/pokemon/{pokemon_id}", timeout=10)
        r.raise_for_status()
        moves_raw = r.json()["moves"]
        results = []
        seen = set()
        for m in moves_raw:
            move_name = m["move"]["name"].replace("-", " ").title()
            if move_name in seen:
                continue
            seen.add(move_name)
            methods = list({vd["move_learn_method"]["name"]
                            for vd in m["version_group_details"]})
            method_label = "/".join(sorted(methods)[:2])  # keep it short
            move_r = requests.get(m["move"]["url"], timeout=8)
            if move_r.ok:
                md = move_r.json()
                results.append({
                    "name":         move_name,
                    "power":        md.get("power") or 0,
                    "type":         md.get("type", {}).get("name", "normal"),
                    "accuracy":     md.get("accuracy") or 100,
                    "pp":           md.get("pp", 10),
                    "learn_method": method_label,
                })
            else:
                results.append({
                    "name": move_name, "power": 0, "type": "normal",
                    "accuracy": 100, "pp": 10, "learn_method": "level-up",
                })
        return sorted(results, key=lambda x: x["name"])
    except Exception:
        return []


def get_random_starters(n: int = 3) -> list[dict]:
    """Pick n random starters (no duplicates)."""
    chosen_ids = random.sample(ALL_STARTERS, n)
    return [fetch_pokemon(pid) for pid in chosen_ids]


def get_random_wild(min_id: int = 1, max_id: int = 1025) -> dict:
    """Return a random wild pokemon (all generations, up to Gen 9)."""
    pid = random.randint(min_id, max_id)
    return fetch_pokemon(pid)


def get_gym_leader_team(gym_index: int) -> list[dict]:
    """Return a gym leader's pokemon based on gym number (0-7)."""
    GYM_TEAMS = [
        [74, 95],           # Gym 1 – Rock
        [43, 70, 182],      # Gym 2 – Grass
        [72, 120, 121],     # Gym 3 – Water
        [136, 38, 78],      # Gym 4 – Fire/Electric
        [124, 122],         # Gym 5 – Psychic
        [85, 36, 36],       # Gym 6 – Normal/Electric
        [62, 117, 91],      # Gym 7 – Water/Ice
        [130, 143, 59],     # Gym 8 – Mixed (Elite)
    ]
    team_ids = GYM_TEAMS[min(gym_index, 7)]
    return [fetch_pokemon(pid) for pid in team_ids]


def get_evolution_info(pokemon_id: int) -> dict | None:
    """
    Return evolution info dict or None if no evolution exists.
    Dict contains:
      - evolved: the evolved pokemon dict
      - min_level: int or None (None means no level requirement)
      - trigger: str (e.g. 'level-up', 'use-item', 'trade', 'shed')
      - item: str or None (e.g. 'fire-stone')
    """
    try:
        r = requests.get(f"{BASE_URL}/pokemon-species/{pokemon_id}", timeout=10)
        r.raise_for_status()
        evo_url = r.json()["evolution_chain"]["url"]
        evo_r   = requests.get(evo_url, timeout=10)
        evo_r.raise_for_status()
        chain   = evo_r.json()["chain"]

        def find_next(node, target_id):
            if node["species"]["url"].split("/")[-2] == str(target_id):
                if node["evolves_to"]:
                    evo_node    = node["evolves_to"][0]
                    next_id     = int(evo_node["species"]["url"].split("/")[-2])
                    details     = evo_node.get("evolution_details", [{}])[0]
                    trigger     = details.get("trigger", {}).get("name", "level-up")
                    min_level   = details.get("min_level")  # None if not level-based
                    item        = None
                    if details.get("item"):
                        item = details["item"].get("name")
                    return {"next_id": next_id, "trigger": trigger,
                            "min_level": min_level, "item": item}
            for child in node["evolves_to"]:
                result = find_next(child, target_id)
                if result:
                    return result
            return None

        info = find_next(chain, pokemon_id)
        if info:
            evolved = fetch_pokemon(info["next_id"])
            return {
                "evolved":   evolved,
                "trigger":   info["trigger"],
                "min_level": info["min_level"],
                "item":      info["item"],
            }
    except Exception:
        pass
    return None


def get_evolution(pokemon_id: int, current_level: int = None) -> dict | None:
    """
    Return evolved form if the pokemon can evolve.
    - Level-up evolutions: only if current_level >= min_level (or no min_level set).
    - Item/trade/other evolutions: always allowed (no level gate).
    Pass current_level=None to skip the level check entirely (backwards compat).
    """
    info = get_evolution_info(pokemon_id)
    if not info:
        return None

    trigger   = info["trigger"]
    min_level = info["min_level"]
    evolved   = info["evolved"]

    # Item, trade, shed evolutions — always allow
    if trigger in ("use-item", "trade", "shed"):
        return evolved

    # Level-up evolution — enforce level requirement if provided
    if trigger == "level-up":
        if current_level is not None and min_level is not None:
            if current_level < min_level:
                return None   # not high enough yet
        return evolved

    # Any other trigger — allow freely
    return evolved


def can_evolve_preview(pokemon_id: int, current_level: int) -> tuple[bool, str]:
    """
    Returns (can_evolve_now, reason_string) for UI display.
    e.g. (False, "Needs Lv.36") or (True, "Ready!") or (True, "Needs Fire Stone")
    """
    info = get_evolution_info(pokemon_id)
    if not info:
        return False, "No evolution"

    trigger   = info["trigger"]
    min_level = info["min_level"]
    item      = info["item"]

    if trigger in ("use-item", "trade", "shed"):
        item_name = item.replace("-", " ").title() if item else "item/trade"
        return True, f"Needs {item_name}"

    if trigger == "level-up":
        if min_level is not None and current_level < min_level:
            return False, f"Needs Lv.{min_level}"
        return True, "Ready to evolve!"

    return True, "Ready to evolve!"


def get_pokemon_sprite(pokemon_id: int, animated: bool = True) -> str:
    poke = fetch_pokemon(pokemon_id)
    return poke["sprite_anim"] if animated else poke["sprite"]


def type_badge_html(type_name: str) -> str:
    color = TYPE_COLORS.get(type_name, "#888")
    return f'<span class="type-badge" style="background:{color};">{type_name}</span>'
