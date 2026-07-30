# Depths of Dread — Game Design Document

**Version:** 1.1.0 · **Last updated:** 2026-07-30
**Platform:** Any terminal (macOS / Linux / Windows-WSL / iPad via iSH)
**Engine:** Pure Python 3.8+, zero external dependencies, curses rendering
**License:** MIT · **Credits:** Built by Will Rompf with Claude (Anthropic)

---

## 1. Vision

Depths of Dread is a **classic-form terminal roguelike** — permadeath, procedural
floors, tile glyphs — built on a modern spine: full test coverage, telemetry-driven
balance, three graphics modes, and a first-of-its-kind twist: **the game can play
itself**, either with a deterministic bot or with a live Claude model making tactical
decisions in a split-screen panel.

### Design pillars

1. **Dread is the resource.** Light runs out, food runs out, HP runs out. Every
   system pressures the player downward — the only way out is through.
2. **Runs anywhere, needs nothing.** One `git clone`, one `python3 dungeon.py`.
   No pip installs, no assets, no GPU. An iPad on a plane is a target platform.
3. **Depth through interacting systems, not content bloat.** Water conducts
   lightning and blocks fire auras; fire suppresses troll regeneration; noise wakes
   sleepers; ice carries you into danger. Features must touch each other.
4. **The AI is a citizen, not a gimmick.** Bot and agent modes exercise the same
   game rules as a human, produce structured telemetry, and serve as the balance
   feedback loop (30-game batches are the standard regression instrument).
5. **Choices with teeth.** Branch forks, cursed shrines, unidentified potions,
   scroll-dissolving floodwater — risk/reward is explicit and irreversible.

---

## 2. Lore & Setting

### Background

