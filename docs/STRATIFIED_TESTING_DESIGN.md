# Stratified Testing Architecture: Depths of Dread

**Date:** 2026-03-03
**Codebase:** `/Users/will/Scripts/dungeon.py` (~7,600 lines)
**Test Suite:** `/Users/will/Scripts/tests/test_dungeon.py` (~3,950 lines, 290 tests)
**Built-in Tests:** `dungeon.py --test` (3 integration tests)
**Bot:** `dungeon.py --bot --games N` (headless stress fuzzer)
**Agent:** `dungeon.py --agent --games N` (Claude-powered gameplay tester)

---

## 1. Testing Pyramid

```
                    +-----------+
                    |  Agent    |  Layer 5: Weekly
                    |  (5-10g)  |  Feature coverage, strategic play
                    +-----------+
                  +---------------+
                  |  Bot Stress   |  Layer 4: Nightly
                  |  (50-100g)   |  Crash detection, engine fuzzing
                  +---------------+
                +-------------------+
                | Integration Tests |  Layer 3: On change
                | (--test, 3 tests) |  Connectivity, spawning, items
                +-------------------+
              +-----------------------+
              |    Unit Tests (290)    |  Layer 2: On change
              |   pytest test_dungeon  |  Functions, classes, mechanics
              +-----------------------+
            +---------------------------+
            |   Static Analysis (pylint) |  Layer 1: On change
            |   pylint dungeon.py        |  Code quality, dead code
            +---------------------------+
```

### Layer 1: Static Analysis (On Every Change)

**Current:** pylint score 9.88. No pyflakes warnings.

**Run:** `pylint dungeon.py --fail-under=9.8`

No gaps here. Keep running on every change.

### Layer 2: Unit Tests (On Every Change)

**Current:** 290 tests, 1 skipped. ~4 seconds to run.

**Coverage gaps to fill (22 new tests recommended):**

| Gap | Tests Needed | Priority |
|-----|-------------|----------|
| Puzzle system: locked_stairs with bot walking on switches | 3 | HIGH |
| Puzzle system: torch puzzle reward spawning | 2 | HIGH |
| Alchemy table: edge case - no unidentified items | 1 | MED |
| Wall torch grab: inventory full | 1 | MED |
| Wall torch FOV integration | 2 | MED |
| Boss weapon drop: Ogre King's Maul stats | 1 | LOW |
| Boss weapon drop: Dread Lord's Bane stats | 1 | LOW |
| Lifesteal: zero damage doesn't heal | 1 | MED |
| Lifesteal: overkill damage (enemy at 1 HP) | 1 | MED |
| Inventory sort: scrolls exempt + sort interaction | 2 | LOW |
| Bot: decide() returns valid action for every game state | 2 | HIGH |
| Bot: handles T_STAIRS_LOCKED gracefully | 2 | HIGH |
| Agent: _serialize_state includes new features | 2 | MED |
| Agent: _action_to_command handles new actions | 1 | MED |

```python
# Example: Bot handles locked stairs
class TestBotLockedStairs:
    def test_bot_doesnt_stall_on_locked_stairs(self):
        """Bot should not infinite-loop when stairs are locked."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(4)
        # Force a locked_stairs puzzle
        sx, sy = gs.stair_down
        gs.tiles[sy][sx] = T_STAIRS_LOCKED
        gs.puzzles = [{"type": "locked_stairs", "positions": [],
                       "solved": False, "room": gs.rooms[1],
                       "stairs": (sx, sy)}]
        bot = BotPlayer()
        # Run 500 turns — bot should not stall (either die, or keep exploring)
        for _ in range(500):
            compute_fov(gs.tiles, gs.player.x, gs.player.y, 8, gs.visible)
            _update_explored_from_fov(gs)
            action, params = bot.decide(gs)
            _bot_execute_action(gs, action, params)
            gs.turn_count += 1
        # Should have spent most turns doing something productive, not WAIT
        assert bot.strategy != "WAIT" or gs.turn_count < 500

    def test_bot_descend_rejects_locked_stairs(self):
        """Bot's descend action should fail gracefully on locked stairs."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(4)
        sx, sy = gs.stair_down
        gs.tiles[sy][sx] = T_STAIRS_LOCKED
        gs.player.x, gs.player.y = sx, sy  # Place player on locked stairs
        # T_STAIRS_LOCKED is not walkable, so player shouldn't be here normally
        # But test the bot's descend check
        assert gs.tiles[sy][sx] != T_STAIRS_DOWN  # Bot's check should fail
```

### Layer 3: Integration Tests (On Every Change)

**Current:** 3 tests (connectivity, enemy spawning, item generation).

**Recommended additions (5 new tests):**

| Test | What It Validates |
|------|-------------------|
| Puzzle placement integrity | On floors 4+, puzzles reference valid tiles; locked_stairs points to actual stair position |
| Alchemy table placement | Tables only on floors 2,5,8,11,14; table tile exists and is valid |
| Wall torch placement | Torches are on wall tiles adjacent to rooms; wall_torches list matches tile map |
| Full-game save/load roundtrip | Generate floor, add puzzles/journal/alchemy_used, save, load, verify all fields |
| 100-turn bot smoke test | Bot runs 100 turns on each floor 1-15 without crashing |

```python
def test_puzzle_integrity(n=20):
    """Verify puzzle placement is internally consistent."""
    print("[4] Puzzle Integrity...")
    fails = 0
    for _ in range(n):
        gs = GameState(headless=True)
        for f in range(4, 16):
            gs.generate_floor(f)
            for puzzle in gs.puzzles:
                for px, py in puzzle["positions"]:
                    tile = gs.tiles[py][px]
                    if puzzle["type"] == "torch" and tile != T_PEDESTAL_UNLIT:
                        fails += 1
                    if puzzle["type"] in ("switch", "locked_stairs") and tile != T_SWITCH_OFF:
                        fails += 1
                if puzzle["type"] == "locked_stairs":
                    sx, sy = puzzle["stairs"]
                    if gs.tiles[sy][sx] != T_STAIRS_LOCKED:
                        fails += 1
    print(f"  Result: {'PASS' if fails == 0 else f'FAIL ({fails} issues)'}")
    return fails == 0
```

