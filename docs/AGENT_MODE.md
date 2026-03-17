# Depths of Dread — Agent Mode (`--agent`)

Claude-powered hybrid AI player. Uses BotPlayer for routine turns (instant) and Claude Haiku for tactical decisions (~1-6s per call).

## How It Works

### Hybrid Architecture
```
Each turn:
  1. Check trigger conditions (enemies? low HP? boss? shop? shrine? new floor?)
  2. If NO trigger → BotPlayer.decide(gs) [instant, zero latency]
  3. If trigger → serialize game state → call claude -p → parse action → execute
  4. Render frame + telemetry overlay
```

### Trigger Conditions (when Claude is consulted)
| Trigger | Condition | Why |
|---------|-----------|-----|
| Combat | Enemies in FOV | Weapon choice, positioning, flee-or-fight |
| Low HP | HP < 40% | Heal vs flee vs fight through |
| Full inventory | Inv full + item on ground | What to drop, what to keep |
| Shop | Adjacent to shopkeeper | Buy priorities given current state |
| Boss fight | Boss enemy visible | Spell/item strategy |
| New floor | Just descended | Assess starting position |
| Shrine | Standing on shrine | Pray or skip given current HP/state |

### State Serialization (~300 chars sent to Claude)
Ultra-compact text format. Example:
```
F5/15 HP28/40(70%) MP26/26 Hng44% G63 T627 Exp20%
Wpn:Rapier(atk6) Arm:Scale Mail(def6) Torch:0%off
Inv(7/20): food:1 potion:2 arrow:8
Enemies: Orc hp15 3E, Skeleton hp8 5NE
Items: Bread(2), Gold(4)
Near: stairs(8) SHOP_ADJ
```

### Claude Call Details
- Binary: `/Users/will/.local/bin/claude`
- Flags: `-p <state> --output-format json --model haiku --system-prompt <prompt> --max-turns 1`
- Critical: `CLAUDECODE` env var stripped to avoid nested-session error
- Cost: $0 (Claude Max subscription covers `claude -p` pipe mode)
- Timeout: 30s per call
- Typical latency: 1-6s depending on complexity

### Response Format
Claude returns: `{"action": "<action>", "reason": "<1 sentence>"}`

Supported actions: move_north/south/east/west/ne/nw/se/sw, attack, fire_<dir>, cast_heal, cast_fireball_<dir>, cast_freeze, cast_lightning_<dir>, cast_teleport, use_potion, eat_food, equip <item>, descend, rest, wait, pickup, pray, toggle_torch

### Fallback
If Claude returns invalid JSON, missing action key, or times out → BotPlayer handles that turn. Fallback count tracked in telemetry.

## Running It

```bash
# Visual mode — split-screen: game + decision log (132+ col terminal)
python3 ~/Scripts/dungeon.py --agent

# Batch mode — headless, prints per-game + summary stats
python3 ~/Scripts/dungeon.py --agent --games 5

# Speed control
python3 ~/Scripts/dungeon.py --agent --speed 0.5   # slower
python3 ~/Scripts/dungeon.py --agent --speed 2.0    # faster
```

### Visual Mode Controls
- `q` — quit
- `space` — pause/unpause
- `+`/`-` — speed up/slow down
- `t` — toggle telemetry overlay

### Telemetry Overlay
```
AGENT TELEMETRY (Claude-powered)
Strategy: COMBAT     Turn: 234
Reason: "engaging orc with ranged before melee"
Claude calls: 12     Avg: 3.2s  Falls: 1
HP: 28/45 (62%)      Hunger: 72%
Floor: 5  Kills: 23  Score: 1,450
[t]elemetry [+/-]speed [space]pause [q]uit
```

## Code Location

All in `/Users/will/Scripts/dungeon.py`:
- `AGENT_SYSTEM_PROMPT` — tactical system prompt for Haiku
- `AgentPlayer` class — hybrid decision-maker (~180 lines)
- `agent_game_loop()` — visual mode with THINKING overlay
- `agent_batch_mode()` — headless multi-game with Claude metrics
- `--agent` CLI flag in `_parse_args()`

