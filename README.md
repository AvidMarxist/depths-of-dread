```
    ____             __  __                ____  ___                    __
   / __ \___  ____  / /_/ /_  _____   ____/ / / / __ \________  ____ _/ /
  / / / / _ \/ __ \/ __/ __ \/ ___/  / __  / / / / / / ___/ _ \/ __ `/ /
 / /_/ /  __/ /_/ / /_/ / / (__  )  / /_/ / / / /_/ / /  /  __/ /_/ / /
/_____/\___/ .___/\__/_/ /_/____/   \__,_/ / /_____/_/   \___/\__,_/_/
          /_/                             |/
```

# Depths of Dread

**A terminal roguelike dungeon crawler with Claude-powered AI agents. v1.0.**

Descend 20 floors of procedurally generated dungeons. Fight 30+ enemy types and 8 bosses with multi-phase fights. Choose your class, solve puzzles, brew alchemy, and survive — or watch an AI do it for you.

Built entirely in Python with zero external dependencies. Runs in any terminal.

---

## Play Modes

| Mode | Command | What It Does |
|------|---------|-------------|
| **Interactive** | `python3 dungeon.py` | You play the game |
| **Bot** | `python3 dungeon.py --bot` | Decision-tree AI plays (instant) |
| **Agent** | `python3 dungeon.py --agent` | Claude Haiku-powered AI plays with split-screen decision panel |
| **Batch** | `python3 dungeon.py --bot --games 10` | Run N headless games for testing (class rotation) |
| **Batch JSON** | `python3 dungeon.py --bot --games 10 --json` | Structured JSON output for trend tracking |
| **Agent Batch** | `python3 dungeon.py --agent --games 6` | Run N Claude-powered games (2 per class rotation) |

In Agent mode, press **Shift+P** to enter **Pilot Mode** — take manual control, unstick the AI, guide it through puzzles, then release back.

---

## Features

### Core
- BSP dungeon generation with 20 themed floors
- Shadowcasting field-of-view with fog of war
- A* pathfinding for enemies and auto-explore
- Permadeath with save/load (checksum-protected)
- Session recording and replay

### Combat & Classes
- **Warrior** — high HP, Whirlwind, Cleaving Strike, Shield Wall
- **Mage** — spells scale with level, Fireball, Chain Lightning, Meteor, Mana Shield
- **Rogue** — stealth bonuses, Backstab (2x crit), Poison Blade, Smoke Bomb

### Enemies & Bosses
- 30+ enemy types with 9 unique AI behaviors (mimic, phase spider, mind flayer, summoner, etc.)
- 3 main bosses with multi-phase fights: Ogre King (F5), Vampire Lord (F10), Dread Lord (F15)
- Abyssal Horror (F20) — the true final boss with void AOE and shadow summons
- 4 branch mini-bosses: Crypt Guardian, Flame Tyrant, Elder Brain, Beast Lord
- **Dread Lord phases** — taunting summoner → shadow strike teleports → darkness arena (drains your torch, summons wraiths)
- **Monster fleeing** — wounded enemies retreat (undead and bosses fight to death)

### Dungeon Branches
- Floor 5: Choose **Flooded Crypts** (undead, water) or **Burning Pits** (demons, lava)
- Floor 10: Choose **Mind Halls** (psychic, paralyze) or **Beast Warrens** (fast beasts, traps)
- Each branch has themed enemies, terrain modifications, and a mini-boss guardian

### Stealth System
- Enemies spawn **asleep** or **unwary** — sleeping enemies skip turns, unwary only patrol
- Movement generates noise (corridors=1, floors=2, doors=4, combat=8, spells=6)
- Rogue class generates 50% less noise
- Attacking sleeping enemies = guaranteed 2x crit; unwary = 1.5x crit

### Resistance & Elements
- Fire, cold, and poison damage types
- Rings grant elemental resistance (50% damage reduction)
- Enemy vulnerabilities (trolls weak to fire, wraiths weak to fire, etc.)
- Fire suppresses troll regeneration for 5 turns

### Environmental Interactions
- Water extinguishes burning status and blocks fire aura
- Lightning spells on water tiles chain to all nearby water-standing enemies
- Lava passable with fire or cold resistance (-2 HP per step)

### Traps
- Hidden traps trigger on step; search to reveal; disarm with Rogue bonus
- 6 trap types: spike, dart (poison), pit (stun), teleport, alarm, gas (confusion)
- Enemies trigger traps too — lure them over!

### Other Systems
- **Environmental vignettes** — 30 atmospheric encounters (fallen adventurers, whispering bones, shadow gardens) with floor-appropriate lore and loot
- **Bestiary** (press M) — progressive reveal based on encounter count
- **Puzzle system** — torch pedestals, switches, locked stairs
- **Alchemy tables** — identify unknown potions, scrolls, and rings; grant alchemical boons
- **Fountains** — magical healing waters, chance of permanent +1 max HP
- **Secret rooms** — hidden chambers behind walls, search (/) to discover, contain valuable loot
- **Journal** — tracks discovered item effects
- **Boss weapon drops** — Vampiric Blade with 20% lifesteal, Void Reaver (tier 6)
- **Shops** — spend gold on items mid-dungeon
- **Shrines** — pray for boons (some are cursed)
- **Wall torches** — grab for torch fuel
- **Challenge modes** — Ironman (permadeath), Speedrun (floor timer), Pacifist, Dark (reduced torch)
- **Difficulty modes** — easy, normal, hard (--difficulty flag)
- **Meta-progression** — lifetime stats unlock bonuses for future runs
- **256-color palettes** — 19 themed floor palettes with automatic fallback to 16-color
- **Unicode tiles** — rich glyphs (█ walls, · floors, ≈ water, ▼▲ stairs) with ASCII fallback

---

## Controls

| Key | Action |
|-----|--------|
| Arrow keys / WASD / hjkl / yubn | Move (8 directions) |
| Walk into enemy | Melee attack |
| `f` + direction | Fire projectile (arrows, daggers, wands) |
| `z` | Spell menu (pick spell → pick direction) |
| `t` | Techniques menu (class combat abilities) |
| `C` | Class ability (Battle Cry / Arcane Blast / Shadow Step) |
| `i` | Inventory (use, equip, drop items) |
| `,` | Pick up item / Grab wall torch |
| `e` | Interact (alchemy table, pedestal, fountain) |
| `>` / `<` | Descend / Ascend stairs |
| `$` | Browse shop |
| `p` | Pray at shrine |
| `/` | Search for traps & secrets |
| `D` | Disarm visible trap |
| `o` | Auto-explore |
| `Tab` | Auto-fight (attack nearest enemy) |
| `R` | Rest until healed |
| `.` or `5` | Wait (skip one turn, heal if not starving) |
| `T` | Toggle torch on/off |
| `J` | Journal (identified items log) |
| `M` | Bestiary (Monster Memory) |
| `c` | Character sheet |
| `S` | Lifetime stats |
| `x` | Examine/look mode |
| `m` | Message log |
| `Q` | Save & Quit |
| `?` | Help (2-page in-game reference) |

### Agent Mode Controls
| Key | Action |
|-----|--------|
| `q` | Quit |
| `Space` | Pause/resume |
| `+` / `-` | Speed up / slow down |
| `t` | Toggle decision panel |
| `Shift+P` | Pilot mode (take/release manual control) |

---

## Installation

### PC / Mac (Recommended)

**Option A — Run directly (simplest):**
```bash
# Just download and run — no install needed
git clone https://github.com/AvidMarxist/depths-of-dread.git
cd depths-of-dread
python3 src/depths_of_dread/game.py
```

**Option B — Install as a package:**
```bash
git clone https://github.com/AvidMarxist/depths-of-dread.git
cd depths-of-dread
pip install -e .
depths-of-dread          # Play!
depths-of-dread --bot    # Watch the bot play
depths-of-dread --agent  # Watch Claude play (requires Claude CLI)
```

**Option C — pip install (coming soon):**
```bash
pip install depths-of-dread
```

### Requirements
- **Python 3.8+** (included on macOS and most Linux distros)
- A terminal that supports curses (macOS Terminal, iTerm2, Linux terminal, Windows Terminal with WSL)
- **No external Python packages required** — uses only the standard library
- Minimum terminal size: 80 columns x 24 rows (132+ columns for agent split-screen)

### Windows
Windows doesn't include curses natively. Options:
1. **WSL (recommended):** Install WSL2, then run normally in the WSL terminal
2. **windows-curses:** `pip install windows-curses` then run in Windows Terminal

---

### iPad (via iSH)

Play on iPad using [iSH](https://apps.apple.com/us/app/ish-shell/id1436902243), a free Linux terminal emulator.

**One-time setup (requires WiFi):**
```bash
# 1. Install iSH from the App Store

