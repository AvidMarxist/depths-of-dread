"""
Bot / Agent module for Depths of Dread.

Contains BotPlayer (decision-tree AI), AgentPlayer (Claude-powered),
FeatureTracker, and game loop functions for bot/agent modes.
"""

import curses
import random
import time
import sys
import json
import os
import subprocess
from collections import deque

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


def _get_game():
    from . import game
    return game

# BOT PLAYER (AI Auto-Play)
# ============================================================

class BotPlayer:
    """AI bot that plays the game using a priority-based decision tree."""

    def __init__(self):
        self.strategy = "INIT"
        self.target_desc = ""
        self.items_used = 0
        self.potions_saved = 0
        self.decisions = 0
        self._explore_target = None  # Committed exploration target (x, y)
        self._explore_stuck = 0      # Counter for detecting oscillation
        self._last_positions = []     # Recent positions for loop detection
        self._floor_tiles_visited = set()  # Unique tiles visited on current floor
        self._floor_start_turn = 0         # Turn when we entered this floor
        self._current_floor = 0            # Track floor for reset

    def decide(self, gs):
        """Returns (action, params) tuple. Deterministic given same state."""
        self.decisions += 1
        p = gs.player

        # Paralysis: can't do anything, just wait
        if "Paralysis" in p.status_effects:
            self.strategy = "PARALYZED"
            self.target_desc = "can't move"
            return ("rest", {})

        # Fear: move away from enemies (can't approach them)
        if "Fear" in p.status_effects:
            flee_dir = self._flee_direction(gs)
            if flee_dir:
                self.strategy = "FEARED"
                self.target_desc = "fleeing in terror"
                return ("move", {"dx": flee_dir[0], "dy": flee_dir[1]})
            self.strategy = "FEARED"
            self.target_desc = "cowering"
            return ("rest", {})

        # Confusion: movement is randomized, just try to move
        if "Confusion" in p.status_effects:
            self.strategy = "CONFUSED"
            self.target_desc = "stumbling"
            dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
            return ("move", {"dx": dx, "dy": dy})

        # Floor change detection — reset per-floor tracking
        if p.floor != self._current_floor:
            self._current_floor = p.floor
            self._floor_tiles_visited = set()
            self._floor_start_turn = gs.turn_count
            self._explore_target = None
            self._explore_stuck = 0

        # Track unique tiles visited on this floor
        self._floor_tiles_visited.add((p.x, p.y))

        # Loop detection: track last 6 positions, detect oscillation
        self._last_positions.append((p.x, p.y))
        if len(self._last_positions) > 6:
            self._last_positions.pop(0)
        if len(self._last_positions) >= 6:
            unique = set(self._last_positions)
            if len(unique) <= 2:
                self._explore_stuck += 1
                self._explore_target = None  # Force new target
            else:
                self._explore_stuck = 0

        # --- Layer 1: Survival ---
        hp_pct = p.hp / p.max_hp if p.max_hp > 0 else 0
        hunger_pct = p.hunger

        # Urgent heal if poisoned and HP getting low
        if "Poison" in p.status_effects and hp_pct < 0.5:
            for item in p.inventory:
                if item.item_type == "potion" and item.identified and item.data.get("effect") == "Healing":
                    self.strategy = "HEAL"
                    self.target_desc = "poisoned! healing"
                    return ("use_item", {"item": item, "type": "potion"})
            if p.mana >= SPELLS["Heal"]["cost"]:
                self.strategy = "HEAL"
                self.target_desc = "poisoned! heal spell"
                return ("cast_spell", {"spell": "Heal"})

        # Heal if HP < 40%
        if hp_pct < 0.4:
            # Try healing potion
            for item in p.inventory:
                if item.item_type == "potion":
                    if item.identified and item.data.get("effect") == "Healing":
                        self.strategy = "HEAL"
                        self.target_desc = "potion"
                        return ("use_item", {"item": item, "type": "potion"})
                    elif not item.identified and hp_pct < 0.25:
                        self.strategy = "HEAL"
                        self.target_desc = "unknown potion (desperate)"
                        return ("use_item", {"item": item, "type": "potion"})
            # Try Heal spell
            if p.mana >= SPELLS["Heal"]["cost"]:
                self.strategy = "HEAL"
                self.target_desc = "spell"
                return ("cast_spell", {"spell": "Heal"})
            # Eat food if it restores some HP via hunger
            if hunger_pct < 60:
                for item in p.inventory:
                    if item.item_type == "food":
                        self.strategy = "HEAL"
                        self.target_desc = "food"
                        return ("use_item", {"item": item, "type": "food"})
            # Rest if no enemies visible and hunger ok
            if hunger_pct > 30 and not self._enemies_visible(gs):
                self.strategy = "REST"
                self.target_desc = "resting"
                return ("rest", {})

        # Eat food if hunger < 30%
        if hunger_pct < 30:
            for item in p.inventory:
                if item.item_type == "food":
                    self.strategy = "EAT"
                    self.target_desc = item.display_name
                    return ("use_item", {"item": item, "type": "food"})

        # Equip better gear immediately
        equip_action = self._check_equipment_upgrade(gs)
        if equip_action:
            return equip_action

        # Flee if HP < 20% and enemies visible
        if hp_pct < 0.2 and self._enemies_visible(gs):
            flee_dir = self._flee_direction(gs)
            if flee_dir:
                self.strategy = "FLEE"
                self.target_desc = "running away"
                return ("move", {"dx": flee_dir[0], "dy": flee_dir[1]})

        # --- Layer 2: Combat ---
        nearest_enemy = self._nearest_visible_enemy(gs)
        if nearest_enemy:
            dist = abs(nearest_enemy.x - p.x) + abs(nearest_enemy.y - p.y)

            # Warrior: Whirlwind when 3+ adjacent enemies
            if (p.player_class == "warrior" and "Whirlwind" in p.known_abilities
                    and p.mana >= B["whirlwind_cost"]):
                adj_count = sum(1 for e in gs.enemies
                               if e.is_alive() and abs(e.x - p.x) <= 1 and abs(e.y - p.y) <= 1
                               and (e.x != p.x or e.y != p.y))
                if adj_count >= 3:
                    self.strategy = "COMBAT"
                    self.target_desc = f"whirlwind ({adj_count} adjacent)"
                    return ("use_ability", {"ability": "Whirlwind"})

            # Warrior: Shield Wall when HP < 30% and no heal available
            if (p.player_class == "warrior" and "Shield Wall" in p.known_abilities
                    and p.mana >= B["shield_wall_cost"] and "Shield Wall" not in p.status_effects
                    and hp_pct < 0.3):
                has_heal = any(it.item_type == "potion" and it.identified and it.data.get("effect") == "Healing"
                              for it in p.inventory)
                if not has_heal:
                    self.strategy = "COMBAT"
                    self.target_desc = "shield wall (low HP)"
                    return ("use_ability", {"ability": "Shield Wall"})

            # Rogue: Backstab before engaging bosses
            if (p.player_class == "rogue" and "Backstab" in p.known_abilities
                    and p.mana >= B["backstab_cost"] and nearest_enemy.boss
                    and "Backstab" not in p.status_effects):
                self.strategy = "COMBAT"
                self.target_desc = f"backstab -> {nearest_enemy.name}"
                return ("use_ability", {"ability": "Backstab"})

            # Rogue: Smoke Bomb when HP < 30% and 2+ enemies visible
            if (p.player_class == "rogue" and "Smoke Bomb" in p.known_abilities
                    and p.mana >= B["smoke_bomb_cost"] and hp_pct < 0.3):
                visible_count = sum(1 for e in gs.enemies
                                   if e.is_alive() and (e.x, e.y) in gs.visible)
                if visible_count >= 2:
                    self.strategy = "COMBAT"
                    self.target_desc = f"smoke bomb ({visible_count} visible)"
                    return ("use_ability", {"ability": "Smoke Bomb"})

            # Ranged attack if enemy > 2 tiles away
            if dist > 2:
                # Try wand
                for item in p.inventory:
                    if item.item_type == "wand" and item.data.get("charges", 0) > 0:
                        dx = 1 if nearest_enemy.x > p.x else (-1 if nearest_enemy.x < p.x else 0)
                        dy = 1 if nearest_enemy.y > p.y else (-1 if nearest_enemy.y < p.y else 0)
                        if dx != 0 or dy != 0:
                            self.strategy = "COMBAT"
                            self.target_desc = f"wand -> {nearest_enemy.name}"
                            return ("fire", {"dx": dx, "dy": dy})
                # Try bow
                if p.bow:
                    for item in p.inventory:
                        if item.item_type == "arrow" and item.count > 0:
                            dx = 1 if nearest_enemy.x > p.x else (-1 if nearest_enemy.x < p.x else 0)
                            dy = 1 if nearest_enemy.y > p.y else (-1 if nearest_enemy.y < p.y else 0)
                            if dx != 0 or dy != 0:
                                self.strategy = "COMBAT"
                                self.target_desc = f"arrow -> {nearest_enemy.name}"
                                return ("fire", {"dx": dx, "dy": dy})

            # Mage: Cast Chain Lightning on 2+ visible enemies
            if (p.player_class == "mage" and "Chain Lightning" in p.known_spells
                    and p.mana >= SPELLS["Chain Lightning"]["cost"] and p.mana > p.max_mana * 0.5):
                visible_enemies = sum(1 for e in gs.enemies
                                     if e.is_alive() and (e.x, e.y) in gs.visible)
                if visible_enemies >= 2:
                    self.strategy = "COMBAT"
                    self.target_desc = f"chain lightning ({visible_enemies} visible)"
                    return ("cast_spell", {"spell": "Chain Lightning", "target": nearest_enemy})

            # Cast Fireball on 2+ clustered enemies
            if ("Fireball" in p.known_spells and p.mana >= SPELLS["Fireball"]["cost"]
                    and p.mana > p.max_mana * 0.5):
                clustered = sum(1 for e in gs.enemies
                               if e.is_alive() and (e.x, e.y) in gs.visible
                               and abs(e.x - nearest_enemy.x) + abs(e.y - nearest_enemy.y) <= 2)
                if clustered >= 2:
                    self.strategy = "COMBAT"
                    self.target_desc = f"fireball ({clustered} targets)"
                    dx = 1 if nearest_enemy.x > p.x else (-1 if nearest_enemy.x < p.x else 0)
                    dy = 1 if nearest_enemy.y > p.y else (-1 if nearest_enemy.y < p.y else 0)
                    return ("cast_spell", {"spell": "Fireball", "dx": dx, "dy": dy})

            # Cast Freeze on bosses
            if ("Freeze" in p.known_spells and nearest_enemy.boss
                    and p.mana >= SPELLS["Freeze"]["cost"] and nearest_enemy.frozen_turns <= 0):
                self.strategy = "COMBAT"
                self.target_desc = f"freeze -> {nearest_enemy.name}"
                return ("cast_spell", {"spell": "Freeze", "target": nearest_enemy})

            # Melee: auto-fight step (move toward or attack)
            if dist == 1:
                self.strategy = "COMBAT"
                self.target_desc = nearest_enemy.name
                return ("move", {"dx": nearest_enemy.x - p.x, "dy": nearest_enemy.y - p.y})
            else:
                step = astar(gs.tiles, p.x, p.y, nearest_enemy.x, nearest_enemy.y, max_steps=30)
                if step:
                    self.strategy = "COMBAT"
                    self.target_desc = f"approaching {nearest_enemy.name}"
                    return ("move", {"dx": step[0], "dy": step[1]})

        # --- Layer 3: Exploration ---
        # Pick up items on current tile
        items_here = [i for i in gs.items if i.x == p.x and i.y == p.y]
        if items_here:
            self.strategy = "LOOT"
            self.target_desc = "pickup"
            return ("pickup", {})

        # Pray at shrine if HP > 60%
        if gs.tiles[p.y][p.x] == T_SHRINE and hp_pct > 0.6:
            self.strategy = "EXPLORE"
            self.target_desc = "praying"
            return ("pray", {})

        # Descend stairs when floor is explored enough
        if gs.tiles[p.y][p.x] == T_STAIRS_DOWN:
            explored_pct = self._floor_explored_pct(gs)
            if explored_pct > 0.4 or (explored_pct > 0.2 and hp_pct > 0.5):
                self.strategy = "DESCEND"
                self.target_desc = f"floor {p.floor + 1}"
                return ("descend", {})

        # After 150+ turns on a floor, prioritize finding stairs
        if gs.turn_count > 150 * p.floor and p.floor < MAX_FLOORS:
            sx, sy = gs.stair_down
            if gs.tiles[sy][sx] == T_STAIRS_DOWN:
                step = astar(gs.tiles, p.x, p.y, sx, sy, max_steps=80)
                if step:
                    self.strategy = "DESCEND"
                    self.target_desc = "urgently seeking stairs"
                    return ("move", {"dx": step[0], "dy": step[1]})
            elif gs.tiles[sy][sx] == T_STAIRS_LOCKED:
                # Stairs are locked — keep exploring (walk on switches naturally)
                self.strategy = "EXPLORE"
                self.target_desc = "stairs locked, exploring"
                # Don't try to pathfind to locked stairs

        # Auto-explore with committed target (prevents oscillation)
        # Invalidate target if we reached it or it's now explored
        if self._explore_target:
            tx, ty = self._explore_target
            if (p.x == tx and p.y == ty) or gs.explored[ty][tx]:
                self._explore_target = None

        # If stuck in a loop, pick a random walkable neighbor to break out
        if self._explore_stuck >= 3:
            self._explore_stuck = 0
            self._explore_target = None
            neighbors = []
            for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1),(1,1),(1,-1),(-1,1),(-1,-1)]:
                nx, ny = p.x + ddx, p.y + ddy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
                    if not any(e.x == nx and e.y == ny and e.is_alive() for e in gs.enemies):
                        neighbors.append((ddx, ddy))
            if neighbors:
                # Pick the neighbor closest to stairs to make progress
                sx, sy = gs.stair_down
                neighbors.sort(key=lambda d: abs(p.x+d[0]-sx) + abs(p.y+d[1]-sy))
                dx, dy = neighbors[0]
                self.strategy = "UNSTICK"
                self.target_desc = "breaking loop"
                return ("move", {"dx": dx, "dy": dy})

        if not self._explore_target:
            self._explore_target = _bfs_unexplored(gs)

        if self._explore_target:
            tx, ty = self._explore_target
            step = astar(gs.tiles, p.x, p.y, tx, ty, max_steps=50)
            if step:
                self.strategy = "EXPLORE"
                self.target_desc = "unexplored"
                return ("move", {"dx": step[0], "dy": step[1]})
            else:
                self._explore_target = None  # Unreachable, pick new target

        # Find stairs if fully explored
        sx, sy = gs.stair_down
        if gs.tiles[sy][sx] == T_STAIRS_DOWN and p.floor < MAX_FLOORS:
            step = astar(gs.tiles, p.x, p.y, sx, sy, max_steps=80)
            if step:
                self.strategy = "DESCEND"
                self.target_desc = "heading to stairs"
                return ("move", {"dx": step[0], "dy": step[1]})

        # Floor-level stall detection: if 500+ turns on this floor and barely moving,
        # bias movement toward stairs coordinates (random walk, not pathfind)
        floor_turns = gs.turn_count - self._floor_start_turn
        if floor_turns > 500 and len(self._floor_tiles_visited) < 30:
            sx, sy = gs.stair_down
            dx = 1 if sx > p.x else (-1 if sx < p.x else 0)
            dy = 1 if sy > p.y else (-1 if sy < p.y else 0)
            # Try biased direction first, then any walkable neighbor
            for ddx, ddy in [(dx, dy), (dx, 0), (0, dy), (-dx, 0), (0, -dy)]:
                if ddx == 0 and ddy == 0:
                    continue
                nx, ny = p.x + ddx, p.y + ddy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
                    self.strategy = "FORCE_MOVE"
                    self.target_desc = "stall break, toward stairs"
                    return ("move", {"dx": ddx, "dy": ddy})

        # --- Layer 4: Resource Management ---
        # Toggle torch
        if p.torch_lit and not self._enemies_visible(gs) and p.torch_fuel < TORCH_MAX_FUEL * 0.25:
            self.strategy = "MANAGE"
            self.target_desc = "conserve torch"
            return ("toggle_torch", {})
        if not p.torch_lit and self._enemies_visible(gs) and p.torch_fuel > 0:
            self.strategy = "MANAGE"
            self.target_desc = "light torch"
            return ("toggle_torch", {})

        # Fallback: wait
        self.strategy = "WAIT"
        self.target_desc = "waiting"
        return ("rest", {})

    def _enemies_visible(self, gs):
        return any(e.is_alive() and (e.x, e.y) in gs.visible and not e.disguised for e in gs.enemies)

    def _nearest_visible_enemy(self, gs):
        p = gs.player
        nearest = None
        nd = 999
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                d = abs(e.x - p.x) + abs(e.y - p.y)
                if d < nd:
                    nd = d
                    nearest = e
        return nearest

    def _flee_direction(self, gs):
        """Move away from nearest enemy."""
        p = gs.player
        nearest = self._nearest_visible_enemy(gs)
        if not nearest:
            return None
        # Move in opposite direction
        dx = -1 if nearest.x > p.x else (1 if nearest.x < p.x else 0)
        dy = -1 if nearest.y > p.y else (1 if nearest.y < p.y else 0)
        nx, ny = p.x + dx, p.y + dy
        if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
            return (dx, dy)
        # Try cardinal directions
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = p.x + ddx, p.y + ddy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
                if not any(e.x == nx and e.y == ny and e.is_alive() for e in gs.enemies):
                    return (ddx, ddy)
        return None

    def _check_equipment_upgrade(self, gs):
        """Check if we have better unequipped gear."""
        p = gs.player
        for item in p.inventory:
            if item.equipped:
                continue
            if item.item_type == "weapon":
                if not p.weapon or item.data.get("dmg", (0,0))[1] > p.weapon.data.get("dmg", (0,0))[1]:
                    self.strategy = "EQUIP"
                    self.target_desc = item.display_name
                    return ("equip", {"item": item})
            elif item.item_type == "armor":
                if not p.armor or item.data.get("defense", 0) > p.armor.data.get("defense", 0):
                    self.strategy = "EQUIP"
                    self.target_desc = item.display_name
                    return ("equip", {"item": item})
            elif item.item_type == "ring" and not p.ring:
                if item.data.get("effect") != "hunger":  # Don't equip cursed ring
                    self.strategy = "EQUIP"
                    self.target_desc = item.display_name
                    return ("equip", {"item": item})
            elif item.item_type == "bow":
                if not p.bow or item.data.get("dmg", (0,0))[1] > p.bow.data.get("dmg", (0,0))[1]:
                    self.strategy = "EQUIP"
                    self.target_desc = item.display_name
                    return ("equip", {"item": item})
        return None

    def _floor_explored_pct(self, gs):
        explored = sum(1 for row in gs.explored for c in row if c)
        total = count_walkable(gs.tiles)
        return explored / total if total > 0 else 1.0