Tests in `/Users/will/Scripts/tests/test_dungeon.py`:
- `TestAgentPlayer` class — 27 tests covering serialization, triggers, parsing, action mapping, fallback

## Performance Data

*(Updated after batch runs — see session-log.md for latest numbers)*

### Bot Baseline (decision tree, no Claude — March 2026)
- Avg floor: 13.1 (warrior), 10.2 (all classes), Max floor: 20
- F20 reach rate: ~2% (warrior), ~1.5% (all classes)
- 0% timeout rate across 3500+ games
- 4-layer priority AI: Survival → Combat → Exploration → Resources
- Phase-aware boss strategy, fear handling, smart levelup choices
- Speed: instant (no external calls)

### Agent Results (Feb 28, 2026 — first test game, pre-optimization)
- Floor reached: **10** (vs bot avg 8.8)
- Kills: 43, Score: 5,998, Turns: 1,750
- Death cause: starvation (food management still a weakness)
- Claude calls: 292, Avg latency: 12.8s, Fallbacks: 99 (34%)
- Runtime: ~62 min (vs bot's ~2 sec for same game)

### Optimizations Applied (Feb 28)
- **Prompt compression**: 1100 chars → 380 chars (~65% reduction)
- **State serialization**: 500 chars → 300 chars (~40% reduction)
- **stdin piping**: State passed via stdin instead of CLI arg (eliminates shell escaping errors)
- **Retry logic**: 2 attempts (15s + 10s timeout) before fallback
- **Fuzzy action matching**: Handles Claude variations (e.g. "heal" → "cast_heal", "north" → "move_north")
- **Expected impact**: Latency 12.8s → 3-5s, Fallbacks 34% → <10%

## Live Monitor

A dedicated curses dashboard for watching agent games in real-time.

```bash
# Terminal 1: Start agent game
python3 ~/Scripts/dungeon.py --agent --games 5

# Terminal 2: Watch live
python3 ~/Scripts/dread-monitor.py

# Or just get summary after games finish
python3 ~/Scripts/dread-monitor.py --summary
```

### Monitor Dashboard Shows:
- Game status (current game #, elapsed time, seed)
- Player state with HP/hunger bars (color-coded: green/yellow/red)
- Claude inference stats (total calls, avg latency, fallbacks, errors)
- Recent Claude decisions table (action, latency, reasoning)
- Completed game results (floor, kills, score, calls)

### How It Works:
- Agent writes JSONL events to `~/.depths_of_dread_agent.log`
- Events: `game_start`, `snapshot` (every 25 turns), `claude_call`, `claude_error`, `fallback`, `game_end`
- Monitor reads the log with tail-follow semantics, refreshes every 500ms
- Controls: `q` quit, `c` clear log

### Files:
- `/Users/will/Scripts/dread-monitor.py` — standalone monitor script
- `~/.depths_of_dread_agent.log` — JSONL event stream (cleared on each new agent session)

---

## Architecture Decisions

**Why hybrid instead of pure Claude?**
Calling Claude on every turn would be 5000+ API calls per game at ~3s each = 4+ hours per game. The hybrid approach calls Claude only when it matters (~50-200 calls per game), keeping total game time reasonable while getting smart tactical decisions.

**Why Haiku not Sonnet?**
Latency. Haiku responds in ~1-3s, Sonnet would be 3-8s. For a game running at 0.15s/turn for routine moves, even 3s feels slow. The tactical decisions here don't need Sonnet-level reasoning.

**Why `claude -p` not Anthropic API?**
Will's Claude Max subscription covers `claude -p` at $0. Using the API would require a separate API key and billing. The pipe mode works perfectly for single-turn Q&A.

**Why not just improve the decision tree?**
The decision tree is good at routine play but fundamentally can't reason about tradeoffs like "should I use my last heal potion now or save it for the boss 2 floors down?" Claude can actually think about multi-step strategy.
