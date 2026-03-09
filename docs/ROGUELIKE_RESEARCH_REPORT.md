# Roguelike Genre Research Report
## Depths of Dread: Competitive Analysis & Development Roadmap

**Prepared for:** Will Rompf
**Date:** March 3, 2026
**Scope:** 14 classic and modern roguelikes analyzed against Depths of Dread (v7597 LOC)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Game-by-Game Analysis](#2-game-by-game-analysis)
3. [Common Feature Matrix](#3-common-feature-matrix)
4. [Gap Analysis: Depths of Dread vs Classics](#4-gap-analysis-depths-of-dread-vs-classics)
5. [Recommended Additions](#5-recommended-additions)
6. [Architecture Lessons](#6-architecture-lessons)

---

## 1. Executive Summary

Depths of Dread is a competent, focused roguelike that successfully implements the core pillars of the genre: procedural dungeon generation (BSP), permadeath with save/load, turn-based combat, item identification, FOV/light mechanics, and multiple character classes. At ~7,600 lines of pure Python with zero external dependencies, it punches well above its weight. The Bot and Agent AI systems are genuinely innovative -- no classic roguelike shipped with a built-in LLM-powered player.

**Where Dread excels compared to classics:**
- Clean, modern Python codebase (vs. C/C++ sprawl in NetHack/Angband/DCSS)
- Built-in AI players (Bot + Claude Agent) -- unique in the genre
- Session recording and replay -- rare feature, well-implemented
- Balanced difficulty curve across 15 floors with themed zones
- Level-up choice system (choose-your-bonus) -- modern design borrowed from ToME/DCSS
- Puzzle system (pedestals, switches, locked stairs) -- uncommon in traditional roguelikes

**Where Dread falls short of genre expectations:**
- **No dungeon branches** -- every classic except Rogue has them; Dread is strictly linear
- **No religion/deity system** -- present in NetHack, DCSS, ADOM, Angband; a genre staple
- **Shallow monster AI** -- 8 AI types vs. NetHack's item-using, spell-casting, retreating monsters
- **No stealth system** -- Brogue, Sil, Cogmind, and Infra Arcana all have stealth as core gameplay
- **No trap system** -- Rogue had traps in 1980; nearly universal across the genre
- **Limited environmental interaction** -- water and lava exist but are mostly cosmetic
- **No equipment cursing/blessing** -- NetHack's BUC system is iconic and broadly adopted
- **No resistance/vulnerability system** -- fire/cold/poison resistances are standard across all major roguelikes
- **Only 15 floors** -- most classics have 26-100+ levels

**Key strategic recommendation:** Dread's greatest opportunity is not to compete with NetHack on complexity but to follow Brogue's design philosophy -- elegant depth through interconnected simple systems. The Claude Agent AI is a genuine differentiator that no classic possesses. Lean into that.

---

## 2. Game-by-Game Analysis

### 2.1 Rogue (1980) -- The Progenitor

**Developer:** Michael Toy, Glenn Wichman, Ken Arnold
**Language:** C
**Status:** Complete, no active development

**Core Features:**
- 26 dungeon levels, descend to retrieve the Amulet of Yendor and return
- Grid-based 3x3 room layouts per floor with corridors
- 26 monster types (one per letter of the alphabet)
- Weapons, armor, potions, scrolls, wands, food, rings
- Item identification: potions identified by color, scrolls by label; randomized each game
- Hunger clock requiring food management
- Permadeath with save-on-exit

**Monster AI:** Extremely simple -- monsters either chase the player or wander randomly. No special abilities, no fleeing, no item use.

**Win Condition:** Retrieve the Amulet of Yendor from level 26 and ascend back to level 1.

**What Made It Special:** Rogue proved that procedural content generation could create compelling gameplay. Every run was different. The item identification system forced players to take risks. The simplicity of its systems created surprising emergent behavior.

**Relevance to Dread:** Dread already exceeds Rogue in most dimensions. However, Rogue's "retrieve-and-return" objective is more interesting than Dread's "kill the boss on floor 15" -- the return trip with the Amulet added enormous tension. Consider an extraction mechanic.

---

### 2.2 NetHack (1987-present) -- The Kitchen Sink

**Developer:** The DevTeam
**Language:** C (~350,000 lines)
**Source:** [GitHub](https://github.com/NetHack/NetHack) (open source)
**Status:** Active (v3.6.7, v3.7 in development)

**Core Features:**
- ~50 dungeon levels across multiple branches (Mines, Sokoban, Vlad's Tower, Gehennom, etc.)
- 13 character roles (Archaeologist, Barbarian, Caveman, Healer, Knight, Monk, Priest, Ranger, Rogue, Samurai, Tourist, Valkyrie, Wizard) x 5 races x 3 alignments
- ~380 monster types with complex behaviors (item use, spell casting, fleeing, breeding, mimicry, shapeshifting)
- ~500 item types with BUC (Blessed/Uncursed/Cursed) system
- Pet system: tame animals that fight alongside you, level up, use equipment
- Polymorph: transform yourself or monsters into other creatures
- Altar sacrifice system: offer monster corpses for divine favor
- Price identification: learn item identity from shop prices
- Intrinsic resistances from eating monster corpses
- Wishes (via wand of wishing, luck, etc.)
- Engravings (write messages on the floor with wands to test them)
- Sokoban puzzle levels
- Extinction (kill enough of a monster type and no more spawn)

**Monster AI:**
- Intelligent monsters pick up and use items (potions, wands, scrolls)
- Monsters can wear armor and wield weapons
- Monsters flee when low on HP (cowardly flag)
- Liches and other spellcasters use spells tactically
- Mind flayers drain intelligence through tentacle attacks
- Mimics disguise as items or dungeon features
- Quantum mechanics: Schroedingers Cat exists in superposition

**Item Identification:**
- Three-tier system: appearance -> named -> formally identified
- BUC status (Blessed/Uncursed/Cursed) affects all item behavior
- Potions identified by color, scrolls by label, wands by material
- Price identification from shop prices is a key advanced technique
- Engrave-testing wands ("Elbereth" carved with a wand reveals its type)

**Win Condition:** Descend through the dungeon, retrieve the Amulet of Yendor from the bottom of Gehennom, ascend through the Elemental Planes, and offer the Amulet to your god on the Astral Plane.

**What Players Love:** The phrase "The DevTeam Thinks of Everything" (TDTTOE) captures NetHack's appeal -- nearly every interaction you can imagine has been coded. Dipping a poisoned corpse into a fountain, zapping yourself with a wand of polymorph while wearing a ring of polymorph control, using a cockatrice corpse as a weapon -- the emergent possibilities are legendary.

**What Players Criticize:** Unfair instadeaths (YASD -- "Yet Another Stupid Death"), spoiler-dependent gameplay, an ascension that requires hundreds of hours of learning, and UI that hasn't fundamentally changed since the 1980s.

**Relevance to Dread:** NetHack's interacting systems are its masterpiece. Dread doesn't need 500 items, but it needs more systems that interact with each other. Currently, Dread's systems are largely independent -- items don't interact with terrain, monsters don't use items, status effects don't combine.

---

### 2.3 Angband (1990-present) -- The Deep Dive

**Developer:** Community (originally Ben Harrison)
**Language:** C
**Source:** [GitHub](https://github.com/angband/angband) (open source)
**Status:** Active

**Core Features:**
- 100 dungeon levels, plus a town level for shopping/resupply
- Non-persistent levels: leaving a floor destroys it permanently
- Massive dungeon levels (many screens wide and tall)
- Tolkien-themed (goal: defeat Morgoth on level 100)
- Monster memory system: game remembers what you've observed about each monster type
- Ego items (enchanted variants like "of Gondolin," "of Westernesse")
- Artifact weapons and armor (unique named items)
- Resistance system: fire, cold, acid, lightning, poison, and many more
- Speed system: faster characters get more turns per round

**Monster AI:**
- Distance-based tracking using noise/scent pathfinding
- Morale-based fleeing (timid creatures flee at small wounds, maniacs fight to death)
- Spell-casting monsters with varied abilities (breath weapons, summoning, healing)
- "Breeds explosively" flag: creatures like lice multiply rapidly
- Monsters cannot pick up or use items (items generate on death)

**Dungeon Generation:** Random rooms and corridors, vaults (pre-designed areas with treasure and danger), greater vaults as special challenges. Every level is fresh -- no persistent maps.

**Win Condition:** Descend 100 levels to defeat Morgoth, Lord of Darkness.

**What Makes It Special:** Angband's non-persistent levels create a unique gameplay loop. You can always retreat to town, resupply, and dive again. The game is about finding the right depth where rewards match your power. The monster memory system rewards long-term play.

**What Players Criticize:** Repetitive gameplay (dive, retreat, shop, dive), lack of variety in dungeon layouts, and extremely long completion times (hundreds of hours).

**Relevance to Dread:** Angband's monster memory system would be excellent for Dread -- tracking what the player has learned about each enemy type. The resistance/vulnerability system is a must-add. The ego item system (enchanted weapon variants) could add item variety without many new base types.

---

### 2.4 ADOM (1994-present) -- The Story-Driven Roguelike

**Developer:** Thomas Biskup
**Language:** Originally C, rewritten for commercial release
**Status:** Active (Steam release with graphics)

**Core Features:**
- Overworld wilderness map with multiple towns, dungeons, and special locations
- 50+ level main dungeon (Caverns of Chaos) plus many side dungeons
- 12 races, 22 classes (combinations dramatically affect gameplay)
- Quest system: NPCs assign missions, solutions can be good or evil
- Alignment system (Lawful/Neutral/Chaotic) affecting NPC interactions, quests, and endings
- **Corruption system:** gradual chaos corruption causes mutations (beneficial, mixed, or harmful)
- Skills system (Herbalism, Alchemy, Mining, Swimming, etc.)
- Persistent levels: floors stay as you left them
- Herb growing system based on Conway's Game of Life
- Multiple endings based on alignment, corruption level, and quest completion
- Talent system for further character customization

**Corruption System (Signature Mechanic):**
Corruption accumulates over time, especially in deeper areas. Each corruption manifests as a visible mutation: antennae growing, skin turning to scales, legs becoming hooves. Some corruptions are useful (see invisible), some mixed (extra arms but reduced charisma), some devastating (food consumption doubles). At maximum corruption, your character becomes a "writhing mass of primal chaos" -- game over. This creates a ticking clock beyond hunger.

**Win Conditions:** Multiple -- close the chaos gate, become an ultra ending champion, or simply die trying. The game has ~7 different endings depending on player actions.

**What Makes It Special:** ADOM combines roguelike gameplay with RPG storytelling. The corruption system is brilliant -- it creates mounting tension as you race to complete your goals before chaos consumes you. The overworld gives the game a sense of place that pure dungeon crawlers lack.

**Relevance to Dread:** The corruption system is the single most transplantable concept for Dread. A gradual mutation/curse system that creates a secondary ticking clock (beyond hunger) would add enormous strategic depth. The quest system from NPCs is also worth considering -- even simple "kill X on floor Y" quests would add purpose.

---

### 2.5 Dungeon Crawl Stone Soup (DCSS) -- The Modern Standard

**Developer:** Community (originally Linley Henzell)
**Language:** C++ (~400,000 lines)
**Source:** [GitHub](https://github.com/crawl/crawl) (open source)
**Status:** Very active (0.33 as of 2025)

**Core Features:**
- 15 main dungeon levels plus ~15 branch dungeons (Lair, Orcish Mines, Elven Halls, Vaults, Depths, Zot, Abyss, Pandemonium, Hell branches)
- 27 playable species with unique mechanics (Octopodes wear 8 rings, Mummies can't drink potions, Felids have 9 lives)
- 26 backgrounds (starting loadouts, not permanent classes)
- **26 gods** each with unique mechanics, abilities, and restrictions
- Rune system: collect 3+ runes to enter the Realm of Zot and retrieve the Orb
- Skill training through use (hit things with swords to train short blades)
- Auto-explore, auto-fight built into the game
- Online play (watch other players in real-time via WebTiles)
- Tournament system with community scoring

**Religion System (Signature Feature):**
- **Trog:** Berserker god. Gifts weapons, forbids magic. Berserk ability.
- **Okawaru:** War god. Gifts weapons/armor. Heroism/Finesse abilities.
- **Sif Muna:** Magic god. Gifts spellbooks. Channel magic ability.
- **Xom:** Chaos god. Random help and random punishment. Unpredictable.
- **Jiyva:** Slime god. Reshape your body, eat items. Bizarre gameplay.
- **Makhleb:** Demon god. Health on kills, demon summoning.
- **Ashenzari:** Knowledge god. See through walls, sense items. Demands cursed equipment.
- Each god has piety that increases/decreases based on behavior conformance.
- Abandoning a god triggers divine wrath (punishments lasting hundreds of turns).

**Dungeon Branches:**
Branching paths create strategic choices. Do you enter the Spider's Nest or the Snake Pit? Do you attempt the Tomb of the Ancients for a bonus rune? Each branch has unique monsters, terrain, and challenges.

**Monster AI:**
- Monsters flee when low on HP (intelligent ones teleport or use potions)
- Monsters track invisible players through noise
- Unique named monsters with special abilities
- Monsters coordinate attacks (packs surround you)
- Friendly fire awareness (monsters avoid hitting allies with beams)

**Design Philosophy:** DCSS explicitly removes "unfun" mechanics. No food clock (removed in 0.26), no inventory Tetris, no item identification. The game believes every decision should be interesting -- if the optimal play is boring, the mechanic should be redesigned.

**What Players Love:** Tight balance, constantly evolving design, web-based play, spectator mode, the god system's replayability, and the design philosophy of "no boring decisions."

**What Players Criticize:** Frequent removal of mechanics that veterans enjoy (food, item identification), perceived "streamlining" that reduces depth, and the Abyss being tedious.

**Relevance to Dread:** DCSS is the single most relevant comparison for Dread. Similar floor count (15 main + branches vs. Dread's 15 linear), similar complexity ambition. The god system is the genre's gold standard for replayability -- even a simplified version (3-5 gods with 2-3 abilities each) would transform Dread. Dungeon branches are the #1 structural improvement Dread needs. DCSS's auto-explore/auto-fight implementation should inform Dread's existing but simpler versions.

---

### 2.6 Brogue (2009-present) -- The Elegant Minimalist

**Developer:** Brian Walker (Community Edition maintained)
**Language:** C
**Source:** [GitHub](https://github.com/tmewett/BrogueCE) (open source)
**Status:** Community Edition active

**Core Features:**
- 26 levels to retrieve the Amulet of Yendor (deeper levels contain lumenstones for bonus score)
- No character classes or levels -- progression is entirely through items
- **Scrolls of Enchantment** as the core progression mechanic (~15 per run, permanently enhance one item)
- Ally system: free captive monsters to fight alongside you
- Rich terrain interactions: fire spreads through grass, swamp gas explodes, water conducts electricity
- Visible color-coding for information density (each color has specific meaning)
- Self-identifying items (use them enough and they identify themselves)
- Simple but deep combat: heavy armor reduces damage but increases hit chance against you

**Terrain Interactions (Signature Feature):**
- Grass catches fire, creating spreading conflagrations
- Swamp gas is flammable and explosive
- Water conducts lightning
- Bog generates confusion gas
- Bridges can be destroyed
- Darkness is a real environmental hazard

**Ally System:**
Free captive monsters from cages. Allies level up alongside you, gain new abilities, and can be enhanced with wands of empowerment. Build strategies around your allies: use a war troll as a tank while you fire staffs, or swarm with empowered monkey allies.

**What Makes It Special:** Brogue proves that depth does not require complexity. Every system interacts with every other system. Fire + gas = explosion. Water + lightning = area damage. Allies + empowerment = army building. The enchantment system forces strategic commitment (enchant your sword? or your armor? or your staff?).

**Relevance to Dread:** Brogue should be Dread's primary design inspiration. Dread already has water and lava tiles, but they're mostly cosmetic. Making terrain interactive (fire spreading, water slowing, gas clouds from alchemy) would create emergent gameplay without adding much code. The ally system could work with Dread's summon scroll -- what if summoned creatures became persistent allies?

---

### 2.7 Caves of Qud (2015-present) -- The Mutation Engine

**Developer:** Freehold Games
**Language:** C#
**Status:** Active (recently released 1.0)

**Core Features:**
- Open-world exploration with procedural and fixed areas
- Two genotypes: Mutants (70+ mutations) and True Kin (cybernetic implants)
- Mutation system: physical mutations (wings, multiple arms, quills, flaming hands) and mental mutations (telepathy, telekinesis, precognition)
- Cooking system: combine ingredients for custom buffs
- Tinkering/crafting from salvaged components
- Faction system: 60+ factions with reputation tracking
- Water as currency in a post-apocalyptic desert
- Procedural history and procedurally generated books/lore
- Dense, literary writing

**Mutation System (Signature Feature):**
Mutations gain levels as you level up, growing more powerful. Physical mutations undergo "rapid advancement" at certain levels (permanent +3 bonus). Mental mutations scale with Ego stat. Defects (negative mutations) grant bonus mutation points at character creation, enabling risk/reward tradeoffs.

**What Makes It Special:** The worldbuilding density is unmatched. Procedurally generated histories, cultures, and myths. Every playthrough reveals new lore. The mutation system creates characters that feel genuinely alien -- a four-armed, telepathic, flaming-handed plant person is a valid build.

**Relevance to Dread:** Mutations are relevant as a potential extension of the corruption/curse concept. Rather than just negative effects, offer mixed mutations that change gameplay. A "Third Eye" mutation that grants extra FOV radius but attracts wraiths, for example.

---

### 2.8 Cogmind (2015-present) -- The Modular Robot

**Developer:** Grid Sage Games (Kyzrati)
**Language:** C#
**Status:** Active

**Core Features:**
- Play as a robot, scavenging parts from destroyed machines
- 1000+ parts replacing traditional character sheet (no levels, no stats -- your build IS your equipment)
- Destructible environment
- Stealth as a primary viable strategy (anti-combat design)
- Faction ecosystem: robots have hierarchies, patrol routes, alert states
- Heat/electromagnetic signature tracking
- Time-energy system (100 time units per turn, actions cost varying amounts)
- Information warfare (hacking, sensor disruption)

**What Makes It Special:** The "build = character" concept eliminates grinding and creates immediate tactical decisions. Every part you pick up is a meaningful choice. Stealth is as viable as combat. The destructible environment creates real consequences.

**Relevance to Dread:** Cogmind's stealth system is instructive. Dread's Rogue class has stealth-adjacent abilities (Shadow Step, Smoke Bomb) but no actual stealth system. A noise/detection model where moving creates sound and enemies can be alert/unaware/asleep would deepen Rogue gameplay significantly.

---

### 2.9 Tales of Maj'Eyal (ToME) (2012-present) -- The Talent Tree Master

**Developer:** DarkGod
**Language:** Lua (T-Engine4)
**Source:** [GitHub](https://github.com/toome/t-engine4) (open source)
**Status:** Active

**Core Features:**
- 25 classes across 6 class types, many with unique resource systems
- Talent tree system: 4-talent trees organized into category types
- Three talent types: Passive (always on), Active (use in combat), Sustained (toggle on/off)
- Class-specific resources (Hate for shadowblades, Paradox for chronomancers, Souls for necromancers)
- Overworld map with fixed towns and procedural dungeons
- Adventure mode (finite lives) alongside Roguelike mode (permadeath)
- Prodigies: powerful endgame talents unlocked at levels 30 and 42

**Talent Tree System (Signature Feature):**
Each class has 6-8 talent trees with 4 talents each. You invest points to unlock and level talents. Trees are organized thematically -- a Berserker has "Warcries," "Bloodbath," "Combat Techniques," etc. The depth comes from choosing which trees to invest in and which to ignore.

**What Makes It Special:** ToME proves you can have immense depth without sacrificing accessibility. The talent tree system gives clear progression paths while allowing meaningful build diversity. The class design is among the best in the genre -- each class plays genuinely differently.

**Relevance to Dread:** Dread's level-up choice system (Might/Arcana/Fortitude/Agility/Vitality) is a simplified version of ToME's approach. Consider expanding it: instead of 5 generic bonuses, offer class-specific talent trees where each choice unlocks a new passive or active ability. The Warrior already has Whirlwind/Cleaving Strike/Shield Wall -- frame these as a talent tree and add more options.

---

### 2.10 Sil (2012) -- The Stealth Masterpiece

**Developer:** Scatha & half
**Language:** C (Angband variant)
**Status:** Sil-Q (community fork) active

**Core Features:**
- Tolkien First Age setting (escape from Morgoth's fortress with a Silmaril)
- Skill-check based combat (d20 + skill vs. d20 + difficulty)
- Heavy armor: easier to hit, but reduces damage taken
- Light weapons: more accurate, better critical chance
- Abilities: purchased with XP, linked to skills (Stealth, Melee, Archery, etc.)
- Stealth as a fully viable win strategy (sneak past everything)
- Monster alertness states: Asleep, Unwary, Alert

**Stealth System (Signature Feature):**
Every round, the player makes a Stealth roll (stealth score + d10). Nearby monsters make Perception rolls (perception + d10). If the monster's roll exceeds yours, they become more alert. Alertness progresses: Asleep -> Unwary -> Alert. Light sources, noise from combat, and opening doors increase detection risk.

**What Makes It Special:** Sil is the most elegant combat system in the genre. Every decision matters: do you wear heavy armor and tank, or go light for stealth and crits? Do you invest XP in Melee abilities or Stealth abilities? The skill check system is transparent and fair.

**Relevance to Dread:** Sil's stealth system is the gold standard and should directly inform Dread's implementation. The monster alertness model (Asleep/Unwary/Alert) maps perfectly to Dread's existing `alerted` flag -- just expand it to three states.

---

### 2.11 Infra Arcana (2011-present) -- The Horror Roguelike

**Developer:** Martin Tornquist
**Language:** C++
**Source:** [GitHub](https://github.com/martin-tornqvist/ia) (open source)
**Status:** Active (v23.0.0)

**Core Features:**
- Lovecraftian horror setting (early 20th century)
- Goal: retrieve the Shining Trapezohedron from a cult dungeon
- **Shock/Insanity system** replacing hunger as the primary clock
- No XP from kills -- level-ups from exploration and events
- Trait selection on level-up (powerful passive bonuses)
- Firearms and explosives alongside melee
- Darkness and light as core gameplay (staying in darkness increases Shock)

**Shock/Insanity System (Signature Feature):**
Shock accumulates from: seeing horrifying monsters, staying in darkness, carrying unholy artifacts, using occult powers, spending too much time in the dungeon. Standing in light reduces Shock. Descending a floor resets Shock to 0. When Shock reaches 100%, you "snap" -- random effects like uncontrollable laughter, fainting, or gaining a permanent phobia. Then Shock resets, but Insanity increases permanently. At 100% Insanity, game over.

**What Makes It Special:** Infra Arcana replaces the hunger clock (widely considered the genre's most tedious mechanic) with a thematic, interesting alternative. The Shock system forces you to play efficiently -- dawdling costs sanity, not food. This creates urgency without the tedium of "eat bread every 50 turns."

**Relevance to Dread:** The Shock system is highly relevant because Dread already has both a hunger system and a "Dread" theme. A "Dread meter" that increases from seeing bosses, exploring deep floors, and staying in darkness would be incredibly thematic. It could replace or supplement hunger as the primary pressure clock.

---

### 2.12 Cataclysm: Dark Days Ahead (2013-present) -- The Survival Sandbox

**Developer:** Community (CleverRaven)
**Language:** C++
**Source:** [GitHub](https://github.com/CleverRaven/Cataclysm-DDA) (open source)
**Status:** Very active

**Core Features:**
- Post-apocalyptic open-world survival
- Hunger, thirst, temperature, morale, sleep, illness, pain, addiction tracking
- Deep crafting system (thousands of recipes requiring materials, tools, skills, and recipe knowledge)
- Vehicle construction and modification
- Bionic implants and mutations
- Non-linear gameplay -- no dungeon, no goal, just survive
- NPC interactions and faction relationships
- Construction system (build fortifications, shelters, farms)

**What Makes It Special:** CDDA is the most detailed survival simulation in any roguelike. Temperature simulation, realistic wound treatment, drug withdrawal effects, vehicle physics, farming cycles -- it's a survival sim first and a roguelike second.

**Relevance to Dread:** Limited direct relevance due to vastly different scope. However, CDDA's crafting system (combining items to create new items) could inspire a simplified version for Dread's alchemy tables. Currently, alchemy tables just identify items -- they could combine potions or upgrade equipment.

---

### 2.13 Zork (1977-1982) -- The Text Adventure Pioneer

**Developer:** Infocom (Tim Anderson, Marc Blank, Bruce Daniels, Dave Lebling)
**Language:** ZIL (Zork Implementation Language)

**Core Features:**
- Natural language parser understanding ~900 words and 70 actions
- Elaborate puzzles requiring creative item combination
- Vibrant, humorous writing establishing game personality
- No procedural generation -- handcrafted world
- Light/darkness mechanics (get eaten by a grue in the dark)

**Relevance to Dread:** Zork's contribution is the concept of game personality through writing. Dread has death quips and flavor text, but could dramatically benefit from more environmental storytelling -- room descriptions, lore fragments, journal entries about previous adventurers who failed.

---

### 2.14 Dwarf Fortress Adventure Mode (2006-present)

**Developer:** Tarn & Zach Adams
**Language:** C++

**Core Features:**
- Procedurally generated world with history spanning hundreds of years
- Anatomically detailed combat (target individual fingers, sever arteries, bruise specific organs)
- Material properties affecting combat (steel vs. iron vs. copper)
- Wrestling and grappling system
- NPC conversation system
- Procedural character portraits reflecting wounds and equipment
- World persistence: your adventurer exists in a world others have affected

**Relevance to Dread:** Dwarf Fortress's locational damage system (targeting body parts) could add depth to Dread's combat without enormous complexity. "You slash the Troll's left arm" is more interesting than "You hit the Troll for 8 damage."

---

## 3. Common Feature Matrix

| Feature | Rogue | NetHack | Angband | ADOM | DCSS | Brogue | CoQ | Cogmind | ToME | Sil | IA | CDDA | DF:AM | **Dread** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Permadeath** | Y | Y | Y | Y | Y | Y | Y | Y | Opt | Y | Y | Opt | Y | **Y** |
| **Dungeon Branches** | N | Y | N | Y | Y | N | Open | Y | Y | N | N | Open | Open | **N** |
| **Classes/Races** | N | Y | Y | Y | Y | N | Y | N | Y | N | N | Y | Y | **Y (3)** |
| **Religion/Gods** | N | Y | N | Y | Y | N | N | N | N | N | N | N | N | **N** |
| **Item ID System** | Y | Y | Y | Y | Removed | Y | Partial | N | N | N | N | N | N | **Y** |
| **Hunger Clock** | Y | Y | Y | Y | Removed | Y | Y | N | N | Y | Shock | Y | N | **Y** |
| **Trap System** | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | **N** |
| **Stealth System** | N | N | N | Partial | N | Partial | Y | Y | Partial | Y | Y | Y | Y | **N** |
| **Resistance Types** | N | Y | Y | Y | Y | N | Y | N | Y | Y | Y | Y | Y | **N** |
| **Cursed/Blessed Items** | N | Y | Y | Y | Y | N | N | N | N | N | N | N | N | **N** |
| **Allies/Pets** | N | Y | N | Y | Y | Y | Y | N | Y | N | N | Y | Y | **N** |
| **Environmental Interaction** | N | Y | N | Partial | Partial | Y | Y | Y | N | N | N | Y | Y | **Minimal** |
| **Crafting/Alchemy** | N | N | N | Y | N | N | Y | N | N | N | N | Y | Y | **Minimal** |
| **Monster Fleeing** | N | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | **N** |
| **Monster Item Use** | N | Y | N | Y | Y | N | Y | N | Y | N | N | N | Y | **N** |
| **Monster Spells** | N | Y | Y | Y | Y | Partial | Y | Y | Y | N | Y | N | N | **Partial** |
| **Multiple Endings** | N | N | N | Y | N | N | Y | Y | Y | N | N | N | N | **N** |
| **Overworld Map** | N | N | N | Y | N | N | Y | N | Y | N | N | Y | Y | **N** |
| **Scoring System** | Y | Y | Y | N | N | Y | N | Y | N | Y | Y | N | N | **Y** |
| **Auto-Explore** | N | N | N | N | Y | N | Y | N | Y | N | N | Y | N | **Y** |
| **Auto-Fight** | N | N | N | N | Y | N | N | N | Y | N | N | N | N | **Y** |
| **AI Player (Bot)** | N | N | N | N | N | N | N | N | N | N | N | N | N | **Y** |
| **AI Player (LLM)** | N | N | N | N | N | N | N | N | N | N | N | N | N | **Y** |
| **Session Replay** | N | N | N | N | Partial | N | N | N | N | N | N | N | N | **Y** |
| **Save/Load** | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | **Y** |
| **Puzzle Rooms** | N | Y | N | Partial | N | N | N | N | N | N | N | N | N | **Y** |
| **Journal System** | N | Partial | N | Partial | N | N | Y | N | Y | N | N | N | N | **Y** |
| **Light/Torch** | N | Y | Y | Y | N | Y | Y | N | N | Y | Y | Y | Y | **Y** |
| **Shops** | N | Y | Y | Y | Y | N | Y | N | Y | N | N | N | N | **Y** |

**Legend:** Y = Yes, N = No, Partial = Limited implementation, Opt = Optional, Open = Open world (no dungeon), Removed = Was present but removed

---

## 4. Gap Analysis: Depths of Dread vs Classics

### 4.1 Critical Gaps (Present in 10+ of 13 analyzed games)

**1. Trap System**
Present in every analyzed game except Cogmind (which has its own version). Dread has zero traps. This is the most glaring omission.
- Common trap types: pit traps, teleport traps, alarm traps, dart traps, bear traps
- Trap interaction: detection (Rogue class bonus), disarming, triggering on purpose, using against enemies

**2. Monster Fleeing/Retreat**
Present in 12/13 games. Dread's monsters never flee. They fight to the death or chase indefinitely.
- NetHack: cowardly flag
- Angband: morale-based (damage taken vs. morale threshold)
- DCSS: intelligent monsters use escape items, teleport, or run

**3. Resistance/Vulnerability System**
Present in 10/13 games. Dread has no elemental resistance system despite having fire (lava, Fireball, Fire Elemental) and cold/lightning spells.
- Standard set: fire, cold, lightning, poison, acid
- Gained through: equipment, potions, racial traits, consumables, divine gifts
- Creates tactical depth: "this enemy is fire-resistant, switch to lightning"

**4. Monster Item Use**
Present in 6/13 games. Dread's monsters have no item interaction.
- NetHack: monsters pick up and use potions, wands, armor, weapons
- DCSS: unique monsters have special equipment that drops on death
- This creates "arms race" dynamics and makes equipment drops meaningful

### 4.2 Significant Gaps (Present in 6-9 of 13 analyzed games)

**5. Stealth System**
Present in 8/13 games. Dread has no stealth beyond Rogue's class abilities.
- Monster alertness states (Asleep/Unwary/Alert)
- Noise generation from combat, movement, doors
- Stealth attacks from unaware state deal bonus damage

**6. Ally/Pet System**
Present in 8/13 games. Dread has no persistent allies.
- Summoned creatures could become temporary allies
- Freed prisoners could join the party
- Allies create tactical positioning decisions

**7. Dungeon Branches**
Present in 7/13 games (excluding open-world games). Dread is strictly linear.
- Even 2-3 optional branches would dramatically increase replayability
- Branch choice = strategic decision (easier path vs. better loot)
- Enables runes/keys gating the final floor

**8. Religion/Deity System**
Present in 5/13 games, but those 5 (NetHack, ADOM, DCSS, Angband, ToME) are the most-played roguelikes.
- Even a simple system (3 gods, 2 abilities each) adds replayability
- Prayer mechanic already exists in Dread's shrine system -- expand it

**9. Cursed/Blessed Item States**
Present in 5/13 games. Dread has Ring of Hunger as a "cursed" item but no systematic curse/bless system.
- BUC adds risk to equipping unidentified items
- Cursed items can't be unequipped without remove curse
- Blessed items have enhanced effects

### 4.3 Notable Gaps (Present in 3-5 of 13 analyzed games)

**10. Environmental Interaction**
Present in 5/13 games. Dread has water (slows) and lava (damages) but limited interaction.
- Fire spreading through flammable terrain
- Explosions destroying walls/doors
- Water conducting lightning spells
- Gas clouds from alchemy/potion reactions
- Oil on ground making creatures slip

**11. Crafting/Alchemy System**
Present in 4/13 games. Dread has alchemy tables that only identify items.
- Combine two potions to create a new one
- Upgrade weapons/armor at forges
- Recipe discovery through experimentation

**12. Multiple Endings**
Present in 4/13 games. Dread has exactly one ending (kill the Dread Lord).
- Good/evil endings based on shrine choices
- Speed run ending for fast completions
- Pacifist ending (escape without killing the Dread Lord)
- Secret ending for finding hidden content

### 4.4 Where Dread Exceeds Classics

**Bot AI Player:** No classic roguelike ships with a built-in automated player. Dread's BotPlayer with 4-layer decision tree and loop detection is unique.

**Agent AI Player:** Claude-powered tactical decision-making is unprecedented. The hybrid approach (Bot for routine, Claude for tactical) is genuinely novel game design.

**Session Recording/Replay:** While DCSS has WebTiles spectating and some games have ttyrec support, Dread's built-in JSONL recording with visual replay is more polished than most.

**Puzzle System:** Floor puzzles (pedestals, switches, locked stairs) are uncommon in traditional roguelikes. Brogue has key vaults, NetHack has Sokoban, but Dread's implementation is distinctive.

**Level-Up Choice System:** The choose-your-bonus system at level up (Might/Arcana/Fortitude/Agility/Vitality plus class-specific options) is more engaging than the stat-point-allocation systems in most classics.

**Themed Floor Progression:** Dungeon -> Caverns -> Catacombs -> Hellvault -> Abyss provides clear thematic progression. Most classics have less distinct visual theming.

---

## 5. Recommended Additions

### 5.1 Must-Have (Genre Expectations Dread Lacks)

These features are so universal that their absence makes Dread feel incomplete to roguelike veterans.

**M1. Trap System** (Effort: Medium, ~200-300 LOC)
```
Trap types:
- Pit trap: fall damage + potentially fall to next floor
- Dart trap: ranged poison damage
- Teleport trap: random teleport
- Alarm trap: alerts all enemies on floor
- Bear trap: immobilize for 3 turns
- Gas trap: create confusion/poison cloud

Implementation:
- Add T_TRAP_HIDDEN and T_TRAP_VISIBLE tile types
- Traps placed during floor generation (2-5 per floor scaling with depth)
- Rogue class: 30% chance to detect hidden traps when adjacent
- All classes: 's' key to search adjacent tiles for traps
- Disarm: INT/DEX check (Rogue bonus), failure triggers trap
- Monsters can trigger traps too (tactical use!)
```

**M2. Monster Fleeing** (Effort: Low, ~50-80 LOC)
```
Add morale system:
- Each enemy type gets a morale threshold (0.0 to 1.0)
  - Rats: 0.2 (flee at 80% HP)
  - Goblins: 0.4 (flee at 60% HP)
  - Trolls: 0.7 (fight until 30% HP)
  - Bosses: 1.0 (never flee)
- When HP < morale * max_hp, enemy switches to flee AI
- Flee AI: move away from player using A*, pick random direction if cornered
- Fleeing enemies that reach map edge despawn (escaped)
- XP awarded for routing enemies (half kill XP)
```

**M3. Resistance/Vulnerability System** (Effort: Medium, ~200-250 LOC)
```
Elements: Fire, Cold, Lightning, Poison
- Fire Elemental: immune to fire, vulnerable to cold
- Wraith: resistant to physical, vulnerable to fire
- Troll: regenerates, but fire stops regen for 5 turns
- Demon: resistant to fire, vulnerable to cold

Player resistances gained through:
- Equipment (Ring of Fire Resistance, Mithril Mail = cold resist)
- Potions (temporary)
- Shrine boons
- Level-up choices (new option: "Attunement: +1 resistance")

Combat: resistance reduces elemental damage by 50%, vulnerability increases by 50%
```

**M4. Trap + Environmental Hazard Interaction** (Effort: Low, ~100 LOC)
```
Water + Lightning = AoE damage to everything in water
Lava + Cold spell = create temporary floor (5 turns)
Fire on grass/wooden doors = spreading fire
Oil + fire = large explosion
Gas cloud + fire = explosion
```

### 5.2 Should-Have (Significant Depth Improvements)

These features would meaningfully differentiate Dread and increase replayability.

**S1. Dungeon Branches** (Effort: High, ~400-600 LOC)
```
Structure:
Floor 1-4: Main Dungeon (linear)
Floor 5: Branch choice appears:
  - Path A: The Flooded Crypts (water-heavy, undead, cold damage)
  - Path B: The Burning Pits (lava-heavy, demons, fire damage)
Floor 6-8: Chosen branch (unique enemies, terrain, loot)
Floor 9: Branches merge back to main dungeon
Floor 10: Second branch choice:
  - Path A: The Mind Halls (mind flayers, psychic damage, confusion)
  - Path B: The Beast Warrens (pack enemies, traps, speed challenges)
Floor 11-13: Chosen branch
Floor 14: Converge
Floor 15: Dread Lord

Each branch has a unique mini-boss and exclusive loot.
This doubles effective content with minimal additional enemy/item types.
```

**S2. Stealth System** (Effort: Medium, ~250-350 LOC)
```
Monster states: ASLEEP (doesn't act), UNWARY (patrols, easy to sneak past),
               ALERT (actively hunts player)

Noise system:
- Walking on floor: 2 noise
- Walking on corridor: 1 noise
- Opening door: 4 noise
- Combat: 8 noise
- Spells: 6 noise
- Rogue class: all noise reduced by 50%

Detection: Each turn, noise propagates through tiles. If noise reaches
a sleeping/unwary enemy, they roll perception vs. player stealth.
Failure = state upgrade (asleep->unwary->alert).

Backstab: attacking an asleep/unwary enemy = guaranteed crit (2x damage)
This makes Rogue's existing abilities (Backstab, Shadow Step) much more
meaningful and creates a distinct playstyle.
```

**S3. Simple Deity System** (Effort: High, ~500-700 LOC)
```
Three gods, choose at first shrine encountered:

VALTHOR (War God):
- Passive: +2 STR while worshipping
- Ability 1 (piety 30): Battle Rage (berserk without potion, 1/floor)
- Ability 2 (piety 60): Divine Weapon (enchant wielded weapon +3)
- Restriction: Never flee from combat
- Wrath (if abandoned): Strength drain for 50 turns

SYLARA (Nature God):
- Passive: Hunger depletes 50% slower
- Ability 1 (piety 30): Heal (free heal spell, 1/floor)
- Ability 2 (piety 60): Regeneration (passive HP regen)
- Restriction: Never use fire spells/wands
- Wrath: Poison for 30 turns

NETHYS (Shadow God):
- Passive: +5% evasion, see in darkness (radius 3 even without torch)
- Ability 1 (piety 30): Shadow Cloak (invisibility for 10 turns, 1/floor)
- Ability 2 (piety 60): Death Strike (instant kill non-boss below 15% HP)
- Restriction: Never pray at shrines (only worship through kills)
- Wrath: Blindness for 20 turns

Piety gained by: kills (Valthor/Nethys), healing (Sylara),
  exploring floors (all), offering gold at shrines (Valthor/Sylara)
```

**S4. Monster Memory/Bestiary** (Effort: Low, ~100-150 LOC)
```
Track per-monster-type:
- Times encountered
- Times killed
- Damage dealt/received
- Special abilities observed (poison, teleport, etc.)
- Resistances/vulnerabilities observed

Display via 'M' key (Monster Memory screen)
First encounter: "Rat - A small vermin. Aggressive."
After 5 kills: "Rat - HP: ~6, DMG: 1-3, No special abilities."
After 10 kills: "Rat - Cowardly. Weak to fire."

This rewards experienced players and integrates with the
resistance/vulnerability system.
```

### 5.3 Nice-to-Have (Polish and Advanced Features)

**N1. Cursed/Blessed Items** (Effort: Medium, ~200 LOC)
```
- 15% of equipment spawns cursed (negative enchantment, can't unequip)
- 10% spawns blessed (bonus enchantment)
- Scroll of Remove Curse: uncurse all worn equipment
- Shrine prayer can bless/curse items
- Adds risk to equipping unidentified gear
```

**N2. Environmental Storytelling** (Effort: Low, ~150 LOC)
```
- Skeletal remains on floor tiles with randomized lore messages:
  "A skeleton clutches a journal: 'Floor 7... the trolls never stop..'"
  "Scratched into the wall: 'BEWARE THE MIMIC'"
  "A half-eaten adventurer. Their pack contains..."
- 1-2 per floor, provides atmosphere and occasional hints
- Themed to floor zone (Dungeon/Caverns/Catacombs/Hellvault/Abyss)
```

**N3. Thrown Potions** (Effort: Low, ~80 LOC)
```
- Allow potions to be thrown at enemies (like scrolls but targeted)
- Potion of Healing: heals the target (throw at ally?)
- Potion of Poison: damages enemy
- Potion of Blindness: blinds enemy for N turns
- Potion of Speed: speeds up target (don't throw at enemies!)
- Uses existing projectile system
```

**N4. Unique Named Items** (Effort: Medium, ~200 LOC)
```
Artifacts: unique items that appear only once per run
- "Thornhaven's Last Light" (torch, infinite fuel, +2 FOV radius)
- "The Famine Ring" (Ring of Hunger + Ring of Regeneration combined)
- "Wraithbane" (weapon, bonus damage vs. undead, glows near hidden enemies)
- 1 artifact guaranteed per 5 floors, always on the floor (not from drops)
```

**N5. Ally System** (Effort: Medium-High, ~300-400 LOC)
```
- Scroll of Summon now creates a persistent ally (instead of hostile)
- Allies follow you between floors
- Maximum 1 ally at a time
- Ally levels up when you do (HP + damage increase)
- 'a' key: command ally (follow, wait, attack target)
- Allies can die permanently
- Specific enemy types can be "tamed" by Rogues (rat, bat, goblin)
```

**N6. Dread Meter (Corruption/Insanity)** (Effort: Medium, ~250 LOC)
```
Thematic replacement/supplement for hunger as pressure clock:
- Dread increases: seeing bosses (+20), entering new floors (+5),
  staying on a floor >100 turns (+1/turn), being in darkness (+0.5/turn)
- Dread decreases: kills (-2), finding treasure (-1), praying (-10),
  resting near wall torches (-3/rest)
- At 50% Dread: minor effects (hallucinations - fake enemies appear)
- At 75% Dread: moderate effects (random paralysis, stat drain)
- At 100% Dread: character flees to the surface (run ends, scored)
- Thematically perfect for "Depths of DREAD"
```

### 5.4 Unique Opportunities (Leveraging the Claude AI Agent)

These are features no classic roguelike can offer because they didn't have LLMs.

**U1. AI Narrator** (Effort: Medium, ~200 LOC)
```
Use Claude to generate contextual narration for key events:
- Boss encounters: "The Vampire Lord rises from his coffin,
  crimson eyes blazing. 'Another mortal seeks the throne?
  How... delicious.'"
- Floor transitions: procedurally generated descriptions
- Item discovery: flavor text for rare items
- Death: personalized epitaph based on run history
- Victory: unique congratulatory narrative

Implementation: 1 Claude call per major event (boss, floor, death)
Cost: ~5-10 calls per run at haiku tier = negligible
```

**U2. Adaptive Difficulty via Agent** (Effort: Medium, ~200 LOC)
```
Use the Agent's game state analysis to tune difficulty:
- If player is consistently dying on floor 3-5: reduce enemy count
- If player is breezing through: add elite variants of enemies
- Track across sessions via lifetime stats
- Claude analyzes play patterns and suggests balance adjustments
- "The dungeon senses your weakness..." / "The dungeon respects your strength..."
```

**U3. AI Dungeon Master Mode** (Effort: High, ~500 LOC)
```
A new mode where Claude acts as a DM:
- Generates custom room descriptions
- Creates dynamic quests ("An imprisoned dwarf begs for help")
- Adjusts encounters based on narrative arc
- Provides hints when player is stuck
- Creates a unique storyline per run

This would be Dread's killer feature -- a roguelike with a
procedurally generated narrative driven by an AI storyteller.
```

**U4. Post-Run Analysis** (Effort: Low, ~100 LOC)
```
After death/victory, Claude analyzes the session recording:
- "You died because you entered floor 10 without fire resistance"
- "Your best move was saving the Scroll of Teleport for the boss"
- "Consider: the Warrior's Shield Wall would have saved you on turn 847"
- "Rating: B+ (strong early game, overextended on floor 12)"

Uses existing session recording JSONL format.
One Claude call at end of run.
```

**U5. Community Challenge Generator** (Effort: Low, ~80 LOC)
```
Claude generates daily/weekly challenges:
- "Pacifist Run: reach floor 10 without killing anything"
- "Speed Run: clear floor 15 in under 500 turns"
- "Minimalist: win with only items found on the floor (no shops)"
- "The Dread Diet: win without eating food (Mage + regen ring)"
```

---

## 6. Architecture Lessons

### 6.1 What Classic Source Codes Teach Us

**NetHack (C, ~350K LOC):**
- Monolithic architecture, deeply interconnected systems
- `fight.c` handles melee, `mhitu.c` handles monster attacks on you, `mhitm.c` handles monster-on-monster -- three separate files for conceptually related code
- Item behavior scattered across dozens of files (one per item type)
- **Lesson for Dread:** NetHack's architecture is a cautionary tale. Dread's single-file approach is actually better for a game of this scale. Keep it single-file until it exceeds ~15K LOC, then split into modules by system (combat.py, dungeon.py, items.py, monsters.py)

**DCSS (C++, ~400K LOC):**
- Well-structured with clear separation: `mon-act.cc`, `mon-cast.cc`, `mon-gear.cc`, `mon-pathfind.cc`
- Data-driven design: monster definitions, item properties, and spell effects in external data files (YAML/text)
- **Lesson for Dread:** Dread already does this well with ENEMY_TYPES, WEAPON_TYPES, etc. as data dictionaries. Expand this pattern for new systems (trap types, deity definitions, branch definitions).

**Brogue (C, ~30K LOC):**
- Clean, modular C with excellent naming conventions
- Terrain interactions implemented through a dispatch table (fire_type + terrain_type -> result)
- AI behaviors are simple state machines with clear state transitions
- **Lesson for Dread:** Brogue is the right complexity target. At 7.6K LOC, Dread could grow to Brogue's 30K LOC and still be maintainable. The dispatch-table approach to terrain interactions is elegant -- implement it for elemental damage + terrain combinations.

**Angband (C, ~100K LOC):**
- Data-driven monster and item definitions in text files (`monster.txt`, `object.txt`)
- Monster AI in `mon-move.c` uses distance maps (noise/scent propagation)
- **Lesson for Dread:** The noise/scent propagation model is exactly what Dread needs for a stealth system. Compute a noise map each turn (BFS from player with decay), check if noise at each monster's position exceeds their perception threshold.

### 6.2 Dread's Current Architecture: Strengths and Risks

**Strengths:**
- Single file, zero dependencies -- easy to deploy, easy to understand
- Clean separation of data (ENEMY_TYPES, WEAPON_TYPES) from logic
- BALANCE dictionary for tuning -- excellent for iteration
- GameState class encapsulates all mutable state cleanly
- Bot/Agent as separate classes composing with GameState -- good OOP
- Session recording as JSONL -- simple, appendable, parseable

**Risks as complexity grows:**
- At 7.6K LOC, the file is manageable. At 15K+, a single file becomes unwieldy for navigation
- Enemy AI is scattered across 8 separate functions (`_chase_move`, `_patrol_move`, `_ambush_move`, etc.) -- not easily extensible
- Adding new systems (stealth, traps, deities) will bloat the constants section
- The `game_loop` function is a massive if/elif chain -- adding more keys will make it harder to maintain

**Recommended architecture evolution (at ~12K+ LOC):**
```
dungeon/
  __init__.py       -- Package init, version
  constants.py      -- All data definitions (enemies, items, spells, etc.)
  balance.py        -- BALANCE dict + helpers
  game_state.py     -- GameState, Player, Enemy, Item classes
  dungeon_gen.py    -- BSP generation, floor population
  fov.py            -- Shadowcasting, LOS
  pathfinding.py    -- A*, BFS, noise propagation
  combat.py         -- Melee, ranged, spell, ability logic
  items.py          -- Item use, identification, crafting
  monsters.py       -- AI behaviors, morale, alertness
  ui.py             -- Curses rendering, screens, input handling
  bot.py            -- BotPlayer
  agent.py          -- AgentPlayer
  recording.py      -- SessionRecorder, replay
  save.py           -- Save/load, lifetime stats
  deities.py        -- God system (future)
  traps.py          -- Trap system (future)
  branches.py       -- Branch definitions (future)
dungeon.py          -- Entry point (thin wrapper)
```

### 6.3 Data-Driven Design Patterns from Classics

The most maintainable roguelikes use data-driven design extensively. Dread already does this for enemies and items. Extend the pattern:

```python
# Trap definitions (data-driven, like ENEMY_TYPES)
TRAP_TYPES = {
    "pit":      {"name": "Pit Trap",      "char": '^', "damage": (3, 8),  "effect": "fall",     "detect_dc": 12},
    "dart":     {"name": "Dart Trap",      "char": '^', "damage": (2, 6),  "effect": "poison",   "detect_dc": 14},
    "teleport": {"name": "Teleport Trap",  "char": '^', "damage": (0, 0),  "effect": "teleport", "detect_dc": 16},
    "alarm":    {"name": "Alarm Trap",     "char": '^', "damage": (0, 0),  "effect": "alert_all","detect_dc": 10},
    "gas":      {"name": "Gas Trap",       "char": '^', "damage": (0, 0),  "effect": "confusion","detect_dc": 18},
}

# Deity definitions (data-driven)
DEITIES = {
    "valthor": {
        "name": "Valthor", "domain": "War",
        "passive": {"stat": "strength", "value": 2},
        "abilities": [
            {"name": "Battle Rage", "piety_req": 30, "cooldown": "per_floor", "effect": "berserk"},
            {"name": "Divine Weapon", "piety_req": 60, "cooldown": "per_floor", "effect": "enchant_weapon"},
        ],
        "restriction": "never_flee",
        "piety_gain": {"kill": 2, "explore_floor": 5},
        "wrath": {"effect": "str_drain", "duration": 50},
    },
    # ... more deities
}
```

### 6.4 Testing Strategy

Dread already has 244 unit tests -- excellent. For new systems, follow DCSS's testing model:

- **Trap tests:** Verify detection rolls, damage application, disarm mechanics, monster triggering
- **Stealth tests:** Verify noise propagation, alertness state transitions, backstab damage
- **Deity tests:** Verify piety accumulation, ability unlocks, restriction enforcement, wrath triggers
- **Resistance tests:** Verify damage modification, resistance stacking, vulnerability interactions
- **Integration tests:** Bot plays 100 games with new systems, verify no crashes, reasonable win rates

### 6.5 Performance Considerations

At 15 floors with ~20-30 enemies per floor, Dread has no performance concerns. However, some proposed systems have performance implications:

- **Noise propagation (stealth):** BFS from player position each turn. At 80x40 map, this is ~3,200 tiles max. Trivially fast in Python.
- **Terrain fire spreading:** Cellular automata each turn for fire tiles. Only process fire tiles + neighbors. Negligible cost.
- **AI state machine per monster:** Currently O(n) per turn for n enemies. Adding stealth checks doesn't change this.
- **Session recording with new events:** JSONL append is O(1). No concern.

---

## Sources

### Primary Sources
- [Rogue - Wikipedia](https://en.wikipedia.org/wiki/Rogue_(video_game))
- [Rogue - RogueBasin](https://www.roguebasin.com/index.php/Rogue)
- [NetHack Wiki](https://nethackwiki.com/wiki/NetHack)
- [NetHack Identification System](https://nethackwiki.com/wiki/Identification)
- [NetHack Source Architecture (DeepWiki)](https://deepwiki.com/NetHack/NetHack)
- [NetHack Level Generation](https://deepwiki.com/NetHack/NetHack/3.2-level-generation)
- [NetHack Polymorph System](https://nethackwiki.com/wiki/Polymorph)
- [NetHack Pet System](https://nethackwiki.com/wiki/Pet)
- [Angband - Wikipedia](https://en.wikipedia.org/wiki/Angband_(video_game))
- [Angband Monster AI (GitHub)](https://github.com/angband/angband/blob/master/src/doc/monster-ai.md)
- [Angband Manual](https://angband.readthedocs.io/en/latest/hacking/how-it-works.html)
- [ADOM - Wikipedia](https://en.wikipedia.org/wiki/Ancient_Domains_of_Mystery)
- [ADOM Corruption Guide](http://adomgb.info/adomgb-0-10.html)
- [DCSS - Wikipedia](https://en.wikipedia.org/wiki/Dungeon_Crawl_Stone_Soup)
- [DCSS GitHub Repository](https://github.com/crawl/crawl)
- [DCSS God Mechanics Wiki](https://crawl.develz.org/wiki/doku.php?id=dcss:brainstorm:god:concept:general)
- [DCSS Dungeon Branches (CrawlWiki)](http://crawl.chaosforge.org/Dungeon_branches)
- [DCSS Choosing a God (CrawlWiki)](http://crawl.chaosforge.org/Choosing_a_god)
- [Brogue - Wikipedia](https://en.wikipedia.org/wiki/Brogue_(video_game))
- [Brogue Community Edition (GitHub)](https://github.com/tmewett/BrogueCE)
- [Brogue Dungeon Generation Analysis](http://anderoonies.github.io/2020/03/17/brogue-generation.html)
- [Brogue Enchantment Scroll (Wiki)](https://brogue.fandom.com/wiki/Scroll_of_Enchanting)
- [Caves of Qud Mutations (Wiki)](https://wiki.cavesofqud.com/wiki/Mutations)
- [Caves of Qud - RogueBasin](https://www.roguebasin.com/index.php/Caves_of_Qud)
- [Cogmind - Wikipedia](https://en.wikipedia.org/wiki/Cogmind)
- [Cogmind Blog](https://www.gridsagegames.com/blog/2015/04/cogmind-roguelike/)
- [Tales of Maj'Eyal - RogueBasin](https://www.roguebasin.com/index.php/Tales_of_Maj'Eyal)
- [ToME Talent System](https://te4.org/wiki/Talent)
- [Sil - RogueBasin](https://www.roguebasin.com/index.php/Sil)
- [Sil Manual (PDF)](http://www.amirrorclear.net/flowers/game/sil/v101/Sil-Manual.pdf)
- [Infra Arcana - RogueBasin](https://www.roguebasin.com/index.php/Infra_Arcana)
- [Infra Arcana Madness Analysis](https://blog.patientrock.com/descending-into-madness-infra-arcana/)
- [Cataclysm: DDA - Wikipedia](https://en.wikipedia.org/wiki/Cataclysm:_Dark_Days_Ahead)
- [Dwarf Fortress Combat Wiki](https://dwarffortresswiki.org/index.php/Combat)
- [Zork - Wikipedia](https://en.wikipedia.org/wiki/Zork)
- [Zork Source Code Analysis](https://medium.com/swlh/zork-the-great-inner-workings-b68012952bdc)
- [Berlin Interpretation - RogueBasin](https://www.roguebasin.com/index.php/Berlin_Interpretation)
- [Personalities of Different Roguelikes - RogueBasin](https://www.roguebasin.com/index.php/Personalities_of_different_roguelikes)
- [7 Roguelikes Every Developer Should Study (Gamasutra)](https://www.gamedeveloper.com/design/7-roguelikes-that-every-developer-should-study)
- [Roguelike Development Resources (GitHub)](https://github.com/marukrap/RoguelikeDevResources)
- [Great Contemporary Roguelikes (Rogueliker)](https://rogueliker.com/great-roguelike-games/)

---

*This report was generated through extensive web research, source code analysis, and comparison against the Depths of Dread codebase at `/Users/will/Scripts/dungeon.py` (7,597 lines, Python curses, zero external dependencies).*