def _update_explored_from_fov(gs):
    """Mark all visible tiles as explored (needed for headless/bot mode)."""
    for (mx, my) in gs.visible:
        if 0 <= mx < MAP_W and 0 <= my < MAP_H:
            gs.explored[my][mx] = True


# ============================================================
# AGENT PLAYER — Claude-powered hybrid AI
# ============================================================

class FeatureTracker:
    """Track which game features the agent encounters and interacts with."""

    def __init__(self):
        self.features = {
            "puzzle_torch": {"encountered": False, "solved": False},
            "puzzle_switch": {"encountered": False, "solved": False},
            "puzzle_locked": {"encountered": False, "solved": False},
            "alchemy_table": {"encountered": False, "used": False},
            "journal": {"opened": False, "entries": 0},
            "wall_torch": {"encountered": False, "grabbed": False},
            "boss_weapon_drop": {"dropped": False, "equipped": False},
            "lifesteal": {"triggered": False, "total_healed": 0},
            "shop": {"encountered": False, "bought": False},
            "shrine": {"encountered": False, "prayed": False},
            "wand_used": {"used": False},
        }
        self.classes_played = set()
        self.spells_cast = set()
        self.abilities_used = set()

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
                ptype = puzzle["type"]
                key = f"puzzle_{ptype}" if f"puzzle_{ptype}" in self.features else None
                if key:
                    self.features[key]["solved"] = True

        if gs.journal:
            self.features["journal"]["entries"] = len(gs.journal)
        if gs.wall_torches:
            self.features["wall_torch"]["encountered"] = True

        # Track action-based features
        if action_str in ("use_alchemy", "alchemy", "identify"):
            self.features["alchemy_table"]["used"] = True
        if action_str in ("grab_wall_torch", "grab_torch"):
            self.features["wall_torch"]["grabbed"] = True
        if action_str in ("open_journal", "journal"):
            self.features["journal"]["opened"] = True

        # Boss weapon
        if p.weapon and p.weapon.data.get("boss_drop"):
            self.features["boss_weapon_drop"]["equipped"] = True

        # Shop/shrine
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = p.x + ddx, p.y + ddy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] == T_SHOP_FLOOR:
                self.features["shop"]["encountered"] = True

    def coverage_pct(self):
        """Return overall feature coverage as a percentage."""
        total = 0
        covered = 0
        for val in self.features.values():
            for subval in val.values():
                if isinstance(subval, bool):
                    total += 1
                    if subval:
                        covered += 1
        return covered / total if total > 0 else 0

    def report(self):
        """Return human-readable feature coverage report."""
        lines = ["FEATURE COVERAGE REPORT", "=" * 40]
        for key, val in sorted(self.features.items()):
            parts = []
            for k, v in val.items():
                if isinstance(v, bool):
                    parts.append(f"{k}:{'YES' if v else 'no'}")
                else:
                    parts.append(f"{k}:{v}")
            lines.append(f"  {key:25s} {' | '.join(parts)}")
        lines.append(f"\n  Coverage: {self.coverage_pct():.0%}")
        if self.classes_played:
            lines.append(f"  Classes: {', '.join(sorted(self.classes_played))}")
        if self.spells_cast:
            lines.append(f"  Spells: {', '.join(sorted(self.spells_cast))}")
        if self.abilities_used:
            lines.append(f"  Abilities: {', '.join(sorted(self.abilities_used))}")
        return "\n".join(lines)


