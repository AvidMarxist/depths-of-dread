# Depths of Dread — Code Quality Audit

**Date:** 2026-03-08 (initial) | **Updated:** 2026-03-10 (v1.0)
**Codebase:** ~11,900 source lines | 6,328 test lines | 13 source modules | 474 tests across 10 test files

---

## Executive Summary

Depths of Dread is a well-structured Python roguelike with strong fundamentals: clean layered architecture, zero circular dependencies, comprehensive test coverage across all ISO 25010 dimensions, and a solid data-driven design.

**v1.0 (Mar 10):** Two refactoring passes addressed all Tier 1 and Tier 2 issues from the original audit. The codebase now has full type hint coverage, dispatch patterns replacing all oversized if/elif chains, a custom exception hierarchy, extracted modules (bot → bot/agent/agent_ui, GameState → floor_gen), per-module test files, 93 magic numbers extracted into BALANCE dict, and ruff + mypy running clean. Visual upgrade: 256-color themed palettes (19 floor themes) with unicode tile characters and automatic fallback. Bot improvements: puzzle-solving AI for locked stairs, structured JSON batch output. Polish pass: 30 floor-appropriate environmental vignettes with map rendering, multi-phase Dread Lord boss fight (taunts → shadow strikes → darkness arena), test-quick.sh unified test runner.

### Scorecard

| Category | Score (Mar 8) | Score (v1.0) | What Changed |
|----------|:-----:|:-----:|---------|
| Architecture & Structure | 7/10 | **9/10** | GameState split, bot.py split into 3 files, 13 clean modules |
| Code Quality | 5/10 | **8/10** | Dispatch dicts, 93 magic numbers extracted, ruff enforced |
| Design Patterns | 7/10 | **8/10** | Command dispatch, spell dispatch, layered bot decisions |
| Error Handling | 4/10 | **6/10** | Custom exception hierarchy, specific except clauses |
| Testing | 8/10 | **9/10** | Split into 10 per-module files + shared conftest.py + test-quick.sh |
| Performance | 7/10 | 7/10 | No change |
| Documentation | 3/10 | **7/10** | 100% type hints, README, audit docs, feature inventory |
| Security | 7/10 | 7/10 | No change |
| Maintainability | 5/10 | **8/10** | Explicit imports, dispatch patterns, modular tests, lint baseline |
| Python Modernism | 4/10 | **7/10** | Full type hints, ruff + mypy clean, modern import style |
| **Overall** | **5.7/10** | **7.6/10** | **All Tier 1+2 complete, polish pass, tagged v1.0** |

---

## 1. Architecture & Structure

### What's Good

- **Clean dependency graph** — no circular imports. Layers flow correctly:
  ```
  constants (leaf)
    → entities → mapgen
      → combat → items → ui → persistence
        → bot → game (orchestrators)
  ```
- **Domain-driven modules** — `combat.py`, `mapgen.py`, `items.py` — not `utils.py` or `helpers.py`
- **Data-driven design** — all balance tuning, enemy defs, spell defs, item templates centralized in `constants.py`

### What Needs Work

| Finding | Severity | Best Practice Violated |
|---------|----------|----------------------|
| **GameState is a God class** — 750+ lines, 35 attributes, 25+ methods handling floor gen, enemy/item population, shop/shrine/trap placement, puzzles, NPCs, enchant anvils, fountains, secret rooms | HIGH | Single Responsibility. Max class size ~400 lines |
| **`from .module import *` used in bot.py and game.py** — 8 wildcard imports creating flat namespace soup | HIGH | Never use `from module import *` (PEP 8, every style guide) |
| **6 lazy/deferred imports** inside function bodies (items.py imports game.render_game; persistence.py imports from game, ui, combat) | MEDIUM | Circular dependency workarounds indicate architectural boundary violations |
| **bot.py (2,398 lines) and items.py (1,658 lines)** exceed reasonable module size | MEDIUM | Target ~400 lines/module, ceiling ~600 |

### Recommendations

1. **Split GameState** into `GameState` (core state + accessors) + `FloorGenerator` (all `_populate_*`, `_place_*` methods). Estimated effort: medium. High payoff.
2. **Replace all `from .x import *`** with explicit imports. Run `ruff` to identify what's actually used. Estimated effort: low-medium.
3. **Split bot.py** into `bot.py` (BotPlayer), `agent.py` (AgentPlayer + agent_game_loop), `agent_ui.py` (render panel). Three files ~800 lines each.
4. **Resolve lazy imports** by extracting shared interfaces/types into a `types.py` or `protocols.py` module.

---

