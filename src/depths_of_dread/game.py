#!/usr/bin/env python3
"""
DEPTHS OF DREAD - A Terminal Roguelike
======================================
Fifteen floors of darkness beneath Thornhaven.
Slay the Dread Lord or die trying.

Built for someone who grew up on NetHack, Rogue, and BBS door games.
Pure Python curses. No external dependencies.

Controls: WASD / Arrows / hjklyubn (vi keys)
  f: Fire projectile (then direction)
  z: Cast spell
"""

import curses
import random
# math — available if needed but not currently used
import time
import sys
import heapq
import json
import hashlib
import os
from pathlib import Path
from collections import deque
import argparse
import datetime
import subprocess
# threading — available if needed but not currently used

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
from .mapgen import _has_los, _cast_light, _carve_room_shape, _carve_corridor, _add_cave_features, _generate_fallback, _MULT
from .combat import *
from .combat import (_bestiary_record, _award_kill, _check_levelups, _trigger_trap,
                     _check_traps_on_move, _passive_trap_detect, _search_for_traps,
                     _disarm_trap, _compute_noise, _stealth_detection, _update_boss_phase,
                     _try_enemy_move, _flee_move, _chase_move, _erratic_move, _patrol_move,
                     _pack_move, _ambush_move, _ranged_move, _summoner_move, _mimic_move,
                     _phase_move, _mind_flayer_move)
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
from .bot import *
from .bot import (BotPlayer, FeatureTracker, AgentPlayer,
                  bot_game_loop, agent_game_loop, bot_batch_mode, agent_batch_mode,
                  _bot_execute_action, _update_explored_from_fov)


# ============================================================
# GAME STATE
# ============================================================