class AgentPlayer:
    """Hybrid AI: BotPlayer for routine turns, Claude (Haiku) for tactical decisions."""

    def __init__(self, game_id=1):
        self.bot = BotPlayer()  # Fallback for non-triggered turns
        self.strategy = "INIT"
        self.target_desc = ""
        self.reason = ""        # Last Claude reasoning
        self.claude_calls = 0
        self.total_latency = 0.0
        self.fallbacks = 0
        self.items_used = 0
        self._thinking = False   # True while waiting for Claude
        self._last_floor = 0
        self._last_call_latency = 0.0  # Latency of most recent Claude call
        self._consulted_shop = False    # Only consult Claude about shop once per floor
        self._consulted_shrine = False  # Only consult Claude about shrine once per floor
        self._consulted_locked_stairs = False
        self._seen_wall_torch = False
        self._last_consult_turn = 0     # Cooldown: min turns between non-critical calls
        self._last_state_hash = None    # State dedup: skip if unchanged
        # --- Health monitoring ---
        self._health_interval = 10          # Check every N turns
        self._health_warnings = []          # Accumulated warnings
        self._window_calls = 0              # Claude calls in current window
        self._window_start_turn = 0         # Turn at start of current window
        self._floor_start_turn = 0          # Turn when current floor started
        self._action_window = deque(maxlen=20)  # Recent actions for distribution check
        self._hp_samples = deque(maxlen=10)     # Recent HP readings for trend
        self._trigger_counts = {}           # Track what's triggering Claude calls
        # --- Stuck detection ---
        self._position_history = deque(maxlen=20)  # Last 20 positions
        self._last_stuck_turn = 0                  # Turn when last stuck trigger fired
        self._game_id = game_id
        self._log_file = None
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

    def _open_log(self):
        """Open the agent log file for real-time JSONL streaming."""
        if self._log_file is None:
            self._log_file = open(AGENT_LOG_PATH, 'a')

    def _log(self, event_type, data=None):
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

    def close_log(self):
        """Close the log file."""
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def _serialize_state(self, gs):
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

    def _state_hash(self, gs):
        """Quick hash of game state for dedup."""
        p = gs.player
        enemies = tuple(sorted((e.x, e.y, e.hp) for e in gs.enemies
                               if e.is_alive() and (e.x, e.y) in gs.visible))
        return hash((p.x, p.y, p.hp, p.mana, int(p.hunger), p.floor, enemies))

    def _should_consult(self, gs):
        """Check if this turn warrants a Claude call. Tracks trigger reasons for health monitoring."""
        p = gs.player
        reason = None

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
    HEALTH_BASELINES = {
        "calls_per_turn_max": 0.5,       # Expected: ~0.3, alert if >0.5 sustained
        "fallback_rate_max": 0.25,        # Expected: <10%, alert if >25%
        "avg_latency_max": 15.0,          # Expected: ~5-8s, alert if >15s
        "turns_per_floor_max": 600,       # Expected: 200-400, alert if >600
        "action_monotony_max": 0.80,      # Alert if >80% of recent actions are identical
        "hp_loss_no_enemies_max": 5,      # Alert if losing HP with no visible enemies (per window)
    }

    def _health_check(self, gs):
        """Run every _health_interval turns. Compares runtime metrics against baselines.
        Logs warnings and returns list of active warnings."""
        warnings = []
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

    def _post_game_report(self, gs):
        """Post-game health summary. Call after game ends. Returns dict of metrics + flags."""
        p = gs.player
        report = {
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
        flags = []
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

    def _call_claude(self, state_text):
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

    def _parse_response(self, raw):
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

    def _action_to_command(self, action_str, gs):
        """Map Claude's action string → (action, params) for _bot_execute_action.

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

    def _track_coverage(self, gs, action_str=""):
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

    def decide(self, gs):
        """Returns (action, params) — consults Claude for tactical decisions, BotPlayer otherwise."""
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


AGENT_PANEL_X = 82  # Right panel starts 2 cols after game area (col 80)
AGENT_PANEL_MIN_W = 50  # Minimum panel width to be useful
AGENT_SPLIT_MIN_COLS = AGENT_PANEL_X + AGENT_PANEL_MIN_W  # 132 cols needed


def _render_agent_panel(scr, agent, gs, decision_log):
    """Render the split-screen decision panel to the right of the game."""
    term_h, term_w = scr.getmaxyx()
    panel_w = term_w - AGENT_PANEL_X - 1
    if panel_w < AGENT_PANEL_MIN_W:
        return  # Terminal too narrow

    px = AGENT_PANEL_X
    p = gs.player

    # Draw vertical separator
    for row in range(min(term_h - 1, SCREEN_H)):
        safe_addstr(scr, row, px - 1, "|", curses.color_pair(C_DARK))

    y = 0

    # --- Header ---
    header = " CLAUDE AGENT "
    pad = (panel_w - len(header)) // 2
    safe_addstr(scr, y, px, " " * panel_w, curses.color_pair(C_MAGENTA))
    safe_addstr(scr, y, px + max(0, pad), header,
               curses.color_pair(C_MAGENTA) | curses.A_BOLD)
    y += 1

    # --- Stats row ---
    avg_lat = agent.total_latency / agent.claude_calls if agent.claude_calls > 0 else 0
    safe_addstr(scr, y, px, f"Calls:{agent.claude_calls:<4} Avg:{avg_lat:.1f}s "
               f"Falls:{agent.fallbacks} Err:{getattr(agent, '_error_count', 0)}",
               curses.color_pair(C_CYAN))
    y += 1

    # --- Current strategy ---
    safe_addstr(scr, y, px, f"Mode: {agent.strategy:<10} Floor {p.floor}/{MAX_FLOORS}  "
               f"Turn {gs.turn_count}",
               curses.color_pair(C_YELLOW))
    y += 1

    # --- HP bar ---
    hp_pct = p.hp / p.max_hp if p.max_hp > 0 else 0
    bar_w = min(20, panel_w - 16)
    filled = int(hp_pct * bar_w)
    hp_bar = "#" * filled + "-" * (bar_w - filled)
    hp_cp = C_GREEN if hp_pct > 0.6 else (C_YELLOW if hp_pct > 0.3 else C_RED)
    safe_addstr(scr, y, px, f"HP [{hp_bar}] {p.hp}/{p.max_hp}",
               curses.color_pair(hp_cp))
    y += 1

    # --- Hunger bar ---
    hunger_pct = p.hunger / 100.0
    hfilled = int(hunger_pct * bar_w)
    hunger_bar = "#" * hfilled + "-" * (bar_w - hfilled)
    hg_cp = C_GREEN if p.hunger > 50 else (C_YELLOW if p.hunger > 20 else C_RED)
    safe_addstr(scr, y, px, f"HG [{hunger_bar}] {p.hunger:.0f}%",
               curses.color_pair(hg_cp))
    y += 1

    # --- Calls/turn ratio (live health indicator) ---
    cpt = agent.claude_calls / gs.turn_count if gs.turn_count > 0 else 0
    cpt_cp = C_GREEN if cpt <= 0.3 else (C_YELLOW if cpt <= 0.5 else C_RED)
    safe_addstr(scr, y, px, f"C/T: {cpt:.2f}  ", curses.color_pair(cpt_cp))
    fb_rate = agent.fallbacks / agent.claude_calls if agent.claude_calls > 0 else 0
    fb_cp = C_GREEN if fb_rate <= 0.1 else (C_YELLOW if fb_rate <= 0.25 else C_RED)
    safe_addstr(scr, y, px + 10, f"FB: {fb_rate:.0%}", curses.color_pair(fb_cp))
    y += 1

    # --- Health warnings (most recent) ---
    if agent._health_warnings:
        recent = agent._health_warnings[-min(2, len(agent._health_warnings)):]
        for warn in recent:
            if y >= term_h - 3:
                break
            safe_addstr(scr, y, px, warn[:panel_w], curses.color_pair(C_RED))
            y += 1

    # --- Separator ---
    safe_addstr(scr, y, px, "-" * panel_w, curses.color_pair(C_DARK))
    y += 1

    # --- Decision log header ---
    safe_addstr(scr, y, px, "DECISION LOG", curses.color_pair(C_CYAN) | curses.A_BOLD)
    y += 1

    # --- Decision entries (newest first, fill remaining space) ---
    max_rows = min(len(decision_log), term_h - y - 2)
    entries = list(decision_log)[-max_rows:] if max_rows > 0 else []
    for i, entry in enumerate(reversed(entries)):
        if y >= term_h - 1:
            break
        action = entry.get("action", "?")
        if action is None:
            action = "ERR"
        latency = entry.get("latency", 0)
        reason = entry.get("reason", "")

        # First line: action + latency
        lat_cp = C_GREEN if latency < 3 else (C_YELLOW if latency < 8 else C_RED)
        action_str = f"{action[:18]:<18}"
        safe_addstr(scr, y, px, action_str,
                   curses.color_pair(C_MAGENTA) | (curses.A_BOLD if i == 0 else 0))
        safe_addstr(scr, y, px + 19, f"{latency:.1f}s", curses.color_pair(lat_cp))
        y += 1

        # Second line: reason (wrapped if needed)
        if reason and y < term_h - 1:
            reason_w = panel_w - 2
            reason_display = reason[:reason_w]
            safe_addstr(scr, y, px + 1, reason_display,
                       curses.color_pair(C_WHITE) if i == 0 else curses.color_pair(C_DARK))
            y += 1

    # --- Footer ---
    if term_h > 1:
        safe_addstr(scr, term_h - 1, px, "[q]uit [space]pause [+/-]speed [t]panel [P]ilot",
                   curses.color_pair(C_DARK))


_PILOT_MOVE_KEYS = {
    curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
    curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
    ord('w'): (0,-1), ord('s'): (0,1),
    ord('a'): (-1,0), ord('d'): (1,0),
    ord('h'): (-1,0), ord('j'): (0,1),
    ord('k'): (0,-1), ord('l'): (1,0),
    ord('y'): (-1,-1), ord('u'): (1,-1),
    ord('b'): (-1,1), ord('n'): (1,1),
}

def _pilot_process_key(gs, scr, key):
    """Process a single keypress during pilot mode. Returns True if turn was spent."""
    p = gs.player
    if key in _PILOT_MOVE_KEYS:
        dx, dy = _PILOT_MOVE_KEYS[key]
        return player_move(gs, dx, dy)
    elif key == ord('>'):
        if p.floor == MAX_FLOORS:
            boss_alive = any(e.boss and e.etype == "dread_lord" and e.is_alive() for e in gs.enemies)
            if boss_alive:
                gs.msg("The Dread Lord still lives!", C_RED)
            else:
                gs.victory = True
                gs.game_over = True
            return False
        if gs.tiles[p.y][p.x] == T_STAIRS_DOWN:
            new_floor = p.floor + 1
            if new_floor in BRANCH_CHOICES and new_floor not in gs.branch_choices:
                _get_game()._show_branch_choice(scr, gs, new_floor)
            gs.msg(f"Descending to floor {new_floor}...", C_YELLOW)
            gs.generate_floor(new_floor)
            return True
        gs.msg("No stairs here.", C_WHITE)
        return False
    elif key == ord('.') or key == ord('5'):
        return True  # Rest/wait
    elif key == ord(',') or key == ord('g'):
        # Pickup items at player position
        items_here = [i for i in gs.items if i.x == p.x and i.y == p.y]
        for it in items_here:
            if it.item_type == "gold":
                p.gold += it.count
                gs.msg(f"Picked up {it.count} gold.", C_GOLD)
                gs.items.remove(it)
            elif len(p.inventory) < p.carry_capacity or it.item_type == "scroll":
                p.inventory.append(it)
                gs.msg(f"Picked up {it.display_name}.", C_WHITE)
                gs.items.remove(it)
            else:
                gs.msg("Inventory full!", C_RED)
        return False
    elif key == ord('e'):
        # Use first potion in inventory
        potions = [i for i in p.inventory if i.item_type == "potion" and not i.equipped]
        if potions:
            use_potion(gs, potions[0])
            return True
        gs.msg("No potions.", C_WHITE)
        return False
    elif key == ord('E'):
        # Eat food
        food = [i for i in p.inventory if i.item_type == "food" and not i.equipped]
        if food:
            p.hunger = min(100.0, p.hunger + B["food_restore"])
            p.inventory.remove(food[0])
            gs.msg("You eat some food.", C_GREEN)
            return True
        gs.msg("No food.", C_WHITE)
        return False
    elif key == ord('f'):
        fire_projectile(gs, scr)
        return True
    elif key == ord('z'):
        cast_spell_menu(gs, scr)
        return False
    elif key == ord('p'):
        pray_at_shrine(gs)
        return True
    elif key == ord('i'):
        show_inventory(scr, gs)
        return False
    elif key == ord('/'):
        _search_for_traps(gs)
        return True
    elif key == ord('D'):
        _disarm_trap(gs)
        return True
    elif key == ord('T'):
        p.torch_lit = not p.torch_lit
        gs.msg(f"Torch {'lit' if p.torch_lit else 'extinguished'}.", C_YELLOW)
        return False
    elif key == ord('M'):
        show_bestiary(scr, gs)
        return False
    return False


def agent_game_loop(scr, speed=0.15, max_turns=10000):
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
    decision_log = deque(maxlen=50)  # Rolling log of Claude decisions
    pilot_mode = False  # Player takes manual control when True

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


def agent_batch_mode(num_games=10, player_class=None):
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

    results = []
    total_claude_calls = 0
    total_claude_latency = 0.0
    total_fallbacks = 0
    batch_tracker = FeatureTracker()

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


def _bot_execute_action(gs, action, params):
    """Execute a bot action on the game state. Returns True if turn was spent."""
    p = gs.player
    if action == "move":
        return player_move(gs, params["dx"], params["dy"])
    elif action == "rest":
        if p.hp < p.max_hp and p.hunger > B["rest_hunger_threshold"]:
            p.hp = min(p.max_hp, p.hp + B["rest_hp_per_turn"])
        p.hunger = max(0, p.hunger - B["rest_wait_hunger_cost"])
        return True
    elif action == "use_item":
        item = params["item"]
        if params["type"] == "potion":
            use_potion(gs, item)
        elif params["type"] == "food":
            use_food(gs, item)
        return True
    elif action == "cast_spell":
        spell = params["spell"]
        if spell == "Heal":
            cast_spell_headless(gs, "Heal")
        elif spell == "Fireball":
            cast_spell_headless(gs, "Fireball", direction=(params.get("dx", 0), params.get("dy", 0)))
        elif spell == "Freeze":
            cast_spell_headless(gs, "Freeze", target_enemy=params.get("target"))
        elif spell == "Lightning Bolt":
            cast_spell_headless(gs, "Lightning Bolt", direction=(params.get("dx", 0), params.get("dy", 0)))
        elif spell == "Chain Lightning":
            cast_spell_headless(gs, "Chain Lightning", target_enemy=params.get("target"))
        elif spell == "Meteor":
            cast_spell_headless(gs, "Meteor", direction=(params.get("dx", 0), params.get("dy", 0)))
        elif spell == "Mana Shield":
            cast_spell_headless(gs, "Mana Shield")
        elif spell == "Teleport":
            cast_spell_headless(gs, "Teleport")
        return True
    elif action == "fire":
        return fire_projectile_headless(gs, params["dx"], params["dy"])
    elif action == "descend":
        if p.floor < MAX_FLOORS:
            new_floor = p.floor + 1
            if new_floor in BRANCH_CHOICES and new_floor not in gs.branch_choices:
                _get_game()._choose_branch_headless(gs, new_floor)
            gs.generate_floor(new_floor)
            return True
        elif p.floor == MAX_FLOORS:
            if not any(e.boss and e.etype == "dread_lord" and e.is_alive() for e in gs.enemies):
                gs.victory = True
                gs.game_over = True
                return True
        return False
    elif action == "pickup":
        pickup = [i for i in gs.items if i.x == p.x and i.y == p.y]
        for item in pickup:
            if item.item_type == "gold":
                p.gold += item.data["amount"]
                gs.items.remove(item)
            elif len(p.inventory) < p.carry_capacity:
                gs.items.remove(item)
                p.inventory.append(item)
                p.items_found += 1
        return bool(pickup)
    elif action == "pray":
        pray_at_shrine(gs)
        return True
    elif action == "equip":
        item = params["item"]
        if item.item_type == "weapon":
            if p.weapon:
                p.weapon.equipped = False
            item.equipped = True
            p.weapon = item
        elif item.item_type == "armor":
            if p.armor:
                p.armor.equipped = False
            item.equipped = True
            p.armor = item
        elif item.item_type == "ring":
            if p.ring:
                p.ring.equipped = False
            item.equipped = True
            p.ring = item
        elif item.item_type == "bow":
            if p.bow:
                p.bow.equipped = False
            item.equipped = True
            p.bow = item
        return False  # Equipping doesn't spend a turn
    elif action == "toggle_torch":
        p.torch_lit = not p.torch_lit
        return False
    elif action == "use_ability":
        return use_ability_headless(gs, params["ability"])
    elif action == "use_alchemy":
        return use_alchemy_table(gs)
    elif action == "interact_pedestal":
        return _interact_pedestal(gs, p.x, p.y)
    elif action == "grab_wall_torch":
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            tx, ty = p.x + ddx, p.y + ddy
            if 0 <= tx < MAP_W and 0 <= ty < MAP_H and gs.tiles[ty][tx] == T_WALL_TORCH:
                gs.tiles[ty][tx] = T_WALL
                if (tx, ty) in gs.wall_torches:
                    gs.wall_torches.remove((tx, ty))
                torch_item = Item(0, 0, "torch", "Torch",
                                {"name": "Torch", "char": '(', "fuel": 60, "desc": "Taken from wall."})
                p.inventory.append(torch_item)
                gs.msg("You take a torch from the wall.", C_YELLOW)
                return True
        return False
    return False


def bot_game_loop(scr, speed=0.08, max_turns=5000):
    """Run a bot-controlled game visually in the terminal."""
    curses.curs_set(0)
    scr.nodelay(False)
    scr.keypad(True)
    init_colors()

    gs = _get_game().GameState(player_class="warrior")
    gs._scr = scr
    _get_game()._init_new_game(gs)
    bot = BotPlayer()
    show_telemetry = True
    paused = False
    delay_ms = max(10, int(speed * 1000))

    while gs.running and not gs.game_over and gs.turn_count < max_turns:
        fov_radius = gs.player.get_torch_radius()
        if "Blindness" in gs.player.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        _update_explored_from_fov(gs)

        # Auto-apply pending level-ups
        while gs.player.pending_levelups:
            auto_apply_levelup(gs.player)

        action, params = bot.decide(gs)
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

        # Telemetry overlay
        if show_telemetry:
            p = gs.player
            hp_pct = int(p.hp / p.max_hp * 100) if p.max_hp > 0 else 0
            tlines = [
                "BOT TELEMETRY",
                f"Turn: {gs.turn_count:<6} Speed: {1000/max(1,delay_ms):.0f} fps",
                f"Strategy: {bot.strategy:<10} Target: {bot.target_desc[:14]}",
                f"HP: {p.hp}/{p.max_hp} ({hp_pct}%) Hunger: {p.hunger:.0f}%",
                f"Floor: {p.floor}  Kills: {p.kills}  Lv: {p.level}",
                f"Gold: {p.gold}  Items: {len(p.inventory)}/{p.carry_capacity}",
                "[t]elemetry [+/-]speed [space]pause [q]uit",
            ]
            for i, line in enumerate(tlines):
                safe_addstr(scr, i, SCREEN_W - len(line) - 1, line,
                           curses.color_pair(C_CYAN) if i > 0 else
                           curses.color_pair(C_CYAN) | curses.A_BOLD)
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
            delay_ms = min(1000, delay_ms * 2)
        elif ck == ord('t'):
            show_telemetry = not show_telemetry

        curses.napms(delay_ms)

    # Show final screen
    render_game(scr, gs)
    if gs.victory:
        show_enhanced_victory(scr, gs)
    elif gs.game_over:
        show_enhanced_death(scr, gs)
    else:
        safe_addstr(scr, SCREEN_H // 2, 10, f"Bot stopped at turn {gs.turn_count}",
                   curses.color_pair(C_YELLOW) | curses.A_BOLD)
        scr.refresh()
        scr.nodelay(False)
        scr.getch()


def bot_batch_mode(num_games=10, player_class=None):
    """Run multiple bot games headless and print summary stats.

    Args:
        num_games: Number of games to play.
        player_class: Force a class ("warrior"/"mage"/"rogue") or None for rotation.
    """
    CLASSES = ["warrior", "mage", "rogue"]
    results = []
    crashes = []
    for i in range(num_games):
        game_class = player_class or CLASSES[i % len(CLASSES)]
        try:
            gs = _get_game().GameState(headless=True, player_class=game_class)
            _get_game()._init_new_game(gs)
            bot = BotPlayer()
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

                action, params = bot.decide(gs)
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

            p = gs.player
            result = {
                "game": i + 1,
                "class": game_class,
                "victory": gs.victory,
                "floor": p.floor,
                "level": p.level,
                "kills": p.kills,
                "turns": gs.turn_count,
                "score": calculate_score(p, gs),
                "death_cause": gs.death_cause or ("victory" if gs.victory else "timeout"),
                "locked_stairs": gs.tiles[gs.stair_down[1]][gs.stair_down[0]] == T_STAIRS_LOCKED,
                "puzzles": len(gs.puzzles),
                "puzzles_solved": sum(1 for pz in gs.puzzles if pz["solved"]),
            }
            results.append(result)
            cls_tag = game_class[0].upper()
            status = "WIN!" if gs.victory else f"Died F{p.floor}"
            flags = ""
            if result["locked_stairs"]:
                flags += " [LOCKED]"
            print(f"  Game {i+1:3d}: [{cls_tag}] {status:<12} Lv{p.level} T{gs.turn_count:5d} K{p.kills:3d} Score:{calculate_score(p, gs)}{flags}")

        except Exception as exc:
            import traceback
            crash = {
                "game": i + 1,
                "class": game_class,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            crashes.append(crash)
            print(f"  Game {i+1:3d}: [{game_class[0].upper()}] CRASH: {exc}")

    # Summary
    print("\n" + "=" * 50)
    print("BOT BATCH SUMMARY")
    print("=" * 50)
    if results:
        wins = sum(1 for r in results if r["victory"])
        avg_floor = sum(r["floor"] for r in results) / len(results)
        avg_kills = sum(r["kills"] for r in results) / len(results)
        avg_turns = sum(r["turns"] for r in results) / len(results)
        avg_score = sum(r["score"] for r in results) / len(results)
        max_floor = max(r["floor"] for r in results)
        timeout_count = sum(1 for r in results if r["death_cause"] == "timeout")
        locked_count = sum(1 for r in results if r.get("locked_stairs"))
        print(f"  Games: {num_games}  Wins: {wins}  Win rate: {wins/len(results)*100:.0f}%")
        print(f"  Avg floor: {avg_floor:.1f}  Max floor: {max_floor}  Avg kills: {avg_kills:.1f}")
        print(f"  Avg turns: {avg_turns:.0f}  Avg score: {avg_score:.0f}")
        print(f"  Timeouts: {timeout_count}  Locked stairs encounters: {locked_count}")
        # Per-class breakdown
        for cls in CLASSES:
            cls_results = [r for r in results if r["class"] == cls]
            if cls_results:
                cls_avg_floor = sum(r["floor"] for r in cls_results) / len(cls_results)
                cls_avg_kills = sum(r["kills"] for r in cls_results) / len(cls_results)
                print(f"    {cls.capitalize():8s}: {len(cls_results)} games, avg F{cls_avg_floor:.1f}, avg K{cls_avg_kills:.0f}")
        # Death causes
        causes = {}
        for r in results:
            c = r["death_cause"]
            causes[c] = causes.get(c, 0) + 1
        print(f"  Death causes: {causes}")
    if crashes:
        print(f"  CRASHES: {len(crashes)}")
        for c in crashes:
            print(f"    Game {c['game']} [{c['class']}]: {c['error']}")
    return results

