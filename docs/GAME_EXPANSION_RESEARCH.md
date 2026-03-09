# Depths of Dread — Expansion Research Report

**Prepared:** March 5, 2026
**Current State:** 15 floors, 23+ enemy types, 3 bosses, 4 branch mini-bosses, BSP dungeons, ~9,100 lines Python curses
**Goal:** Make the game deeper and more fun — practical recommendations backed by research

---

## 1. Classic Game Lengths and Floor Counts

### Text Adventures (Zork)

| Game | Rooms | Puzzles | Typical Playtime |
|------|-------|---------|-----------------|
| Zork I | 110 | ~30 | 6-10 hours (first play) |
| Zork II | 86 | ~25 | 6-8 hours |
| Zork III | ~100 | ~20 | 5-7 hours |

Zork games are purely puzzle-driven — no combat, no procedural generation. A skilled player can finish Zork I in 236 moves, but first-timers spend hours stuck on individual puzzles. The takeaway: **content density matters more than raw room count.** 110 rooms of hand-crafted puzzles produces 6-10 hours of play. 15 floors of procedural content can too, if each floor is mechanically distinct.

### Classic Roguelikes

| Game | Total Floors/Levels | Branches | Winning Run Time | Notes |
|------|-------------------|----------|-----------------|-------|
| **Rogue** (1980) | 26 | None | 1-2 hours | The original. Linear descent. |
| **NetHack** | ~50 total | 8+ branches | 2-5 hours (experienced), 4-8+ hours (first ascension) | Gnomish Mines (8-9 floors), Sokoban (4), Quest (5-7), Gehennom (variable), Vlad's Tower (3), Fort Ludios (1), Elemental Planes (4+Astral) |
| **DCSS** | 15 main + 73 branch = 88 finite | 15+ branches | 3-6 hours (3-rune), 8-15 hours (15-rune) | The gold standard for branch design |
| **ADOM** | 50 (Caverns of Chaos) + branches | 12+ dungeons | 8-20 hours | Overworld + multiple dungeons, not just one |
| **Angband** | 100 | None (linear) | 12-24 hours (experienced), 80-160 hours (cautious first win) | Pure depth, minimal branching |
| **Brogue** | 26 (+optional depths beyond) | None | 30-60 minutes | The minimalist masterpiece |
| **Caves of Qud** | 30+ underground + surface | Open world | 8-12 hours (main quest) | Surface biomes + vertical depth |
| **Dwarf Fortress (Adventure)** | 50+ z-levels, up to 600 | N/A | Indefinite | Simulation, not traditional roguelike structure |
| **Cataclysm: DDA** | Surface + underground labs | Open world | Indefinite (survival sandbox) | No "win" condition per se |

### The Floor Count Question: Is 15 Enough?

**Short answer: Yes, but only if those 15 floors are dense and varied.**

The data reveals three distinct models:

1. **The Brogue Model (26 floors, 30-60 min):** Tight, focused, every floor matters. No filler. High replayability through brevity. Brogue proves you can make a complete roguelike feel epic in under an hour.

2. **The DCSS Model (15 main + 73 branch = 88):** Only 15 main dungeon floors, but the real game is in the branches. A 3-rune win touches maybe 30-40 floors total. A 15-rune completionist run hits 70+. **This is the most relevant model for Dread.**

3. **The Angband Model (100 floors, 12-24 hours):** Linear depth, repetitive, demands grinding. Generally considered the weakest design by modern standards. More floors =/= more fun.

**Recommendation for Dread:** Don't add more main floors. Instead, add more **branch depth and variety**. DCSS's 15 main floors + extensive branching is the proven sweet spot. You're already at 15 main floors — that's correct. The gap is in branch content.

---

## 2. Biomes and Themed Areas

### How the Classics Handle Themed Areas

#### NetHack's Branch Design (Thematic + Mechanical)

NetHack has 8+ distinct areas, each with unique mechanics:

| Branch | Floors | Theme | Unique Mechanic |
|--------|--------|-------|----------------|
| Gnomish Mines | 8-9 | Underground mines, shops | Persistent shops, peaceful gnomes, Mine's End loot |
| Sokoban | 4 | Puzzle branch | Boulder-pushing puzzles (unique to this branch), guaranteed artifact reward |
| The Quest | 5-7 | Role-specific homeland | Unique per class, quest artifact, nemesis boss |
| Fort Ludios | 1 | Military fortress | Massive treasure vault, army of soldiers |
| Gehennom | Variable | Hell/demons | Maze-heavy, demon lairs, fire traps, no teleport control |
| Vlad's Tower | 3 | Gothic castle | Upward tower (reversal!), vampire lord, required artifact |
| Elemental Planes | 4 | Earth/Air/Fire/Water | Each plane has completely different survival rules |
| Astral Plane | 1 | Divine endgame | Three altars, riders of the apocalypse, final sacrifice |

**Key insight:** Sokoban changes the entire gameplay loop (puzzles instead of combat). Vlad's Tower reverses direction (going up instead of down). The Elemental Planes each redefine what "surviving a floor" means. The best branches don't just reskin enemies — they change the rules.

#### DCSS's Branch Design (The Gold Standard)

DCSS has the most sophisticated branch system in roguelikes:

| Branch | Floors | Accessed From | Theme |
|--------|--------|--------------|-------|
| Dungeon | 15 | — | Generic dungeon, increasing difficulty |
| Temple | 1 | D:4-7 | Altars to all gods, no enemies |
| Lair | 6 | D:8-11 | Animals, natural creatures, open layouts |
| Orc Mines | 2 | D:9-12 | Orcs, shops, treasure |
| Swamp OR Shoals | 4 | Lair | Water-heavy (Swamp = poison/undead, Shoals = merfolk/tides) |
| Snake Pit OR Spider's Nest | 4 | Lair | Nagas/poison OR spiders/webs |
| Slime Pits | 5 | Lair:4-5 | Slimes, corrosion, acid, no walls (eaten away) |
| Elven Halls | 3 | Orc:2 | Elves, magic-heavy, dangerous casters |
| Vaults | 5 | D:13-14 | Military fortress, vaults of loot, guards |
| Depths | 4 | D:15 | Deep dungeon, portal access |
| Crypt | 3 | Depths | Undead, necromancy |
| Tomb | 3 | Crypt/Depths | Mummies, curses, traps — extremely dangerous |
| Realm of Zot | 5 | Depths (needs 3 runes) | Final area, dragons, orbs of fire |
| Pandemonium | Infinite | Depths | Unique demon lords, random layouts |
| Hell (4 branches) | 7 each | Depths | Dis/Gehenna/Cocytus/Tartarus — endgame optional |
| Abyss | Infinite | Random banishment | Chaotic, disorienting, survival mode |
| Ziggurat | 27 | Depths (portal) | Arena gauntlet, escalating hordes |

**Critical DCSS design principles:**
- Mutually exclusive branches (Swamp OR Shoals) create replayability — you never see everything in one run
- Branch difficulty is non-linear — Slime Pits are accessible early but deadly
- Some branches change fundamental rules (Abyss has no stairs, Slime Pits dissolve your scrolls)
- Rune-gating forces engagement with branches before the endgame

#### ADOM's Approach (Overworld + Dungeons)

ADOM uses a different model entirely: an overworld map connecting multiple standalone dungeons:

| Location | Floors | Theme |
|----------|--------|-------|
| Caverns of Chaos | 50 | Main dungeon, generic + special levels |
| Infinite Dungeon | Infinite | Pure grinding/survival |
| Pyramid | 2 | Mummy lord, traps |
| Dwarven Halls | 2 | High-danger dwarven ruins |
| Fungal Caves | 3 | Fungi, herbs, mushroom-themed |
| Elemental Temples | 4 (Water, Air, Fire, Earth) | Each scattered through CoC |
| Tower of Eternal Flames | 4 | Fire-themed, quest location |
| Unreal Cave / Blue Dragon Caves | Multi | Late-game, mana temple |

