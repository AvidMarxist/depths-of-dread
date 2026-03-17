# Depths of Dread — Feature Inventory

**Total Source Lines:** ~12,640 (13 modules, all fully typed)
**Last Updated:** 2026-03-17

---

## 1. CORE LOOP

### Movement & Turns
- **Player Movement** — WASD/Arrow keys/vi keys (hjklyubn), 4 cardinal or 8 diagonal
- **Turn Counter** — Increments on every action, used for cooldowns/spawn timing
- **Floor Transitions** — '>' descends, 'u' ascends. Floor 20 = victory
- **Hunger System** — 0.12% per move, starvation = 1 HP/turn damage
- **Speedrun Challenge Timer** — Floor time limit = 100 + floor*20 turns

### Floor Progression
- **20 Floors** total, deeper = harder enemies/better loot
- **15 Named Themes** — "The Entrance", "Catacomb", etc.
- **Branch System** — At floors 7, 10, 13: choose 1 of 2 paths (7 branch pairs total). Each spans 3-4 floors with unique enemies/terrain/mini-boss
- **Branch Terrain** — Branches convert 3% of tiles to water/lava

---

## 2. COMBAT

### Melee
- Hit chance: 75% base + 2%/level
- Critical hits: 10% base + 2%/level, 1.8x damage
- Damage: weapon + STR//3, reduced by enemy DEF//2
- Evasion: 5% base + class bonuses, capped at 40%

### Stealth & Backstab
- 60% of enemies spawn asleep (2x backstab damage)
- Unwary state = 1.5x backstab
- Rogue Backstab ability: guaranteed 2.5x crit, partial defense ignore
- Alertness states: asleep → unwary → alert

### Ranged
- **Bows** — Equip + arrows (stacking consumable), projectile animation
- **Throwing Daggers** — 5-tile range, stacking
- **Wands** — 6 types, charge-based, Mage bonus +50% dmg/+2 range

### Spells (8 total)
- **All classes:** Fireball (3x3 AoE), Lightning Bolt (line + water chain), Heal, Teleport, Freeze (3 turns)
- **Mage only:** Chain Lightning (3 targets, 75% decay), Meteor (5x5 AoE), Mana Shield (absorb with mana)
- Mana regen: 1 per 3 turns automatic
- Spell resistance: some enemies take 50% less from fire/cold

### Class Abilities
- **Warrior:** Whirlwind (all adjacent), Cleaving Strike (2x ignore DEF), Shield Wall (50% reduction 8 turns), Battle Cry (freeze nearby 5 turns)
- **Rogue:** Backstab (2.5x crit), Poison Blade (10 attacks), Smoke Bomb (blind enemies + evasion), Shadow Step
- **Mage:** Arcane Blast (ranged 5 tiles)
- All abilities have cooldowns (10-15 turns)

### Enemy AI (9 types)
- Patrol, Chase (A*), Erratic, Pack, Ranged, Summoner (spawn allies), Mind Flayer (psychic), Mimic (disguise as gold), Phase (through walls), Ambush, Fleeing

### Boss System
- 8 bosses with 2-3 phases (behavior changes at 50%/25% HP)
- Vampire: doubled lifesteal → summon bats
- Dread Lord (floor 20), Abyssal Horror (final), Flame Tyrant, Elder Brain, Beast Lord, Crypt Guardian
- Boss weapon drops (unique enchanted weapons)

### Status Effects (15+)
- Poison, Paralysis, Fear, Blindness, Strength, Speed, Resistance, Berserk, Confusion, Frozen (2x damage then break), Silence, Bleed (stacking), Mana Shield, Smoke Evasion, Poison Blade, Shield Wall

---

## 3. CHARACTER SYSTEM

### 4 Classes
- **Warrior** — HP:38, MP:14, STR:6, DEF:3. Melee specialist.
- **Mage** — HP:26, MP:28, STR:4, DEF:1. Full spell access.
- **Rogue** — HP:30, MP:20, STR:5, DEF:2. Evasion+15%, trap detect+30%.
- **Adventurer** (classless) — HP:30, MP:20, STR:5, DEF:1. Balanced/classic.

