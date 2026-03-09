# Depths of Dread -- Balance & Tuning Analysis

**Date:** March 5, 2026
**Source:** `/Users/will/Scripts/dungeon.py` (~9,100+ lines)
**Trigger:** Agent run reached floor 15 with 7,700 gold -- suggesting broken economy

---

## Executive Summary: Top 10 Balance Issues (Ranked by Severity)

| # | Issue | Severity | Impact |
|---|-------|----------|--------|
| 1 | **Gold scales quadratically, sinks scale linearly** | CRITICAL | Gold piles = `(5-15) * floor`, enemy drops = `(3-10) * floor`, both multiplied by increasing enemy counts. Income grows ~O(floor^2) but shop prices barely scale. By floor 15, cumulative gold exceeds 10,000g with nowhere to spend it. |
| 2 | **Shops only on odd floors (8 total), inventory too small** | HIGH | 3-5 random items + 1 heal + 1 food per shop. Max spend per shop ~250-350g. Over 15 floors, max possible spending is ~2,000-2,800g against ~10,000-15,000g income. |
| 3 | **Enemy HP scaling is anemic (+10% per floor beyond min)** | HIGH | `enemy_hp_scale_per_floor: 0.1` means a goblin (12 HP base, min_floor 1) on floor 8 has 12 * 1.7 = 20 HP. Meanwhile player STR grows +3-4/level. Player damage outscales enemy HP by ~floor 5. |
| 4 | **No shop price scaling with floor depth** | HIGH | Random items: `(tier+1) * randint(20,50)`. A tier 2 weapon costs 60-150g on floor 1 AND floor 13. With 1,000+ gold by floor 7, everything is trivially affordable. |
| 5 | **Enemy damage doesn't scale at all** | HIGH | Enemy damage comes from ENEMY_TYPES and never scales. A goblin always hits for 2-5 regardless of floor. Only "new" enemies appear at deeper floors, but their damage ranges are fixed. |
| 6 | **XP curve too generous in early/mid game** | MEDIUM | Level 2 needs only 25 XP. A single goblin (15 XP) + rat (5 XP) + centipede (8 XP) = level 2. Floor 1 has 7+ enemies = easy level 3 by floor 2. |
| 7 | **Potions/scrolls are abundant AND powerful** | MEDIUM | 18% potion weight + 14% scroll weight = 32% of all drops are consumables. Heal potions restore 15-30 + 2*level HP. With ~15-20 items per floor, expect 5-6 consumables per floor. |
| 8 | **Warrior class is significantly stronger than Mage/Rogue** | MEDIUM | 40 HP + 7 STR + 3 DEF start vs Mage 20 HP + 3 STR + 0 DEF. Level-up: Warrior gets 5-10 HP + 2 STR + 1 DEF vs Mage 2-5 HP + 1 STR + 0 DEF. Warrior's survivability is 2-3x Mage by mid-game. |
| 9 | **Hunger is trivially manageable** | LOW | 22% food weight + 2-3 guaranteed food/floor + shop food. At 0.12 hunger/move, player can take ~833 steps before starving from full. Average floor takes ~100-200 moves. Food is never scarce. |
| 10 | **Traps are negligible threat** | LOW | Spike trap: 3-8 damage. By floor 5 player has 60-80 HP. Trap damage is <10% of HP pool and doesn't scale with depth. |

---

## 1. Gold Economy (THE CORE PROBLEM)

### Gold Income Per Floor

**Gold Piles** (line 1651-1655):
- Count: `randint(gold_piles_min=2, gold_piles_max=5)` per floor (avg 3.5)
- Amount per pile: `randint(gold_per_floor_min=5, gold_per_floor_max=15) * floor_num`
- Average per pile: 10 * floor_num
- **Average gold from piles per floor: 35 * floor_num**

**Enemy Gold Drops** (line 2013-2015):
- Drop chance: `enemy_gold_drop_chance = 0.50` (50%!)
- Amount: `randint(gold_drop_min=3, gold_drop_max=10) * floor_num`
- Average per drop: 6.5 * floor_num
- Enemy count: `enemies_base(5) + floor*enemies_per_floor(2) + randint(0,3)` = avg 6.5 + 2*floor
- **Average gold from enemies per floor: (6.5 + 2*floor) * 0.5 * 6.5 * floor**

**Cumulative Gold Income (expected):**

| Floor | From Piles | From Enemies | Floor Total | Cumulative |
|-------|-----------|-------------|-------------|------------|
| 1     | 35        | 28          | 63          | 63         |
| 3     | 105       | 122         | 227         | 428        |
| 5     | 175       | 268         | 443         | 1,199      |
| 7     | 245       | 466         | 711         | 2,482      |
| 10    | 350       | 861         | 1,211       | 5,589      |
| 13    | 455       | 1,373       | 1,828       | 10,431     |
| 15    | 525       | 1,779       | 2,304       | 14,795     |