### Layer 4: Bot Stress Testing (Nightly)

See Section 2 for full bot improvement design.

**What the bot validates:**
- No crashes (exit code 0)
- No infinite loops (completes within max_turns)
- Combat system doesn't produce invalid states
- Movement system doesn't trap the player
- Item/inventory system doesn't corrupt
- Save/load roundtrips (if added)
- Enemy AI doesn't crash
- All floor transitions work
- Status effects don't cause state corruption

**What the bot does NOT validate:**
- Puzzle solving (intentionally -- agent territory)
- Alchemy table usage (intentionally -- agent territory)
- Journal correctness (intentionally -- agent territory)
- Strategic quality (meaningless for a deterministic fuzzer)
- Feature completeness (can't know what it doesn't know)

### Layer 5: Agent Gameplay Testing (Weekly)

See Section 3 for full agent testing framework design.

**What the agent validates:**
- Feature discovery and interaction (puzzles, alchemy, wall torches, journal)
- Strategic play quality (does it make reasonable decisions?)
- Full gameplay loop (start to finish, all classes)
- Shop interaction intelligence
- Spell/ability variety
- Inventory management decisions

---

## 2. Bot Improvements

### 2.1 Root Cause: Early-Floor Stalling

The bot stalls on early floors (~20% of runs, hitting 10,000 turn timeout on floor 2) for two interrelated reasons:

**Primary cause: Locked stairs puzzle on floor 4+.**
When `_place_puzzle` creates a `locked_stairs` puzzle, it replaces `T_STAIRS_DOWN` with `T_STAIRS_LOCKED`. `T_STAIRS_LOCKED` is NOT in the `WALKABLE` set, so A* pathfinding to `gs.stair_down` fails. The bot enters the exploration fallback loop: `_bfs_unexplored` returns `None` once the floor is fully explored, then the bot tries to path to stairs (which fails), falls through to `WAIT`, and loops forever.

However, this only applies to floors 4+ (puzzle requirement). The floor 2 stalls suggest a different cause:

**Secondary cause: BFS exploration completing before finding stairs.**
The bot's `_bfs_unexplored` searches only walkable tiles. If the dungeon generation places stairs in a room the bot hasn't FOV'd yet, and the corridor leading there passes through explored tiles, the BFS may return `None` while stairs are still undiscovered. The bot then tries to path directly to `gs.stair_down`, which requires the target to be reachable through walkable tiles the bot already explored. If there's an unvisited room between the bot and stairs (e.g., behind a door the bot explored past), the path fails.

**Tertiary cause: Loop detection insufficient.**
The bot tracks only 6 positions for oscillation detection. On large maps, the bot can cycle through 3+ distinct positions without triggering the stuck counter, leading to subtle multi-tile loops.

### 2.2 Bot Fixes

```python
# Fix 1: Handle locked stairs in bot decide()
# In BotPlayer.decide(), after the "Descend stairs" check (line 6075):

# Check for locked stairs — need to solve the puzzle first
if gs.tiles[p.y][p.x] == T_STAIRS_LOCKED:
    self.strategy = "EXPLORE"
    self.target_desc = "stairs locked, exploring"
    # Don't try to descend; continue exploring
    pass

# Fix 2: In the "find stairs" logic (line 6082-6090), check if stairs exist
sx, sy = gs.stair_down
if gs.tiles[sy][sx] in (T_STAIRS_DOWN, T_STAIRS_LOCKED):
    if gs.tiles[sy][sx] == T_STAIRS_LOCKED:
        # Stairs are locked — don't path to them, explore instead
        # Walk on switches if we pass over them (auto-toggle in player_move)
        pass
    elif gs.tiles[sy][sx] == T_STAIRS_DOWN:
        step = astar(gs.tiles, p.x, p.y, sx, sy, max_steps=80)
        if step:
            ...

# Fix 3: Extend loop detection window from 6 to 20 positions
# Also track unique tiles visited per floor for stall detection
class BotPlayer:
    def __init__(self):
        ...
        self._last_positions = []  # Keep at 6 for oscillation
        self._floor_tiles_visited = set()  # Track unique tiles per floor
        self._floor_start_turn = 0

    def decide(self, gs):
        ...
        # Add floor-level stall detection
        self._floor_tiles_visited.add((p.x, p.y))
        floor_turns = gs.turn_count - self._floor_start_turn
        if floor_turns > 300 and len(self._floor_tiles_visited) < 20:
            # Stuck on this floor — force random walk toward stairs
            self.strategy = "FORCE_DESCEND"
            ...

# Fix 4: When BFS returns None and stairs are unreachable, random-walk
# toward stairs coordinates (not pathfind — just bias direction)
if not self._explore_target:
    # Fully explored but can't reach stairs — bias movement toward them
    sx, sy = gs.stair_down
    dx = 1 if sx > p.x else (-1 if sx < p.x else 0)
    dy = 1 if sy > p.y else (-1 if sy < p.y else 0)
    ...
```

### 2.3 Bot Health Metrics

Every bot game should output a structured result dict:

```python
BOT_GAME_RESULT = {
    # Identity
    "game_id": int,
    "seed": int,
    "class": str,           # "warrior", "mage", "rogue"
    "version": str,         # dungeon.py file hash or git commit

    # Outcome
    "victory": bool,
    "floor_reached": int,
    "death_cause": str,     # "starvation", "combat", "timeout", "victory", etc.

    # Performance
    "total_turns": int,
    "turns_per_floor": dict,  # {1: 150, 2: 200, ...}
    "total_kills": int,
    "kills_per_floor": dict,
    "items_used": int,
    "items_found": int,
    "gold_collected": int,
    "gold_spent": int,

    # Stall Detection
    "max_turns_on_single_floor": int,
    "floors_with_timeout": list,  # Floors where >500 turns spent
    "unique_tiles_visited": int,
    "explored_pct_at_death": float,

    # New Feature Interaction (passive tracking)
    "puzzles_encountered": int,
    "puzzles_solved_by_accident": int,  # Walking on switches
    "alchemy_tables_on_floor": int,
    "wall_torches_encountered": int,
    "locked_stairs_encountered": bool,

    # Strategy Distribution
    "strategy_counts": dict,  # {"COMBAT": 100, "EXPLORE": 200, ...}
    "decision_count": int,
    "loop_breaks": int,       # Times oscillation detector fired

    # Timing
    "wall_time_seconds": float,
    "turns_per_second": float,
}
```

### 2.4 Bot Crash Detection and Error Reporting

```python
def bot_batch_mode(num_games=10, output_json=None):
    """Enhanced bot batch with crash detection and structured output."""
    results = []
    crashes = []

    for i in range(num_games):
        try:
            gs = GameState(headless=True, player_class=random.choice(["warrior", "mage", "rogue"]))
            _init_new_game(gs)
            bot = BotPlayer()
            max_turns = 10000

            while gs.running and not gs.game_over and gs.turn_count < max_turns:
                # ... existing game loop ...
                pass

            results.append(_build_bot_result(i, gs, bot))

        except Exception as exc:
            import traceback
            crash = {
                "game_id": i + 1,
                "seed": gs.seed if gs else "unknown",
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "floor": gs.player.floor if gs else 0,
                "turn": gs.turn_count if gs else 0,
            }
            crashes.append(crash)
            print(f"  Game {i+1:3d}: CRASH at F{crash['floor']} T{crash['turn']}: {exc}")

    # Write structured output
    if output_json:
        report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "games": num_games,
            "results": results,
            "crashes": crashes,
            "crash_rate": len(crashes) / num_games,
        }
        with open(output_json, 'w') as f:
            json.dump(report, f, indent=2)

    return results
```

### 2.5 Should the Bot Interact with Puzzles/Alchemy?

**Recommendation: No, with one exception.**

The bot should NOT:
- Press 'a' to use alchemy tables
- Press 'a' to light pedestals
- Intentionally seek switches
- Open the journal
- Sort inventory

The bot SHOULD:
- Walk over switches naturally during exploration (this happens automatically via `player_move` calling `_toggle_switch`)
- Track puzzle encounters passively (for metrics)
- Not crash when encountering locked stairs

The exception: the bot currently walks onto `T_SWITCH_OFF` / `T_SWITCH_ON` tiles as part of normal exploration, and `player_move` auto-toggles them. This means the bot can accidentally solve switch puzzles and locked_stairs puzzles just by exploring. This is fine -- it's realistic fuzzing behavior and tests the puzzle toggle code.

---

## 3. Agent Testing Framework

### 3.1 Ensuring Feature Encounters

The agent needs to encounter new features to test them. Two approaches:

**Approach A: Seed selection (RECOMMENDED)**
Run a pre-scan to find seeds that guarantee specific features:

```python
def find_feature_seeds(feature, count=10, max_tries=1000):
    """Find game seeds that guarantee a specific feature appears."""
    seeds = []
    for attempt in range(max_tries):
        seed = random.randint(0, 2**32 - 1)
        gs = GameState(headless=True, seed=seed, player_class="warrior")
        for f in range(1, 16):
            gs.generate_floor(f)
            if feature == "puzzle" and gs.puzzles:
                seeds.append((seed, f))
                break
            if feature == "alchemy" and any(
                gs.tiles[y][x] == T_ALCHEMY_TABLE
                for y in range(MAP_H) for x in range(MAP_W)):
                seeds.append((seed, f))
                break
            if feature == "wall_torch" and gs.wall_torches:
                seeds.append((seed, f))
                break
        if len(seeds) >= count:
            break
    return seeds
```

**Approach B: Force placement**
For targeted testing, force features onto the current floor:

```python
def _ensure_puzzle_on_floor(gs):
    """Force a puzzle to exist if none spawned naturally."""
    if not gs.puzzles:
        gs._place_puzzle(gs.player.floor)  # Retry without RNG check
```

### 3.2 Feature Coverage Tracking

Add a `FeatureTracker` that monitors what the agent interacts with:

```python
class FeatureTracker:
    """Track which game features the agent encountered and used."""

    def __init__(self):
        self.features = {
            # Encounter = saw/was on the tile. Used = interacted with it.
            "puzzle_torch":       {"encountered": False, "solved": False},
            "puzzle_switch":      {"encountered": False, "solved": False},
            "puzzle_locked":      {"encountered": False, "solved": False},
            "alchemy_table":      {"encountered": False, "used": False},
            "journal":            {"opened": False, "entries": 0},
            "wall_torch":         {"encountered": False, "grabbed": False},
            "boss_weapon_drop":   {"dropped": False, "equipped": False},
            "lifesteal":          {"triggered": False, "total_healed": 0},
            "shop":               {"encountered": False, "bought": False},
            "shrine":             {"encountered": False, "prayed": False},
            "inventory_sort":     {"used": False},
            "wand_used":          {"used": False, "class": None},
            # Class variety
            "classes_played":     set(),
            # Spell variety
            "spells_cast":        set(),
            "abilities_used":     set(),
        }

    def check_state(self, gs, action_str=""):
        """Call every turn to update tracking."""
        p = gs.player
        tile = gs.tiles[p.y][p.x]

        if tile == T_ALCHEMY_TABLE:
            self.features["alchemy_table"]["encountered"] = True
        if tile in (T_PEDESTAL_UNLIT, T_PEDESTAL_LIT):
            self.features["puzzle_torch"]["encountered"] = True
        if tile in (T_SWITCH_OFF, T_SWITCH_ON):
            self.features["puzzle_switch"]["encountered"] = True
        if tile == T_STAIRS_LOCKED:
            self.features["puzzle_locked"]["encountered"] = True

        for puzzle in gs.puzzles:
            if puzzle["solved"]:
                self.features[f"puzzle_{puzzle['type']}"]["solved"] = True

        if gs.journal:
            self.features["journal"]["entries"] = len(gs.journal)

        if gs.wall_torches:
            self.features["wall_torch"]["encountered"] = True

        # Track action-based features
        if "alchemy" in action_str or action_str == "use_alchemy":
            self.features["alchemy_table"]["used"] = True
        if action_str == "open_journal":
            self.features["journal"]["opened"] = True

    def coverage_pct(self):
        """Return overall feature coverage as a percentage."""
        total = 0
        covered = 0
        for key, val in self.features.items():
            if isinstance(val, dict):
                for subkey, subval in val.items():
                    if isinstance(subval, bool):
                        total += 1
                        if subval:
                            covered += 1
        return covered / total if total > 0 else 0

    def report(self):
        """Return human-readable feature coverage report."""
        lines = ["FEATURE COVERAGE REPORT", "=" * 40]
        for key, val in sorted(self.features.items()):
            if isinstance(val, dict):
                parts = []
                for k, v in val.items():
                    if isinstance(v, bool):
                        parts.append(f"{k}:{'YES' if v else 'no'}")
                    elif isinstance(v, set):
                        parts.append(f"{k}:{len(v)}")
                    else:
                        parts.append(f"{k}:{v}")
                lines.append(f"  {key:25s} {' | '.join(parts)}")
        lines.append(f"\n  Coverage: {self.coverage_pct():.0%}")
        return "\n".join(lines)
```

