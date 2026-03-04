# Depths of Dread

A terminal roguelike dungeon crawler built with Python and curses.

## Features

- **BSP dungeon generation** with 15 themed floors
- **Shadowcasting FOV** and fog of war
- **3 character classes**: Warrior, Mage, Rogue
- **19+ enemy types** including 3 bosses and 4 branch mini-bosses
- **Stealth system**: Monster alertness (asleep/unwary/alert), noise mechanics, backstab bonuses
- **Dungeon branches**: Branching paths at floors 5 and 10 with themed content
- **Monster Memory/Bestiary**: Track encounters, kills, abilities with progressive reveal
- **Spells, abilities, and status effects**: Fireball, Freeze, Chain Lightning, Mana Shield, and more
- **A* pathfinding** for enemies and auto-explore
- **Puzzle system**: Torch pedestals, switches, locked stairs
- **Alchemy tables** for identifying items
- **Journal system** for tracking discovered items
- **Save/load** with checksum integrity (permadeath on death)
- **Bot AI** for automated play (decision tree)
- **Agent AI** (hybrid Claude-powered) for tactical decisions
- **Session recording** and replay

## Installation

```bash
pip install depths-of-dread
```

Or from source:

```bash
git clone https://github.com/willrompf/depths-of-dread.git
cd depths-of-dread
pip install -e .
```

## Usage

### Interactive Play
```bash
depths-of-dread
# or
python -m depths_of_dread
```

### Bot Mode (AI plays)
```bash
depths-of-dread --bot
depths-of-dread --bot --games 10  # batch mode
```

### Agent Mode (Claude-powered hybrid AI)
```bash
depths-of-dread --agent
```

### Controls

| Key | Action |
|-----|--------|
| Arrow keys / WASD / hjkl | Move |
| Walk into enemy | Melee attack |
| f | Fire projectile |
| z | Cast spell |
| t | Class technique |
| i | Inventory |
| , | Pick up item |
| > / < | Descend / Ascend stairs |
| o | Auto-explore |
| Tab | Auto-fight |
| M | Bestiary (Monster Memory) |
| ? | Help |

## Requirements

- Python 3.8+
- Terminal with curses support (macOS/Linux)
- No external dependencies for the game itself

## Testing

```bash
pytest tests/
# or built-in tests:
depths-of-dread --test
```

## License

MIT