The `* floor_num` multiplier on BOTH gold piles AND enemy drops creates a **quadratic growth curve**. Floor 15 generates 37x more gold than floor 1.

### Gold Sinks

**Shops** (line 1718-1752):
- Appear on odd floors only: `floor_num % 2 == 0: return` (floors 1,3,5,7,9,11,13,15 = 8 shops)
- Items per shop: `randint(3,5)` random + 1 heal potion + 1 food = 5-7 items
- Pricing (line 1735-1741):
  - Weapons/armor: `(tier+1) * randint(20,50)` -- tier 0-5, so 20-300g
  - Potions/scrolls: `randint(15,60)` -- tiny!
  - Food: `randint(10,25)`
  - Rings: `randint(50,120)`
  - Heal potion: `25 + floor*5` (floor 15 = 100g)
  - Food: 15g flat
- **Max spend per shop: ~300-600g** (buying everything)
- **Max total shop spending across 8 shops: ~2,400-4,800g**

**Sell values** (line 698-725):
- Weapons: `(tier+1) * 15` (max 90g for tier 5)
- Armor: `defense * 20` (max 200g for Dread Plate)
- Potions: 8g, Scrolls: 12g, Food: 3g
- These are so low they barely offset anything

### The Verdict

By floor 10, the player has **~5,500g** and has spent at most **~2,000g** across 5 shops. By floor 15, they have **~10,000-15,000g accumulated** with only 3 more shops to spend at. The 7,700g observation is completely consistent with these numbers.

**Root cause:** Gold generation scales with `floor_num` (linear multiplier on both pile amounts AND enemy drops), but gold sinks are essentially flat.

---

## 2. Difficulty Curve

### Enemy Scaling

**Enemy Count per Floor** (line 1595):
```python
num = B["enemies_base"](5) + floor_num * B["enemies_per_floor"](2) + randint(0, B["enemies_random_bonus"](3))
```
- Floor 1: 7-10 enemies
- Floor 5: 15-18 enemies
- Floor 10: 25-28 enemies
- Floor 15: 35-38 enemies

**Enemy HP Scaling** (line 1630):
```python
scale = 1.0 + (floor_num - ENEMY_TYPES[etype]["min_floor"]) * B["enemy_hp_scale_per_floor"](0.1)
```
- This is the ONLY scaling enemies get. No damage scaling, no defense scaling.
- A goblin (min_floor=1) on floor 8: 12 * 1.7 = 20 HP
- A goblin on floor 8 still hits for 2-5 and has 1 defense
- An orc (min_floor=4) on floor 10: 25 * 1.6 = 40 HP, still hits for 3-8

**Enemy Damage Ranges (fixed, never scale):**

| Enemy | HP | Damage | Defense | XP | Floors |
|-------|-----|--------|---------|-----|--------|
| Rat | 6 | 1-3 | 0 | 5 | 1-5 |
| Bat | 4 | 1-2 | 0 | 3 | 1-6 |
| Goblin | 12 | 2-5 | 1 | 15 | 1-8 |
| Skeleton | 18 | 3-6 | 2 | 25 | 3-10 |
| Orc | 25 | 3-8 | 3 | 35 | 4-11 |
| Wraith | 30 | 4-8 | 2 | 50 | 6-13 |
| Archer | 20 | 3-7 | 1 | 40 | 5-12 |
| Troll | 45 | 5-10 | 4 | 70 | 7-14 |
| Demon | 55 | 6-12 | 5 | 100 | 10-15 |
| Lich | 50 | 5-10 | 4 | 120 | 11-15 |
| Mind Flayer | 60 | 5-11 | 5 | 130 | 12-15 |

### Player Power Scaling

**Warrior Level-Up Gains** (per level, line 326):
- Base: 5-10 HP, 1-3 MP, 2 STR, 1 DEF
- + Level-up choice bonus (best: Cleave = +3 HP, +3 STR, +1 DEF)
- **Per level: ~10-13 HP, +3-5 STR, +1-2 DEF**

**Warrior Progression (estimated):**

| Level | Floor (approx) | HP | STR | DEF | Weapon Tier | Avg Damage |
|-------|----------------|-----|-----|-----|-------------|------------|
| 1 | 1 | 40 | 7 | 3 | 0 (1-4) | 3-6 |
| 3 | 2-3 | 62 | 14 | 5 | 1 (2-5) | 7-10 |
| 5 | 4-5 | 85 | 21 | 7 | 2 (3-8) | 12-16 |
| 7 | 6-7 | 108 | 28 | 9 | 2-3 (4-10) | 16-22 |
| 9 | 8-10 | 130 | 35 | 11 | 3-4 (5-12) | 22-28 |
| 11 | 11-13 | 152 | 42 | 13 | 4-5 (6-14) | 28-35 |