# 2. Open iSH and install Python
apk add python3

# 3. Download the game
apk add git
git clone https://github.com/AvidMarxist/depths-of-dread.git
```

**Play (works offline after setup):**
```bash
cd depths-of-dread
python3 src/depths_of_dread/game.py
```

**Tips for iPad:**
- Use a Bluetooth keyboard for the best experience
- iSH runs x86 emulation so startup takes a few seconds
- The on-screen keyboard works but arrow keys require the extended keyboard row
- Bot mode (`--bot`) works great for watching on a flight
- Agent mode is not available on iPad (requires Claude CLI)

---

## Agent Mode (Claude-Powered AI)

Agent mode uses a hybrid architecture: a decision-tree bot handles routine turns, and Claude Haiku is consulted for tactical decisions (combat, puzzles, shops, shrines, boss fights, exploration strategy).

### Requirements
Agent mode requires the [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated:
```bash
# Install Claude CLI
npm install -g @anthropic-ai/claude-code

# Authenticate (opens browser)
claude auth login
```

You need your own **Claude Max subscription** or **Anthropic API key**. The game does not include or require any API credentials — agent mode calls the `claude` binary on your machine.

### How It Works
- Bot handles movement, basic combat, item pickup (~97% of turns)
- Claude Haiku is called for: enemies visible, low HP, boss fights, shops, shrines, puzzles, alchemy, new floors, and when stuck
- Split-screen panel shows Claude's reasoning, strategy, latency, and decision history
- **Pilot Mode (Shift+P):** Take manual control mid-game, then hand back to the agent
- Stuck detector: if the agent repeats positions for 15+ turns, Claude is consulted for escape

### Cost
Agent mode calls Claude Haiku (~$0.005-0.01 per game). A typical game uses 100-200 Claude calls at ~$0.00005 each.

---

## Testing

```bash
# Quick test suite (lint + unit tests + built-in tests, ~30s)
./test-quick.sh

