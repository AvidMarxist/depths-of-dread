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
from __future__ import annotations

import curses
import random
import time
import sys
import os
from collections import deque
import argparse
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .entities import Item, Player, ShopItem
    from .persistence import SessionRecorder

# --- Constants (data layer — wildcard import is intentional) ---
from .constants import *  # noqa: F403 — constants are the shared data layer
from .constants import _CHALLENGE_MODES, _DIR_MAP

# --- Entities ---
from .entities import (
    Item, Enemy, Player, ShopItem,
    show_levelup_choice, auto_apply_levelup,
    generate_levelup_choices, apply_levelup_choice,
    _unlock_next_spell, _unlock_next_ability,
)

# --- Map generation ---
from .mapgen import (
    BSPNode, generate_dungeon, compute_fov, astar,
    flood_fill_count, count_walkable,
    _has_los, _cast_light, _carve_room_shape, _carve_corridor,
    _add_cave_features, _generate_fallback, _MULT,
)

# --- Floor generation (extracted from GameState) ---
from .floor_gen import generate_floor

# --- Combat ---
from .combat import (
    sound_alert, enemy_attack, process_enemies,
    _bestiary_record, _award_kill, _check_levelups, _trigger_trap,
    _check_traps_on_move, _passive_trap_detect, _search_for_traps,
    _disarm_trap, _compute_noise, _stealth_detection, _update_boss_phase,
    _try_enemy_move, _flee_move, _chase_move, _erratic_move, _patrol_move,
    _pack_move, _ambush_move, _ranged_move, _summoner_move, _mimic_move,
    _phase_move, _mind_flayer_move,
)

# --- Items & abilities ---
from .items import (
    player_move, player_attack, process_status,
    pray_at_shrine, use_class_ability, use_alchemy_table,
    enchant_weapon_headless, fire_projectile, fire_projectile_headless,
    cast_spell_menu, cast_spell_headless, use_technique_menu,
    use_potion, use_scroll, use_food, use_ability_headless,
    show_journal,
    _get_direction_delta, _animate_projectile, _launch_projectile,
    _apply_spell_resist, _cast_spell, _execute_ability,
    _journal_potion_desc, _journal_scroll_desc, _toggle_switch,
    _interact_pedestal, _interact_npc, _process_branch_effects,
)

# --- UI / rendering ---
from .ui import (
    render_game, show_title, show_inventory, show_character,
    show_help, show_messages, show_bestiary, show_shop,
    look_mode, rest_until_healed, check_context_tips,
    show_enhanced_victory, show_enhanced_death,
    auto_fight_step, auto_explore_step, calculate_score,
    _draw_tile, _inv_letter, _inv_key_to_idx, _describe_tile, _bfs_unexplored,
)

# --- Persistence ---
from .persistence import (
    save_game, load_game, save_exists, delete_save,
    load_lifetime_stats, save_lifetime_stats, show_lifetime_stats,
    SessionRecorder, list_recordings, replay_session,
    check_meta_unlocks, apply_meta_unlocks,
    _default_lifetime_stats, _compute_checksum,
    _serialize_item, _serialize_item_on_ground, _serialize_enemy,
    _deserialize_item, _deserialize_item_ground, _deserialize_enemy,
    _format_lifetime_stats_lines,
)

# --- Bot / Agent ---
from .bot import (
    BotPlayer, FeatureTracker, AgentPlayer,
    bot_game_loop, agent_game_loop, bot_batch_mode, agent_batch_mode,
    _bot_execute_action, _update_explored_from_fov,
)


# ============================================================
# GAME STATE
# ============================================================