By level 7 (approx floor 6-7), the Warrior has 108 HP and deals 16-22 damage. The toughest non-boss enemy available (Troll, 45 HP) dies in 2-3 hits while dealing 5-10 damage per hit (reduced by ~5 defense). **The player outscales enemies by floor 5-6.**

### Boss Analysis

| Boss | HP | Damage | Floor | Player Level (est) | Player HP (est) |
|------|-----|--------|-------|--------------------|--------------------|
| Ogre King | 80 | 6-14 | 5 | 4-5 | 75-85 |
| Vampire Lord | 100 | 7-13 | 10 | 8-9 | 120-140 |
| Dread Lord | 200 | 10-20 | 15 | 11-13 | 150-175 |

- **Ogre King** feels about right -- similar HP to player, meaningful damage
- **Vampire Lord** is a pushover -- 100 HP vs player's 120-140 HP and 20+ damage per hit. Dies in 5-6 hits. Lifesteal helps but not enough.
- **Dread Lord** at 200 HP with regen 2 is the hardest fight but by floor 15, player has top-tier weapons (6-14 + 5 bonus + STR/3) and 150+ HP. 8-10 hit fight while Dread Lord's 10-20 damage is partially absorbed by 10+ defense.

---

## 3. Item Economy

### Drop Rate Analysis

**Items per floor** (line 1637-1638):
```python
num = items_base(4) + floor_num * items_per_floor(1) + randint(0, items_random_bonus(3))
```
- Floor 1: 5-8 items
- Floor 5: 9-12 items
- Floor 10: 14-17 items
- Floor 15: 19-22 items

Plus 2-3 guaranteed food + 2-5 gold piles = **9-16 total items on floor 1, 23-30 on floor 15**.

**Item Type Distribution (weights, line 69-81):**

| Type | Weight | % | Per Floor (floor 10) |
|------|--------|---|---------------------|
| Food | 22 | 20.9% | 2.9 + 2-3 guaranteed = ~5 |
| Potion | 18 | 17.1% | 2.4 |
| Weapon | 14 | 13.3% | 1.9 |
| Scroll | 14 | 13.3% | 1.9 |
| Armor | 11 | 10.5% | 1.5 |
| Ring | 8 | 7.6% | 1.1 |
| Bow | 4 | 3.8% | 0.5 |
| Arrow | 4 | 3.8% | 0.5 |
| Wand | 4 | 3.8% | 0.5 |
| Throwing Dagger | 3 | 2.9% | 0.4 |
| Torch | 3 | 2.9% | 0.4 |

Plus 30% chance of an item drop per enemy kill (line 2009).

**Potion/Scroll Abundance:**
- Floor 10 gets ~2.4 potions from floor spawns + ~2.5 from enemy drops (30% chance * 25 enemies * ~33% consumable) = ~5 consumables per floor
- Healing potions restore 15-30 + 2*level = 35-50 HP at level 9
- This is **way too generous** -- one heal potion undoes 3-5 enemy hits

**Weapon/Armor Progression** (line 1663-1672):
- Eligible weapons: `tier <= (floor_num//3)+1`
  - Floor 1-2: tier 0-1 (Rusty Dagger through Mace)
  - Floor 3-5: tier 0-2 (up to Rapier)
  - Floor 6-8: tier 0-3 (up to Katana)
  - Floor 9-11: tier 0-4 (up to Flamebrand)
  - Floor 12+: tier 0-5 (up to Vorpal Blade)
- This feels reasonable but combined with auto-equip (line 4005-4017), the player always has current-tier gear

**Ring Balance:**
- Resistance rings have `min_floor` gates (fire: 4, cold: 6, poison: 3) but the filter in `_random_item` doesn't check `min_floor`! (line 1685-1686 just does `random.choice(RING_TYPES)`)
- **BUG:** Fire/Cold/Poison resist rings can drop on any floor, bypassing their intended min_floor gates

---

## 4. XP & Leveling

### XP Curve

```python
xp_next = int(xp_base(25) * xp_growth(1.5) ** (level - 1))
```

