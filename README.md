# ⚡ Pokémon Journeys

A multi-trainer Pokémon RPG built with Streamlit. Three trainers — **Addy**, **Oakley**, and **Raelynn** — compete to collect gym badges and climb the leaderboard. All progress is tracked in a shared `data/teams.csv` synced to this GitHub repository.

---

## 🎮 Features

| Feature | Details |
|---|---|
| **Starter selection** | 3 random starters drawn from all Gen 1–3 starters |
| **Wild battles** | Turn-based combat against random Gen 1–3 Pokémon |
| **Gym battles** | 8 open-world gyms (choose any order) |
| **Evolution** | Pokémon evolve every 5 wins via PokéAPI chain |
| **Sprites & animations** | Official artwork + Gen V animated sprites |
| **Team tracking** | CSV stored on GitHub, shared across all trainers |
| **Leaderboard** | Badges → wins determines ranking |

---

## 🗂 Project Structure

```
Pokemon-Journeys/
├── app.py                    # Main Streamlit entry point
├── requirements.txt
├── data/
│   └── teams.csv             # Shared trainer progress (synced to GitHub)
├── pages/
│   ├── home.py               # Trainer select + starter choose
│   ├── wild_battle.py        # Wild encounter battles
│   ├── gym_battle.py         # Gym leader battles
│   └── team_stats.py         # Leaderboard & charts
├── utils/
│   ├── pokemon_api.py        # PokeAPI wrapper (cached)
│   ├── csv_manager.py        # GitHub CSV read/write
│   └── game_state.py         # Session state + battle math
└── .streamlit/
    ├── config.toml           # Dark theme config
    └── secrets.toml.example  # Template for GitHub token
```

---

## 🚀 Deploy to Streamlit Cloud

1. **Fork or push** this repo to GitHub (already at `FletcherRoss/Pokemon-Journeys`)

2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**

3. Set:
   - Repository: `FletcherRoss/Pokemon-Journeys`
   - Branch: `main`
   - Main file: `app.py`

4. Under **Settings → Secrets**, add:
   ```toml
   GITHUB_TOKEN = "ghp_your_token_here"
   ```
   Create a token at [github.com/settings/tokens](https://github.com/settings/tokens) with **repo** scope.

5. Click **Deploy** 🎉

---

## 🔑 GitHub Token (for CSV sync)

The app reads `data/teams.csv` from this repo via the GitHub API and writes back after every battle. Without a token the app still works — data is saved locally per session but won't persist across users.

**Token permissions needed:** `repo` (full repository access)

---

## 🛠 Run Locally

```bash
git clone https://github.com/FletcherRoss/Pokemon-Journeys.git
cd Pokemon-Journeys
pip install -r requirements.txt
# Optionally: create .streamlit/secrets.toml with GITHUB_TOKEN
streamlit run app.py
```

---

## 🧠 Battle System

- Damage uses the Gen 1 formula: `((2L/5 + 2) × Power × Atk/Def / 50 + 2) × STAB × random`
- STAB (Same Type Attack Bonus): 1.5× if move type matches Pokémon type
- Level-up every 10 XP × current level; stats grow 5% per level
- Evolution unlocked every 5 wins; checks PokéAPI evolution chain

---

## 📡 Data Sources

- [PokéAPI](https://pokeapi.co/) — Pokémon data, moves, sprites, evolution chains
- Sprites: official artwork + Gen V animated sprites from PokeAPI CDN

---

*Built with ❤️ and Streamlit*
