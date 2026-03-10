"""
Agent module for Depths of Dread.

Contains AgentPlayer (Claude-powered hybrid AI) and agent game loop functions.
"""
from __future__ import annotations

import curses
import random
import time
import sys
import json
import os
import subprocess
from collections import deque
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .game import GameState
    from .entities import Item, Enemy, Player
    import io

# Agent-commons: universal agentic testing framework (optional)
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'agent-commons'))
    from agent_commons import (
        ProgressStallDetector, ActionRepetitionDetector, ResourceBudgetMonitor,
        DecisionTrace, StateSnapshotManager, ActionDistribution,
        StructuredOutputValidator, StallRecoveryManager,
        FeatureCoverageTracker, NoveltySeekerBias, DREAD_FEATURES,
        PostRunSummaryReport, DeathAutopsy,
        CallBudgetManager, TriggerDeduplicator,
    )
    HAS_AGENT_COMMONS = True
except ImportError:
    HAS_AGENT_COMMONS = False

from .constants import *
from .constants import _CHALLENGE_MODES, _DIR_MAP
from .entities import *
from .entities import _unlock_next_spell, _unlock_next_ability
from .mapgen import *
from .mapgen import _has_los, compute_fov, astar
from .combat import *
from .combat import (_bestiary_record, _award_kill, _check_levelups, _trigger_trap,
                     _check_traps_on_move, _passive_trap_detect, _search_for_traps,
                     _disarm_trap, _compute_noise, _stealth_detection, _update_boss_phase,
                     _try_enemy_move, _flee_move, _chase_move)
from .items import *
from .items import (_get_direction_delta, _animate_projectile, _launch_projectile,
                    _apply_spell_resist, _cast_spell, _execute_ability,
                    _journal_potion_desc, _journal_scroll_desc, _toggle_switch,
                    _interact_pedestal, _interact_npc, _process_branch_effects)
from .ui import *
from .ui import (_draw_tile, _inv_letter, _inv_key_to_idx, _describe_tile, _bfs_unexplored)
from .persistence import *
from .persistence import (_default_lifetime_stats, _compute_checksum,
                          _serialize_item, _serialize_item_on_ground, _serialize_enemy,
                          _deserialize_item, _deserialize_item_ground, _deserialize_enemy,
                          _format_lifetime_stats_lines)

from .bot import BotPlayer, _bot_execute_action, _update_explored_from_fov
from .agent_ui import (
    FeatureTracker, _render_agent_panel, _pilot_process_key,
    AGENT_PANEL_X, AGENT_PANEL_MIN_W, AGENT_SPLIT_MIN_COLS,
)


def _get_game() -> Any:
    from . import game
    return game