| Level | XP Needed | Cumulative | Approx Enemies to Kill |
|-------|-----------|------------|----------------------|
| 2 | 25 | 25 | 2 goblins |
| 3 | 37 | 62 | +1 skeleton |
| 4 | 56 | 118 | +2 orcs |
| 5 | 84 | 202 | +2 archers |
| 6 | 126 | 328 | +3 wraiths |
| 7 | 189 | 517 | +3 wraiths |
| 8 | 284 | 801 | +4 trolls |
| 9 | 427 | 1,228 | +6 trolls |
| 10 | 640 | 1,868 | +6 demons |
| 11 | 961 | 2,829 | +7 demons |
| 12 | 1,441 | 4,270 | +11 liches |
| 13 | 2,162 | 6,432 | ... |

**XP Income per Floor:**

| Floor | Avg Enemies | Avg XP/Enemy | Total XP | Levels Gained |
|-------|-------------|-------------|----------|---------------|
| 1 | 8 | ~8 (rats/bats/goblins) | ~64 | 1-2 |
| 3 | 12 | ~20 (skeletons) | ~240 | ~1 |
| 5 | 16 | ~30 (orcs/archers) + boss 200 | ~680 | ~1 |
| 7 | 20 | ~45 (wraiths/trolls) | ~900 | ~1 |
| 10 | 26 | ~70 (demons/trolls) + boss 350 | ~2,170 | ~1-2 |
| 13 | 32 | ~100 (liches/mind flayers) | ~3,200 | ~1 |
| 15 | 36 | ~110 + boss 1000 | ~4,960 | ~1 |

**Expected level at milestones:**
- Floor 5: Level 5-6 (matches boss difficulty nicely)
- Floor 10: Level 9-10 (slightly overleveled for Vampire Lord)
- Floor 15: Level 12-14 (adequate for Dread Lord)

The XP curve is actually one of the **better-balanced** systems. The 1.5x growth factor keeps pace with increasing enemy XP values. The main issue is that the early game (floors 1-3) gives too many easy levels -- the player hits level 3-4 before facing any real threat.

### Level-Up Stat Gains

**The real problem is the stat gains are too generous:**
- Warrior base: +7.5 HP + 2 STR + 1 DEF per level
- Plus choice bonus: +5-12 HP, +0-3 STR, +0-2 DEF
- Net per level: **+12-20 HP, +2-5 STR, +1-3 DEF**
- Over 12 levels: +144-240 HP, +24-60 STR, +12-36 DEF

Enemy damage doesn't scale at all, so each level makes the player proportionally harder to kill.

---

## 5. Class Balance

### Starting Stats Comparison

| | Warrior | Mage | Rogue |
|---|---------|------|-------|
| HP | 40 | 20 | 25 |
| MP | 10 | 35 | 15 |
| STR | 7 | 3 | 5 |
| DEF | 3 | 0 | 1 |
| Crit Bonus | 0 | 0 | +10% |
| Evasion Bonus | 0 | 0 | +10% |

### Level-Up Comparison (per level)

| | Warrior | Mage | Rogue |
|---|---------|------|-------|
| HP | 5-10 | 2-5 | 3-6 |
| MP | 1-3 | 3-7 | 2-4 |
| STR | 2 | 1 | 1 |
| DEF | 1 | 0 | 1 |

### At Level 10 (base gains only, no choices)

| | Warrior | Mage | Rogue |
|---|---------|------|-------|
| HP | 40+67=107 | 20+31=51 | 25+40=65 |
| STR | 7+18=25 | 3+9=12 | 5+9=14 |
| DEF | 3+9=12 | 0+0=0 | 1+9=10 |

**Warrior has 2x Mage HP, 2x STR, and infinite more DEF at level 10.** Mage compensates with spells, but:
- Fireball: 12-25 + level damage, costs 12 mana. At level 10 with ~85 mana, that's ~7 fireballs.
- Warrior melee at level 10: ~20-30 damage per hit, unlimited uses, with lifesteal potential.
- **Mage's glass cannon design breaks down because enemy density is high and mana is finite per floor.** Mana regen is 1 per 5 turns -- painfully slow.

**Rogue** is middle ground but stealth backstab (2x damage on sleeping enemies, 60% spawn asleep) makes early floors trivially easy. Late game, enemies are all alert and Rogue's evasion cap (40%) helps but doesn't compensate for lower HP.

### Class Ability Analysis

**Warrior:**
- Battle Cry (C key): Freeze all nearby enemies 5 turns, 8 MP, 15-turn cooldown. Extremely strong panic button.
- Whirlwind: Hit all adjacent, 8 MP. Excellent for packs.
- Cleaving Strike: 2x damage ignoring defense, 10 MP. Boss killer.
- Shield Wall: -50% damage for 8 turns, 6 MP. Stacks with high DEF.