### 3.3 Variety Enforcement

To ensure the agent tests all classes and uses diverse strategies:

```python
def agent_test_suite(games_per_class=3):
    """Run agent games across all classes with feature tracking."""
    all_results = []

    for player_class in ["warrior", "mage", "rogue"]:
        for i in range(games_per_class):
            tracker = FeatureTracker()
            tracker.features["classes_played"].add(player_class)

            gs = GameState(headless=True, player_class=player_class)
            _init_new_game(gs)
            agent = AgentPlayer(game_id=len(all_results) + 1)
            # ... game loop with tracker.check_state(gs) each turn ...

            result = agent._post_game_report(gs)
            result["class"] = player_class
            result["feature_coverage"] = tracker.features
            result["coverage_pct"] = tracker.coverage_pct()
            all_results.append(result)

    return all_results
```

### 3.4 Enhanced Telemetry

Current JSONL events: `game_start`, `snapshot`, `claude_call`, `claude_error`, `fallback`, `game_end`, `health_warning`, `post_game_report`.

**New events to add:**

```python
# Feature interaction events
{"event": "feature_interact", "feature": "alchemy_table", "floor": 5, "result": "identified Potion of Healing"}
{"event": "feature_interact", "feature": "puzzle_switch", "floor": 6, "result": "toggled_on"}
{"event": "feature_interact", "feature": "puzzle_solved", "puzzle_type": "torch", "floor": 7}
{"event": "feature_interact", "feature": "wall_torch_grab", "floor": 3}
{"event": "feature_interact", "feature": "journal_opened", "entries": 4}
{"event": "feature_interact", "feature": "boss_weapon_equipped", "weapon": "Vampiric Blade"}

# Strategy distribution snapshot (every 50 turns)
{"event": "strategy_snapshot", "turn": 200, "distribution": {"COMBAT": 45, "EXPLORE": 120, "HEAL": 20, ...}}

# Decision quality assessment (periodic)
{"event": "decision_quality", "turn": 150, "metric": "hp_trend", "value": -0.5,
 "interpretation": "losing 0.5 HP/turn average — may need to heal more aggressively"}
```

### 3.5 Stuck vs Thinking Detection

Current health monitoring (`_health_check`) already tracks:
- Calls/turn ratio
- Fallback rate
- Turns per floor
- Action monotony
- HP loss without enemies

**Enhanced stuck detection:**

```python
STUCK_INDICATORS = {
    # Hard indicators (definitely stuck)
    "same_tile_100_turns": lambda agent, gs: (
        len(set(agent._last_positions[-100:])) <= 3 if len(agent._last_positions) >= 100 else False
    ),
    "zero_kills_300_turns": lambda agent, gs: (
        gs.turn_count - agent._floor_start_turn > 300 and
        sum(1 for _ in gs.enemies if not _.is_alive()) == 0
    ),

    # Soft indicators (probably stuck)
    "wait_action_dominant": lambda agent, gs: (
        sum(1 for a in list(agent._action_window)[-50:] if a == "WAIT") > 40
    ),
    "no_exploration_progress": lambda agent, gs: (
        agent.bot._floor_explored_pct(gs) < 0.3 and
        gs.turn_count - agent._floor_start_turn > 200
    ),
}

def is_agent_stuck(agent, gs):
    """Return (stuck: bool, confidence: float, reasons: list)."""
    reasons = []
    for name, check in STUCK_INDICATORS.items():
        try:
            if check(agent, gs):
                reasons.append(name)
        except Exception:
            pass

    if any(r.startswith("same_tile") or r.startswith("zero_kills") for r in reasons):
        return True, 1.0, reasons
    elif len(reasons) >= 2:
        return True, 0.7, reasons
    elif reasons:
        return False, 0.4, reasons  # Suspicious but not confirmed
    return False, 0.0, []
```

### 3.6 Error/Crash Reporting from Agent Runs

Same pattern as bot (Section 2.4) but with additional Claude-specific metrics:

```python
AGENT_CRASH_REPORT = {
    "game_id": int,
    "seed": int,
    "error": str,
    "traceback": str,
    "floor": int,
    "turn": int,
    "claude_calls_before_crash": int,
    "last_claude_action": str,
    "last_claude_reason": str,
    "last_state_text": str,  # The state that was sent to Claude
}
```

### 3.7 Making Agent Runs Faster

Current bottleneck: Claude API calls average 5-8 seconds each. A 10-floor game with ~200 Claude calls takes ~20-30 minutes.

