"""
Floor generation for Depths of Dread.

Extracted from GameState to separate floor-building concerns
from core game state management.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .constants import (
    ARMOR_TYPES,
    ARROW_ITEM,
    BOW_TYPES,
    BRANCH_CHOICES,
    BRANCH_DEFS,
    C_CYAN,
    C_RED,
    C_YELLOW,
    ENEMY_TYPES,
    FOOD_TYPES,
    MAP_H,
    MAP_W,
    MAX_FLOORS,
    NPC_TYPES,
    POTION_EFFECTS,
    RING_TYPES,
    SCROLL_EFFECTS,
    T_ALCHEMY_TABLE,
    T_CORRIDOR,
    T_ENCHANT_ANVIL,
    T_FLOOR,
    T_FOUNTAIN,
    T_LAVA,
    T_PEDESTAL_UNLIT,
    T_SECRET_WALL,
    T_SHOP_FLOOR,
    T_SHRINE,
    T_STAIRS_DOWN,
    T_STAIRS_LOCKED,
    T_SWITCH_OFF,
    T_WALL,
    T_WALL_TORCH,
    T_WATER,
    THEMES,
    THROWING_DAGGER,
    TORCH_TYPES,
    TRAP_TYPES,
    VIGNETTE_TEMPLATES,
    WAND_TYPES,
    WEAPON_TYPES,
    B,
)
from .entities import Enemy, Item
from .mapgen import generate_dungeon

if TYPE_CHECKING:
    from .game import GameState


def generate_floor(gs: GameState, floor_num: int) -> None:
    """Generate a new dungeon floor with all content."""
    gs.player.floor = floor_num
    if floor_num > gs.player.deepest_floor:
        gs.player.deepest_floor = floor_num
    gs.speedrun_timer = 0
    gs.floors_explored.add(floor_num)
    gs.tiles, gs.rooms, start, gs.stair_down = generate_dungeon(floor_num)
    gs.player.x, gs.player.y = start
    gs.explored = [[False] * MAP_W for _ in range(MAP_H)]
    gs.enemies = []
    gs.items = []
    gs.shops = []
    gs.shop_discovered = False
    gs.alchemy_used = set()
    gs.puzzles = []
    gs.wall_torches = []
    gs.traps = []
    gs.vignettes = []
    gs.npcs = []
    # Determine active branch for this floor
    gs.active_branch = _get_active_branch(gs, floor_num)
    # Apply branch-specific terrain modifications
    if gs.active_branch:
        _apply_branch_terrain(gs, floor_num, gs.active_branch)
    _populate_enemies(gs, floor_num)
    _populate_items(gs, floor_num)
    _place_shop(gs, floor_num)
    _place_shrine(gs, floor_num)
    _place_alchemy_table(gs, floor_num)
    _place_wall_torches(gs, floor_num)
    _place_puzzle(gs, floor_num)
    _place_traps(gs, floor_num)
    _place_vignettes(gs, floor_num)
    _place_npcs(gs, floor_num)
    _place_enchant_anvil(gs, floor_num)
    _place_fountain(gs, floor_num)
    _place_secret_room(gs, floor_num)
    # Branch-specific extra traps
    if gs.active_branch:
        bdef = BRANCH_DEFS[gs.active_branch]
        extra_traps = bdef.get("extra_traps", 0)
        for _ in range(extra_traps):
            _place_single_trap(gs, floor_num)
    # Determine theme
    if gs.active_branch:
        theme = BRANCH_DEFS[gs.active_branch]["theme"]
    else:
        theme = THEMES[floor_num - 1] if floor_num <= len(THEMES) else "The Abyss"
    gs.msg(f"--- Floor {floor_num}: {theme} ---", C_YELLOW)
    if gs.active_branch:
        bdef = BRANCH_DEFS[gs.active_branch]
        gs.msg(f"You are in {bdef['name']}.", C_CYAN)
    if floor_num == MAX_FLOORS:
        gs.msg("You feel an overwhelming dread...", C_RED)


def _get_active_branch(gs: GameState, floor_num: int) -> str | None:
    """Determine if the given floor is in a branch. Returns branch key or None."""
    for choice_floor, (branch_a, branch_b) in BRANCH_CHOICES.items():
        chosen = gs.branch_choices.get(choice_floor)
        if chosen:
            bdef = BRANCH_DEFS[chosen]
            if floor_num in bdef["floors"]:
                return chosen
    return None


def _apply_branch_terrain(gs: GameState, floor_num: int, branch_key: str) -> None:
    """Modify terrain tiles for a branch (more water/lava)."""
    bdef = BRANCH_DEFS[branch_key]
    floor_tiles = [(x, y) for y in range(MAP_H) for x in range(MAP_W)
                   if gs.tiles[y][x] == T_FLOOR]
    random.shuffle(floor_tiles)
    water_count = int(len(floor_tiles) * B["branch_terrain_base_fraction"] * bdef.get("water_boost", 1.0))
    lava_count = int(len(floor_tiles) * B["branch_terrain_base_fraction"] * bdef.get("lava_boost", 1.0))
    idx = 0
    for _ in range(water_count):
        if idx < len(floor_tiles):
            x, y = floor_tiles[idx]
            if (x, y) != (gs.player.x, gs.player.y) and (x, y) != gs.stair_down:
                gs.tiles[y][x] = T_WATER
            idx += 1
    for _ in range(lava_count):
        if idx < len(floor_tiles):
            x, y = floor_tiles[idx]
            if (x, y) != (gs.player.x, gs.player.y) and (x, y) != gs.stair_down:
                gs.tiles[y][x] = T_LAVA
            idx += 1


def _populate_enemies(gs: GameState, floor_num: int) -> None:
    num = B["enemies_base"] + floor_num * B["enemies_per_floor"] + random.randint(0, B["enemies_random_bonus"])
    # Branch-specific enemy pool override
    if gs.active_branch:
        bdef = BRANCH_DEFS[gs.active_branch]
        eligible = [k for k in bdef["enemy_pool"] if k in ENEMY_TYPES and not ENEMY_TYPES[k].get("boss")]
        num += bdef.get("extra_enemies", 0)
    else:
        eligible = [k for k, v in ENEMY_TYPES.items()
                    if v["min_floor"] <= floor_num <= v.get("max_floor", 99) and not v.get("boss")]
    # Bosses: standard bosses spawn on their designated floors
    for etype, tmpl in ENEMY_TYPES.items():
        if tmpl.get("boss") and tmpl["min_floor"] == floor_num:
            if etype in ("crypt_guardian", "flame_tyrant", "elder_brain", "beast_lord"):
                continue
            pos = _find_spawn_pos(gs)
            if pos:
                gs.enemies.append(Enemy(pos[0], pos[1], etype))
                gs.msg("A powerful presence lurks on this floor...", C_RED)
    # Branch mini-boss
    if gs.active_branch:
        bdef = BRANCH_DEFS[gs.active_branch]
        if floor_num == bdef.get("mini_boss_floor"):
            mini_boss = bdef["mini_boss"]
            pos = _find_spawn_pos(gs)
            if pos:
                gs.enemies.append(Enemy(pos[0], pos[1], mini_boss))
                gs.msg(f"The {ENEMY_TYPES[mini_boss]['name']} guards this place!", C_RED)
    # Apex enemies: rare powerful enemies on deep floors
    apex_types = [k for k, v in ENEMY_TYPES.items()
                  if v.get("apex") and v["min_floor"] <= floor_num <= v.get("max_floor", 99)]
    if apex_types and random.random() < B["apex_spawn_chance"]:
        apex_type = random.choice(apex_types)
        pos = _find_spawn_pos(gs)
        if pos:
            apex = Enemy(pos[0], pos[1], apex_type)
            apex.alertness = "unwary"
            gs.enemies.append(apex)
            gs.msg("You sense something ancient and terrible on this floor...", C_RED)
    for _ in range(num):
        if not eligible:
            break
        etype = random.choice(eligible)
        pos = _find_spawn_pos(gs)
        if pos:
            e = Enemy(pos[0], pos[1], etype)
            floors_above_min = floor_num - ENEMY_TYPES[etype]["min_floor"]
            scale = 1.0 + floors_above_min * B["enemy_hp_scale_per_floor"]
            hp_mult = gs.difficulty_mods.get("enemy_hp_mult", 1.0)
            e.max_hp = int(e.max_hp * scale * hp_mult)
            e.hp = e.max_hp
            dmg_scale = 1.0 + floors_above_min * B["enemy_dmg_scale_per_floor"]
            dmg_mult = gs.difficulty_mods.get("enemy_dmg_mult", 1.0)
            e.dmg = (int(e.dmg[0] * dmg_scale * dmg_mult), max(int(e.dmg[1] * dmg_scale * dmg_mult), int(e.dmg[0] * dmg_scale * dmg_mult) + 1))
            e.defense = int(e.defense + floors_above_min * B["enemy_def_scale_per_floor"])
            e.alertness = "asleep" if random.random() < B["asleep_spawn_chance"] else "unwary"
            gs.enemies.append(e)


def _populate_items(gs: GameState, floor_num: int) -> None:
    num = B["items_base"] + floor_num * B["items_per_floor"] + random.randint(0, B["items_random_bonus"])
    for _ in range(num):
        pos = _find_spawn_pos(gs)
        if pos:
            item = _random_item(gs, pos[0], pos[1], floor_num)
            if item:
                gs.items.append(item)
    # Guarantee food items per floor so starvation isn't RNG-dependent
    for _ in range(random.randint(B["guaranteed_food_min"], B["guaranteed_food_max"])):
        pos = _find_spawn_pos(gs)
        if pos:
            f = random.choice(FOOD_TYPES)
            gs.items.append(Item(pos[0], pos[1], "food", f["name"], f))
    for _ in range(random.randint(B["gold_piles_min"], B["gold_piles_max"])):
        pos = _find_spawn_pos(gs)
        if pos:
            amt = random.randint(B["gold_per_floor_min"], B["gold_per_floor_max"]) * min(floor_num, 5)
            gs.items.append(Item(pos[0], pos[1], "gold", 0, {"amount": amt, "name": f"{amt} gold"}))


def _random_item(gs: GameState, x: int, y: int, floor_num: int) -> Item | None:
    weights = B["item_weights"]
    types = list(weights.keys())
    probs = list(weights.values())
    item_type = random.choices(types, weights=probs, k=1)[0]

    if item_type == "weapon":
        eligible = [w for w in WEAPON_TYPES if w["tier"] <= (floor_num // 3) + 1]
        if eligible:
            w = random.choice(eligible)
            return Item(x, y, "weapon", WEAPON_TYPES.index(w), w)
    elif item_type == "armor":
        eligible = [a for a in ARMOR_TYPES if a["tier"] <= (floor_num // 3) + 1]
        if eligible:
            a = random.choice(eligible)
            return Item(x, y, "armor", ARMOR_TYPES.index(a), a)
    elif item_type == "potion":
        eff = random.choice(POTION_EFFECTS)
        return Item(x, y, "potion", eff,
                    {"effect": eff, "color_name": gs.potion_ids[eff], "char": '!'})
    elif item_type == "scroll":
        eff = random.choice(SCROLL_EFFECTS)
        return Item(x, y, "scroll", eff,
                    {"effect": eff, "label": gs.scroll_ids[eff], "char": '?'})
    elif item_type == "food":
        f = random.choice(FOOD_TYPES)
        return Item(x, y, "food", f["name"], f)
    elif item_type == "ring":
        eligible = [r for r in RING_TYPES if r.get("min_floor", 0) <= floor_num]
        r = random.choice(eligible) if eligible else random.choice(RING_TYPES[:5])
        return Item(x, y, "ring", r["name"], r)
    elif item_type == "bow":
        eligible = [b for b in BOW_TYPES if b["tier"] <= (floor_num // 3) + 1]
        if eligible:
            b = random.choice(eligible)
            return Item(x, y, "bow", b["name"], b)
        it = Item(x, y, "arrow", "Arrow", dict(ARROW_ITEM))
        it.count = random.randint(B["arrow_count_min"], B["arrow_count_max"])
        return it
    elif item_type == "arrow":
        it = Item(x, y, "arrow", "Arrow", dict(ARROW_ITEM))
        it.count = random.randint(B["arrow_count_min"], B["arrow_count_max"])
        return it
    elif item_type == "throwing_dagger":
        it = Item(x, y, "throwing_dagger", "Throwing Dagger", dict(THROWING_DAGGER))
        it.count = random.randint(B["dagger_count_min"], B["dagger_count_max"])
        return it
    elif item_type == "wand":
        eligible = [w for w in WAND_TYPES if w["tier"] <= (floor_num // 3) + 2]
        if eligible:
            w = random.choice(eligible)
            data = dict(w)
            return Item(x, y, "wand", w["name"], data)
    elif item_type == "torch":
        t = random.choice(TORCH_TYPES)
        return Item(x, y, "torch", t["name"], dict(t))

    # Fallback
    f = random.choice(FOOD_TYPES)
    return Item(x, y, "food", f["name"], f)


def _place_shop(gs: GameState, floor_num: int) -> None:
    if floor_num % 2 == 0:
        return
    if len(gs.rooms) < 3:
        return
    room = gs.rooms[len(gs.rooms) // 2]
    rx, ry, rw, rh = room
    for yy in range(ry, ry + rh):
        for xx in range(rx, rx + rw):
            if 0 < xx < MAP_W - 1 and 0 < yy < MAP_H - 1:
                if gs.tiles[yy][xx] == T_FLOOR:
                    gs.tiles[yy][xx] = T_SHOP_FLOOR
    shop_items = []
    for _ in range(random.randint(B["shop_items_min"], B["shop_items_max"])):
        item = _random_item(gs, rx + 1, ry + 1, floor_num)
        if item:
            item.identified = True
            floor_mult = 1 + floor_num * B["shop_floor_price_scale"]
            price = int((item.data.get("tier", 1) + 1) * random.randint(B["shop_weapon_price_min"], B["shop_weapon_price_max"]) * floor_mult)
            if item.item_type in ("potion", "scroll"):
                price = int(random.randint(B["shop_potion_price_min"], B["shop_potion_price_max"]) * floor_mult)
            elif item.item_type == "food":
                price = int(random.randint(B["shop_food_price_min"], B["shop_food_price_max"]) * floor_mult)
            elif item.item_type == "ring":
                price = int(random.randint(B["shop_ring_price_min"], B["shop_ring_price_max"]) * floor_mult)
            shop_items.append(ShopItem(item, price))
    # Always stock healing and food
    heal = Item(0, 0, "potion", "Healing",
                {"effect": "Healing", "color_name": gs.potion_ids["Healing"], "char": '!'})
    heal.identified = True
    shop_items.append(ShopItem(heal, B["shop_heal_base_price"] + floor_num * B["shop_heal_floor_scale"]))
    food = random.choice(FOOD_TYPES)
    fi = Item(0, 0, "food", food["name"], food)
    fi.identified = True
    shop_items.append(ShopItem(fi, B["shop_food_price"]))
    gs.shops.append((room, shop_items))


def _place_shrine(gs: GameState, floor_num: int) -> None:
    if floor_num % 4 != 2:
        return
    if len(gs.rooms) < 2:
        return
    room = gs.rooms[random.randint(1, len(gs.rooms) - 1)]
    cx = room[0] + room[2] // 2
    cy = room[1] + room[3] // 2
    if 0 < cx < MAP_W - 1 and 0 < cy < MAP_H - 1:
        gs.tiles[cy][cx] = T_SHRINE


def _place_alchemy_table(gs: GameState, floor_num: int) -> None:
    if floor_num not in (2, 5, 8, 11, 14):
        return
    if len(gs.rooms) < 2:
        return
    room = gs.rooms[random.randint(1, len(gs.rooms) - 1)]
    cx = room[0] + room[2] // 2
    cy = room[1] + room[3] // 2 + 1
    if 0 < cx < MAP_W - 1 and 0 < cy < MAP_H - 1:
        if gs.tiles[cy][cx] == T_FLOOR:
            gs.tiles[cy][cx] = T_ALCHEMY_TABLE


def _place_wall_torches(gs: GameState, floor_num: int) -> None:
    if not gs.rooms:
        return
    for room in gs.rooms:
        if random.random() > B["wall_torch_room_chance"]:
            continue
        rx, ry, rw, rh = room
        if floor_num >= 10 and random.random() < 0.5:
            continue
        num_torches = random.randint(2, 4)
        placed = 0
        for _ in range(num_torches * 4):
            if placed >= num_torches:
                break
            side = random.randint(0, 3)
            if side == 0:
                tx = random.randint(rx, rx + rw - 1)
                ty = ry - 1
            elif side == 1:
                tx = random.randint(rx, rx + rw - 1)
                ty = ry + rh
            elif side == 2:
                tx = rx - 1
                ty = random.randint(ry, ry + rh - 1)
            else:
                tx = rx + rw
                ty = random.randint(ry, ry + rh - 1)
            if 0 < tx < MAP_W - 1 and 0 < ty < MAP_H - 1:
                if gs.tiles[ty][tx] == T_WALL:
                    gs.tiles[ty][tx] = T_WALL_TORCH
                    gs.wall_torches.append((tx, ty))
                    placed += 1


def _place_puzzle(gs: GameState, floor_num: int) -> None:
    if floor_num < 4 or random.random() > B["puzzle_floor_chance"]:
        return
    if len(gs.rooms) < 4:
        return
    start_room = gs.rooms[0]
    shop_rooms = [r for r, _ in gs.shops] if gs.shops else []
    candidates = [r for r in gs.rooms[1:] if r not in shop_rooms]
    if not candidates:
        return
    room = random.choice(candidates)
    rx, ry, rw, rh = room
    puzzle_type = random.choice(["torch", "switch", "locked_stairs", "sequence", "pressure"])

    if puzzle_type == "torch":
        count = random.randint(3, 4)
        positions = []
        for _ in range(count):
            px = random.randint(rx, rx + rw - 1)
            py = random.randint(ry, ry + rh - 1)
            if 0 < px < MAP_W - 1 and 0 < py < MAP_H - 1 and gs.tiles[py][px] == T_FLOOR:
                gs.tiles[py][px] = T_PEDESTAL_UNLIT
                positions.append((px, py))
        if positions:
            gs.puzzles.append({"type": "torch", "positions": positions, "solved": False, "room": room})

    elif puzzle_type == "switch":
        count = 3
        positions = []
        for _ in range(count):
            px = random.randint(rx, rx + rw - 1)
            py = random.randint(ry, ry + rh - 1)
            if 0 < px < MAP_W - 1 and 0 < py < MAP_H - 1 and gs.tiles[py][px] == T_FLOOR:
                gs.tiles[py][px] = T_SWITCH_OFF
                positions.append((px, py))
        if positions:
            gs.puzzles.append({"type": "switch", "positions": positions, "solved": False, "room": room})

    elif puzzle_type == "locked_stairs":
        sx, sy = gs.stair_down
        if gs.tiles[sy][sx] == T_STAIRS_DOWN:
            gs.tiles[sy][sx] = T_STAIRS_LOCKED
            positions = []
            for _ in range(2):
                px = random.randint(rx, rx + rw - 1)
                py = random.randint(ry, ry + rh - 1)
                if 0 < px < MAP_W - 1 and 0 < py < MAP_H - 1 and gs.tiles[py][px] == T_FLOOR:
                    gs.tiles[py][px] = T_SWITCH_OFF
                    positions.append((px, py))
            if positions:
                gs.puzzles.append({"type": "locked_stairs", "positions": positions,
                                   "solved": False, "room": room, "stairs": (sx, sy)})

    elif puzzle_type == "sequence":
        count = random.randint(3, 5)
        positions = []
        for _ in range(count):
            px = random.randint(rx, rx + rw - 1)
            py = random.randint(ry, ry + rh - 1)
            if 0 < px < MAP_W - 1 and 0 < py < MAP_H - 1 and gs.tiles[py][px] == T_FLOOR:
                gs.tiles[py][px] = T_PEDESTAL_UNLIT
                positions.append((px, py))
        if len(positions) >= 3:
            correct_order = list(range(len(positions)))
            random.shuffle(correct_order)
            gs.puzzles.append({
                "type": "sequence", "positions": positions,
                "correct_order": correct_order, "current_step": 0,
                "solved": False, "room": room
            })

    elif puzzle_type == "pressure":
        count = random.randint(3, 4)
        positions = []
        for _ in range(count):
            px = random.randint(rx, rx + rw - 1)
            py = random.randint(ry, ry + rh - 1)
            if 0 < px < MAP_W - 1 and 0 < py < MAP_H - 1 and gs.tiles[py][px] == T_FLOOR:
                gs.tiles[py][px] = T_SWITCH_OFF
                positions.append((px, py))
        if positions:
            gs.puzzles.append({
                "type": "pressure", "positions": positions,
                "activated": [], "timer": 0, "timer_max": 15,
                "solved": False, "room": room
            })


def _place_traps(gs: GameState, floor_num: int) -> None:
    count = B["trap_base_count"] + int(floor_num * B["trap_per_floor"])
    eligible_traps = [k for k, v in TRAP_TYPES.items() if v["min_floor"] <= floor_num]
    if not eligible_traps:
        return
    start_room = gs.rooms[0] if gs.rooms else None
    for _ in range(count):
        for attempt in range(50):
            x = random.randint(1, MAP_W - 2)
            y = random.randint(1, MAP_H - 2)
            if gs.tiles[y][x] != T_FLOOR:
                continue
            if start_room:
                sx, sy, sw, sh = start_room
                if sx <= x < sx + sw and sy <= y < sy + sh:
                    continue
            if any(t["x"] == x and t["y"] == y for t in gs.traps):
                continue
            if abs(x - gs.player.x) + abs(y - gs.player.y) <= 3:
                continue
            trap_type = random.choice(eligible_traps)
            gs.traps.append({
                "x": x, "y": y, "type": trap_type,
                "visible": False, "triggered": False, "disarmed": False
            })
            break


def _place_vignettes(gs: GameState, floor_num: int) -> None:
    if not gs.rooms or len(gs.rooms) < 3:
        return
    # More vignettes on deeper floors (1-2 early, 2-3 deep)
    count = random.randint(1, 2) if floor_num < 10 else random.randint(2, 3)
    used_rooms: set[tuple[int, int, int, int]] = set()
    start_room = gs.rooms[0]
    shop_rooms = {r for r, _ in gs.shops} if gs.shops else set()
    # Filter vignettes appropriate for this floor depth
    eligible = [v for v in VIGNETTE_TEMPLATES
                if v.get("min_floor", 1) <= floor_num <= v.get("max_floor", 20)]
    if not eligible:
        eligible = VIGNETTE_TEMPLATES  # fallback
    for _ in range(count):
        candidates = [r for r in gs.rooms[1:]
                      if r not in used_rooms and r != start_room and r not in shop_rooms]
        if not candidates:
            break
        room = random.choice(candidates)
        used_rooms.add(room)
        rx, ry, rw, rh = room
        vx = rx + rw // 2
        vy = ry + rh // 2
        if 0 < vx < MAP_W - 1 and 0 < vy < MAP_H - 1 and gs.tiles[vy][vx] == T_FLOOR:
            template = random.choice(eligible)
            vignette = {
                "x": vx, "y": vy,
                "name": template["name"],
                "lore": template["lore"],
                "examined": False,
                "loot_spawned": False,
                "loot_chance": template["loot_chance"],
                "loot_tier": template["loot_tier"],
            }
            gs.vignettes.append(vignette)


def _place_npcs(gs: GameState, floor_num: int) -> None:
    if floor_num < 2 or random.random() > B["npc_spawn_chance"]:
        return
    if not gs.rooms or len(gs.rooms) < 3:
        return
    eligible = [k for k, v in NPC_TYPES.items()
                if v["min_floor"] <= floor_num <= v["max_floor"]]
    if not eligible:
        return
    npc_type = random.choice(eligible)
    npc_def = NPC_TYPES[npc_type]
    start_room = gs.rooms[0]
    shop_rooms = {r for r, _ in gs.shops} if gs.shops else set()
    candidates = [r for r in gs.rooms[1:]
                  if r != start_room and r not in shop_rooms]
    if not candidates:
        return
    room = random.choice(candidates)
    rx, ry, rw, rh = room
    nx = rx + rw // 2
    ny = ry + rh // 2
    if 0 < nx < MAP_W - 1 and 0 < ny < MAP_H - 1 and gs.tiles[ny][nx] == T_FLOOR:
        gs.npcs.append({
            "x": nx, "y": ny,
            "type": npc_type,
            "name": npc_def["name"],
            "char": npc_def["char"],
            "color": npc_def["color"],
            "dialogue": npc_def["dialogue"],
            "interaction": npc_def["interaction"],
            "interacted": False,
        })


def _place_enchant_anvil(gs: GameState, floor_num: int) -> None:
    if floor_num < B["enchant_anvil_min_floor"]:
        return
    if random.random() > B["enchant_anvil_chance"]:
        return
    if not gs.rooms or len(gs.rooms) < 3:
        return
    start_room = gs.rooms[0]
    shop_rooms = {r for r, _ in gs.shops} if gs.shops else set()
    candidates = [r for r in gs.rooms[1:] if r != start_room and r not in shop_rooms]
    if not candidates:
        return
    room = random.choice(candidates)
    rx, ry, rw, rh = room
    ax = rx + rw // 2
    ay = ry + rh // 2
    if 0 < ax < MAP_W - 1 and 0 < ay < MAP_H - 1 and gs.tiles[ay][ax] == T_FLOOR:
        gs.tiles[ay][ax] = T_ENCHANT_ANVIL


def _place_fountain(gs: GameState, floor_num: int) -> None:
    if random.random() > B["fountain_spawn_chance"]:
        return
    if not gs.rooms or len(gs.rooms) < 2:
        return
    start_room = gs.rooms[0]
    candidates = [r for r in gs.rooms[1:] if r != start_room]
    if not candidates:
        return
    room = random.choice(candidates)
    rx, ry, rw, rh = room
    fx = rx + rw // 2
    fy = ry + rh // 2
    if 0 < fx < MAP_W - 1 and 0 < fy < MAP_H - 1 and gs.tiles[fy][fx] == T_FLOOR:
        gs.tiles[fy][fx] = T_FOUNTAIN


def _place_secret_room(gs: GameState, floor_num: int) -> None:
    if floor_num < B["secret_room_min_floor"]:
        return
    if random.random() > B["secret_room_chance"]:
        return
    if not gs.rooms or len(gs.rooms) < 3:
        return
    room = random.choice(gs.rooms[1:])
    rx, ry, rw, rh = room
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    random.shuffle(directions)
    for dx, dy in directions:
        if dx == -1:
            sx, sy = rx - 4, ry + rh // 2 - 1
            wall_x, wall_y = rx - 1, ry + rh // 2
        elif dx == 1:
            sx, sy = rx + rw + 1, ry + rh // 2 - 1
            wall_x, wall_y = rx + rw, ry + rh // 2
        elif dy == -1:
            sx, sy = rx + rw // 2 - 1, ry - 4
            wall_x, wall_y = rx + rw // 2, ry - 1
        else:
            sx, sy = rx + rw // 2 - 1, ry + rh
            wall_x, wall_y = rx + rw // 2, ry + rh
        if sx < 1 or sy < 1 or sx + 3 >= MAP_W - 1 or sy + 3 >= MAP_H - 1:
            continue
        if wall_x < 1 or wall_y < 1 or wall_x >= MAP_W - 1 or wall_y >= MAP_H - 1:
            continue
        can_place = True
        for yy in range(sy, sy + 3):
            for xx in range(sx, sx + 3):
                if gs.tiles[yy][xx] != T_WALL:
                    can_place = False
                    break
            if not can_place:
                break
        if not can_place:
            continue
        if gs.tiles[wall_y][wall_x] != T_WALL:
            continue
        for yy in range(sy, sy + 3):
            for xx in range(sx, sx + 3):
                gs.tiles[yy][xx] = T_FLOOR
        gs.tiles[wall_y][wall_x] = T_SECRET_WALL
        cx, cy = sx + 1, sy + 1
        tier = min(floor_num // 3, len(WEAPON_TYPES) - 1)
        loot_roll = random.random()
        if loot_roll < B["secret_room_weapon_chance"]:
            wt = WEAPON_TYPES[min(tier + 1, len(WEAPON_TYPES) - 1)]
            item = Item(cx, cy, "weapon", wt["name"], dict(wt))
            item.identified = True
            gs.items.append(item)
        elif loot_roll < B["secret_room_weapon_chance"] + B["secret_room_gold_chance"]:
            amt = random.randint(B["secret_room_gold_min"], B["secret_room_gold_max"]) * max(1, floor_num // 3)
            gs.items.append(Item(cx, cy, "gold", 0, {"amount": amt, "name": f"{amt} gold"}))
        else:
            at = ARMOR_TYPES[min(tier + 1, len(ARMOR_TYPES) - 1)]
            item = Item(cx, cy, "armor", at["name"], dict(at))
            item.identified = True
            gs.items.append(item)
        break


def _place_single_trap(gs: GameState, floor_num: int) -> None:
    eligible_traps = [k for k, v in TRAP_TYPES.items() if v["min_floor"] <= floor_num]
    if not eligible_traps:
        return
    for _ in range(50):
        x = random.randint(1, MAP_W - 2)
        y = random.randint(1, MAP_H - 2)
        if gs.tiles[y][x] != T_FLOOR:
            continue
        if any(t["x"] == x and t["y"] == y for t in gs.traps):
            continue
        if abs(x - gs.player.x) + abs(y - gs.player.y) <= 3:
            continue
        trap_type = random.choice(eligible_traps)
        gs.traps.append({
            "x": x, "y": y, "type": trap_type,
            "visible": False, "triggered": False, "disarmed": False
        })
        break


def _find_spawn_pos(gs: GameState) -> tuple[int, int] | None:
    for _ in range(100):
        x = random.randint(1, MAP_W - 2)
        y = random.randint(1, MAP_H - 2)
        if gs.tiles[y][x] in (T_FLOOR, T_CORRIDOR):
            if abs(x - gs.player.x) + abs(y - gs.player.y) > 5:
                if not any(e.x == x and e.y == y for e in gs.enemies):
                    return (x, y)
    return None


# Import ShopItem here to avoid circular import at module level
from .entities import ShopItem