## 2. Code Quality

### Naming: PASS

Good `snake_case` throughout. Function names reveal intent (`_populate_enemies`, `fire_projectile`, `check_level_up`). Boolean properties read as assertions. No abbreviation abuse.

### Function Size: FAIL

Best practice: ≤40 lines per function, ceiling 60. Cyclomatic complexity ≤10.

| Function | Lines | Location | Issue |
|----------|------:|----------|-------|
| `game_loop` | ~450 | game.py:1021-1471 | Massive if/elif chain for every keybinding |
| `BotPlayer.decide` | ~347 | bot.py:80-427 | 7-level nesting, priority tree |
| `_cast_spell` | ~243 | items.py:667-910 | 30+ spell cases |
| `show_inventory` | ~224 | ui.py:672-896 | Full inventory UI |
| `render_sidebar` | ~178 | ui.py:166-344 | Sidebar rendering |
| `agent_game_loop` | ~170 | bot.py:1741-1911 | Agent game loop |
| `agent_batch_mode` | ~151 | bot.py:1911-2062 | Multi-game testing |
| `process_enemies` | ~148 | combat.py:549-697 | Enemy turn processing |
| `AgentPlayer._action_to_command` | ~138 | bot.py:1203-1341 | Command translation |
| `replay_session` | ~136 | persistence.py:626-762 | Session replay |

**10 functions exceed 100 lines. 6 exceed the 150-line emergency threshold.**

### Magic Numbers: FAIL

871 numeric literals found outside `constants.py`. Examples from the codebase:

```python
# combat.py — hardcoded thresholds
if hp_pct < 0.4:           # Why 0.4? Should be BALANCE["flee_threshold"]
dmg = max(1, dmg - enemy.defense // B["defense_divisor"])

# bot.py — inline decision thresholds
if p.floor <= 3:            # Why 3? Should be named constant
if hp_pct < 0.35:           # Why 0.35 vs the 0.4 in combat.py?

# game.py — spawn formulas
enemies_base=3, enemies_per_floor=1.5  # Already in BALANCE, good
random.randint(1, 3)        # Magic range — what does 1-3 represent?
```

### Recommendations

1. **game_loop → Command Pattern dispatch.** Replace the 450-line if/elif with a `COMMANDS = {"h": cmd_move_left, "i": cmd_inventory, ...}` dict. Each handler is a small function. This alone cuts game_loop to ~50 lines.
2. **_cast_spell → match/case or dispatch dict.** `SPELL_HANDLERS = {"fireball": cast_fireball, ...}`. Each spell handler is 5-15 lines.
3. **BotPlayer.decide → extract priority methods.** `_survival_priority()`, `_combat_priority()`, `_exploration_priority()` — each 50-80 lines.
4. **Extract magic numbers** to named constants in `BALANCE` dict or module-level constants.

---

## 3. Design Patterns

### Patterns Present (Good)

| Pattern | Where | Quality |
|---------|-------|---------|
| State Machine (implicit) | Enemy alertness, boss phases, player status | Works but not formalized |
| Strategy | Enemy AI types via `ENEMY_TYPES[etype]["ai"]` | Data-driven, clean |
| Factory | Item/enemy creation from templates | Functional style, appropriate |
| Data-Driven Design | All definitions in `constants.py` dicts | Strong — single source of truth |
| Priority Queue | BotPlayer decision tree | Works but deeply nested |

### Patterns Missing (Should Add)

| Pattern | Where It Would Help | Priority |
|---------|-------------------|----------|
| **Command** | Player/monster actions as objects. Enables: undo, replay serialization, AI action queues, input remapping. Currently actions are implicit tuples | HIGH |
| **Event System / Observer** | Decouple combat events → UI messages → achievement tracking → sound. Currently all procedural | HIGH |
| **Formal State Machine** | Game states (menu/playing/inventory/targeting), enemy AI. Currently implicit via flags and if/elif | MEDIUM |
| **match/case dispatch** | Replace 30+ spell if/elif, keybinding dispatch, AI type dispatch | MEDIUM |

### Recommendations

1. **Command Pattern for actions** — define `@dataclass` commands (`MoveCommand(dx, dy)`, `AttackCommand(target)`, `UseItemCommand(item)`) and dispatch them. This naturally separates input → intent → execution.
2. **Event bus** — lightweight pub/sub: `events.emit("enemy_killed", enemy=e)`. UI subscribes to render messages. Stats subscribe to track kills. Achievements subscribe to check conditions.

---

## 4. Error Handling

### What's Good