### Leveling
- XP to level = 25 * 1.5^(level-1)
- Level-up choices: Vitality, Mana, Strength, Defense, Evasion, or class-specific (Arcana/Cleave/Lethality)
- Class-specific gains per level (HP/MP/STR/DEF)

### Inventory
- Carry capacity = 15 + STR
- 4 equipment slots: weapon, armor, ring, bow
- Stack items (arrows, daggers, food) = 1 slot

---

## 4. ITEMS & EQUIPMENT

### Weapons (~20 types, 5 tiers)
- Spawn tier scales with floor depth
- Enchantable (+bonus damage via scrolls/anvils)
- Boss drops: unique weapons with lifesteal/special effects

### Armor (~15 types)
- Flat defense value, some grant elemental resistance

### Rings (~12 types)
- Strength, Defense, Evasion, Elemental Resistance
- Ring of Hunger (cursed: +15% hunger drain)

### Potions (10 types)
- Unidentified by color until drunk. ID shuffled per game.
- Healing, Strength, Speed, Poison (bad), Blindness (bad), Experience, Resistance, Berserk, Mana

### Scrolls (10 types)
- Unidentified by label until read. ID shuffled per game.
- Identify, Teleport, Fireball, Mapping, Enchant, Fear, Summon (bad), Lightning

### Food (5 types)
- Ration, Bread, Mystery Meat (20% food poisoning), Honey Cake, Exotic Fruit
- 2-3 guaranteed per floor

### Torches
- 200 fuel max, depletes 1/turn when lit
- Radius: 8 (full) → 6 → 4 → 2 (empty)
- Toggle on/off, flicker warning at 50%
- Refill via loot drops

### Gold
- 1-3 piles per floor, enemy drops (30% chance)
- Currency for shops and enchant anvils

---

## 5. MAP GENERATION

### Dungeon Layout (80x40)
- BSP algorithm with room shapes: rectangular (50%), circular (20%), L-shaped (15%), pillared (15%)
- L-shaped corridors, 30% door placement at chokepoints
- 1-3 extra loop corridors for alternate routes
- Connectivity verification (95%+ reachable), fallback grid generator

### Special Rooms & Features
- **Shops** — Every other odd floor
- **Shrines** — Floors 2,6,10,14. Prayer: 30% full heal, 20% +max HP, 15% +STR, 15% +DEF, 10% nothing, 10% curse
- **Alchemy Tables** — Floors 2,5,8,11,14. Identify 1 unID'd item
- **Wall Torches** — 40% of rooms get 2-4 torches (atmosphere)
- **Enchant Anvils** — 20% chance on floors 6+, pay gold to enchant
- **Fountains** — 40% per floor, drink for 15-30 HP or +max HP (10%)
- **Secret Rooms** — 20% chance on floors 3+, hidden behind secret walls, contain loot

### Terrain
- Water tiles (cold damage + extra hunger)
- Lava tiles (proximity heat damage within 2 tiles)
- Cave features on floors 4+ (1-4 caverns, 10-30 tiles each)

---

## 6. ENTITIES

### 30+ Enemy Types
- **Common (1-4):** Rat, Goblin, Spider, Skeleton, Orc, Zombie
- **Mid (5-10):** Troll, Vampire, Ghost, Necromancer, Ogre, Harpy, Wraith
- **Deep (11+):** Stone Colossus, Hydra, Mind Flayer, Lich, Demon, Mimic, Summoner, Chimera
- **Bosses:** Dread Lord (20), Flame Tyrant (15), Vampire (15), Elder Brain (12), Beast Lord (11), Crypt Guardian (9), Abyssal Horror (20 final)
- **Apex enemies:** 15% spawn chance on deep floors, special abilities

### Enemy Scaling
- HP: +18%/floor, Damage: +8%/floor, Defense: +0.3/floor

### NPCs
- 30% spawn chance. Sage (mana regen buff), Knight (defense buff). 30-turn duration.

---

