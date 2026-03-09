# Depths of Dread: D&D RPG Evolution Research

**Date:** 2026-02-28
**Purpose:** Research document for evolving Depths of Dread from a basic roguelike toward D&D-inspired RPG elements.
**Current Game:** `/Users/will/Scripts/dungeon.py` (~2,742 lines, Python curses, 15 floors, BSP generation)

---

## Table of Contents

1. [Monster Research](#1-monster-research)
2. [Map & Dungeon Design](#2-map--dungeon-design)
3. [Character Classes & RPG Systems](#3-character-classes--rpg-systems)
4. [RPG vs Roguelike Balance](#4-rpg-vs-roguelike-balance)
5. [Implementation Priorities](#5-implementation-priorities)

---

## 1. Monster Research

### 1.1 Current Monster Inventory

The game currently has 13 enemy types (including 3 bosses) with 6 AI behaviors:

| Monster | Char | HP | DMG | DEF | XP | Speed | AI | Floors | Special |
|---------|------|----|-----|-----|----|-------|----|--------|---------|
| Rat | r | 6 | 1-3 | 0 | 5 | 1.2 | chase | 1-5 | - |
| Bat | b | 4 | 1-2 | 0 | 3 | 1.5 | erratic | 1-6 | - |
| Goblin | g | 12 | 2-5 | 1 | 15 | 1.0 | chase | 1-8 | - |
| Skeleton | s | 18 | 3-6 | 2 | 25 | 0.8 | patrol | 3-10 | - |
| Orc | o | 25 | 3-8 | 3 | 35 | 0.9 | pack | 4-11 | - |
| Wraith | W | 30 | 4-8 | 2 | 50 | 1.0 | ambush | 6-13 | - |
| Dark Archer | A | 20 | 3-7 | 1 | 40 | 1.0 | ranged | 5-12 | - |
| Troll | T | 45 | 5-10 | 4 | 70 | 0.6 | chase | 7-14 | regen 1 |
| Demon | D | 55 | 6-12 | 5 | 100 | 1.0 | chase | 10-15 | - |
| Lich | L | 50 | 5-10 | 4 | 120 | 0.9 | summoner | 11-15 | - |
| Ogre King | O | 80 | 6-14 | 6 | 200 | 0.7 | chase | 5 | **BOSS** |
| Vampire Lord | V | 100 | 7-13 | 5 | 350 | 1.1 | ambush | 10 | **BOSS**, lifesteal |
| Dread Lord | & | 200 | 10-20 | 8 | 1000 | 1.0 | summoner | 15 | **BOSS**, regen 2 |

**Current AI types:** chase, erratic, patrol, pack, ambush, ranged, summoner

**Gap analysis:** All current monsters deal only basic melee/ranged damage. No poison, paralysis, teleportation, phasing, auras, or elemental effects. No monster "families" or themed groups. Only 3 boss encounters across 15 floors.

### 1.2 D&D 5e Monster Database Analysis

From the 5e Complete Index spreadsheet (4,148 monsters total), organized by type:

| Monster Type | Count | Dungeon-Relevant | Key Examples |
|-------------|-------|-----------------|--------------|
| Humanoid | 945 | 218 | Kobold, Drow, Duergar, Goblin, Orc, Gnoll |
| Monstrosity | 530 | 159 | Mimic, Basilisk, Rust Monster, Phase Spider, Bulette |
| Undead | 391 | 170 | Ghoul, Wight, Wraith, Vampire, Lich, Mummy Lord |
| Fiend | 330 | 62 | Imp, Quasit, Hell Hound, Vrock, Balor |
| Aberration | 328 | 95 | Mind Flayer, Beholder, Aboleth, Intellect Devourer |
| Beast | 317 | 71 | Giant Spider, Giant Bat, Cave Fisher, Darkmantle |
| Construct | 267 | 66 | Golem variants, Animated Armor, Shield Guardian |
| Fey | 218 | 32 | Dryad, Boggle, Darkling, Quickling |
| Dragon | 218 | 54 | Wyrmlings through Ancient, Deep Dragons |
| Plant | 156 | 42 | Myconid, Shrieker, Violet Fungus, Shambling Mound |
| Elemental | 153 | 40 | Mephits, Fire Snake, Salamander, Galeb Duhr |
| Giant | 133 | 35 | Ogre, Troll variants, Ettercap, Stone Giant |
| Celestial | 95 | 11 | Rare in dungeons, used for special encounters |
| Ooze | 67 | 35 | Gray Ooze, Gelatinous Cube, Ochre Jelly, Black Pudding |

### 1.3 SRD Monsters by Challenge Rating (Roguelike-Relevant)

These are the core SRD monsters most suitable for a dungeon-crawling roguelike, mapped to approximate floor tiers:

**Tier 1: Floors 1-3 (CR 0 to CR 1)**
- CR 0: Rat, Bat, Spider, Shrieker (alarm fungus), Lemure
- CR 1/4: Goblin, Skeleton, Zombie, Kobold, Giant Centipede, Violet Fungus, Flying Sword
- CR 1/2: Hobgoblin, Orc, Shadow, Gray Ooze, Rust Monster, Cockatrice
- CR 1: Ghoul, Giant Spider, Bugbear, Specter, Harpy, Imp, Dryad

**Tier 2: Floors 4-6 (CR 2 to CR 4)**
- CR 2: Ogre, Gargoyle, Mimic, Gelatinous Cube, Ghast, Ettercap, Gibbering Mouther
- CR 3: Minotaur, Basilisk, Phase Spider, Hell Hound, Wight, Mummy, Owlbear, Manticore
- CR 4: Ghost, Black Pudding, Chuul, Ettin, Lamia, Succubus/Incubus

**Tier 3: Floors 7-10 (CR 5 to CR 8)**
- CR 5: Troll, Wraith, Bulette, Earth Elemental, Fire Elemental, Flesh Golem, Roper, Vampire Spawn
- CR 6: Medusa, Chimera, Drider, Invisible Stalker, Wyvern
- CR 7: Oni, Stone Giant, Shield Guardian
- CR 8: Hydra, Frost Giant, Assassin, Chain Devil, Cloaker, Spirit Naga

**Tier 4: Floors 11-15 (CR 9 to CR 15+)**
- CR 9: Bone Devil, Clay Golem, Fire Giant, Treant
- CR 10: Aboleth, Stone Golem, Guardian Naga
- CR 11: Behir, Remorhaz, Roc
- CR 13: Vampire, Rakshasa, Storm Giant, Nalfeshnee
- CR 15: Mummy Lord, Purple Worm
- CR 16: Iron Golem, Marilith
- CR 21: Lich (true form)

### 1.4 Recommended New Monster Types (28 monsters across 5 tiers)

#### Tier 1: The Upper Depths (Floors 1-3) -- "Vermin & Petty Evil"

| Monster | Char | AI | Special Ability | D&D Inspiration |
|---------|------|----|-----------------|-----------------|
| **Centipede** | c | chase | **Poison bite** (2 dmg/turn for 5 turns) | Giant Centipede |
| **Kobold** | k | pack | **Trap-setter** (places caltrops on tiles) | Kobold |
| **Zombie** | z | chase | **Undying** (50% chance to stand back up 1 turn after death) | Zombie |
| **Fungus** | f | stationary | **Spore cloud** (blinds adjacent tiles for 3 turns when hit) | Violet Fungus |
| **Slime** | j | wander | **Acid body** (corrodes weapon on hit, -1 dmg permanently) | Gray Ooze |

#### Tier 2: The Haunted Halls (Floors 4-6) -- "Tricks & Terrors"

| Monster | Char | AI | Special Ability | D&D Inspiration |
|---------|------|----|-----------------|-----------------|
| **Mimic** | m | ambush | **Disguise** (appears as item/chest until player adjacent) | Mimic |
| **Phase Spider** | p | phase | **Phase shift** (teleports 3 tiles when hit, attacks from behind) | Phase Spider |
| **Gargoyle** | G | ambush | **Stone form** (immune to damage when stationary, looks like wall) | Gargoyle |
| **Ghast** | h | chase | **Paralysis** (melee hit has 25% chance to paralyze 2 turns) | Ghast |
| **Gelatinous Cube** | C | patrol | **Engulf** (moves onto player, traps them, acid dmg each turn) | Gelatinous Cube |
| **Basilisk** | B | chase | **Petrifying gaze** (player must avert eyes or slow 50% for 5 turns) | Basilisk |

#### Tier 3: The Dark Depths (Floors 7-10) -- "Elemental Fury"

| Monster | Char | AI | Special Ability | D&D Inspiration |
|---------|------|----|-----------------|-----------------|
| **Fire Elemental** | F | chase | **Burning aura** (1 dmg/turn to all adjacent), ignites on death (3x3) | Fire Elemental |
| **Medusa** | M | ranged | **Petrifying gaze** (ranged attack, player turns to stone = death if not saved) | Medusa |
| **Rust Monster** | R | chase | **Corrode** (degrades equipped armor by -2 DEF per hit) | Rust Monster |
| **Invisible Stalker** | i | ambush | **Invisible** (not shown on map, revealed only when adjacent or by Mapping scroll) | Invisible Stalker |
| **Minotaur** | n | chase | **Charge** (runs in straight line, double damage, stuns self 1 turn on miss) | Minotaur |
| **Roper** | P | stationary | **Tentacle grab** (pulls player 3 tiles toward it from range 6) | Roper |
| **Will-o-Wisp** | w | erratic | **Lightning touch** + **Consume life** (heals when player takes dmg nearby) | Will-o'-Wisp |

#### Tier 4: The Abyss (Floors 11-14) -- "Ancient Horrors"

| Monster | Char | AI | Special Ability | D&D Inspiration |
|---------|------|----|-----------------|-----------------|
| **Mind Flayer** | I | ranged | **Mind blast** (cone AoE, stuns 3 turns), **Devour brain** (instant kill if stunned) | Mind Flayer |
| **Beholder** | E | ranged | **Eye rays** (random effect each turn: damage/paralyze/disintegrate/fear) | Beholder |
| **Death Knight** | K | chase | **Hellfire orb** (ranged AoE fire+necrotic), **Command undead** (buffs nearby undead) | Death Knight |
| **Iron Golem** | X | patrol | **Poison breath** (cone, 3x3), **Magic immune** (spells do 0 damage) | Iron Golem |
| **Bone Devil** | d | chase | **Sting** (poison + fear for 5 turns), **Fly** (ignores water/lava) | Bone Devil |
| **Shadow Dragon** | S | ambush | **Shadow breath** (line, drains max HP by 10%), **Stealth** (invisible in darkness) | Shadow Dragon |

#### Tier 5: The Throne of Dread (Floor 15) -- "Endgame"

| Monster | Char | AI | Special Ability | D&D Inspiration |
|---------|------|----|-----------------|-----------------|
| **Pit Fiend** | H | summoner | **Wall of fire** (creates fire tiles), **Fireball** (ranged AoE), summons lesser fiends | Pit Fiend |
| **Dracolich** | Z | ranged | **Breath weapon** (alternates fire/cold/lightning), **Frightful presence** (fear aura) | Dracolich |

### 1.5 New AI Behaviors Required

| AI Type | Behavior | Used By |
|---------|----------|---------|
| **stationary** | Doesn't move, attacks when adjacent/in range | Fungus, Roper |
| **phase** | Teleports away when damaged, flanks player | Phase Spider |
| **charge** | Runs in straight lines toward player, high damage | Minotaur |
| **aura** | Passive damage/effect to all creatures in radius | Fire Elemental, Death Knight |
| **disguise** | Appears as item or terrain until triggered | Mimic, Gargoyle |
| **grab** | Pulls player toward self from range | Roper |
| **eye_ray** | Multiple random ranged effects per turn | Beholder |

### 1.6 Monster Special Abilities Catalog

These are the key ability categories to implement, drawing from D&D 5e's monster trait system:

**Status Effects (new)**
| Effect | Duration | Mechanic | Inflicted By |
|--------|----------|----------|-------------|
| Poison | 3-8 turns | X dmg per turn | Centipede, Bone Devil, Iron Golem |
| Paralysis | 2-4 turns | Cannot move or attack | Ghast, Mind Flayer |
| Fear | 3-6 turns | Must move away from source, -50% hit chance | Bone Devil, Shadow Dragon, Dracolich |
| Petrification | 3-5 turns | Speed reduced to 0 (partial) or death (full) | Basilisk, Medusa |
| Corrode | Permanent | Weapon or armor loses stats | Rust Monster, Slime |
| Engulf | Until escape | Trapped, acid damage per turn, STR check to escape | Gelatinous Cube |

**Passive Abilities (new)**
| Ability | Mechanic | Monsters |
|---------|----------|----------|
| Damage Aura | Adjacent creatures take X dmg/turn | Fire Elemental |
| Magic Immunity | Spells deal 0 damage | Iron Golem |
| Invisibility | Not rendered until adjacent or detected | Invisible Stalker |
| Undying | % chance to revive 1 turn after death | Zombie |
| Disguise | Appears as item/terrain | Mimic, Gargoyle |
| Phase | Teleports when damaged | Phase Spider |
| Flying | Ignores water, lava, pits | Bone Devil, Will-o-Wisp |
| Spore Cloud | AoE blind effect when hit | Fungus |

**Active Abilities (new)**
| Ability | Mechanic | Monsters |
|---------|----------|----------|
| Pull/Grab | Drags player X tiles toward monster | Roper |
| Charge | Straight-line rush, double damage | Minotaur |
| Mind Blast | Cone AoE stun | Mind Flayer |
| Eye Rays | Random effect from a table each turn | Beholder |
| Breath Weapon | Line or cone AoE, elemental damage | Shadow Dragon, Dracolich |
| Trap Setting | Places hazard tiles | Kobold |
| Life Drain | Reduces max HP (not just current) | Shadow Dragon |
| Summon | Spawns weaker allies | Death Knight, Pit Fiend |

### 1.7 Monster Families & Themed Zones

Organize monsters into families that appear together, creating themed dungeon sections:

**The Beast Lair (Floors 1-3)**
- Rats, Bats, Centipedes, Giant Spiders
- Environmental: webs (slow movement), burrows (surprise spawns)
- Mini-boss: **Brood Mother** (giant spider, spawns spiderlings, web traps)

**The Goblin Warren (Floors 2-4)**
- Goblins, Kobolds, Orcs, Hobgoblins
- Environmental: crude traps, barricades, alarm gongs
- Mini-boss: **Goblin Warchief** (buffs nearby goblins, calls reinforcements)

**The Undead Crypt (Floors 4-7)**
- Zombies, Skeletons, Ghasts, Wights, Wraiths, Specters
- Environmental: coffins (spawn enemies), desecrated shrines, darkness zones
- Mini-boss: **Crypt Lord** (raises fallen enemies as zombies, fear aura)

**The Fungal Caverns (Floors 5-8)**
- Fungus, Slime, Myconids, Gelatinous Cube
- Environmental: spore clouds, acid pools, bioluminescent lighting
- Mini-boss: **Myconid Sovereign** (AoE spore confusion, summons myconids, heals from plant allies)

**The Elemental Forge (Floors 7-10)**
- Fire Elemental, Rust Monster, Iron Golem, Salamanders, Magma Mephits
- Environmental: lava rivers, forges, heat damage zones, steam vents
- Mini-boss: **Forge Guardian** (fire aura, creates lava tiles, immune to fire spells)

**The Mind's Eye (Floors 9-12)**
- Mind Flayer, Beholder, Invisible Stalker, Aberrations
- Environmental: psychic interference (random confusion), reality warps, anti-magic zones
- Mini-boss: **Elder Brain** (dominate nearby enemies to attack player, AoE psychic damage)

**The Bone Pit (Floors 11-14)**
- Bone Devils, Death Knights, Liches, Shadow Dragons
- Environmental: soul traps, necrotic aura zones, darkness
- Mini-boss: **Bone Colossus** (assembled from defeated skeletons, grows stronger as you kill undead on the floor)

### 1.8 Expanded Boss Roster

Current: 3 bosses at floors 5, 10, 15. Recommended: boss or mini-boss every 2-3 floors.

| Floor | Boss/Mini-boss | HP | Special Mechanics |
|-------|---------------|----|--------------------|
| 2 | **Brood Mother** | 40 | Spawns spiderlings, web traps slow player, vulnerable to fire |
| 4 | **Goblin Warchief** | 55 | Calls reinforcements every 5 turns, throws bombs, flees when low |
| 5 | **Ogre King** (existing) | 80 | Keep as-is |
| 7 | **Crypt Lord** | 90 | Raises fallen enemies, fear aura, drain touch, 2 phases |
| 9 | **Forge Guardian** | 110 | Fire aura, creates lava, immune to fire, vulnerable to cold |
| 10 | **Vampire Lord** (existing) | 100 | Keep lifesteal, add bat-form escape at 25% HP |
| 12 | **Elder Brain** | 130 | Mind control (turns your summons/dominated enemies against you), psychic cone |
| 14 | **Bone Colossus** | 160 | Regenerates from corpses on the floor, AoE bone shrapnel, 3 phases |
| 15 | **The Dread Lord** (existing) | 200 | Keep as final boss, add phase transitions |

### 1.9 Environmental Hazards Tied to Monsters

| Hazard | Effect | Associated Zone |
|--------|--------|-----------------|
| **Spider Webs** | Halves movement speed, flammable | Beast Lair |
| **Poison Gas** | 1 dmg/turn while in tile | Fungal Caverns |
| **Bone Piles** | Zombies/skeletons can rise from them | Undead Crypt |
| **Acid Pools** | 3 dmg/turn, dissolves leather armor | Fungal Caverns |
| **Steam Vents** | Periodic burst of 5 dmg, blocks vision | Elemental Forge |
| **Psychic Static** | Random confusion (move in wrong direction) | Mind's Eye |
| **Soul Traps** | Drains 5 mana when stepped on | Bone Pit |
| **Alarm Gongs** | Alerts all enemies on floor when triggered | Goblin Warren |
| **Desecrated Ground** | Undead regenerate 1 HP/turn while on these tiles | Undead Crypt |
| **Anti-Magic Zones** | Cannot cast spells in these tiles | Mind's Eye |

---

## 2. Map & Dungeon Design

### 2.1 Current Generation System

The game uses BSP (Binary Space Partitioning) exclusively:
- `BSPNode` class splits the 80x40 map recursively (depth 3-5, min_size 7-10)
- Rooms created within leaf nodes, L-shaped corridors connect them
- Extra corridors added for loops (1-3 random room connections)
- Doors placed at corridor chokepoints (30% chance)
- Cave features (drunkard's walk) added on floors 4+
- Water pools on floors 7+, lava on floors 10+
- 5 floor themes: Dungeon (1-3), Caverns (4-6), Catacombs (7-9), Hellvault (10-12), Abyss (13-15)

**Strengths:** Reliable, guarantees connectivity, room count control
**Weaknesses:** Rectangular rooms only, corridors feel samey, no special room shapes, limited environmental storytelling

### 2.2 Dungeon Generation Algorithms

| Algorithm | Control | Visual Style | Repair Needed | Complexity | Best For |
|-----------|---------|-------------|---------------|-----------|----------|
| **BSP** (current) | High | Geometric | De-grid with jitter | Low | Structured dungeons, guaranteed room counts |
| **Cellular Automata** | Medium | Organic caves | Connectivity fixes | Medium | Natural caverns, mine shafts |
| **Drunkard's Walk** | Low | Chaotic tunnels | Prefab injection | Very Low | Winding passages, organic caves |
| **Wave Function Collapse** | High | Themed/consistent | Contradiction handling | High | Art-directed, themed areas |
| **Graph Grammars** | Very High | Abstract/controlled | Rule verification | Very High | Key-lock progression, quest structures |
| **Hybrid (BSP + Walker)** | Medium-High | Mixed | Boundary protection | Medium | Best of both worlds |

**Recommendation:** Use a hybrid approach:
1. Keep BSP as the base for structured floors (Dungeon, Catacombs)
2. Add cellular automata for cave floors (Caverns)
3. Use prefab/template rooms for special encounters
4. Reserve drunkard's walk for connecting organic areas

### 2.3 Themed Dungeon Zones

Expand from 5 generic themes to 8+ distinct zone types, each with unique tile types, generation rules, and atmosphere:

#### Zone: The Crypt
- **Generation:** BSP with narrow rooms (coffin chambers), long corridors
- **Tiles:** Coffins (lootable but may spawn undead), tombstones (lore text), crumbling walls (can be broken)
- **Lighting:** Very dark, torches matter more, eerie blue light from spectral sources
- **Encounters:** Undead themed, coffin ambushes
- **Floors:** 4-6

#### Zone: The Fungal Caverns
- **Generation:** Cellular automata (organic cave shapes)
- **Tiles:** Mushroom patches (food source), spore clouds (vision-blocking), acid pools, bioluminescent fungi (natural light sources)
- **Lighting:** Dim natural glow, specific bright fungi
- **Encounters:** Plant, Ooze, Myconid themed
- **Floors:** 5-7

#### Zone: The Library / Arcane Sanctum
- **Generation:** BSP with larger rectangular rooms, book-lined corridors
- **Tiles:** Bookshelves (lore/spell scrolls), enchanting tables, runic circles, animated books
- **Lighting:** Magical ambient light, reading lamp spots
- **Encounters:** Constructs, Arcane themed
- **Special:** Higher scroll drop rate, spell learning opportunities
- **Floors:** 6-8

#### Zone: The Prison
- **Generation:** Grid-based (cell blocks), central corridors, guard posts
- **Tiles:** Locked cells (keys needed), chains, torture devices, prisoner NPCs
- **Lighting:** Intermittent torches
- **Encounters:** Escaped prisoners, guards, undead prisoners
- **Special:** NPC allies can be freed, key-and-lock puzzles
- **Floors:** 3-5

#### Zone: The Forge / Foundry
- **Generation:** Large central rooms (forge halls) with smaller storage rooms
- **Tiles:** Anvils (weapon upgrade), lava channels, conveyor belts (forced movement), steam vents
- **Lighting:** Bright from lava/fire
- **Encounters:** Constructs, Elementals, Salamanders
- **Special:** Crafting opportunities, trap mechanisms
- **Floors:** 8-10

#### Zone: The Sewers / Aqueducts
- **Generation:** Drunkard's walk (winding tunnels), water channels
- **Tiles:** Flowing water (pushes player), grates (restricted passage), drain pools
- **Lighting:** Dim, reflections off water
- **Encounters:** Oozes, vermin, wererats
- **Floors:** 2-4

#### Zone: The Throne Room / Great Hall
- **Generation:** Single massive room with columns, antechambers
- **Tiles:** Columns (cover), throne (lore trigger), trophy cases (loot), banners
- **Lighting:** Dramatic, torch-lined
- **Purpose:** Boss arena, always appears on boss floors
- **Floors:** 5, 10, 15 (boss floors)

#### Zone: The Abyssal Rift
- **Generation:** Hybrid (BSP islands connected by narrow bridges over void)
- **Tiles:** Void tiles (instant death if fall), bridges (narrow), floating platforms
- **Lighting:** Otherworldly glow, shifting colors
- **Encounters:** Fiends, Aberrations
- **Floors:** 13-15

### 2.4 Special Room Types

| Room Type | Mechanic | Frequency |
|-----------|----------|-----------|
| **Trap Room** | Pressure plates, dart traps, pit traps, collapsing ceiling. Skill check (DEX-based) to avoid. Reward: treasure behind traps. | 1 per 3 floors |
| **Puzzle Room** | Lever sequences, colored switches, pattern matching. Reward: powerful item or shortcut. | 1 per 4 floors |
| **Treasure Vault** | Locked door (key from boss or elite enemy), contains high-tier loot. | 1 per 5 floors |
| **Arena** | Sealed room, waves of enemies, reward after clearing. No escape until done. | 1 per 4 floors |
| **Fountain Room** | Healing fountain (limited uses), sometimes cursed. | 1 per 3 floors |
| **Summoning Circle** | Risk/reward: step in to gain power or face powerful enemy. | 1 per 5 floors |
| **Collapsed Section** | Partially blocked, requires clearing rubble. Secret shortcut. | Random |
| **Library Alcove** | Contains lore scrolls, spell learning opportunity, journal entries. | In Library zones |

### 2.5 Vertical Elements

Terminal roguelikes can suggest verticality through mechanics:

- **Pits:** Tile type that drops player to the floor below (or damages). Enemies can be knocked in.
- **Balconies/Ledges:** Elevated tiles where ranged enemies have advantage. Player needs stairs or teleport to reach.
- **Chasms:** Wide gaps requiring bridge items or teleport to cross. Shortcut potential.
- **Crumbling floors:** Tiles that break after being stepped on, creating pits.
- **Multi-level rooms:** A "grand chamber" that spans 2 floors, with stairs internal to the room.

### 2.6 Secret Passages & Hidden Rooms

- **Hidden doors:** Walls that can be discovered by searching adjacent tiles (DEX/INT check or dedicated 's' key)
- **Cracked walls:** Visual hint (different character '#' vs '.' vs '%'), breakable with attack
- **Secret levers:** Interact with bookshelf/statue to reveal passage
- **Illusory walls:** Walk through what appears to be wall (detected by high perception or Mapping scroll)
- **Discovery rate:** ~1-2 hidden rooms per floor, containing better loot or shortcuts

### 2.7 Environmental Storytelling

Add discoverable lore elements:

- **Adventurer corpses:** "You find the remains of a previous adventurer..." with journal entry and loot
- **Wall inscriptions:** Hints about upcoming boss weaknesses, floor layout clues
- **NPC ghosts:** Non-hostile spirits that share lore or warnings
- **Evidence of battles:** Scorch marks, broken weapons, blood trails leading to treasure or danger
- **Dungeon history:** Progressive story pieces that reveal why the Dread Lord exists
- **Graffiti:** "Turn back" / "The third lever is a trap" / "Beware the eye"

### 2.8 Procedural Generation Enhancements

**Immediate improvements to current BSP:**
1. Room shape variety: Add circular rooms (approximated), L-shaped rooms, T-shaped rooms
2. Room size variety: Vary min_room based on floor theme (tight crypts vs. grand halls)
3. Corridor variety: Winding corridors (not just L-shaped), varying width
4. Pillar placement: Add columns within large rooms for tactical cover

**Medium-term additions:**
1. Cellular automata generator for cave floors (replace current `_add_cave_features` drunkard walk)
2. Prefab room templates: Hand-designed special rooms inserted into BSP structure
3. Room connection graph: Ensure interesting loops, dead ends with treasure, branching paths

**Long-term:**
1. Wave Function Collapse for themed tileset consistency
2. Graph grammar for key-lock puzzle generation

---

## 3. Character Classes & RPG Systems

### 3.1 Current Player System

```
Player stats: HP(30), MP(20), STR(5), DEF(1), Level, XP, Gold, Hunger(100)
Equipment slots: Weapon, Armor, Ring, Bow
Spells: Fireball, Lightning Bolt, Heal, Teleport, Freeze (all unlocked at start)
Level up: +4-8 HP, +2-5 MP, +1 STR, +1 DEF (fixed progression, no choice)
```

**Key limitation:** Every run plays identically. No build variety, no meaningful choices at level-up, no class identity.

### 3.2 D&D 5e Class Reference

From the 5e Complete Index (199 class/subclass entries) and SRD analysis:

| Class | Hit Die | Primary Stat | Armor | Weapons | Key Feature | Roguelike Relevance |
|-------|---------|-------------|-------|---------|-------------|-------------------|
| Barbarian | d12 | STR | Light/Med/Shield | Simple+Martial | Rage (damage resistance + bonus damage) | HIGH: tanky melee |
| Fighter | d10 | STR/DEX | All | All | Action Surge, Extra Attack | HIGH: versatile combat |
| Rogue | d8 | DEX | Light | Simple+Rapier+Crossbow | Sneak Attack, Cunning Action | HIGH: stealth/position |
| Ranger | d10 | DEX/WIS | Light/Med/Shield | Simple+Martial | Favored Enemy, Natural Explorer | MEDIUM: ranged + tracking |
| Cleric | d8 | WIS | Light/Med/Shield | Simple | Divine Magic, Channel Divinity | HIGH: healing + buffs |
| Wizard | d6 | INT | None | Dagger/Staff | Spellbook, Arcane Recovery | HIGH: powerful magic, fragile |
| Paladin | d10 | STR/CHA | All | Simple+Martial | Divine Smite, Lay on Hands | MEDIUM: complex hybrid |
| Sorcerer | d6 | CHA | None | Simple | Metamagic, Innate casting | MEDIUM: overlaps with Wizard |
| Monk | d8 | DEX/WIS | None | Simple+Shortsword | Unarmed combat, Ki | MEDIUM: unique but niche |
| Warlock | d8 | CHA | Light | Simple | Eldritch Blast, Pact features | LOW: patron system is complex |
| Bard | d8 | CHA | Light | Simple+Rapier+Crossbow | Inspiration, Jack-of-all-trades | LOW: support role, no party |
| Druid | d8 | WIS | Light/Med/Shield | Simple | Wild Shape, Nature magic | LOW: shapeshifting complex |
| Artificer | d8 | INT | Light/Med/Shield | Simple | Infusions, Crafting | LOW: crafting system is deep |

### 3.3 Recommended Starting Classes (6 classes)

For a single-player roguelike, classes need to be mechanically distinct without requiring party dynamics. Here are 6 classes that cover the playstyle spectrum:

#### 1. WARRIOR (Fighter/Barbarian hybrid)
**Fantasy:** The unstoppable melee combatant. Tank hits, deal heavy damage.

| Stat | Base | Per Level |
|------|------|-----------|
| HP | 40 | +6-10 |
| MP | 5 | +1-2 |
| STR | 7 | +2 |
| DEF | 3 | +1 |

- **Starting gear:** Short Sword, Leather Armor, 5 Rations
- **Equipment:** Can use ALL weapons and ALL armor
- **Class ability: Rage** (3 uses per floor) -- +50% melee damage, -25% damage taken for 8 turns. Cannot cast spells during Rage.
- **Level 3: Cleave** -- Melee attacks hit all adjacent enemies (not just target)
- **Level 5: Second Wind** -- Restore 25% max HP once per floor
- **Level 7: Berserker** -- When below 30% HP, auto-enter free Rage
- **Spell access:** None (relies entirely on items for magic effects)
- **Playstyle:** Aggressive melee. Charge in, tank damage, cleave through groups. Simple to play, hard to master resource management (Rage uses, healing items).

#### 2. MAGE (Wizard)
**Fantasy:** Glass cannon. Devastating spells, paper-thin defenses.

| Stat | Base | Per Level |
|------|------|-----------|
| HP | 20 | +3-5 |
| MP | 35 | +4-7 |
| STR | 2 | +1 |
| DEF | 0 | +0 |

- **Starting gear:** Staff (low damage, +2 spell dmg), Robe (0 DEF, +3 MP), 3 Scrolls
- **Equipment:** Staves and daggers only. Robes only (no metal armor).
- **Class ability: Arcane Recovery** -- Rest to recover 30% max MP (once per floor)
- **Spell access: ALL spells** + exclusive spells:
  - **Level 1:** Fireball, Lightning Bolt, Freeze, Teleport, Heal (all unlocked)
  - **Level 3: Magic Missile** -- Auto-hit ranged attack, never misses, low damage
  - **Level 5: Chain Lightning** -- Bounces to 3 nearby enemies
  - **Level 7: Disintegrate** -- Single target massive damage (costs 25 MP)
  - **Level 9: Meteor** -- 5x5 AoE, destroys terrain, huge damage (costs 35 MP)
- **Passive: Mana Shield** -- Can spend MP instead of HP for incoming damage (2 MP = 1 HP)
- **Playstyle:** Stay at range, manage mana carefully, devastating when resources are available but extremely vulnerable when dry. High skill ceiling.

#### 3. ROGUE (Rogue/Assassin)
**Fantasy:** The shadow-striker. Unseen, deadly, evasive.

| Stat | Base | Per Level |
|------|------|-----------|
| HP | 25 | +4-6 |
| MP | 15 | +2-3 |
| STR | 4 | +1 |
| DEF | 1 | +1 |

- **Starting gear:** Dagger (fast, +crit chance), Leather Armor, 10 Throwing Daggers, Lockpick Set
- **Equipment:** Light weapons only (daggers, rapiers, short swords). Light armor only.
- **Class ability: Sneak Attack** -- 2x damage when attacking unaware enemy or from stealth. 3x at level 7.
- **Level 3: Stealth** -- Toggle ability. While stealthy: invisible to enemies beyond 3 tiles, move at half speed, first attack from stealth is Sneak Attack.
- **Level 5: Evasion** -- 50% chance to completely avoid AoE damage (spells, breath weapons, traps)
- **Level 7: Shadow Step** -- Teleport to any tile within 4 spaces that is not in enemy FOV (3 uses/floor)
- **Passive: Lockpick** -- Can open locked chests/doors without keys. Can disarm traps.
- **Passive: Perception** -- Automatically detects hidden doors and traps within 4 tiles.
- **Playstyle:** Methodical. Scout ahead, pick off enemies one at a time from stealth, avoid fair fights. Excels at exploration and treasure-finding.

#### 4. CLERIC (Cleric)
**Fantasy:** The divine protector. Healing, buffs, undead-slayer.

| Stat | Base | Per Level |
|------|------|-----------|
| HP | 30 | +5-8 |
| MP | 25 | +3-5 |
| STR | 4 | +1 |
| DEF | 2 | +1 |

- **Starting gear:** Mace (bonus damage to undead), Chain Mail, Holy Symbol (+healing power)
- **Equipment:** Simple weapons + maces. All armor up to medium.
- **Class ability: Turn Undead** (3 uses/floor) -- All undead within 5 tiles flee for 5 turns. At level 7, weak undead are destroyed outright.
- **Spell access: Healing + Divine:**
  - **Level 1:** Heal (enhanced: heals 50% more than other classes), Bless (+2 STR/DEF for 20 turns)
  - **Level 3: Smite** -- Melee attack + radiant damage (extra vs undead/fiends)
  - **Level 5: Sanctuary** -- Creates a 3x3 safe zone, enemies cannot enter for 5 turns
  - **Level 7: Resurrection** -- After dying, revive with 25% HP (once per run)
  - **Level 9: Holy Nova** -- AoE damage to all enemies in LOS, heals player
- **Passive: Divine Favor** -- Shrines always give positive results (never cursed)
- **Playstyle:** Sustainable. Excellent self-healing keeps you alive through attrition. Strong against undead. Moderate damage but exceptional survival. Best class for learning the game.

#### 5. RANGER (Ranger)
**Fantasy:** The master archer. Long-range precision, nature affinity.

| Stat | Base | Per Level |
|------|------|-----------|
| HP | 28 | +4-7 |
| MP | 15 | +2-4 |
| STR | 5 | +1 |
| DEF | 1 | +1 |

- **Starting gear:** Long Bow, Short Sword, Leather Armor, 20 Arrows, 5 Rations
- **Equipment:** All ranged weapons, light/medium weapons, light/medium armor.
- **Class ability: Mark Prey** -- Designate one enemy. All attacks against marked enemy deal +30% damage. Persists until target dies.
- **Level 3: Volley** -- Fire arrows at all enemies within 3 tiles of a target point (AoE ranged)
- **Level 5: Nature's Bounty** -- Identify all food on the floor, slower hunger depletion (-30%)
- **Level 7: Piercing Shot** -- Arrow passes through all enemies in a line, full damage to each
- **Passive: Eagle Eye** -- Extended FOV radius (+3 tiles), see enemy HP
- **Passive: Tracker** -- Footprints of enemies visible on tiles they've walked on recently
- **Playstyle:** Positional. Keep distance, kite enemies through corridors, use terrain to your advantage. Arrow management is key resource. Very strong in open rooms, weaker in tight spaces.

#### 6. NECROMANCER (Warlock/Necromancy Wizard hybrid)
**Fantasy:** The dark summoner. Raise the dead, drain life, command minions.

| Stat | Base | Per Level |
|------|------|-----------|
| HP | 22 | +3-6 |
| MP | 30 | +3-6 |
| STR | 3 | +1 |
| DEF | 0 | +0 |

- **Starting gear:** Bone Wand (ranged necrotic), Tattered Robes, Skull Talisman (+summon HP)
- **Equipment:** Staves, wands, daggers. Robes only.
- **Class ability: Raise Dead** (costs 15 MP) -- Reanimate a killed enemy to fight for you. Max 2 minions at once. Minions have 50% of original enemy's stats.
- **Level 3: Life Drain** -- Ranged attack that heals player for 50% of damage dealt
- **Level 5: Corpse Explosion** -- Detonate a corpse for AoE damage based on original enemy's max HP
- **Level 7: Death Pact** -- Sacrifice a minion to fully heal player
- **Level 9: Army of the Dead** -- Raise all corpses on the floor (once per floor)
- **Passive: Soul Harvest** -- Gain +2 max HP permanently for every 10 kills
- **Playstyle:** Resource management of corpses and minions. Let minions tank while you drain life from range. Snowball class -- gets stronger the more enemies you kill. Risky early game, dominant late game.

### 3.4 Stat System Enhancement

**Current:** HP, MP, STR, DEF, Hunger
**Proposed additions:**

| Stat | Abbreviation | Effect | Primary For |
|------|-------------|--------|------------|
| HP | HP | Health points | Warrior, Cleric |
| MP | MP | Mana/spell points | Mage, Necromancer |
| STR | STR | Melee damage bonus | Warrior |
| DEX | DEX | Ranged damage, evasion, stealth, trap disarm | Rogue, Ranger |
| INT | INT | Spell damage, mana regen, hidden room detection | Mage, Necromancer |
| WIS | WIS | Healing power, divine spell effectiveness, trap detection | Cleric |
| DEF | DEF | Damage reduction (from armor + base) | All |

**Implementation note:** DEX, INT, WIS are new. Each class has 1-2 primary stats that scale faster. Non-primary stats still grow but slowly. This creates natural build divergence without requiring a full D&D ability score system.

### 3.5 Spell School System

Replace the current flat spell list with schools that tie to classes:

| School | Spells | Available To |
|--------|--------|-------------|
| **Evocation** (damage) | Fireball, Lightning Bolt, Chain Lightning, Magic Missile, Meteor, Disintegrate | Mage |
| **Restoration** (healing) | Heal, Greater Heal, Bless, Sanctuary, Resurrection, Holy Nova | Cleric, (Mage: Heal only) |
| **Necromancy** (death) | Life Drain, Raise Dead, Corpse Explosion, Death Pact, Army of the Dead | Necromancer |
| **Transmutation** (utility) | Teleport, Haste, Fortify, Transmute (change item properties) | Mage, Cleric |
| **Illusion** (trickery) | Invisibility (short duration), Mirror Image (25% miss chance), Phantasm (fear AoE) | Rogue, Mage |
| **Abjuration** (defense) | Shield (+5 DEF for 10 turns), Freeze, Dispel (remove enemy buffs), Ward (absorb next X damage) | Mage, Cleric |
| **Nature** (ranger) | Entangle (root enemies in area), Barkskin (+DEF), Cure Poison, Beast Sense (reveal all enemies on floor) | Ranger |
| **War** (combat) | Smite, Cleave (AoE melee), Battle Cry (buff allies), Charge | Warrior (limited), Cleric |

### 3.6 Level-Up Choices

Replace automatic stat gains with meaningful decisions:

**Every level:** Choose ONE of:
1. **Stat Boost:** +2 to one stat (STR, DEX, INT, WIS)
2. **HP Boost:** +8 max HP
3. **MP Boost:** +6 max MP
4. **New Spell:** Learn a spell from your class list (if available)

**Every 3 levels (3, 6, 9, 12):** Choose a **Feat** (one-time permanent bonus):

| Feat | Effect | Best For |
|------|--------|---------|
| **Tough** | +20 max HP | Warrior, Cleric |
| **Arcane Adept** | +15 max MP, spells cost -2 MP | Mage |
| **Quick Hands** | +30% attack speed | Rogue, Ranger |
| **Iron Stomach** | Hunger depletes 50% slower | All (survival) |
| **Lucky** | +15% crit chance | Rogue |
| **Spell Penetration** | Spells ignore magic resistance | Mage, Necromancer |
| **Heavy Armor Master** | -2 damage from all sources (flat) | Warrior, Cleric |
| **Dual Wielder** | Equip two weapons, attack with both | Rogue, Warrior |
| **Spell Sniper** | Spell range +50% | Mage, Ranger |
| **Sentinel** | Enemies that attack you in melee can't move away next turn | Warrior |

### 3.7 Equipment Class Restrictions

| Equipment Type | Warrior | Mage | Rogue | Cleric | Ranger | Necromancer |
|---------------|---------|------|-------|--------|--------|-------------|
| Heavy Armor (Plate, Chain) | Yes | No | No | Medium only | No | No |
| Light Armor (Leather, Studded) | Yes | No | Yes | Yes | Yes | No |
| Robes | No | Yes | No | No | No | Yes |
| All Melee Weapons | Yes | No | No | No | No | No |
| Light Melee (Dagger, Rapier) | Yes | Yes | Yes | No | Yes | Yes |
| Maces/Hammers | Yes | No | No | Yes | No | No |
| Bows | Yes | No | No | No | Yes | No |
| Staves | No | Yes | No | Yes | No | Yes |
| Wands | No | Yes | No | No | No | Yes |
| Shields | Yes | No | No | Yes | No | No |

**New slot: Off-hand** -- Shield (DEF bonus) OR second weapon (dual-wield) OR torch (light) OR focus item (+spell damage).

---

## 4. RPG vs Roguelike Balance

### 4.1 The Spectrum

| Pure Roguelike | | | | RPG-Heavy Roguelite |
|---------------|--|--|--|---------------------|
| NetHack | Brogue | DCSS | Hades | Dead Cells |
| No meta-progression | No meta-progression | No meta-progression | Story meta + upgrades | Full upgrade paths |
| Extreme depth | Elegant simplicity | Deep but accessible | Accessible depth | Action-first |
| Hidden mechanics | Transparent mechanics | Transparent mechanics | Transparent mechanics | Transparent mechanics |
| Hundreds of hours | Dozens of hours | Hundreds of hours | 30-60 hours | 30-50 hours |

### 4.2 What Makes the Best Hybrid Games Work

**Lessons from DCSS (Pure Roguelike):**
- 648 starting combinations (race x class), each genuinely distinct
- "No no-brainers" -- every choice involves meaningful tradeoffs
- No grinding: shops don't buy items, limited resources prevent low-risk farming
- Skill > randomness, but randomness forces adaptation
- 1% win rate creates genuine achievement
- God/religion system adds another axis of build customization
- Handmade vaults within procedural dungeons prevent total randomness

**Lessons from Hades (Roguelite):**
- Death IS progress: returning to hub advances story and relationships
- Dialog bits advance with each run, making every attempt meaningful
- 10 hours of contextual dialog written for chained narrative events
- Meta-progression (Mirror of Night upgrades) provides between-run investment
- Boon system (god powers) creates unique builds each run within familiar framework
- Difficulty scales through "Heat" system for experienced players
- Accessibility: narrative rewards engagement regardless of skill level

**Lessons from Slay the Spire (Deckbuilder Roguelite):**
- Build-defining choices at every step (card selection, relic acquisition)
- Each run tells a "build story" -- what synergy did you find?
- 4 characters with fundamentally different mechanics
- Ascension levels provide long-term progression without trivializing the game
- Information is transparent -- you can always calculate if a play is correct

**Lessons from Dead Cells (Action Roguelite):**
- Permanent unlocks (weapons, mutations) expand the possibility space
- Biome choice creates route variety within the same game
- Boss cell difficulty levels as meta-progression goal
- Dual scaling: player skill AND build quality both matter

**Lessons from Brogue (Minimalist Roguelike):**
- Depth through interaction: items combine in emergent ways
- Every potion, scroll, and wand has multiple uses depending on context
- No character classes -- the dungeon defines your build
- Transparency: all mechanics are discoverable through play

### 4.3 Permadeath vs Meta-Progression: Recommendation for Depths of Dread

**Recommendation: Layered meta-progression that respects the roguelike core.**

#### What Dies With You (Per-Run):
- Character level, stats, equipment, inventory, gold
- Floor progress
- Spells learned during the run
- Minions, buffs, status effects

#### What Persists Between Runs (Meta-Progression):

**Tier 1: Knowledge (always persists)**
- Potion/scroll identification carries between runs (once identified, always identified)
- Monster bestiary: enemies you've killed are documented with their abilities
- Map knowledge: floor themes you've seen are previewed before entering
- Lore fragments: collected story pieces persist in a journal

**Tier 2: Unlocks (milestone-based)**
- New character classes unlock after specific achievements (e.g., "Kill 50 undead" unlocks Cleric)
- New starting items unlock after reaching certain floors
- New shrine types appear after praying X times
- Challenge modifiers unlock after first win (like Hades' Heat system)

**Tier 3: Permanent Upgrades (currency-based, limited)**
- "Soul Essence" collected from bosses and elite enemies
- Spend at a meta-hub between runs on SMALL permanent bonuses:
  - +1 starting HP per class (cap: +10)
  - +1 starting MP per class (cap: +5)
  - +5% shop discount (cap: -25%)
  - Start with 1 identified potion type
  - Unlock additional starting item options
- **Critical:** These should provide convenience, NOT power. A skilled player should be able to win with zero meta-upgrades. The upgrades make the early game smoother, not the late game trivial.

**Tier 4: Cosmetic/Story (always persists)**
- Death counter and statistics
- Achievement system (first boss kill, first win, speed run, pacifist floor, etc.)
- Character gravestones appear in future runs where you died
- NPCs remember you across runs (like Hades' dialog system)

### 4.4 Build Depth in a Permadeath Game

**The Goldilocks principle:** Builds should be deep enough to feel distinct but not so deep that dying feels like losing hours of planning.

- **Character creation:** Quick (choose class + name, 30 seconds)
- **First meaningful choice:** Within 2 minutes (first item, first enemy encounter)
- **Build identity established:** By floor 3 (class abilities + early equipment)
- **Build peaks:** Floors 8-12 (all major abilities, key equipment found)
- **Average run length:** 30-60 minutes (enough to invest, not enough to devastate on death)

**DCSS principle applied:** "Not all combinations play equally well." Some class + floor RNG combos will be harder. That's a feature, not a bug. It makes winning feel earned.

### 4.5 Lore Delivery System

Drawing from Hades' narrative design:

**In-dungeon lore:**
- Wall inscriptions (1-2 per floor, randomized from a pool)
- Adventurer journals (found on corpses, tell stories of previous delvers)
- Boss pre-fight dialog (each boss has 3-5 lines that rotate across runs)
- NPC ghosts on specific floors (conversation advances with each run)

**Between-run lore (if hub is implemented):**
- Death dialog: Hypnos-style quips about how you died
- NPC conversations that advance incrementally
- Bestiary entries that reveal monster backstories as you fight them
- The story of the Dread Lord and Thornhaven unfolds across 20+ runs

**Lore structure:**
- **Layer 1:** What is the Dread Lord? (Revealed in first 3-5 runs through basic inscriptions)
- **Layer 2:** Why does the dungeon exist? (Revealed through adventurer journals, runs 5-15)
- **Layer 3:** What happened to Thornhaven? (NPC ghost conversations, runs 10-25)
- **Layer 4:** The true ending / secret ending (specific conditions, runs 25+)

### 4.6 "One More Run" Design

What makes players come back:

| Factor | Implementation |
|--------|---------------|
| **Short run time** | 30-60 min target. Fast enough to say "just one more" |
| **Early momentum** | First 3 floors should feel fast and exciting. No boring setup phase. |
| **Variety** | 6 classes x themed zones x random items = never the same run twice |
| **Near-misses** | Death messages that show "you were 2 floors from the boss" or "3 more hits would have won" |
| **Unlock drip** | Something new every 2-3 runs (new item type, new monster knowledge, new lore) |
| **Build stories** | "Remember when I found the Vorpal Blade on floor 2 and steamrolled?" |
| **Difficulty ladder** | After first win, unlock harder modifiers. Always a next challenge. |
| **Daily challenge** | Seeded run with leaderboard. Same dungeon for everyone that day. |
| **Statistics** | Track everything: fastest win, most kills, deepest floor, favorite class. Make players want to beat their own records. |

---

## 5. Implementation Priorities

### Phase 1: Foundation (Highest Impact, Moderate Effort)
1. **Character Classes** -- Implement 3 classes first: Warrior, Mage, Rogue
   - Class selection screen at game start
   - Different starting stats, equipment, and 1 unique ability each
   - Equipment restrictions
2. **New Status Effects** -- Poison, Paralysis, Fear (infrastructure for monster abilities)
3. **6-8 New Monsters** -- One per tier with unique abilities (Centipede, Mimic, Phase Spider, Fire Elemental, Mind Flayer, Beholder)
4. **Level-Up Choices** -- Replace auto-stat-gains with pick-one-of-three

### Phase 2: Depth (High Impact, Higher Effort)
5. **Remaining 3 Classes** -- Cleric, Ranger, Necromancer
6. **Monster Families** -- Group monsters by zone theme, implement themed floor generation
7. **Special Rooms** -- Trap rooms, arenas, treasure vaults (3-4 types)
8. **Spell School System** -- Organize spells by school, class-restricted access
9. **Hidden Rooms & Secrets** -- Searchable walls, secret passages

### Phase 3: Polish & Meta (Medium Impact, High Effort)
10. **Meta-Progression** -- Potion knowledge persistence, bestiary, soul essence upgrades
11. **Environmental Hazards** -- Webs, poison gas, steam vents, psychic static
12. **Lore System** -- Inscriptions, journals, NPC ghosts, boss dialog
13. **Cellular Automata Generator** -- For cave/fungal floors
14. **Feat System** -- Level-up feat choices every 3 levels
15. **Mini-Bosses** -- Fill in missing boss gaps (floors 2, 4, 7, 9, 12, 14)

### Phase 4: Endgame (Lower Impact, Moderate Effort)
16. **Challenge Modifiers** -- Post-win difficulty scaling
17. **Daily Seeded Runs** -- Deterministic seed system for shareable runs
18. **Hub Area** -- Between-run narrative space (major undertaking)
19. **New Equipment Slot** -- Off-hand (shields, dual-wield, focus items)
20. **Vertical Elements** -- Pits, chasms, multi-level rooms

---

## Appendix A: Monster Ability Quick-Reference for Implementation

Each ability below maps to a code change in the Enemy class or combat system:

```
NEW ENEMY FIELDS NEEDED:
  - special_abilities: list of ability dicts
  - resistances: set of damage types immune/resistant to
  - vulnerabilities: set of damage types that deal 2x
  - flying: bool (ignores terrain)
  - invisible: bool (not rendered normally)
  - disguise: str (what it looks like when disguised)
  - aura_type: str (damage type of aura)
  - aura_radius: int
  - aura_damage: int
  - phase_chance: float (chance to teleport when hit)
  - summon_type: str (what it summons)
  - summon_max: int

NEW AI HOOKS NEEDED:
  - on_damaged(self, gs, damage, source): for phase, spore cloud, etc.
  - on_death(self, gs): for death burst, undying, corpse explosion
  - on_turn_start(self, gs): for aura damage, regeneration
  - on_adjacent(self, gs, target): for engulf, paralysis touch
  - can_see_player(self, gs): for disguise reveal triggers
```

## Appendix B: ASCII Character Assignments

Current characters in use: `r b g s o W A T D L O V &`
Available good single characters for new monsters:

| Char | Monster | Mnemonic |
|------|---------|----------|
| c | Centipede | **c**entipede |
| k | Kobold | **k**obold |
| z | Zombie | **z**ombie |
| f | Fungus | **f**ungus |
| j | Slime/Jelly | **j**elly |
| m | Mimic | **m**imic |
| p | Phase Spider | **p**hase |
| G | Gargoyle | **G**argoyle |
| h | Ghast | g**h**ast |
| C | Gelatinous Cube | **C**ube |
| B | Basilisk | **B**asilisk |
| F | Fire Elemental | **F**ire |
| M | Medusa | **M**edusa |
| R | Rust Monster | **R**ust |
| i | Invisible Stalker | **i**nvisible |
| n | Minotaur | mi**n**otaur |
| P | Roper | ro**P**er |
| w | Will-o-Wisp | **w**isp |
| I | Mind Flayer | m**I**nd |
| E | Beholder | **E**ye |
| K | Death Knight | **K**night |
| X | Iron Golem | e**X**oskeleton |
| d | Bone Devil | **d**evil |
| S | Shadow Dragon | **S**hadow |
| H | Pit Fiend | **H**ell |
| Z | Dracolich | draco-li**Z**ard |

## Appendix C: Sources

### D&D 5e Data
- 5e Complete Index v3.6 spreadsheet (4,148 monsters, 199 class/subclass entries, 670+ spells)
- 5th Edition SRD Monster Index: https://5thsrd.org/gamemaster_rules/monster_indexes/monsters_by_cr/
- 5e SRD Traits & Actions: https://www.5esrd.com/gamemastering/traits-and-actions-for-monsters-and-npcs/
- RPGBOT Class Guides: https://rpgbot.net/dnd5/characters/classes/
- D&D Beyond Class Reference: https://www.dndbeyond.com/classes

### Dungeon Design
- Dyson's Dodecahedron Map Archive: https://dysonlogos.blog/maps/
- Dungeon Generation Algorithms Analysis: https://pulsegeek.com/articles/dungeon-generation-algorithms-patterns-and-tradeoffs/
- AtTheMatinee Dungeon Generation Demos: https://github.com/AtTheMatinee/dungeon-generation
- Procedural Dungeon Generation with Cellular Automata: https://blog.jrheard.com/procedural-dungeon-generation-cellular-automata

### Roguelike Design
- Hades Narrative Design Case Study: https://www.davideaversa.it/blog/hades-case-study-storytelling-roguelike-games/
- Hades: Failure is Death, and Death is Progress: https://natalia-nazeem.medium.com/failure-is-death-and-death-is-progress
- DCSS: The Greatest Roguelike (Game Design Analysis): https://www.jorgezhang.com/2020/06/dungeon-crawl-stone-soup-the-greatest-roguelike-of-all-time-and-what-it-can-tell-us-about-game-design/
- Roguelike Design with Greg Kasavin: https://www.gamedeveloper.com/design/roguelikes-and-narrative-design-with-i-hades-i-creative-director-greg-kasavin
- Best Roguelike Games Directory: https://rogueliker.com/best-roguelike-games/
- Roguelite Progression Systems: https://gamerant.com/roguelite-games-with-best-progression-systems/