**Mage:**
- Arcane Blast (C key): 3x3 AoE 15-30 damage, 15 MP, 12-turn cooldown. Good but expensive.
- Chain Lightning: 10-20 base + chains, 14 MP. Underwhelming vs single targets.
- Meteor: 25-45 + 2*level, 5x5 AoE, 20 MP. Strong but very expensive.
- Mana Shield: Absorb damage from mana, 10 MP. Best defensive ability but drains mana fast.

**Rogue:**
- Shadow Step (C key): Teleport behind enemy + auto-crit, 10 MP, 10-turn cooldown. Best burst ability.
- Backstab: Guaranteed 2.5x crit, 6 MP. Insane damage.
- Poison Blade: Melee applies poison 10 turns, 8 MP. Good sustained.
- Smoke Bomb: Blind + freeze + evasion, 8 MP. Strong utility.

**Assessment:** Warrior is strongest because survivability > everything in a roguelike. Mage has the best AoE but dies to two bad hits. Rogue is best for skilled players who abuse stealth, but the bot/agent doesn't optimize stealth play.

---

## 6. Hunger / Survival

### Hunger Math

- Drain: `hunger_per_move = 0.12` per step
- Starting hunger: 100
- Steps to starve from full: 100 / 0.12 = **833 steps**
- Average floor exploration: ~100-200 steps
- **5-8 floors before starving from full**

### Food Supply

- 22% weight in random items = ~2-3 food from random drops per floor
- 2-3 guaranteed food per floor (line 1646)
- Shop food available for 15g
- Enemy item drops (30% chance) can be food
- **Total: ~4-6 food items per floor**

Food types: Stale Bread (15), Dried Meat (25), Elven Waybread (40), Mystery Meat (20). Average nutrition: ~25.

At 25 nutrition per food and 4-6 food per floor:
- Nutrition income per floor: 100-150
- Nutrition drain per floor (200 steps): 24
- **Player gains 4-6x more food than needed per floor**

**Hunger is a non-factor.** It exists as flavor text, not as a survival pressure.

---

## 7. Trap / Environmental Balance

### Trap Damage

| Trap | Damage | Effect | Min Floor |
|------|--------|--------|-----------|
| Spike | 3-8 | None | 1 |
| Dart | 2-6 | Poison | 3 |
| Pit | 4-10 | Stun | 2 |
| Teleport | 0 | Teleport | 5 |
| Alarm | 0 | Alert all | 1 |
| Gas | 1-3 | Confusion | 7 |

**Trap count per floor** (line 1875):
```python
count = min(6, trap_base_count(2) + int(floor_num * trap_per_floor(0.5)))
```
- Floor 1: 2 traps
- Floor 5: 4 traps
- Floor 8+: 6 traps (cap)

**Assessment:** Spike trap does 3-8 damage against a player with 40+ HP on floor 1, 100+ HP by floor 5. That's 2-8% of HP. **Traps are decoration, not threats.** They don't scale with floor depth at all.

The cap of 6 traps per floor means deeper floors aren't more dangerous trap-wise. Combined with Rogue's 30% passive detection and active search (`/` key), traps are easily avoided.

### Environmental Interactions

- **Water** (floor 7+): Extra hunger cost (50% chance), extinguishes fire. Rarely matters because hunger is trivial.
- **Lava** (floor 10+): Not walkable by player or enemies. Purely terrain obstacle.
- **Fire Aura** enemies: 1-3 damage when adjacent. Blocked by water tile or fire resist ring. Negligible.

---

## Recommendations

### Priority 1: Fix the Gold Economy

**Problem:** Gold income = O(floor^2), gold sinks = O(1)

**Option A: Reduce Gold Generation (Conservative)**
```python
# BEFORE
"gold_per_floor_min": 5,
"gold_per_floor_max": 15,
"gold_piles_min": 2,
"gold_piles_max": 5,
"enemy_gold_drop_chance": 0.50,
"gold_drop_min": 3,
"gold_drop_max": 10,

# AFTER
"gold_per_floor_min": 3,         # was 5
"gold_per_floor_max": 8,         # was 15 (reduced multiplier base)
"gold_piles_min": 1,             # was 2
"gold_piles_max": 3,             # was 5
"enemy_gold_drop_chance": 0.30,  # was 0.50
"gold_drop_min": 2,              # was 3
"gold_drop_max": 6,              # was 10
```
**Impact:** Cuts gold income by ~55-60%. Floor 15 cumulative drops from ~14,800g to ~5,900g.

**Option B: Remove Floor Multiplier from Gold (Aggressive)**

Change line 1654 and 2014:
```python
# BEFORE
amt = random.randint(B["gold_per_floor_min"], B["gold_per_floor_max"]) * floor_num

# AFTER
amt = random.randint(B["gold_per_floor_min"], B["gold_per_floor_max"]) + floor_num * 2
```
**Impact:** Changes gold from multiplicative to additive scaling. Floor 15 pile = 7-17g instead of 75-225g.