class AgentPlayer:
    """Hybrid AI: BotPlayer for routine turns, Claude (Haiku) for tactical decisions."""

    def __init__(self, game_id: int = 1) -> None:
        self.bot: BotPlayer = BotPlayer()  # Fallback for non-triggered turns
        self.strategy: str = "INIT"
        self.target_desc: str = ""
        self.reason: str = ""        # Last Claude reasoning
        self.claude_calls: int = 0
        self.total_latency: float = 0.0
        self.fallbacks: int = 0
        self.items_used: int = 0
        self._thinking: bool = False   # True while waiting for Claude
        self._last_floor: int = 0
        self._last_call_latency: float = 0.0  # Latency of most recent Claude call
        self._consulted_shop: bool = False    # Only consult Claude about shop once per floor
        self._consulted_shrine: bool = False  # Only consult Claude about shrine once per floor
        self._consulted_locked_stairs: bool = False
        self._seen_wall_torch: bool = False
        self._last_consult_turn: int = 0     # Cooldown: min turns between non-critical calls
        self._last_state_hash: int | None = None    # State dedup: skip if unchanged
        # --- Health monitoring ---
        self._health_interval: int = 10          # Check every N turns
        self._health_warnings: list[str] = []          # Accumulated warnings
        self._window_calls: int = 0              # Claude calls in current window
        self._window_start_turn: int = 0         # Turn at start of current window
        self._floor_start_turn: int = 0          # Turn when current floor started
        self._action_window: deque[str] = deque(maxlen=20)  # Recent actions for distribution check
        self._hp_samples: deque[int] = deque(maxlen=10)     # Recent HP readings for trend
        self._trigger_counts: dict[str, int] = {}           # Track what's triggering Claude calls
        # --- Stuck detection ---
        self._position_history: deque[tuple[int, int]] = deque(maxlen=20)  # Last 20 positions
        self._last_stuck_turn: int = 0                  # Turn when last stuck trigger fired
        self._game_id: int = game_id
        self._log_file: io.TextIOWrapper | None = None
        # --- Agent-commons integration ---
        if HAS_AGENT_COMMONS:
            log_dir = os.path.expanduser("~/.depths_of_dread_agent_traces")
            os.makedirs(log_dir, exist_ok=True)
            trace_path = os.path.join(log_dir, f"game_{game_id}.jsonl")
            self._ac_trace = DecisionTrace(trace_path)
            self._ac_snapshots = StateSnapshotManager(
                snapshot_dir=log_dir, every_n_turns=25)
            self._ac_actions = ActionDistribution()
            self._ac_stall = ProgressStallDetector(threshold=20)
            self._ac_rep = ActionRepetitionDetector(window=20, repeat_threshold=5)
            self._ac_coverage = FeatureCoverageTracker()
            self._ac_coverage.register_features(DREAD_FEATURES)
            self._ac_novelty = NoveltySeekerBias(weight=0.3)
            self._ac_budget = CallBudgetManager(per_game=300, per_batch=1800)
            self._ac_validator = StructuredOutputValidator()
            self._ac_recovery = StallRecoveryManager(
                valid_actions=["move_north", "move_south", "move_east", "move_west",
                               "attack", "wait", "use_potion", "descend"])
            self._ac_dedup = TriggerDeduplicator()
            for trig, cd, crit in [
                ("enemies_visible", 0, False), ("low_hp", 3, True),
                ("boss", 0, True), ("new_floor", 0, True),
                ("shop", 10, False), ("shrine", 10, False),
                ("alchemy_table", 0, False), ("pedestal", 0, False),
                ("locked_stairs", 0, False), ("wall_torch", 10, False),
                ("stuck", 0, True), ("inventory_full", 5, False),
            ]:
                self._ac_dedup.register_trigger(trig, cooldown_turns=cd, critical=crit)
        else:
            self._ac_trace = None

    def _open_log(self) -> None:
        """Open the agent log file for real-time JSONL streaming."""
        if self._log_file is None:
            self._log_file = open(AGENT_LOG_PATH, 'a')

    def _log(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Write a JSONL event to the agent log (flushed immediately)."""
        self._open_log()
        entry = {
            "ts": time.time(),
            "game": self._game_id,
            "event": event_type,
        }
        if data:
            entry.update(data)
        self._log_file.write(json.dumps(entry) + "\n")
        self._log_file.flush()

    def close_log(self) -> None:
        """Close the log file."""
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def _serialize_state(self, gs: GameState) -> str:
        """Compact game state text for Claude (~300 chars target)."""
        p = gs.player
        hp_pct = int(p.hp / p.max_hp * 100) if p.max_hp > 0 else 0

        # Weapon/armor — short form
        wpn = f"{p.weapon.display_name}(atk{p.weapon.data.get('dmg', (0,0))[1]})" if p.weapon else "Fists"
        arm = f"{p.armor.display_name}(def{p.armor.data.get('defense', 0)})" if p.armor else "None"
        torch_pct = int(p.torch_fuel / TORCH_MAX_FUEL * 100) if TORCH_MAX_FUEL > 0 else 0

        # Inventory — just counts by type
        inv_counts = {}
        for item in p.inventory:
            if item.equipped:
                continue
            t = item.item_type
            inv_counts[t] = inv_counts.get(t, 0) + (item.count if hasattr(item, 'count') else 1)
        inv_str = " ".join(f"{k}:{v}" for k, v in inv_counts.items()) if inv_counts else "empty"

        # Visible enemies — compact
        enemy_parts = []
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                dx, dy = e.x - p.x, e.y - p.y
                dist = abs(dx) + abs(dy)
                d = ""
                if dy < 0: d += "N"
                if dy > 0: d += "S"
                if dx > 0: d += "E"
                if dx < 0: d += "W"
                boss = "!" if e.boss else ""
                alert_tag = f"[{e.alertness[0]}]" if e.alertness != "alert" else ""
                enemy_parts.append(f"{e.name}{boss}{alert_tag} hp{e.hp} {dist}{d}")
        enemies_str = ", ".join(enemy_parts) if enemy_parts else "none"

        # Visible items on ground — compact, limit to 3
        item_parts = []
        for item in gs.items:
            if (item.x, item.y) in gs.visible:
                dist = abs(item.x - p.x) + abs(item.y - p.y)
                if dist <= 8:
                    item_parts.append(f"{item.display_name}({dist})")
        items_str = ", ".join(item_parts[:3]) if item_parts else "none"

        # Nearby features — compact
        features = []
        sx, sy = gs.stair_down
        if (sx, sy) in gs.visible:
            features.append(f"stairs({abs(sx - p.x) + abs(sy - p.y)})")
        if gs.tiles[p.y][p.x] == T_SHRINE:
            features.append("ON_SHRINE")
        if gs.tiles[p.y][p.x] == T_STAIRS_DOWN:
            features.append("ON_STAIRS")
        if gs.tiles[p.y][p.x] == T_ALCHEMY_TABLE:
            used = "used" if (p.x, p.y) in gs.alchemy_used else "available"
            features.append(f"ALCHEMY({used})")
        if gs.tiles[p.y][p.x] in (T_PEDESTAL_UNLIT, T_PEDESTAL_LIT):
            state = "unlit" if gs.tiles[p.y][p.x] == T_PEDESTAL_UNLIT else "lit"
            features.append(f"PEDESTAL({state})")
        if gs.tiles[gs.stair_down[1]][gs.stair_down[0]] == T_STAIRS_LOCKED:
            features.append("STAIRS_LOCKED")
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = p.x + ddx, p.y + ddy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] == T_SHOP_FLOOR:
                features.append("SHOP_ADJ")
                break
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] == T_WALL_TORCH:
                features.append("WALL_TORCH_ADJ")
                break
        features_str = " ".join(features) if features else ""

        explored_pct = self.bot._floor_explored_pct(gs)

        class_str = CHARACTER_CLASSES[p.player_class]["name"] if p.player_class and p.player_class in CHARACTER_CLASSES else "Adv"
        status_str = " ".join(f"{k}({v})" for k, v in p.status_effects.items()) if p.status_effects else ""
        line = (f"F{p.floor}/{MAX_FLOORS} {class_str} HP{p.hp}/{p.max_hp}({hp_pct}%) MP{p.mana}/{p.max_mana} "
                f"Hng{p.hunger:.0f}% G{p.gold} T{gs.turn_count} Exp{explored_pct:.0%}\n"
                f"Wpn:{wpn} Arm:{arm} Torch:{torch_pct}%{'lit' if p.torch_lit else 'off'}\n"
                f"Inv({len(p.inventory)}/{p.carry_capacity}): {inv_str}\n"
                f"Enemies: {enemies_str}\n"
                f"Items: {items_str}")
        if status_str:
            line += f"\nStatus: {status_str}"
        # Include known spells and abilities so Claude can see what's available
        spells_str = ", ".join(sorted(p.known_spells))
        line += f"\nSpells: {spells_str}"
        if p.known_abilities:
            abilities_str = ", ".join(sorted(p.known_abilities))
            line += f"\nAbilities: {abilities_str}"
        if features_str:
            line += f"\nNear: {features_str}"
        if gs.puzzles:
            pz_parts = [f"{pz['type']}({'SOLVED' if pz['solved'] else 'active'})" for pz in gs.puzzles]
            line += f"\nPuzzles: {', '.join(pz_parts)}"
        if gs.journal:
            line += f"\nJournal: {len(gs.journal)} identified"
        if p.weapon and p.weapon.data.get("lifesteal"):
            line += "\nLifesteal weapon equipped"
        if gs.active_branch and gs.active_branch in BRANCH_DEFS:
            line += f"\nBranch: {BRANCH_DEFS[gs.active_branch]['name']}"
        # Stuck context: tell Claude where we've been
        if len(self._position_history) >= 15 and len(set(self._position_history)) <= 4:
            recent = list(set(self._position_history))
            line += f"\n!! STUCK — repeating positions {recent}. Try a NEW direction or teleport."
        return line

    def _state_hash(self, gs: GameState) -> int:
        """Quick hash of game state for dedup."""
        p = gs.player
        enemies = tuple(sorted((e.x, e.y, e.hp) for e in gs.enemies
                               if e.is_alive() and (e.x, e.y) in gs.visible))
        return hash((p.x, p.y, p.hp, p.mana, int(p.hunger), p.floor, enemies))

    def _should_consult(self, gs: GameState) -> bool:
        """Check if this turn warrants a Claude call. Tracks trigger reasons for health monitoring."""
        p = gs.player
        reason: str | None = None

        # Enemies visible — combat decisions
        if self.bot._enemies_visible(gs):
            reason = "enemies_visible"

        # Low HP (< 40%) with meaningful choices to make
        elif p.max_hp > 0 and p.hp / p.max_hp < 0.4:
            reason = "low_hp"

        # Full inventory + item on ground
        elif len(p.inventory) >= gs.player.carry_capacity:
            items_here = [i for i in gs.items if i.x == p.x and i.y == p.y and i.item_type != "gold"]
            if items_here:
                reason = "inventory_full"

        # Shop adjacent (only consult once per floor)
        if reason is None and not self._consulted_shop:
            for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                nx, ny = p.x + ddx, p.y + ddy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] == T_SHOP_FLOOR:
                    self._consulted_shop = True
                    reason = "shop"
                    break

        # Boss visible
        if reason is None:
            for e in gs.enemies:
                if e.is_alive() and e.boss and (e.x, e.y) in gs.visible:
                    reason = "boss"
                    break

        # New floor (just descended) — reset per-floor flags
        if reason is None and p.floor != self._last_floor:
            self._last_floor = p.floor
            self._consulted_shop = False
            self._consulted_shrine = False
            self._consulted_locked_stairs = False
            self._seen_wall_torch = False
            reason = "new_floor"

        # Shrine — standing on one (only consult once per floor)
        if reason is None and gs.tiles[p.y][p.x] == T_SHRINE and not self._consulted_shrine:
            self._consulted_shrine = True
            reason = "shrine"

        # Alchemy table — standing on one (consult once)
        if reason is None and gs.tiles[p.y][p.x] == T_ALCHEMY_TABLE:
            if (p.x, p.y) not in gs.alchemy_used:
                reason = "alchemy_table"

        # Puzzle pedestal — standing on unlit one
        if reason is None and gs.tiles[p.y][p.x] == T_PEDESTAL_UNLIT:
            reason = "pedestal"

        # Locked stairs visible (consult once per floor)
        if reason is None and not getattr(self, '_consulted_locked_stairs', False):
            sx, sy = gs.stair_down
            if gs.tiles[sy][sx] == T_STAIRS_LOCKED and (sx, sy) in gs.visible:
                self._consulted_locked_stairs = True
                reason = "locked_stairs"

        # Wall torch adjacent (first encounter per floor)
        if reason is None and not getattr(self, '_seen_wall_torch', False):
            for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                tx, ty = p.x + ddx, p.y + ddy
                if 0 <= tx < MAP_W and 0 <= ty < MAP_H and gs.tiles[ty][tx] == T_WALL_TORCH:
                    self._seen_wall_torch = True
                    reason = "wall_torch"
                    break

        # Stuck detection: player hasn't moved meaningfully in 15 turns
        if reason is None:
            self._position_history.append((p.x, p.y))
            if len(self._position_history) >= 15 and gs.turn_count - self._last_stuck_turn >= 20:
                unique_positions = len(set(self._position_history))
                if unique_positions <= 4:  # Bouncing between 4 or fewer tiles
                    self._last_stuck_turn = gs.turn_count
                    reason = "stuck"

        if reason:
            # Cooldown: skip non-critical triggers if consulted recently
            critical = reason in ("boss", "low_hp", "new_floor", "alchemy_table", "pedestal", "locked_stairs", "stuck")
            if not critical and self._last_consult_turn and gs.turn_count - self._last_consult_turn < 3:
                return False

            # State dedup: skip if state unchanged since last call (non-critical only)
            if not critical:
                state_hash = self._state_hash(gs)
                if state_hash == self._last_state_hash:
                    return False
                self._last_state_hash = state_hash

            self._last_consult_turn = gs.turn_count
            self._window_calls += 1
            self._trigger_counts[reason] = self._trigger_counts.get(reason, 0) + 1
            return True

        return False

    # --- Health monitoring baselines ---
    HEALTH_BASELINES: dict[str, float] = {
        "calls_per_turn_max": 0.5,       # Expected: ~0.3, alert if >0.5 sustained
        "fallback_rate_max": 0.25,        # Expected: <10%, alert if >25%
        "avg_latency_max": 15.0,          # Expected: ~5-8s, alert if >15s
        "turns_per_floor_max": 600,       # Expected: 200-400, alert if >600
        "action_monotony_max": 0.80,      # Alert if >80% of recent actions are identical
        "hp_loss_no_enemies_max": 5,      # Alert if losing HP with no visible enemies (per window)
    }

    def _health_check(self, gs: GameState) -> list[str]:
        """Run every _health_interval turns. Compares runtime metrics against baselines.
        Logs warnings and returns list of active warnings."""
        warnings: list[str] = []
        turn = gs.turn_count
        window_turns = turn - self._window_start_turn

        if window_turns < self._health_interval:
            return warnings

        # --- Calls/turn ratio ---
        if window_turns > 0:
            ratio = self._window_calls / window_turns
            if ratio > self.HEALTH_BASELINES["calls_per_turn_max"]:
                w = f"HEALTH: calls/turn={ratio:.2f} (max {self.HEALTH_BASELINES['calls_per_turn_max']})"
                warnings.append(w)
                # Log trigger distribution to help diagnose
                if self._trigger_counts:
                    top = sorted(self._trigger_counts.items(), key=lambda x: -x[1])[:3]
                    w += f" triggers={top}"
                    warnings[-1] = w

        # --- Fallback rate ---
        if self.claude_calls > 5:
            fb_rate = self.fallbacks / self.claude_calls
            if fb_rate > self.HEALTH_BASELINES["fallback_rate_max"]:
                warnings.append(f"HEALTH: fallback_rate={fb_rate:.0%} (max {self.HEALTH_BASELINES['fallback_rate_max']:.0%})")

        # --- Average latency ---
        if self.claude_calls > 0:
            avg_lat = self.total_latency / self.claude_calls
            if avg_lat > self.HEALTH_BASELINES["avg_latency_max"]:
                warnings.append(f"HEALTH: avg_latency={avg_lat:.1f}s (max {self.HEALTH_BASELINES['avg_latency_max']}s)")

        # --- Turns per floor (stuck detection) ---
        floor_turns = turn - self._floor_start_turn
        if floor_turns > self.HEALTH_BASELINES["turns_per_floor_max"]:
            warnings.append(f"HEALTH: turns_on_floor={floor_turns} (max {self.HEALTH_BASELINES['turns_per_floor_max']})")

        # --- Action monotony (same action repeated) ---
        if len(self._action_window) >= 10:
            from collections import Counter
            counts = Counter(self._action_window)
            most_common_action, most_common_count = counts.most_common(1)[0]
            monotony = most_common_count / len(self._action_window)
            if monotony > self.HEALTH_BASELINES["action_monotony_max"]:
                warnings.append(f"HEALTH: action_monotony={monotony:.0%} action='{most_common_action}' (max {self.HEALTH_BASELINES['action_monotony_max']:.0%})")

        # --- HP loss without visible enemies ---
        if len(self._hp_samples) >= 2:
            hp_loss = self._hp_samples[0] - self._hp_samples[-1]
            if hp_loss > self.HEALTH_BASELINES["hp_loss_no_enemies_max"]:
                enemies_visible = any(e.is_alive() and (e.x, e.y) in gs.visible and not e.disguised for e in gs.enemies)
                if not enemies_visible:
                    warnings.append(f"HEALTH: hp_loss={hp_loss} with no visible enemies (poison? fire_aura? starvation?)")

        # Log warnings
        for w in warnings:
            self._log("health_warning", {"turn": turn, "warning": w})

        # Reset window counters
        self._window_calls = 0
        self._window_start_turn = turn
        self._hp_samples.clear()
        self._trigger_counts.clear()
        self._health_warnings = warnings
        return warnings

    def _post_game_report(self, gs: GameState) -> dict[str, Any]:
        """Post-game health summary. Call after game ends. Returns dict of metrics + flags."""
        p = gs.player
        report: dict[str, Any] = {
            "turns": gs.turn_count,
            "floor": p.floor,
            "kills": p.kills,
            "victory": gs.victory,
            "claude_calls": self.claude_calls,
            "fallbacks": self.fallbacks,
            "avg_latency": self.total_latency / self.claude_calls if self.claude_calls > 0 else 0,
            "calls_per_turn": self.claude_calls / gs.turn_count if gs.turn_count > 0 else 0,
            "fallback_rate": self.fallbacks / self.claude_calls if self.claude_calls > 0 else 0,
            "warnings_total": len(self._health_warnings),
        }
        # Flag anomalies
        flags: list[str] = []
        if report["calls_per_turn"] > self.HEALTH_BASELINES["calls_per_turn_max"]:
            flags.append(f"HIGH calls/turn: {report['calls_per_turn']:.2f}")
        if report["fallback_rate"] > self.HEALTH_BASELINES["fallback_rate_max"]:
            flags.append(f"HIGH fallback rate: {report['fallback_rate']:.0%}")
        if report["avg_latency"] > self.HEALTH_BASELINES["avg_latency_max"]:
            flags.append(f"HIGH latency: {report['avg_latency']:.1f}s")
        if gs.turn_count > 0 and not gs.victory and p.floor <= 2 and gs.turn_count > 1000:
            flags.append(f"STUCK: {gs.turn_count} turns, only floor {p.floor}")
        report["flags"] = flags
        self._log("post_game_report", report)

        # Agent-commons: generate detailed summary and autopsy
        if HAS_AGENT_COMMONS and self._ac_trace is not None:
            try:
                summary_gen = PostRunSummaryReport()
                game_stats = {
                    "floor": p.floor, "score": calculate_score(gs) if hasattr(gs, 'player') else 0,
                    "turns": gs.turn_count,
                    "outcome": "victory" if gs.victory else "death",
                    "cause": getattr(p, 'death_cause', 'unknown'),
                    "hp": p.hp,
                    "duration_s": report.get("game_time_s", 0),
                    "stalls_recovered": self._ac_recovery.total_recoveries if hasattr(self, '_ac_recovery') else 0,
                }
                summary_text = summary_gen.generate(
                    trace=self._ac_trace, coverage=self._ac_coverage,
                    actions=self._ac_actions, game_stats=game_stats)
                self._log("ac_summary", {"text": summary_text})
                report["ac_summary"] = summary_text

                # Coverage report
                report["ac_coverage_pct"] = round(self._ac_coverage.coverage_pct(), 1)
                report["ac_covered"] = self._ac_coverage.covered()
                report["ac_uncovered"] = self._ac_coverage.uncovered()

                # Action distribution
                report["ac_action_dist"] = self._ac_actions.percentages()

                # Death autopsy if not victory
                if not gs.victory:
                    autopsy_gen = DeathAutopsy()
                    potions = sum(1 for i in p.inventory if i.item_type == "potion")
                    food = sum(1 for i in p.inventory if i.item_type == "food")
                    autopsy_text = autopsy_gen.generate(
                        trace=self._ac_trace,
                        final_state={
                            "cause": getattr(p, 'death_cause', 'unknown'),
                            "hp": p.hp, "potions": potions, "food": food,
                            "mana": p.mana,
                        })
                    self._log("ac_autopsy", {"text": autopsy_text})
                    report["ac_autopsy"] = autopsy_text

                # Save coverage for cross-run analysis
                cov_path = os.path.expanduser(f"~/.depths_of_dread_agent_traces/coverage_game_{self._game_id}.json")
                self._ac_coverage.save(cov_path)
            except Exception as e:
                self._log("ac_error", {"error": str(e)[:200]})

        return report

    def _call_claude(self, state_text: str) -> dict[str, Any] | None:
        """Call claude via stdin with game state, return parsed action dict or None.

        Uses stdin pipe instead of -p arg to avoid shell escaping issues and
        arg length limits.  Retries once on failure with a shorter timeout.
        """
        cmd = [
            CLAUDE_BIN,
            "-p", "-",        # Read prompt from stdin
            "--output-format", "json",
            "--model", "haiku",
            "--system-prompt", AGENT_SYSTEM_PROMPT,
            "--max-turns", "1",
            "--setting-sources", "",  # Skip CLAUDE.md — saves ~19K tokens & halves latency
        ]
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # Avoid nested-session error

        timeouts = [30, 20]  # First attempt 30s, retry 20s
        for attempt, timeout in enumerate(timeouts):
            try:
                start = time.time()
                result = subprocess.run(
                    cmd, input=state_text,
                    capture_output=True, text=True, timeout=timeout, env=env,
                )
                elapsed = time.time() - start
                self.total_latency += elapsed
                self._last_call_latency = elapsed
                self.claude_calls += 1

                if result.returncode != 0:
                    self._log("claude_error", {
                        "returncode": result.returncode,
                        "stderr": result.stderr[:200],
                        "attempt": attempt + 1,
                    })
                    if attempt < len(timeouts) - 1:
                        continue  # Retry
                    return None

                # Use agent-commons validator if available, else legacy parser
                parsed = None
                if HAS_AGENT_COMMONS and self._ac_trace is not None:
                    from agent_commons.reliability import ACTION_SCHEMA
                    val_parsed, val_errors = self._ac_validator.validate(result.stdout, ACTION_SCHEMA)
                    if val_parsed and not val_errors:
                        parsed = val_parsed
                    elif val_parsed and val_errors:
                        # Partial parse — try legacy as fallback
                        parsed = self._parse_response(result.stdout)
                    else:
                        parsed = self._parse_response(result.stdout)
                else:
                    parsed = self._parse_response(result.stdout)

                self._log("claude_call", {
                    "latency": round(elapsed, 2),
                    "action": parsed.get("action") if parsed else None,
                    "reason": parsed.get("reason", "") if parsed else None,
                    "state_preview": state_text[:120],
                    "attempt": attempt + 1,
                })
                # Agent-commons: log to decision trace
                if HAS_AGENT_COMMONS and self._ac_trace is not None:
                    trigger = self._trigger_counts.copy()
                    last_trigger = max(trigger, key=trigger.get) if trigger else "unknown"
                    self._ac_trace.log_decision(
                        turn=0,  # Will be set by caller context
                        trigger=last_trigger,
                        parsed_action=parsed.get("action") if parsed else None,
                        latency_ms=round(elapsed * 1000),
                        fallback_used=parsed is None,
                    )
                if parsed:
                    return parsed
                # Parseable failure — retry
                if attempt < len(timeouts) - 1:
                    self._log("claude_error", {"error": "unparseable_response", "attempt": attempt + 1, "raw": result.stdout[:300]})
                    continue
                self._log("claude_error", {"error": "unparseable_response_final", "attempt": attempt + 1, "raw": result.stdout[:300]})
                return None
            except subprocess.TimeoutExpired:
                self._log("claude_error", {"error": f"timeout_{timeout}s", "attempt": attempt + 1})
                if attempt < len(timeouts) - 1:
                    continue  # Retry with shorter timeout
                return None
            except Exception as exc:
                self._log("claude_error", {"error": str(exc)[:200], "attempt": attempt + 1})
                return None
        return None

    def _parse_response(self, raw: str) -> dict[str, Any] | None:
        """Extract action JSON from Claude's response.

        Claude --output-format json returns: {"type":"result","result":"..."}
        The result field contains the actual response text which should be
        our action JSON, possibly wrapped in markdown fences.
        """
        try:
            envelope = json.loads(raw)
            inner = envelope.get("result", "")
        except (json.JSONDecodeError, AttributeError):
            inner = raw

        # Strip markdown code fences if present
        inner = inner.strip()
        if inner.startswith("```"):
            lines = inner.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            inner = "\n".join(lines).strip()

        # Extract first JSON object — Haiku often appends analysis text after the JSON
        brace_start = inner.find("{")
        if brace_start >= 0:
            depth = 0
            for i, ch in enumerate(inner[brace_start:], brace_start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        inner = inner[brace_start:i + 1]
                        break

        try:
            data = json.loads(inner)
            if "action" in data:
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        return None

    def _action_to_command(self, action_str: str, gs: GameState) -> tuple[str, dict[str, Any]] | None:
        """Map Claude's action string -> (action, params) for _bot_execute_action.

        Handles common Claude response variations:
        - 'move north' vs 'move_north'
        - 'heal' vs 'cast_heal'
        - 'potion' vs 'use_potion'
        - 'eat' vs 'eat_food'
        """
        action_str = action_str.strip().lower()
        # Normalize: replace spaces with underscores, strip quotes
        action_str = action_str.replace(" ", "_").strip('"\'')
        p = gs.player

        # Movement — handle 'move_north', 'north', 'go_north', 'move_n'
        move_match = None
        if action_str.startswith("move_"):
            move_match = action_str[5:]
        elif action_str.startswith("go_"):
            move_match = action_str[3:]
        elif action_str in _DIR_MAP:
            move_match = action_str
        if move_match and move_match in _DIR_MAP:
            dx, dy = _DIR_MAP[move_match]
            return ("move", {"dx": dx, "dy": dy})

        # Attack (move toward nearest enemy) — handle 'attack', 'melee', 'attack_nearest'
        if action_str in ("attack", "melee", "attack_nearest"):
            nearest = self.bot._nearest_visible_enemy(gs)
            if nearest:
                dx = nearest.x - p.x
                dy = nearest.y - p.y
                dx = max(-1, min(1, dx))
                dy = max(-1, min(1, dy))
                return ("move", {"dx": dx, "dy": dy})

        # Fire projectile — handle 'fire_east', 'shoot_east'
        fire_match = None
        if action_str.startswith("fire_"):
            fire_match = action_str[5:]
        elif action_str.startswith("shoot_"):
            fire_match = action_str[6:]
        if fire_match and fire_match in _DIR_MAP:
            dx, dy = _DIR_MAP[fire_match]
            return ("fire", {"dx": dx, "dy": dy})

        # Spells — handle 'cast_heal', 'heal'
        if action_str in ("cast_heal", "heal"):
            return ("cast_spell", {"spell": "Heal"})
        if action_str.startswith("cast_fireball") or action_str.startswith("fireball"):
            parts = action_str.split("_")
            dir_name = parts[-1] if len(parts) > 1 else ""
            dx, dy = _DIR_MAP.get(dir_name, (0, 0))
            if dx == 0 and dy == 0:
                nearest = self.bot._nearest_visible_enemy(gs)
                if nearest:
                    dx = 1 if nearest.x > p.x else (-1 if nearest.x < p.x else 0)
                    dy = 1 if nearest.y > p.y else (-1 if nearest.y < p.y else 0)
            return ("cast_spell", {"spell": "Fireball", "dx": dx, "dy": dy})
        if action_str in ("cast_freeze", "freeze"):
            nearest = self.bot._nearest_visible_enemy(gs)
            return ("cast_spell", {"spell": "Freeze", "target": nearest})
        if action_str.startswith("cast_lightning") or action_str.startswith("lightning"):
            parts = action_str.split("_")
            dir_name = parts[-1] if len(parts) > 1 else ""
            dx, dy = _DIR_MAP.get(dir_name, (0, 0))
            return ("cast_spell", {"spell": "Lightning Bolt", "dx": dx, "dy": dy})
        if action_str in ("cast_teleport", "teleport"):
            return ("cast_spell", {"spell": "Teleport"})
        if action_str in ("cast_chain_lightning", "chain_lightning"):
            nearest = self.bot._nearest_visible_enemy(gs)
            return ("cast_spell", {"spell": "Chain Lightning", "target": nearest})
        if action_str.startswith("cast_meteor") or action_str.startswith("meteor"):
            parts = action_str.split("_")
            dir_name = parts[-1] if len(parts) > 1 else ""
            dx, dy = _DIR_MAP.get(dir_name, (0, 0))
            if dx == 0 and dy == 0:
                nearest = self.bot._nearest_visible_enemy(gs)
                if nearest:
                    dx = 1 if nearest.x > p.x else (-1 if nearest.x < p.x else 0)
                    dy = 1 if nearest.y > p.y else (-1 if nearest.y < p.y else 0)
            return ("cast_spell", {"spell": "Meteor", "dx": dx, "dy": dy})
        if action_str in ("cast_mana_shield", "mana_shield"):
            return ("cast_spell", {"spell": "Mana Shield"})

        # Class abilities — handle 'use_whirlwind', 'whirlwind', etc.
        _ABILITY_MAP = {
            "use_whirlwind": "Whirlwind", "whirlwind": "Whirlwind",
            "use_cleaving_strike": "Cleaving Strike", "cleaving_strike": "Cleaving Strike",
            "use_shield_wall": "Shield Wall", "shield_wall": "Shield Wall",
            "use_backstab": "Backstab", "backstab": "Backstab",
            "use_poison_blade": "Poison Blade", "poison_blade": "Poison Blade",
            "use_smoke_bomb": "Smoke Bomb", "smoke_bomb": "Smoke Bomb",
        }
        if action_str in _ABILITY_MAP:
            return ("use_ability", {"ability": _ABILITY_MAP[action_str]})

        # Items — handle 'use_potion', 'potion', 'drink_potion'
        if action_str in ("use_potion", "potion", "drink_potion"):
            for item in p.inventory:
                if item.item_type == "potion":
                    return ("use_item", {"item": item, "type": "potion"})
        if action_str in ("eat_food", "eat", "food"):
            for item in p.inventory:
                if item.item_type == "food":
                    return ("use_item", {"item": item, "type": "food"})

        # Equip — handle 'equip_<name>' and 'equip <name>'
        if action_str.startswith("equip_") or action_str.startswith("equip "):
            equip_name = action_str.split("_", 1)[-1].strip().lower() if "_" in action_str else action_str[6:].strip().lower()
            for item in p.inventory:
                if equip_name in item.display_name.lower() and not item.equipped:
                    return ("equip", {"item": item})

        # Other actions — handle variations
        if action_str in ("descend", "go_down", "stairs", "go_downstairs"):
            return ("descend", {})
        if action_str in ("rest", "wait", "pass", "skip", "do_nothing"):
            return ("rest", {})
        # New feature actions
        if action_str in ("use_alchemy", "alchemy", "identify"):
            if gs.tiles[p.y][p.x] == T_ALCHEMY_TABLE:
                return ("use_alchemy", {})
        if action_str in ("light_pedestal", "pedestal"):
            if gs.tiles[p.y][p.x] == T_PEDESTAL_UNLIT:
                return ("interact_pedestal", {})
        if action_str in ("grab_wall_torch", "grab_torch", "take_torch"):
            return ("grab_wall_torch", {})

        if action_str in ("pickup", "pick_up", "grab", "get", "take"):
            return ("pickup", {})
        if action_str in ("pray", "use_shrine"):
            return ("pray", {})
        if action_str in ("toggle_torch", "torch"):
            return ("toggle_torch", {})

        return None  # Unparseable

    def _track_coverage(self, gs: GameState, action_str: str = "") -> None:
        """Track feature coverage events from game state and action."""
        if not HAS_AGENT_COMMONS or self._ac_trace is None:
            return
        p = gs.player
        cov = self._ac_coverage
        a = action_str.lower()
        # Action-based coverage
        if "potion" in a or "heal" in a:
            cov.mark("used_potion")
        if "eat" in a or "food" in a:
            cov.mark("ate_food")
        if "equip" in a and "weapon" in a:
            cov.mark("equipped_weapon")
        if "equip" in a and "armor" in a:
            cov.mark("equipped_armor")
        if "equip" in a and "ring" in a:
            cov.mark("equipped_ring")
        if "cast" in a or "spell" in a:
            cov.mark("cast_spell")
        if "fireball" in a:
            cov.mark("cast_fireball")
        if a in ("cast_heal", "heal"):
            cov.mark("cast_heal")
        if "lightning" in a:
            cov.mark("cast_lightning")
        if "teleport" in a:
            cov.mark("cast_teleport")
        if "pray" in a or "shrine" in a:
            cov.mark("used_shrine")
        if "alchemy" in a or "identify" in a:
            cov.mark("used_alchemy_table")
        if "torch" in a:
            cov.mark("toggled_torch")
        if "fire" in a and "ball" not in a:
            cov.mark("fired_projectile")
        if "scroll" in a:
            cov.mark("used_scroll")
        if "pickup" in a or "pick_up" in a:
            cov.mark("picked_up_item")
        if "search" in a or "trap" in a:
            cov.mark("searched_for_traps")
        if "disarm" in a:
            cov.mark("disarmed_trap")
        if "descend" in a:
            cov.mark("descended_stairs")
        # State-based coverage
        if p.floor >= 5:
            cov.mark("reached_floor_5")
        if p.floor >= 10:
            cov.mark("reached_floor_10")
        if p.floor >= 15:
            cov.mark("reached_floor_15")
        if gs.active_branch:
            cov.mark("entered_branch")

    def decide(self, gs: GameState) -> tuple[str, dict[str, Any]]:
        """Returns (action, params) -- consults Claude for tactical decisions, BotPlayer otherwise."""
        p = gs.player

        # Track floor changes for health monitoring
        if p.floor != self._last_floor:
            self._floor_start_turn = gs.turn_count

        # HP sampling for health monitoring
        self._hp_samples.append(p.hp)

        # Log game state snapshot every 25 turns
        if gs.turn_count % 25 == 0:
            self._log("snapshot", {
                "turn": gs.turn_count, "floor": p.floor,
                "hp": p.hp, "max_hp": p.max_hp,
                "mana": p.mana, "hunger": round(p.hunger, 1),
                "kills": p.kills, "gold": p.gold,
                "inventory": len(p.inventory),
            })
            # Agent-commons: state snapshot at periodic intervals
            if HAS_AGENT_COMMONS and self._ac_trace is not None:
                if self._ac_snapshots.should_snapshot("periodic", gs.turn_count):
                    self._ac_snapshots.save_snapshot({
                        "turn": gs.turn_count, "floor": p.floor,
                        "hp": p.hp, "max_hp": p.max_hp,
                        "mana": p.mana, "hunger": round(p.hunger, 1),
                        "kills": p.kills, "gold": p.gold,
                        "inventory": len(p.inventory),
                        "explored": round(self.bot._floor_explored_pct(gs), 2),
                    }, "periodic", gs.turn_count)

        # Run health check periodically
        if gs.turn_count > 0 and gs.turn_count % self._health_interval == 0:
            self._health_check(gs)

        # Agent-commons: stall detection (progress = floor * 1000 + kills)
        ac_stalled = False
        ac_repeated = False
        if HAS_AGENT_COMMONS and self._ac_trace is not None:
            progress = p.floor * 1000 + p.kills
            ac_stalled = self._ac_stall.update(progress)

        if self._should_consult(gs):
            # Agent-commons: check call budget
            if HAS_AGENT_COMMONS and self._ac_trace is not None:
                if not self._ac_budget.spend():
                    # Budget exhausted — use bot only
                    self._log("budget_exhausted", {"turn": gs.turn_count})
                    action, params = self.bot.decide(gs)
                    self.strategy = self.bot.strategy
                    self.target_desc = self.bot.target_desc
                    self._action_window.append(self.strategy)
                    return (action, params)

            state_text = self._serialize_state(gs)
            # Agent-commons: append novelty hint to state
            if HAS_AGENT_COMMONS and self._ac_trace is not None:
                hint = self._ac_novelty.generate_exploration_hint(self._ac_coverage)
                if self._ac_coverage.coverage_pct() < 60:
                    state_text += f"\n{hint}"

            self._thinking = True
            response = self._call_claude(state_text)
            self._thinking = False

            if response and "action" in response:
                self.reason = response.get("reason", "")
                cmd = self._action_to_command(response["action"], gs)
                if cmd:
                    action, params = cmd
                    # Determine strategy label from action
                    action_str = response["action"].lower()
                    if "fire" in action_str or "attack" in action_str or "cast" in action_str:
                        self.strategy = "COMBAT"
                    elif "heal" in action_str or "potion" in action_str:
                        self.strategy = "HEAL"
                    elif "move" in action_str:
                        self.strategy = "TACTICAL"
                    elif "descend" in action_str:
                        self.strategy = "DESCEND"
                    else:
                        self.strategy = "CLAUDE"
                    self.target_desc = response["action"]
                    self._action_window.append(self.strategy)
                    # Agent-commons: record action + coverage
                    if HAS_AGENT_COMMONS and self._ac_trace is not None:
                        self._ac_actions.record(self.strategy)
                        ac_repeated = self._ac_rep.record(self.strategy)
                        self._track_coverage(gs, response["action"])
                    return (action, params)

            # Claude failed — fallback to bot
            self.fallbacks += 1
            self.reason = "(fallback to bot)"
            self._log("fallback", {"turn": gs.turn_count, "reason": "claude_failed"})

        # Agent-commons: attempt stall recovery if stalled or repeating
        if HAS_AGENT_COMMONS and self._ac_trace is not None and (ac_stalled or ac_repeated):
            recovery_action = self._ac_recovery.attempt_recovery(
                state_text=self._serialize_state(gs),
                action_history=self._ac_rep.history,
                call_fn=None,  # Skip LLM reflection for now — use random action
            )
            if recovery_action:
                cmd = self._action_to_command(recovery_action, gs)
                if cmd:
                    self._log("ac_recovery", {"turn": gs.turn_count, "action": recovery_action})
                    self.strategy = "RECOVERY"
                    self.target_desc = f"recovery:{recovery_action}"
                    self._action_window.append(self.strategy)
                    return cmd

        # Non-triggered turn or fallback: use BotPlayer
        action, params = self.bot.decide(gs)
        self.strategy = self.bot.strategy
        self.target_desc = self.bot.target_desc
        self._action_window.append(self.strategy)
        # Agent-commons: record bot action
        if HAS_AGENT_COMMONS and self._ac_trace is not None:
            self._ac_actions.record(self.strategy)
            self._ac_rep.record(self.strategy)
        return (action, params)


def agent_game_loop(scr: Any, speed: float = 0.15, max_turns: int = 10000) -> None:
    """Run a Claude-powered agent game visually in the terminal."""
    curses.curs_set(0)
    scr.nodelay(False)
    scr.keypad(True)
    init_colors()

    # Clear agent log for fresh session
    try:
        open(AGENT_LOG_PATH, 'w').close()
    except OSError:
        pass

    gs = _get_game().GameState(player_class="warrior")
    gs._scr = scr
    _get_game()._init_new_game(gs)
    agent = AgentPlayer(game_id=1)
    agent._log("game_start", {"seed": gs.seed, "mode": "visual", "class": "warrior"})
    show_panel = True
    paused = False
    delay_ms = max(10, int(speed * 1000))
    decision_log: deque[dict[str, Any]] = deque(maxlen=50)  # Rolling log of Claude decisions
    pilot_mode: bool = False  # Player takes manual control when True

    while gs.running and not gs.game_over and gs.turn_count < max_turns:
        fov_radius = gs.player.get_torch_radius()
        if "Blindness" in gs.player.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        _update_explored_from_fov(gs)

        # Auto-apply pending level-ups
        while gs.player.pending_levelups:
            auto_apply_levelup(gs.player)

        if pilot_mode:
            # Player manual control — same keys as interactive game
            safe_addstr(scr, 0, SCREEN_W // 2 - 6, " PILOT MODE ",
                       curses.color_pair(C_YELLOW) | curses.A_BOLD | curses.A_REVERSE)
            safe_addstr(scr, SCREEN_H - 1, 0, " Shift+P to release back to agent ",
                       curses.color_pair(C_YELLOW))
            scr.refresh()
            scr.nodelay(False)
            key = scr.getch()
            if key == ord('P'):
                pilot_mode = False
                continue
            turn_spent = _pilot_process_key(gs, scr, key)
            was_claude = False
        else:
            pre_calls = agent.claude_calls
            action, params = agent.decide(gs)
            was_claude = agent.claude_calls > pre_calls

            # Capture Claude decision into the rolling log
            if was_claude and agent.reason and agent.reason != "(fallback to bot)":
                decision_log.append({
                    "action": agent.target_desc,
                    "reason": agent.reason,
                    "latency": agent._last_call_latency,
                    "turn": gs.turn_count,
                })

            turn_spent = _bot_execute_action(gs, action, params)

        if turn_spent:
            gs.turn_count += 1
            if gs.last_noise > 0:
                _stealth_detection(gs, gs.last_noise)
            gs.last_noise = 0
            process_enemies(gs)
            process_status(gs)
            if gs.player.hp <= 0:
                gs.game_over = True

        # Re-compute FOV after action for rendering
        fov_radius = gs.player.get_torch_radius()
        if "Blindness" in gs.player.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        _update_explored_from_fov(gs)
        render_game(scr, gs)

        # Split-screen: decision panel on the right (if terminal is wide enough)
        _, term_w = scr.getmaxyx()
        if show_panel and term_w >= AGENT_SPLIT_MIN_COLS:
            _render_agent_panel(scr, agent, gs, decision_log)
        elif show_panel:
            # Narrow terminal fallback: compact overlay in top-right of game area
            p = gs.player
            hp_pct = int(p.hp / p.max_hp * 100) if p.max_hp > 0 else 0
            avg_lat = agent.total_latency / agent.claude_calls if agent.claude_calls > 0 else 0
            reason_display = agent.reason[:36] if agent.reason else ""
            tlines = [
                "AGENT (Claude-powered)",
                f"Strategy: {agent.strategy:<10} Turn: {gs.turn_count}",
                f'"{reason_display}"',
                f"Calls: {agent.claude_calls:<4} Avg: {avg_lat:.1f}s Falls: {agent.fallbacks}",
                f"HP: {p.hp}/{p.max_hp} ({hp_pct}%) Hunger: {p.hunger:.0f}%",
                f"F{p.floor} K{p.kills} Score:{calculate_score(p, gs):,}",
                "[t]panel [+/-]speed [space]pause [q]uit",
            ]
            for i, line in enumerate(tlines):
                safe_addstr(scr, i, SCREEN_W - len(line) - 1, line,
                           curses.color_pair(C_MAGENTA) if i == 0 else
                           curses.color_pair(C_CYAN))
        scr.refresh()

        # Handle user input
        scr.nodelay(True)
        ck = scr.getch()
        scr.nodelay(False)
        if ck == ord('q'):
            break
        elif ck == ord(' '):
            paused = not paused
            if paused:
                safe_addstr(scr, SCREEN_H // 2, SCREEN_W // 2 - 4, "PAUSED",
                           curses.color_pair(C_YELLOW) | curses.A_BOLD)
                scr.refresh()
                scr.nodelay(False)
                while True:
                    pk = scr.getch()
                    if pk == ord(' ') or pk == ord('q'):
                        paused = False
                        if pk == ord('q'):
                            gs.running = False
                        break
        elif ck == ord('+') or ck == ord('='):
            delay_ms = max(10, delay_ms // 2)
        elif ck == ord('-'):
            delay_ms = min(2000, delay_ms * 2)
        elif ck == ord('t'):
            show_panel = not show_panel
        elif ck == ord('P'):
            pilot_mode = not pilot_mode
            if pilot_mode:
                agent._log("pilot_mode", {"action": "engaged", "turn": gs.turn_count})
            else:
                agent._log("pilot_mode", {"action": "released", "turn": gs.turn_count})

        if not pilot_mode:
            curses.napms(delay_ms)

    # Log game end + health report
    p = gs.player
    agent._post_game_report(gs)
    agent._log("game_end", {
        "victory": gs.victory, "floor": p.floor, "kills": p.kills,
        "turns": gs.turn_count, "score": calculate_score(p, gs),
        "claude_calls": agent.claude_calls, "fallbacks": agent.fallbacks,
        "avg_latency": round(agent.total_latency / agent.claude_calls, 2) if agent.claude_calls > 0 else 0,
        "death_cause": gs.death_cause or ("victory" if gs.victory else "stopped"),
    })
    agent.close_log()

    # Show final screen
    render_game(scr, gs)
    if gs.victory:
        show_enhanced_victory(scr, gs)
    elif gs.game_over:
        show_enhanced_death(scr, gs)
    else:
        safe_addstr(scr, SCREEN_H // 2, 10, f"Agent stopped at turn {gs.turn_count}",
                   curses.color_pair(C_YELLOW) | curses.A_BOLD)
        scr.refresh()
        scr.nodelay(False)
        scr.getch()


def agent_batch_mode(num_games: int = 10, player_class: str | None = None) -> list[dict[str, Any]]:
    """Run multiple agent games headless and print summary stats.

    Args:
        num_games: Number of games to play.
        player_class: Force a class or None for rotation across warrior/mage/rogue.
    """
    CLASSES = ["warrior", "mage", "rogue"]
    # Clear agent log for fresh batch
    try:
        open(AGENT_LOG_PATH, 'w').close()
    except OSError:
        pass

    results: list[dict[str, Any]] = []
    total_claude_calls: int = 0
    total_claude_latency: float = 0.0
    total_fallbacks: int = 0
    batch_tracker: FeatureTracker = FeatureTracker()

    for i in range(num_games):
        game_class = player_class or CLASSES[i % len(CLASSES)]
        tracker = FeatureTracker()
        tracker.classes_played.add(game_class)
        batch_tracker.classes_played.add(game_class)

        gs = _get_game().GameState(headless=True, player_class=game_class)
        _get_game()._init_new_game(gs)
        agent = AgentPlayer(game_id=i + 1)
        agent._log("game_start", {"seed": gs.seed, "mode": "batch", "game_num": i + 1, "total_games": num_games, "class": game_class})
        max_turns = 10000
        max_iterations = max_turns * 3  # Safety: prevent infinite no-turn loops
        iterations = 0

        while gs.running and not gs.game_over and gs.turn_count < max_turns and iterations < max_iterations:
            iterations += 1
            fov_radius = gs.player.get_torch_radius()
            if "Blindness" in gs.player.status_effects:
                fov_radius = 1
            compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
            _update_explored_from_fov(gs)

            # Auto-apply pending level-ups
            while gs.player.pending_levelups:
                auto_apply_levelup(gs.player)

            action, params = agent.decide(gs)
            turn_spent = _bot_execute_action(gs, action, params)

            # Track feature interactions
            action_str = agent.action if hasattr(agent, 'action') else ""
            tracker.check_state(gs, action_str)

            if turn_spent:
                gs.turn_count += 1
                if gs.last_noise > 0:
                    _stealth_detection(gs, gs.last_noise)
                gs.last_noise = 0
                process_enemies(gs)
                process_status(gs)
                if gs.player.hp <= 0:
                    gs.game_over = True

        p = gs.player
        total_claude_calls += agent.claude_calls
        total_claude_latency += agent.total_latency
        total_fallbacks += agent.fallbacks
        avg_lat = agent.total_latency / agent.claude_calls if agent.claude_calls > 0 else 0

        health_report = agent._post_game_report(gs)
        agent._log("game_end", {
            "victory": gs.victory, "floor": p.floor, "kills": p.kills,
            "turns": gs.turn_count, "score": calculate_score(p, gs),
            "claude_calls": agent.claude_calls, "fallbacks": agent.fallbacks,
            "avg_latency": round(avg_lat, 2),
            "death_cause": gs.death_cause or ("victory" if gs.victory else "timeout"),
            "feature_coverage": tracker.coverage_pct(),
        })
        agent.close_log()

        # Merge per-game tracker into batch tracker
        for key, val in tracker.features.items():
            for subkey, subval in val.items():
                if isinstance(subval, bool) and subval:
                    batch_tracker.features[key][subkey] = True
                elif isinstance(subval, int) and subval > batch_tracker.features[key].get(subkey, 0):
                    batch_tracker.features[key][subkey] = subval

        results.append({
            "game": i + 1,
            "class": game_class,
            "victory": gs.victory,
            "floor": p.floor,
            "level": p.level,
            "kills": p.kills,
            "turns": gs.turn_count,
            "score": calculate_score(p, gs),
            "death_cause": gs.death_cause or ("victory" if gs.victory else "timeout"),
            "claude_calls": agent.claude_calls,
            "avg_latency": avg_lat,
            "fallbacks": agent.fallbacks,
            "health_flags": health_report.get("flags", []),
            "calls_per_turn": health_report.get("calls_per_turn", 0),
            "feature_coverage": f"{tracker.coverage_pct():.0%}",
        })
        status = "WIN!" if gs.victory else f"Died F{p.floor}"
        cls_tag = game_class[0].upper()
        flag_str = f"  !! {', '.join(health_report['flags'])}" if health_report.get("flags") else ""
        print(f"  Game {i+1:3d}: [{cls_tag}] {status:<12} Lv{p.level} T{gs.turn_count:5d} K{p.kills:3d} "
              f"Score:{calculate_score(p, gs):5d} Claude:{agent.claude_calls:3d} Avg:{avg_lat:.1f}s "
              f"C/T:{health_report.get('calls_per_turn', 0):.2f}{flag_str}")

    # Summary
    print("\n" + "=" * 60)
    print("AGENT BATCH SUMMARY (Claude-powered)")
    print("=" * 60)
    wins = sum(1 for r in results if r["victory"])
    avg_floor = sum(r["floor"] for r in results) / len(results)
    avg_kills = sum(r["kills"] for r in results) / len(results)
    avg_turns = sum(r["turns"] for r in results) / len(results)
    avg_score = sum(r["score"] for r in results) / len(results)
    max_floor = max(r["floor"] for r in results)
    crash_count = sum(1 for r in results if r["death_cause"] == "timeout")
    avg_calls = total_claude_calls / len(results)
    avg_total_lat = total_claude_latency / total_claude_calls if total_claude_calls > 0 else 0
    print(f"  Games: {num_games}  Wins: {wins}  Win rate: {wins/num_games*100:.0f}%")
    print(f"  Avg floor: {avg_floor:.1f}  Max floor: {max_floor}  Avg kills: {avg_kills:.1f}")
    print(f"  Avg turns: {avg_turns:.0f}  Avg score: {avg_score:.0f}")
    print(f"  Timeouts: {crash_count}")
    print(f"  Claude calls/game: {avg_calls:.0f}  Avg latency: {avg_total_lat:.1f}s  Fallbacks: {total_fallbacks}")
    causes = {}
    for r in results:
        c = r["death_cause"]
        causes[c] = causes.get(c, 0) + 1
    print(f"  Death causes: {causes}")
    # Health monitoring summary
    avg_cpt = sum(r.get("calls_per_turn", 0) for r in results) / len(results)
    flagged_games = [r for r in results if r.get("health_flags")]
    cpt_status = "OK" if avg_cpt <= 0.5 else "HIGH"
    print(f"\n  HEALTH: Avg calls/turn: {avg_cpt:.2f} [{cpt_status}]")
    if flagged_games:
        print(f"  HEALTH: {len(flagged_games)}/{num_games} games flagged:")
        for r in flagged_games:
            print(f"    Game {r['game']} [{r.get('class', '?')[0].upper()}]: {', '.join(r['health_flags'])}")
    else:
        print("  HEALTH: All games clean — no anomalies detected")
    # Feature coverage
    print(f"\n{batch_tracker.report()}")
    return results