**ADOM's key insight:** An overworld creates a sense of a living world rather than a pure dungeon crawl. Side dungeons feel like choices, not obligations.

### Biome Recommendations for Depths of Dread

Your current branches are a solid foundation but underexploit the concept:

| Current Branch | Floors | What It Does Well | What's Missing |
|---------------|--------|------------------|---------------|
| Flooded Crypts | 3 (6-8) | Thematic terrain (water), unique enemies | No mechanical difference beyond water tiles |
| Burning Pits | 3 (6-8) | Thematic terrain (lava) | Same — just lava instead of water |
| Mind Halls | 3 (11-13) | Psychic enemies are mechanically distinct | Terrain is generic |
| Beast Warrens | 3 (11-13) | More enemies + traps = interesting pressure | Best of the four — changes difficulty, not just theme |

**Proposed New/Enhanced Biomes:**

| Biome | Floors | Unique Mechanic | Why It Works |
|-------|--------|----------------|-------------|
| **The Sunken Library** | 3 | Spell scrolls everywhere but water damage destroys them. Solve "puzzle rooms" to unlock sealed vaults. Enemies are enchanted constructs. | Changes the loot game — risk/reward with water |
| **The Fungal Depths** | 3 | Spore clouds create "fog of war" zones. Stepping on mushrooms releases effects (heal, poison, confusion, teleport). Terrain is alive. | Environmental interaction, unpredictable |
| **The Clockwork Halls** | 3 | Rotating rooms, conveyor-belt floors, timed doors. Gear-themed traps. Bronze automaton enemies. | Changes movement/pathfinding, unique puzzle feel |
| **The Frozen Abyss** | 3 | Ice floor (sliding mechanics — move until you hit something). Frozen enemies thaw after N turns. Cold damage ambient per turn without torch. | Physics-based movement is a real rule change |
| **The Living Caverns** | 3 | Walls shift between turns. Rooms grow/shrink. Organic terrain. Parasite enemies that embed in walls. | The dungeon itself is the enemy |
| **The Void** | 3 (post-boss) | No walls. Floating platforms. Darkness is absolute (torch range halved). Eldritch horrors. High reward loot. | Optional post-game challenge, pure dread atmosphere |

**Priority recommendation:** Start with The Fungal Depths and The Frozen Abyss. Both add genuine mechanical variety (spore effects, ice sliding) without requiring massive engine changes. The Clockwork Halls would be incredible but requires significant new systems (conveyor belts, rotating rooms).

### Environmental Storytelling Through Biomes

The most effective roguelike environmental storytelling uses:

1. **Pre-placed "vignette" rooms:** A skeleton holding a journal entry next to an empty potion bottle. A barricaded room with scratch marks on the inside of the door. These cost almost nothing to implement (add to room generation) but create atmosphere.

2. **Progressive decay:** Early floors have intact furniture, torches on walls, readable signs. Deep floors have crumbled walls, dried blood, broken equipment. Your BSP generator can flag rooms by floor depth and place appropriate decorative elements.

3. **Branch-specific lore items:** Each branch could have 3-5 discoverable journal fragments that tell a story. "Day 14: The water keeps rising. We sealed the lower crypts but I can hear them scratching..." This is pure text — minimal code, maximum atmosphere.

4. **Returning NPCs/ghosts:** A ghost on floor 3 warns about the Burning Pits. If you chose Flooded Crypts instead, a different ghost on floor 7 says "You chose wisely... the pits claimed the last party." Reactive world-building.

---

## 3. Large Monsters / Multi-Tile Creatures

### Do Classic Roguelikes Use Multi-Tile Monsters?