Beneath the frontier town of **Thornhaven**, an old delving-shaft breaks into
something far older: twenty floors of worked stone, drowned crypts, and burning
vaults descending toward a wound in the world called **The Abyss**. Generations of
adventurers have gone down. The dungeon is furnished with their endings — fallen
bodies still clutching journals, abandoned camps, war memorials to companies no one
remembers (the game's 31 environmental vignettes are the archaeological record of
every party that didn't make it).

### The descent

The dungeon's character changes with depth, told through floor themes:

| Floors | Theme | Character |
|--------|-------|-----------|
| 1–3 | Dungeon | Worked stone, rats and goblins — the "civilized" upper works |
| 4–6 | Caverns | Natural cave, water features, first branch temptations |
| 7–9 | Catacombs | Bone and ash; the dead outnumber the living |
| 10–12 | Hellvault | Fire, demons, the dungeon stops pretending to be a place |
| 13–14 | Abyss (approach) | Reality thins; void creatures leak through |
| 15 | **The Throne of Dread** | Seat of the Dread Lord |
| 16–19 | The Shattered Depths → The Final Descent | Post-Throne descent: broken space, forgotten realms |
| 20 | **The Heart of Darkness** | The Abyss itself |

### The antagonists

- **The Ogre King (Floor 5)** — a brute tyrant taxing the upper dungeon. The first
  wall; skippable if you dare leave him behind you.
- **The Vampire Lord (Floor 10)** — lord of the Catacombs. In phase 2 his attacks
  accelerate and drain life.
- **The Dread Lord (Floor 15)** — the game's namesake and narrative gate. A
  three-phase fight: *taunting summoner* → *shadow-strike teleports* → *darkness
  arena* (drains your torch and raises wraiths). His throne room **seals the way
  down**; only his death cracks the floor open onto the stairway into The Abyss.
- **The Abyssal Horror (Floor 20)** — the true final boss. Void AOE, shadow
  summons. Killing it and descending the final stair wins the run.

Below the Throne, the dungeon is no longer a dungeon — the floor 17 fork offers the
**Frozen Abyss** (a cold so old it predates the stone) or the **Sunken Library**
(the archive of every delver civilization the Abyss has swallowed, guarded by the
Kraken in its flooded stacks).

### Voices in the dark

Five NPC archetypes wander the dungeon, each a different relationship to the
descent: the **Wandering Merchant** (profiteering from it), the **Lost Adventurer**
(defeated by it), the **Old Sage** (studying it), the **Wounded Knight** (warning
about it), and the **Ghost Guide** (killed by it, still helping). Shrines answer
prayers — usually. Some are cursed.

---

## 3. Core Gameplay

### The loop

**Explore → Fight/Sneak → Loot → Manage (light, hunger, HP) → Descend.**
Permadeath. A run ends in death (save deleted) or victory on floor 20. Sessions are
recorded as JSONL and replayable.

### Player classes

| Class | HP | MP | STR | DEF | Signature ability (cost) | Identity |
|-------|----|----|-----|-----|--------------------------|----------|
| **Warrior** | 40 | 10 | 7 | 3 | Battle Cry — freeze all nearby enemies 5 turns (8 MP) | Frontline attrition; techniques: Whirlwind, Cleaving Strike, Shield Wall |
| **Mage** | 20 | 35 | 3 | 0 | Arcane Blast — 3×3 AoE at range (15 MP) | Glass cannon; exclusive spells: Chain Lightning, Meteor, Mana Shield |
| **Rogue** | 25 | 15 | 5 | 1 | Shadow Step — teleport behind enemy + auto-crit (10 MP) | Stealth: −50% noise, +10% crit, Backstab (2× crit), Poison Blade, Smoke Bomb |
| **Adventurer** | — | — | — | — | none | Classless baseline ("classic mode") |

Leveling: XP curve `25 × 1.5^(level−1)`; on level-up the player chooses a stat
track (Vitality / Might / etc. — class-tuned gains). Techniques and spells unlock
progressively per class.

### Controls (canonical)

8-way movement (arrows / WASD / hjkl / yubn); bump-to-attack; `f` fire projectile,
`z` spells, `t` techniques, `C` class ability, `i` inventory, `,` pickup/grab
torch, `e` interact, `>`/`<` stairs, `$` shop, `p` pray, `/` search, `D` disarm,
`o` auto-explore, `Tab` auto-fight, `R` rest, `T` torch toggle, `G` graphics mode,
`J` journal, `M` bestiary, `c` character sheet, `S` lifetime stats, `x` look,
`m` message log, `Q` save & quit, `?` help.

---

## 4. Systems

### 4.1 Combat

- **To-hit** rolls vs evasion; **damage** = weapon roll + STR − target DEF/divisor.
- **Crits**: base + per-level scaling; Rogue +10% class bonus. Stealth attacks on
  sleeping enemies auto-crit at 2.0×, unwary at 1.5×; Backstab ability 2× guaranteed.
- **Enemy speed is real time-slicing**: each enemy banks `speed` energy per player
  turn and spends whole points as actions (capped at 3/turn). Bats (1.5) lunge
  twice every other turn; phase-2 Vampire Lord (2.0) doubles up every turn.
- **Morale**: wounded non-undead, non-boss enemies flee at their HP threshold;
  cornered enemies turn and fight. Magical fear (Scroll of Fear) is a timed rout.
- **Ranged**: bows + arrows, throwing daggers, charged wands (fire/frost/lightning).
  Projectiles animate along their line in interactive mode.

### 4.2 Stealth & noise

Enemies spawn **asleep** (skip turns) or **unwary** (patrol only) and escalate to
**alert**. Every action emits noise — corridor step 1, room step 2, door 4, spell
6, combat 8 — which alerts enemies within range. Rogues halve noise. Sighting is
FOV-based and mutual; "A goblin spots you!" is a real state change.

### 4.3 Elements & status effects

- **Damage types**: physical, fire, cold, poison. Enemies carry resist/vulnerable
  lists (trolls burn; wraiths hate fire; ice creatures fear it). Resist = −50%,
  vulnerability = amplified.
- **Environmental chemistry**: water extinguishes Burning and blocks fire auras
  (steam); lightning cast onto water chains to everything standing in it; lava is
  lethal without fire/cold resistance (passable at −2 HP/step with it); fire
  suppresses troll regeneration for 5 turns.
- **Player statuses**: Poison, Bleed (stacking), Fear, Confusion, Paralysis,
  Frozen (shatter bonus when hit), Silence (blocks spells, wands, Arcane Blast),
  Blindness (FOV 1), Constricted (Kraken grab — STR-scaled escape rolls; you can
  still fight while held), plus buffs: Strength, Speed, Resistance, Berserk,
  Shield Wall, Mana Shield, Poison Blade, Backstab.

### 4.4 Light & hunger

The torch is a fuel tank (wall torches, torch items, and lantern oil refill it);
radius shrinks as fuel dies. Resting and waiting cost hunger; at 0 hunger,
**starvation damage ticks every turn, moving or not**. Mystery Meat is a gamble.
Fountains heal and occasionally grant permanent +1 max HP.

### 4.5 Traps & puzzles

- **6 trap types** (spike, poison dart, pit/stun, teleport, alarm, confusion gas),
  hidden until triggered, searched (`/`), or passively noticed. Rogue-bonus
  disarming. **Enemies trigger traps too** — kiting is a valid tactic. Revealed
  traps stay marked on the map.
- **5 puzzle types**: torch pedestals, switch banks, locked-stairs switch hunts,
  lit-in-order sequence pedestals, timed pressure plates. Rewards: gold + high-tier
  loot. (Locked-stairs puzzles are generation-validated so they can never spawn
  unsolvable.)
- **Secret rooms** behind false walls — search to reveal; the walls genuinely
  block sight and movement until found.

### 4.6 Economy & services

Gold from piles, drops, and selling. Sinks: **shops** (every other odd floor,
price-scaled by depth), **enchanting anvils** (100g, one of six weapon
enchantments: Flame, Frost, Venom, Lightning, Vampiric, Keen — enchanted gear shows
its `+N`), **alchemy tables** (identify unknowns, alchemical boons, reveal traps),
**shrines** (free, but gamble). Unidentified potions/scrolls use per-run shuffled
identities; discoveries land in the **Journal**.

### 4.7 Knowledge systems

The **Bestiary** (`M`) reveals monster intel progressively per *sighting* (1 seen:
name → 3: stats → 5: abilities → 10: damage records + resistances). **Context
tips** fire once each at teachable moments. The **look/examine** cursor describes
any visible tile, enemy, NPC, item, or revealed trap.

---

## 5. The Dungeon

### 5.1 Structure

20 floors of BSP-generated rooms (circular, L-shaped, pillared variants) linked by
corridors, with recursive-shadowcasting FOV, A* pathfinding, and guaranteed
connectivity. Stairs descend one-way — but **floors persist**: ascending restores
the floor exactly as you left it (corpses stay looted; nothing restocks).

### 5.2 Branch forks

At five depths the stairway splits; the choice is permanent for the run:

| Floor | Option A | Option B |
|-------|----------|----------|
| 2 | **Fungal Depths** — spores, poison, Fungal Queen | **Trapped Halls** — trap gauntlet, Trap Master |
| 5 | **Flooded Crypts** — water, undead, Crypt Guardian | **Burning Pits** — lava, demons, Flame Tyrant |
| 10 | **Mind Halls** — psychic, paralysis, Elder Brain | **Beast Warrens** — fast packs, traps, Beast Lord |
| 13 | **Void Rift** — shadow horrors, Void Herald | **Infernal Forge** — molten constructs, Inferno King |
| 17 | **The Frozen Abyss** — sheet ice (you slide until something stops you), Frost Revenants, Ice Golems, **Frost Titan** | **The Sunken Library** — flooded archives, +4 scrolls/floor but wading can dissolve carried scrolls, **the Kraken** (ink-cloud blindness + constricting tentacles) |

Branches re-theme terrain, enemy pools, palettes, and trap density. Ice sliding is
a movement rule change: momentum carries the player across `░` tiles into walls,
water, enemies — or worse.

### 5.3 Bestiary (41 enemy types)

- **11 AI archetypes**: chase, patrol, erratic, pack (flanking + allies), ambush,
  ranged, summoner, mimic (disguised as gold), phase (teleporting spiders),
  mind-flayer (psychic ranged + silence), kraken (ink + constrict).
- **10 bosses**: 4 mainline (Ogre King, Vampire Lord, Dread Lord, Abyssal Horror)
  + 6 branch guardians. Mainline bosses have scripted multi-phase behavior.
- **4 apex predators** (rare late-game elites): Ancient Dragon (breath weapon +
  fire aura), Hydra (triple attack + regen), Shadow Wyrm, Stone Colossus (stun).
- Enemy stats scale with depth-above-minimum, then difficulty multipliers.

---

## 6. Difficulty, Challenge & Meta

### Difficulty presets (`--difficulty`)

| | Enemy HP | Enemy DMG | Items | Food | XP | Gold |
|--|---|---|---|---|---|---|
| Easy | 0.7× | 0.7× | 1.3× | 1.5× | 1.3× | 1.5× |
| Normal | 1.0× | 1.0× | 1.0× | 1.0× | 1.0× | 1.0× |
| Hard | 1.4× | 1.3× | 0.8× | 0.7× | 0.8× | 0.7× |

### Challenge modes (stack with difficulty)

- `--ironman` — save/load fully disabled; quitting abandons the run
- `--speedrun` — per-floor timer
- `--pacifist` — killing any non-boss ends the run
- `--dark` — starting torch capped, sight radius capped at 4, all map-reveal
  effects (Scroll of Mapping, Ghost Guide) fizzle

### Meta-progression (7 lifetime unlocks)

Earned across runs from persistent lifetime stats, applied at game start:
Potion Affinity (3 games), Cartographer (reach F5), Inheritance (50 kills, +50g),
Hardy Constitution (5 deaths, +10 HP), Prepared Explorer (reach F10, +torch),
Magical Aptitude (first win, +5 MP), Armed & Ready (30 kills in one run, tier-2
weapon).

### Scoring

`gold + 10×kills + 100×deepest floor + damage dealt (+ victory bonus)` —
shown with per-run stats, death cause, and lifetime records on the death/victory
screens.

---

## 7. Presentation

### Graphics modes (`G` cycles; auto-detects terminal capability)

1. **Old School** — pure ASCII (`#`, `.`, `~`), 16 colors. Runs on anything.
2. **Slightly Less Old School** — Unicode glyphs (█ walls, · floors, ≈ water,
   ░ ice, ▼▲ stairs, Ω fountains) + **21 themed 256-color floor palettes**
   (mossy Caverns greens, bone-grey Catacombs, crimson Throne of Dread, glacial
   Frozen Abyss…), with lit/dim variants for FOV vs. explored memory.
3. **8-Bit** — NES-inspired: rooms render as dark background-tinted panels,
   hazards as saturated fg-on-bg blocks (yellow-on-red lava, cyan-on-blue water),
   entities recolored onto the room background. Requires 256-color support.

### Lighting & feedback

Torch-radius FOV with fog of war; wall torches and lava are real light sources
(LOS-checked glow). Projectile and spell animations; HP bar blinks at critical;
terminal-bell audio cues for crits, boss encounters, low torch, and death.
Minimum terminal 80×24 (132+ for agent split-screen).

---

## 8. AI Play Modes

### Bot mode (`--bot`)

A deterministic 4-layer decision tree (survival → combat → economy → exploration)
with fear/flee handling, boss strategies, puzzle solving, branch selection, and
committed exploration targets. Runs a full game in seconds. **Batch mode**
(`--games N --json`) rotates classes and emits structured per-game + summary JSON
(floors, deaths, timeouts, locked stairs, puzzle counts) — the project's standard
balance instrument.

### Agent mode (`--agent`)

Hybrid architecture: the bot handles ~97% of turns; **Claude Haiku is consulted**
at decision points — boss visible (highest priority), combat, low HP
(rate-limited), shops, shrines, puzzles, alchemy, new floors, stuck detection.
Split-screen panel shows reasoning, strategy, latency, and decision history.
**Pilot Mode (Shift+P)** hands control to the human mid-run and back. Requires the
Claude CLI; costs ~$0.005–0.01 per game. Integrates the `agent-commons` framework
(call budgets, decision traces, stall recovery, coverage tracking, death
autopsies) when present.

### Recording & replay

Every interactive run records seed, inputs, branch choices, and state snapshots to
JSONL; `--replay` re-simulates it visually with pause/speed controls.

---

## 9. Technical Design

- **Zero dependencies** — Python stdlib + curses only. Windows via WSL or
  `windows-curses`; iPad via iSH.
- **15 modules, ~13k lines**: `game.py` (loop/state/dispatch), `constants.py`
  (all tuning in a `BALANCE` dict + data tables), `combat.py`, `items.py`,
  `floor_gen.py`, `mapgen.py` (BSP/FOV/A*), `entities.py`, `ui.py`,
  `persistence.py`, `bot.py`, `agent.py`, `agent_ui.py`, `exceptions.py`.
  Fully type-hinted; ruff + mypy clean.
- **Saves**: single-slot JSON with SHA-256 checksum (tamper → rejected).
  Serializes full player/floor/enemy state including floor-scaled stats,
  difficulty, challenge flags, puzzles, bestiary, shops, NPCs, vignettes.
  Permadeath deletes on death; ironman never writes.
- **Testing**: 503 pytest tests across 11 files (unit + integration + quality/
  stress), built-in self-tests (`--test`), pty-driven interactive smoke tests,
  and bot-batch regression runs. Philosophy: full ISO 25010 — act like a real
  user, not just a unit-test suite.

---

## 10. Version History

| Version | Date | Highlights |
|---------|------|------------|
| 0.x | 2026-03-04 → 03-09 | Initial release; balance overhauls (gold economy, enemy scaling); the big expansion (boss phases, vignettes, apex enemies, branches, NPCs, meta-progression, Abyss floors 16–20, challenge modes); modular split from a 10k-line single file |
| **1.0.0** | 2026-03-10/11 | Tagged release: 474 tests, typed codebase, BALANCE extraction, ruff/mypy baseline, 256-color palettes + Unicode tiles, graphics toggle, `dungeon.py` launcher |
| 1.0.x | 2026-03-17 → 03-31 | Bot AI overhaul (4-layer priority, fear handling, boss strategy — 3,500+ test games); death-screen crash fix |
| **1.1.0** | 2026-07-30 | **The Great Repair + Frozen Depths.** Multi-agent code review fixed ~45 defects, including: 256-color theming dead since launch (stale import snapshot), meta-unlocks never applied, save/load resetting enemy stats/difficulty/challenge flags, enemy speed >1.0 inert, Silence/Rogue crit/Scroll of Fear/difficulty loot multipliers inert, secret walls walkable and transparent, ascend-stairs loot farm (fixed via floor caching), Dread Lord skippable (now seals F15), replay ImportError, auto-fight hang, invisible NPCs/revealed traps, bestiary counting hits as encounters. **New:** 8-Bit graphics mode; floor 17 branch pair (Frozen Abyss ice-sliding vs Sunken Library scroll-soak + Kraken); 5 new enemies; cumulative puzzle telemetry. Tests 474 → 503; bot avg floor 10.1 → 12.0. |

---

## 11. Roadmap

**Next up (backlog, rough priority):**

1. **Dread Meter** — a corruption/insanity resource that rises in darkness, deep
   floors, and boss encounters; thresholds bring debuffs and hallucinations;
   relieved at fountains/shrines. The thematic capstone system.
2. **Mage balance** — still the weakest class (bot avg floor 9.3 vs Warrior 14.1,
   Rogue 12.5). Mana economy is the bottleneck; candidates: cheaper early spells,
   mana-on-kill, wand synergy.
3. **Crafting recipes at alchemy tables** — 5–8 combine-item recipes on existing
   infrastructure.
4. **Adaptive difficulty** (`--adaptive`) — per-floor tuning from run telemetry.
5. **Post-run Claude analysis** — feed the session JSONL to Claude for a
   narrative autopsy (~100 LOC; best effort/reward on the list).
6. **Code hygiene** — retire dead BALANCE keys, unify the five direction-key maps,
   extend replay to record class/gear for true determinism.

**Long-horizon:** AI Dungeon Master mode (Claude narrates/mutates a run live);
daily-challenge seeds; a from-scratch PICO-8 / NES demake (see
`RETRO_GAME_DEV_RESEARCH.md` — the full game cannot fit NES constraints; a
single-screen roguelike-lite could).

**Explicitly rejected:** multi-tile monsters (breaks 1-wide corridors, FOV, and
pathfinding for marginal value — see `GAME_EXPANSION_RESEARCH.md`).

---

## 12. Reference: Content Inventory

- **Classes:** 3 + classless Adventurer
- **Enemies:** 41 types · 10 bosses · 4 apex · 11 AI archetypes
- **Spells:** 8 (Fireball, Lightning Bolt, Heal, Teleport, Freeze, Chain
  Lightning†, Meteor†, Mana Shield†; † = Mage-only)
- **Weapons:** 10 tiers 0–5 + 4 boss drops (Ogre King's Maul, Vampiric Blade,
  Dread Lord's Bane, Void Reaver) · 6 enchantments
- **Armor:** 8 (Torn Rags → Dread Plate) · **Bows:** 3 · **Wands:** 3
- **Rings:** 8 (incl. cursed Ring of Hunger) · **Potions:** 9 · **Scrolls:** 8
- **Food:** 4 · **Light:** 3 refuel items + wall torches
- **Floors:** 20 · **Branches:** 10 across 5 forks · **Themes/palettes:** 21
- **Traps:** 6 · **Puzzles:** 5 types · **Vignettes:** 31 · **NPCs:** 5
- **Challenge modes:** 4 · **Difficulties:** 3 · **Meta unlocks:** 7
- **Graphics modes:** 3 · **Play modes:** interactive, bot, agent, batch, replay