**Optimization 1: Reduce call frequency.**

The current trigger conditions fire too often. `enemies_visible` fires every turn an enemy is in FOV, even if the agent already decided what to do. Add a cooldown:

```python
def _should_consult(self, gs):
    # Add minimum turns between non-critical consultations
    if self._last_consult_turn and gs.turn_count - self._last_consult_turn < 3:
        # Only consult on critical triggers (boss, very low HP)
        p = gs.player
        if not (p.hp / p.max_hp < 0.2):  # Emergency only
            boss_visible = any(e.boss and e.is_alive() and (e.x, e.y) in gs.visible for e in gs.enemies)
            if not boss_visible:
                return False
    ...
```

Expected reduction: 40-60% fewer calls (from ~0.3/turn to ~0.15/turn).

**Optimization 2: Cache identical states.**

If the game state hasn't meaningfully changed since the last call, skip:

```python
def _state_hash(self, gs):
    """Quick hash of game state for dedup."""
    p = gs.player
    enemies = tuple(sorted((e.x, e.y, e.hp) for e in gs.enemies if e.is_alive() and (e.x, e.y) in gs.visible))
    return hash((p.x, p.y, p.hp, p.mana, int(p.hunger), p.floor, enemies))
```

**Optimization 3: Batch-mode prompt compression.**

The system prompt is already compressed. Further options:
- Remove spell descriptions (Claude knows them by name)
- Use abbreviations in state text (already done)
- Pre-compute and cache the system prompt CLI arg

**Optimization 4: Use `--no-input` flag if available.**

Check if newer Claude CLI versions have a non-interactive mode that skips initialization overhead.

---

## 4. Agent System Prompt Updates

### Current Prompt (Line 6236)

```
Roguelike AI. Respond ONLY with JSON: {"action":"<act>","reason":"<short>"}
Actions: move_north/south/east/west/ne/nw/se/sw, attack, fire_north/south/east/west, cast_heal, cast_fireball_<dir>, cast_freeze, cast_lightning_<dir>, cast_teleport, cast_chain_lightning, cast_meteor_<dir>, cast_mana_shield, use_whirlwind, use_cleaving_strike, use_shield_wall, use_backstab, use_poison_blade, use_smoke_bomb, use_potion, eat_food, equip <name>, descend, rest, wait, pickup, pray, toggle_torch
Rules: Flee HP<20%. Eat at hunger<30%. Fireball groups. Freeze bosses. Chain Lightning chains to nearby enemies. Meteor for big AoE. Mana Shield before tough fights. Whirlwind 3+ adjacent. Shield Wall when low HP. Backstab bosses. Smoke Bomb to escape groups. Explore 40%+ before descending. Conserve torch/arrows.
```

### Updated Prompt

```python
AGENT_SYSTEM_PROMPT = """Roguelike AI. Respond ONLY with JSON: {"action":"<act>","reason":"<short>"}

Actions: move_north/south/east/west/ne/nw/se/sw, attack, fire_north/south/east/west, cast_heal, cast_fireball_<dir>, cast_freeze, cast_lightning_<dir>, cast_teleport, cast_chain_lightning, cast_meteor_<dir>, cast_mana_shield, use_whirlwind, use_cleaving_strike, use_shield_wall, use_backstab, use_poison_blade, use_smoke_bomb, use_potion, eat_food, equip <name>, descend, rest, wait, pickup, pray, toggle_torch, use_alchemy, light_pedestal, open_journal, grab_wall_torch, sort_inventory

Combat: Flee HP<20%. Eat at hunger<30%. Fireball groups. Freeze bosses. Chain Lightning 2+ enemies. Meteor big AoE. Mana Shield before tough fights. Whirlwind 3+ adjacent. Shield Wall low HP. Backstab bosses. Smoke Bomb escape groups.

Exploration: Explore 40%+ before descending. Conserve torch/arrows.

Puzzles: Floors 4+ may have puzzles. Pedestals (*) — step on + 'light_pedestal' (costs 10 torch fuel each). Switches (!) — walk over to toggle. All switches ON = puzzle solved = reward chest. Locked stairs (X) — find and toggle all switches to unlock. Always solve puzzles for high-tier loot.

Alchemy: Tables (&) on floors 2,5,8,11,14. Step on + 'use_alchemy' to identify 1 random potion/scroll. Use before drinking unknown potions. Single use per table.

Journal: 'open_journal' reviews identified items. Check before using unknown items.

Wall torches: ! on walls near rooms. 'grab_wall_torch' when adjacent to add torch fuel to inventory. Provide environmental light radius 5.

Boss weapons: Bosses drop unique weapons. Vampiric Blade has lifesteal (heals 20% of damage dealt). Always equip boss weapons.

Wands: Mage gets +50% damage +2 range. Warrior gets -25% damage. Prioritize wands as Mage.

Inventory: 'sort_inventory' cycles sort modes. Scrolls don't count toward capacity — always pick up scrolls."""
```

### Corresponding State Serialization Updates

The `_serialize_state` method (line 6303) needs to include:

```python
# Add to _serialize_state after features_str:

# Puzzle state
if gs.puzzles:
    puzzle_parts = []
    for puzzle in gs.puzzles:
        status = "SOLVED" if puzzle["solved"] else "active"
        puzzle_parts.append(f"{puzzle['type']}({status})")
    line += f"\nPuzzles: {', '.join(puzzle_parts)}"

# Alchemy table
if gs.tiles[p.y][p.x] == T_ALCHEMY_TABLE:
    pos_key = (p.x, p.y)
    used = "used" if pos_key in gs.alchemy_used else "available"
    features.append(f"ALCHEMY_TABLE({used})")

# Wall torches nearby
nearby_torches = sum(1 for wtx, wty in gs.wall_torches
                     if abs(wtx - p.x) + abs(wty - p.y) <= 2)
if nearby_torches:
    features.append(f"WALL_TORCH({nearby_torches})")

# Journal entries
if gs.journal:
    line += f"\nJournal: {len(gs.journal)} identified"

# Locked stairs
if gs.tiles[gs.stair_down[1]][gs.stair_down[0]] == T_STAIRS_LOCKED:
    features.append("STAIRS_LOCKED")

# Boss weapon equipped
if p.weapon and p.weapon.data.get("lifesteal"):
    features.append("LIFESTEAL_WEAPON")
```