| Game | Multi-Tile? | Details |
|------|------------|---------|
| NetHack | No | All creatures are 1 tile, including dragons |
| DCSS | No | Dragons, giants, everything is 1 tile |
| ADOM | No | Same |
| Angband | No | Same — even Morgoth is one tile |
| Brogue | No | Same |
| **Cogmind** | **YES** | Large robots occupy 2x2 or 3x3 tiles. The definitive implementation. |
| **IVAN** | Partially | 2x2 monsters exist but are rare and often break walls to move |
| **Zorbus** | Yes | Multi-tile creatures with large character display |

**The honest assessment:** Multi-tile monsters are extremely rare in roguelikes for good reasons. Cogmind is the only game that does it well, and its developer (Kyzrati) wrote extensively about the engineering challenges.

### Implementation Challenges (from Cogmind's Developer)

1. **Pathfinding:** Standard A* assumes 1-tile entities. Multi-tile creatures need `isValid()` checks on ALL occupied cells for every pathfinding step. This is computationally expensive and creates frequent stuck situations in tight corridors.

2. **Corridor Problem:** BSP dungeons (which Dread uses) generate lots of 1-tile-wide corridors. A 2x2 creature literally cannot traverse them. Solutions:
   - Make multi-tile creatures destroy walls (IVAN's approach — messy)
   - Only spawn them in large rooms (limits their impact)
   - Generate wider corridors when multi-tile enemies are present (changes dungeon feel)

3. **FOV/Visibility:** When only 1 tile of a 2x2 creature is visible, players can't distinguish it from a 1-tile creature. Cogmind solves this by showing the full creature outline even when partially visible, but this breaks FOV purity.

4. **Collision:** When a 2x2 creature moves, it vacates 2 cells and occupies 2 new ones. What happens if another entity is in one of those cells? Cogmind uses push/crush mechanics — the large creature shoves smaller ones aside.

5. **Targeting:** Which tile do you attack? Which tile takes damage? Cogmind treats the "root" cell as the entity's position and treats all occupied cells as valid attack targets.

6. **Map Design:** Multi-tile creatures work best on open maps. Cogmind's levels are specifically designed with wide corridors and open areas. BSP dungeons with standard corridor widths would be hostile to multi-tile creatures.

### Recommendation: Don't Do Multi-Tile. Do "Apex Predator" Design Instead.

The better approach (used by every classic roguelike) is to make large creatures feel large through **mechanics**, not through tile count:

**"Feels Large" Without Multi-Tile:**

| Mechanic | Example | Implementation Effort |
|----------|---------|---------------------|
| **Breath weapon (cone)** | Dragon breathes fire in a 3-wide, 5-deep cone | Medium — cone AOE calculation |
| **Tail swipe (arc)** | Dragon hits all creatures in a 3-tile arc behind it | Low — check adjacent tiles in an arc |
| **Wing buffet (knockback)** | Dragon pushes all adjacent creatures 2 tiles back | Low — apply knockback vector |
| **Tremor/stomp (AOE)** | Giant stomps, all creatures within 2 tiles take damage and are stunned | Low — radius check |
| **Charge (line)** | Bull demon charges in a line, hitting everything in its path | Medium — line-of-sight traversal with damage |
| **Coil/constrict (grab)** | Serpent grabs player, preventing movement for N turns, damage per turn | Low — status effect |
| **Aura (passive AOE)** | Dragon radiates heat — 2 damage/turn to anything within 3 tiles | Low — distance check per turn |
| **Demolish walls** | Huge creature destroys adjacent walls when moving | Medium — terrain modification |

**NetHack's Dragon Design (1-tile, feels massive):**
- Dragons have elemental breath weapons (fire, frost, lightning, acid, etc.)
- Dragon scales drop as armor (one of the best armor types in the game)
- Different colors = different elements = different strategies required
- Baby dragons grow into adult dragons if left alive too long

**Recommended "Dragon-Tier" Enemies for Dread:**

| Enemy | Char | Mechanics | Appears |
|-------|------|-----------|---------|
| **Ancient Dragon** | `D` | Breath weapon (fire cone, 3x5), wing buffet (knockback 2), 200 HP, drops dragon scale armor | Floor 13-15 or branch boss |
| **Kraken** | `K` | Tentacle grab (constrict 3 turns), ink cloud (blindness AOE 3 tiles), only in water-heavy areas | Flooded Crypts boss alternative |
| **Stone Colossus** | `C` | Tremor stomp (AOE 2, stun), charge (line 4 tiles), immune to projectiles, slow (0.5 speed) | Floor 14-15 |
| **Hydra** | `H` | Multi-attack (number of attacks = number of heads, starts at 3), cutting damage adds a head (DCSS mechanic!) | Floor 10-14 |
| **Shadow Wyrm** | `W` | Darkness aura (reduces torch range by 3), phase through walls, ambush from darkness | Floor 12-15 |

The Hydra is especially worth stealing from DCSS — it creates a genuine tactical puzzle. Slashing weapons make it stronger (more heads = more attacks). Players must use fire, clubs, or magic. It's the kind of enemy that makes players think differently.

---

## 4. Specific Expansion Recommendations for Depths of Dread

### Current State Assessment

**Strengths:**
- Solid core loop (move, fight, loot, descend)
- Branch system exists and works
- Good enemy variety (23+ types with distinct AIs)
- Class system with meaningful differentiation
- Stealth/alertness system adds tactical depth
- Bot and Agent play modes are unique features

**Weaknesses / Gaps:**
- Branches are cosmetically different but mechanically similar (water vs lava swaps)
- No floors have unique gameplay rules (every floor plays the same)
- No persistent progression between runs (roguelikes increasingly have meta-progression)
- Limited environmental interaction (water/lava exist but few other terrain types)
- Boss fights are stat-checks, not mechanical puzzles
- 15 floors of similar-feeling content

### Ranked Expansion Ideas: Effort vs Impact

| Rank | Feature | Impact | Effort | Why |
|------|---------|--------|--------|-----|
| **1** | **Mechanically unique branch floors** | VERY HIGH | Medium | Transform existing branches from reskins to rule-changers. Ice floors with sliding, fungal spores, etc. This is the #1 thing that would make the game feel deeper. Each branch should change HOW you play, not just WHAT you fight. |
| **2** | **Boss mechanical phases** | HIGH | Medium | Current bosses are stat-checks. Add phases: Dread Lord phase 1 (summoner), phase 2 at 50% HP (enrages, stops summoning, double damage, charges), phase 3 at 25% (desperate, casts AOE darkness). Makes the climax memorable. |
| **3** | **Environmental vignettes + lore** | HIGH | LOW | Pre-placed room templates with environmental storytelling. Skeleton with journal, barricaded room, ritual circle, abandoned camp. 20-30 vignette templates, randomly placed. Huge atmosphere boost for minimal code. |
| **4** | **Dragon-tier apex enemies** | HIGH | Medium | Ancient Dragon with breath cone, Hydra with head mechanics, Kraken with constrict. These create tactical puzzles, not just harder stat-checks. 3-4 new enemy types with unique mechanics. |
| **5** | **One more branch pair (floors 3 and 14)** | HIGH | Medium | Currently branches at 5 and 10. Add a choice at floor 3 (early divergence) and floor 14 (pre-boss divergence). This means 4 choice points in a 15-floor game — much more replayability. Early branch could be "Goblin Warrens vs Rat Catacombs." Late branch could be "The Frozen Abyss vs The Void." |
| **6** | **Puzzle rooms (Sokoban-style)** | MEDIUM-HIGH | Medium | 1-2 per run, procedurally placed. Boulder-pushing, switch-sequence, or "kill enemies in order" puzzles. Reward is guaranteed good loot. Breaks up combat monotony. NetHack's Sokoban is beloved specifically because it's a different kind of challenge in the middle of a combat game. |
| **7** | **Status effect expansion** | MEDIUM | LOW | Add: Bleed (damage over time, movement leaves blood trail), Frozen (skip turn, shatter on hit = bonus damage), Silence (no spells/wands), Blindness (no FOV, stumble randomly). Currently have Poison/Paralysis/Fear/Confusion. Double the tactical space cheaply. |
| **8** | **Meta-progression (between runs)** | MEDIUM | Medium-High | Unlock new starting equipment, character perks, or cosmetic options based on achievements across runs. "Kill 100 demons" unlocks fire resistance starting perk. Gives failed runs meaning. Modern roguelikes (Hades, Dead Cells, Slay the Spire) all do this. |
| **9** | **NPC encounters** | MEDIUM | Medium | A merchant on floor 3, a trapped adventurer on floor 7 who joins temporarily, a fortune teller who reveals branch contents. 3-5 NPC types. Adds social dimension to a lonely dungeon. |
| **10** | **Wider floors / room variety** | MEDIUM | LOW-Medium | BSP generates samey rectangular rooms. Add circular rooms, L-shaped rooms, pillared halls, throne rooms. Different room shapes create different combat dynamics (pillars = cover, wide halls = ranged advantage). |
| **11** | **Post-boss content (floors 16-20)** | MEDIUM | HIGH | "The Abyss" — 5 optional floors after the Dread Lord. Eldritch horrors, no rules, massive rewards. Only for mastery runs. Risk: dilutes the climactic ending. Benefit: gives skilled players somewhere to go. |
| **12** | **Weapon enchantment / crafting** | MEDIUM | Medium | Combine items at alchemy tables: weapon + fire scroll = flaming weapon. Simple crafting adds depth without requiring new UI. 5-8 recipes. |
| **13** | **Challenge modes** | LOW-MEDIUM | LOW | "Ironman" (no healing potions), "Speedrun" (turn counter, bonus for fast completion), "Pacifist" (kill as few as possible), "One Torch" (start with one torch, no refills). Zero new content needed — just rule modifiers. |
| **14** | **Sound/music cues via terminal bells** | LOW | LOW | Terminal bell on boss appearance, low HP, trap trigger. Primitive but effective for tension. Might annoy some users — make it toggleable. |
| **15** | **Multi-tile monsters** | LOW | VERY HIGH | As researched above: massive implementation cost, breaks BSP corridors, minimal payoff over well-designed 1-tile apex predators. Not recommended. |

### The Recommended Build Order

If I were prioritizing a development roadmap:

**Phase 1: Depth Without New Content (1-2 sessions)**
- Boss mechanical phases (#2)
- Environmental vignettes + lore (#3)
- Status effect expansion (#7)
- Room shape variety (#10)

These are all LOW-to-MEDIUM effort changes that make existing content feel significantly richer. No new floors, no new systems — just making what's there more interesting.

**Phase 2: Mechanical Variety (2-3 sessions)**
- Mechanically unique branch floors (#1) — pick 2 branches to overhaul
- Dragon-tier apex enemies (#4) — add 3 new enemy types
- One puzzle room template (#6)

This is where the game starts feeling genuinely different on repeat plays.

**Phase 3: Structural Expansion (2-3 sessions)**
- New branch pair at floors 3 and 14 (#5)
- NPC encounters (#9)
- Meta-progression (#8) if you want between-run hooks

This is where the game goes from "solid roguelike" to "I need to play this again to see the other branches."

**Phase 4: Endgame / Polish (optional)**
- Post-boss content (#11)
- Challenge modes (#13)
- Weapon enchantment (#12)

Only if the core game feels complete and you want more.

---

## Appendix: Key Lessons from the Research

1. **DCSS proves 15 main floors is the sweet spot** — but only if branches add 30-50+ more floors of optional content. Your current 12 branch floors (4 branches x 3 floors) should grow to 24-36.

2. **The best branches change rules, not just enemies.** Sokoban adds puzzles. Elemental Planes redefine survival. Abyss removes stairs. Your branches currently just swap water/lava and enemy pools. That's theming, not mechanical variety.

3. **Multi-tile monsters are a trap** (pun intended). Every classic roguelike represents dragons as 1 tile. The effort-to-fun ratio is terrible. Cogmind is the exception, and its developer spent months on it with a custom engine designed for it.

4. **Environmental storytelling is the cheapest way to add depth.** Pre-placed vignettes, journal fragments, and reactive NPC dialogue cost almost nothing to implement but make the dungeon feel alive rather than purely procedural.

5. **Boss phases are non-negotiable for a satisfying endgame.** Every memorable roguelike boss changes behavior as it takes damage. A boss that just has more HP is a speed bump, not a climax.

6. **Brogue's lesson: restraint is a feature.** Brogue is 26 floors with maybe 40 enemy types and no classes, and it's considered one of the best roguelikes ever made. Depth comes from interaction complexity, not content volume. Every new system should create emergent interactions with existing systems.

---

## Sources

- [Zork - Wikipedia](https://en.wikipedia.org/wiki/Zork)
- [Zork I - Zork Wiki](https://zork.fandom.com/wiki/Zork_I:_The_Great_Underground_Empire)
- [Zork III Game World - DeepWiki](https://deepwiki.com/historicalsource/zork3/5-game-world)
- [NetHack Mazes of Menace - NetHack Wiki](https://nethackwiki.com/wiki/Mazes_of_Menace)
- [NetHack Dungeon Level - NetHack Wiki](https://nethackwiki.com/wiki/Dungeon_level)
- [NetHack Sokoban - NetHack Wiki](https://nethackwiki.com/wiki/Sokoban)
- [NetHack Demogorgon - NetHack Wiki](https://nethackwiki.com/wiki/Demogorgon)
- [NetHack Speed Ascension - NetHack Wiki](https://nethackwiki.com/wiki/Speed_ascension)
- [Analysis of Expert NetHack Play](https://codehappy.net/nethack/data.htm)
- [DCSS Dungeon Branches - CrawlWiki](http://crawl.chaosforge.org/Dungeon_branches)
- [DCSS The Dungeon - CrawlWiki](http://crawl.chaosforge.org/The_Dungeon)
- [DCSS The Lair - CrawlWiki](http://crawl.chaosforge.org/The_Lair)
- [DCSS Speed Running - CrawlWiki](http://crawl.chaosforge.org/Speed_running)
- [DCSS Walkthrough - CrawlWiki](http://crawl.chaosforge.org/Walkthrough)
- [ADOM Caverns of Chaos - ADOM Wiki](https://ancardia.fandom.com/wiki/Caverns_of_chaos)
- [ADOM Locations - ADOM Wiki](https://ancardia.fandom.com/wiki/Locations)
- [Angband Dungeon Guide](https://angband.readthedocs.io/en/latest/dungeon.html)
- [Angband Forum: How Long Does a Game Take](https://angband.live/forums/forum/angband/vanilla/5769-how-long-does-a-game-take-you)
- [Brogue - RogueBasin](https://www.roguebasin.com/index.php/Brogue)
- [Brogue Level Generation - Brogue Wiki](https://brogue.fandom.com/wiki/Level_Generation)
- [Caves of Qud Zone Tiers - Official Wiki](https://wiki.cavesofqud.com/wiki/Zone_tier)
- [Caves of Qud Game Length Discussion](https://steamcommunity.com/app/333640/discussions/0/1489992080506463558/)
- [Dwarf Fortress Z-levels - DF Wiki](https://dwarffortresswiki.org/index.php/Z-level)
- [Cogmind: Multi-tile Robots](https://www.gridsagegames.com/blog/2013/10/multi-tile-robots/)
- [Cogmind: Developing Multitile Creatures in Roguelikes](https://www.gridsagegames.com/blog/2020/04/developing-multitile-creatures-roguelikes/)
- [Cogmind: Multitile Actors Revisited (2024)](https://www.gridsagegames.com/blog/2024/09/multitile-actors-revisited/)
- [Roguelike Personalities - RogueBasin](https://www.roguebasin.com/index.php/Personalities_of_different_roguelikes)
- [Environmental Storytelling in Video Games](https://gamedesignskills.com/game-design/environmental-storytelling/)