class GameState:
    def __init__(self, headless: bool = False, seed: int | None = None, player_class: str | None = None, difficulty: str = "normal") -> None:
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
        self.tips_shown = set()
        self.first_melee_done = False
        self.shop_discovered = False
        self.journal = {}
        self.alchemy_used = set()
        self.puzzles = []
        self.wall_torches = []
        self.vignettes = []
        self.npcs = []
        self.traps = []
        self.last_noise = 0
        self.branch_choices = {}
        self.active_branch = None
        self.bestiary = {}
        self.auto_fighting = False
        self.challenge_ironman = False
        self.challenge_speedrun = False
        self.challenge_pacifist = False
        self.challenge_dark = False
        self.speedrun_timer = 0
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

    def msg(self, text: str, color: int = C_WHITE) -> None:
        self.messages.append((text, color))

    def generate_floor(self, floor_num: int) -> None:
        """Delegate to floor_gen module."""
        generate_floor(self, floor_num)

    def _find_spawn_pos(self) -> tuple[int, int] | None:
        from .floor_gen import _find_spawn_pos
        return _find_spawn_pos(self)

    def _random_item(self, x: int, y: int, floor_num: int) -> Item | None:
        from .floor_gen import _random_item
        return _random_item(self, x, y, floor_num)

    def _get_active_branch(self, floor_num: int) -> str | None:
        from .floor_gen import _get_active_branch
        return _get_active_branch(self, floor_num)

    def get_shop_at(self, x: int, y: int) -> tuple[tuple[int, int, int, int], list[ShopItem]] | None:
        for room, items in self.shops:
            rx, ry, rw, rh = room
            if rx <= x < rx+rw and ry <= y < ry+rh:
                return (room, items)
        return None


# ============================================================
# MAIN GAME LOOP
# ============================================================
# (floor generation logic is now in floor_gen.py)

def show_class_select(scr: Any) -> str | None:
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


def _show_branch_choice(scr: Any, gs: GameState, floor_num: int) -> str | None:
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


def _choose_branch_headless(gs: GameState, floor_num: int) -> str | None:
    """Auto-choose a branch for bot/headless modes (random pick)."""
    if floor_num not in BRANCH_CHOICES:
        return None
    branch_a_key, branch_b_key = BRANCH_CHOICES[floor_num]
    choice = random.choice([branch_a_key, branch_b_key])
    gs.branch_choices[floor_num] = choice
    gs.msg(f"You enter {BRANCH_DEFS[choice]['name']}...", C_YELLOW)
    return choice


def _init_new_game(gs: GameState) -> None:
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


# ---- Command handlers (each takes gs, scr; returns bool|None for turn_spent) ----

def _cmd_descend(gs: GameState, scr: Any) -> bool | None:
    if gs.player.floor == MAX_FLOORS:
        boss_alive = any(e.boss and e.etype == "abyssal_horror" and e.is_alive()
                         for e in gs.enemies)
        if boss_alive:
            gs.msg("The Abyssal Horror still lives!", C_RED)
        else:
            gs.victory = True
            gs.game_over = True
        return None
    if gs.tiles[gs.player.y][gs.player.x] == T_STAIRS_DOWN:
        new_floor = gs.player.floor + 1
        if new_floor in BRANCH_CHOICES and new_floor not in gs.branch_choices:
            _show_branch_choice(scr, gs, new_floor)
        gs.msg(f"Descending to floor {new_floor}...", C_YELLOW)
        render_game(scr, gs)
        curses.napms(500)
        gs.generate_floor(new_floor)
        if gs.recorder:
            gs.recorder.record_floor_change(gs)
        if new_floor == MAX_FLOORS:
            gs.msg("A terrible darkness fills this place...", C_RED)
            gs.msg("The Dread Lord awaits.", C_RED)
            render_game(scr, gs)
            curses.napms(1000)
        return True
    gs.msg("No stairs here.", C_WHITE)
    return None


def _cmd_ascend(gs: GameState, scr: Any) -> bool | None:
    if gs.tiles[gs.player.y][gs.player.x] == T_STAIRS_UP:
        if gs.player.floor > 1:
            new_floor = gs.player.floor - 1
            gs.msg(f"Ascending to floor {new_floor}...", C_YELLOW)
            render_game(scr, gs)
            curses.napms(500)
            gs.generate_floor(new_floor)
            return True
        gs.msg("You can't leave yet.", C_WHITE)
    else:
        gs.msg("No stairs here.", C_WHITE)
    return None


def _cmd_wait(gs: GameState, scr: Any) -> bool:
    p = gs.player
    if p.hp < p.max_hp and p.hunger > B["rest_hunger_threshold"]:
        p.hp = min(p.max_hp, p.hp + B["rest_hp_per_turn"])
    p.hunger = max(0, p.hunger - B["rest_wait_hunger_cost"])
    return True


def _cmd_pray(gs: GameState, scr: Any) -> bool | None:
    if gs.tiles[gs.player.y][gs.player.x] == T_SHRINE:
        pray_at_shrine(gs)
        return True
    gs.msg("Nothing to pray to here.", C_WHITE)
    return None