class GameState:
    def __init__(self, headless=False, seed=None, player_class=None, difficulty="normal"):
        self.seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        random.seed(self.seed)
        self.difficulty = difficulty
        self.difficulty_mods = DIFFICULTY_PRESETS.get(difficulty, DIFFICULTY_PRESETS["normal"])
        self.player = Player(player_class=player_class)
        self.tiles = None
        self.rooms = None
        self.enemies = []
        self.items = []
        self.shops = []
        self.messages = deque(maxlen=MAX_MESSAGES)
        self.visible = set()
        self.explored = [[False]*MAP_W for _ in range(MAP_H)]
        self.stair_down = (0, 0)
        self.running = True
        self.game_over = False
        self.victory = False
        self.turn_count = 0
        self.start_time = time.time()
        self._headless = headless
        self._scr = None  # set during game_loop for projectile animation
        self.death_cause = None
        self.recorder = None  # SessionRecorder, set during game init
        self.floors_explored = set()  # track unique floors visited
        # First-encounter tips tracking (Phase 5, item 25)
        self.tips_shown = set()
        # First melee attack tracking (Phase 3, item 14)
        self.first_melee_done = False
        # Shop discovery flag — message fires when FOV first sees shop tile (#10)
        self.shop_discovered = False
        # Journal — tracks identified item effects (#6)
        self.journal = {}
        # Alchemy tables used on this floor (#7)
        self.alchemy_used = set()
        # Puzzles on current floor (#9)
        self.puzzles = []
        # Wall torches on current floor (#1)
        self.wall_torches = []
        # Environmental vignettes on current floor
        self.vignettes = []
        # NPC encounters on current floor
        self.npcs = []
        # Traps on current floor
        self.traps = []
        # Stealth system: noise generated this turn
        self.last_noise = 0
        # Dungeon branch system
        self.branch_choices = {}  # {floor_num: "branch_key"}
        self.active_branch = None  # Current branch key or None
        # Monster Memory / Bestiary
        self.bestiary = {}  # {etype: {"encountered": N, "killed": N, "dmg_dealt": N, "dmg_taken": N, "abilities": set()}}
        # Auto-fight / auto-explore state
        self.auto_fighting = False
        # Challenge modes (Phase 4)
        self.challenge_ironman = False
        self.challenge_speedrun = False
        self.challenge_pacifist = False
        self.challenge_dark = False
        self.speedrun_timer = 0  # Turns per floor limit
        self.auto_exploring = False
        self.auto_fight_target = None
        # Shuffle potion/scroll identities per game
        self.potion_ids = {}
        self.scroll_ids = {}
        self.id_potions = set()
        self.id_scrolls = set()
        colors = list(POTION_COLORS)
        random.shuffle(colors)
        for i, eff in enumerate(POTION_EFFECTS):
            self.potion_ids[eff] = colors[i]
        labels = list(SCROLL_LABELS)
        random.shuffle(labels)
        for i, eff in enumerate(SCROLL_EFFECTS):
            self.scroll_ids[eff] = labels[i]

    def msg(self, text, color=C_WHITE):
        self.messages.append((text, color))

    def _get_active_branch(self, floor_num):
        """Determine if the given floor is in a branch. Returns branch key or None."""
        for choice_floor, (branch_a, branch_b) in BRANCH_CHOICES.items():
            chosen = self.branch_choices.get(choice_floor)
            if chosen:
                bdef = BRANCH_DEFS[chosen]
                if floor_num in bdef["floors"]:
                    return chosen
        return None

    def _apply_branch_terrain(self, floor_num, branch_key):
        """Modify terrain tiles for a branch (more water/lava)."""
        bdef = BRANCH_DEFS[branch_key]
        # Replace some floor tiles with water or lava based on branch
        floor_tiles = [(x, y) for y in range(MAP_H) for x in range(MAP_W)
                       if self.tiles[y][x] == T_FLOOR]
        random.shuffle(floor_tiles)
        water_count = int(len(floor_tiles) * 0.03 * bdef.get("water_boost", 1.0))
        lava_count = int(len(floor_tiles) * 0.03 * bdef.get("lava_boost", 1.0))
        idx = 0
        for _ in range(water_count):
            if idx < len(floor_tiles):
                x, y = floor_tiles[idx]
                # Don't replace player position or stairs
                if (x, y) != (self.player.x, self.player.y) and (x, y) != self.stair_down:
                    self.tiles[y][x] = T_WATER
                idx += 1
        for _ in range(lava_count):
            if idx < len(floor_tiles):
                x, y = floor_tiles[idx]
                if (x, y) != (self.player.x, self.player.y) and (x, y) != self.stair_down:
                    self.tiles[y][x] = T_LAVA
                idx += 1

    def generate_floor(self, floor_num):
        self.player.floor = floor_num
        if floor_num > self.player.deepest_floor:
            self.player.deepest_floor = floor_num
        self.speedrun_timer = 0  # Reset speedrun timer per floor
        self.floors_explored.add(floor_num)
        self.tiles, self.rooms, start, self.stair_down = generate_dungeon(floor_num)
        self.player.x, self.player.y = start
        self.explored = [[False]*MAP_W for _ in range(MAP_H)]
        self.enemies = []
        self.items = []
        self.shops = []
        self.shop_discovered = False
        self.alchemy_used = set()
        self.puzzles = []
        self.wall_torches = []
        self.traps = []
        self.vignettes = []
        self.npcs = []
        # Determine active branch for this floor
        self.active_branch = self._get_active_branch(floor_num)
        # Apply branch-specific terrain modifications
        if self.active_branch:
            self._apply_branch_terrain(floor_num, self.active_branch)
        self._populate_enemies(floor_num)
        self._populate_items(floor_num)
        self._place_shop(floor_num)
        self._place_shrine(floor_num)
        self._place_alchemy_table(floor_num)
        self._place_wall_torches(floor_num)
        self._place_puzzle(floor_num)
        self._place_traps(floor_num)
        self._place_vignettes(floor_num)
        self._place_npcs(floor_num)
        self._place_enchant_anvil(floor_num)
        self._place_fountain(floor_num)
        self._place_secret_room(floor_num)
        # Branch-specific extra traps
        if self.active_branch:
            bdef = BRANCH_DEFS[self.active_branch]
            extra_traps = bdef.get("extra_traps", 0)
            for _ in range(extra_traps):
                self._place_single_trap(floor_num)
        # Determine theme
        if self.active_branch:
            theme = BRANCH_DEFS[self.active_branch]["theme"]
        else:
            theme = THEMES[floor_num-1] if floor_num <= len(THEMES) else "The Abyss"
        self.msg(f"--- Floor {floor_num}: {theme} ---", C_YELLOW)
        if self.active_branch:
            bdef = BRANCH_DEFS[self.active_branch]
            self.msg(f"You are in {bdef['name']}.", C_CYAN)
        if floor_num == MAX_FLOORS:
            self.msg("You feel an overwhelming dread...", C_RED)

    def _populate_enemies(self, floor_num):
        num = B["enemies_base"] + floor_num * B["enemies_per_floor"] + random.randint(0, B["enemies_random_bonus"])
        # Branch-specific enemy pool override
        if self.active_branch:
            bdef = BRANCH_DEFS[self.active_branch]
            eligible = [k for k in bdef["enemy_pool"] if k in ENEMY_TYPES and not ENEMY_TYPES[k].get("boss")]
            num += bdef.get("extra_enemies", 0)
        else:
            eligible = [k for k, v in ENEMY_TYPES.items()
                        if v["min_floor"] <= floor_num <= v.get("max_floor", 99) and not v.get("boss")]
        # Bosses: standard bosses spawn on their designated floors
        for etype, tmpl in ENEMY_TYPES.items():
            if tmpl.get("boss") and tmpl["min_floor"] == floor_num:
                # Skip branch mini-bosses unless on correct branch floor
                if etype in ("crypt_guardian", "flame_tyrant", "elder_brain", "beast_lord"):
                    continue  # These are handled separately below
                pos = self._find_spawn_pos()
                if pos:
                    self.enemies.append(Enemy(pos[0], pos[1], etype))
                    self.msg("A powerful presence lurks on this floor...", C_RED)
        # Branch mini-boss
        if self.active_branch:
            bdef = BRANCH_DEFS[self.active_branch]
            if floor_num == bdef.get("mini_boss_floor"):
                mini_boss = bdef["mini_boss"]
                pos = self._find_spawn_pos()
                if pos:
                    self.enemies.append(Enemy(pos[0], pos[1], mini_boss))
                    self.msg(f"The {ENEMY_TYPES[mini_boss]['name']} guards this place!", C_RED)
        # Apex enemies: rare powerful enemies on deep floors
        apex_types = [k for k, v in ENEMY_TYPES.items()
                      if v.get("apex") and v["min_floor"] <= floor_num <= v.get("max_floor", 99)]
        if apex_types and random.random() < B["apex_spawn_chance"]:
            apex_type = random.choice(apex_types)
            pos = self._find_spawn_pos()
            if pos:
                apex = Enemy(pos[0], pos[1], apex_type)
                apex.alertness = "unwary"
                self.enemies.append(apex)
                self.msg(f"You sense something ancient and terrible on this floor...", C_RED)
        for _ in range(num):
            if not eligible:
                break
            etype = random.choice(eligible)
            pos = self._find_spawn_pos()
            if pos:
                e = Enemy(pos[0], pos[1], etype)
                floors_above_min = floor_num - ENEMY_TYPES[etype]["min_floor"]
                scale = 1.0 + floors_above_min * B["enemy_hp_scale_per_floor"]
                hp_mult = self.difficulty_mods.get("enemy_hp_mult", 1.0)
                e.max_hp = int(e.max_hp * scale * hp_mult)
                e.hp = e.max_hp
                # Scale enemy damage and defense with floor depth
                dmg_scale = 1.0 + floors_above_min * B["enemy_dmg_scale_per_floor"]
                dmg_mult = self.difficulty_mods.get("enemy_dmg_mult", 1.0)
                e.dmg = (int(e.dmg[0] * dmg_scale * dmg_mult), max(int(e.dmg[1] * dmg_scale * dmg_mult), int(e.dmg[0] * dmg_scale * dmg_mult) + 1))
                e.defense = int(e.defense + floors_above_min * B["enemy_def_scale_per_floor"])
                # Stealth system: assign initial alertness
                e.alertness = "asleep" if random.random() < B["asleep_spawn_chance"] else "unwary"
                self.enemies.append(e)

    def _populate_items(self, floor_num):
        num = B["items_base"] + floor_num * B["items_per_floor"] + random.randint(0, B["items_random_bonus"])
        for _ in range(num):
            pos = self._find_spawn_pos()
            if pos:
                item = self._random_item(pos[0], pos[1], floor_num)
                if item:
                    self.items.append(item)
        # Guarantee food items per floor so starvation isn't RNG-dependent
        for _ in range(random.randint(B["guaranteed_food_min"], B["guaranteed_food_max"])):
            pos = self._find_spawn_pos()
            if pos:
                f = random.choice(FOOD_TYPES)
                self.items.append(Item(pos[0], pos[1], "food", f["name"], f))
        for _ in range(random.randint(B["gold_piles_min"], B["gold_piles_max"])):
            pos = self._find_spawn_pos()
            if pos:
                amt = random.randint(B["gold_per_floor_min"], B["gold_per_floor_max"]) * min(floor_num, 5)
                self.items.append(Item(pos[0], pos[1], "gold", 0, {"amount": amt, "name": f"{amt} gold"}))

    def _random_item(self, x, y, floor_num):
        weights = B["item_weights"]
        types = list(weights.keys())
        probs = list(weights.values())
        item_type = random.choices(types, weights=probs, k=1)[0]

        if item_type == "weapon":
            eligible = [w for w in WEAPON_TYPES if w["tier"] <= (floor_num//3)+1]
            if eligible:
                w = random.choice(eligible)
                return Item(x, y, "weapon", WEAPON_TYPES.index(w), w)
        elif item_type == "armor":
            eligible = [a for a in ARMOR_TYPES if a["tier"] <= (floor_num//3)+1]
            if eligible:
                a = random.choice(eligible)
                return Item(x, y, "armor", ARMOR_TYPES.index(a), a)
        elif item_type == "potion":
            eff = random.choice(POTION_EFFECTS)
            return Item(x, y, "potion", eff,
                       {"effect": eff, "color_name": self.potion_ids[eff], "char": '!'})
        elif item_type == "scroll":
            eff = random.choice(SCROLL_EFFECTS)
            return Item(x, y, "scroll", eff,
                       {"effect": eff, "label": self.scroll_ids[eff], "char": '?'})
        elif item_type == "food":
            f = random.choice(FOOD_TYPES)
            return Item(x, y, "food", f["name"], f)
        elif item_type == "ring":
            eligible = [r for r in RING_TYPES if r.get("min_floor", 0) <= floor_num]
            r = random.choice(eligible) if eligible else random.choice(RING_TYPES[:5])
            return Item(x, y, "ring", r["name"], r)
        elif item_type == "bow":
            eligible = [b for b in BOW_TYPES if b["tier"] <= (floor_num//3)+1]
            if eligible:
                b = random.choice(eligible)
                return Item(x, y, "bow", b["name"], b)
            # Fallback to arrows
            it = Item(x, y, "arrow", "Arrow", dict(ARROW_ITEM))
            it.count = random.randint(3, 8)
            return it
        elif item_type == "arrow":
            it = Item(x, y, "arrow", "Arrow", dict(ARROW_ITEM))
            it.count = random.randint(3, 8)
            return it
        elif item_type == "throwing_dagger":
            it = Item(x, y, "throwing_dagger", "Throwing Dagger", dict(THROWING_DAGGER))
            it.count = random.randint(2, 5)
            return it
        elif item_type == "wand":
            eligible = [w for w in WAND_TYPES if w["tier"] <= (floor_num//3)+2]
            if eligible:
                w = random.choice(eligible)
                data = dict(w)
                return Item(x, y, "wand", w["name"], data)
        elif item_type == "torch":
            t = random.choice(TORCH_TYPES)
            return Item(x, y, "torch", t["name"], dict(t))

        # Fallback if nothing generated (e.g., no eligible weapons on early floors)
        f = random.choice(FOOD_TYPES)
        return Item(x, y, "food", f["name"], f)

    def _place_shop(self, floor_num):
        if floor_num % 2 == 0:  # Shops on odd floors: 1,3,5,7,9,11,13,15 (#19)
            return
        if len(self.rooms) < 3:
            return
        room = self.rooms[len(self.rooms)//2]
        rx, ry, rw, rh = room
        for yy in range(ry, ry+rh):
            for xx in range(rx, rx+rw):
                if 0 < xx < MAP_W-1 and 0 < yy < MAP_H-1:
                    if self.tiles[yy][xx] == T_FLOOR:
                        self.tiles[yy][xx] = T_SHOP_FLOOR
        shop_items = []
        for _ in range(random.randint(B["shop_items_min"], B["shop_items_max"])):
            item = self._random_item(rx+1, ry+1, floor_num)
            if item:
                item.identified = True
                floor_mult = 1 + floor_num * 0.1  # Prices scale +10% per floor
                price = int((item.data.get("tier", 1)+1) * random.randint(20, 50) * floor_mult)
                if item.item_type in ("potion", "scroll"):
                    price = int(random.randint(15, 60) * floor_mult)
                elif item.item_type == "food":
                    price = int(random.randint(10, 25) * floor_mult)
                elif item.item_type == "ring":
                    price = int(random.randint(50, 120) * floor_mult)
                shop_items.append(ShopItem(item, price))
        # Always stock healing and food
        heal = Item(0, 0, "potion", "Healing",
                   {"effect": "Healing", "color_name": self.potion_ids["Healing"], "char": '!'})
        heal.identified = True
        shop_items.append(ShopItem(heal, B["shop_heal_base_price"] + floor_num * B["shop_heal_floor_scale"]))
        food = random.choice(FOOD_TYPES)
        fi = Item(0, 0, "food", food["name"], food)
        fi.identified = True
        shop_items.append(ShopItem(fi, B["shop_food_price"]))
        self.shops.append((room, shop_items))

    def _place_shrine(self, floor_num):
        if floor_num % 4 != 2:
            return
        if len(self.rooms) < 2:
            return
        room = self.rooms[random.randint(1, len(self.rooms)-1)]
        cx = room[0] + room[2]//2
        cy = room[1] + room[3]//2
        if 0 < cx < MAP_W-1 and 0 < cy < MAP_H-1:
            self.tiles[cy][cx] = T_SHRINE

    def _place_alchemy_table(self, floor_num):
        """Place alchemy table on specific floors (#7)."""
        if floor_num not in (2, 5, 8, 11, 14):
            return
        if len(self.rooms) < 2:
            return
        room = self.rooms[random.randint(1, len(self.rooms)-1)]
        cx = room[0] + room[2]//2
        cy = room[1] + room[3]//2 + 1  # offset from center
        if 0 < cx < MAP_W-1 and 0 < cy < MAP_H-1:
            if self.tiles[cy][cx] == T_FLOOR:
                self.tiles[cy][cx] = T_ALCHEMY_TABLE

    def _place_wall_torches(self, floor_num):
        """Place wall torches in rooms for environmental lighting (#1)."""
        if not self.rooms:
            return
        for room in self.rooms:
            if random.random() > 0.40:  # 40% of rooms get torches
                continue
            rx, ry, rw, rh = room
            # Deeper floors = fewer lit rooms
            if floor_num >= 10 and random.random() < 0.5:
                continue
            num_torches = random.randint(2, 4)
            placed = 0
            for _ in range(num_torches * 4):  # try multiple positions
                if placed >= num_torches:
                    break
                # Pick a wall position bordering the room
                side = random.randint(0, 3)
                if side == 0:  # top wall
                    tx = random.randint(rx, rx + rw - 1)
                    ty = ry - 1
                elif side == 1:  # bottom wall
                    tx = random.randint(rx, rx + rw - 1)
                    ty = ry + rh
                elif side == 2:  # left wall
                    tx = rx - 1
                    ty = random.randint(ry, ry + rh - 1)
                else:  # right wall
                    tx = rx + rw
                    ty = random.randint(ry, ry + rh - 1)
                if 0 < tx < MAP_W-1 and 0 < ty < MAP_H-1:
                    if self.tiles[ty][tx] == T_WALL:
                        self.tiles[ty][tx] = T_WALL_TORCH
                        self.wall_torches.append((tx, ty))
                        placed += 1

    def _place_puzzle(self, floor_num):
        """Place puzzle on floors 4+ with 25% chance (#9)."""
        if floor_num < 4 or random.random() > 0.25:
            return
        if len(self.rooms) < 4:
            return
        # Pick a room that isn't the start room or shop room
        start_room = self.rooms[0]
        shop_rooms = [r for r, _ in self.shops] if self.shops else []
        candidates = [r for r in self.rooms[1:] if r not in shop_rooms]
        if not candidates:
            return
        room = random.choice(candidates)
        rx, ry, rw, rh = room
        puzzle_type = random.choice(["torch", "switch", "locked_stairs", "sequence", "pressure"])

        if puzzle_type == "torch":
            # Place 3-4 pedestals to light
            count = random.randint(3, 4)
            positions = []
            for _ in range(count):
                px = random.randint(rx, rx + rw - 1)
                py = random.randint(ry, ry + rh - 1)
                if 0 < px < MAP_W-1 and 0 < py < MAP_H-1 and self.tiles[py][px] == T_FLOOR:
                    self.tiles[py][px] = T_PEDESTAL_UNLIT
                    positions.append((px, py))
            if positions:
                self.puzzles.append({"type": "torch", "positions": positions, "solved": False, "room": room})

        elif puzzle_type == "switch":
            # Place 3 switches — all must be ON
            count = 3
            positions = []
            for _ in range(count):
                px = random.randint(rx, rx + rw - 1)
                py = random.randint(ry, ry + rh - 1)
                if 0 < px < MAP_W-1 and 0 < py < MAP_H-1 and self.tiles[py][px] == T_FLOOR:
                    self.tiles[py][px] = T_SWITCH_OFF
                    positions.append((px, py))
            if positions:
                self.puzzles.append({"type": "switch", "positions": positions, "solved": False, "room": room})

        elif puzzle_type == "locked_stairs":
            # Lock the stairs, place switches to unlock
            sx, sy = self.stair_down
            if self.tiles[sy][sx] == T_STAIRS_DOWN:
                self.tiles[sy][sx] = T_STAIRS_LOCKED
                # Place 2 switches in the puzzle room
                positions = []
                for _ in range(2):
                    px = random.randint(rx, rx + rw - 1)
                    py = random.randint(ry, ry + rh - 1)
                    if 0 < px < MAP_W-1 and 0 < py < MAP_H-1 and self.tiles[py][px] == T_FLOOR:
                        self.tiles[py][px] = T_SWITCH_OFF
                        positions.append((px, py))
                if positions:
                    self.puzzles.append({"type": "locked_stairs", "positions": positions,
                                         "solved": False, "room": room, "stairs": (sx, sy)})

        elif puzzle_type == "sequence":
            # Sequence puzzle: pedestals must be lit in a specific order
            count = random.randint(3, 5)
            positions = []
            for _ in range(count):
                px = random.randint(rx, rx + rw - 1)
                py = random.randint(ry, ry + rh - 1)
                if 0 < px < MAP_W-1 and 0 < py < MAP_H-1 and self.tiles[py][px] == T_FLOOR:
                    self.tiles[py][px] = T_PEDESTAL_UNLIT
                    positions.append((px, py))
            if len(positions) >= 3:
                # Correct order is stored; player must figure it out
                correct_order = list(range(len(positions)))
                random.shuffle(correct_order)
                self.puzzles.append({
                    "type": "sequence", "positions": positions,
                    "correct_order": correct_order, "current_step": 0,
                    "solved": False, "room": room
                })

        elif puzzle_type == "pressure":
            # Pressure plate puzzle: stand on all plates within a time limit
            count = random.randint(3, 4)
            positions = []
            for _ in range(count):
                px = random.randint(rx, rx + rw - 1)
                py = random.randint(ry, ry + rh - 1)
                if 0 < px < MAP_W-1 and 0 < py < MAP_H-1 and self.tiles[py][px] == T_FLOOR:
                    self.tiles[py][px] = T_SWITCH_OFF
                    positions.append((px, py))
            if positions:
                self.puzzles.append({
                    "type": "pressure", "positions": positions,
                    "activated": [], "timer": 0, "timer_max": 15,
                    "solved": False, "room": room
                })

    def _place_traps(self, floor_num):
        """Place traps on floor tiles. Hidden overlay tracked in self.traps."""
        count = B["trap_base_count"] + int(floor_num * B["trap_per_floor"])
        eligible_traps = [k for k, v in TRAP_TYPES.items() if v["min_floor"] <= floor_num]
        if not eligible_traps:
            return
        start_room = self.rooms[0] if self.rooms else None
        for _ in range(count):
            for attempt in range(50):
                x = random.randint(1, MAP_W - 2)
                y = random.randint(1, MAP_H - 2)
                if self.tiles[y][x] != T_FLOOR:
                    continue
                # Not in starting room
                if start_room:
                    sx, sy, sw, sh = start_room
                    if sx <= x < sx + sw and sy <= y < sy + sh:
                        continue
                # Not on stairs or shop
                if any(t["x"] == x and t["y"] == y for t in self.traps):
                    continue
                # Not near player start
                if abs(x - self.player.x) + abs(y - self.player.y) <= 3:
                    continue
                trap_type = random.choice(eligible_traps)
                self.traps.append({
                    "x": x, "y": y, "type": trap_type,
                    "visible": False, "triggered": False, "disarmed": False
                })
                break

    def _place_vignettes(self, floor_num):
        """Place 1-2 environmental vignettes per floor for storytelling."""
        if not self.rooms or len(self.rooms) < 3:
            return
        count = random.randint(1, 2)
        used_rooms = set()
        start_room = self.rooms[0]
        shop_rooms = {r for r, _ in self.shops} if self.shops else set()
        for _ in range(count):
            candidates = [r for r in self.rooms[1:]
                         if r not in used_rooms and r != start_room and r not in shop_rooms]
            if not candidates:
                break
            room = random.choice(candidates)
            used_rooms.add(room)
            rx, ry, rw, rh = room
            # Find a floor tile in the room
            vx = rx + rw // 2
            vy = ry + rh // 2
            if 0 < vx < MAP_W - 1 and 0 < vy < MAP_H - 1 and self.tiles[vy][vx] == T_FLOOR:
                template = random.choice(VIGNETTE_TEMPLATES)
                vignette = {
                    "x": vx, "y": vy,
                    "name": template["name"],
                    "lore": template["lore"],
                    "examined": False,
                    "loot_spawned": False,
                    "loot_chance": template["loot_chance"],
                    "loot_tier": template["loot_tier"],
                }
                self.vignettes.append(vignette)

    def _place_npcs(self, floor_num):
        """Place 0-1 NPCs per floor (30% chance on floors 2+)."""
        if floor_num < 2 or random.random() > 0.30:
            return
        if not self.rooms or len(self.rooms) < 3:
            return
        eligible = [k for k, v in NPC_TYPES.items()
                    if v["min_floor"] <= floor_num <= v["max_floor"]]
        if not eligible:
            return
        npc_type = random.choice(eligible)
        npc_def = NPC_TYPES[npc_type]
        # Find a floor tile in a non-start, non-shop room
        start_room = self.rooms[0]
        shop_rooms = {r for r, _ in self.shops} if self.shops else set()
        candidates = [r for r in self.rooms[1:]
                      if r != start_room and r not in shop_rooms]
        if not candidates:
            return
        room = random.choice(candidates)
        rx, ry, rw, rh = room
        nx = rx + rw // 2
        ny = ry + rh // 2
        if 0 < nx < MAP_W - 1 and 0 < ny < MAP_H - 1 and self.tiles[ny][nx] == T_FLOOR:
            self.npcs.append({
                "x": nx, "y": ny,
                "type": npc_type,
                "name": npc_def["name"],
                "char": npc_def["char"],
                "color": npc_def["color"],
                "dialogue": npc_def["dialogue"],
                "interaction": npc_def["interaction"],
                "interacted": False,
            })

    def _place_enchant_anvil(self, floor_num):
        """Place enchanting anvil on deep floors (Phase 4)."""
        if floor_num < B["enchant_anvil_min_floor"]:
            return
        if random.random() > B["enchant_anvil_chance"]:
            return
        if not self.rooms or len(self.rooms) < 3:
            return
        start_room = self.rooms[0]
        shop_rooms = {r for r, _ in self.shops} if self.shops else set()
        candidates = [r for r in self.rooms[1:] if r != start_room and r not in shop_rooms]
        if not candidates:
            return
        room = random.choice(candidates)
        rx, ry, rw, rh = room
        ax = rx + rw // 2
        ay = ry + rh // 2
        if 0 < ax < MAP_W - 1 and 0 < ay < MAP_H - 1 and self.tiles[ay][ax] == T_FLOOR:
            self.tiles[ay][ax] = T_ENCHANT_ANVIL

    def _place_fountain(self, floor_num):
        """Place 0-1 healing fountains per floor."""
        if random.random() > 0.4:  # 40% chance per floor
            return
        if not self.rooms or len(self.rooms) < 2:
            return
        start_room = self.rooms[0]
        candidates = [r for r in self.rooms[1:] if r != start_room]
        if not candidates:
            return
        room = random.choice(candidates)
        rx, ry, rw, rh = room
        fx = rx + rw // 2
        fy = ry + rh // 2
        if 0 < fx < MAP_W - 1 and 0 < fy < MAP_H - 1 and self.tiles[fy][fx] == T_FLOOR:
            self.tiles[fy][fx] = T_FOUNTAIN

    def _place_secret_room(self, floor_num):
        """Place a hidden room behind a secret wall on floors 3+."""
        if floor_num < 3:
            return
        if random.random() > 0.20:  # 20% chance
            return
        if not self.rooms or len(self.rooms) < 3:
            return
        # Pick a room to attach secret room to
        room = random.choice(self.rooms[1:])
        rx, ry, rw, rh = room
        # Try each direction for placing a 3x3 secret room
        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        random.shuffle(directions)
        for dx, dy in directions:
            if dx == -1:  # West
                sx, sy = rx - 4, ry + rh // 2 - 1
                wall_x, wall_y = rx - 1, ry + rh // 2
            elif dx == 1:  # East
                sx, sy = rx + rw + 1, ry + rh // 2 - 1
                wall_x, wall_y = rx + rw, ry + rh // 2
            elif dy == -1:  # North
                sx, sy = rx + rw // 2 - 1, ry - 4
                wall_x, wall_y = rx + rw // 2, ry - 1
            else:  # South
                sx, sy = rx + rw // 2 - 1, ry + rh
                wall_x, wall_y = rx + rw // 2, ry + rh
            # Check bounds
            if sx < 1 or sy < 1 or sx + 3 >= MAP_W - 1 or sy + 3 >= MAP_H - 1:
                continue
            if wall_x < 1 or wall_y < 1 or wall_x >= MAP_W - 1 or wall_y >= MAP_H - 1:
                continue
            # Check the 3x3 area is all wall (carve-able)
            can_place = True
            for yy in range(sy, sy + 3):
                for xx in range(sx, sx + 3):
                    if self.tiles[yy][xx] != T_WALL:
                        can_place = False
                        break
                if not can_place:
                    break
            if not can_place:
                continue
            # Check the connecting wall tile
            if self.tiles[wall_y][wall_x] != T_WALL:
                continue
            # Carve the secret room
            for yy in range(sy, sy + 3):
                for xx in range(sx, sx + 3):
                    self.tiles[yy][xx] = T_FLOOR
            # Place secret wall entrance
            self.tiles[wall_y][wall_x] = T_SECRET_WALL
            # Place loot inside
            cx, cy = sx + 1, sy + 1
            tier = min(floor_num // 3, len(WEAPON_TYPES) - 1)
            loot_roll = random.random()
            if loot_roll < 0.4:
                # Good weapon
                wt = WEAPON_TYPES[min(tier + 1, len(WEAPON_TYPES) - 1)]
                item = Item(cx, cy, "weapon", wt["name"], dict(wt))
                item.identified = True
                self.items.append(item)
            elif loot_roll < 0.7:
                # Gold pile
                amt = random.randint(50, 150) * max(1, floor_num // 3)
                self.items.append(Item(cx, cy, "gold", 0, {"amount": amt, "name": f"{amt} gold"}))
            else:
                # Good armor
                at = ARMOR_TYPES[min(tier + 1, len(ARMOR_TYPES) - 1)]
                item = Item(cx, cy, "armor", at["name"], dict(at))
                item.identified = True
                self.items.append(item)
            break

    def _place_single_trap(self, floor_num):
        """Place a single additional trap (used by branch system)."""
        eligible_traps = [k for k, v in TRAP_TYPES.items() if v["min_floor"] <= floor_num]
        if not eligible_traps:
            return
        for _ in range(50):
            x = random.randint(1, MAP_W - 2)
            y = random.randint(1, MAP_H - 2)
            if self.tiles[y][x] != T_FLOOR:
                continue
            if any(t["x"] == x and t["y"] == y for t in self.traps):
                continue
            if abs(x - self.player.x) + abs(y - self.player.y) <= 3:
                continue
            trap_type = random.choice(eligible_traps)
            self.traps.append({
                "x": x, "y": y, "type": trap_type,
                "visible": False, "triggered": False, "disarmed": False
            })
            break

    def _find_spawn_pos(self):
        for _ in range(100):
            x = random.randint(1, MAP_W-2)
            y = random.randint(1, MAP_H-2)
            if self.tiles[y][x] in (T_FLOOR, T_CORRIDOR):
                if abs(x-self.player.x) + abs(y-self.player.y) > 5:
                    if not any(e.x == x and e.y == y for e in self.enemies):
                        return (x, y)
        return None

    def get_shop_at(self, x, y):
        for room, items in self.shops:
            rx, ry, rw, rh = room
            if rx <= x < rx+rw and ry <= y < ry+rh:
                return (room, items)
        return None

# ============================================================
# MAIN GAME LOOP
# ============================================================

def show_class_select(scr):
    """Show class selection screen. Returns class key or None for classless."""
    scr.erase()
    safe_addstr(scr, 1, 20, "CHOOSE YOUR CLASS", curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 2, 20, "=" * 17, curses.color_pair(C_DARK))
    row = 4
    classes = list(CHARACTER_CLASSES.items())
    for i, (key, cc) in enumerate(classes):
        color = [C_RED, C_CYAN, C_GREEN][i]
        safe_addstr(scr, row, 5, f"[{i+1}] {cc['name']}", curses.color_pair(color) | curses.A_BOLD)
        safe_addstr(scr, row, 25, cc['desc'], curses.color_pair(C_WHITE))
        row += 1
        safe_addstr(scr, row, 9, f"HP:{cc['hp']} MP:{cc['mp']} STR:{cc['str']} DEF:{cc['defense']}", curses.color_pair(C_DARK))
        row += 1
        safe_addstr(scr, row, 9, f"Ability: {cc['ability']} — {cc['ability_desc']}", curses.color_pair(C_DARK))
        row += 2
    safe_addstr(scr, row, 5, "[4] Adventurer", curses.color_pair(C_YELLOW) | curses.A_BOLD)
    safe_addstr(scr, row, 25, "Classic mode — no class, balanced stats", curses.color_pair(C_WHITE))
    row += 2
    safe_addstr(scr, row + 1, 15, "Press 1-4 to choose", curses.color_pair(C_UI))
    scr.refresh()
    while True:
        key = scr.getch()
        if key == ord('1'):
            return classes[0][0]
        elif key == ord('2'):
            return classes[1][0]
        elif key == ord('3'):
            return classes[2][0]
        elif key == ord('4'):
            return None


def _show_branch_choice(scr, gs, floor_num):
    """Show branch selection screen (curses UI) when descending to a branch floor."""
    if floor_num not in BRANCH_CHOICES:
        return None
    branch_a_key, branch_b_key = BRANCH_CHOICES[floor_num]
    branch_a = BRANCH_DEFS[branch_a_key]
    branch_b = BRANCH_DEFS[branch_b_key]

    # Flush buffered keypresses
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)

    scr.erase()
    y = 2
    safe_addstr(scr, y, 4, "THE PATH BRANCHES", curses.color_pair(C_TITLE) | curses.A_BOLD)
    y += 2
    safe_addstr(scr, y, 4, f"As you descend to floor {floor_num}, two passages open before you.", curses.color_pair(C_WHITE))
    y += 2

    # Branch A
    safe_addstr(scr, y, 4, f"[1] {branch_a['name']}", curses.color_pair(C_YELLOW) | curses.A_BOLD)
    y += 1
    safe_addstr(scr, y, 8, f"Floors {branch_a['floors'][0]}-{branch_a['floors'][-1]}", curses.color_pair(C_UI))
    y += 1
    enemies_a = [ENEMY_TYPES[e]["name"] for e in branch_a["enemy_pool"][:3]]
    safe_addstr(scr, y, 8, f"Denizens: {', '.join(enemies_a)}", curses.color_pair(C_DARK))
    y += 1
    mini_a = ENEMY_TYPES[branch_a["mini_boss"]]["name"]
    safe_addstr(scr, y, 8, f"Guardian: {mini_a}", curses.color_pair(C_RED))
    y += 2

    # Branch B
    safe_addstr(scr, y, 4, f"[2] {branch_b['name']}", curses.color_pair(C_YELLOW) | curses.A_BOLD)
    y += 1
    safe_addstr(scr, y, 8, f"Floors {branch_b['floors'][0]}-{branch_b['floors'][-1]}", curses.color_pair(C_UI))
    y += 1
    enemies_b = [ENEMY_TYPES[e]["name"] for e in branch_b["enemy_pool"][:3]]
    safe_addstr(scr, y, 8, f"Denizens: {', '.join(enemies_b)}", curses.color_pair(C_DARK))
    y += 1
    mini_b = ENEMY_TYPES[branch_b["mini_boss"]]["name"]
    safe_addstr(scr, y, 8, f"Guardian: {mini_b}", curses.color_pair(C_RED))
    y += 2

    safe_addstr(scr, y, 4, "Choose your path (1 or 2):", curses.color_pair(C_WHITE) | curses.A_BOLD)
    scr.refresh()

    while True:
        key = scr.getch()
        if key == ord('1'):
            gs.branch_choices[floor_num] = branch_a_key
            gs.msg(f"You enter {branch_a['name']}...", C_YELLOW)
            return branch_a_key
        elif key == ord('2'):
            gs.branch_choices[floor_num] = branch_b_key
            gs.msg(f"You enter {branch_b['name']}...", C_YELLOW)
            return branch_b_key


def _choose_branch_headless(gs, floor_num):
    """Auto-choose a branch for bot/headless modes (random pick)."""
    if floor_num not in BRANCH_CHOICES:
        return None
    branch_a_key, branch_b_key = BRANCH_CHOICES[floor_num]
    choice = random.choice([branch_a_key, branch_b_key])
    gs.branch_choices[floor_num] = choice
    gs.msg(f"You enter {BRANCH_DEFS[choice]['name']}...", C_YELLOW)
    return choice


def _init_new_game(gs):
    """Set up starter gear for a new game."""
    pc = gs.player.player_class
    if pc == "warrior":
        # Long Sword + standard gear
        sw = Item(0, 0, "weapon", 3, WEAPON_TYPES[3])  # Long Sword
        sw.identified = True
        sw.equipped = True
        gs.player.weapon = sw
        gs.player.inventory.append(sw)
    elif pc == "mage":
        # Rusty Dagger + mana potion
        sw = Item(0, 0, "weapon", 0, WEAPON_TYPES[0])
        sw.identified = True
        sw.equipped = True
        gs.player.weapon = sw
        gs.player.inventory.append(sw)
        # Extra mana — mage starts with full (already set by class stats)
    elif pc == "rogue":
        # Short Sword + throwing daggers
        sw = Item(0, 0, "weapon", 1, WEAPON_TYPES[1])  # Short Sword
        sw.identified = True
        sw.equipped = True
        gs.player.weapon = sw
        gs.player.inventory.append(sw)
        daggers = Item(0, 0, "throwing_dagger", "Throwing Dagger", dict(THROWING_DAGGER))
        daggers.count = 8
        gs.player.inventory.append(daggers)
    else:
        # Classic adventurer
        sw = Item(0, 0, "weapon", 0, WEAPON_TYPES[0])
        sw.identified = True
        sw.equipped = True
        gs.player.weapon = sw
        gs.player.inventory.append(sw)
    # Common starter items for all classes
    for fd in [FOOD_TYPES[0], FOOD_TYPES[1]]:
        fi = Item(0, 0, "food", fd["name"], fd)
        gs.player.inventory.append(fi)
    hp = Item(0, 0, "potion", "Healing",
             {"effect": "Healing", "color_name": gs.potion_ids["Healing"], "char": '!'})
    gs.player.inventory.append(hp)
    sb = Item(0, 0, "bow", "Short Bow", dict(BOW_TYPES[0]))
    sb.identified = True
    sb.equipped = True
    gs.player.bow = sb
    gs.player.inventory.append(sb)
    arrows = Item(0, 0, "arrow", "Arrow", dict(ARROW_ITEM))
    arrows.count = 10
    gs.player.inventory.append(arrows)
    gs.generate_floor(1)
    # Increment lifetime game counter
    lt = load_lifetime_stats()
    lt["total_games"] += 1
    save_lifetime_stats(lt)
    # Start session recording
    try:
        gs.recorder = SessionRecorder(gs.seed)
        gs.recorder.record_floor_change(gs)
    except Exception:
        gs.recorder = None
    gs.msg("You descend into the darkness beneath Thornhaven...", C_YELLOW)
    gs.msg("Press ? for help.", C_DARK)
    # Apply challenge modes (Phase 4)
    gs.challenge_ironman = _CHALLENGE_MODES.get("ironman", False)
    gs.challenge_speedrun = _CHALLENGE_MODES.get("speedrun", False)
    gs.challenge_pacifist = _CHALLENGE_MODES.get("pacifist", False)
    gs.challenge_dark = _CHALLENGE_MODES.get("dark", False)
    if gs.challenge_ironman:
        gs.msg("IRONMAN MODE: No saves. Death is permanent.", C_RED)
    if gs.challenge_speedrun:
        gs.msg("SPEEDRUN MODE: Clear each floor before time runs out!", C_RED)
    if gs.challenge_pacifist:
        gs.msg("PACIFIST MODE: You must not kill any non-boss enemy.", C_RED)
    if gs.challenge_dark:
        gs.player.torch_fuel = min(50, gs.player.torch_fuel)
        gs.msg("DARK MODE: Light is scarce. Tread carefully.", C_RED)


def game_loop(scr):
    """Main game loop. Handles input, rendering, and game state updates."""
    curses.curs_set(0)
    scr.nodelay(False)
    scr.keypad(True)
    init_colors()

    # Terminal size check (Phase 7, item 31)
    h, w = scr.getmaxyx()
    if h < MIN_TERMINAL_H or w < MIN_TERMINAL_W:
        scr.erase()
        safe_addstr(scr, 0, 0,
                   f"Terminal too small. Need {MIN_TERMINAL_W}x{MIN_TERMINAL_H}, currently {w}x{h}. Please resize.",
                   0)
        scr.refresh()
        scr.getch()
        return

    show_title(scr)

    # Check for saved game (Phase 7, item 33)
    gs = None
    if save_exists():
        scr.erase()
        safe_addstr(scr, 10, 20, "Saved game found.", curses.color_pair(C_YELLOW) | curses.A_BOLD)
        safe_addstr(scr, 12, 20, "Continue saved game? (y/n)", curses.color_pair(C_WHITE))
        scr.refresh()
        while True:
            key = scr.getch()
            if key == ord('y') or key == ord('Y'):
                gs = load_game()
                if gs:
                    gs._headless = False
                    gs._scr = scr
                    gs.msg("Game loaded.", C_GREEN)
                else:
                    scr.erase()
                    safe_addstr(scr, 10, 20, "Save file corrupted or tampered.",
                               curses.color_pair(C_RED))
                    safe_addstr(scr, 12, 20, "Starting new game...",
                               curses.color_pair(C_WHITE))
                    scr.refresh()
                    curses.napms(1500)
                    delete_save()
                break
            elif key == ord('n') or key == ord('N'):
                delete_save()
                break

    if gs is None:
        cli_class = _CHALLENGE_MODES.get("player_class")
        cli_diff = _CHALLENGE_MODES.get("difficulty", "normal")
        cli_seed = _CHALLENGE_MODES.get("seed")
        chosen_class = cli_class or show_class_select(scr)
        gs = GameState(player_class=chosen_class, difficulty=cli_diff, seed=cli_seed)
        gs._scr = scr
        _init_new_game(gs)

    MOVE_KEYS = {
        curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
        curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
        ord('w'): (0,-1), ord('s'): (0,1),
        ord('a'): (-1,0), ord('d'): (1,0),
        ord('h'): (-1,0), ord('j'): (0,1),
        ord('k'): (0,-1), ord('l'): (1,0),
        ord('y'): (-1,-1), ord('u'): (1,-1),
        ord('b'): (-1,1), ord('n'): (1,1),
    }

    while gs.running and not gs.game_over:
        # Terminal resize detection (Phase 7, item 30)
        cur_h, cur_w = scr.getmaxyx()
        if cur_h < MIN_TERMINAL_H or cur_w < MIN_TERMINAL_W:
            scr.erase()
            safe_addstr(scr, 0, 0,
                       f"Terminal too small! Need {MIN_TERMINAL_W}x{MIN_TERMINAL_H} (currently {cur_w}x{cur_h})",
                       curses.A_BOLD)
            scr.refresh()
            curses.napms(200)
            continue

        # Paralysis: skip player's turn entirely
        if "Paralysis" in gs.player.status_effects:
            render_game(scr, gs)
            gs.msg("You are paralyzed!", C_YELLOW)
            gs.turn_count += 1
            process_enemies(gs)
            process_status(gs)
            if gs.player.hp <= 0:
                gs.game_over = True
            curses.napms(200)
            continue
        # Frozen: skip turn, take bonus damage if hit (shatter)
        if "Frozen" in gs.player.status_effects:
            render_game(scr, gs)
            gs.msg("You are frozen solid!", C_CYAN)
            gs.turn_count += 1
            process_enemies(gs)
            process_status(gs)
            if gs.player.hp <= 0:
                gs.game_over = True
            curses.napms(200)
            continue

        # Auto-fight loop (Phase 4, item 20)
        if gs.auto_fighting:
            render_game(scr, gs)
            result = auto_fight_step(gs)
            if result is None:
                gs.auto_fighting = False
                continue
            if result:
                gs.turn_count += 1
                if gs.last_noise > 0:
                    _stealth_detection(gs, gs.last_noise)
                gs.last_noise = 0
                process_enemies(gs)
                process_status(gs)
                check_context_tips(gs)
                if gs.player.hp <= 0:
                    gs.game_over = True
            curses.napms(80)
            continue

        # Auto-explore loop (Phase 4, item 21)
        if gs.auto_exploring:
            render_game(scr, gs)
            result = auto_explore_step(gs)
            if result is None:
                gs.auto_exploring = False
                continue
            if result:
                gs.turn_count += 1
                if gs.last_noise > 0:
                    _stealth_detection(gs, gs.last_noise)
                gs.last_noise = 0
                process_enemies(gs)
                process_status(gs)
                check_context_tips(gs)
                if gs.player.hp <= 0:
                    gs.game_over = True
            curses.napms(40)
            # Check for keypress to cancel
            scr.nodelay(True)
            cancel_key = scr.getch()
            scr.nodelay(False)
            if cancel_key != -1:
                gs.auto_exploring = False
                gs.msg("Exploring cancelled.", C_WHITE)
            continue

        # Pending level-up choices
        while gs.player.pending_levelups:
            show_levelup_choice(scr, gs)

        render_game(scr, gs)
        key = scr.getch()
        turn_spent = False

        # Record input for session replay
        if gs.recorder and key != -1:
            key_name = None
            if key in MOVE_KEYS:
                # Map key to character name for replay
                for ch in 'wasdhljkyubn':
                    if key == ord(ch):
                        key_name = ch
                        break
                if key_name is None:
                    for name, code in [('UP', curses.KEY_UP), ('DOWN', curses.KEY_DOWN),
                                        ('LEFT', curses.KEY_LEFT), ('RIGHT', curses.KEY_RIGHT)]:
                        if key == code:
                            key_name = name
                            break
            elif key == ord('>'):
                key_name = '>'
            elif key == ord('<'):
                key_name = '<'
            elif key == ord('.') or key == ord('5'):
                key_name = '.'
            elif key == ord(','):
                key_name = ','
            elif key == ord('f'):
                key_name = 'f'
            elif key == ord('z'):
                key_name = 'z'
            elif key == ord('p'):
                key_name = 'p'
            if key_name:
                gs.recorder.record_input(key_name, gs.turn_count)

        if key in MOVE_KEYS:
            dx, dy = MOVE_KEYS[key]
            turn_spent = player_move(gs, dx, dy)
        elif key == ord('>'):
            if gs.player.floor == MAX_FLOORS:
                boss_alive = any(e.boss and e.etype == "abyssal_horror" and e.is_alive()
                                for e in gs.enemies)
                if boss_alive:
                    gs.msg("The Abyssal Horror still lives!", C_RED)
                else:
                    gs.victory = True
                    gs.game_over = True
            else:
                if gs.tiles[gs.player.y][gs.player.x] == T_STAIRS_DOWN:
                    new_floor = gs.player.floor + 1
                    # Branch selection at branch floors
                    if new_floor in BRANCH_CHOICES and new_floor not in gs.branch_choices:
                        _show_branch_choice(scr, gs, new_floor)
                    # Floor transition message (Phase 3, item 17)
                    gs.msg(f"Descending to floor {new_floor}...", C_YELLOW)
                    render_game(scr, gs)
                    curses.napms(500)
                    gs.generate_floor(new_floor)
                    if gs.recorder:
                        gs.recorder.record_floor_change(gs)
                    # Boss floor warning (Phase 6, item 29)
                    if new_floor == MAX_FLOORS:
                        gs.msg("A terrible darkness fills this place...", C_RED)
                        gs.msg("The Dread Lord awaits.", C_RED)
                        render_game(scr, gs)
                        curses.napms(1000)
                    turn_spent = True
                else:
                    gs.msg("No stairs here.", C_WHITE)
        elif key == ord('<'):
            if gs.tiles[gs.player.y][gs.player.x] == T_STAIRS_UP:
                if gs.player.floor > 1:
                    new_floor = gs.player.floor - 1
                    gs.msg(f"Ascending to floor {new_floor}...", C_YELLOW)
                    render_game(scr, gs)
                    curses.napms(500)
                    gs.generate_floor(new_floor)
                    turn_spent = True
                else:
                    gs.msg("You can't leave yet.", C_WHITE)
            else:
                gs.msg("No stairs here.", C_WHITE)
        elif key == ord('.') or key == ord('5'):
            # Wait/rest one turn
            p = gs.player
            if p.hp < p.max_hp and p.hunger > B["rest_hunger_threshold"]:
                p.hp = min(p.max_hp, p.hp + B["rest_hp_per_turn"])
            p.hunger = max(0, p.hunger - B["rest_wait_hunger_cost"])
            turn_spent = True
        elif key == ord('i'):
            turn_spent = show_inventory(scr, gs)
        elif key == ord('c'):
            show_character(scr, gs)
        elif key == ord('C'):
            # Class ability
            turn_spent = use_class_ability(gs, scr)
        elif key == ord('?'):
            show_help(scr)
        elif key == ord('m'):
            show_messages(scr, gs)
        elif key == ord('J'):
            show_journal(scr, gs)
        elif key == ord('M'):
            show_bestiary(scr, gs)
        elif key == ord('$'):
            show_shop(scr, gs)
        elif key == ord('p'):
            if gs.tiles[gs.player.y][gs.player.x] == T_SHRINE:
                pray_at_shrine(gs)
                turn_spent = True
            else:
                gs.msg("Nothing to pray to here.", C_WHITE)
        elif key == ord('f'):
            turn_spent = fire_projectile(gs, scr)
        elif key == ord('z'):
            turn_spent = cast_spell_menu(gs, scr)
        elif key == ord('t'):
            turn_spent = use_technique_menu(gs, scr)
        elif key == ord('x'):
            # Look/examine mode (Phase 4, item 23)
            look_mode(gs, scr)
        elif key == 9:  # Tab key = auto-fight (Phase 4, item 20)
            gs.auto_fighting = True
            gs.auto_fight_target = None
            gs.msg("Auto-fighting...", C_YELLOW)
        elif key == ord('o'):
            # Auto-explore (Phase 4, item 21)
            gs.auto_exploring = True
            gs.msg("Exploring...", C_YELLOW)
        elif key == ord('R'):
            # Rest until healed (Phase 4, item 22)
            rest_until_healed(gs, scr)
        elif key == ord('S'):
            # Lifetime stats overlay
            show_lifetime_stats(scr)
        elif key == ord('e'):
            # Alchemy table (#7), light pedestal (#9), or fountain
            px, py = gs.player.x, gs.player.y
            if gs.tiles[py][px] == T_ALCHEMY_TABLE:
                turn_spent = use_alchemy_table(gs)
            elif gs.tiles[py][px] == T_PEDESTAL_UNLIT:
                turn_spent = _interact_pedestal(gs, px, py)
            elif gs.tiles[py][px] == T_FOUNTAIN:
                p = gs.player
                heal = random.randint(15, 30)
                p.hp = min(p.max_hp, p.hp + heal)
                gs.msg(f"You drink from the fountain. Refreshing! (+{heal} HP)", C_WATER)
                if random.random() < 0.10:
                    p.max_hp += 1
                    p.hp = min(p.max_hp, p.hp + 1)
                    gs.msg("Blessed water! You feel permanently stronger! (+1 max HP)", C_YELLOW)
                p.fountains_used += 1
                gs.tiles[py][px] = T_FLOOR  # Fountain is consumed
                turn_spent = True
            else:
                gs.msg("Nothing to interact with here.", C_DARK)
        elif key == ord('E'):
            # Enchant weapon at anvil (Phase 4)
            px, py = gs.player.x, gs.player.y
            if gs.tiles[py][px] == T_ENCHANT_ANVIL:
                turn_spent = enchant_weapon_headless(gs)
            else:
                gs.msg("You need to be at an enchanting anvil!", C_DARK)
        elif key == ord('T'):
            # Toggle torch on/off to conserve fuel
            p = gs.player
            if p.torch_fuel <= 0:
                has_torches = any(i.item_type == "torch" for i in p.inventory)
                if has_torches:
                    gs.msg("No fuel! Use a torch from inventory (i) to refuel.", C_RED)
                else:
                    gs.msg("No torch fuel! Grab wall torches (,) or find torch items.", C_RED)
            else:
                p.torch_lit = not p.torch_lit
                if p.torch_lit:
                    gs.msg("You light your torch.", C_YELLOW)
                else:
                    gs.msg("You extinguish your torch to save fuel.", C_DARK)
        elif key == ord('Q'):
            # Save and quit (Phase 7, item 33)
            scr.erase()
            safe_addstr(scr, 10, 20, "Save and quit? (y/n/c)", curses.color_pair(C_YELLOW))
            safe_addstr(scr, 12, 20, "y=Save & Quit  n=Quit without saving  c=Cancel",
                       curses.color_pair(C_DARK))
            scr.refresh()
            while True:
                qk = scr.getch()
                if qk == ord('y') or qk == ord('Y'):
                    if save_game(gs):
                        gs.msg("Game saved.", C_GREEN)
                    gs.running = False
                    break
                elif qk == ord('n') or qk == ord('N'):
                    gs.running = False
                    break
                elif qk == ord('c') or qk == ord('C') or qk == 27:
                    break
        elif key == ord('q'):
            # Lowercase q hint (Phase 1, item 5)
            gs.msg("Press Q (shift) to quit.", C_DARK)
        elif key == ord('/'):
            # Search for traps
            _search_for_traps(gs)
            turn_spent = True
        elif key == ord('D'):
            # Disarm adjacent trap
            turn_spent = _disarm_trap(gs)
        elif key == ord(','):
            pickup = [i for i in gs.items if i.x == gs.player.x and i.y == gs.player.y]
            for item in pickup:
                if item.item_type == "gold":
                    gs.player.gold += item.data["amount"]
                    gs.player.gold_earned += item.data["amount"]
                    gs.msg(f"Picked up {item.data['amount']} gold.", C_GOLD)
                    gs.items.remove(item)
                else:
                    capacity_ok = (item.item_type == "scroll" or
                                   sum(1 for it in gs.player.inventory if it.item_type != "scroll") < gs.player.carry_capacity)
                    if capacity_ok:
                        gs.items.remove(item)
                        gs.player.inventory.append(item)
                        gs.player.items_found += 1
                        gs.player.items_by_type[item.item_type] = gs.player.items_by_type.get(item.item_type, 0) + 1
                        gs.msg(f"Picked up {item.display_name}.", item.color)
                    else:
                        gs.msg("Inventory full!", C_RED)
            # Grab adjacent wall torch (#1)
            if not pickup:
                grabbed_torch = False
                for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    tx, ty = gs.player.x + ddx, gs.player.y + ddy
                    if 0 <= tx < MAP_W and 0 <= ty < MAP_H and gs.tiles[ty][tx] == T_WALL_TORCH:
                        gs.tiles[ty][tx] = T_WALL
                        if (tx, ty) in gs.wall_torches:
                            gs.wall_torches.remove((tx, ty))
                        fuel = 60
                        gs.player.torch_fuel = min(TORCH_MAX_FUEL, gs.player.torch_fuel + fuel)
                        gs.msg(f"You grab a wall torch and refuel! (+{fuel} fuel)", C_YELLOW)
                        gs.player.torches_grabbed += 1
                        grabbed_torch = True
                        break
                turn_spent = grabbed_torch or bool(pickup)
            else:
                turn_spent = bool(pickup)
        else:
            # Unknown command feedback (Phase 1, item 1)
            if key != -1 and key != 27:  # ignore resize events and ESC
                gs.msg("Unknown command. Press ? for help.", C_DARK)

        if turn_spent:
            gs.turn_count += 1
            # Stealth detection: check noise before enemies act
            if gs.last_noise > 0:
                _stealth_detection(gs, gs.last_noise)
            gs.last_noise = 0
            process_enemies(gs)
            process_status(gs)
            check_context_tips(gs)
            # Record state snapshot every 10 turns
            if gs.recorder and gs.turn_count % 10 == 0:
                gs.recorder.record_state_snapshot(gs)
            if gs.player.hp <= 0:
                gs.game_over = True

    render_game(scr, gs)
    replay_path = None
    if gs.recorder:
        replay_path = gs.recorder.filepath
    if gs.victory:
        if gs.recorder:
            gs.recorder.record_victory(gs)
            gs.recorder.close()
        show_enhanced_victory(scr, gs)
        delete_save()  # Permadeath: delete save on win too
    elif gs.game_over:
        if gs.recorder:
            gs.recorder.record_death(gs)
            gs.recorder.close()
        show_enhanced_death(scr, gs)
        delete_save()  # Permadeath: delete save on death
    # Auto-replay prompt (#3)
    if replay_path and os.path.exists(replay_path) and (gs.victory or gs.game_over):
        scr.erase()
        safe_addstr(scr, 10, 20, "Watch replay? (y/n)", curses.color_pair(C_YELLOW))
        scr.refresh()
        while True:
            rk = scr.getch()
            if rk == ord('y') or rk == ord('Y'):
                replay_session(scr, replay_path, speed=2.0)
                break
            elif rk == ord('n') or rk == ord('N') or rk == 27:
                break


def main(stdscr=None):
    if stdscr is None:
        curses.wrapper(game_loop)
    else:
        game_loop(stdscr)


# ============================================================

# ============================================================
# TESTS
# ============================================================

def test_connectivity(n=50):
    print(f"[1] Dungeon Connectivity ({n} dungeons)...")
    fails = 0
    for _ in range(n):
        floor = random.randint(1, MAX_FLOORS)
        tiles, _, start, _ = generate_dungeon(floor)
        w = count_walkable(tiles)
        r = flood_fill_count(tiles, start[0], start[1])
        if w == 0 or r / w < 0.95:
            fails += 1
            print(f"  FAIL floor {floor}: {r}/{w} ({r/w:.1%})")
    print(f"  Result: {n-fails}/{n} passed")
    return fails == 0


def test_enemies():
    print("[2] Enemy Spawning...")
    gs = GameState()
    seen = set()
    for f in range(1, MAX_FLOORS+1):
        gs.generate_floor(f)
        for e in gs.enemies:
            seen.add(e.etype)
    non_boss = {k for k, v in ENEMY_TYPES.items() if not v.get("boss")}
    missing = non_boss - seen
    print(f"  Spawned: {len(seen)}/{len(ENEMY_TYPES)} types")
    if missing:
        print(f"  FAIL: Missing non-boss: {missing}")
        return False
    print("  Result: PASS")
    return True


def test_items():
    print("[3] Item Generation...")
    gs = GameState()
    seen = set()
    for f in range(1, MAX_FLOORS+1):
        gs.generate_floor(f)
        for item in gs.items:
            seen.add(item.item_type)
        for _, si_list in gs.shops:
            for si in si_list:
                seen.add(si.item.item_type)
    expected = {"weapon", "armor", "potion", "scroll", "gold", "food", "ring"}
    missing = expected - seen
    print(f"  Types: {len(seen & expected)}/{len(expected)}")
    if missing:
        print(f"  FAIL: Missing: {missing}")
        return False
    print("  Result: PASS")
    return True


def run_tests():
    print("=" * 50)
    print("DEPTHS OF DREAD - Test Suite")
    print("=" * 50)
    t1 = test_connectivity(50)
    t2 = test_enemies()
    t3 = test_items()
    print("=" * 50)
    print("ALL TESTS PASSED" if all([t1, t2, t3]) else "SOME TESTS FAILED")
    print("=" * 50)
    return all([t1, t2, t3])


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Depths of Dread - A Terminal Roguelike",
        epilog="Controls: WASD/Arrows/hjkl to move. ? for in-game help. Q to save & quit.")
    parser.add_argument("--test", action="store_true", help="Run built-in tests")
    parser.add_argument("--bot", action="store_true", help="Watch AI bot play")
    parser.add_argument("--agent", action="store_true", help="Watch Claude-powered agent play")
    parser.add_argument("--games", type=int, default=0, help="Bot/agent batch mode: run N games headless")
    parser.add_argument("--replay", type=str, default="", help="Replay a recorded session")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay/bot speed multiplier")
    parser.add_argument("--recordings", action="store_true", help="List saved recordings")
    parser.add_argument("--seed", type=int, default=None, help="Set random seed for reproducible dungeon")
    parser.add_argument("--class", dest="player_class", choices=["warrior", "mage", "rogue"],
                        default=None, help="Start as a specific class (skip selection)")
    parser.add_argument("--difficulty", choices=["easy", "normal", "hard"],
                        default="normal", help="Difficulty: easy/normal/hard (default: normal)")
    # Challenge modes (Phase 4)
    parser.add_argument("--ironman", action="store_true", help="Ironman: no save/load, permadeath only")
    parser.add_argument("--speedrun", action="store_true", help="Speedrun: turn timer, no resting")
    parser.add_argument("--pacifist", action="store_true", help="Pacifist: no direct kills allowed")
    parser.add_argument("--dark", action="store_true", help="Dark mode: reduced FOV, no map reveal")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.test:
        sys.exit(0 if run_tests() else 1)
    elif args.recordings:
        list_recordings()
    elif args.agent:
        if args.games > 0:
            agent_batch_mode(args.games)
        else:
            curses.wrapper(lambda scr: agent_game_loop(scr, speed=args.speed))
    elif args.bot:
        if args.games > 0:
            bot_batch_mode(args.games)
        else:
            curses.wrapper(lambda scr: bot_game_loop(scr, speed=args.speed))
    elif args.replay:
        filepath = args.replay
        if not os.path.exists(filepath):
            # Try in recordings dir
            alt = os.path.join(RECORDINGS_DIR, filepath)
            if os.path.exists(alt):
                filepath = alt
            else:
                print(f"Recording not found: {filepath}")
                sys.exit(1)
        curses.wrapper(lambda scr: replay_session(scr, filepath, speed=args.speed))
    else:
        # Apply challenge modes
        _CHALLENGE_MODES["ironman"] = args.ironman
        _CHALLENGE_MODES["speedrun"] = args.speedrun
        _CHALLENGE_MODES["pacifist"] = args.pacifist
        _CHALLENGE_MODES["dark"] = args.dark
        _CHALLENGE_MODES["difficulty"] = args.difficulty
        _CHALLENGE_MODES["player_class"] = args.player_class
        _CHALLENGE_MODES["seed"] = args.seed
        main()