## 7. PUZZLES & INTERACTABLES

- **Puzzle rooms** — 25% chance on floors 4+. Pressure plates, switches, combination locks. Reward: 30-80 gold.
- **Switches** — Toggle floor tiles, trigger puzzle logic or unlock doors
- **Pedestals** — Light with torch fuel (cost 10) to activate effects
- **Alchemy tables** — Identify potions/scrolls (limited uses)
- **Journal entries** — Flavor text for identified items
- **Vignettes** — Ambient lore text on walls (atmosphere)

---

## 8. UI & DISPLAY

### HUD (right sidebar, 21 chars)
- HP bar (color-coded, blinks at critical), Mana bar, Hunger, Torch fuel
- Equipment display (weapon + damage, armor + defense, ranged, ring)
- Status effects with remaining turns, turn counter, gold, kills

### Map View (58x20 viewport)
- Fog of war (8-tile FOV radius, explored tiles dimmed)
- 256-color themed rendering with 16-color fallback
- Unicode tile characters with ASCII fallback
- Projectile/spell animations

### Screens
- Help (?), Inventory (i), Character (c), Bestiary (B), Shop, Level-Up, Death, Victory

### Convenience
- Look mode (l) — examine any tile
- Auto-fight (a), Auto-explore (e), Rest (z)

---

## 9. PERSISTENCE

### Save/Load
- JSON save file with SHA256 checksum tamper protection
- Version migration (v1-v5)

### Lifetime Stats
- Games, wins, deaths, highest floor/level, longest run, total kills
- Win rate calculation

### Meta-Progression Unlocks
- Stat thresholds unlock bonuses for future runs (extra items, gold, HP, etc.)

### Session Recording
- JSONL action log per game
- Replay system for playback/analysis

---

## 10. BOT & AGENT MODES

### Bot (Decision Tree)
- 4-layer priority: Survival → Combat → Exploration → Resources
- Class-specific ability usage, spell casting, A* pathfinding
- Loop detection (6-position history), tile coverage tracking

### Agent (Claude-Powered Hybrid)
- Bot for routine turns, Claude Haiku for tactical triggers
- Triggers: low HP, boss, new floor, shop/shrine, stuck detection
- State serialization (~300 chars), fallback to bot on API failure
- Health monitoring, stuck detection, action/feature tracking

### Batch Mode
- Bot: N games headless, output stats
- Agent: N games headless, track API usage/cost/latency
- JSON output (--json), class rotation (--class), progress to stderr

---

## 11. CHALLENGE MODES

- **Ironman** — No saving, permadeath
- **Speedrun** — Floor time limit (100 + floor*20 turns)
- **Pacifist** — No killing non-boss enemies
- **Dark** — Torch fuel capped at 50

---

## 12. ADDITIONAL SYSTEMS

### Noise & Stealth
- Actions generate noise (walk=2, combat=8, spell=6). Rogue: 50% less.
- Noise decay 1/tile. Enemies alert within range.

### Traps (6+ types)
- Pit, Spikes, Poison Gas, Teleport, Alarm, Lightning
- 2 + 0.5*floor traps per floor
- Hidden until triggered/detected. Rogue: 30% passive detect.
- Disarm: 40% base + 3%/level (rogue only)

### Elemental Resistances
- Resist = 50% less damage, Vulnerable = 150%
- Armor/rings can grant resistances

### Enchantments (~10 types)
- Vampiric, Keen, Burning, Frostbite, Poison, Stun
- Applied via anvil (100 gold) or boss drops
- Proc on hit with varying chances

### Difficulty Presets
- Easy, Normal, Hard — multipliers on enemy HP/damage, items, food, XP, gold

---

## COMPLETENESS ASSESSMENT

**Status: FEATURE-COMPLETE.** Every system listed above is implemented and functional. No placeholder or stub features found.

**Minor gaps:**
- Boss phases implemented but limited complexity variation
- Agent mode depends on external API availability
- Some branch effects feel luck-based rather than puzzle-like
- Water tiles have damage but no movement/gameplay effects beyond that