- Zero bare `except:` clauses
- Save/load catches `FileNotFoundError`, `json.JSONDecodeError`, `ValueError`
- Optional dependencies degrade gracefully (`agent_commons` import)

### What's Missing

| Finding | Severity | Best Practice |
|---------|----------|---------------|
| **No custom exception hierarchy** | MEDIUM | Should have `DepthsOfDreadError` base + `InvalidMoveError`, `CombatError`, `GenerationError` |
| **Silent failures** — `except SomeError: pass` in persistence.py:120 | MEDIUM | At minimum log the error. Silent swallowing hides bugs |
| **No structured logging** | MEDIUM | Game loop errors should be logged with context (floor, turn, action) |
| **No top-level error boundary** in game_loop | LOW | A crash during gameplay loses the session. Wrap in try/except with auto-save |

### Recommendations

1. **Add a custom exception hierarchy.** Small effort, big debugging payoff.
2. **Replace silent failures** with logging: `logger.warning(f"Save failed: {e}")`.
3. **Add crash recovery** — wrap game_loop in try/except that auto-saves on unexpected errors.

---

## 5. Testing — STRONGEST AREA

### What's Good

- **474 tests** across **105 test classes** — 0.58:1 test-to-source ratio
- **All 8 ISO 25010 dimensions** covered: functionality, performance, compatibility, usability, reliability, security, maintainability, portability
- **Performance benchmarks** with timing assertions (pathfinding, dungeon gen)
- **Save integrity** — checksum validation, JSON injection tests
- **Parametrized tests** for combinatorial coverage
- **Good fixtures** — `gs`, `gs_with_gear`, `gs_with_enemy`

### What Could Be Better

| Finding | Severity | Recommendation |
|---------|----------|----------------|
| **Single test file** (6,280 lines) | MEDIUM | Split into `test_combat.py`, `test_items.py`, `test_mapgen.py`, etc. Mirror source structure |
| **No property-based tests** | MEDIUM | Use Hypothesis for: dungeon connectivity invariants, damage bounds, save round-trips |
| **No mutation testing** | LOW | Run `mutmut` on combat.py and mapgen.py to find weak assertions |
| **Limited agent testing** | LOW | BotPlayer stress tests, AgentPlayer mock tests |
| **No branch coverage tracking** | MEDIUM | Add `--cov-branch` to pytest. Target ≥75% |

### Recommendations

1. **Split test_game.py** into per-module test files. Immediate readability win.
2. **Add Hypothesis tests** for 3 high-value invariants:
   - `generate_dungeon()` always produces connected map with path from start to exit
   - `serialize → deserialize` round-trip preserves all state
   - `player_attack()` damage is always ≥ 0

---

## 6. Performance

### What's Good

- `__slots__` on `Item` class (memory optimization for high-volume objects)
- `heapq` for A* pathfinding priority queue
- BSP dungeon generation (efficient spatial partitioning)
- Performance test assertions (pathfinding < threshold, dungeon gen < threshold)

### What Could Be Better

| Finding | Severity | Recommendation |
|---------|----------|----------------|
| Enemy and Player lack `__slots__` | LOW | Enemy has 33 attrs, Player has 45+ — `__slots__` would reduce memory |
| No `@lru_cache` on repeated calculations | LOW | FOV, pathfinding with same params could benefit |
| No profiling infrastructure | LOW | Add `cProfile` harness for "play 100 turns" benchmark |
| Linear entity lookups | LOW | `gs.enemies` is a list — if entity count grows, consider spatial hash |

---

## 7. Documentation — WEAKEST AREA

### Type Hints: 0% Coverage

**Zero return type annotations across 223 functions.** This is the single biggest gap in the codebase.

```python
# Current
def player_attack(gs, enemy):
    ...

# Should be
def player_attack(gs: GameState, enemy: Enemy) -> tuple[int, bool]:
    ...
```

Without type hints:
- No IDE autocomplete or error detection
- Refactoring is risky (no static analysis safety net)
- New contributors can't understand function contracts without reading implementations
- `mypy`/`pyright` can't run

### Docstrings: ~15-20% Coverage

Existing docstrings are good quality (explain purpose, not mechanics), but most functions have none.

### Recommendations

1. **Type hints are the #1 priority improvement.** Start with `entities.py` (the core types everything depends on), then `combat.py` and `mapgen.py`.
2. **Add `mypy` to CI** once type hints reach ~50% coverage.
3. **Docstrings** on all public functions — focus on contracts (params, returns, raises, side effects).

---

## 8. Security: ADEQUATE

- Save files use JSON (not pickle) — no arbitrary code execution risk
- Checksum validation on save files
- No `eval()` or `exec()` on data
- API keys handled via environment variables (agent mode)
- JSON injection tested