# Unit tests only (474 tests)
python3 -m pytest tests/

# Lint only (ruff + mypy)
./lint.sh

# Built-in tests (dungeon connectivity, enemy spawning, item generation)
python3 src/depths_of_dread/game.py --test

# Bot batch (stress test, auto class rotation)
python3 src/depths_of_dread/game.py --bot --games 10

# Bot batch with JSON output (for trend tracking)
python3 src/depths_of_dread/game.py --bot --games 10 --json > results.json

# Bot batch, single class
python3 src/depths_of_dread/game.py --bot --games 10 --class warrior

# Agent batch (requires Claude CLI)
python3 src/depths_of_dread/game.py --agent --games 6
```

### Play Modes

```bash
# Difficulty modes
python3 src/depths_of_dread/game.py --difficulty easy    # Relaxed
python3 src/depths_of_dread/game.py --difficulty hard    # Punishing

# Quick start a specific class
python3 src/depths_of_dread/game.py --class warrior

# Challenge modes
python3 src/depths_of_dread/game.py --ironman   # Permadeath, no save
python3 src/depths_of_dread/game.py --dark      # Reduced FOV
```

---

## Project Structure

```
depths-of-dread/
  src/depths_of_dread/
    game.py          # Game loop, GameState, command dispatch (~1,090 lines)
    constants.py     # All balance tuning, enemy/item/spell/theme definitions (~1,180 lines)
    bot.py           # BotPlayer decision-tree AI + batch mode (~1,050 lines)
    agent.py         # AgentPlayer Claude-powered hybrid AI (~1,350 lines)
    agent_ui.py      # Agent mode UI: split panel, pilot mode, FeatureTracker (~390 lines)
    items.py         # Item usage, spells, player actions (~1,700 lines)
    ui.py            # Rendering, inventory, character sheet, menus (~1,640 lines)
    combat.py        # Combat resolution, enemy AI, status effects (~1,070 lines)
    persistence.py   # Save/load, session recording, replay (~770 lines)
    floor_gen.py     # Floor generation, enemy/item/feature population (~710 lines)
    entities.py      # Player, Enemy, Item, ShopItem classes (~450 lines)
    mapgen.py        # BSP dungeon generation, FOV, A* pathfinding (~430 lines)
    exceptions.py    # Custom exception hierarchy (~30 lines)
    __init__.py      # Version info
    __main__.py      # python -m entry point
  tests/
    conftest.py      # Shared fixtures
    test_bot.py      # Bot/agent AI tests
    test_branches.py # Dungeon branches, puzzles, NPCs
    test_combat.py   # Combat, traps, stealth, status effects
    test_entities.py # Player, items, equipment
    test_game_integration.py  # Game loop, keybindings, auto-fight/explore
    test_items.py    # Spells, potions, scrolls, abilities, shops
    test_mapgen.py   # Dungeon generation, pathfinding
    test_persistence.py  # Save/load, recordings, serialization
    test_quality.py  # Performance, security, balance, stress tests
    test_ui.py       # HUD, menus, inventory display
  docs/              # Design docs, audit reports, feature inventory
  pyproject.toml     # Package config, ruff + mypy settings
  test-quick.sh      # Full test suite: lint + pytest + built-in tests (~30s)
  lint.sh            # ruff + mypy validation
  LICENSE            # MIT
```

~11,900 lines of source across 13 modules. 474 tests across 10 test files. Zero external dependencies — just Python's standard library and a terminal.

---

## License

MIT — do whatever you want with it.

## Credits

Built by Will Rompf with Claude (Anthropic).
