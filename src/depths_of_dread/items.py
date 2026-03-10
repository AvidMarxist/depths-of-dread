from __future__ import annotations

import random
import curses
from typing import Any, TYPE_CHECKING

from .constants import *
from .entities import Item, Enemy, Player
from .mapgen import astar, _has_los, compute_fov
from .combat import (sound_alert, _award_kill, _check_levelups, _compute_noise,
                     player_attack, _check_traps_on_move, _passive_trap_detect)

if TYPE_CHECKING:
    from collections.abc import Callable
    from .game import GameState


def _get_render_game() -> Callable[..., None]:
    from .game import render_game
    return render_game


# ============================================================
# ITEM USE
# ============================================================

def use_potion(gs: GameState, item: Item) -> None:
    p = gs.player
    eff = item.data["effect"]
    p.potions_drunk += 1
    if eff not in gs.id_potions:
        gs.id_potions.add(eff)
        gs.msg(f"It was a Potion of {eff}!", C_MAGENTA)
        # Also identify any in inventory
        for inv in p.inventory:
            if inv.item_type == "potion" and inv.data.get("effect") == eff:
                inv.identified = True
    # Journal: record identified effect (#6)
    gs.journal[f"Potion of {eff}"] = _journal_potion_desc(eff)
    if eff == "Healing":
        h = random.randint(B["heal_potion_min"], B["heal_potion_max"]) + p.level * B["heal_potion_level_scale"]
        p.hp = min(p.max_hp, p.hp + h)
        gs.msg(f"You feel much better! (+{h} HP)", C_GREEN)
    elif eff == "Strength":
        p.status_effects["Strength"] = B["strength_duration_base"] + p.level * B["strength_duration_level_scale"]
        gs.msg("Power surges through your muscles!", C_YELLOW)
    elif eff == "Speed":
        p.status_effects["Speed"] = B["speed_duration_base"] + p.level * B["speed_duration_level_scale"]
        gs.msg("Everything seems to slow down!", C_CYAN)
    elif eff == "Poison":
        d = random.randint(5, 15)
        p.hp -= d
        gs.msg(f"Urgh! Poison! (-{d} HP)", C_RED)
        if p.hp <= 0:
            gs.game_over = True
            gs.death_cause = "poison"
            sound_alert(gs, "death")
    elif eff == "Blindness":
        p.status_effects["Blindness"] = B["blindness_duration"]
        gs.msg("Everything goes dark!", C_DARK)
    elif eff == "Experience":
        xp = p.xp_next // 2
        p.xp += xp
        gs.msg(f"Wisdom fills your mind! (+{xp} XP)", C_YELLOW)
        for lvl, hp_g, str_g, mp_g in p.check_level_up():
            gs.msg(f"*** LEVEL UP! Level {lvl}! +{hp_g} HP, +{str_g} STR, +{mp_g} MP ***", C_YELLOW)
    elif eff == "Resistance":
        p.status_effects["Resistance"] = B["resistance_duration"]
        gs.msg("Your skin hardens!", C_BLUE)
    elif eff == "Berserk":
        p.status_effects["Berserk"] = B["berserk_duration"]
        gs.msg("BLOOD RAGE! You see red!", C_RED)
    elif eff == "Mana":
        restored = min(p.max_mana - p.mana, 15 + p.level * 2)
        p.mana += restored
        gs.msg(f"Magical energy floods your mind! (+{restored} MP)", C_CYAN)
    p.inventory.remove(item)


def use_scroll(gs: GameState, item: Item) -> None:
    p = gs.player
    eff = item.data["effect"]
    p.scrolls_read += 1
    if eff not in gs.id_scrolls:
        gs.id_scrolls.add(eff)
        gs.msg(f"It was a Scroll of {eff}!", C_YELLOW)
        for inv in p.inventory:
            if inv.item_type == "scroll" and inv.data.get("effect") == eff:
                inv.identified = True
    # Journal: record identified effect (#6)
    gs.journal[f"Scroll of {eff}"] = _journal_scroll_desc(eff)
    if eff == "Identify":
        for inv in p.inventory:
            inv.identified = True
        gs.msg("Your possessions glow with knowledge!", C_CYAN)
    elif eff == "Teleport":
        pos = gs._find_spawn_pos()
        if pos:
            p.x, p.y = pos
            gs.msg("Reality blinks! You're somewhere else!", C_MAGENTA)
    elif eff == "Fireball":
        kills = 0
        for e in gs.enemies:
            if abs(e.x-p.x) + abs(e.y-p.y) <= 4:
                e.hp -= random.randint(15, 30)
                if not e.is_alive():
                    kills += _award_kill(gs, e, msg=False)
        gs.msg(f"FIRE ERUPTS! {kills} enemies caught in the blast!", C_RED)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
    elif eff == "Mapping":
        for y in range(MAP_H):
            for x in range(MAP_W):
                if gs.tiles[y][x] != T_WALL:
                    gs.explored[y][x] = True
        gs.msg("The entire floor is revealed!", C_CYAN)
    elif eff == "Enchant":
        if p.weapon:
            p.weapon.data["bonus"] = p.weapon.data.get("bonus", 0) + 2
            lo, hi = p.weapon.data["dmg"]
            p.weapon.data["dmg"] = (lo+1, hi+1)
            gs.msg(f"Your {p.weapon.display_name} glows with power!", C_YELLOW)
        elif p.armor:
            p.armor.data["defense"] += 2
            gs.msg(f"Your {p.armor.display_name} shimmers!", C_YELLOW)
        else:
            gs.msg("The magic dissipates uselessly.", C_DARK)
    elif eff == "Fear":
        c = 0
        for e in gs.enemies:
            if abs(e.x-p.x)+abs(e.y-p.y) <= 8 and not e.boss:
                e.alerted = False
                c += 1
        gs.msg(f"{c} enemies flee in terror!", C_MAGENTA)
    elif eff == "Summon":
        pos = gs._find_spawn_pos()
        if pos:
            mt = random.choice(["goblin", "skeleton", "orc"])
            m = Enemy(pos[0], pos[1], mt)
            m.alerted = True
            gs.enemies.append(m)
            gs.msg(f"A hostile {m.name} appears! Bad scroll!", C_RED)
    elif eff == "Lightning":
        nearest = None
        nd = 999
        for e in gs.enemies:
            d = abs(e.x-p.x) + abs(e.y-p.y)
            if d < nd:
                nearest = e
                nd = d
        if nearest and nd <= 10:
            dmg = random.randint(20, 40)
            nearest.hp -= dmg
            gs.msg(f"Lightning strikes {nearest.name} for {dmg}!", C_CYAN)
            if not nearest.is_alive():
                _award_kill(gs, nearest, msg=f"The {nearest.name} is destroyed!")
                gs.enemies = [e for e in gs.enemies if e.is_alive()]
        else:
            gs.msg("Lightning crackles harmlessly.", C_CYAN)
    p.inventory.remove(item)


def use_food(gs: GameState, item: Item) -> None:
    p = gs.player
    n = item.data.get("nutrition", 20)
    p.hunger = min(100, p.hunger + n)
    p.foods_eaten += 1
    gs.msg(f"You eat the {item.display_name}. ({n} nutrition)", C_GREEN)
    if item.data.get("name") == "Mystery Meat" and random.random() < 0.2:
        d = random.randint(1, 5)
        gs.msg(f"Ugh, that tasted terrible! (-{d} HP)", C_RED)
        p.hp -= d
        if p.hp <= 0:
            gs.game_over = True
            gs.death_cause = "food poisoning"
            sound_alert(gs, "death")
    p.inventory.remove(item)


def pray_at_shrine(gs: GameState) -> None:
    p = gs.player
    roll = random.random()
    threshold_heal = B["shrine_full_heal_chance"]
    threshold_maxhp = threshold_heal + B["shrine_max_hp_chance"]
    threshold_str = threshold_maxhp + B["shrine_str_chance"]
    threshold_def = threshold_str + B["shrine_def_chance"]
    threshold_nothing = threshold_def + B["shrine_nothing_chance"]
    if roll < threshold_heal:
        p.hp = p.max_hp
        gs.msg("Divine light! Fully restored!", C_YELLOW)
    elif roll < threshold_maxhp:
        p.max_hp += 5
        p.hp += 5
        gs.msg("Vitality increases! (+5 max HP)", C_GREEN)
    elif roll < threshold_str:
        p.strength += 2
        gs.msg("Strength flows through you! (+2 STR)", C_YELLOW)
    elif roll < threshold_def:
        p.defense += 2
        gs.msg("Your body toughens! (+2 DEF)", C_BLUE)
    elif roll < threshold_nothing:
        gs.msg("The shrine is silent.", C_DARK)
    else:
        # Curse: lose some% of current HP, but never instakill
        pct = random.uniform(B["shrine_curse_min_pct"], B["shrine_curse_max_pct"])
        d = max(1, int(p.hp * pct))
        p.hp -= d
        gs.msg(f"A dark energy courses through you! (-{d} HP)", C_RED)
        if p.hp <= 0:
            p.hp = 1  # Shrine curse is punishing but not lethal
            gs.msg("You barely cling to life!", C_RED)
        sound_alert(gs, "low_hp")
    gs.tiles[p.y][p.x] = T_FLOOR