One concern: `subprocess` calls in bot.py and game.py should validate arguments to prevent injection if any user input flows into them.

---

## 9. Maintainability

### Risk Map

```
                    HIGH CHANGE FREQUENCY
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                  │
         │   items.py      │   game.py        │  ← DANGER ZONE
         │   combat.py     │   bot.py         │    (high change + high complexity)
         │                 │                  │
HIGH     ├─────────────────┼──────────────────┤
COMPLEXITY│                │                  │
         │   mapgen.py     │   constants.py   │  ← MONITOR
         │   persistence   │   entities.py    │    (complex but stable)
         │                 │                  │
         └─────────────────┼──────────────────┘
                           │
                    LOW CHANGE FREQUENCY
```

### Coupling Analysis

The wildcard imports in `game.py` and `bot.py` mean these files are coupled to **every symbol** in the codebase. Any rename, any new function, any removed constant — these files "see" it. This is the highest-risk coupling pattern possible in Python.

### Recommendations

1. **Explicit imports everywhere.** This is table-stakes for maintainability.
2. **Extract the game_loop keybinding dispatch** to a command dict. Currently the #1 "afraid to touch this" area.
3. **Track complexity trends** — run `radon cc -s -a` periodically. Current average CC is likely 8-12 (high).

---

## 10. Python Modernism

| Modern Practice | Status | Priority to Add |
|----------------|--------|----------------|
| Type hints (PEP 484) | Missing entirely | **MUST** |
| `@dataclass` for entities | Not used (manual `__init__`) | SHOULD |
| `match`/`case` (3.10+) | Not used | SHOULD — natural fit for spell/command dispatch |
| `pathlib.Path` | Mixed — some `os.path`, some `pathlib` | SHOULD |
| f-strings | Used consistently | PASS |
| `ruff` formatting | Not configured | SHOULD |
| `__slots__` on all entities | Only on Item | SHOULD |

---

## Priority Action Plan

### Tier 1 — High Impact ✅ COMPLETE (Mar 9-10)

| # | Action | Status |
|---|--------|--------|
| 1 | **Add type hints** to all 10 source files | ✅ Done — 100% function signature coverage |
| 2 | **Replace wildcard imports** with explicit imports in game.py | ✅ Done — constants.py excepted as shared data layer |
| 3 | **Command dispatch for game_loop** — `COMMAND_HANDLERS` dict | ✅ Done — 210-line if/elif → 6-line dispatch |
| 4 | **Split GameState** into GameState + floor_gen.py | ✅ Done — 676 lines extracted |

### Tier 2 — Medium Impact ✅ COMPLETE (Mar 10)

| # | Action | Status |
|---|--------|--------|
| 5 | **Spell dispatch dict** for `_cast_spell` | ✅ Done — `SPELL_HANDLERS` dict + 8 handlers |
| 6 | **Split test_game.py** into per-module test files | ✅ Done — 10 test files + conftest.py |
| 7 | **Extract BotPlayer priority methods** | ✅ Done — 4 layer methods + 4 combat sub-helpers |
| 8 | **Add custom exception hierarchy** | ✅ Done — exceptions.py with 7 exception types |
| 9 | **Split bot.py** into bot/agent/agent_ui | ✅ Done — 906 + 1,309 + 361 lines |

### Tier 3 — Polish (partially complete)

| # | Action | Status |
|---|--------|--------|
| 10 | Extract magic numbers to named constants | ✅ Done — 93 literals → BALANCE dict |
| 11 | Add Hypothesis property-based tests | ⬜ Open |
| 12 | Convert entities to `@dataclass(slots=True)` | ⬜ Open |
| 13 | Add `ruff` config | ✅ Done — clean baseline, lint.sh |
| 14 | Add `mypy` to CI | ✅ Done — clean baseline, 0 errors |
| 15 | Add docstrings to all public functions | ⬜ Open |

---

## Methodology

This audit was conducted by:
1. **Best practices research** — current (2025-2026) Python and game development guidance from 30+ sources including PEPs, Clean Code/Architecture, Bob Nystrom's Game Programming Patterns, Martin Fowler's refactoring catalog, and community best practices
2. **Deep codebase exploration** — every Python file read and analyzed for patterns, smells, and architectural concerns
3. **Quantitative metrics** — automated analysis of line counts, function sizes, magic numbers, type hint coverage, import structure, and test coverage mapping

Each finding was scored against industry best practices with priority ratings (MUST/SHOULD/NICE) to produce actionable, ranked recommendations.