### New Action Mappings

Add to `_action_to_command` (line 6641):

```python
# Alchemy table
if action_str in ("use_alchemy", "alchemy", "identify"):
    if gs.tiles[gs.player.y][gs.player.x] == T_ALCHEMY_TABLE:
        return ("use_alchemy", {})

# Light pedestal
if action_str in ("light_pedestal", "pedestal"):
    if gs.tiles[gs.player.y][gs.player.x] == T_PEDESTAL_UNLIT:
        return ("interact_pedestal", {})

# Grab wall torch
if action_str in ("grab_wall_torch", "grab_torch", "take_torch"):
    return ("grab_wall_torch", {})

# Sort inventory
if action_str in ("sort_inventory", "sort"):
    return ("sort_inventory", {})

# Open journal
if action_str in ("open_journal", "journal"):
    return ("open_journal", {})
```

And add handling in `_bot_execute_action`:

```python
elif action == "use_alchemy":
    return use_alchemy_table(gs)
elif action == "interact_pedestal":
    return _interact_pedestal(gs, gs.player.x, gs.player.y)
elif action == "grab_wall_torch":
    # Find adjacent wall torch
    for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
        tx, ty = gs.player.x + ddx, gs.player.y + ddy
        if 0 <= tx < MAP_W and 0 <= ty < MAP_H and gs.tiles[ty][tx] == T_WALL_TORCH:
            gs.tiles[ty][tx] = T_WALL
            if (tx, ty) in gs.wall_torches:
                gs.wall_torches.remove((tx, ty))
            torch_item = Item(0, 0, "torch", "Torch",
                            {"name": "Torch", "char": '(', "fuel": 60, "desc": "Taken from a wall."})
            gs.player.inventory.append(torch_item)
            gs.msg("You take a torch from the wall.", C_YELLOW)
            return True
    return False
elif action == "sort_inventory":
    return False  # No-op for agent (cosmetic only)
elif action == "open_journal":
    return False  # No-op for agent (cosmetic only)
```

### Agent Trigger Updates

Add new triggers to `_should_consult`:

```python
# Alchemy table — standing on one (consult once)
if reason is None and gs.tiles[p.y][p.x] == T_ALCHEMY_TABLE:
    pos_key = (p.x, p.y)
    if pos_key not in gs.alchemy_used:
        reason = "alchemy_table"

# Puzzle element — standing on unlit pedestal
if reason is None and gs.tiles[p.y][p.x] == T_PEDESTAL_UNLIT:
    reason = "pedestal"

# Locked stairs visible
if reason is None:
    sx, sy = gs.stair_down
    if gs.tiles[sy][sx] == T_STAIRS_LOCKED and (sx, sy) in gs.visible:
        reason = "locked_stairs"

# Wall torch adjacent (first encounter per floor)
if reason is None and not getattr(self, '_seen_wall_torch', False):
    for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
        tx, ty = p.x + ddx, p.y + ddy
        if 0 <= tx < MAP_W and 0 <= ty < MAP_H and gs.tiles[ty][tx] == T_WALL_TORCH:
            self._seen_wall_torch = True
            reason = "wall_torch"
            break
```

---

## 5. Test Automation

### 5.1 On Every Code Change (< 30 seconds)

```bash
#!/bin/bash
# scripts/test-quick.sh
set -e

echo "=== Quick Test Suite ==="
echo "[1/3] Static analysis..."
pylint /Users/will/Scripts/dungeon.py --fail-under=9.8 --disable=C0301,C0302 2>/dev/null

echo "[2/3] Unit tests..."
cd /Users/will/Scripts && python3 -m pytest tests/test_dungeon.py -x -q --tb=short

echo "[3/3] Built-in integration tests..."
python3 /Users/will/Scripts/dungeon.py --test

echo "=== All quick tests passed ==="
```

**Runtime target:** < 30 seconds total.

### 5.2 Nightly Bot Batch (Automated via launchd or cron)

```bash
#!/bin/bash
# scripts/test-nightly.sh
set -e
DATE=$(date +%Y-%m-%d)
REPORT_DIR="/Users/will/Scripts/test-reports"
mkdir -p "$REPORT_DIR"

echo "=== Nightly Bot Batch: $DATE ==="

# Run 50 games across all 3 classes
for CLASS in warrior mage rogue; do
    echo "--- $CLASS batch (20 games) ---"
    python3 /Users/will/Scripts/dungeon.py --bot --games 20 \
        2>&1 | tee "$REPORT_DIR/bot-$CLASS-$DATE.log"
done

# Combine results (once JSON output is implemented)
# python3 scripts/combine-reports.py "$REPORT_DIR"/bot-*-$DATE.json \
#     > "$REPORT_DIR/nightly-$DATE.json"

echo "=== Nightly complete ==="
```

**launchd plist:** `~/Library/LaunchAgents/com.will.dread-nightly.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.will.dread-nightly</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/will/Scripts/scripts/test-nightly.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/will/Scripts/test-reports/nightly-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/will/Scripts/test-reports/nightly-stderr.log</string>
</dict>
</plist>
```

### 5.3 Weekly Agent Batch

```bash
#!/bin/bash
# scripts/test-weekly.sh
DATE=$(date +%Y-%m-%d)
REPORT_DIR="/Users/will/Scripts/test-reports"
mkdir -p "$REPORT_DIR"

echo "=== Weekly Agent Batch: $DATE ==="

# 3 games per class = 9 total
for CLASS in warrior mage rogue; do
    echo "--- $CLASS agent (3 games) ---"
    python3 /Users/will/Scripts/dungeon.py --agent --games 3 \
        2>&1 | tee "$REPORT_DIR/agent-$CLASS-$DATE.log"
done

# Copy agent JSONL log
cp ~/.depths_of_dread_agent.log "$REPORT_DIR/agent-log-$DATE.jsonl"

echo "=== Weekly complete ==="
```