**Option C: Add Gold Sinks (Best Long-Term)**
- **Enchanting service at shops:** Pay gold to upgrade weapon/armor (+1 damage/defense per tier, increasing cost: 100, 250, 500, 1000g)
- **Potion brewing:** Buy specific potion effects at shops for 50-200g scaled by floor
- **Shrine donations:** Pay gold at shrines to guarantee positive outcomes (100g = no curse risk, 500g = choose blessing)
- **Life insurance:** Pay gold to reduce death penalty (if you add one) or resurrect once
- **Shop price scaling:** `base_price * (1 + floor_num * 0.15)` -- floor 15 items cost 3.25x floor 1

**RECOMMENDATION:** Do Option A + add shop price scaling (Option C partial). Quick to implement, big impact.

### Priority 2: Enemy Scaling

**Add damage and defense scaling per floor:**

```python
# In _populate_enemies, after HP scaling (line 1630-1632):
scale = 1.0 + (floor_num - ENEMY_TYPES[etype]["min_floor"]) * B["enemy_hp_scale_per_floor"]
e.max_hp = int(e.max_hp * scale)
e.hp = e.max_hp

# ADD THESE:
dmg_scale = 1.0 + (floor_num - ENEMY_TYPES[etype]["min_floor"]) * B["enemy_dmg_scale_per_floor"]
e.dmg = (int(e.dmg[0] * dmg_scale), int(e.dmg[1] * dmg_scale))
e.defense = int(e.defense + (floor_num - ENEMY_TYPES[etype]["min_floor"]) * B["enemy_def_scale_per_floor"])
```

New BALANCE keys:
```python
"enemy_hp_scale_per_floor": 0.15,   # was 0.10 -- +15% HP per floor beyond min
"enemy_dmg_scale_per_floor": 0.08,  # NEW -- +8% damage per floor beyond min
"enemy_def_scale_per_floor": 0.3,   # NEW -- +0.3 defense per floor beyond min
```

**Impact:** A goblin on floor 8 (7 floors above min):
- HP: 12 * 2.05 = 25 (was 19)
- Damage: (2-5) * 1.56 = (3-8) (was 2-5)
- Defense: 1 + 2.1 = 3 (was 1)

### Priority 3: Boss Difficulty

```python
# BEFORE
"vampire_lord": {"hp": 100, "dmg": (7,13), "defense": 5, ...}
"dread_lord":   {"hp": 200, "dmg": (10,20), "defense": 8, ...}

# AFTER
"vampire_lord": {"hp": 150, "dmg": (9,16), "defense": 7, ...}   # +50% HP, +25% damage, +2 DEF
"dread_lord":   {"hp": 350, "dmg": (14,28), "defense": 12, ...}  # +75% HP, +40% damage, +4 DEF
```

Also consider giving bosses:
- **Phase 2 enrage:** Below 30% HP, boss gets +50% damage and +0.3 speed
- **Minion spawning for Dread Lord:** Currently only every 5 turns via summoner AI. Make it every 3 turns.

### Priority 4: Reduce Consumable Abundance

```python
# BEFORE
"item_weights": {
    "potion": 18,
    "scroll": 14,
    "food": 22,
}

# AFTER
"item_weights": {
    "potion": 12,      # was 18
    "scroll": 10,      # was 14
    "food": 15,        # was 22 (still most common, but not overwhelming)
}
```

Also reduce guaranteed food:
```python
"guaranteed_food_min": 1,  # was 2
"guaranteed_food_max": 2,  # was 3
```

### Priority 5: Level-Up Stat Reduction

```python
# BEFORE (Warrior)
"level_hp": (5, 10), "level_str": 2, "level_def": 1,

# AFTER
"level_hp": (3, 7), "level_str": 1, "level_def": 1,
```

```python
# BEFORE (level-up choices)
{"name": "Vitality",  "desc": "+big HP",  "hp": 12, ...}
{"name": "Might",     "desc": "+HP +STR", "hp": 5, "str": 2, ...}

# AFTER
{"name": "Vitality",  "desc": "+big HP",  "hp": 8, ...}   # was 12
{"name": "Might",     "desc": "+HP +STR", "hp": 3, "str": 1, ...}  # was 5/2
```

### Priority 6: Fix Ring min_floor Bug

In `_random_item` (line 1685-1686), the ring generation ignores `min_floor`:
```python
# BEFORE
elif item_type == "ring":
    r = random.choice(RING_TYPES)
    return Item(x, y, "ring", r["name"], r)

# AFTER
elif item_type == "ring":
    eligible = [r for r in RING_TYPES if r.get("min_floor", 0) <= floor_num]
    if eligible:
        r = random.choice(eligible)
        return Item(x, y, "ring", r["name"], r)
```