def _cmd_interact(gs: GameState, scr: Any) -> bool | None:
    px, py = gs.player.x, gs.player.y
    if gs.tiles[py][px] == T_ALCHEMY_TABLE:
        return use_alchemy_table(gs)
    elif gs.tiles[py][px] == T_PEDESTAL_UNLIT:
        return _interact_pedestal(gs, px, py)
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
        gs.tiles[py][px] = T_FLOOR
        return True
    gs.msg("Nothing to interact with here.", C_DARK)
    return None


def _cmd_enchant(gs: GameState, scr: Any) -> bool | None:
    px, py = gs.player.x, gs.player.y
    if gs.tiles[py][px] == T_ENCHANT_ANVIL:
        return enchant_weapon_headless(gs)
    gs.msg("You need to be at an enchanting anvil!", C_DARK)
    return None


def _cmd_toggle_torch(gs: GameState, scr: Any) -> None:
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
    return None


def _cmd_quit(gs: GameState, scr: Any) -> None:
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
    return None


def _cmd_auto_fight(gs: GameState, scr: Any) -> None:
    gs.auto_fighting = True
    gs.auto_fight_target = None
    gs.msg("Auto-fighting...", C_YELLOW)
    return None


def _cmd_auto_explore(gs: GameState, scr: Any) -> None:
    gs.auto_exploring = True
    gs.msg("Exploring...", C_YELLOW)
    return None


def _cmd_pickup(gs: GameState, scr: Any) -> bool:
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
    # Grab adjacent wall torch
    if not pickup:
        grabbed_torch = False
        for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
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
        return grabbed_torch or bool(pickup)
    return bool(pickup)


# Command dispatch table — maps key codes to handler functions
COMMAND_HANDLERS = {
    ord('>'): _cmd_descend,
    ord('<'): _cmd_ascend,
    ord('.'): _cmd_wait,
    ord('5'): _cmd_wait,
    ord('i'): lambda gs, scr: show_inventory(scr, gs),
    ord('c'): lambda gs, scr: (show_character(scr, gs), None)[1],
    ord('C'): lambda gs, scr: use_class_ability(gs, scr),
    ord('?'): lambda gs, scr: (show_help(scr), None)[1],
    ord('m'): lambda gs, scr: (show_messages(scr, gs), None)[1],
    ord('J'): lambda gs, scr: (show_journal(scr, gs), None)[1],
    ord('M'): lambda gs, scr: (show_bestiary(scr, gs), None)[1],
    ord('$'): lambda gs, scr: (show_shop(scr, gs), None)[1],
    ord('p'): _cmd_pray,
    ord('f'): lambda gs, scr: fire_projectile(gs, scr),
    ord('z'): lambda gs, scr: cast_spell_menu(gs, scr),
    ord('t'): lambda gs, scr: use_technique_menu(gs, scr),
    ord('x'): lambda gs, scr: (look_mode(gs, scr), None)[1],
    9:        _cmd_auto_fight,   # Tab key
    ord('o'): _cmd_auto_explore,
    ord('R'): lambda gs, scr: (rest_until_healed(gs, scr), None)[1],
    ord('S'): lambda gs, scr: (show_lifetime_stats(scr), None)[1],
    ord('e'): _cmd_interact,
    ord('E'): _cmd_enchant,
    ord('T'): _cmd_toggle_torch,
    ord('Q'): _cmd_quit,
    ord('q'): lambda gs, scr: (gs.msg("Press Q (shift) to quit.", C_DARK), None)[1],
    ord('/'): lambda gs, scr: (_search_for_traps(gs), True)[1],
    ord('D'): lambda gs, scr: _disarm_trap(gs),
    ord(','): _cmd_pickup,
}


def game_loop(scr: Any) -> None:
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

        # Command dispatch — replaces the old if/elif chain
        if key in MOVE_KEYS:
            dx, dy = MOVE_KEYS[key]
            turn_spent = player_move(gs, dx, dy)
        elif key in COMMAND_HANDLERS:
            result = COMMAND_HANDLERS[key](gs, scr)
            if result is not None:
                turn_spent = result
        elif key != -1 and key != 27:
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


def main(stdscr: Any | None = None) -> None:
    if stdscr is None:
        curses.wrapper(game_loop)
    else:
        game_loop(stdscr)


# ============================================================

# ============================================================
# TESTS
# ============================================================

def test_connectivity(n: int = 50) -> bool:
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


def test_enemies() -> bool:
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


def test_items() -> bool:
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


def run_tests() -> bool:
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


def _parse_args() -> argparse.Namespace:
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
