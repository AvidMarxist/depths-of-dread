"""
Bot module for Depths of Dread.

Contains BotPlayer (decision-tree AI) and bot game loop functions.
"""
from __future__ import annotations

import curses
import json
import os
import random
import sys
import time
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .entities import Enemy, Item, Player
    from .game import GameState

from .combat import *
from .combat import (
    _award_kill,
    _bestiary_record,
    _chase_move,
    _check_levelups,
    _check_traps_on_move,
    _compute_noise,
    _disarm_trap,
    _flee_move,
    _passive_trap_detect,
    _search_for_traps,
    _stealth_detection,
    _trigger_trap,
    _try_enemy_move,
    _update_boss_phase,
)
from .constants import *
from .constants import _CHALLENGE_MODES, _DIR_MAP
from .entities import *
from .entities import _unlock_next_ability, _unlock_next_spell
from .items import *
from .items import (
    _animate_projectile,
    _apply_spell_resist,
    _cast_spell,
    _execute_ability,
    _get_direction_delta,
    _interact_npc,
    _interact_pedestal,
    _journal_potion_desc,
    _journal_scroll_desc,
    _launch_projectile,
    _process_branch_effects,
    _toggle_switch,
)
from .mapgen import *
from .mapgen import _has_los, astar, compute_fov
from .persistence import *
from .persistence import (
    _compute_checksum,
    _default_lifetime_stats,
    _deserialize_enemy,
    _deserialize_item,
    _deserialize_item_ground,
    _format_lifetime_stats_lines,
    _serialize_enemy,
    _serialize_item,
    _serialize_item_on_ground,
)
from .ui import *
from .ui import _bfs_unexplored, _describe_tile, _draw_tile, _inv_key_to_idx, _inv_letter


def _get_game() -> Any:
    from . import game
    return game

# BOT PLAYER (AI Auto-Play)
# ============================================================