### Priority 7: Trap Scaling

```python
# ADD to BALANCE:
"trap_damage_scale_per_floor": 0.15,  # +15% trap damage per floor

# In _trigger_trap (line 2031-2032):
# BEFORE
lo, hi = tdata["damage"]
dmg = random.randint(lo, hi) if hi > 0 else 0

# AFTER
lo, hi = tdata["damage"]
floor_scale = 1.0 + gs.player.floor * B["trap_damage_scale_per_floor"]
dmg = int(random.randint(lo, hi) * floor_scale) if hi > 0 else 0
```

Also remove the cap of 6 traps:
```python
# BEFORE
count = min(6, B["trap_base_count"] + int(floor_num * B["trap_per_floor"]))

# AFTER
count = B["trap_base_count"] + int(floor_num * B["trap_per_floor"])
```

---

## Difficulty Scaling Framework

### Metrics to Track (Runtime)

| Metric | How to Measure | Expected Range | Warning Threshold |
|--------|---------------|----------------|-------------------|
| Gold accumulation rate | `player.gold / floor` | 50-200g per floor | >400g/floor |
| HP percentage | `player.hp / player.max_hp` at floor start | 50-80% | >90% consistently |
| Death frequency (batch) | deaths per 10 games | 4-6 / 10 | <2 (too easy) or >8 (too hard) |
| Average floor reached | across batch games | 8-10 | >12 (too easy) or <5 (too hard) |
| Kills per floor | `player.kills / player.floor` | 8-15 | >25 (farming) |
| Consumables hoarded | potions + scrolls in inventory | 3-8 | >12 (abundance) |
| Shop purchase rate | items bought / items available | 40-70% | <20% (too expensive or too rich) |

### Dynamic Difficulty Adjustment

Add a `DIFFICULTY` dict alongside `BALANCE`:

```python
DIFFICULTY_PRESETS = {
    "easy": {
        "gold_mult": 1.2,
        "enemy_hp_mult": 0.8,
        "enemy_dmg_mult": 0.8,
        "item_drop_mult": 1.3,
        "xp_mult": 1.2,
        "food_mult": 1.5,
        "shop_price_mult": 0.8,
    },
    "normal": {
        "gold_mult": 1.0,
        "enemy_hp_mult": 1.0,
        "enemy_dmg_mult": 1.0,
        "item_drop_mult": 1.0,
        "xp_mult": 1.0,
        "food_mult": 1.0,
        "shop_price_mult": 1.0,
    },
    "hard": {
        "gold_mult": 0.6,
        "enemy_hp_mult": 1.3,
        "enemy_dmg_mult": 1.2,
        "item_drop_mult": 0.7,
        "xp_mult": 0.8,
        "food_mult": 0.6,
        "shop_price_mult": 1.5,
    },
}
```

**Adaptive Mode** (adjust every floor transition):
```python
def adjust_difficulty(gs):
    p = gs.player
    # Too easy indicators
    if p.hp > p.max_hp * 0.9 and p.gold > p.floor * 300:
        # Increase enemy stats by 10%, reduce drops by 10%
        gs.difficulty_mult["enemy_hp"] = min(1.5, gs.difficulty_mult["enemy_hp"] + 0.1)
        gs.difficulty_mult["item_drop"] = max(0.5, gs.difficulty_mult["item_drop"] - 0.1)
    # Too hard indicators
    elif p.hp < p.max_hp * 0.3:
        # Reduce enemy stats, increase healing
        gs.difficulty_mult["enemy_dmg"] = max(0.6, gs.difficulty_mult["enemy_dmg"] - 0.1)
        gs.difficulty_mult["item_drop"] = min(1.5, gs.difficulty_mult["item_drop"] + 0.1)
```

### Implementation Plan

1. Add `--difficulty easy|normal|hard` CLI flag
2. Apply multipliers in `_populate_enemies`, `_populate_items`, `_place_shop`
3. Add adaptive mode toggle: `--adaptive`
4. Log difficulty adjustments to agent log for analysis
5. Track all metrics in `SessionRecorder` for post-run analysis

---

## Quick Wins (1-2 Line Changes, Big Impact)

### 1. Cap enemy gold drop floor multiplier
**File:** `dungeon.py` line 2014
```python
# BEFORE
amt = random.randint(B["gold_drop_min"], B["gold_drop_max"]) * p.floor

# AFTER
amt = random.randint(B["gold_drop_min"], B["gold_drop_max"]) * min(p.floor, 5)
```
**Impact:** Caps gold drop scaling at floor 5. Floor 15 enemy drop is 15-50g instead of 45-150g. Single biggest gold nerf.

