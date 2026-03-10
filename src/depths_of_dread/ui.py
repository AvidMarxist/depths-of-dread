"""
UI / Rendering module for Depths of Dread.

Contains all rendering functions, UI screens, context tips,
look/examine mode, auto-fight, auto-explore, rest, and
enhanced death/victory screens.
"""
from __future__ import annotations

import curses
import random
import time
import types
from collections import deque
from typing import TYPE_CHECKING, Any

from .combat import player_attack, process_enemies
from .constants import *
from .constants import _floor_theme_name, _get_theme_pairs, get_tile_char
from .entities import Item, Player
from .mapgen import _has_los, astar, compute_fov

if TYPE_CHECKING:
    from .game import GameState


def _get_items() -> types.ModuleType:
    from . import items
    return items


def _get_game() -> types.ModuleType:
    from . import game
    return game


# ============================================================
# RENDERING
# ============================================================

def render_map(scr: Any, gs: GameState) -> None:
    p = gs.player
    cam_x = max(0, min(p.x - VIEW_W//2, MAP_W - VIEW_W))
    cam_y = max(0, min(p.y - VIEW_H//2, MAP_H - VIEW_H))
    blind = "Blindness" in p.status_effects

    for sy in range(VIEW_H):
        for sx in range(VIEW_W):
            mx = cam_x + sx
            my = cam_y + sy
            if mx < 0 or mx >= MAP_W or my < 0 or my >= MAP_H:
                safe_addstr(scr, sy, sx, ' ')
                continue

            in_fov = (mx, my) in gs.visible and not blind

            if in_fov:
                gs.explored[my][mx] = True

            if mx == p.x and my == p.y:
                player_pair = C_PLAYER_256 if HAS_256_COLORS else C_PLAYER
                safe_addstr(scr, sy, sx, '@', curses.color_pair(player_pair) | curses.A_BOLD)
                continue

            # Enemy
            if in_fov:
                enemy_here = None
                for e in gs.enemies:
                    if e.x == mx and e.y == my and e.is_alive():
                        enemy_here = e
                        break
                if enemy_here:
                    if enemy_here.disguised:
                        # Disguised mimic looks like gold
                        gold_pair = C_GOLD_256 if HAS_256_COLORS else C_GOLD
                        safe_addstr(scr, sy, sx, '$',
                                   curses.color_pair(gold_pair) | curses.A_BOLD)
                    elif enemy_here.alertness == "asleep":
                        # Asleep enemies render with 'z' and dim
                        safe_addstr(scr, sy, sx, 'z',
                                   curses.color_pair(C_DARK) | curses.A_DIM)
                    else:
                        attr = curses.color_pair(enemy_here.color)
                        if enemy_here.boss:
                            attr |= curses.A_BOLD
                        elif enemy_here.alertness == "alert":
                            attr |= curses.A_BOLD
                        # unwary enemies render at normal brightness (no A_BOLD)
                        safe_addstr(scr, sy, sx, enemy_here.char, attr)
                    continue

            # Items
            if in_fov:
                item_here = None
                for it in gs.items:
                    if it.x == mx and it.y == my:
                        item_here = it
                        break
                if item_here:
                    safe_addstr(scr, sy, sx, item_here.char,
                               curses.color_pair(item_here.color) | curses.A_BOLD)
                    continue

            # Vignettes (show char on map before player steps on them)
            if in_fov:
                vig_here = None
                for vig in gs.vignettes:
                    if vig["x"] == mx and vig["y"] == my and not vig["examined"]:
                        vig_here = vig
                        break
                if vig_here:
                    safe_addstr(scr, sy, sx, '?',
                               curses.color_pair(C_MAGENTA) | curses.A_BOLD)
                    continue

            # Tiles
            if in_fov:
                _draw_tile(scr, sy, sx, gs.tiles[my][mx], True, p.floor, gs.active_branch)
            elif gs.explored[my][mx]:
                _draw_tile(scr, sy, sx, gs.tiles[my][mx], False, p.floor, gs.active_branch)
            else:
                safe_addstr(scr, sy, sx, ' ')


def _draw_tile(scr: Any, sy: int, sx: int, tile: int, lit: bool, floor_num: int,
               active_branch: str | None = None) -> None:
    ch = get_tile_char(tile)

    # 256-color themed rendering
    if HAS_256_COLORS:
        theme = _floor_theme_name(floor_num, active_branch)
        wall_p, wall_dim_p, floor_p, floor_dim_p = _get_theme_pairs(theme)
        if lit:
            if tile in (T_WALL, T_SECRET_WALL):
                a = curses.color_pair(wall_p)
            elif tile in (T_FLOOR, T_CORRIDOR, T_SHOP_FLOOR, T_TRAP_HIDDEN):
                a = curses.color_pair(floor_p) | curses.A_DIM
            elif tile == T_DOOR:
                a = curses.color_pair(C_YELLOW) | curses.A_BOLD
            elif tile in (T_STAIRS_DOWN, T_STAIRS_UP):
                a = curses.color_pair(C_YELLOW) | curses.A_BOLD
            elif tile == T_WATER:
                a = curses.color_pair(C_WATER_256) | curses.A_BOLD
            elif tile == T_LAVA:
                a = curses.color_pair(C_LAVA_256) | curses.A_BOLD
            elif tile == T_FOUNTAIN:
                a = curses.color_pair(C_WATER_256) | curses.A_BOLD
            elif tile == T_SHRINE:
                a = curses.color_pair(C_SHRINE) | curses.A_BOLD
            elif tile == T_ALCHEMY_TABLE:
                a = curses.color_pair(C_CYAN) | curses.A_BOLD
            elif tile == T_WALL_TORCH:
                a = curses.color_pair(C_GOLD_256) | curses.A_BOLD
            elif tile in (T_PEDESTAL_UNLIT, T_SWITCH_OFF):
                a = curses.color_pair(wall_dim_p)
            elif tile in (T_PEDESTAL_LIT, T_SWITCH_ON):
                a = curses.color_pair(C_GOLD_256) | curses.A_BOLD
            elif tile == T_STAIRS_LOCKED:
                a = curses.color_pair(C_RED) | curses.A_BOLD
            elif tile == T_TRAP_VISIBLE:
                a = curses.color_pair(C_RED) | curses.A_BOLD
            elif tile == T_ENCHANT_ANVIL:
                a = curses.color_pair(C_CYAN) | curses.A_BOLD
            else:
                a = curses.color_pair(floor_p)
        else:
            # Explored but not in FOV
            if tile in (T_WALL, T_SECRET_WALL):
                a = curses.color_pair(wall_dim_p)
            elif tile in (T_STAIRS_DOWN, T_STAIRS_UP):
                a = curses.color_pair(C_YELLOW) | curses.A_DIM
            else:
                a = curses.color_pair(floor_dim_p)
        safe_addstr(scr, sy, sx, ch, a)
        return

    # Fallback: standard 16-color rendering
    if lit:
        if tile == T_WALL:
            if floor_num <= 3:
                a = curses.color_pair(C_WHITE) | curses.A_DIM
            elif floor_num <= 6:
                a = curses.color_pair(C_GREEN) | curses.A_DIM
            elif floor_num <= 9:
                a = curses.color_pair(C_DARK) | curses.A_DIM
            elif floor_num <= 12:
                a = curses.color_pair(C_RED) | curses.A_DIM
            else:
                a = curses.color_pair(C_MAGENTA) | curses.A_DIM
        elif tile in (T_FLOOR, T_CORRIDOR, T_SHOP_FLOOR):
            a = curses.color_pair(C_WHITE) | curses.A_DIM
        elif tile == T_DOOR:
            a = curses.color_pair(C_YELLOW) | curses.A_BOLD
        elif tile in (T_STAIRS_DOWN, T_STAIRS_UP):
            a = curses.color_pair(C_YELLOW) | curses.A_BOLD
        elif tile == T_WATER:
            a = curses.color_pair(C_WATER) | curses.A_BOLD
        elif tile == T_LAVA:
            a = curses.color_pair(C_LAVA) | curses.A_BOLD
        elif tile == T_SHRINE:
            a = curses.color_pair(C_SHRINE) | curses.A_BOLD
        elif tile == T_ALCHEMY_TABLE:
            a = curses.color_pair(C_CYAN) | curses.A_BOLD
        elif tile == T_WALL_TORCH:
            a = curses.color_pair(C_YELLOW) | curses.A_BOLD
        elif tile in (T_PEDESTAL_UNLIT, T_SWITCH_OFF):
            a = curses.color_pair(C_DARK) | curses.A_BOLD
        elif tile in (T_PEDESTAL_LIT, T_SWITCH_ON):
            a = curses.color_pair(C_YELLOW) | curses.A_BOLD
        elif tile == T_STAIRS_LOCKED:
            a = curses.color_pair(C_RED) | curses.A_BOLD
        elif tile == T_FOUNTAIN:
            a = curses.color_pair(C_WATER) | curses.A_BOLD
        elif tile == T_SECRET_WALL:
            if floor_num <= 3:
                a = curses.color_pair(C_WHITE) | curses.A_DIM
            elif floor_num <= 6:
                a = curses.color_pair(C_GREEN) | curses.A_DIM
            elif floor_num <= 9:
                a = curses.color_pair(C_DARK) | curses.A_DIM
            elif floor_num <= 12:
                a = curses.color_pair(C_RED) | curses.A_DIM
            else:
                a = curses.color_pair(C_MAGENTA) | curses.A_DIM
        elif tile == T_TRAP_HIDDEN:
            a = curses.color_pair(C_WHITE) | curses.A_DIM
        elif tile == T_TRAP_VISIBLE:
            a = curses.color_pair(C_RED) | curses.A_BOLD
        else:
            a = curses.color_pair(C_WHITE)
    else:
        a = curses.color_pair(C_DARK) | curses.A_DIM
        if tile in (T_STAIRS_DOWN, T_STAIRS_UP):
            a = curses.color_pair(C_YELLOW) | curses.A_DIM
    safe_addstr(scr, sy, sx, ch, a)


def render_sidebar(scr: Any, gs: GameState) -> None:
    p = gs.player
    x = STAT_X
    sw = SCREEN_W - x - 1  # available sidebar width
    theme = THEMES[p.floor-1] if p.floor <= len(THEMES) else "Abyss"

    if gs.active_branch and gs.active_branch in BRANCH_DEFS:
        branch_name = BRANCH_DEFS[gs.active_branch]["name"]
        safe_addstr(scr, 0, x, f" {branch_name}", curses.color_pair(C_TITLE) | curses.A_BOLD)
    else:
        safe_addstr(scr, 0, x, f" {theme}", curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 1, x, f" Floor {p.floor}/{MAX_FLOORS}", curses.color_pair(C_UI))
    class_label = CHARACTER_CLASSES[p.player_class]["name"] if p.player_class and p.player_class in CHARACTER_CLASSES else ""
    if class_label:
        safe_addstr(scr, 2, x, f" Lv:{p.level} {class_label}", curses.color_pair(C_UI))
    else:
        safe_addstr(scr, 2, x, f" Lv:{p.level} XP:{p.xp}/{p.xp_next}", curses.color_pair(C_UI))

    # HP bar with color coding (Phase 2 item 9)
    hp_pct = max(0, p.hp / p.max_hp) if p.max_hp > 0 else 0
    hpc = C_GREEN if hp_pct > 0.6 else (C_YELLOW if hp_pct > 0.3 else C_RED)
    hp_attr = curses.color_pair(hpc)
    if hp_pct <= 0.2:
        hp_attr |= curses.A_BOLD  # Bold red when critically low
    bw = 12
    filled = int(hp_pct * bw)
    bar = '#' * filled + '-' * (bw - filled)
    safe_addstr(scr, 4, x, " HP:", curses.color_pair(C_WHITE))
    safe_addstr(scr, 4, x+4, bar, hp_attr)
    hp_num_attr = hp_attr
    if hp_pct <= 0.2:
        hp_num_attr |= curses.A_BLINK  # Blink when critically low
    safe_addstr(scr, 5, x, f"    {p.hp}/{p.max_hp}", hp_num_attr)

    # Mana bar
    mana_pct = max(0, p.mana / p.max_mana) if p.max_mana > 0 else 0
    mc = C_CYAN if mana_pct > 0.3 else C_RED
    mfilled = int(mana_pct * bw)
    mbar = '#' * mfilled + '-' * (bw - mfilled)
    safe_addstr(scr, 6, x, " MP:", curses.color_pair(C_WHITE))
    safe_addstr(scr, 6, x+4, mbar, curses.color_pair(mc))
    safe_addstr(scr, 7, x, f"    {p.mana}/{p.max_mana}", curses.color_pair(mc))

    # Hunger
    hpct = p.hunger / 100.0
    hc = C_GREEN if hpct > 0.5 else (C_YELLOW if hpct > 0.2 else C_RED)
    hl = "Full" if hpct > 0.7 else ("Hungry" if hpct > 0.3 else "Starving!")
    safe_addstr(scr, 8, x, f" {hl}", curses.color_pair(hc))

    # Torch with current/max format (Phase 2 item 12) + lit/unlit status
    tpct = p.torch_fuel / TORCH_MAX_FUEL
    tc = C_YELLOW if tpct > 0.25 else (C_RED if tpct > 0 else C_DARK)
    torch_status = "" if p.torch_lit else "[OFF]"
    if not p.torch_lit:
        tc = C_DARK
    safe_addstr(scr, 9, x, f" Torch:{p.torch_fuel}/{TORCH_MAX_FUEL}{torch_status}", curses.color_pair(tc))

    # Ammo counter: show arrows and throwing daggers if carried
    row = 10
    ammo_parts = []
    for inv in p.inventory:
        if inv.item_type == "arrow" and inv.count > 0:
            ammo_parts.append(f"Arr:{inv.count}")
        elif inv.item_type == "throwing_dagger" and inv.count > 0:
            ammo_parts.append(f"Dgr:{inv.count}")
    if ammo_parts:
        safe_addstr(scr, row, x, f" {' '.join(ammo_parts)}", curses.color_pair(C_WHITE))
        row += 1

    safe_addstr(scr, row, x, f" STR:{p.strength} DEF:{p.total_defense()}", curses.color_pair(C_WHITE))
    row += 1

    # Equipment names with stats on HUD (#5, #22)
    row += 1  # blank line
    name_w = min(SIDEBAR_NAME_WIDTH, sw - 5)  # 5 chars for " Wpn:" prefix
    if p.weapon:
        lo, hi = p.weapon.data["dmg"]
        b = p.weapon.data.get("bonus", 0)
        wpn = f"{p.weapon.display_name[:name_w-6]} {lo}-{hi}"
        if b:
            wpn += f"+{b}"
    else:
        wpn = "Fists"
    safe_addstr(scr, row, x, f" Wpn:{wpn}", curses.color_pair(C_WHITE))
    row += 1
    if p.armor:
        arm = f"{p.armor.display_name[:name_w-4]} [{p.armor.data['defense']}]"
    else:
        arm = "None"
    safe_addstr(scr, row, x, f" Arm:{arm}", curses.color_pair(C_BLUE))
    row += 1
    # Ranged weapon on HUD
    ranged = None
    for inv in p.inventory:
        if inv.item_type == "bow":
            ranged = inv
            break
        if inv.item_type == "wand":
            ranged = inv
            break
    if ranged:
        rng_name = ranged.display_name[:name_w]
        safe_addstr(scr, row, x, f" Rng:{rng_name}", curses.color_pair(C_YELLOW))
        row += 1
    rng = p.ring.display_name[:name_w] if p.ring else ""
    if rng:
        safe_addstr(scr, row, x, f" R:{rng}", curses.color_pair(C_CYAN))
        row += 1
    # Elemental resistances on HUD
    resists = p.player_resists()
    if resists:
        res_str = " ".join(sorted(resists))
        safe_addstr(scr, row, x, f" Res:{res_str}", curses.color_pair(C_CYAN))
        row += 1
    # Technique/skill hint on HUD (#2/#4)
    cd_str = f" CD:{p.ability_cooldown}" if p.ability_cooldown > 0 else ""
    if p.player_class == "mage":
        safe_addstr(scr, row, x, f" [z]Spells [C]ArcBlast{cd_str}", curses.color_pair(C_CYAN))
        row += 1
    elif p.player_class == "warrior":
        safe_addstr(scr, row, x, f" [C]BattleCry{cd_str}", curses.color_pair(C_GREEN))
        row += 1
        if p.known_abilities:
            abilities_list = list(p.known_abilities)
            if len(abilities_list) == 1:
                ab_name = abilities_list[0][:12]
                safe_addstr(scr, row, x, f" [t]{ab_name}", curses.color_pair(C_GREEN))
            else:
                safe_addstr(scr, row, x, f" [t]{len(abilities_list)} Techniques", curses.color_pair(C_GREEN))
            row += 1
    elif p.player_class == "rogue":
        safe_addstr(scr, row, x, f" [C]ShadowStep{cd_str}", curses.color_pair(C_GREEN))
        row += 1
        if p.known_abilities:
            abilities_list = list(p.known_abilities)
            if len(abilities_list) == 1:
                ab_name = abilities_list[0][:12]
                safe_addstr(scr, row, x, f" [t]{ab_name}", curses.color_pair(C_GREEN))
            else:
                safe_addstr(scr, row, x, f" [t]{len(abilities_list)} Techniques", curses.color_pair(C_GREEN))
            row += 1
    elif p.player_class and p.known_abilities:
        abilities_list = list(p.known_abilities)
        if len(abilities_list) == 1:
            ab_name = abilities_list[0][:12]
            safe_addstr(scr, row, x, f" [t]{ab_name}", curses.color_pair(C_GREEN))
        else:
            safe_addstr(scr, row, x, f" [t]{len(abilities_list)} Techniques", curses.color_pair(C_GREEN))
        row += 1

    row += 1  # blank line
    safe_addstr(scr, row, x, f" Gold:{p.gold}", curses.color_pair(C_GOLD))
    row += 1
    safe_addstr(scr, row, x, f" Kills:{p.kills}", curses.color_pair(C_RED))
    row += 1
    # Turn counter in HUD (Phase 2 item 11)
    safe_addstr(scr, row, x, f" Turn:{gs.turn_count}", curses.color_pair(C_DARK))
    row += 1

    # Status effects with overflow cap (Phase 2 item 6)
    STATUS_COLORS = {"Poison": C_GREEN, "Paralysis": C_YELLOW, "Fear": C_MAGENTA,
                     "Berserk": C_RED, "Blindness": C_DARK, "Speed": C_CYAN,
                     "Strength": C_RED, "Resistance": C_BLUE, "Confusion": C_MAGENTA,
                     "Frozen": C_CYAN, "Silence": C_MAGENTA}
    y = row
    max_effect_lines = SCREEN_H - 1 - y  # lines available
    effects_list = list(p.status_effects.items())
    for i, (eff, turns) in enumerate(effects_list):
        if i >= max_effect_lines - 1 and len(effects_list) > max_effect_lines:
            remaining = len(effects_list) - i
            safe_addstr(scr, y, x, f" +{remaining} more", curses.color_pair(C_MAGENTA))
            break
        if y < SCREEN_H - 1:
            eff_color = STATUS_COLORS.get(eff, C_MAGENTA)
            safe_addstr(scr, y, x, f" {eff}({turns})", curses.color_pair(eff_color))
            y += 1


def render_messages(scr: Any, gs: GameState) -> None:
    msgs = list(gs.messages)
    start_y = VIEW_H
    # Build display lines with word-wrap (Phase 2 item 8)
    display_lines = []
    for text, color in msgs:
        if len(text) <= VIEW_W:
            display_lines.append((text, color))
        else:
            # Word-wrap long messages
            words = text.split(' ')
            line = ''
            for word in words:
                if len(line) + len(word) + 1 <= VIEW_W:
                    line = line + ' ' + word if line else word
                else:
                    if line:
                        display_lines.append((line, color))
                    line = word[:VIEW_W]  # truncate single long words
            if line:
                display_lines.append((line, color))
    # Show last MSG_H lines
    for i in range(min(MSG_H, len(display_lines))):
        idx = len(display_lines) - MSG_H + i
        if idx < 0:
            continue
        text, color = display_lines[idx]
        safe_addstr(scr, start_y + i, 0, text[:VIEW_W], curses.color_pair(color))


def render_game(scr: Any, gs: GameState) -> None:
    scr.erase()
    fov_radius = gs.player.get_torch_radius()
    if "Blindness" in gs.player.status_effects:
        fov_radius = 1
    compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
    # Wall torch lighting (#1): tiles near wall torches are also visible if in LOS
    if gs.wall_torches:
        wall_torch_radius = 5
        for wtx, wty in gs.wall_torches:
            if abs(wtx - gs.player.x) + abs(wty - gs.player.y) <= fov_radius + wall_torch_radius:
                # Add tiles lit by this torch that are in LOS from player
                for dy2 in range(-wall_torch_radius, wall_torch_radius + 1):
                    for dx2 in range(-wall_torch_radius, wall_torch_radius + 1):
                        lx, ly = wtx + dx2, wty + dy2
                        if 0 <= lx < MAP_W and 0 <= ly < MAP_H:
                            if dx2*dx2 + dy2*dy2 <= wall_torch_radius * wall_torch_radius:
                                if _has_los(gs.tiles, gs.player.x, gs.player.y, lx, ly):
                                    gs.visible.add((lx, ly))
    # Lava light: lava tiles emit light radius 3
    lava_radius = 3
    for ly2 in range(max(0, gs.player.y - fov_radius - lava_radius),
                      min(MAP_H, gs.player.y + fov_radius + lava_radius + 1)):
        for lx2 in range(max(0, gs.player.x - fov_radius - lava_radius),
                          min(MAP_W, gs.player.x + fov_radius + lava_radius + 1)):
            if gs.tiles[ly2][lx2] == T_LAVA:
                for dy3 in range(-lava_radius, lava_radius + 1):
                    for dx3 in range(-lava_radius, lava_radius + 1):
                        nlx, nly = lx2 + dx3, ly2 + dy3
                        if (0 <= nlx < MAP_W and 0 <= nly < MAP_H
                                and dx3*dx3 + dy3*dy3 <= lava_radius * lava_radius):
                            if _has_los(gs.tiles, gs.player.x, gs.player.y, nlx, nly):
                                gs.visible.add((nlx, nly))
    # Shop discovery: fire message when player first sees a shop tile (#10)
    if not gs.shop_discovered and gs.shops:
        for vx, vy in gs.visible:
            if gs.tiles[vy][vx] == T_SHOP_FLOOR:
                gs.shop_discovered = True
                gs.msg("You see a merchant's stall nearby.", C_GOLD)
                break
    render_map(scr, gs)
    render_sidebar(scr, gs)
    render_messages(scr, gs)
    safe_addstr(scr, SCREEN_H-1, 0,
               " ?:Help i:Inv f:Fire z:Spell t:Tech /:Search T:Torch >:Down",
               curses.color_pair(C_DARK) | curses.A_DIM)
    scr.refresh()


# ============================================================
# UI SCREENS
# ============================================================

def show_title(scr: Any) -> None:
    scr.erase()
    h, w = scr.getmaxyx()
    art = [
        " ____  _____ ____ _____ _   _ ____",
        "|  _ \\| ____|  _ \\_   _| | | / ___|",
        "| | | |  _| | |_) || | | |_| \\___ \\",
        "| |_| | |___|  __/ | | |  _  |___) |",
        "|____/|_____|_|    |_| |_| |_|____/",
        "",
        "  ___  _____   ____  ____  _____    _    ____",
        " / _ \\|  ___| |  _ \\|  _ \\| ____|  / \\  |  _ \\",
        "| | | | |_    | | | | |_) |  _|   / _ \\ | | | |",
        "| |_| |  _|   | |_| |  _ <| |___ / ___ \\| |_| |",
        " \\___/|_|     |____/|_| \\_\\_____/_/   \\_\\____/",
    ]
    sy = max(0, h//2 - 12)
    for i, line in enumerate(art):
        x = max(0, (w - len(line))//2)
        safe_addstr(scr, sy+i, x, line, curses.color_pair(C_RED) | curses.A_BOLD)

    sub = "A Terminal Roguelike"
    safe_addstr(scr, sy+12, max(0,(w-len(sub))//2), sub, curses.color_pair(C_YELLOW))

    flavor = [
        "Thornhaven is doomed. Beneath the old keep,",
        "fifteen floors of darkness hide the Dread Lord.",
        "You are the last one foolish enough to descend.",
    ]
    for i, line in enumerate(flavor):
        safe_addstr(scr, sy+14+i, max(0,(w-len(line))//2), line, curses.color_pair(C_WHITE))

    prompt = "[ Press any key to begin ]"
    safe_addstr(scr, sy+19, max(0,(w-len(prompt))//2), prompt,
               curses.color_pair(C_YELLOW) | curses.A_BOLD)
    ctrl = "Move: WASD / Arrows / hjklyubn"
    safe_addstr(scr, sy+21, max(0,(w-len(ctrl))//2), ctrl, curses.color_pair(C_DARK))

    scr.refresh()
    scr.getch()


def show_help(scr: Any) -> None:
    """Show comprehensive help screen with categories (Phase 5, item 24)."""
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    pages = [
        [
            ("DEPTHS OF DREAD - Help (1/2)", C_TITLE),
            ("", C_WHITE),
            ("=== Movement ===", C_YELLOW),
            ("Arrow keys / WASD / hjkl  Move (cardinal)", C_WHITE),
            ("yubn                      Move (diagonal)", C_WHITE),
            ("", C_WHITE),
            ("=== Combat ===", C_YELLOW),
            ("[Walk into enemy]  Melee attack", C_WHITE),
            ("f  Fire projectile (arrows, daggers, wands)", C_WHITE),
            ("z  Cast spell      (opens spell menu)", C_WHITE),
            ("t  Techniques      (class combat abilities)", C_WHITE),
            ("Tab  Auto-fight    (attack nearest enemy)", C_WHITE),
            ("", C_WHITE),
            ("=== Items ===", C_YELLOW),
            (",  Pick up item    i  Open inventory", C_WHITE),
            ("x+letter  Drop     $  Browse shop", C_WHITE),
            ("", C_WHITE),
            ("=== Exploration ===", C_YELLOW),
            ("o  Auto-explore    x  Examine/look", C_WHITE),
            (">  Descend stairs  <  Ascend stairs", C_WHITE),
            (".  Wait/rest       R  Rest until healed", C_WHITE),
            ("T  Toggle torch    p  Pray at shrine", C_WHITE),
            ("/  Search for traps  D  Disarm trap", C_WHITE),
        ],
        [
            ("DEPTHS OF DREAD - Help (2/2)", C_TITLE),
            ("", C_WHITE),
            ("=== Info ===", C_YELLOW),
            ("c  Character sheet  m  Message log", C_WHITE),
            ("M  Bestiary (Monster Memory)", C_WHITE),
            ("S  Lifetime stats   Q  Quit (Shift+Q)", C_WHITE),
            ("?  This help screen", C_WHITE),
            ("", C_WHITE),
            ("=== Symbols ===", C_YELLOW),
            (") Weapon  [ Armor  ! Potion  ? Scroll", C_WHITE),
            ("% Food    = Ring   } Bow     / Wand", C_WHITE),
            ("> Down    < Up     + Door    ~ Water", C_WHITE),
            ("_ Shrine  $ Gold   @ You     & Alchemy", C_WHITE),
            ("! Wall Torch  * Pedestal  X Locked Stairs", C_WHITE),
            ("{ Fountain    ^ Trap (visible)", C_WHITE),
            ("", C_WHITE),
            ("=== Game Mechanics ===", C_YELLOW),
            ("Hunger: Depletes each turn. Eat food (%) to restore.", C_WHITE),
            ("Torches: Light fades. Wall torches (!) light rooms.", C_WHITE),
            ("  Grab wall torches with ,  Puzzles: * and switches.", C_WHITE),
            ("Shrines: Prayer grants boons, but beware curses.", C_WHITE),
            ("Shops on odd floors (1,3,5,7,...). Press $ to browse.", C_WHITE),
            ("J=Journal  e=Interact (alchemy, pedestal, fountain)", C_WHITE),
            ("Inventory: [/] scroll, S sort. Better armor auto-equips.", C_WHITE),
            ("Traps: Hidden traps hurt. / to search. D to disarm.", C_WHITE),
            ("Resist: Rings grant fire/cold/poison resistance.", C_WHITE),
            ("Water: Blocks fire aura. Lightning arcs in water.", C_WHITE),
            ("Stealth: Enemies spawn asleep(z) or unwary.", C_WHITE),
            ("  Noise wakes them. Rogue=50% less noise.", C_WHITE),
            ("  Attack sleeping/unwary = guaranteed crit!", C_WHITE),
            ("Q=Save & Quit (auto-loads). S=Lifetime stats.", C_WHITE),
        ],
    ]
    for page in pages:
        scr.erase()
        for i, (t, c) in enumerate(page):
            if i >= SCREEN_H - 1:
                break
            safe_addstr(scr, i, 1, t, curses.color_pair(c))
        safe_addstr(scr, SCREEN_H-1, 1, "[ Press any key for next / ESC to close ]",
                   curses.color_pair(C_YELLOW))
        scr.refresh()
        key = scr.getch()
        if key == 27:
            return


def _inv_letter(idx: int) -> str:
    """Map inventory index to display letter: a-z then A-Z."""
    if idx < 26:
        return chr(ord('a') + idx)
    elif idx < 52:
        return chr(ord('A') + idx - 26)
    return '?'

def _inv_key_to_idx(key: int, scroll_offset: int = 0) -> int:
    """Convert keypress to inventory index (accounting for scroll)."""
    if ord('a') <= key <= ord('z'):
        return key - ord('a') + scroll_offset
    elif ord('A') <= key <= ord('Z'):
        return key - ord('A') + 26 + scroll_offset
    return -1

def show_bestiary(scr: Any, gs: GameState) -> None:
    """Show the Monster Memory / Bestiary screen (M key)."""
    # Flush buffered keypresses
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)

    # Collect encountered monster types sorted by encounters (desc)
    entries = []
    for etype, data in gs.bestiary.items():
        if etype in ENEMY_TYPES and data["encountered"] > 0:
            entries.append((etype, data))
    entries.sort(key=lambda x: x[1]["encountered"], reverse=True)

    if not entries:
        scr.erase()
        safe_addstr(scr, 2, 4, "BESTIARY - Monster Memory", curses.color_pair(C_TITLE) | curses.A_BOLD)
        safe_addstr(scr, 4, 4, "No monsters encountered yet.", curses.color_pair(C_DARK))
        safe_addstr(scr, 6, 4, "Press any key to return.", curses.color_pair(C_WHITE))
        scr.refresh()
        scr.getch()
        return

    # Pagination
    page_size = max(1, SCREEN_H - 6)
    page = 0
    total_pages = max(1, (len(entries) + page_size - 1) // page_size)

    while True:
        scr.erase()
        safe_addstr(scr, 0, 4, f"BESTIARY - Monster Memory (Page {page+1}/{total_pages})",
                    curses.color_pair(C_TITLE) | curses.A_BOLD)
        safe_addstr(scr, 1, 4, "Knowledge grows with each encounter.", curses.color_pair(C_DARK))

        y = 3
        start = page * page_size
        end = min(start + page_size, len(entries))
        for i in range(start, end):
            etype, data = entries[i]
            edef = ENEMY_TYPES[etype]
            enc = data["encountered"]
            killed = data["killed"]

            # Progressive reveal based on encounter count
            name = edef["name"]
            char = edef.get("char", '?')
            # Tier 1: 1+ encounters — name and basic description
            line = f" {char} {name}"
            if enc >= 1:
                line += f"  (Seen: {enc}, Killed: {killed})"
            safe_addstr(scr, y, 2, line, curses.color_pair(C_WHITE))
            y += 1

            # Tier 2: 3+ encounters — show HP and damage range
            if enc >= 3:
                hp_str = f"HP: ~{edef['hp']}"
                dmg_lo, dmg_hi = edef.get("dmg", (0, 0))
                dmg_str = f"DMG: {dmg_lo}-{dmg_hi}"
                def_str = f"DEF: {edef.get('defense', 0)}"
                safe_addstr(scr, y, 6, f"{hp_str}  {dmg_str}  {def_str}", curses.color_pair(C_UI))
                y += 1

            # Tier 3: 5+ encounters — show observed abilities
            if enc >= 5 and data["abilities"]:
                ab_str = ", ".join(data["abilities"])
                safe_addstr(scr, y, 6, f"Abilities: {ab_str}", curses.color_pair(C_YELLOW))
                y += 1

            # Tier 4: 10+ encounters — show damage stats and resistances
            if enc >= 10:
                avg_dealt = data["dmg_dealt"] // max(1, enc)
                avg_taken = data["dmg_taken"] // max(1, enc)
                safe_addstr(scr, y, 6, f"Avg dmg dealt: {avg_dealt}  Avg dmg taken: {avg_taken}",
                            curses.color_pair(C_CYAN))
                y += 1
                # Resistances/vulnerabilities from definition
                resists = edef.get("resists", [])
                vulns = edef.get("vulnerable", [])
                if resists or vulns:
                    rv_parts = []
                    if resists:
                        rv_parts.append(f"Resists: {', '.join(resists)}")
                    if vulns:
                        rv_parts.append(f"Weak to: {', '.join(vulns)}")
                    safe_addstr(scr, y, 6, "  ".join(rv_parts), curses.color_pair(C_GREEN))
                    y += 1

            if y >= SCREEN_H - 2:
                break

        nav = "[ESC/q] Close"
        if total_pages > 1:
            nav += "  [n] Next  [p] Prev"
        safe_addstr(scr, SCREEN_H - 1, 4, nav, curses.color_pair(C_DARK))
        scr.refresh()

        key = scr.getch()
        if key in (27, ord('q'), ord('Q'), ord('m'), ord('M')):
            break
        elif key == ord('n') and page < total_pages - 1:
            page += 1
        elif key == ord('p') and page > 0:
            page -= 1


def show_inventory(scr: Any, gs: GameState) -> bool:
    p = gs.player
    scroll_offset = 0
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    while True:
        scr.erase()
        safe_addstr(scr, 0, 1, "INVENTORY", curses.color_pair(C_TITLE) | curses.A_BOLD)
        # Stats header (#23)
        hp_pct = p.hp / p.max_hp if p.max_hp > 0 else 0
        hpc = C_GREEN if hp_pct > 0.6 else (C_YELLOW if hp_pct > 0.3 else C_RED)
        safe_addstr(scr, 1, 1, f"HP:{p.hp}/{p.max_hp} MP:{p.mana}/{p.max_mana} Hunger:{int(p.hunger)}%",
                   curses.color_pair(hpc))
        scroll_count = sum(1 for it in p.inventory if it.item_type == "scroll")
        non_scroll = sum(1 for it in p.inventory if it.item_type != "scroll")
        if scroll_count > 0:
            cap_str = f"({non_scroll}/{p.carry_capacity} items + {scroll_count} scrolls, {p.gold}g)"
        else:
            cap_str = f"({len(p.inventory)}/{p.carry_capacity}, {p.gold}g)"
        wpn_str = p.weapon.display_name if p.weapon else "Fists"
        arm_str = p.armor.display_name if p.armor else "None"
        safe_addstr(scr, 2, 1, f"Wpn:{wpn_str}  Arm:{arm_str}  {cap_str}",
                   curses.color_pair(C_DARK))
        header_rows = 3
        visible_rows = SCREEN_H - header_rows - 2  # leave room for footer
        if not p.inventory:
            safe_addstr(scr, header_rows + 1, 2, "Your pack is empty.", curses.color_pair(C_DARK))
        else:
            # Clamp scroll offset
            max_offset = max(0, len(p.inventory) - visible_rows)
            scroll_offset = max(0, min(scroll_offset, max_offset))
            # Show scroll indicators
            if scroll_offset > 0:
                safe_addstr(scr, header_rows, SCREEN_W - 12, "^ more above", curses.color_pair(C_DARK))
            if scroll_offset + visible_rows < len(p.inventory):
                safe_addstr(scr, SCREEN_H - 3, SCREEN_W - 12, "v more below", curses.color_pair(C_DARK))
            for vi, i in enumerate(range(scroll_offset, min(len(p.inventory), scroll_offset + visible_rows))):
                item = p.inventory[i]
                letter = _inv_letter(i)
                prefix = "(E) " if item.equipped else ""
                name = f"{letter}) {prefix}{item.display_name}"
                if item.item_type == "weapon":
                    lo, hi = item.data["dmg"]
                    b = item.data.get("bonus", 0)
                    name += f" [{lo}-{hi}+{b}]"
                elif item.item_type == "armor":
                    name += f" [Def:{item.data['defense']}]"
                elif item.item_type == "bow":
                    lo, hi = item.data["dmg"]
                    name += f" [{lo}-{hi} rng:{item.data.get('range',6)}]"
                elif item.item_type == "wand":
                    name += f" [{item.data.get('charges',0)} chg]"
                # Journal hint for identified potions/scrolls (#6)
                if item.item_type == "potion" and item.identified:
                    hint = gs.journal.get(f"Potion of {item.data['effect']}", "")
                    if hint:
                        name += f" ({hint[:20]})"
                elif item.item_type == "scroll" and item.identified:
                    hint = gs.journal.get(f"Scroll of {item.data['effect']}", "")
                    if hint:
                        name += f" ({hint[:20]})"
                safe_addstr(scr, header_rows + vi, 2, name[:SCREEN_W-14], curses.color_pair(item.color))

        footer = "[a-z/A-Z] Use  [x] Drop  [S] Sort  [PgUp/Dn] Scroll  [ESC] Close"
        safe_addstr(scr, SCREEN_H-1, 1, footer[:SCREEN_W-2], curses.color_pair(C_DARK))
        scr.refresh()
        key = scr.getch()
        if key == 27:
            return False
        elif key == curses.KEY_PPAGE or key == ord('['):
            scroll_offset = max(0, scroll_offset - visible_rows)
        elif key == curses.KEY_NPAGE or key == ord(']'):
            scroll_offset = min(max(0, len(p.inventory) - visible_rows), scroll_offset + visible_rows)
        elif key == curses.KEY_UP:
            scroll_offset = max(0, scroll_offset - 1)
        elif key == curses.KEY_DOWN:
            scroll_offset = min(max(0, len(p.inventory) - visible_rows), scroll_offset + 1)
        elif key == ord('x'):
            safe_addstr(scr, SCREEN_H-1, 1, "Drop which? (letter)    ", curses.color_pair(C_YELLOW))
            scr.refresh()
            dk = scr.getch()
            idx = _inv_key_to_idx(dk, 0)
            if 0 <= idx < len(p.inventory):
                item = p.inventory[idx]
                if item.equipped:
                    item.equipped = False
                    if item.item_type == "weapon":
                        p.weapon = None
                    elif item.item_type == "armor":
                        p.armor = None
                    elif item.item_type == "ring":
                        p.ring = None
                    elif item.item_type == "bow":
                        p.bow = None
                item.x = p.x
                item.y = p.y
                gs.items.append(item)
                p.inventory.remove(item)
                gs.msg(f"Dropped {item.display_name}.", C_WHITE)
        elif key == ord('S'):
            # Inventory sort cycling (#12)
            sort_mode = getattr(gs, '_inv_sort_mode', 0)
            sort_mode = (sort_mode + 1) % 3
            gs._inv_sort_mode = sort_mode
            if sort_mode == 1:
                p.inventory.sort(key=lambda it: (it.item_type, it.display_name))
                gs.msg("Sorted by type.", C_WHITE)
            elif sort_mode == 2:
                p.inventory.sort(key=lambda it: it.display_name)
                gs.msg("Sorted by name.", C_WHITE)
            else:
                gs.msg("Default order.", C_WHITE)
            # Re-link equipped references after sort
            for it in p.inventory:
                if it.equipped:
                    if it.item_type == "weapon":
                        p.weapon = it
                    elif it.item_type == "armor":
                        p.armor = it
                    elif it.item_type == "ring":
                        p.ring = it
                    elif it.item_type == "bow":
                        p.bow = it
        else:
            idx = _inv_key_to_idx(key, 0)
            if 0 <= idx < len(p.inventory):
                item = p.inventory[idx]
                if item.item_type == "weapon":
                    if item.equipped:
                        item.equipped = False
                        p.weapon = None
                        gs.msg(f"Unequipped {item.display_name}.", C_WHITE)
                    else:
                        if p.weapon:
                            p.weapon.equipped = False
                        item.equipped = True
                        p.weapon = item
                        gs.msg(f"Equipped {item.display_name}.", C_YELLOW)
                    return True
                elif item.item_type == "armor":
                    if item.equipped:
                        item.equipped = False
                        p.armor = None
                        gs.msg(f"Removed {item.display_name}.", C_WHITE)
                    else:
                        if p.armor:
                            p.armor.equipped = False
                        item.equipped = True
                        p.armor = item
                        gs.msg(f"Donned {item.display_name}.", C_BLUE)
                    return True
                elif item.item_type == "ring":
                    if item.equipped:
                        item.equipped = False
                        p.ring = None
                        gs.msg(f"Removed {item.display_name}.", C_WHITE)
                    else:
                        if p.ring:
                            p.ring.equipped = False
                        item.equipped = True
                        p.ring = item
                        gs.msg(f"Put on {item.display_name}.", C_CYAN)
                    return True
                elif item.item_type == "bow":
                    if item.equipped:
                        item.equipped = False
                        p.bow = None
                        gs.msg(f"Unequipped {item.display_name}.", C_WHITE)
                    else:
                        if p.bow:
                            p.bow.equipped = False
                        item.equipped = True
                        p.bow = item
                        gs.msg(f"Equipped {item.display_name}.", C_YELLOW)
                    return True
                elif item.item_type == "potion":
                    _get_items().use_potion(gs, item)
                    return True
                elif item.item_type == "scroll":
                    _get_items().use_scroll(gs, item)
                    return True
                elif item.item_type == "food":
                    _get_items().use_food(gs, item)
                    return True
                elif item.item_type == "torch":
                    fuel = item.data.get("fuel", 50)
                    p.torch_fuel = min(TORCH_MAX_FUEL, p.torch_fuel + fuel)
                    gs.msg(f"Refueled torch! (+{fuel} fuel)", C_YELLOW)
                    p.inventory.remove(item)
                    return True
                elif item.item_type == "wand":
                    # Use wand from inventory (#13)
                    charges = item.data.get("charges", 0)
                    if charges <= 0:
                        gs.msg("The wand is empty.", C_DARK)
                    else:
                        gs.msg("Fire wand which direction?", C_CYAN)
                        if scr:
                            render_game(scr, gs)
                            dk = scr.getch()
                            DIR_KEYS = {
                                curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
                                curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
                                ord('w'): (0,-1), ord('s'): (0,1),
                                ord('a'): (-1,0), ord('d'): (1,0),
                                ord('h'): (-1,0), ord('j'): (0,1),
                                ord('k'): (0,-1), ord('l'): (1,0),
                                ord('y'): (-1,-1), ord('u'): (1,-1),
                                ord('b'): (-1,1), ord('n'): (1,1),
                            }
                            if dk == 27:
                                gs.msg("Cancelled.", C_DARK)
                            elif dk in DIR_KEYS:
                                ddx, ddy = DIR_KEYS[dk]
                                _get_items()._launch_projectile(gs, ddx, ddy, "wand", item)
                                return True
                            else:
                                gs.msg("Invalid direction.", C_DARK)
    return False


def show_character(scr: Any, gs: GameState) -> None:
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    p = gs.player
    scr.erase()
    safe_addstr(scr, 0, 1, "CHARACTER SHEET", curses.color_pair(C_TITLE) | curses.A_BOLD)
    lines = [
        (f"Level: {p.level}  XP: {p.xp}/{p.xp_next}", C_WHITE),
        (f"Floor: {p.floor}  Deepest: {p.deepest_floor}", C_WHITE),
        ("", C_WHITE),
        (f"HP: {p.hp}/{p.max_hp}  MP: {p.mana}/{p.max_mana}", C_GREEN),
        (f"STR: {p.strength}  DEF: {p.total_defense()}  Evasion: {p.evasion_chance()}%", C_WHITE),
        (f"Hunger: {int(p.hunger)}%  Torch: {p.torch_fuel}/{TORCH_MAX_FUEL} {'[LIT]' if p.torch_lit else '[OFF]'}", C_YELLOW),
        ("", C_WHITE),
        (f"Weapon: {p.weapon.display_name if p.weapon else 'Fists'}", C_WHITE),
        (f"Armor:  {p.armor.display_name if p.armor else 'None'}", C_BLUE),
        (f"Ring:   {p.ring.display_name if p.ring else 'None'}", C_CYAN),
        ("", C_WHITE),
        (f"Gold: {p.gold} (earned:{p.gold_earned} spent:{p.gold_spent})  Kills: {p.kills}", C_GOLD),
        (f"Turns: {gs.turn_count}  Potions: {p.potions_drunk}  Food: {p.foods_eaten}", C_WHITE),
        (f"Traps: hit:{p.traps_triggered} found:{p.traps_found} disarmed:{p.traps_disarmed}", C_WHITE),
        ("", C_WHITE),
        ("Identified Potions:", C_MAGENTA),
    ]
    for eff in gs.id_potions:
        lines.append((f"  {gs.potion_ids[eff]} = {eff}", C_MAGENTA))
    lines.append(("Identified Scrolls:", C_YELLOW))
    for eff in gs.id_scrolls:
        lines.append((f"  {gs.scroll_ids[eff]} = {eff}", C_YELLOW))
    for i, (t, c) in enumerate(lines):
        if i+2 >= SCREEN_H-1:
            break
        safe_addstr(scr, i+2, 2, t, curses.color_pair(c))
    safe_addstr(scr, SCREEN_H-1, 1, "[ Press any key ]", curses.color_pair(C_YELLOW))
    scr.refresh()
    scr.getch()


def show_shop(scr: Any, gs: GameState) -> None:
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    p = gs.player
    shop = gs.get_shop_at(p.x, p.y)
    if not shop:
        gs.msg("No shop here.", C_WHITE)
        return
    _, shop_items = shop
    sell_mode = False
    while True:
        scr.erase()
        safe_addstr(scr, 0, 1, "THE MERCHANT'S STALL", curses.color_pair(C_GOLD) | curses.A_BOLD)
        safe_addstr(scr, 1, 1, f"Your gold: {p.gold}", curses.color_pair(C_GOLD))

        if not sell_mode:
            # --- BUY MODE ---
            safe_addstr(scr, 2, 1, '"Fair prices, friend."', curses.color_pair(C_WHITE))
            for i, si in enumerate(shop_items):
                if i+4 >= SCREEN_H-2:
                    break
                letter = chr(ord('a')+i)
                if si.sold:
                    safe_addstr(scr, i+4, 2, f"{letter}) [SOLD]", curses.color_pair(C_DARK))
                else:
                    pc = C_GREEN if p.gold >= si.price else C_RED
                    safe_addstr(scr, i+4, 2, f"{letter}) {si.item.display_name}",
                               curses.color_pair(si.item.color))
                    safe_addstr(scr, i+4, 34, f"{si.price}g", curses.color_pair(pc))
            safe_addstr(scr, SCREEN_H-1, 1, "[a-z] Buy  [s] Sell  [ESC] Leave", curses.color_pair(C_DARK))
        else:
            # --- SELL MODE ---
            safe_addstr(scr, 2, 1, '"What have you got for me?"', curses.color_pair(C_WHITE))
            sellable = [(i, item) for i, item in enumerate(p.inventory) if not item.equipped]
            if not sellable:
                safe_addstr(scr, 4, 2, "(nothing to sell — unequip items first)", curses.color_pair(C_DARK))
            for si_idx, (inv_idx, item) in enumerate(sellable):
                if si_idx+4 >= SCREEN_H-2:
                    break
                letter = chr(ord('a') + si_idx)
                val = item.sell_value
                safe_addstr(scr, si_idx+4, 2, f"{letter}) {item.display_name}",
                           curses.color_pair(item.color))
                safe_addstr(scr, si_idx+4, 34, f"+{val}g", curses.color_pair(C_GOLD))
            safe_addstr(scr, SCREEN_H-1, 1, "[a-z] Sell  [b] Buy  [ESC] Leave", curses.color_pair(C_DARK))

        scr.refresh()
        key = scr.getch()
        if key == 27:
            return
        if not sell_mode and key == ord('s'):
            sell_mode = True
            continue
        if sell_mode and key == ord('b'):
            sell_mode = False
            continue

        if not sell_mode:
            # BUY
            idx = key - ord('a')
            if 0 <= idx < len(shop_items):
                si = shop_items[idx]
                if si.sold:
                    gs.msg("Already sold.", C_DARK)
                elif p.gold < si.price:
                    gs.msg("Can't afford that.", C_RED)
                elif (si.item.item_type != "scroll" and
                      sum(1 for it in p.inventory if it.item_type != "scroll") >= p.carry_capacity):
                    gs.msg("Inventory full!", C_RED)
                else:
                    p.gold -= si.price
                    p.gold_spent += si.price
                    ic = Item(0, 0, si.item.item_type, si.item.subtype, si.item.data)
                    ic.identified = True
                    p.inventory.append(ic)
                    si.sold = True
                    gs.msg(f"Bought {ic.display_name} for {si.price}g.", C_GOLD)
        else:
            # SELL
            sellable = [(i, item) for i, item in enumerate(p.inventory) if not item.equipped]
            idx = key - ord('a')
            if 0 <= idx < len(sellable):
                inv_idx, item = sellable[idx]
                val = item.sell_value
                p.gold += val
                p.inventory.pop(inv_idx)
                gs.msg(f"Sold {item.display_name} for {val}g.", C_GOLD)


def show_messages(scr: Any, gs: GameState) -> None:
    scr.erase()
    safe_addstr(scr, 0, 1, "MESSAGE LOG", curses.color_pair(C_TITLE) | curses.A_BOLD)
    msgs = list(gs.messages)
    start = max(0, len(msgs) - (SCREEN_H-3))
    for i, (t, c) in enumerate(msgs[start:]):
        if i+2 >= SCREEN_H-1:
            break
        safe_addstr(scr, i+2, 1, t[:SCREEN_W-2], curses.color_pair(c))
    safe_addstr(scr, SCREEN_H-1, 1, "[ Press any key ]", curses.color_pair(C_YELLOW))
    scr.refresh()
    scr.getch()


def calculate_score(p: Player, gs: GameState) -> int:
    """Calculate final score."""
    score = p.gold + p.kills * B["score_per_kill"] + p.deepest_floor * B["score_per_floor"] + p.damage_dealt
    if gs.victory:
        score += B["score_victory_bonus"]
    return score


def show_death(scr: Any, gs: GameState) -> None:
    p = gs.player
    elapsed = int(time.time() - gs.start_time)
    m, s = elapsed // 60, elapsed % 60
    scr.erase()
    _, w = scr.getmaxyx()
    tomb = [
        "      _______",
        "     /       \\",
        "    /  R.I.P  \\",
        "   /           \\",
        "  | HERE LIES A  |",
        "  | BRAVE BUT    |",
        "  | FOOLISH      |",
        "  | ADVENTURER   |",
        "  |______________|",
        "  |______________|",
    ]
    sy = 1
    for i, line in enumerate(tomb):
        safe_addstr(scr, sy+i, max(0,(w-len(line))//2), line, curses.color_pair(C_RED))
    quip = random.choice(DEATH_QUIPS)
    safe_addstr(scr, sy+11, max(0,(w-len(quip))//2), f'"{quip}"', curses.color_pair(C_MAGENTA))
    cause = gs.death_cause or "unknown causes"
    safe_addstr(scr, sy+12, max(0,(w-len(cause)-10)//2), f"Cause: {cause}", curses.color_pair(C_RED))
    stats = [
        f"Floor: {p.deepest_floor}/{MAX_FLOORS}  Level: {p.level}  Kills: {p.kills}",
        f"Gold: {p.gold} (earned:{p.gold_earned} spent:{p.gold_spent})  Turns: {gs.turn_count}  Time: {m}m{s}s",
        f"Items: {p.items_found}  Potions: {p.potions_drunk}  Food: {p.foods_eaten}  Torches: {p.torches_grabbed}",
        f"Spells: {p.spells_cast}  Shots: {p.projectiles_fired}  Traps: {p.traps_triggered}",
        f"Damage dealt: {p.damage_dealt}  Taken: {p.damage_taken}",
    ]
    for i, line in enumerate(stats):
        safe_addstr(scr, sy+14+i, max(0,(w-len(line))//2), line, curses.color_pair(C_YELLOW))
    score = calculate_score(p, gs)
    sc = f"SCORE: {score}"
    safe_addstr(scr, sy+19, max(0,(w-len(sc))//2), sc, curses.color_pair(C_GOLD) | curses.A_BOLD)
    pr = "[ Press any key ]"
    safe_addstr(scr, min(SCREEN_H-1, sy+21), max(0,(w-len(pr))//2), pr, curses.color_pair(C_DARK))
    scr.refresh()
    scr.getch()


def show_victory(scr: Any, gs: GameState) -> None:
    p = gs.player
    elapsed = int(time.time() - gs.start_time)
    m, s = elapsed // 60, elapsed % 60
    scr.erase()
    _, w = scr.getmaxyx()
    art = [
        "  *  .  *  .  *  .  *  .  *",
        "    ___________________",
        "   /                   \\",
        "  /   VICTORY!!!        \\",
        " /  THE DREAD LORD       \\",
        "|   IS VANQUISHED         |",
        "|  THORNHAVEN IS SAVED!   |",
        "|_________________________|",
        "  *  .  *  .  *  .  *  .  *",
    ]
    sy = 1
    for i, line in enumerate(art):
        safe_addstr(scr, sy+i, max(0,(w-len(line))//2), line,
                   curses.color_pair(C_YELLOW) | curses.A_BOLD)
    stats = [
        f"Level: {p.level}   Kills: {p.kills}   Bosses: {p.bosses_killed}",
        f"Gold: {p.gold}   Turns: {gs.turn_count}   Time: {m}m{s}s",
        f"Items: {p.items_found}  Potions: {p.potions_drunk}  Scrolls: {p.scrolls_read}",
        f"Damage dealt: {p.damage_dealt}  Taken: {p.damage_taken}",
        "",
        "You are a true hero of Thornhaven!",
    ]
    for i, line in enumerate(stats):
        safe_addstr(scr, sy+11+i, max(0,(w-len(line))//2), line, curses.color_pair(C_GREEN))
    score = calculate_score(p, gs)
    sc = f"SCORE: {score}"
    safe_addstr(scr, sy+18, max(0,(w-len(sc))//2), sc, curses.color_pair(C_GOLD) | curses.A_BOLD)
    pr = "[ Press any key ]"
    safe_addstr(scr, min(SCREEN_H-1, sy+20), max(0,(w-len(pr))//2), pr, curses.color_pair(C_DARK))
    scr.refresh()
    scr.getch()


# ============================================================
# CONTEXT TIPS (Phase 5, item 25)
# ============================================================

def check_context_tips(gs: GameState) -> None:
    """Fire first-encounter tips. Each tip shows exactly once."""
    p = gs.player
    # First enemy adjacent
    if "enemy_adjacent" not in gs.tips_shown:
        for e in gs.enemies:
            if e.is_alive() and abs(e.x - p.x) + abs(e.y - p.y) == 1:
                gs.tips_shown.add("enemy_adjacent")
                gs.msg("Tip: Walk into enemies to attack them!", C_MAGENTA)
                break
    # First shrine seen
    if "shrine" not in gs.tips_shown:
        for (mx, my) in gs.visible:
            if 0 <= mx < MAP_W and 0 <= my < MAP_H and gs.tiles[my][mx] == T_SHRINE:
                gs.tips_shown.add("shrine")
                gs.msg("Tip: Press 'p' to pray. Shrines grant boons... but some are cursed.", C_MAGENTA)
                break
    # First unidentified potion in inventory
    if "unid_potion" not in gs.tips_shown:
        for inv in p.inventory:
            if inv.item_type == "potion" and not inv.identified:
                gs.tips_shown.add("unid_potion")
                gs.msg("Tip: This potion is unidentified. Use it to discover its effect, or find an Identify scroll.", C_MAGENTA)
                break
    # First closed door seen
    if "door" not in gs.tips_shown:
        for (mx, my) in gs.visible:
            if 0 <= mx < MAP_W and 0 <= my < MAP_H and gs.tiles[my][mx] == T_DOOR:
                gs.tips_shown.add("door")
                gs.msg("Tip: Walk into doors to open them.", C_MAGENTA)
                break
    # First shop
    if "shop" not in gs.tips_shown:
        if gs.tiles[p.y][p.x] == T_SHOP_FLOOR and gs.get_shop_at(p.x, p.y):
            gs.tips_shown.add("shop")
            gs.msg("Tip: Press '$' to browse the merchant's wares.", C_MAGENTA)
    # First projectile weapon found
    if "projectile" not in gs.tips_shown:
        for inv in p.inventory:
            if inv.item_type in ("bow", "wand", "throwing_dagger"):
                gs.tips_shown.add("projectile")
                gs.msg("Tip: Press 'f' to fire projectiles. You need ammo!", C_MAGENTA)
                break


# ============================================================
# LOOK/EXAMINE MODE (Phase 4, item 23)
# ============================================================

def look_mode(gs: GameState, scr: Any) -> None:
    """Enter cursor mode to examine tiles."""
    if scr is None:
        return
    cx, cy = gs.player.x, gs.player.y
    gs.msg("Look mode: move cursor, ESC to exit.", C_CYAN)
    LOOK_KEYS = {
        curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
        curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
        ord('w'): (0,-1), ord('s'): (0,1),
        ord('a'): (-1,0), ord('d'): (1,0),
        ord('h'): (-1,0), ord('j'): (0,1),
        ord('k'): (0,-1), ord('l'): (1,0),
        ord('y'): (-1,-1), ord('u'): (1,-1),
        ord('b'): (-1,1), ord('n'): (1,1),
    }
    while True:
        # Render game with cursor
        render_game(scr, gs)
        # Draw cursor
        cam_x = max(0, min(gs.player.x - VIEW_W//2, MAP_W - VIEW_W))
        cam_y = max(0, min(gs.player.y - VIEW_H//2, MAP_H - VIEW_H))
        scr_cx = cx - cam_x
        scr_cy = cy - cam_y
        if 0 <= scr_cx < VIEW_W and 0 <= scr_cy < VIEW_H:
            try:
                scr.addstr(scr_cy, scr_cx, 'X', curses.color_pair(C_YELLOW) | curses.A_BLINK)
            except curses.error:
                pass
        # Build description
        desc = _describe_tile(gs, cx, cy)
        safe_addstr(scr, SCREEN_H-1, 0, desc[:SCREEN_W-1], curses.color_pair(C_CYAN))
        scr.refresh()
        key = scr.getch()
        if key == 27:
            return
        if key in LOOK_KEYS:
            dx, dy = LOOK_KEYS[key]
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H:
                cx, cy = nx, ny


def _describe_tile(gs: GameState, x: int, y: int) -> str:
    """Return description string for tile at (x, y)."""
    if not (0 <= x < MAP_W and 0 <= y < MAP_H):
        return "Out of bounds"
    if (x, y) not in gs.visible:
        if gs.explored[y][x]:
            return "Explored but not visible"
        return "Unknown"
    # Check for player
    if x == gs.player.x and y == gs.player.y:
        return "You (@)"
    # Check for enemy
    for e in gs.enemies:
        if e.x == x and e.y == y and e.is_alive():
            boss_str = " (BOSS)" if e.boss else " (hostile)"
            return f"{e.name}{boss_str} HP: {e.hp}/{e.max_hp}"
    # Check for items
    for it in gs.items:
        if it.x == x and it.y == y:
            return it.display_name
    # Tile description
    tile = gs.tiles[y][x]
    TILE_NAMES = {
        T_WALL: "Wall", T_FLOOR: "Floor tile", T_CORRIDOR: "Corridor",
        T_DOOR: "Door", T_STAIRS_DOWN: "Stairs down (>)",
        T_STAIRS_UP: "Stairs up (<)", T_WATER: "Water (shallow)",
        T_LAVA: "Lava (deadly!)", T_SHOP_FLOOR: "Shop floor",
        T_SHRINE: "Shrine (press 'p' to pray)",
        T_ALCHEMY_TABLE: "Alchemy table (press 'e')",
        T_WALL_TORCH: "Wall torch (light source)",
        T_FOUNTAIN: "Magical fountain (press 'e' to drink)",
        T_PEDESTAL_UNLIT: "Unlit pedestal (press 'e')",
        T_PEDESTAL_LIT: "Lit pedestal",
        T_SWITCH_OFF: "Switch (OFF)",
        T_SWITCH_ON: "Switch (ON)",
        T_STAIRS_LOCKED: "Sealed stairs (solve puzzle)",
    }
    return TILE_NAMES.get(tile, "Unknown tile")


# ============================================================
# AUTO-FIGHT (Phase 4, item 20)
# ============================================================

def auto_fight_step(gs: GameState) -> bool | None:
    """Execute one step of auto-fight. Returns True if a turn was spent, None to stop."""
    p = gs.player
    # Stop conditions
    if p.hp < p.max_hp * AUTO_FIGHT_HP_THRESHOLD:
        gs.msg("Auto-fight stopped: low HP!", C_YELLOW)
        gs.auto_fighting = False
        return None
    # Find nearest visible enemy
    nearest = None
    nd = 999
    for e in gs.enemies:
        if e.is_alive() and (e.x, e.y) in gs.visible:
            d = abs(e.x - p.x) + abs(e.y - p.y)
            if d < nd:
                nd = d
                nearest = e
    if nearest is None:
        gs.msg("Auto-fight stopped: no enemies visible.", C_YELLOW)
        gs.auto_fighting = False
        return None
    # Check if a new enemy appeared that wasn't the target
    if gs.auto_fight_target and nearest is not gs.auto_fight_target:
        if gs.auto_fight_target.is_alive() and (gs.auto_fight_target.x, gs.auto_fight_target.y) in gs.visible:
            pass  # original target still visible, keep going
        else:
            gs.auto_fight_target = nearest
    else:
        gs.auto_fight_target = nearest
    target = gs.auto_fight_target
    if not target.is_alive():
        gs.msg("Auto-fight: target defeated.", C_GREEN)
        gs.auto_fight_target = None
        gs.auto_fighting = False
        return None
    # If adjacent, attack
    if abs(target.x - p.x) + abs(target.y - p.y) == 1:
        player_attack(gs, target)
        return True
    # Otherwise, pathfind toward
    step = astar(gs.tiles, p.x, p.y, target.x, target.y, max_steps=30)
    if step:
        return _get_items().player_move(gs, step[0], step[1])
    gs.msg("Auto-fight stopped: can't reach target.", C_YELLOW)
    gs.auto_fighting = False
    return None


# ============================================================
# AUTO-EXPLORE (Phase 4, item 21)
# ============================================================

def auto_explore_step(gs: GameState) -> bool | None:
    """Execute one step of auto-explore using BFS. Returns True if turn spent, None to stop."""
    p = gs.player
    # Stop conditions
    if p.hp < p.max_hp * AUTO_EXPLORE_HP_THRESHOLD:
        gs.msg("Exploring stopped: low HP!", C_YELLOW)
        gs.auto_exploring = False
        return None
    # Enemy in FOV?
    for e in gs.enemies:
        if e.is_alive() and (e.x, e.y) in gs.visible:
            gs.msg("Exploring stopped: enemy spotted!", C_YELLOW)
            gs.auto_exploring = False
            return None
    # Item on current tile?
    for it in gs.items:
        if it.x == p.x and it.y == p.y:
            gs.msg("Exploring stopped: item found!", C_YELLOW)
            gs.auto_exploring = False
            return None
    # Stairs on current tile?
    if gs.tiles[p.y][p.x] in (T_STAIRS_DOWN, T_STAIRS_UP):
        gs.msg("Exploring stopped: stairs found!", C_YELLOW)
        gs.auto_exploring = False
        return None
    # BFS to nearest unexplored walkable tile
    target = _bfs_unexplored(gs)
    if target is None:
        gs.msg("Exploring stopped: fully explored.", C_YELLOW)
        gs.auto_exploring = False
        return None
    tx, ty = target
    step = astar(gs.tiles, p.x, p.y, tx, ty, max_steps=50)
    if step:
        return _get_items().player_move(gs, step[0], step[1])
    gs.msg("Exploring stopped: can't reach target.", C_YELLOW)
    gs.auto_exploring = False
    return None


def _bfs_unexplored(gs: GameState) -> tuple[int, int] | None:
    """BFS from player position to find nearest unexplored walkable tile."""
    p = gs.player
    visited = set()
    queue = deque([(p.x, p.y)])
    visited.add((p.x, p.y))
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in visited:
                continue
            if nx < 0 or nx >= MAP_W or ny < 0 or ny >= MAP_H:
                continue
            if gs.tiles[ny][nx] not in WALKABLE:
                continue
            visited.add((nx, ny))
            if not gs.explored[ny][nx]:
                return (nx, ny)
            queue.append((nx, ny))
    return None


# ============================================================
# REST UNTIL HEALED (Phase 4, item 22)
# ============================================================

def rest_until_healed(gs: GameState, scr: Any) -> int:
    """Skip turns until HP == max_hp. Returns total turns rested."""
    p = gs.player
    if p.hp >= p.max_hp:
        gs.msg("You are already at full health.", C_WHITE)
        return 0
    turns_rested = 0
    gs.msg("Resting...", C_CYAN)
    while p.hp < p.max_hp and gs.running and not gs.game_over:
        # Stop if enemy in FOV
        fov_radius = p.get_torch_radius()
        if "Blindness" in p.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, p.x, p.y, fov_radius, gs.visible)
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                gs.msg(f"Resting interrupted! {e.name} spotted! (Rested {turns_rested} turns)", C_RED)
                return turns_rested
        # Stop if hunger too low
        if p.hunger <= REST_HUNGER_THRESHOLD:
            gs.msg(f"Too hungry to rest! (Rested {turns_rested} turns)", C_YELLOW)
            return turns_rested
        # Rest one turn
        if p.hunger > B["rest_hunger_threshold"]:
            p.hp = min(p.max_hp, p.hp + B["rest_hp_per_turn"])
        p.hunger = max(0, p.hunger - B["hunger_rest_cost"])
        gs.turn_count += 1
        turns_rested += 1
        process_enemies(gs)
        _get_items().process_status(gs)
        if p.hp <= 0:
            gs.game_over = True
            break
        # Render periodically
        if scr and turns_rested % 5 == 0:
            render_game(scr, gs)
    if p.hp >= p.max_hp:
        gs.msg(f"Rested for {turns_rested} turns. Fully healed!", C_GREEN)
    return turns_rested


# ============================================================
# ENHANCED DEATH & VICTORY SCREENS (Phase 6)
# ============================================================

def show_enhanced_death(scr: Any, gs: GameState) -> None:
    """Enhanced death screen with full statistics (Phase 6, item 27)."""
    # Flush any buffered keypresses so death screen isn't dismissed instantly
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    curses.napms(500)  # Brief pause before showing death stats

    p = gs.player
    elapsed = int(time.time() - gs.start_time)
    m, s = elapsed // 60, elapsed % 60
    scr.erase()
    h, w = scr.getmaxyx()

    lines = [
        ("+" + "=" * 36 + "+", C_RED),
        ("|      REST IN PEACE               |", C_RED),
        ("|                                   |", C_RED),
        (f"|   Level {p.level} {CHARACTER_CLASSES[p.player_class]['name'] if p.player_class and p.player_class in CHARACTER_CLASSES else 'Adventurer'}{' ' * max(0, 24 - len(f'Level {p.level} ' + (CHARACTER_CLASSES.get(p.player_class, {}).get('name', 'Adventurer') if p.player_class else 'Adventurer')))}|", C_RED),
        ("|                                   |", C_RED),
    ]
    cause = gs.death_cause or "unknown causes"
    cause_line = f"|   Slain by: {cause}"
    cause_line = cause_line[:36] + " " * max(0, 37 - len(cause_line)) + "|"
    lines.append((cause_line, C_RED))
    floor_line = f"|   on Floor {p.floor}, Turn {gs.turn_count}"
    floor_line = floor_line[:36] + " " * max(0, 37 - len(floor_line)) + "|"
    lines.append((floor_line, C_RED))
    lines.append(("+" + "=" * 36 + "+", C_RED))
    # Stats section
    wpn_name = p.weapon.display_name[:14] if p.weapon else "Fists"
    arm_name = p.armor.display_name[:14] if p.armor else "None"
    ring_name = p.ring.display_name[:14] if p.ring else "None"
    lines.extend([
        (f"  HP: {p.hp}/{p.max_hp}  STR: {p.strength}  DEF: {p.total_defense()}", C_YELLOW),
        (f"  Wpn: {wpn_name}  Arm: {arm_name}", C_WHITE),
        (f"  Ring: {ring_name}  Gold: {p.gold}", C_CYAN),
        ("", C_WHITE),
        (f"  Enemies killed: {p.kills}", C_GREEN),
        (f"  Floors explored: {len(gs.floors_explored)}", C_GREEN),
        (f"  Deepest floor: {p.deepest_floor}", C_GREEN),
        (f"  Spells cast: {p.spells_cast}  Potions: {p.potions_drunk}", C_GREEN),
        (f"  Time: {m}m{s}s  Damage dealt: {p.damage_dealt}", C_GREEN),
    ])
    # Last messages
    lines.append(("", C_WHITE))
    lines.append(("  Last words:", C_MAGENTA))
    last_msgs = list(gs.messages)[-3:]
    for msg_text, _ in last_msgs:
        lines.append((f'  "{msg_text[:34]}"', C_MAGENTA))

    quip = random.choice(DEATH_QUIPS)
    lines.append(("", C_WHITE))
    lines.append((f'  "{quip}"', C_DARK))

    score = calculate_score(p, gs)
    lines.append(("", C_WHITE))
    lines.append((f"  SCORE: {score}", C_GOLD))

    # Lifetime stats
    game_mod = _get_game()
    lifetime = game_mod.update_lifetime_stats(gs)
    lines.extend(game_mod._format_lifetime_stats_lines(lifetime))

    sy = max(0, (h - len(lines) - 2) // 2)
    for i, (text, color) in enumerate(lines):
        if sy + i >= h - 1:
            break
        cx = max(0, (w - len(text)) // 2)
        safe_addstr(scr, sy + i, cx, text, curses.color_pair(color))

    pr = "[ Press ENTER or SPACE to continue ]"
    safe_addstr(scr, min(h - 1, sy + len(lines) + 1), max(0, (w - len(pr)) // 2),
               pr, curses.color_pair(C_DARK))
    scr.refresh()
    while True:
        k = scr.getch()
        if k in (10, 13, 32):  # Enter or Space (#24)
            break


def show_enhanced_victory(scr: Any, gs: GameState) -> None:
    """Enhanced victory screen with celebration art (Phase 6, item 28)."""
    p = gs.player
    elapsed = int(time.time() - gs.start_time)
    m, s = elapsed // 60, elapsed % 60
    scr.erase()
    h, w = scr.getmaxyx()

    lines = [
        ("*  .  *  .  *  .  *  .  *  .  *", C_YELLOW),
        ("", C_WHITE),
        ("     V I C T O R Y ! ! !", C_YELLOW),
        ("", C_WHITE),
        ("  THE DREAD LORD IS VANQUISHED", C_GREEN),
        ("  THORNHAVEN IS SAVED!", C_GREEN),
        ("", C_WHITE),
        ("*  .  *  .  *  .  *  .  *  .  *", C_YELLOW),
        ("", C_WHITE),
        (f"  Class: {CHARACTER_CLASSES[p.player_class]['name'] if p.player_class and p.player_class in CHARACTER_CLASSES else 'Adventurer'}  Level: {p.level}", C_GREEN),
        (f"  Kills: {p.kills}  Bosses: {p.bosses_killed}", C_GREEN),
        (f"  Gold: {p.gold}  Turns: {gs.turn_count}  Time: {m}m{s}s", C_GREEN),
        (f"  Floors explored: {len(gs.floors_explored)}", C_GREEN),
        (f"  Items: {p.items_found}  Potions: {p.potions_drunk}  Scrolls: {p.scrolls_read}", C_GREEN),
        (f"  Spells cast: {p.spells_cast}  Shots: {p.projectiles_fired}", C_GREEN),
        (f"  Damage dealt: {p.damage_dealt}  Taken: {p.damage_taken}", C_GREEN),
        ("", C_WHITE),
        ("  You are a true hero of Thornhaven!", C_YELLOW),
    ]

    score = calculate_score(p, gs)
    lines.extend([
        ("", C_WHITE),
        (f"  SCORE: {score}", C_GOLD),
        ("  (Base + 5000 victory bonus!)", C_GOLD),
    ])

    # Lifetime stats
    game_mod = _get_game()
    lifetime = game_mod.update_lifetime_stats(gs)
    lines.extend(game_mod._format_lifetime_stats_lines(lifetime))

    sy = max(0, (h - len(lines) - 2) // 2)
    for i, (text, color) in enumerate(lines):
        if sy + i >= h - 1:
            break
        cx = max(0, (w - len(text)) // 2)
        safe_addstr(scr, sy + i, cx, text,
                   curses.color_pair(color) | (curses.A_BOLD if color == C_YELLOW else 0))

    pr = "[ Press ENTER or SPACE to continue ]"
    safe_addstr(scr, min(h - 1, sy + len(lines) + 1), max(0, (w - len(pr)) // 2),
               pr, curses.color_pair(C_DARK))
    scr.refresh()
    while True:
        k = scr.getch()
        if k in (10, 13, 32):  # Enter or Space (#24)
            break