class BotPlayer:
    """AI bot that plays the game using a priority-based decision tree."""

    def __init__(self) -> None:
        self.strategy: str = "INIT"
        self.target_desc: str = ""
        self.items_used: int = 0
        self.potions_saved: int = 0
        self.decisions: int = 0
        self._explore_target: tuple[int, int] | None = None  # Committed exploration target (x, y)
        self._explore_stuck: int = 0      # Counter for detecting oscillation
        self._last_positions: list[tuple[int, int]] = []     # Recent positions for loop detection
        self._floor_tiles_visited: set[tuple[int, int]] = set()  # Unique tiles visited on current floor
        self._floor_start_turn: int = 0         # Turn when we entered this floor
        self._current_floor: int = 0            # Track floor for reset

    def decide(self, gs: GameState) -> tuple[str, dict[str, Any]]:
        """Returns (action, params) tuple. Deterministic given same state."""
        self.decisions += 1
        p = gs.player

        # Status effect overrides (can't use normal decision tree)
        if "Paralysis" in p.status_effects:
            self.strategy = "PARALYZED"
            self.target_desc = "can't move"
            return ("rest", {})
        if "Fear" in p.status_effects:
            flee_dir = self._flee_direction(gs)
            if flee_dir:
                self.strategy = "FEARED"
                self.target_desc = "fleeing in terror"
                return ("move", {"dx": flee_dir[0], "dy": flee_dir[1]})
            self.strategy = "FEARED"
            self.target_desc = "cowering"
            return ("rest", {})
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

        # Priority layers — first non-None result wins
        for layer in (self._decide_survival, self._decide_combat,
                      self._decide_exploration, self._decide_resources):
            result = layer(gs)
            if result is not None:
                return result

        # Fallback: wait
        self.strategy = "WAIT"
        self.target_desc = "waiting"
        return ("rest", {})

    # ------------------------------------------------------------------
    # Layer 1: Survival
    # ------------------------------------------------------------------

    def _decide_survival(self, gs: GameState) -> tuple[str, dict[str, Any]] | None:
        """Heal, eat, equip, flee — staying alive is priority one."""
        p = gs.player
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
            if p.mana >= SPELLS["Heal"]["cost"]:
                self.strategy = "HEAL"
                self.target_desc = "spell"
                return ("cast_spell", {"spell": "Heal"})
            if hunger_pct < 60:
                for item in p.inventory:
                    if item.item_type == "food":
                        self.strategy = "HEAL"
                        self.target_desc = "food"
                        return ("use_item", {"item": item, "type": "food"})
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

        return None

    # ------------------------------------------------------------------
    # Layer 2: Combat
    # ------------------------------------------------------------------

    def _decide_combat(self, gs: GameState) -> tuple[str, dict[str, Any]] | None:
        """Engage visible enemies with class abilities, ranged, spells, or melee."""
        p = gs.player
        nearest_enemy = self._nearest_visible_enemy(gs)
        if not nearest_enemy:
            return None

        hp_pct = p.hp / p.max_hp if p.max_hp > 0 else 0
        dist = abs(nearest_enemy.x - p.x) + abs(nearest_enemy.y - p.y)

        # Class abilities
        result = self._try_warrior_abilities(gs, nearest_enemy, hp_pct)
        if result:
            return result
        result = self._try_rogue_abilities(gs, nearest_enemy, hp_pct)
        if result:
            return result

        # Ranged attack if enemy > 2 tiles away
        if dist > 2:
            result = self._try_ranged_attack(gs, nearest_enemy)
            if result:
                return result

        # Offensive spells
        result = self._try_spell_attack(gs, nearest_enemy)
        if result:
            return result

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

        return None

    def _try_warrior_abilities(self, gs: GameState, nearest_enemy: Enemy,
                               hp_pct: float) -> tuple[str, dict[str, Any]] | None:
        """Whirlwind on groups, Shield Wall when desperate."""
        p = gs.player
        if p.player_class != "warrior":
            return None

        # Whirlwind when 3+ adjacent enemies
        if "Whirlwind" in p.known_abilities and p.mana >= B["whirlwind_cost"]:
            adj_count = sum(1 for e in gs.enemies
                           if e.is_alive() and abs(e.x - p.x) <= 1 and abs(e.y - p.y) <= 1
                           and (e.x != p.x or e.y != p.y))
            if adj_count >= 3:
                self.strategy = "COMBAT"
                self.target_desc = f"whirlwind ({adj_count} adjacent)"
                return ("use_ability", {"ability": "Whirlwind"})

        # Shield Wall when HP < 30% and no heal available
        if ("Shield Wall" in p.known_abilities and p.mana >= B["shield_wall_cost"]
                and "Shield Wall" not in p.status_effects and hp_pct < 0.3):
            has_heal = any(it.item_type == "potion" and it.identified and it.data.get("effect") == "Healing"
                          for it in p.inventory)
            if not has_heal:
                self.strategy = "COMBAT"
                self.target_desc = "shield wall (low HP)"
                return ("use_ability", {"ability": "Shield Wall"})

        return None

    def _try_rogue_abilities(self, gs: GameState, nearest_enemy: Enemy,
                             hp_pct: float) -> tuple[str, dict[str, Any]] | None:
        """Backstab bosses, Smoke Bomb when outnumbered and hurt."""
        p = gs.player
        if p.player_class != "rogue":
            return None

        # Backstab before engaging bosses
        if ("Backstab" in p.known_abilities and p.mana >= B["backstab_cost"]
                and nearest_enemy.boss and "Backstab" not in p.status_effects):
            self.strategy = "COMBAT"
            self.target_desc = f"backstab -> {nearest_enemy.name}"
            return ("use_ability", {"ability": "Backstab"})

        # Smoke Bomb when HP < 30% and 2+ enemies visible
        if ("Smoke Bomb" in p.known_abilities and p.mana >= B["smoke_bomb_cost"]
                and hp_pct < 0.3):
            visible_count = sum(1 for e in gs.enemies
                               if e.is_alive() and (e.x, e.y) in gs.visible)
            if visible_count >= 2:
                self.strategy = "COMBAT"
                self.target_desc = f"smoke bomb ({visible_count} visible)"
                return ("use_ability", {"ability": "Smoke Bomb"})

        return None

    def _try_ranged_attack(self, gs: GameState,
                           nearest_enemy: Enemy) -> tuple[str, dict[str, Any]] | None:
        """Fire wand or bow at distant enemies."""
        p = gs.player

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

        return None

    def _try_spell_attack(self, gs: GameState,
                          nearest_enemy: Enemy) -> tuple[str, dict[str, Any]] | None:
        """Chain Lightning, Fireball on groups; Freeze on bosses."""
        p = gs.player

        # Mage: Chain Lightning on 2+ visible enemies
        if (p.player_class == "mage" and "Chain Lightning" in p.known_spells
                and p.mana >= SPELLS["Chain Lightning"]["cost"] and p.mana > p.max_mana * 0.5):
            visible_enemies = sum(1 for e in gs.enemies
                                 if e.is_alive() and (e.x, e.y) in gs.visible)
            if visible_enemies >= 2:
                self.strategy = "COMBAT"
                self.target_desc = f"chain lightning ({visible_enemies} visible)"
                return ("cast_spell", {"spell": "Chain Lightning", "target": nearest_enemy})

        # Fireball on 2+ clustered enemies
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

        # Freeze on bosses
        if ("Freeze" in p.known_spells and nearest_enemy.boss
                and p.mana >= SPELLS["Freeze"]["cost"] and nearest_enemy.frozen_turns <= 0):
            self.strategy = "COMBAT"
            self.target_desc = f"freeze -> {nearest_enemy.name}"
            return ("cast_spell", {"spell": "Freeze", "target": nearest_enemy})

        return None

    # ------------------------------------------------------------------
    # Layer 3: Exploration
    # ------------------------------------------------------------------

    def _decide_exploration(self, gs: GameState) -> tuple[str, dict[str, Any]] | None:
        """Pickup items, pray, descend, auto-explore, unstick."""
        p = gs.player
        hp_pct = p.hp / p.max_hp if p.max_hp > 0 else 0

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
            for ddx, ddy in [(dx, dy), (dx, 0), (0, dy), (-dx, 0), (0, -dy)]:
                if ddx == 0 and ddy == 0:
                    continue
                nx, ny = p.x + ddx, p.y + ddy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
                    self.strategy = "FORCE_MOVE"
                    self.target_desc = "stall break, toward stairs"
                    return ("move", {"dx": ddx, "dy": ddy})

        return None

    # ------------------------------------------------------------------
    # Layer 4: Resource Management
    # ------------------------------------------------------------------

    def _decide_resources(self, gs: GameState) -> tuple[str, dict[str, Any]] | None:
        """Toggle torch to conserve fuel or light up for combat."""
        p = gs.player
        if p.torch_lit and not self._enemies_visible(gs) and p.torch_fuel < TORCH_MAX_FUEL * 0.25:
            self.strategy = "MANAGE"
            self.target_desc = "conserve torch"
            return ("toggle_torch", {})
        if not p.torch_lit and self._enemies_visible(gs) and p.torch_fuel > 0:
            self.strategy = "MANAGE"
            self.target_desc = "light torch"
            return ("toggle_torch", {})
        return None

    def _enemies_visible(self, gs: GameState) -> bool:
        return any(e.is_alive() and (e.x, e.y) in gs.visible and not e.disguised for e in gs.enemies)

    def _nearest_visible_enemy(self, gs: GameState) -> Enemy | None:
        p = gs.player
        nearest: Enemy | None = None
        nd: int = 999
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                d = abs(e.x - p.x) + abs(e.y - p.y)
                if d < nd:
                    nd = d
                    nearest = e
        return nearest

    def _flee_direction(self, gs: GameState) -> tuple[int, int] | None:
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

    def _check_equipment_upgrade(self, gs: GameState) -> tuple[str, dict[str, Any]] | None:
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

    def _floor_explored_pct(self, gs: GameState) -> float:
        explored = sum(1 for row in gs.explored for c in row if c)
        total = count_walkable(gs.tiles)
        return explored / total if total > 0 else 1.0


def _update_explored_from_fov(gs: GameState) -> None:
    """Mark all visible tiles as explored (needed for headless/bot mode)."""
    for (mx, my) in gs.visible:
        if 0 <= mx < MAP_W and 0 <= my < MAP_H:
            gs.explored[my][mx] = True


def _bot_execute_action(gs: GameState, action: str, params: dict[str, Any]) -> bool:
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


def bot_game_loop(scr: Any, speed: float = 0.08, max_turns: int = 5000) -> None:
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


def bot_batch_mode(num_games: int = 10, player_class: str | None = None) -> list[dict[str, Any]]:
    """Run multiple bot games headless and print summary stats.

    Args:
        num_games: Number of games to play.
        player_class: Force a class ("warrior"/"mage"/"rogue") or None for rotation.
    """
    CLASSES: list[str] = ["warrior", "mage", "rogue"]
    results: list[dict[str, Any]] = []
    crashes: list[dict[str, Any]] = []
    for i in range(num_games):
        game_class: str = player_class or CLASSES[i % len(CLASSES)]
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