def process_status(gs: GameState) -> None:
    expired = []
    p = gs.player
    for eff, turns in list(p.status_effects.items()):
        # Poison tick damage
        if eff == "Poison":
            dmg = B["poison_damage_per_tick"]
            p.hp -= dmg
            p.damage_taken += dmg
            if gs.turn_count % 3 == 0:
                gs.msg(f"Poison courses through you! (-{dmg} HP)", C_GREEN)
            if p.hp <= 0:
                gs.game_over = True
                gs.death_cause = "poison"
                gs.msg("You succumb to poison...", C_GREEN)
                sound_alert(gs, "death")
                return
        p.status_effects[eff] = turns - 1
        if p.status_effects[eff] <= 0:
            expired.append(eff)
            del p.status_effects[eff]
    # Bleed tick damage (stacking)
    if p.bleed_stacks > 0 and p.bleed_turns > 0:
        bleed_dmg = B["bleed_damage_per_tick"] * p.bleed_stacks
        p.hp -= bleed_dmg
        p.damage_taken += bleed_dmg
        p.bleed_turns -= 1
        if gs.turn_count % 2 == 0:
            gs.msg(f"You bleed! (-{bleed_dmg} HP, {p.bleed_stacks} stacks)", C_RED)
        if p.bleed_turns <= 0:
            p.bleed_stacks = 0
            gs.msg("The bleeding stops.", C_DARK)
        if p.hp <= 0:
            gs.game_over = True
            gs.death_cause = "bled out"
            gs.msg("You bleed out...", C_RED)
            sound_alert(gs, "death")
            return
    for eff in expired:
        gs.msg(f"{eff} wears off.", C_DARK)
    # Mana regen
    if gs.turn_count % MANA_REGEN_INTERVAL == 0 and gs.player.mana < gs.player.max_mana:
        gs.player.mana = min(gs.player.max_mana, gs.player.mana + 1)
    # Torch fuel burn (only when lit)
    if gs.player.torch_lit and gs.player.torch_fuel > 0:
        gs.player.torch_fuel -= 1
        if gs.player.torch_fuel == 50:
            gs.msg("Your torch flickers...", C_YELLOW)
        elif gs.player.torch_fuel == 0:
            gs.msg("Your torch goes out! Darkness closes in!", C_RED)
            sound_alert(gs, "low_torch")
    # Frozen enemy tick
    for e in gs.enemies:
        if e.frozen_turns > 0:
            e.frozen_turns -= 1
    # Speedrun challenge: floor timer
    if gs.challenge_speedrun and not gs.game_over:
        gs.speedrun_timer += 1
        floor_limit = 100 + p.floor * 20  # Gets harder on deeper floors
        if gs.speedrun_timer >= floor_limit:
            gs.game_over = True
            gs.death_cause = "ran out of time (speedrun)"
            gs.msg("TIME'S UP! The dungeon collapses around you!", C_RED)
            sound_alert(gs, "death")
            return
        remaining = floor_limit - gs.speedrun_timer
        if remaining == 20:
            gs.msg(f"SPEEDRUN: Only {remaining} turns left on this floor!", C_RED)
        elif remaining == 50:
            gs.msg(f"SPEEDRUN: {remaining} turns remaining.", C_YELLOW)
    # Branch floor environmental mechanics
    if gs.active_branch and not gs.game_over:
        _process_branch_effects(gs)
    # Class ability cooldown tick
    if p.ability_cooldown > 0:
        p.ability_cooldown -= 1


def _process_branch_effects(gs: GameState) -> None:
    """Apply environmental effects based on active branch."""
    p = gs.player
    branch = gs.active_branch
    if branch == "flooded_crypts":
        # Standing in water deals cold damage
        if gs.tiles[p.y][p.x] == T_WATER:
            cold_dmg = B["flooded_crypts_water_dmg"]
            if "cold" not in p.player_resists():
                p.hp -= cold_dmg
                p.damage_taken += cold_dmg
                if gs.turn_count % 3 == 0:
                    gs.msg("The frigid water chills your bones! (-{} HP)".format(cold_dmg), C_CYAN)
                if p.hp <= 0:
                    gs.game_over = True
                    gs.death_cause = "frozen in the crypts"
                    sound_alert(gs, "death")
    elif branch == "burning_pits":
        # Proximity to lava causes heat damage
        for dy in range(-B["burning_pits_lava_proximity"], B["burning_pits_lava_proximity"] + 1):
            for dx in range(-B["burning_pits_lava_proximity"], B["burning_pits_lava_proximity"] + 1):
                ny, nx = p.y + dy, p.x + dx
                if 0 <= ny < MAP_H and 0 <= nx < MAP_W and gs.tiles[ny][nx] == T_LAVA:
                    if "fire" not in p.player_resists():
                        heat_dmg = B["burning_pits_heat_dmg"]
                        p.hp -= heat_dmg
                        p.damage_taken += heat_dmg
                        if gs.turn_count % 4 == 0:
                            gs.msg("The intense heat sears you! (-{} HP)".format(heat_dmg), C_LAVA)
                        if p.hp <= 0:
                            gs.game_over = True
                            gs.death_cause = "burned by volcanic heat"
                            sound_alert(gs, "death")
                    return  # Only apply once per turn
    elif branch == "mind_halls":
        # Random confusion from psychic ambient energy
        if random.random() < B["mind_halls_confusion_chance"]:
            if "Confusion" not in p.status_effects:
                p.status_effects["Confusion"] = random.randint(2, 4)
                gs.msg("Psychic whispers cloud your mind!", C_MAGENTA)
    elif branch == "beast_warrens":
        # Beast Warrens: enemies have boosted detection range (handled in detection)
        # Extra noise attracts enemies on even turns
        if gs.turn_count % 6 == 0:
            for e in gs.enemies:
                if not e.alerted and e.alertness == "unwary":
                    dist = abs(e.x - p.x) + abs(e.y - p.y)
                    if dist <= 10:
                        e.alertness = "alert"
                        e.alerted = True
    elif branch == "fungal_depths":
        # Spore clouds: periodic poison chance
        if gs.turn_count % 5 == 0 and random.random() < 0.15:
            if "Poison" not in p.status_effects:
                p.status_effects["Poison"] = 3
                gs.msg("Spores fill the air! You inhale poison!", C_GREEN)
    elif branch == "trapped_halls":
        # Harder to detect traps in this branch (handled by trap_detect_penalty)
        pass  # Extra traps already handled in branch defs
    elif branch == "void_rift":
        # Random teleportation chance
        if gs.turn_count % 8 == 0 and random.random() < 0.10:
            pos = gs._find_spawn_pos()
            if pos:
                p.x, p.y = pos
                gs.msg("Reality shifts! You are teleported!", C_MAGENTA)
    elif branch == "infernal_forge":
        # Standing near lava (same as burning_pits but more intense)
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                ny, nx = p.y + dy, p.x + dx
                if 0 <= ny < MAP_H and 0 <= nx < MAP_W and gs.tiles[ny][nx] == T_LAVA:
                    if "fire" not in p.player_resists():
                        heat_dmg = B["burning_pits_heat_dmg"] + 1
                        p.hp -= heat_dmg
                        p.damage_taken += heat_dmg
                        if gs.turn_count % 3 == 0:
                            gs.msg("Molten metal sears you! (-{} HP)".format(heat_dmg), C_LAVA)
                        if p.hp <= 0:
                            gs.game_over = True
                            gs.death_cause = "melted in the Infernal Forge"
                            sound_alert(gs, "death")
                    return


# ============================================================
# PROJECTILES
# ============================================================

def _get_direction_delta(key: int) -> tuple[int, int] | None:
    """Convert a key to a (dx, dy) direction for projectiles/spells.
    Supports cardinal AND diagonal directions (yubn vi keys)."""
    DIR_KEYS = {
        curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
        curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
        ord('w'): (0,-1), ord('s'): (0,1),
        ord('a'): (-1,0), ord('d'): (1,0),
        ord('h'): (-1,0), ord('j'): (0,1),
        ord('k'): (0,-1), ord('l'): (1,0),
        # Diagonal support
        ord('y'): (-1,-1), ord('u'): (1,-1),
        ord('b'): (-1,1), ord('n'): (1,1),
    }
    return DIR_KEYS.get(key)