### 2. Cap gold pile floor multiplier
**File:** `dungeon.py` line 1654
```python
# BEFORE
amt = random.randint(B["gold_per_floor_min"], B["gold_per_floor_max"]) * floor_num

# AFTER
amt = random.randint(B["gold_per_floor_min"], B["gold_per_floor_max"]) * min(floor_num, 5)
```
**Impact:** Same as above for gold piles. Together, these two changes cut total gold by ~60%.

### 3. Increase enemy HP scaling
**File:** `dungeon.py` line 68 (BALANCE dict)
```python
"enemy_hp_scale_per_floor": 0.10,  # change to 0.18
```
**Impact:** Enemies get 80% more HP at the same floor offset. Troll on floor 14 goes from 45*1.7=77 to 45*2.26=102.

### 4. Reduce heal potion power
```python
"heal_potion_min": 10,  # was 15
"heal_potion_max": 20,  # was 30
```
**Impact:** Heal potions restore 30-40% less. Makes health management matter.

### 5. Reduce guaranteed food
```python
"guaranteed_food_min": 1,  # was 2
"guaranteed_food_max": 2,  # was 3
```
**Impact:** ~33% less free food. Still not scarce, but less trivial.

### 6. Increase mana regen
```python
MANA_REGEN_INTERVAL = 3  # was 5
```
**Impact:** Mage viability buff. 1 mana per 3 turns instead of 5. Helps close the Warrior-Mage gap.

### 7. Add shop price floor scaling (in `_place_shop`)
**File:** `dungeon.py` line 1735
```python
# BEFORE
price = (item.data.get("tier", 1)+1) * random.randint(20, 50)

# AFTER
price = int((item.data.get("tier", 1)+1) * random.randint(20, 50) * (1 + floor_num * 0.1))
```
**Impact:** Floor 10 shop prices are 2x floor 1. Floor 15 prices are 2.5x. Creates meaningful gold sink.

### 8. Vampire Lord HP buff
```python
"vampire_lord": {..., "hp": 150, "dmg": (9,16), ...}  # was hp:100, dmg:(7,13)
```
**Impact:** Floor 10 boss becomes a real fight instead of a speedbump.

### 9. Dread Lord HP buff
```python
"dread_lord": {..., "hp": 300, "dmg": (12,24), "regen": 3, ...}  # was hp:200, dmg:(10,20), regen:2
```
**Impact:** Final boss requires actual resource management to defeat.

### 10. Fix ring min_floor enforcement
Add floor check in `_random_item` ring section (line 1685):
```python
eligible = [r for r in RING_TYPES if r.get("min_floor", 0) <= floor_num]
r = random.choice(eligible) if eligible else random.choice(RING_TYPES[:5])
```
**Impact:** Resistance rings no longer trivialize elemental enemies early.

---

## Summary of Recommended BALANCE Dict Changes

```python
BALANCE = {
    # --- Gold (NERFED) ---
    "gold_per_floor_min": 3,       # was 5
    "gold_per_floor_max": 8,       # was 15
    "gold_piles_min": 1,           # was 2
    "gold_piles_max": 3,           # was 5
    "enemy_gold_drop_chance": 0.30, # was 0.50
    "gold_drop_min": 2,            # was 3
    "gold_drop_max": 6,            # was 10

    # --- Enemy Scaling (BUFFED) ---
    "enemy_hp_scale_per_floor": 0.18,   # was 0.10
    "enemy_dmg_scale_per_floor": 0.08,  # NEW
    "enemy_def_scale_per_floor": 0.3,   # NEW

    # --- Healing (NERFED) ---
    "heal_potion_min": 10,         # was 15
    "heal_potion_max": 20,         # was 30

    # --- Items (NERFED) ---
    "guaranteed_food_min": 1,      # was 2
    "guaranteed_food_max": 2,      # was 3

    # --- Item Weights (ADJUSTED) ---
    "item_weights": {
        "potion": 12,              # was 18
        "scroll": 10,              # was 14
        "food": 15,                # was 22
        # others unchanged
    },
}
```

Plus code changes:
- Cap floor multiplier in gold piles/drops to `min(floor, 5)`
- Add enemy damage/defense scaling in `_populate_enemies`
- Add shop price floor scaling in `_place_shop`
- Fix ring `min_floor` enforcement in `_random_item`
- Buff Vampire Lord and Dread Lord stats
- Faster mana regen for Mage viability

**Expected outcome of all changes:** A player reaching floor 15 should have ~2,000-3,000g (not 7,700g), have been forced to make shop purchase decisions, faced enemies that remain threatening through floor 10+, and needed to manage consumables carefully.