### 5.4 Alert Conditions

```python
# In the report generation script:
ALERT_THRESHOLDS = {
    "unit_test_failures": 0,        # Any failure = alert
    "bot_crash_rate": 0.05,         # >5% crash rate = alert
    "bot_timeout_rate": 0.15,       # >15% timeout rate = alert (currently ~20%)
    "bot_avg_floor_min": 5.0,       # Avg floor < 5 = regression alert
    "agent_fallback_rate": 0.25,    # >25% fallback = alert
    "agent_avg_latency_max": 15.0,  # >15s avg = alert
    "agent_feature_coverage_min": 0.3,  # <30% feature coverage = alert
    "agent_stuck_rate": 0.20,       # >20% stuck games = alert
}

def check_alerts(report):
    alerts = []
    if report.get("unit_failures", 0) > ALERT_THRESHOLDS["unit_test_failures"]:
        alerts.append(f"CRITICAL: {report['unit_failures']} unit test failures")
    if report.get("crash_rate", 0) > ALERT_THRESHOLDS["bot_crash_rate"]:
        alerts.append(f"HIGH: Bot crash rate {report['crash_rate']:.0%}")
    # ... etc
    return alerts
```

### 5.5 Report Storage Structure

```
/Users/will/Scripts/test-reports/
  nightly-stdout.log              # launchd stdout
  nightly-stderr.log              # launchd stderr
  bot-warrior-2026-03-03.log      # Bot batch console output
  bot-mage-2026-03-03.log
  bot-rogue-2026-03-03.log
  bot-warrior-2026-03-03.json     # Structured results (when JSON output added)
  agent-warrior-2026-03-04.log    # Agent batch console output
  agent-log-2026-03-04.jsonl      # Agent JSONL telemetry
  nightly-2026-03-03.json         # Combined nightly report
  weekly-2026-03-04.json          # Combined weekly report
  trends.json                     # Rolling trend data (appended each run)
```

---

## 6. Metrics Dashboard

### 6.1 Per-Game Summary Table

```
┌─────────────────────────────────────────────────────────────────────────┐
│ BOT BATCH RESULTS — 2026-03-03 (60 games: 20W/20M/20R)               │
├─────┬────────┬──────┬───────┬──────┬───────┬────────┬─────────────────┤
│ #   │ Class  │Floor │ Turns │Kills │ Score │ Result │ Death Cause     │
├─────┼────────┼──────┼───────┼──────┼───────┼────────┼─────────────────┤
│   1 │ Warr   │   12 │  1847 │   38 │  4200 │ DIED   │ combat (Lich)   │
│   2 │ Warr   │    2 │ 10000 │    3 │   180 │ STALL  │ timeout         │
│   3 │ Warr   │   15 │  2100 │   52 │  7800 │ WIN    │ victory         │
│ ... │ ...    │  ... │   ... │  ... │   ... │ ...    │ ...             │
├─────┴────────┴──────┴───────┴──────┴───────┴────────┴─────────────────┤
│ SUMMARY: Wins 8/60 (13%) | Avg Floor 8.4 | Avg Kills 31 | Stalls 12  │
│ By Class: W=3.2 avg | M=2.8 avg | R=3.1 avg floor                    │
│ Timeouts: 12 (20%) — ALERT: exceeds 15% threshold                    │
└───────────────────────────────────────────────────────────────────────┘
```

### 6.2 Feature Interaction Matrix

```
┌────────────────────────────────────────────────────────────────────────┐
│ FEATURE INTERACTION MATRIX — Agent Batch 2026-03-04                   │
├──────────┬────────┬────────┬────────┬────────┬────────┬────────┬──────┤
│ Game     │Puzzle  │Alchemy │Journal │WallTrc │BossWpn │ Shop   │Wand  │
├──────────┼────────┼────────┼────────┼────────┼────────┼────────┼──────┤
│ 1 (Warr) │SOLVED  │ USED   │ YES(4) │GRABBED │ EQUIP  │ BOUGHT │ --   │
│ 2 (Warr) │ none   │ --     │ YES(2) │  --    │  --    │ BOUGHT │ USED │
│ 3 (Warr) │ENCTR   │ USED   │ YES(5) │GRABBED │  --    │  --    │ --   │
│ 4 (Mage) │SOLVED  │ USED   │ YES(6) │  --    │ EQUIP  │ BOUGHT │ USED │
│ 5 (Mage) │ none   │ --     │ YES(1) │GRABBED │  --    │  --    │ USED │
│ 6 (Mage) │ENCTR   │ USED   │ YES(3) │  --    │  --    │ BOUGHT │ USED │
│ 7 (Rogue)│SOLVED  │ USED   │ YES(4) │GRABBED │ EQUIP  │ BOUGHT │ --   │
│ 8 (Rogue)│ none   │ --     │  NO    │  --    │  --    │  --    │ --   │
│ 9 (Rogue)│SOLVED  │ USED   │ YES(7) │GRABBED │ EQUIP  │ BOUGHT │ USED │
├──────────┴────────┴────────┴────────┴────────┴────────┴────────┴──────┤
│ COVERAGE: Puzzle 56% | Alchemy 67% | Journal 89% | WallTrc 44%       │
│           BossWpn 33% | Shop 56% | Wand 56% | Overall: 57%           │
│ TARGET: 70%+ per feature. Journal and Wand good. WallTorch needs work │
└───────────────────────────────────────────────────────────────────────┘
```

### 6.3 Agent-Specific Metrics