def _animate_projectile(gs: GameState, path: list[tuple[int, int]], char: str = '*', color: int = C_YELLOW) -> None:
    """Briefly flash the projectile along its path (skip in headless)."""
    if gs._headless or not gs._scr:
        return
    scr = gs._scr
    p = gs.player
    cam_x = max(0, min(p.x - VIEW_W//2, MAP_W - VIEW_W))
    cam_y = max(0, min(p.y - VIEW_H//2, MAP_H - VIEW_H))
    for (px, py) in path:
        sx = px - cam_x
        sy = py - cam_y
        if 0 <= sx < VIEW_W and 0 <= sy < VIEW_H:
            try:
                safe_addstr(scr, sy, sx, char, curses.color_pair(color) | curses.A_BOLD)
                scr.refresh()
                curses.napms(30)
            except Exception:
                pass


def _animate_blast(gs: GameState, cx: int, cy: int, radius: int, char: str = '*', color: int = C_RED) -> None:
    """Flash an AoE blast area for visual feedback (skip in headless)."""
    if gs._headless or not gs._scr:
        return
    scr = gs._scr
    p = gs.player
    cam_x = max(0, min(p.x - VIEW_W//2, MAP_W - VIEW_W))
    cam_y = max(0, min(p.y - VIEW_H//2, MAP_H - VIEW_H))
    # Draw blast tiles
    for by in range(cy - radius, cy + radius + 1):
        for bx in range(cx - radius, cx + radius + 1):
            sx = bx - cam_x
            sy = by - cam_y
            if 0 <= sx < VIEW_W and 0 <= sy < VIEW_H:
                try:
                    safe_addstr(scr, sy, sx, char, curses.color_pair(color) | curses.A_BOLD)
                except Exception:
                    pass
    try:
        scr.refresh()
        curses.napms(200)
    except Exception:
        pass


def fire_projectile(gs: GameState, scr: Any) -> bool:
    """Handle 'f' key — fire arrows, throw daggers, or zap wands."""
    p = gs.player
    # Determine what to fire
    options = []
    # Check for bow + arrows
    if p.bow:
        arrow_item = None
        for inv in p.inventory:
            if inv.item_type == "arrow" and inv.count > 0:
                arrow_item = inv
                break
        if arrow_item:
            options.append(("arrow", arrow_item))
    # Check for throwing daggers
    for inv in p.inventory:
        if inv.item_type == "throwing_dagger" and inv.count > 0:
            options.append(("dagger", inv))
            break
    # Check for wands
    for inv in p.inventory:
        if inv.item_type == "wand" and inv.data.get("charges", 0) > 0:
            options.append(("wand", inv))
            break

    if not options:
        gs.msg("Nothing to fire! Need bow+arrows, daggers, or a wand.", C_RED)
        return False

    # If multiple options, pick first available (arrows > daggers > wands)
    proj_type, proj_item = options[0]

    if scr:
        gs.msg("Fire direction? (wasd/arrows/hjkl/yubn, ESC cancel)", C_YELLOW)
        _get_render_game()(scr, gs)
        key = scr.getch()
    else:
        return False

    if key == 27:  # ESC
        gs.msg("Cancelled.", C_WHITE)
        return False
    direction = _get_direction_delta(key)
    if not direction:
        gs.msg("Cancelled (invalid direction).", C_WHITE)
        return False

    dx, dy = direction
    return _launch_projectile(gs, dx, dy, proj_type, proj_item)


def fire_projectile_headless(gs: GameState, dx: int, dy: int) -> bool:
    """Fire projectile in headless mode (for testing)."""
    p = gs.player
    # Determine what to fire (same priority)
    if p.bow:
        for inv in p.inventory:
            if inv.item_type == "arrow" and inv.count > 0:
                return _launch_projectile(gs, dx, dy, "arrow", inv)
    for inv in p.inventory:
        if inv.item_type == "throwing_dagger" and inv.count > 0:
            return _launch_projectile(gs, dx, dy, "dagger", inv)
    for inv in p.inventory:
        if inv.item_type == "wand" and inv.data.get("charges", 0) > 0:
            return _launch_projectile(gs, dx, dy, "wand", inv)
    return False


def _launch_projectile(gs: GameState, dx: int, dy: int, proj_type: str, proj_item: Item) -> bool:
    """Actually fire the projectile along a line."""
    p = gs.player
    p.projectiles_fired += 1

    if proj_type == "arrow":
        max_range = p.bow.data.get("range", 6)
        base_dmg = p.bow.data["dmg"]
        bonus = p.bow.data.get("bonus", 0)
        proj_item.count -= 1
        if proj_item.count <= 0:
            p.inventory.remove(proj_item)
        char = '-' if dy == 0 else '|'
        color = C_YELLOW
    elif proj_type == "dagger":
        max_range = 5
        base_dmg = proj_item.data["dmg"]
        bonus = 0
        proj_item.count -= 1
        if proj_item.count <= 0:
            p.inventory.remove(proj_item)
        char = '/' if dx != 0 and dy != 0 else ('-' if dy == 0 else '|')
        color = C_WHITE
    elif proj_type == "wand":
        max_range = 8
        base_dmg = proj_item.data["dmg"]
        bonus = 0
        # Wand class scaling (#8)
        if p.player_class == "mage":
            max_range += B["wand_mage_range_bonus"]
        proj_item.data["charges"] -= 1
        if proj_item.data["charges"] <= 0:
            gs.msg(f"The {proj_item.data['name']} crumbles to dust!", C_DARK)
            if proj_item in p.inventory:
                p.inventory.remove(proj_item)
        char = '*'
        color = C_MAGENTA
    else:
        return False

    # Trace the path
    x, y = p.x, p.y
    path = []
    hit_enemy = None
    for _ in range(max_range):
        x += dx
        y += dy
        if x < 0 or x >= MAP_W or y < 0 or y >= MAP_H:
            break
        if gs.tiles[y][x] == T_WALL:
            break
        path.append((x, y))
        # Check for enemy
        for e in gs.enemies:
            if e.x == x and e.y == y and e.is_alive():
                hit_enemy = e
                break
        if hit_enemy:
            break

    _animate_projectile(gs, path, char, color)

    if hit_enemy:
        dmg = random.randint(base_dmg[0], base_dmg[1]) + bonus + p.strength // 4
        # Wand class scaling (#8)
        if proj_type == "wand":
            if p.player_class == "mage":
                dmg = int(dmg * (1 + B["wand_mage_bonus_pct"]))
            elif p.player_class == "warrior":
                dmg = int(dmg * (1 - B["wand_warrior_penalty_pct"]))
        dmg = max(1, dmg - hit_enemy.defense // B["defense_divisor"])
        crit = random.random() < B["ranged_crit_chance"]
        if crit:
            dmg = int(dmg * B["crit_multiplier"])
            gs.msg(f"CRITICAL SHOT! {hit_enemy.name} takes {dmg}!", C_YELLOW)
            sound_alert(gs, "critical_hit")
        else:
            gs.msg(f"You hit {hit_enemy.name} for {dmg}!", C_WHITE)
        hit_enemy.hp -= dmg
        p.damage_dealt += dmg
        if not hit_enemy.is_alive():
            _award_kill(gs, hit_enemy)
            gs.enemies = [e for e in gs.enemies if e.is_alive()]
            _check_levelups(gs)
    else:
        gs.msg("The shot flies into the darkness.", C_DARK)

    return True


# ============================================================
# SPELLS
# ============================================================

def cast_spell_menu(gs: GameState, scr: Any) -> bool:
    """Show spell menu, cast selected spell."""
    p = gs.player
    if scr is None:
        return False

    scr.erase()
    safe_addstr(scr, 0, 1, "SPELLS", curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 1, 1, f"Mana: {p.mana}/{p.max_mana}", curses.color_pair(C_CYAN))

    spell_list = [(name, info) for name, info in SPELLS.items() if name in p.known_spells]
    max_letter = chr(ord('a') + len(spell_list) - 1) if spell_list else 'a'
    for i, (name, info) in enumerate(spell_list):
        y = i + 3
        if y >= SCREEN_H - 2:
            break
        letter = chr(ord('a') + i)
        cost_color = C_CYAN if p.mana >= info["cost"] else C_RED
        safe_addstr(scr, y, 2, f"{letter}) {name}", curses.color_pair(C_WHITE))
        safe_addstr(scr, y, 22, f"[{info['cost']} MP]", curses.color_pair(cost_color))
        safe_addstr(scr, y, 32, info["desc"][:SCREEN_W-34], curses.color_pair(C_DARK))

    safe_addstr(scr, SCREEN_H-2, 1, "Pick a spell, then choose direction if needed", curses.color_pair(C_DARK))
    safe_addstr(scr, SCREEN_H-1, 1, f"[a-{max_letter}] Cast  [ESC] Cancel", curses.color_pair(C_DARK))
    scr.refresh()
    key = scr.getch()
    if key == 27:
        return False
    idx = key - ord('a')
    if idx < 0 or idx >= len(spell_list):
        return False

    spell_name, spell_info = spell_list[idx]
    if p.mana < spell_info["cost"]:
        gs.msg("Not enough mana!", C_RED)
        return False

    return _cast_spell(gs, scr, spell_name, spell_info)


def cast_spell_headless(gs: GameState, spell_name: str, direction: tuple[int, int] | None = None, target_enemy: Enemy | None = None) -> bool:
    """Cast a spell in headless mode (for testing)."""
    p = gs.player
    if spell_name not in SPELLS:
        return False
    if spell_name not in p.known_spells:
        return False
    if "Silence" in p.status_effects:
        gs.msg("You are silenced! Cannot cast spells!", C_MAGENTA)
        return False
    info = SPELLS[spell_name]
    if p.mana < info["cost"]:
        return False
    return _cast_spell(gs, None, spell_name, info, direction=direction, target_enemy=target_enemy)


def _apply_spell_resist(gs: GameState, enemy: Enemy, dmg: int, element: str) -> int:
    """Apply elemental resistance/vulnerability to spell damage on an enemy.
    Returns adjusted damage and whether troll regen was suppressed."""
    if element and element != "physical":
        if element in enemy.resists:
            dmg = max(1, int(dmg * (1 - B["resist_reduction_pct"])))
        if element in enemy.vulnerable:
            dmg = int(dmg * B["vulnerable_increase_pct"])
        if enemy.etype == "troll" and element == "fire":
            enemy.regen_suppressed = 5
    return dmg


def _spell_fireball(gs: GameState, scr: Any, spell_info: dict[str, Any], direction: tuple[int, int] | None, target_enemy: Enemy | None) -> bool:
    """Handle Fireball spell: 3x3 AoE fire damage in a chosen direction."""
    p = gs.player
    if direction is None and scr:
        gs.msg("Fireball direction? (wasd/arrows/hjkl)", C_YELLOW)
        _get_render_game()(scr, gs)
        key = scr.getch()
        direction = _get_direction_delta(key)
    if direction is None:
        gs.msg("Cancelled.", C_WHITE)
        return False
    dx, dy = direction
    cx = p.x + dx * 3
    cy = p.y + dy * 3
    path = []
    for i in range(1, 4):
        path.append((p.x + dx*i, p.y + dy*i))
    _animate_projectile(gs, path, '*', C_RED)
    _animate_blast(gs, cx, cy, 1, '*', C_RED)
    kills = 0
    total_dmg = 0
    for ey in range(cy-1, cy+2):
        for ex in range(cx-1, cx+2):
            for e in gs.enemies:
                if e.x == ex and e.y == ey and e.is_alive():
                    dmg = random.randint(B["fireball_min"], B["fireball_max"]) + p.level * B["fireball_level_scale"]
                    dmg = _apply_spell_resist(gs, e, dmg, "fire")
                    e.hp -= dmg
                    total_dmg += dmg
                    p.damage_dealt += dmg
                    if not e.is_alive():
                        kills += _award_kill(gs, e, msg=False)
    gs.enemies = [e for e in gs.enemies if e.is_alive()]
    gs.msg(f"FIREBALL! {kills} killed, {total_dmg} total damage!", C_RED)
    _check_levelups(gs)
    return True


def _spell_lightning_bolt(gs: GameState, scr: Any, spell_info: dict[str, Any], direction: tuple[int, int] | None, target_enemy: Enemy | None) -> bool:
    """Handle Lightning Bolt spell: line damage with water AoE."""
    p = gs.player
    if direction is None and scr:
        gs.msg("Lightning direction? (wasd/arrows/hjkl)", C_YELLOW)
        _get_render_game()(scr, gs)
        key = scr.getch()
        direction = _get_direction_delta(key)
    if direction is None:
        gs.msg("Cancelled.", C_WHITE)
        return False
    dx, dy = direction
    x, y = p.x, p.y
    path = []
    hits = 0
    total_dmg = 0
    for _ in range(12):
        x += dx
        y += dy
        if x < 0 or x >= MAP_W or y < 0 or y >= MAP_H:
            break
        if gs.tiles[y][x] == T_WALL:
            break
        path.append((x, y))
        for e in gs.enemies:
            if e.x == x and e.y == y and e.is_alive():
                dmg = random.randint(B["lightning_min"], B["lightning_max"]) + p.level * B["lightning_level_scale"]
                dmg = _apply_spell_resist(gs, e, dmg, "lightning")
                e.hp -= dmg
                total_dmg += dmg
                p.damage_dealt += dmg
                hits += 1
                if not e.is_alive():
                    _award_kill(gs, e, msg=False)
    _animate_projectile(gs, path, '#', C_CYAN)
    for px2, py2 in path:
        if 0 <= px2 < MAP_W and 0 <= py2 < MAP_H and gs.tiles[py2][px2] == T_WATER:
            gs.msg("Lightning arcs through the water!", C_YELLOW)
            for e in gs.enemies:
                if (e.is_alive() and gs.tiles[e.y][e.x] == T_WATER
                        and abs(e.x - px2) + abs(e.y - py2) <= 3):
                    water_dmg = random.randint(5, 15)
                    water_dmg = _apply_spell_resist(gs, e, water_dmg, "lightning")
                    e.hp -= water_dmg
                    total_dmg += water_dmg
                    p.damage_dealt += water_dmg
                    if not e.is_alive():
                        hits += 1
                        _award_kill(gs, e, msg=False)
            break  # Only trigger water AoE once
    gs.enemies = [e for e in gs.enemies if e.is_alive()]
    gs.msg(f"LIGHTNING! Hit {hits} enemies for {total_dmg} damage!", C_CYAN)
    _check_levelups(gs)
    return True


def _spell_heal(gs: GameState, scr: Any, spell_info: dict[str, Any], direction: tuple[int, int] | None, target_enemy: Enemy | None) -> bool:
    """Handle Heal spell: restore HP."""
    p = gs.player
    heal_amt = random.randint(B["heal_spell_min"], B["heal_spell_max"]) + p.level * B["heal_spell_level_scale"]
    p.hp = min(p.max_hp, p.hp + heal_amt)
    gs.msg(f"Healing light! (+{heal_amt} HP)", C_GREEN)
    return True


def _spell_teleport(gs: GameState, scr: Any, spell_info: dict[str, Any], direction: tuple[int, int] | None, target_enemy: Enemy | None) -> bool:
    """Handle Teleport spell: blink to a random position."""
    p = gs.player
    pos = gs._find_spawn_pos()
    if pos:
        p.x, p.y = pos
        gs.msg("You blink across the dungeon!", C_MAGENTA)
    else:
        gs.msg("The spell fizzles.", C_DARK)
    return True


def _spell_freeze(gs: GameState, scr: Any, spell_info: dict[str, Any], direction: tuple[int, int] | None, target_enemy: Enemy | None) -> bool:
    """Handle Freeze spell: freeze nearest visible enemy."""
    p = gs.player
    nearest = target_enemy
    if nearest is None:
        nd = 999
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                d = abs(e.x - p.x) + abs(e.y - p.y)
                if d < nd:
                    nd = d
                    nearest = e
    if nearest and nearest.is_alive():
        nearest.frozen_turns = B["freeze_duration"]
        gs.msg(f"The {nearest.name} is frozen solid!", C_CYAN)
        return True
    else:
        gs.msg("No target in sight.", C_DARK)
        return False


def _spell_chain_lightning(gs: GameState, scr: Any, spell_info: dict[str, Any], direction: tuple[int, int] | None, target_enemy: Enemy | None) -> bool:
    """Handle Chain Lightning spell: hit primary target then chain to nearby enemies."""
    p = gs.player
    nearest = target_enemy
    if nearest is None:
        nd = 999
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                d = abs(e.x - p.x) + abs(e.y - p.y)
                if d < nd:
                    nd = d
                    nearest = e
    if nearest is None or not nearest.is_alive():
        gs.msg("No target in sight.", C_DARK)
        return False
    base_dmg = random.randint(B["chain_lightning_min"], B["chain_lightning_max"]) + p.level
    base_dmg = _apply_spell_resist(gs, nearest, base_dmg, "lightning")
    nearest.hp -= base_dmg
    p.damage_dealt += base_dmg
    total_dmg = base_dmg
    kills = 0
    chain_targets = [nearest]
    if not nearest.is_alive():
        kills += _award_kill(gs, nearest, msg=False)
    current_dmg = base_dmg
    last_hit = nearest
    for _ in range(2):
        current_dmg = int(current_dmg * B["chain_lightning_decay"])
        if current_dmg < 1:
            break
        best = None
        best_dist = 999
        for e in gs.enemies:
            if e.is_alive() and e not in chain_targets:
                d = abs(e.x - last_hit.x) + abs(e.y - last_hit.y)
                if d <= B["chain_lightning_chain_range"] and d < best_dist:
                    best_dist = d
                    best = e
        if best is None:
            break
        best.hp -= current_dmg
        p.damage_dealt += current_dmg
        total_dmg += current_dmg
        chain_targets.append(best)
        if not best.is_alive():
            kills += _award_kill(gs, best, msg=False)
        last_hit = best
    gs.enemies = [e for e in gs.enemies if e.is_alive()]
    gs.msg(f"CHAIN LIGHTNING! {len(chain_targets)} hit, {total_dmg} damage, {kills} killed!", C_CYAN)
    _check_levelups(gs)
    return True


def _spell_meteor(gs: GameState, scr: Any, spell_info: dict[str, Any], direction: tuple[int, int] | None, target_enemy: Enemy | None) -> bool:
    """Handle Meteor spell: 5x5 AoE fire damage in a chosen direction."""
    p = gs.player
    if direction is None and scr:
        gs.msg("Meteor direction? (wasd/arrows/hjkl)", C_YELLOW)
        _get_render_game()(scr, gs)
        key = scr.getch()
        direction = _get_direction_delta(key)
    if direction is None:
        gs.msg("Cancelled.", C_WHITE)
        return False
    dx, dy = direction
    cx = p.x + dx * B["meteor_range"]
    cy = p.y + dy * B["meteor_range"]
    _animate_blast(gs, cx, cy, 2, '#', C_RED)
    kills = 0
    total_dmg = 0
    for ey in range(cy - 2, cy + 3):
        for ex in range(cx - 2, cx + 3):
            for e in gs.enemies:
                if e.x == ex and e.y == ey and e.is_alive():
                    dmg = random.randint(B["meteor_min"], B["meteor_max"]) + p.level * B["meteor_level_scale"]
                    dmg = _apply_spell_resist(gs, e, dmg, "fire")
                    e.hp -= dmg
                    total_dmg += dmg
                    p.damage_dealt += dmg
                    if not e.is_alive():
                        kills += _award_kill(gs, e, msg=False)
    gs.enemies = [e for e in gs.enemies if e.is_alive()]
    gs.msg(f"METEOR! {kills} killed, {total_dmg} total damage!", C_RED)
    _check_levelups(gs)
    return True


def _spell_mana_shield(gs: GameState, scr: Any, spell_info: dict[str, Any], direction: tuple[int, int] | None, target_enemy: Enemy | None) -> bool:
    """Handle Mana Shield spell: apply protective status effect."""
    p = gs.player
    p.status_effects["Mana Shield"] = B["mana_shield_duration"]
    gs.msg("A shimmering mana shield surrounds you!", C_CYAN)
    return True


SPELL_HANDLERS: dict[str, Callable[..., bool]] = {
    "Fireball": _spell_fireball,
    "Lightning Bolt": _spell_lightning_bolt,
    "Heal": _spell_heal,
    "Teleport": _spell_teleport,
    "Freeze": _spell_freeze,
    "Chain Lightning": _spell_chain_lightning,
    "Meteor": _spell_meteor,
    "Mana Shield": _spell_mana_shield,
}


def _cast_spell(gs: GameState, scr: Any, spell_name: str, spell_info: dict[str, Any], direction: tuple[int, int] | None = None, target_enemy: Enemy | None = None) -> bool:
    """Execute the spell effect."""
    p = gs.player
    p.mana -= spell_info["cost"]
    # Spells generate noise (stealth system)
    gs.last_noise = max(gs.last_noise, _compute_noise(gs, "spell"))
    p.spells_cast += 1

    handler = SPELL_HANDLERS.get(spell_name)
    if handler is None:
        p.mana += spell_info["cost"]
        p.spells_cast -= 1
        return False

    result = handler(gs, scr, spell_info, direction, target_enemy)
    if not result:
        p.mana += spell_info["cost"]
        p.spells_cast -= 1
    return result


# ============================================================
# PLAYER ACTIONS
# ============================================================

def use_class_ability(gs: GameState, scr: Any = None) -> bool:
    """Activate the player's class-specific ability. Returns True if turn spent."""
    p = gs.player
    if not p.player_class or p.player_class not in CHARACTER_CLASSES:
        gs.msg("You have no class ability.", C_DARK)
        return False
    cc = CHARACTER_CLASSES[p.player_class]
    if p.ability_cooldown > 0:
        gs.msg(f"{cc['ability']} is on cooldown ({p.ability_cooldown} turns).", C_DARK)
        return False
    if p.mana < cc["ability_cost"]:
        gs.msg(f"Not enough mana for {cc['ability']}! (need {cc['ability_cost']})", C_RED)
        return False

    p.mana -= cc["ability_cost"]

    if p.player_class == "warrior":
        # Battle Cry: freeze all enemies within FOV for 5 turns
        frozen_count = 0
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                dist = abs(e.x - p.x) + abs(e.y - p.y)
                if dist <= 6:
                    e.frozen_turns = max(e.frozen_turns, 5)
                    frozen_count += 1
        gs.msg(f"BATTLE CRY! {frozen_count} enemies frozen in terror!", C_RED)
        p.ability_cooldown = B["battle_cry_cooldown"]
        return True

    elif p.player_class == "mage":
        # Arcane Blast: 3x3 AoE at a chosen direction (like fireball but more damage)
        gs.msg("Arcane Blast direction? (movement key)", C_CYAN)
        if scr:
            _get_render_game()(scr, gs)
            key = scr.getch()
            MOVE_KEYS_LOCAL = {
                curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
                curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
                ord('w'): (0,-1), ord('s'): (0,1),
                ord('a'): (-1,0), ord('d'): (1,0),
                ord('h'): (-1,0), ord('j'): (0,1),
                ord('k'): (0,-1), ord('l'): (1,0),
                ord('y'): (-1,-1), ord('u'): (1,-1),
                ord('b'): (-1,1), ord('n'): (1,1),
            }
            if key == 27:
                p.mana += cc["ability_cost"]  # refund
                gs.msg("Cancelled.", C_DARK)
                return False
            if key not in MOVE_KEYS_LOCAL:
                p.mana += cc["ability_cost"]  # refund
                gs.msg("Invalid direction.", C_DARK)
                return False
            dx, dy = MOVE_KEYS_LOCAL[key]
        else:
            dx, dy = 1, 0  # default for headless
        # Hit 3x3 area, 5 tiles out
        cx, cy = p.x + dx * 5, p.y + dy * 5
        _animate_blast(gs, cx, cy, 1, '*', C_CYAN)
        hit_count = 0
        kills = 0
        total_dmg = 0
        for e in gs.enemies:
            if e.is_alive() and abs(e.x - cx) <= 1 and abs(e.y - cy) <= 1:
                dmg = random.randint(B["arcane_blast_min"], B["arcane_blast_max"]) + p.strength
                e.hp -= dmg
                p.damage_dealt += dmg
                total_dmg += dmg
                hit_count += 1
                gs.msg(f"Arcane Blast hits {e.name} for {dmg}!", C_CYAN)
                if not e.is_alive():
                    kills += _award_kill(gs, e)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        gs.msg(f"Arcane Blast detonates! ({hit_count} hit, {kills} killed)", C_CYAN)
        _check_levelups(gs)
        p.ability_cooldown = B["ability_cooldown"]
        return True

    elif p.player_class == "rogue":
        # Shadow Step: teleport behind nearest enemy, auto-crit
        target = None
        min_dist = 999
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                d = abs(e.x - p.x) + abs(e.y - p.y)
                if d < min_dist:
                    min_dist = d
                    target = e
        if not target:
            p.mana += cc["ability_cost"]  # refund
            gs.msg("No visible enemy to Shadow Step to!", C_DARK)
            return False
        # Find tile behind enemy (opposite side from player)
        dx = 1 if target.x > p.x else (-1 if target.x < p.x else 0)
        dy = 1 if target.y > p.y else (-1 if target.y < p.y else 0)
        land_x, land_y = target.x + dx, target.y + dy
        # If landing spot is blocked, land on enemy's tile (attack from current)
        if (0 < land_x < MAP_W-1 and 0 < land_y < MAP_H-1 and
            gs.tiles[land_y][land_x] in WALKABLE and
            not any(e2.x == land_x and e2.y == land_y and e2.is_alive() for e2 in gs.enemies)):
            p.x, p.y = land_x, land_y
        gs.msg(f"You shadow step behind the {target.name}!", C_GREEN)
        # Auto-crit damage
        if p.weapon:
            lo, hi = p.weapon.data["dmg"]
            base_dmg = random.randint(lo, hi) + p.weapon.data.get("bonus", 0) + p.strength
        else:
            base_dmg = random.randint(1, 3) + p.strength
        crit_dmg = int(base_dmg * B["crit_multiplier"])
        target.hp -= crit_dmg
        p.damage_dealt += crit_dmg
        gs.msg(f"CRITICAL! Shadow Strike hits for {crit_dmg}!", C_YELLOW)
        if not target.is_alive():
            _award_kill(gs, target)
            gs.enemies = [e for e in gs.enemies if e.is_alive()]
            _check_levelups(gs)
        p.ability_cooldown = B["shadow_step_cooldown"]
        return True

    return False


# ============================================================
# CLASS TECHNIQUES (Warrior/Rogue abilities — parallel to spells)
# ============================================================

def use_technique_menu(gs: GameState, scr: Any) -> bool:
    """Show class technique menu, execute selected ability."""
    p = gs.player
    if scr is None:
        return False
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)

    if p.player_class == "mage":
        gs.msg("No class techniques. Use [z] for spells.", C_DARK)
        return False

    abilities = CLASS_ABILITIES.get(p.player_class, {})
    known = [(name, info) for name, info in abilities.items() if name in p.known_abilities]

    if not known:
        gs.msg("You haven't learned any techniques yet.", C_DARK)
        return False

    title = "COMBAT TECHNIQUES" if p.player_class == "warrior" else "TECHNIQUES"
    scr.erase()
    safe_addstr(scr, 0, 1, title, curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 1, 1, f"Mana: {p.mana}/{p.max_mana}", curses.color_pair(C_CYAN))

    max_letter = chr(ord('a') + len(known) - 1)
    for i, (name, info) in enumerate(known):
        y = i + 3
        if y >= SCREEN_H - 2:
            break
        letter = chr(ord('a') + i)
        cost_color = C_CYAN if p.mana >= info["cost"] else C_RED
        safe_addstr(scr, y, 2, f"{letter}) {name}", curses.color_pair(C_WHITE))
        safe_addstr(scr, y, 22, f"[{info['cost']} MP]", curses.color_pair(cost_color))
        safe_addstr(scr, y, 32, info["desc"][:SCREEN_W-34], curses.color_pair(C_DARK))

    safe_addstr(scr, SCREEN_H-1, 1, f"[a-{max_letter}] Use  [ESC] Cancel", curses.color_pair(C_DARK))
    scr.refresh()
    key = scr.getch()
    if key == 27:
        return False
    idx = key - ord('a')
    if idx < 0 or idx >= len(known):
        return False

    ability_name, ability_info = known[idx]
    if p.mana < ability_info["cost"]:
        gs.msg("Not enough mana!", C_RED)
        return False

    return _execute_ability(gs, scr, ability_name, ability_info)


def use_ability_headless(gs: GameState, ability_name: str) -> bool:
    """Execute a class ability in headless mode (for bot/agent/tests)."""
    p = gs.player
    if ability_name not in p.known_abilities:
        return False
    abilities = CLASS_ABILITIES.get(p.player_class, {})
    if ability_name not in abilities:
        return False
    info = abilities[ability_name]
    if p.mana < info["cost"]:
        return False
    return _execute_ability(gs, None, ability_name, info)


def _execute_ability(gs: GameState, scr: Any, ability_name: str, ability_info: dict[str, Any]) -> bool:
    """Execute the ability effect. Returns True if turn was spent."""
    p = gs.player
    p.mana -= ability_info["cost"]

    if ability_name == "Whirlwind":
        # Hit ALL adjacent enemies (8 directions)
        hit_count = 0
        total_dmg = 0
        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                if ddx == 0 and ddy == 0:
                    continue
                tx, ty = p.x + ddx, p.y + ddy
                for e in gs.enemies:
                    if e.x == tx and e.y == ty and e.is_alive():
                        dmg = p.attack_damage()
                        dmg = max(1, dmg - e.defense // B["defense_divisor"])
                        e.hp -= dmg
                        p.damage_dealt += dmg
                        total_dmg += dmg
                        hit_count += 1
                        if not e.is_alive():
                            _award_kill(gs, e)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        if hit_count > 0:
            gs.msg(f"WHIRLWIND! Hit {hit_count} enemies for {total_dmg} total damage!", C_YELLOW)
        else:
            gs.msg("WHIRLWIND! But no enemies were adjacent.", C_DARK)
        _check_levelups(gs)
        return True

    elif ability_name == "Cleaving Strike":
        # Auto-target nearest visible enemy, 2x damage ignoring defense
        target = None
        min_dist = 999
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                d = abs(e.x - p.x) + abs(e.y - p.y)
                if d < min_dist:
                    min_dist = d
                    target = e
        if not target:
            p.mana += ability_info["cost"]  # refund
            gs.msg("No visible enemy to strike!", C_DARK)
            return False
        dmg = int(p.attack_damage() * B["cleaving_strike_multiplier"])
        # Ignore enemy defense
        target.hp -= dmg
        p.damage_dealt += dmg
        gs.msg(f"CLEAVING STRIKE! Hit {target.name} for {dmg} damage, ignoring armor!", C_YELLOW)
        if not target.is_alive():
            _award_kill(gs, target)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        _check_levelups(gs)
        return True

    elif ability_name == "Shield Wall":
        p.status_effects["Shield Wall"] = B["shield_wall_duration"]
        gs.msg(f"You raise your shield! Incoming damage halved for {B['shield_wall_duration']} turns.", C_CYAN)
        return True

    elif ability_name == "Backstab":
        # Buff: next melee is guaranteed 2.5x crit (consumed on use)
        p.status_effects["Backstab"] = 99  # effectively infinite, removed on use
        gs.msg("You prepare a deadly backstab...", C_GREEN)
        return True

    elif ability_name == "Poison Blade":
        p.status_effects["Poison Blade"] = B["poison_blade_duration"]
        gs.msg(f"You coat your blade with venom! ({B['poison_blade_duration']} turns)", C_GREEN)
        return True

    elif ability_name == "Smoke Bomb":
        # Freeze + blind all enemies within radius
        hit_count = 0
        for e in gs.enemies:
            if e.is_alive():
                dist = abs(e.x - p.x) + abs(e.y - p.y)
                if dist <= B["smoke_bomb_blind_radius"]:
                    e.frozen_turns = max(e.frozen_turns, B["smoke_bomb_blind_duration"])
                    hit_count += 1
        # Player evasion boost
        p.status_effects["Smoke Evasion"] = B["smoke_bomb_evasion_duration"]
        if hit_count > 0:
            gs.msg(f"SMOKE BOMB! {hit_count} enemies blinded and disoriented!", C_GREEN)
        else:
            gs.msg("SMOKE BOMB! +evasion but no enemies in range.", C_DARK)
        return True

    # Unknown ability
    p.mana += ability_info["cost"]  # refund
    return False


def _journal_potion_desc(eff: str) -> str:
    """Return short description for journal entry (#6)."""
    return {"Healing": "Restores HP", "Strength": "Boost STR temporarily",
            "Speed": "Boost speed temporarily", "Poison": "Deals damage!",
            "Blindness": "Reduces vision!", "Experience": "Grants XP",
            "Resistance": "Reduces incoming damage", "Berserk": "Rage mode",
            "Mana": "Restores MP"}.get(eff, eff)

def _journal_scroll_desc(eff: str) -> str:
    return {"Identify": "Reveals all items", "Teleport": "Random teleport",
            "Fireball": "AoE fire damage", "Mapping": "Reveals floor map",
            "Enchant": "Upgrades weapon/armor", "Fear": "Scares enemies",
            "Summon": "Summons hostile enemy!", "Lightning": "Zaps nearest enemy"}.get(eff, eff)

def use_alchemy_table(gs: GameState) -> bool:
    """Use alchemy table to identify items and grant alchemical insights."""
    p = gs.player
    pos_key = (p.x, p.y)
    if gs.tiles[p.y][p.x] != T_ALCHEMY_TABLE:
        gs.msg("No alchemy table here.", C_DARK)
        return False
    if pos_key in gs.alchemy_used:
        gs.msg("This table has already been used.", C_DARK)
        return False
    # Find unidentified potions/scrolls/rings in inventory
    unid = [it for it in p.inventory
            if it.item_type in ("potion", "scroll", "ring") and not it.identified]
    if not unid:
        # Even with nothing to identify, grant a minor alchemical boon
        boon = random.choice(["mana", "resist", "clarity"])
        if boon == "mana" and p.max_mana > 0:
            restored = min(p.max_mana - p.mana, 10)
            p.mana += restored
            gs.msg(f"The table's residual magic restores {restored} MP!", C_CYAN)
        elif boon == "resist":
            gs.msg("Alchemical fumes grant temporary Resistance!", C_CYAN)
            p.status_effects["Resistance"] = p.status_effects.get("Resistance", 0) + 20
        else:
            # Reveal trap locations on current floor
            revealed = 0
            for trap in gs.traps:
                if not trap["visible"] and not trap["disarmed"]:
                    trap["visible"] = True
                    revealed += 1
            if revealed:
                gs.msg(f"The table's vapors reveal {revealed} hidden trap(s)!", C_YELLOW)
            else:
                gs.msg("Alchemical vapors swirl but reveal nothing new.", C_CYAN)
        gs.alchemy_used.add(pos_key)
        return True
    # Identify ALL unidentified items of the chosen type
    target = random.choice(unid)
    target.identified = True
    eff = target.data.get("effect", "")
    if target.item_type == "potion":
        gs.id_potions.add(eff)
        gs.journal[f"Potion of {eff}"] = _journal_potion_desc(eff)
        count = 0
        for inv in p.inventory:
            if inv.item_type == "potion" and inv.data.get("effect") == eff:
                inv.identified = True
                count += 1
        desc = _journal_potion_desc(eff)
        gs.msg(f"Identified: Potion of {eff} — {desc}", C_CYAN)
        if count > 1:
            gs.msg(f"  ({count} potions of this type identified!)", C_CYAN)
    elif target.item_type == "scroll":
        gs.id_scrolls.add(eff)
        gs.journal[f"Scroll of {eff}"] = _journal_scroll_desc(eff)
        count = 0
        for inv in p.inventory:
            if inv.item_type == "scroll" and inv.data.get("effect") == eff:
                inv.identified = True
                count += 1
        desc = _journal_scroll_desc(eff)
        gs.msg(f"Identified: Scroll of {eff} — {desc}", C_CYAN)
        if count > 1:
            gs.msg(f"  ({count} scrolls of this type identified!)", C_CYAN)
    elif target.item_type == "ring":
        target.identified = True
        ring_eff = target.data.get("effect", target.data.get("resist", "unknown"))
        gs.msg(f"Identified: {target.display_name} — {ring_eff}!", C_CYAN)
    gs.alchemy_used.add(pos_key)
    return True

def _toggle_switch(gs: GameState, sx: int, sy: int) -> None:
    """Toggle a switch and check puzzle state (#9)."""
    tile = gs.tiles[sy][sx]
    if tile == T_SWITCH_OFF:
        gs.tiles[sy][sx] = T_SWITCH_ON
        gs.msg("Click! The switch activates.", C_YELLOW)
    elif tile == T_SWITCH_ON:
        gs.tiles[sy][sx] = T_SWITCH_OFF
        gs.msg("Click! The switch deactivates.", C_YELLOW)
    # Check if any puzzle is solved
    for puzzle in gs.puzzles:
        if puzzle["solved"]:
            continue
        if puzzle["type"] in ("switch", "locked_stairs"):
            all_on = all(gs.tiles[py][px] == T_SWITCH_ON for px, py in puzzle["positions"])
            if all_on:
                puzzle["solved"] = True
                if puzzle["type"] == "locked_stairs":
                    stx, sty = puzzle["stairs"]
                    gs.tiles[sty][stx] = T_STAIRS_DOWN
                    gs.msg("You hear a rumble... The stairs are unlocked!", C_YELLOW)
                else:
                    # Reward: spawn high-tier item
                    rx, ry, rw, rh = puzzle["room"]
                    item = gs._random_item(rx + rw//2, ry + rh//2, gs.player.floor + 2)
                    if item:
                        item.identified = True
                        gs.items.append(item)
                    gs.msg("All switches activated! A chest appears!", C_GOLD)
        elif puzzle["type"] == "pressure":
            # Track which plates have been stepped on
            pos = (sx, sy)
            if pos in [(px, py) for px, py in puzzle["positions"]]:
                if pos not in puzzle["activated"]:
                    puzzle["activated"].append(pos)
                    gs.msg(f"Pressure plate activated! ({len(puzzle['activated'])}/{len(puzzle['positions'])})", C_YELLOW)
                if len(puzzle["activated"]) >= len(puzzle["positions"]):
                    puzzle["solved"] = True
                    rx, ry, rw, rh = puzzle["room"]
                    gold = random.randint(B["puzzle_room_gold_min"], B["puzzle_room_gold_max"])
                    gs.player.gold += gold
                    item = gs._random_item(rx + rw//2, ry + rh//2, gs.player.floor + 2)
                    if item:
                        item.identified = True
                        gs.items.append(item)
                    gs.msg(f"All plates activated! You find {gold} gold and a reward!", C_GOLD)

def _interact_pedestal(gs: GameState, px: int, py: int) -> bool:
    """Light a pedestal (costs torch fuel) (#9)."""
    if gs.tiles[py][px] != T_PEDESTAL_UNLIT:
        return False
    if gs.player.torch_fuel < 10:
        gs.msg("Not enough torch fuel to light the pedestal!", C_RED)
        return False
    gs.player.torch_fuel -= 10
    gs.tiles[py][px] = T_PEDESTAL_LIT
    gs.msg("The pedestal flares to life!", C_YELLOW)
    # Check if torch or sequence puzzle is solved
    for puzzle in gs.puzzles:
        if puzzle["solved"]:
            continue
        if puzzle["type"] == "torch":
            all_lit = all(gs.tiles[py2][px2] == T_PEDESTAL_LIT for px2, py2 in puzzle["positions"])
            if all_lit:
                puzzle["solved"] = True
                rx, ry, rw, rh = puzzle["room"]
                item = gs._random_item(rx + rw//2, ry + rh//2, gs.player.floor + 2)
                if item:
                    item.identified = True
                    gs.items.append(item)
                gs.msg("All pedestals lit! A chest materializes!", C_GOLD)
        elif puzzle["type"] == "sequence":
            # Check if this pedestal is the correct next in sequence
            pos = (px, py)
            if pos in puzzle["positions"]:
                idx = puzzle["positions"].index(pos)
                step = puzzle["current_step"]
                if puzzle["correct_order"][step] == idx:
                    puzzle["current_step"] += 1
                    gs.msg(f"Correct! ({puzzle['current_step']}/{len(puzzle['positions'])})", C_GREEN)
                    if puzzle["current_step"] >= len(puzzle["positions"]):
                        puzzle["solved"] = True
                        rx, ry, rw, rh = puzzle["room"]
                        gold = random.randint(B["puzzle_room_gold_min"], B["puzzle_room_gold_max"])
                        gs.player.gold += gold
                        item = gs._random_item(rx + rw//2, ry + rh//2, gs.player.floor + 3)
                        if item:
                            item.identified = True
                            gs.items.append(item)
                        gs.msg(f"Sequence complete! You find {gold} gold and a rare reward!", C_GOLD)
                else:
                    # Wrong order — reset all pedestals
                    puzzle["current_step"] = 0
                    for px2, py2 in puzzle["positions"]:
                        gs.tiles[py2][px2] = T_PEDESTAL_UNLIT
                    gs.msg("Wrong sequence! The pedestals go dark.", C_RED)
                    # Refund torch fuel since we'll deduct again
                    gs.player.torch_fuel += 10
                    return False
    return True

def enchant_weapon_headless(gs: GameState) -> bool:
    """Apply a random enchantment to the player's equipped weapon (headless)."""
    p = gs.player
    if gs.tiles[p.y][p.x] != T_ENCHANT_ANVIL:
        gs.msg("You need to be at an enchanting anvil!", C_RED)
        return False
    if not p.weapon:
        gs.msg("You have no weapon equipped!", C_RED)
        return False
    if p.gold < B["enchant_gold_cost"]:
        gs.msg(f"You need {B['enchant_gold_cost']} gold to enchant! (Have: {p.gold})", C_RED)
        return False
    if p.weapon.data.get("enchantment"):
        gs.msg("This weapon is already enchanted!", C_YELLOW)
        return False
    p.gold -= B["enchant_gold_cost"]
    p.gold_spent += B["enchant_gold_cost"]
    enchant_key = random.choice(list(ENCHANTMENTS.keys()))
    enchant = ENCHANTMENTS[enchant_key]
    p.weapon.data["enchantment"] = enchant_key
    p.weapon.data["enchant_bonus_dmg"] = enchant["bonus_dmg"]
    p.weapon.data["enchant_proc_chance"] = enchant["proc_chance"]
    p.weapon.data["enchant_proc_effect"] = enchant["proc_effect"]
    old_name = p.weapon.subtype
    p.weapon.subtype = f"{enchant['name']} {old_name}"
    gs.msg(f"Your {old_name} is now enchanted with {enchant['name']}!", C_GOLD)
    gs.msg(f"  {enchant['desc']}", C_YELLOW)
    return True


def _interact_npc(gs: GameState, npc: dict[str, Any]) -> None:
    """Handle NPC encounter interaction."""
    npc["interacted"] = True
    gs.msg(f'{npc["name"]}: "{npc["dialogue"]}"', C_YELLOW)
    p = gs.player

    if npc["interaction"] == "gift":
        item = gs._random_item(npc["x"], npc["y"], p.floor + 1)
        if item:
            item.identified = True
            gs.items.append(item)
            gs.msg(f"The {npc['name']} gives you a {item.subtype}!", C_GOLD)

    elif npc["interaction"] == "buff":
        buff_type = random.choice(["Strength", "Resistance", "Speed"])
        if buff_type == "Strength":
            p.status_effects["Strength"] = 30
            gs.msg("You feel surging power! (+Strength for 30 turns)", C_GREEN)
        elif buff_type == "Resistance":
            p.status_effects["Resistance"] = 30
            gs.msg("A protective ward surrounds you! (+Resistance for 30 turns)", C_CYAN)
        elif buff_type == "Speed":
            p.status_effects["Speed"] = 30
            gs.msg("Your reflexes sharpen! (+Speed for 30 turns)", C_YELLOW)

    elif npc["interaction"] == "warning":
        # Give a weapon and bestiary hint
        item = gs._random_item(npc["x"], npc["y"], p.floor + 2)
        if item:
            item.identified = True
            gs.items.append(item)
            gs.msg(f"The knight hands you a {item.subtype}.", C_GOLD)
        gs.msg("'The next boss is vulnerable to fire and cold. Remember that.'", C_YELLOW)

    elif npc["interaction"] == "reveal":
        # Reveal the entire map
        for y in range(MAP_H):
            for x in range(MAP_W):
                gs.explored[y][x] = True
        gs.msg("The ghost reveals the entire floor to you!", C_MAGENTA)

    elif npc["interaction"] == "shop":
        # Mini-shop: give player 2-3 identified items nearby
        count = random.randint(2, 3)
        for _ in range(count):
            item = gs._random_item(npc["x"], npc["y"], p.floor + 1)
            if item:
                item.identified = True
                item.x = npc["x"] + random.randint(-1, 1)
                item.y = npc["y"] + random.randint(-1, 1)
                gs.items.append(item)
        gs.msg(f"The merchant spreads out {count} items for you!", C_GOLD)


def show_journal(scr: Any, gs: GameState) -> None:
    """Display journal of identified items (#6)."""
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    scr.erase()
    safe_addstr(scr, 0, 1, "JOURNAL", curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 1, 1, "Identified potions and scrolls:", curses.color_pair(C_DARK))
    row = 3
    if not gs.journal:
        safe_addstr(scr, row, 2, "Nothing discovered yet.", curses.color_pair(C_DARK))
    else:
        # Group by type
        potions = [(k, v) for k, v in sorted(gs.journal.items()) if k.startswith("Potion")]
        scrolls = [(k, v) for k, v in sorted(gs.journal.items()) if k.startswith("Scroll")]
        if potions:
            safe_addstr(scr, row, 2, "--- Potions ---", curses.color_pair(C_MAGENTA))
            row += 1
            for name, desc in potions:
                if row >= SCREEN_H - 2:
                    break
                color_name = gs.potion_ids.get(name.replace("Potion of ", ""), "?")
                safe_addstr(scr, row, 3, f"{color_name} = {name}: {desc}", curses.color_pair(C_MAGENTA))
                row += 1
        if scrolls:
            row += 1
            safe_addstr(scr, row, 2, "--- Scrolls ---", curses.color_pair(C_YELLOW))
            row += 1
            for name, desc in scrolls:
                if row >= SCREEN_H - 2:
                    break
                label = gs.scroll_ids.get(name.replace("Scroll of ", ""), "?")
                safe_addstr(scr, row, 3, f"{label} = {name}: {desc}", curses.color_pair(C_YELLOW))
                row += 1
    safe_addstr(scr, SCREEN_H - 1, 1, "[ Press any key ]", curses.color_pair(C_DARK))
    scr.refresh()
    scr.getch()


def player_move(gs: GameState, dx: int, dy: int) -> bool:
    p = gs.player
    # Confusion: random movement direction
    if "Confusion" in p.status_effects:
        dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
        gs.msg("You stumble in confusion!", C_MAGENTA)
    nx, ny = p.x + dx, p.y + dy
    if nx < 0 or nx >= MAP_W or ny < 0 or ny >= MAP_H:
        return False
    tile = gs.tiles[ny][nx]
    if tile == T_WALL:
        gs.msg("Blocked!", C_DARK)
        return False
    if tile == T_LAVA:
        if "fire" in p.player_resists() or "cold" in p.player_resists():
            gs.msg("You endure the searing heat! (-2 HP)", C_RED)
            p.hp -= 2
            p.damage_taken += 2
            if p.hp <= 0:
                gs.game_over = True
                gs.death_cause = "burned by lava"
                sound_alert(gs, "death")
                return True
        else:
            gs.msg("The lava would burn you alive!", C_RED)
            return False
    # Fear: prevent moving closer to visible enemies
    if "Fear" in p.status_effects:
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                old_dist = abs(e.x - p.x) + abs(e.y - p.y)
                new_dist = abs(e.x - nx) + abs(e.y - ny)
                if new_dist < old_dist:
                    gs.msg("Fear grips you! You can't approach the enemy!", C_MAGENTA)
                    return False
    if tile == T_WATER:
        gs.msg("You splash through water.", C_WATER)
        if random.random() < 0.5:
            p.hunger = max(0, p.hunger - B["hunger_per_move"])  # Extra hunger cost
        # Water extinguishes burning/fire effects
        if "Burning" in p.status_effects:
            del p.status_effects["Burning"]
            gs.msg("The water extinguishes the flames!", C_CYAN)
    # Attack enemy
    for e in gs.enemies:
        if e.x == nx and e.y == ny and e.is_alive():
            player_attack(gs, e)
            gs.last_noise = max(gs.last_noise, _compute_noise(gs, "combat"))
            return True
    p.x = nx
    p.y = ny
    # Generate noise for movement (stealth system)
    gs.last_noise = max(gs.last_noise, _compute_noise(gs, "walk"))
    # Trap check
    _check_traps_on_move(gs, nx, ny)
    if gs.game_over:
        return True
    _passive_trap_detect(gs)
    # Hunger
    p.hunger = max(0, p.hunger - B["hunger_per_move"])
    if p.hunger <= 0:
        p.hp -= B["starvation_damage"]
        if gs.turn_count % 5 == 0:
            gs.msg("You are starving!", C_RED)
        if p.hp <= 0:
            gs.game_over = True
            gs.death_cause = "starvation"
            sound_alert(gs, "death")
    if p.ring and p.ring.data.get("effect") == "hunger":
        p.hunger = max(0, p.hunger - B["hunger_curse_extra"])
    if p.ring and p.ring.data.get("effect") == "regen":
        if gs.turn_count % 3 == 0 and p.hp < p.max_hp:
            p.hp = min(p.max_hp, p.hp + 1)
    # Auto-pickup
    pickup = [i for i in gs.items if i.x == nx and i.y == ny]
    for item in pickup:
        if item.item_type == "gold":
            p.gold += item.data["amount"]
            p.gold_earned += item.data["amount"]
            gs.msg(f"Picked up {item.data['amount']} gold.", C_GOLD)
            gs.items.remove(item)
        else:
            # Scrolls exempt from capacity (#16)
            capacity_ok = (item.item_type == "scroll" or
                           sum(1 for it in p.inventory if it.item_type != "scroll") < p.carry_capacity)
            if capacity_ok:
                gs.items.remove(item)
                p.inventory.append(item)
                p.items_found += 1
                p.items_by_type[item.item_type] = p.items_by_type.get(item.item_type, 0) + 1
                gs.msg(f"Picked up {item.display_name}.", item.color)
                # Auto-equip better armor (#14)
                if item.item_type == "armor":
                    cur_def = p.armor.data["defense"] if p.armor else -1
                    if item.data["defense"] > cur_def:
                        if p.armor:
                            p.armor.equipped = False
                        item.equipped = True
                        p.armor = item
                        gs.msg(f"Auto-equipped {item.display_name}!", C_BLUE)
                # Auto-equip weapon if bare-fisted (#14)
                elif item.item_type == "weapon" and not p.weapon:
                    item.equipped = True
                    p.weapon = item
                    gs.msg(f"Auto-equipped {item.display_name}!", C_YELLOW)
            else:
                gs.msg("Inventory full!", C_RED)
    # Tile messages
    if tile == T_STAIRS_DOWN:
        gs.msg("Press > to descend.", C_YELLOW)
    elif tile == T_STAIRS_UP:
        gs.msg("Press < to ascend.", C_YELLOW)
    elif tile == T_SHRINE:
        gs.msg("A shrine glows. Press 'p' to pray.", C_SHRINE)
    elif tile == T_SHOP_FLOOR:
        if gs.get_shop_at(nx, ny):
            gs.msg("A shop! Press '$' to browse.", C_GOLD)
    elif tile == T_ALCHEMY_TABLE:
        gs.msg("An alchemy table! Press 'e' to use.", C_CYAN)
    elif tile == T_FOUNTAIN:
        gs.msg("A magical fountain! Press 'e' to drink.", C_WATER)
    elif tile == T_ENCHANT_ANVIL:
        gs.msg(f"An enchanting anvil! Press 'E' to enchant ({B['enchant_gold_cost']} gold).", C_GOLD)
    elif tile == T_PEDESTAL_UNLIT:
        gs.msg("An unlit pedestal. Step on it to light (costs torch fuel).", C_YELLOW)
    elif tile == T_SWITCH_OFF:
        _toggle_switch(gs, nx, ny)
    elif tile == T_SWITCH_ON:
        _toggle_switch(gs, nx, ny)
    elif tile == T_STAIRS_LOCKED:
        gs.msg("The stairs are sealed! Solve the puzzle to unlock.", C_RED)
    # Vignette interaction
    for vig in gs.vignettes:
        if vig["x"] == nx and vig["y"] == ny and not vig["examined"]:
            vig["examined"] = True
            gs.msg(f"[{vig['name']}] {vig['lore']}", C_MAGENTA)
            # Chance to spawn minor loot
            if not vig["loot_spawned"] and random.random() < vig["loot_chance"]:
                vig["loot_spawned"] = True
                item = gs._random_item(nx, ny, min(gs.player.floor + vig["loot_tier"], MAX_FLOORS))
                if item:
                    item.identified = True
                    gs.items.append(item)
                    gs.msg(f"You find something useful nearby!", C_GOLD)
    # NPC interaction
    for npc in gs.npcs:
        if npc["x"] == nx and npc["y"] == ny and not npc["interacted"]:
            _interact_npc(gs, npc)
    return True
