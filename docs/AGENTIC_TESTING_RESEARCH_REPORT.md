# Universal Agentic Testing Feature Set
## Research Report & Recommendations

**Date:** 2026-03-04
**Author:** Claude (for Will Rompf)
**Scope:** Define a universal feature set for all agentic testing agents across game AI, web app testing, and hybrid LLM-powered agents.

---

## Table of Contents

1. [Research Findings](#1-research-findings)
2. [Our Current State & Pain Points](#2-our-current-state--pain-points)
3. [Universal Feature Set](#3-universal-feature-set)
   - [Health Monitoring](#31-health-monitoring)
   - [Observability](#32-observability)
   - [Human-in-the-Loop](#33-human-in-the-loop)
   - [Reliability](#34-reliability)
   - [Coverage & Exploration](#35-coverage--exploration)
   - [Diagnostics & Reporting](#36-diagnostics--reporting)
   - [Cost Control](#37-cost-control)
4. [Priority Matrix](#4-priority-matrix)
5. [Implementation Roadmap](#5-implementation-roadmap)
6. [Sources](#6-sources)

---

## 1. Research Findings

### 1.1 Academic & Industry Agent Evaluation

**AgentBench** (Tsinghua/MSRA, 2023-2025) established multi-environment evaluation as the standard. Eight diverse environments (OS, database, web shopping, card games, etc.) test planning, reasoning, tool use, and decision-making. The key insight: agents fail differently in different domains, so single-benchmark evaluation is insufficient.

**WebArena** (CMU, 2024) provides self-hosted realistic web environments (e-commerce, forums, code repos, CMS) with 812 templated tasks. Current best agents achieve only ~35% task success, demonstrating how far agents are from reliable autonomy.

**SWE-bench** (Princeton, 2024-2025) evaluates coding agents on real GitHub issues. The "Verified" variant uses human-validated tasks. Top agents solve ~50% of verified issues, with failure modes including wrong file identification, incomplete fixes, and test failures.

**TITAN** (2025, deployed in 8 commercial game QA pipelines) is the most directly relevant framework for us. Key architecture:
- **Perception Abstraction:** Converts high-dimensional game state to interpretable features (HP discretized to High/Medium/Low, nearby entities enumerated)
- **Action Optimization:** Constrains decisions to ~5 recommended actions via relevance rules, preventing the combinatorial explosion of raw action spaces
- **Reflective Self-Correction:** When progress stalls (20 consecutive actions without advancement), triggers LLM reflection with action history to diagnose and recover
- **Coverage-Guided Memory:** Persistent state-action transition graph across episodes, measuring unique abstract states visited
- **Bug Detection Oracles:** Four-layer detection (crash monitor, task status monitor, execution time monitor, logic anomaly detection)
- **Results:** 95% task completion, 74% coverage, 82% bug detection, deployed across PC and mobile MMORPGs

**Coverage-Aware Playtesting** (2025) combines code coverage signals with LLM-guided RL exploration, using coverage as an intrinsic reward to drive agents toward untested game states. Directly addresses our 32% feature coverage problem.

**LLMs as Difficulty Testers** (2024) demonstrates that even when LLM agents can't play optimally, they can reliably measure relative difficulty by comparing agent performance across game variations.

### 1.2 Open Source Agent Frameworks

**LangGraph/LangChain** introduced the most mature error handling patterns:
- **Four-layer fault tolerance:** Retry with backoff, model fallback chains, error classification and routing, checkpoint-based recovery
- **Error classification taxonomy:** Transient (retry), LLM-recoverable (loop back with error context), user-fixable (pause for human), unexpected (propagate for debugging)
- **Results from production:** Unrecoverable failures reduced from 23% to under 2% with 3 days of engineering work

**CrewAI** pioneered task guardrails: post-completion validation rules that check output against expectations (length, tone, quality, format, accuracy) and force the agent to retry if it drifts. This is output-level quality control that supplements input-level prompt engineering.

**AutoGPT** serves as a cautionary tale: without guardrails, agents "get stuck repeating the same failed action endlessly" and "make hundreds of API calls trying to solve simple problems." Sound familiar? Their failure modes are our failure modes.

### 1.3 Observability Ecosystem (2025-2026)

**OpenTelemetry-based tracing** has become the standard for LLM agent observability. Each step (prompt construction, model inference, tool execution, response parsing) is captured as a span, linked into traces. This enables:
- Temporal comparison of successful vs. failed executions
- A/B testing across model versions
- Root cause isolation via hierarchical span analysis

**Key tools:** LangSmith, AgentOps, Langfuse, Datadog LLM Observability, Arize Phoenix. All follow the same pattern: capture traces, aggregate metrics, detect anomalies, alert on deviations.

**Multi-level evaluation architecture** (from Maxim AI):
- **Session-level:** Completion rates, satisfaction, escalation frequency
- **Trace-level:** Latency, token costs, tool efficiency, output quality
- **Span-level:** Retrieval precision, response faithfulness, action correctness

### 1.4 Game AI Testing Specifically

Beyond TITAN, several patterns emerge:

**Automated playtesting** (aplib framework) uses goal-directed agents with DSLs for expressing test scenarios as hierarchical goal structures (main goals decomposed into subgoals). This maps well to our roguelike (goal: reach floor 15, subgoals: survive combat, manage hunger, solve puzzles).

**Coverage metrics for games** differ from web apps:
- **State coverage:** Unique game states visited (not code coverage)
- **Feature coverage:** Percentage of game mechanics interacted with
- **Behavioral coverage:** Diversity of action sequences used
- **Outcome coverage:** Different death causes, win conditions, etc.

**Stall detection threshold:** TITAN uses 20 consecutive non-advancing actions. Industry standard appears to be 15-30 actions depending on domain complexity.

### 1.5 Web App Agentic Testing

**Playwright Agents** (v1.56, October 2025) introduced three specialized AI agents:
- **Planner:** Explores app, designs test plans from natural language prompts
- **Generator:** Creates executable test code from plans
- **Healer:** Automatically fixes failing tests by adapting to UI changes

**Playwright MCP** bridges LLMs to browser automation, but at ~114K tokens per session vs ~27K for the CLI tool. Token efficiency matters for sustained testing.

**Key insight from industry:** MCP-based testing excels at exploratory testing and smoke tests described in natural language, but deterministic test scripts remain essential for release-critical regression testing. The two approaches are complementary, not competitive.

### 1.6 Human-in-the-Loop Patterns

The industry is evolving from "human-in-the-loop" (human must approve each decision) to "human-on-the-loop" (human monitors and intervenes only when needed). Key patterns:

- **Approval gates:** High-impact actions require explicit human confirmation
- **Exception-based intervention:** Only surface decisions that exceed confidence thresholds
- **Adaptive autonomy:** Tighten or loosen agent independence based on performance metrics
- **Coaching mode:** Human watches agent, provides feedback that improves future behavior

LangGraph's `interrupt()` primitive enables agents to pause execution, present state to a human, and resume with human-provided guidance. This is exactly what our "pilot mode" does manually.

---

## 2. Our Current State & Pain Points

### What We Have Today

| Project | Agent Type | LLM Calls | Key Metrics | Main Issues |
|---------|-----------|-----------|-------------|-------------|
| Depths of Dread | Turn-based hybrid (BotPlayer + Haiku) | ~200-300/game | Floor reached, kills, score, fallback rate | Stuck loops, 33-73% fallback, 32% feature coverage, conservative triggers |
| Hexen Agent | Real-time hybrid (bot tics + Haiku) | Untested | Kills, explore %, survival | Brain.py never actually run, no diagnostics |
| WDW Planner | Playwright tests (338 + 91) | 0 (deterministic) | Pass/fail, coverage | No agentic/exploratory testing, no LLM involvement |

### Failure Modes We've Hit (from failure-patterns.md)

1. **Flying Blind:** Agent made 1.9 Claude calls/turn instead of expected ~0.3 (6x deviation) for hundreds of turns before anyone noticed. Shop/shrine triggers fired every turn instead of once.
2. **Stuck Detection Missing:** Agents repeat same actions in loops with no escape mechanism. TITAN solved this with reflection after 20 stalled actions.
3. **Silent Fallback:** Claude timeouts silently fall back to dumb bot with no escalation, no logging, no warning. The agent degrades to a bot and nobody knows.
4. **Parse Failures:** 33-73% fallback rates due to JSON parse failures and timeouts. This is the single biggest reliability problem.
5. **Conservative Triggers:** Agent barely calls Claude because trigger conditions are too narrow. Missing alchemy tables, pedestals, locked stairs, wall torches.
6. **No Post-Run Intelligence:** Batch runs produce minimal diagnostics. Can't answer "what went wrong?" or "what improved?" after runs.
7. **No Feature Coverage Tracking:** 32% coverage is bad, but we only know this from manual analysis. No automated tracking of which game features the agent exercised.

---

## 3. Universal Feature Set

The following features are organized into 7 categories. Each feature is domain-agnostic (applicable to game agents AND web app agents) unless explicitly noted. Every feature includes:
- **What:** What it does
- **Why:** Why it matters (mapped to our pain points where applicable)
- **Effort:** S (< 1 day), M (1-3 days), L (3-7 days)
- **Priority:** P0 (must have before next batch run), P1 (next sprint), P2 (backlog)

---

### 3.1 Health Monitoring

#### H1. Progress Stall Detector
- **What:** Track a "progress metric" (floor number, score, explored %, task completion) and flag when N consecutive actions produce zero progress. Configurable stall threshold (default: 20 actions, per TITAN research).
- **Why:** Directly addresses our #1 pain point. Agents get stuck in loops and waste hundreds of turns/calls. TITAN's reflection trigger at 20 stalled actions is battle-tested across 8 commercial games.
- **Implementation:** Maintain a `last_progress_value` and `stall_counter`. On each action, if progress metric unchanged, increment counter. At threshold, trigger recovery (see R4 below).
- **Effort:** S
- **Priority:** P0

#### H2. Action Repetition Detector
- **What:** Track last N actions in a sliding window. Flag when the same action (or same 2-3 action sequence) repeats more than K times. Distinct from H1 because an agent can be "making progress" on the wrong thing.
- **Why:** Catches pathological loops like "move_north, move_south, move_north, move_south" that don't trigger stall detection (position changes each turn). AutoGPT's most common failure mode.
- **Implementation:** Ring buffer of last 20 actions. Check for repeated subsequences of length 1-3. Configurable repetition threshold (default: 5 consecutive repeats).
- **Effort:** S
- **Priority:** P0

#### H3. Resource Budget Monitor
- **What:** Track LLM calls, tokens consumed, wall-clock time, and in-game resources (HP, hunger, mana) against expected ranges. Flag when any metric exceeds 2x the baseline. Pre-set hard caps that terminate the run.
- **Why:** Directly addresses "flying blind" failure. We had 1.9 calls/turn vs expected 0.3 and didn't notice for hundreds of turns. The system should tell US when something is wrong.
- **Implementation:** Per-metric tracking with configurable baselines and thresholds. Baselines auto-calibrated from first N games if not manually set.
- **Effort:** M
- **Priority:** P0

#### H4. Heartbeat / Liveness Check
- **What:** Periodic liveness assertion (every N seconds or N turns) that confirms the agent loop is still running, the game state is updating, and the LLM subprocess hasn't hung.
- **Why:** Silent hangs (Claude process zombied, game loop deadlocked) are invisible without active liveness checks. Our monitor watches the log file, but if the agent stops writing to the log, the monitor just shows stale data.
- **Implementation:** Timestamp-based watchdog. If no heartbeat within timeout, kill and restart or alert.
- **Effort:** S
- **Priority:** P1

#### H5. State Validity Checker
- **What:** Assert invariants on game/app state after each action. Examples: HP never negative, inventory count matches item list length, player position is on a walkable tile, DOM structure matches expected layout.
- **Why:** Catches bugs in the game/app AND in the agent's state tracking. TITAN's "logic anomaly detection" oracle is this.
- **Effort:** M
- **Priority:** P1

---

### 3.2 Observability

#### O1. Structured Decision Trace
- **What:** For every agent decision, log a structured record: `{timestamp, turn, trigger_reason, state_snapshot, llm_prompt, llm_response, parsed_action, fallback_used, latency_ms, outcome}`. JSONL format, one line per decision.
- **Why:** Without this, we can't answer basic questions: "Why did the agent die?" "What was it doing for the last 50 turns?" "Was the LLM helping or hurting?" Our current agent.log has events but not full decision context.
- **Implementation:** Wrap every decision point in a `log_decision()` call. Already partially done in dread-monitor's JSONL events; needs to be universal and more complete.
- **Effort:** M
- **Priority:** P0

#### O2. State Snapshots at Key Moments
- **What:** Capture full game/app state at: start, floor/level transitions, before boss fights, on death, on stall detection, on fallback, and every N turns (configurable, default 25). Store as JSON alongside the decision trace.
- **Why:** Post-mortem analysis requires understanding state at failure points, not just at the end. TITAN maintains "action and state history" for its reflective reasoning. Our current snapshot is every 25 turns but missing key trigger points.
- **Effort:** S
- **Priority:** P0

#### O3. Decision Replay
- **What:** Given a trace file, replay the agent's decisions step-by-step in a UI (terminal or web). Show state, decision, outcome side-by-side. Allow stepping forward/backward.
- **Why:** "Decision replay" is the agent equivalent of a debugger. Without it, understanding agent behavior requires reading raw JSON logs. TITAN uses action trace memory for exactly this purpose. Our dread-monitor is close but only shows live data, not historical replay.
- **Effort:** L
- **Priority:** P2

#### O4. Metric Baselines & Anomaly Detection
- **What:** For every measurable metric (calls/turn, latency, fallback rate, actions/floor, kill rate, feature interactions/game), maintain rolling baselines from past N runs. Flag deviations exceeding configurable thresholds (default: 2 standard deviations).
- **Why:** This is our "flying blind" fix, formalized. The system should automatically flag "this run had 3x the normal fallback rate" or "agent spent 40% of turns on floor 3, normally it spends 8%."
- **Implementation:** Store run-level summary stats in a JSONL history file. On each new run, compare against rolling averages.
- **Effort:** M
- **Priority:** P1

#### O5. Action Distribution Histogram
- **What:** After each run, output a frequency distribution of all actions taken (move_north: 234, attack: 89, cast_heal: 12, etc.). Compare against expected distributions from baseline runs.
- **Why:** Immediately reveals pathological behavior. If 80% of actions are "wait" or "rest," the agent is stuck. If 0% of actions are "cast_spell," the agent is ignoring a class feature. Our 32% feature coverage problem would be obvious from this histogram.
- **Effort:** S
- **Priority:** P0

---

### 3.3 Human-in-the-Loop

#### L1. Pilot Mode (Interactive Takeover)
- **What:** At any point during an agent run, a human can press a key to pause the agent, take manual control, play some turns, then return control to the agent. Agent continues from the human-modified state.
- **Why:** Already implemented in Depths of Dread as of recent work. Needs to be universal. This is LangGraph's `interrupt()` primitive adapted for games. Critical for debugging ("let me see what happens if I go east instead"), coaching ("here's how to handle this boss"), and verifying agent is reading state correctly.
- **Effort:** S (Dread: done; Hexen: M; WDW: M)
- **Priority:** P0 (for any new agent)

#### L2. Intervention Triggers (Pause-on-Condition)
- **What:** Configurable conditions that automatically pause the agent and alert the human. Examples: "pause when HP < 10%", "pause when entering floor 10+", "pause when fallback rate exceeds 50% in last 20 turns", "pause on any bug detection."
- **Why:** Evolution beyond pilot mode. Instead of the human watching constantly, the system watches and only interrupts when something interesting or concerning happens. Matches the "human-on-the-loop" paradigm from current research.
- **Implementation:** List of predicate functions checked each turn. On match, pause agent, display state, wait for human input (continue/takeover/abort).
- **Effort:** M
- **Priority:** P1

#### L3. Coaching Mode
- **What:** Agent watches the human play and provides tactical advice in real-time (via Claude analysis of game state). Reverse of normal agent mode: human plays, Claude advises.
- **Why:** Already in our backlog. Serves two purposes: (1) entertainment value for the human, (2) training data for understanding what good play looks like. Can feed human decisions back into prompt engineering.
- **Effort:** M
- **Priority:** P2

#### L4. Approval Gates for High-Stakes Actions
- **What:** For web app testing, certain actions require human approval before execution: form submissions, data deletion, payment flows, configuration changes. Agent proposes the action, human approves or rejects.
- **Why:** Standard pattern in production agent systems. For WDW planner testing, we'd want approval gates before actions that modify shared trip data, invoke Firebase operations, or test destructive flows.
- **Implementation:** Wrap high-stakes actions in an `await_approval(action, context)` that blocks until human responds.
- **Effort:** M
- **Priority:** P1 (WDW-specific)

---

### 3.4 Reliability

#### R1. Structured Output with Validation
- **What:** Instead of parsing free-text LLM responses, use constrained output formats (JSON schema, enum-restricted fields). Validate response against schema before acting. On validation failure, send the error back to the LLM with "your response was invalid because X, try again" (LLM-recoverable error pattern from LangGraph).
- **Why:** Our #1 reliability problem. 33-73% fallback rates are primarily parse failures. If we validate and re-prompt instead of falling back, most of these become successful calls.
- **Implementation:** Define response schema per agent type. Use `--output-format json` (already doing this). Add JSON schema validation. On failure, retry with error context (max 2 retries, then fallback).
- **Effort:** M
- **Priority:** P0

#### R2. Tiered Retry with Backoff
- **What:** On LLM failure: (1) Retry same prompt with exponential backoff + jitter (2 attempts, 2s then 5s). (2) If still failing, retry with simplified prompt (fewer tokens, more constrained). (3) If still failing, fall back to bot with full logging.
- **Why:** Our current retry is 2 attempts (15s + 10s timeout). Research shows exponential backoff with jitter is optimal. The "simplified prompt" tier is new and addresses the case where the prompt itself is causing the failure.
- **Implementation:** Three-tier retry: same prompt (2x) -> simplified prompt (1x) -> fallback with logging.
- **Effort:** S
- **Priority:** P0

#### R3. Model Fallback Chain
- **What:** If primary model (Haiku) fails repeatedly, try a secondary model (Sonnet) before falling back to bot. Different models may succeed where others fail due to different failure modes.
- **Why:** LangChain's `RunnableWithFallbacks` pattern. Currently we go straight from Haiku to dumb bot. An intermediate step of "try a different model" could recover many failures.
- **Implementation:** `--agent-model` flag already in backlog. Extend to a chain: `[haiku, sonnet, bot]`.
- **Effort:** M
- **Priority:** P1

#### R4. Stall Recovery Actions
- **What:** When stall detector (H1) or repetition detector (H2) fires, instead of just logging, take recovery action: (1) Ask Claude "you've been stuck for N turns, here's your action history, what should you do differently?" (TITAN's reflective reasoning). (2) If reflection fails, force a random valid action. (3) If still stuck after 2 reflection attempts, force a strategic retreat (move toward stairs/exit).
- **Why:** TITAN's ablation study shows reflective self-correction is the single most impactful component (removing it causes 24% task completion drop). Our agents currently have no recovery mechanism beyond the bot fallback.
- **Implementation:** On stall: serialize last N actions + current state -> Claude reflection prompt -> parse recovery action. Cap at 2 reflection attempts per stall event.
- **Effort:** M
- **Priority:** P0

#### R5. Checkpoint & Resume
- **What:** Periodically save full agent state (game state + agent metadata + trace history) to disk. On crash or timeout, agent can resume from last checkpoint instead of restarting from scratch.
- **Why:** LangGraph's checkpoint-based recovery pattern. A 60-minute agent game that crashes at minute 55 currently loses everything. With checkpoints every 5 minutes, we lose at most 5 minutes of progress.
- **Implementation:** Serialize full state to JSON every N turns (default: 50). Resume flag: `--resume <checkpoint_file>`.
- **Effort:** M
- **Priority:** P1

#### R6. Graceful Degradation Levels
- **What:** Define explicit degradation levels with documented behavior at each level:
  - **Level 0 (Full Agent):** Claude handles all triggers normally
  - **Level 1 (Selective Agent):** Claude handles only high-value triggers (boss, shop, low HP); bot handles routine combat
  - **Level 2 (Emergency Agent):** Claude handles only life-threatening situations
  - **Level 3 (Pure Bot):** All Claude calls disabled, full bot mode
  - Auto-escalate based on fallback rate: if >50% fallbacks in last 20 calls, drop one level
- **Why:** Currently we have Level 0 and Level 3 with nothing in between. A graduated fallback keeps the agent useful even when Claude is struggling.
- **Effort:** M
- **Priority:** P1

---

### 3.5 Coverage & Exploration

#### C1. Feature Coverage Tracker
- **What:** Define a feature registry for each agent domain: list of all game mechanics/app features the agent COULD interact with. Track which ones the agent actually exercises each run. Report coverage percentage and identify untouched features.
- **Why:** Our 32% feature coverage in Dread is measured manually. We need automated tracking. TITAN's "state-action transition graph" is this, formalized.
- **Implementation:** For Dread: `FeatureTracker` class (already in backlog) with features like: `{used_potion, ate_food, equipped_weapon, cast_spell, used_shrine, solved_puzzle, used_alchemy_table, toggled_torch, opened_bestiary, descended_stairs, entered_branch, killed_boss, ...}`. For WDW: `{created_trip, added_dining, used_optimizer, exported_trip, used_gantt, ...}`. Boolean per feature per run.
- **Effort:** M
- **Priority:** P0

#### C2. Novelty-Seeking Bias
- **What:** When the agent has multiple valid actions, bias toward actions targeting unexplored features. Maintain a "feature heat map" from previous runs; prefer cold (unexercised) features over hot (well-exercised) ones.
- **Why:** Research on curiosity-driven exploration shows novelty rewards improve coverage 20-40% over random exploration. Our agent currently has no preference for novel actions, which is why it stays in its comfort zone (basic combat, basic movement) and ignores 68% of game features.
- **Implementation:** Load feature coverage from last N runs. When constructing Claude prompt, add: "Features you haven't tried yet: [list]. Prioritize exploring these." For bot fallback, add weighted random selection favoring unexplored actions.
- **Effort:** M
- **Priority:** P0

#### C3. Directed Exploration Goals
- **What:** Per-run objectives that direct the agent toward specific features or game regions. "This run, focus on: alchemy tables, branch exploration, boss fights." Communicated via system prompt modification.
- **Why:** TITAN's coverage-guided memory system achieves 74% coverage by directing agents toward unvisited states. Without direction, agents converge on the same "safe" strategy every run. Directed exploration ensures cumulative coverage grows across runs.
- **Implementation:** `--explore-focus "alchemy,branches,bosses"` flag that modifies Claude's system prompt. Bot mode gets corresponding adjustments to decision tree weights.
- **Effort:** M
- **Priority:** P1

#### C4. State Space Coverage Map
- **What:** Track unique abstract states visited across all runs. Visualize as a graph or heatmap showing which states are well-explored vs. unexplored. An "abstract state" is a tuple of key variables (floor, HP bucket, inventory profile, nearby entity types).
- **Why:** TITAN's core coverage mechanism. Enables cross-run learning: "in 10 runs, the agent never entered a Burning Pits branch with low HP while holding a fire resistance potion." This reveals blind spots that per-run metrics miss.
- **Implementation:** Define state abstraction function per domain. Hash abstract states. Store visited set in a persistent file. Visualize via terminal heatmap or HTML report.
- **Effort:** L
- **Priority:** P2

#### C5. Behavioral Diversity Score
- **What:** Measure how different each run's action sequence is from previous runs. Use edit distance, action distribution divergence (KL divergence), or unique action bigram count.
- **Why:** If every run looks the same, the agent isn't exploring. High diversity score = agent trying different strategies. Low diversity = converged on a fixed policy.
- **Implementation:** Compare action histograms across runs using Jensen-Shannon divergence. Report diversity score 0.0 (identical to average) to 1.0 (maximally different).
- **Effort:** M
- **Priority:** P2

---

### 3.6 Diagnostics & Reporting

#### D1. Post-Run Summary Report
- **What:** After each run, auto-generate a structured summary:
  ```
  === RUN SUMMARY ===
  Duration: 47m | Turns: 1,823 | Floor: 12 | Score: 8,450
  Claude: 156 calls, 3.2s avg, 8 fallbacks (5.1%)
  Features: 14/32 (44%) [+3 new: alchemy, branch, bestiary]
  Deaths: starvation (HP=28, hunger=0%)
  Anomalies: none
  Stalls: 2 (recovered via reflection)
  Action distribution: move(48%) attack(22%) cast(12%) item(8%) other(10%)
  vs baseline: +15% attack, -20% move, +5% cast
  Top Claude reasons: "engaging orc at range" (12), "healing before boss" (8)
  ```
- **Why:** Currently batch runs produce minimal output. This is the minimum viable post-mortem. Answers "what happened?" at a glance.
- **Effort:** M
- **Priority:** P0

#### D2. Failure Categorization
- **What:** Classify every failure (death, crash, stall, timeout) into a taxonomy:
  - **Agent failures:** Wrong action choice, missed opportunity, suboptimal strategy
  - **Reliability failures:** Parse error, timeout, model error, fallback
  - **Game/app bugs:** Invalid state, crash, unexpected behavior
  - **Coverage gaps:** Died because agent didn't know about feature X
- **Why:** Without categorization, "the agent died" gives no signal about what to fix. TITAN's four-layer oracle (crash, task status, execution time, logic anomaly) is this principle applied.
- **Implementation:** Post-run analysis function that reads trace, classifies each failure event, and aggregates.
- **Effort:** M
- **Priority:** P1

#### D3. Cross-Run Regression Detection
- **What:** Compare current run metrics against rolling baselines. Flag regressions: "average floor dropped from 10.2 to 7.8 (last 5 runs)," "fallback rate increased from 8% to 23%," "new feature coverage decreased."
- **Why:** Without regression detection, a code change that breaks agent performance goes unnoticed until someone manually compares numbers. Standard CI/CD practice applied to agent runs.
- **Implementation:** Store run summaries in JSONL history. Each run compares against rolling 10-run average. Flag metrics that regress more than 1 standard deviation.
- **Effort:** M
- **Priority:** P1

#### D4. Death/Failure Autopsy
- **What:** When the agent dies or fails, extract the last 20 turns of trace data, the state at death, and the last 5 Claude decisions. Format as a "failure autopsy" that a human can read in 30 seconds.
- **Why:** The difference between "agent died" and "agent died because it cast Fireball instead of healing when at 8% HP because Claude's response was 'aggressive attack against the skeleton' even though there was a potion in inventory." The autopsy makes the fix obvious.
- **Implementation:** On death/failure event, slice trace, format as readable block. Include in post-run summary and as standalone output.
- **Effort:** S
- **Priority:** P0

#### D5. Trend Dashboard
- **What:** Persistent HTML or terminal dashboard showing metrics across all historical runs: floor over time, coverage over time, fallback rate over time, feature coverage heatmap, death cause distribution.
- **Why:** Answers "are we getting better?" across days and weeks of runs. Currently we have no longitudinal view.
- **Implementation:** Read JSONL history, generate charts (matplotlib or simple HTML). Auto-update after each run.
- **Effort:** L
- **Priority:** P2

#### D6. A/B Comparison Reports
- **What:** Compare two agent configurations side-by-side: "bot vs agent," "haiku vs sonnet," "old triggers vs new triggers," "with novelty bias vs without." Statistical significance testing on key metrics.
- **Why:** Our backlog has "run agent vs bot A/B benchmark" for both Dread and Hexen. Needs structured comparison, not eyeballing. Research uses Mann-Whitney U tests for game agent comparisons.
- **Implementation:** `--compare <run_a_id> <run_b_id>` command that loads two sets of run histories and produces statistical comparison.
- **Effort:** M
- **Priority:** P1

---

### 3.7 Cost Control

#### CC1. Call Budget with Accounting
- **What:** Set a maximum number of Claude calls per game/session and per batch. Track budget consumption in real-time. When budget is 80% consumed, switch to more conservative trigger conditions (Level 1 degradation). At 100%, switch to pure bot.
- **Why:** Prevents runaway costs (or in our case, runaway time since we're on Max plan). A single game that makes 500 calls at 3s each = 25 minutes of Claude time. Budget caps prevent this.
- **Implementation:** `--call-budget 200` flag. Budget tracker decremented on each call. Degradation level shifts at configurable thresholds.
- **Effort:** S
- **Priority:** P0

#### CC2. Response Caching
- **What:** Cache Claude responses keyed on abstract state. When the agent encounters a state it's seen before (same enemies, same HP range, same inventory profile), return the cached response instead of calling Claude.
- **Why:** Many game situations are structurally identical ("Orc at range 3, HP at 70%, have potion" occurs many times per game). Caching cuts calls 30-50% based on our state abstraction granularity. Anthropic's own prompt caching charges 1/10th for cached reads.
- **Implementation:** Hash the state serialization string. LRU cache with configurable size (default: 200 entries). TTL optional (game state evolves, so identical states may need different responses in different contexts).
- **Effort:** M
- **Priority:** P1

#### CC3. Trigger Deduplication
- **What:** Prevent the same trigger from firing on consecutive turns. If "shop adjacent" fired on turn 100, suppress it until the agent moves away and returns. Track trigger cooldowns per trigger type.
- **Why:** This was our actual bug: shop/shrine triggers fired EVERY turn the agent stood next to them, causing 6x expected Claude calls. A 1-turn cooldown would have prevented this entirely.
- **Implementation:** Per-trigger-type cooldown counter. After trigger fires, suppress for N turns (configurable per trigger type, default: 5).
- **Effort:** S
- **Priority:** P0

#### CC4. Prompt Compression
- **What:** Minimize token count in state serialization without losing decision-relevant information. Use abbreviations, remove redundant context, only include delta from last state. Target: <300 tokens for state, <200 tokens for system prompt.
- **Why:** Already applied once (1100 -> 380 chars). Ongoing discipline. Every saved token across 200 calls per game adds up. Research shows 65-85% prompt compression is achievable without quality loss.
- **Implementation:** Review and compress prompts quarterly. Benchmark decision quality before/after compression.
- **Effort:** S (ongoing)
- **Priority:** P1

#### CC5. Smart Trigger Gating
- **What:** Before calling Claude, estimate whether the situation actually needs LLM reasoning or if the bot can handle it. Example: "enemy visible" triggers Claude, but if it's a single weak enemy and agent has full HP, the bot's "attack nearest" is optimal and Claude adds no value.
- **Why:** Our triggers are boolean (enemy visible = call Claude). Smart gating adds "is this a situation where Claude would decide differently than the bot?" If not, skip the call. Could reduce calls by 40-60% based on how many combat situations are trivially winnable.
- **Implementation:** Pre-filter on each trigger: check if situation is "trivial" (defined per trigger type). For combat: trivial if enemies_total_hp < player_hp * 0.5 and no special enemy types.
- **Effort:** M
- **Priority:** P1

---

## 4. Priority Matrix

### P0 (Must Have Before Next Batch Run) — ~7 days total

| ID | Feature | Effort | Category |
|----|---------|--------|----------|
| H1 | Progress Stall Detector | S | Health |
| H2 | Action Repetition Detector | S | Health |
| H3 | Resource Budget Monitor | M | Health |
| O1 | Structured Decision Trace | M | Observability |
| O2 | State Snapshots at Key Moments | S | Observability |
| O5 | Action Distribution Histogram | S | Observability |
| R1 | Structured Output with Validation | M | Reliability |
| R2 | Tiered Retry with Backoff | S | Reliability |
| R4 | Stall Recovery Actions | M | Reliability |
| C1 | Feature Coverage Tracker | M | Coverage |
| C2 | Novelty-Seeking Bias | M | Coverage |
| D1 | Post-Run Summary Report | M | Diagnostics |
| D4 | Death/Failure Autopsy | S | Diagnostics |
| CC1 | Call Budget with Accounting | S | Cost |
| CC3 | Trigger Deduplication | S | Cost |

### P1 (Next Sprint) — ~10 days total

| ID | Feature | Effort | Category |
|----|---------|--------|----------|
| H4 | Heartbeat / Liveness Check | S | Health |
| H5 | State Validity Checker | M | Health |
| O4 | Metric Baselines & Anomaly Detection | M | Observability |
| L2 | Intervention Triggers (Pause-on-Condition) | M | Human |
| L4 | Approval Gates (WDW-specific) | M | Human |
| R3 | Model Fallback Chain | M | Reliability |
| R5 | Checkpoint & Resume | M | Reliability |
| R6 | Graceful Degradation Levels | M | Reliability |
| C3 | Directed Exploration Goals | M | Coverage |
| D2 | Failure Categorization | M | Diagnostics |
| D3 | Cross-Run Regression Detection | M | Diagnostics |
| D6 | A/B Comparison Reports | M | Diagnostics |
| CC2 | Response Caching | M | Cost |
| CC4 | Prompt Compression | S | Cost |
| CC5 | Smart Trigger Gating | M | Cost |

### P2 (Backlog) — ~10 days total

| ID | Feature | Effort | Category |
|----|---------|--------|----------|
| O3 | Decision Replay | L | Observability |
| L3 | Coaching Mode | M | Human |
| C4 | State Space Coverage Map | L | Coverage |
| C5 | Behavioral Diversity Score | M | Coverage |
| D5 | Trend Dashboard | L | Diagnostics |

---

## 5. Implementation Roadmap

### Phase 1: Foundation (P0 features, ~7 days)

**Goal:** Every agent run produces useful diagnostics and can self-recover from common failures.

**Build order (dependency-aware):**

1. **Day 1-2: Core infrastructure**
   - O1 (Structured Decision Trace) — everything else depends on this
   - O2 (State Snapshots) — feeds into diagnostics
   - CC3 (Trigger Deduplication) — immediate win, prevents 6x call inflation

2. **Day 3-4: Health & Reliability**
   - H1 (Stall Detector) + H2 (Repetition Detector) — build together
   - R2 (Tiered Retry) — simple, high impact
   - R1 (Structured Output Validation) — the 33-73% fallback fix
   - R4 (Stall Recovery) — depends on H1

3. **Day 5-6: Coverage & Cost**
   - C1 (Feature Coverage Tracker) — define feature registries for Dread and Hexen
   - C2 (Novelty-Seeking Bias) — depends on C1
   - CC1 (Call Budget) — simple counter with degradation hooks
   - H3 (Resource Budget Monitor) — extends CC1 with anomaly thresholds

4. **Day 7: Diagnostics**
   - D1 (Post-Run Summary Report) — consumes O1, O5, C1 data
   - D4 (Death Autopsy) — slice trace on death event
   - O5 (Action Distribution Histogram) — aggregate from O1 trace data

**Validation:** Run 10-game batch with all P0 features. Compare against current baseline. Target:
- Fallback rate: <15% (from 33-73%)
- Feature coverage: >50% (from 32%)
- Zero undetected stalls
- Every death has a readable autopsy

### Phase 2: Intelligence (P1 features, ~10 days)

**Goal:** Agent self-monitors, self-corrects, and produces statistically rigorous comparisons across configurations.

**Highlights:**
- R3 (Model Fallback Chain) + R6 (Degradation Levels) — graduated fallback
- O4 (Anomaly Detection) — auto-flag deviations from baseline
- D3 (Regression Detection) + D6 (A/B Comparison) — data-driven improvement
- CC2 (Response Caching) + CC5 (Smart Trigger Gating) — cut Claude calls 40-60%
- L2 (Intervention Triggers) — human-on-the-loop, not human-in-the-loop

### Phase 3: Maturity (P2 features, ~10 days)

**Goal:** Cross-run learning, full state space exploration, longitudinal trend analysis.

**Highlights:**
- C4 (State Space Coverage Map) — persistent cross-run exploration graph
- O3 (Decision Replay) — post-mortem debugger
- D5 (Trend Dashboard) — "are we getting better over time?"

---

### Applying to Each Project

| Feature | Depths of Dread | Hexen Agent | WDW Planner |
|---------|----------------|-------------|-------------|
| H1 (Stall) | Floor/score not advancing | Kill/explore % not advancing | Task completion stalled |
| H2 (Repetition) | Action ring buffer | Tic action buffer | Selector/action buffer |
| O1 (Trace) | JSONL per turn | JSONL per tic batch | JSONL per test step |
| C1 (Coverage) | 32+ game features | Kill/explore/item/class features | 50+ app features |
| R4 (Recovery) | Claude reflection prompt | Claude reflection prompt | Retry with different selector |
| L1 (Pilot) | Already done | Keyboard override mid-game | Manual browser control mid-test |
| D1 (Summary) | Per-game + batch summary | Per-episode summary | Per-suite summary |

---

## 6. Sources

### Academic Papers & Frameworks
- [AgentBench: Evaluating LLMs as Agents](https://arxiv.org/abs/2308.03688) — Multi-environment agent evaluation benchmark
- [TITAN: Leveraging LLM Agents for Automated Video Game Testing](https://arxiv.org/abs/2509.22170) — LLM-driven MMORPG testing framework deployed in 8 commercial pipelines
- [Coverage-Aware Game Playtesting with LLM-Guided RL](https://arxiv.org/html/2512.12706) — Coverage signals as intrinsic reward for exploration
- [LLMs May Not Be Human-Level Players, But They Can Be Testers](https://arxiv.org/abs/2410.02829) — Using LLM agents to measure game difficulty
- [Towards LLM-Based Automatic Playtest](https://arxiv.org/abs/2507.09490) — LLM playtesting approaches
- [Beyond Black-Box Benchmarking: Observability of Agentic Systems](https://arxiv.org/html/2503.06745v1) — Agent observability patterns
- [Navigate the Unknown: LLM Reasoning with Intrinsic Motivation](https://arxiv.org/html/2505.17621v6) — Curiosity-driven exploration in LLM agents

### Industry Frameworks & Tools
- [Playwright Agents Documentation](https://playwright.dev/docs/test-agents) — AI-powered test automation (Planner, Generator, Healer)
- [Playwright MCP Server](https://github.com/microsoft/playwright-mcp) — LLM-to-browser bridge for agentic testing
- [LangSmith Observability Platform](https://www.langchain.com/langsmith/observability) — Agent tracing and evaluation
- [AI Agent Benchmark Compendium](https://github.com/philschmid/ai-agent-benchmark-compendium) — 50+ agent benchmarks catalogued

### Best Practice Guides
- [4 Fault Tolerance Patterns Every AI Agent Needs in Production](https://dev.to/klement_gunndu/4-fault-tolerance-patterns-every-ai-agent-needs-in-production-jih) — Retry, fallback, classification, checkpoint patterns
- [Diagnosing and Measuring AI Agent Failures: A Complete Guide](https://www.getmaxim.ai/articles/diagnosing-and-measuring-ai-agent-failures-a-complete-guide/) — Failure taxonomy and diagnostic patterns
- [Agent Evaluation Framework 2026: Metrics, Rubrics & Benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks) — Evaluation methodology
- [15 AI Agent Observability Tools in 2026](https://aimultiple.com/agentic-monitoring) — Tool landscape
- [AI Agent Monitoring Best Practices](https://uptimerobot.com/knowledge-hub/monitoring/ai-agent-monitoring-best-practices-tools-and-metrics/) — Production monitoring patterns
- [CrewAI Guardrails Guide](https://www.analyticsvidhya.com/blog/2025/11/introduction-to-task-guardrails-in-crewai/) — Task-level output validation
- [Human-in-the-Loop for AI Agents: Best Practices](https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo) — HITL implementation patterns
- [From Human-in-the-Loop to Human-on-the-Loop](https://bytebridge.medium.com/from-human-in-the-loop-to-human-on-the-loop-evolving-ai-agent-autonomy-c0ae62c3bf91) — Evolving autonomy paradigm
- [Mastering Retry Logic Agents: 2025 Best Practices](https://sparkco.ai/blog/mastering-retry-logic-agents-a-deep-dive-into-2025-best-practices) — Retry patterns in depth
- [LLM Cost Optimization: Complete Guide](https://ai.koombea.com/blog/llm-cost-optimization) — Token and call reduction strategies