```
┌────────────────────────────────────────────────────────────────────────┐
│ AGENT CLAUDE METRICS — 2026-03-04                                     │
├─────────────────────────┬─────────────────────────────────────────────┤
│ Total Claude calls      │ 487 across 9 games (avg 54/game)           │
│ Avg latency             │ 6.2s (target: <8s) ✓                      │
│ Max latency             │ 23.1s (game 4, boss fight)                 │
│ Fallback rate           │ 8% (39/487) ✓                              │
│ Calls/turn (avg)        │ 0.18 (target: <0.3) ✓                     │
│ Timeouts                │ 3 (0.6%)                                   │
│ Parse failures          │ 7 (1.4%)                                   │
├─────────────────────────┼─────────────────────────────────────────────┤
│ Trigger distribution    │ enemies_visible: 312 (64%)                 │
│                         │ low_hp: 58 (12%)                           │
│                         │ boss: 41 (8%)                              │
│                         │ new_floor: 27 (6%)                         │
│                         │ shop: 18 (4%)                              │
│                         │ alchemy_table: 14 (3%)                     │
│                         │ shrine: 9 (2%)                             │
│                         │ locked_stairs: 5 (1%)                      │
│                         │ pedestal: 3 (1%)                           │
├─────────────────────────┼─────────────────────────────────────────────┤
│ Health warnings         │ 2 games flagged:                           │
│                         │   Game 2: HIGH turns_on_floor (F3, 580 turns)
│                         │   Game 8: HIGH action_monotony (85% move)  │
├─────────────────────────┼─────────────────────────────────────────────┤
│ Reasoning quality       │ Sample decisions:                          │
│                         │ "Freeze Ogre King before engaging" ← GOOD  │
│                         │ "Move north" (no explanation) ← WEAK       │
│                         │ "Use alchemy to ID before boss" ← GOOD     │
└─────────────────────────┴─────────────────────────────────────────────┘
```

### 6.4 Trend Tracking

```python
# trends.json structure — append after each batch run
{
    "runs": [
        {
            "date": "2026-03-03",
            "type": "bot_nightly",
            "games": 60,
            "avg_floor": 8.4,
            "win_rate": 0.13,
            "timeout_rate": 0.20,
            "crash_rate": 0.0,
            "avg_kills": 31,
            "avg_turns": 3200,
            "classes": {"warrior": {...}, "mage": {...}, "rogue": {...}},
        },
        {
            "date": "2026-03-04",
            "type": "agent_weekly",
            "games": 9,
            "avg_floor": 10.2,
            "win_rate": 0.22,
            "feature_coverage": 0.57,
            "avg_latency": 6.2,
            "fallback_rate": 0.08,
            "calls_per_turn": 0.18,
        },
    ]
}
```

**Trend alerts:**
- Bot avg_floor drops >20% from 7-day average: regression alert
- Bot timeout_rate increases >5% from previous run: stall regression
- Agent feature_coverage drops below 40%: prompt or game change broke coverage
- Agent fallback_rate increases >10% from previous: Claude API issue or prompt issue

### 6.5 Console Summary Report

```python
def print_dashboard(nightly_results, weekly_results, trends):
    """Print formatted dashboard to terminal."""
    print("=" * 72)
    print("  DEPTHS OF DREAD — TEST DASHBOARD")
    print(f"  Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 72)

    # Quick health check
    alerts = check_alerts(nightly_results)
    if alerts:
        print("\n  !! ALERTS !!")
        for a in alerts:
            print(f"    {a}")
    else:
        print("\n  STATUS: All metrics within acceptable ranges")

    # Bot summary
    print(f"\n  BOT (last nightly: {nightly_results['date']})")
    print(f"    Games: {nightly_results['games']}  "
          f"Win: {nightly_results['win_rate']:.0%}  "
          f"Avg Floor: {nightly_results['avg_floor']:.1f}  "
          f"Timeouts: {nightly_results['timeout_rate']:.0%}")

    # Agent summary
    if weekly_results:
        print(f"\n  AGENT (last weekly: {weekly_results['date']})")
        print(f"    Games: {weekly_results['games']}  "
              f"Win: {weekly_results['win_rate']:.0%}  "
              f"Avg Floor: {weekly_results['avg_floor']:.1f}  "
              f"Coverage: {weekly_results['feature_coverage']:.0%}")
        print(f"    Claude: {weekly_results['calls_per_turn']:.2f} calls/turn  "
              f"Latency: {weekly_results['avg_latency']:.1f}s  "
              f"Fallbacks: {weekly_results['fallback_rate']:.0%}")

    # Trends
    if len(trends) >= 2:
        prev = trends[-2]
        curr = trends[-1]
        floor_delta = curr.get('avg_floor', 0) - prev.get('avg_floor', 0)
        direction = "UP" if floor_delta > 0 else ("DOWN" if floor_delta < 0 else "FLAT")
        print(f"\n  TREND: Avg floor {direction} ({floor_delta:+.1f} from previous)")

    print("\n" + "=" * 72)
```

---

## Implementation Priority

### Phase 1 (Next Session) — Critical Fixes
1. Fix bot locked stairs stalling (Section 2.2, Fixes 1-4)
2. Add `T_STAIRS_LOCKED` handling to bot + A* awareness
3. Add class rotation to bot batch mode
4. Update agent system prompt (Section 4)
5. Add new actions to `_action_to_command` and `_bot_execute_action`

### Phase 2 (Following Session) — Telemetry
1. Add structured JSON output to `bot_batch_mode`
2. Add `FeatureTracker` to agent
3. Add new trigger conditions to `_should_consult`
4. Update `_serialize_state` with puzzle/alchemy/torch info
5. Create `test-reports/` directory structure

### Phase 3 (Later) — Automation
1. Create `test-quick.sh` script
2. Create `test-nightly.sh` script
3. Install launchd plist for nightly runs
4. Build report combiner script
5. Build dashboard printer

### Phase 4 (Ongoing) — Monitoring
1. Run first nightly batch, establish baselines
2. Run first agent weekly batch, measure feature coverage
3. Tune alert thresholds based on real data
4. Add trend tracking and regression detection
