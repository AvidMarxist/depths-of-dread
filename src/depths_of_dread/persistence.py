"""
Persistence layer for Depths of Dread.
Handles lifetime stats, save/load, session recording, and session replay.
"""

from __future__ import annotations

import curses
import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .constants import *
from .entities import Enemy, Item

if TYPE_CHECKING:
    from .game import GameState


# ============================================================
# PERSISTENT LIFETIME STATS
# ============================================================

def _default_lifetime_stats() -> dict[str, Any]:
    """Return a fresh lifetime stats dictionary."""
    return {
        "total_games": 0,
        "total_wins": 0,
        "total_deaths": 0,
        "highest_floor": 0,
        "highest_level": 0,
        "longest_run_turns": 0,
        "total_turns": 0,
        "total_kills": 0,
        "most_kills_single_run": 0,
        # Meta-progression unlocks (Phase 3)
        "unlocks": [],
    }


def check_meta_unlocks(stats: dict[str, Any]) -> list[str]:
    """Check which meta-progression unlocks the player has earned."""
    unlocks = list(stats.get("unlocks", []))
    for key, unlock in META_UNLOCKS.items():
        if key in unlocks:
            continue
        req = unlock["req"]
        # Parse simple requirement: "stat_name >= value"
        parts = req.split()
        if len(parts) == 3:
            stat_name, op, value = parts[0], parts[1], int(parts[2])
            stat_val = stats.get(stat_name, 0)
            if op == ">=" and stat_val >= value:
                unlocks.append(key)
    return unlocks


def apply_meta_unlocks(gs: GameState) -> None:
    """Apply meta-progression bonuses at game start."""
    import random as _random
    stats = load_lifetime_stats()
    unlocks = stats.get("unlocks", [])
    p = gs.player
    for key in unlocks:
        if key == "extra_potion":
            # Give random potion
            item = gs._random_item(p.x, p.y, 1)
            if item and item.item_type == "potion":
                p.inventory.append(item)
        elif key == "bonus_gold":
            p.gold += 50
        elif key == "extra_hp":
            p.max_hp += 10
            p.hp += 10
        elif key == "torch_bonus":
            p.torch_fuel = min(TORCH_MAX_FUEL, p.torch_fuel + 100)
        elif key == "mana_bonus":
            p.max_mana += 5
            p.mana += 5
        elif key == "map_reveal":
            # Reveal 30% of explored tiles
            for y in range(MAP_H):
                for x in range(MAP_W):
                    if _random.random() < 0.30:
                        gs.explored[y][x] = True
        elif key == "starting_weapon":
            weapons_t2 = [w for w in WEAPON_TYPES if w.get("tier", 1) == 2]
            if weapons_t2:
                w = _random.choice(weapons_t2)
                item = Item(p.x, p.y, "weapon", w["name"], w)
                item.identified = True
                p.inventory.append(item)


def load_lifetime_stats() -> dict[str, Any]:
    """Load lifetime stats from disk. Returns defaults if missing/corrupt."""
    try:
        with open(STATS_FILE_PATH) as f:
            data = json.load(f)
        # Validate it's a dict with expected keys; fill missing keys with defaults
        if not isinstance(data, dict):
            return _default_lifetime_stats()
        defaults = _default_lifetime_stats()
        for key in defaults:
            if key not in data:
                data[key] = defaults[key]
            elif key == "unlocks":
                if not isinstance(data[key], list):
                    data[key] = defaults[key]
            elif not isinstance(data[key], (int, float)):
                data[key] = defaults[key]
        return data
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return _default_lifetime_stats()


def save_lifetime_stats(stats: dict[str, Any]) -> None:
    """Save lifetime stats to disk."""
    try:
        with open(STATS_FILE_PATH, 'w') as f:
            json.dump(stats, f, indent=2)
    except OSError:
        pass  # Silently fail if we can't write


def update_lifetime_stats(gs: GameState) -> dict[str, Any]:
    """Update lifetime stats at end of a game (death or victory). Returns updated stats."""
    stats = load_lifetime_stats()
    p = gs.player
    # Increment game count (was already incremented at game start)
    if gs.victory:
        stats["total_wins"] += 1
    else:
        stats["total_deaths"] += 1
    stats["highest_floor"] = max(stats["highest_floor"], p.deepest_floor)
    stats["highest_level"] = max(stats["highest_level"], p.level)
    stats["longest_run_turns"] = max(stats["longest_run_turns"], gs.turn_count)
    stats["total_turns"] += gs.turn_count
    stats["total_kills"] += p.kills
    stats["most_kills_single_run"] = max(stats["most_kills_single_run"], p.kills)
    # Check meta-progression unlocks
    new_unlocks = check_meta_unlocks(stats)
    old_unlocks = stats.get("unlocks", [])
    if not isinstance(old_unlocks, list):
        old_unlocks = []
    for u in new_unlocks:
        if u not in old_unlocks:
            old_unlocks.append(u)
            if not gs._headless:
                gs.msg(f"META UNLOCK: {META_UNLOCKS[u]['name']} — {META_UNLOCKS[u]['desc']}!", C_GOLD)
    stats["unlocks"] = old_unlocks
    save_lifetime_stats(stats)
    return stats


def show_lifetime_stats(scr: Any) -> None:
    """Display lifetime stats overlay."""
    from .ui import safe_addstr
    stats = load_lifetime_stats()
    scr.erase()
    h, w = scr.getmaxyx()
    title = "LIFETIME STATS"
    safe_addstr(scr, 1, max(0, (w - len(title)) // 2), title,
               curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 2, max(0, (w - 30) // 2), "=" * 30, curses.color_pair(C_DARK))

    win_rate = f"{stats['total_wins']/stats['total_games']*100:.0f}%" if stats['total_games'] > 0 else "N/A"
    lines = [
        (f"  Games Played:          {stats['total_games']}", C_WHITE),
        (f"  Wins:                  {stats['total_wins']}", C_GREEN),
        (f"  Deaths:                {stats['total_deaths']}", C_RED),
        (f"  Win Rate:              {win_rate}", C_YELLOW),
        ("", C_WHITE),
        (f"  Highest Floor:         {stats['highest_floor']}", C_CYAN),
        (f"  Highest Level:         {stats['highest_level']}", C_CYAN),
        (f"  Longest Run (turns):   {stats['longest_run_turns']}", C_CYAN),
        ("", C_WHITE),
        (f"  Total Turns Played:    {stats['total_turns']}", C_GOLD),
        (f"  Total Enemies Killed:  {stats['total_kills']}", C_GOLD),
        (f"  Most Kills (one run):  {stats['most_kills_single_run']}", C_GOLD),
    ]

    sy = 4
    for i, (text, color) in enumerate(lines):
        if sy + i >= h - 2:
            break
        cx = max(0, (w - len(text)) // 2)
        safe_addstr(scr, sy + i, cx, text, curses.color_pair(color))

    pr = "[ Press any key ]"
    safe_addstr(scr, min(h - 1, sy + len(lines) + 1), max(0, (w - len(pr)) // 2),
               pr, curses.color_pair(C_DARK))
    scr.refresh()
    scr.getch()


def _format_lifetime_stats_lines(stats: dict[str, Any]) -> list[tuple[str, int]]:
    """Format lifetime stats as lines for embedding in death/victory screens."""
    win_rate = f"{stats['total_wins']/stats['total_games']*100:.0f}%" if stats['total_games'] > 0 else "N/A"
    return [
        ("", C_WHITE),
        ("  --- Lifetime Stats ---", C_UI),
        (f"  Games: {stats['total_games']}  Wins: {stats['total_wins']}  Deaths: {stats['total_deaths']}  ({win_rate})", C_DARK),
        (f"  Best Floor: {stats['highest_floor']}  Best Lv: {stats['highest_level']}  Best Kills: {stats['most_kills_single_run']}", C_DARK),
        (f"  Total Kills: {stats['total_kills']}  Total Turns: {stats['total_turns']}", C_DARK),
    ]


# ============================================================
# SAVE/LOAD SYSTEM (Phase 7, item 33)
# ============================================================

def _compute_checksum(data_str: str) -> str:
    """Compute SHA256 checksum for save data integrity."""
    return hashlib.sha256(data_str.encode('utf-8')).hexdigest()


def save_game(gs: GameState) -> bool:
    """Save game state to JSON file."""
    p = gs.player
    save_data = {
        "version": 5,
        "player": {
            "x": p.x, "y": p.y, "hp": p.hp, "max_hp": p.max_hp,
            "mana": p.mana, "max_mana": p.max_mana,
            "strength": p.strength, "defense": p.defense,
            "level": p.level, "xp": p.xp, "xp_next": p.xp_next,
            "floor": p.floor, "gold": p.gold, "turns": p.turns,
            "kills": p.kills, "hunger": p.hunger,
            "torch_fuel": p.torch_fuel,
            "torch_lit": p.torch_lit,
            "deepest_floor": p.deepest_floor,
            "potions_drunk": p.potions_drunk, "scrolls_read": p.scrolls_read,
            "items_found": p.items_found, "damage_dealt": p.damage_dealt,
            "damage_taken": p.damage_taken, "foods_eaten": p.foods_eaten,
            "bosses_killed": p.bosses_killed, "spells_cast": p.spells_cast,
            "projectiles_fired": p.projectiles_fired,
            "gold_earned": p.gold_earned, "gold_spent": p.gold_spent,
            "torches_grabbed": p.torches_grabbed,
            "traps_triggered": p.traps_triggered, "traps_found": p.traps_found,
            "traps_disarmed": p.traps_disarmed,
            "fountains_used": getattr(p, 'fountains_used', 0),
            "secrets_found": getattr(p, 'secrets_found', 0),
            "kills_by_type": getattr(p, 'kills_by_type', {}),
            "items_by_type": getattr(p, 'items_by_type', {}),
            "player_class": p.player_class,
            "pending_levelups": p.pending_levelups,
            "ability_cooldown": p.ability_cooldown,
            "evasion_bonus": getattr(p, '_evasion_bonus', 0),
            "known_spells": sorted(p.known_spells),
            "known_abilities": sorted(p.known_abilities),
            "bleed_stacks": p.bleed_stacks,
            "bleed_turns": p.bleed_turns,
            "status_effects": dict(p.status_effects),
            "inventory": [_serialize_item(it) for it in p.inventory],
            "weapon_idx": p.inventory.index(p.weapon) if p.weapon and p.weapon in p.inventory else -1,
            "armor_idx": p.inventory.index(p.armor) if p.armor and p.armor in p.inventory else -1,
            "ring_idx": p.inventory.index(p.ring) if p.ring and p.ring in p.inventory else -1,
            "bow_idx": p.inventory.index(p.bow) if p.bow and p.bow in p.inventory else -1,
        },
        "turn_count": gs.turn_count,
        "tiles": [[gs.tiles[y][x] for x in range(MAP_W)] for y in range(MAP_H)],
        "explored": [[gs.explored[y][x] for x in range(MAP_W)] for y in range(MAP_H)],
        "stair_down": list(gs.stair_down),
        "enemies": [_serialize_enemy(e) for e in gs.enemies if e.is_alive()],
        "items": [_serialize_item_on_ground(it) for it in gs.items],
        "potion_ids": gs.potion_ids,
        "scroll_ids": gs.scroll_ids,
        "id_potions": list(gs.id_potions),
        "id_scrolls": list(gs.id_scrolls),
        "tips_shown": list(gs.tips_shown),
        "first_melee_done": gs.first_melee_done,
        "floors_explored": list(gs.floors_explored),
        "death_cause": gs.death_cause,
        "shop_discovered": gs.shop_discovered,
        "journal": gs.journal,
        "alchemy_used": [list(p) for p in gs.alchemy_used],
        "wall_torches": gs.wall_torches,
        "puzzles": gs.puzzles,
        "traps": gs.traps,
        "branch_choices": gs.branch_choices,
        "active_branch": gs.active_branch,
        "bestiary": gs.bestiary,
        "vignettes": gs.vignettes,
        "npcs": gs.npcs,
        "shops": [
            {
                "room": list(room),
                "items": [
                    {"item": _serialize_item(si.item), "price": si.price, "sold": si.sold}
                    for si in shop_items
                ],
            }
            for room, shop_items in gs.shops
        ],
    }
    data_str = json.dumps(save_data, separators=(',', ':'))
    checksum = _compute_checksum(data_str)
    wrapper = {"checksum": checksum, "data": save_data}
    try:
        with open(SAVE_FILE_PATH, 'w') as f:
            json.dump(wrapper, f)
        return True
    except (OSError, ValueError, TypeError):
        return False


def load_game() -> GameState | None:
    """Load game state from JSON file. Returns GameState or None."""
    from .entities import ShopItem
    from .game import GameState
    try:
        with open(SAVE_FILE_PATH) as f:
            wrapper = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    # Verify checksum
    stored_checksum = wrapper.get("checksum", "")
    data = wrapper.get("data", {})
    data_str = json.dumps(data, separators=(',', ':'))
    computed = _compute_checksum(data_str)
    if stored_checksum != computed:
        return None  # tampered or corrupted

    try:
        gs = GameState(headless=True)
        pd = data["player"]
        p = gs.player
        p.x, p.y = pd["x"], pd["y"]
        p.hp, p.max_hp = pd["hp"], pd["max_hp"]
        p.mana, p.max_mana = pd["mana"], pd["max_mana"]
        p.strength, p.defense = pd["strength"], pd["defense"]
        p.level, p.xp, p.xp_next = pd["level"], pd["xp"], pd["xp_next"]
        p.floor, p.gold = pd["floor"], pd["gold"]
        p.turns = pd.get("turns", 0)
        p.kills = pd["kills"]
        p.hunger = pd["hunger"]
        p.torch_fuel = pd["torch_fuel"]
        p.torch_lit = pd.get("torch_lit", True)
        p.deepest_floor = pd["deepest_floor"]
        p.potions_drunk = pd["potions_drunk"]
        p.scrolls_read = pd["scrolls_read"]
        p.items_found = pd["items_found"]
        p.damage_dealt = pd["damage_dealt"]
        p.damage_taken = pd["damage_taken"]
        p.foods_eaten = pd["foods_eaten"]
        p.bosses_killed = pd["bosses_killed"]
        p.spells_cast = pd["spells_cast"]
        p.projectiles_fired = pd["projectiles_fired"]
        # v2 fields (class system) — v1 saves get defaults
        p.player_class = pd.get("player_class", None)
        p.pending_levelups = pd.get("pending_levelups", [])
        p.ability_cooldown = pd.get("ability_cooldown", 0)
        p._evasion_bonus = pd.get("evasion_bonus", 0)
        # Migrate known_spells: old saves default to all base spells
        if "known_spells" in pd:
            p.known_spells = set(pd["known_spells"])
        else:
            p.known_spells = set(BASE_SPELLS)
        p.known_abilities = set(pd.get("known_abilities", []))
        p.bleed_stacks = pd.get("bleed_stacks", 0)
        p.bleed_turns = pd.get("bleed_turns", 0)
        # Telemetry counters (v3 — older saves get 0)
        p.gold_earned = pd.get("gold_earned", 0)
        p.gold_spent = pd.get("gold_spent", 0)
        p.torches_grabbed = pd.get("torches_grabbed", 0)
        p.traps_triggered = pd.get("traps_triggered", 0)
        p.traps_found = pd.get("traps_found", 0)
        p.traps_disarmed = pd.get("traps_disarmed", 0)
        p.fountains_used = pd.get("fountains_used", 0)
        p.secrets_found = pd.get("secrets_found", 0)
        p.kills_by_type = pd.get("kills_by_type", {})
        p.items_by_type = pd.get("items_by_type", {})
        p.status_effects = pd.get("status_effects", {})
        # Restore inventory
        p.inventory = [_deserialize_item(d) for d in pd.get("inventory", [])]
        if pd.get("weapon_idx", -1) >= 0 and pd["weapon_idx"] < len(p.inventory):
            p.weapon = p.inventory[pd["weapon_idx"]]
        if pd.get("armor_idx", -1) >= 0 and pd["armor_idx"] < len(p.inventory):
            p.armor = p.inventory[pd["armor_idx"]]
        if pd.get("ring_idx", -1) >= 0 and pd["ring_idx"] < len(p.inventory):
            p.ring = p.inventory[pd["ring_idx"]]
        if pd.get("bow_idx", -1) >= 0 and pd["bow_idx"] < len(p.inventory):
            p.bow = p.inventory[pd["bow_idx"]]

        gs.turn_count = data["turn_count"]
        gs.tiles = data["tiles"]
        gs.explored = data["explored"]
        gs.stair_down = tuple(data["stair_down"])
        gs.enemies = [_deserialize_enemy(d) for d in data.get("enemies", [])]
        gs.items = [_deserialize_item_ground(d) for d in data.get("items", [])]
        gs.potion_ids = data.get("potion_ids", gs.potion_ids)
        gs.scroll_ids = data.get("scroll_ids", gs.scroll_ids)
        gs.id_potions = set(data.get("id_potions", []))
        gs.id_scrolls = set(data.get("id_scrolls", []))
        gs.tips_shown = set(data.get("tips_shown", []))
        gs.first_melee_done = data.get("first_melee_done", False)
        gs.floors_explored = set(data.get("floors_explored", []))
        gs.death_cause = data.get("death_cause")
        gs.shop_discovered = data.get("shop_discovered", False)
        gs.journal = data.get("journal", {})
        gs.alchemy_used = set(tuple(p) for p in data.get("alchemy_used", []))
        gs.wall_torches = data.get("wall_torches", [])
        gs.puzzles = data.get("puzzles", [])
        gs.traps = data.get("traps", [])
        gs.branch_choices = {int(k): v for k, v in data.get("branch_choices", {}).items()}
        gs.active_branch = data.get("active_branch", None)
        gs.bestiary = data.get("bestiary", {})
        gs.vignettes = data.get("vignettes", [])
        gs.npcs = data.get("npcs", [])
        gs.rooms = []  # rooms not needed after generation
        # Restore shops
        gs.shops = []
        for shop_data in data.get("shops", []):
            room = tuple(shop_data["room"])
            shop_items = []
            for si_data in shop_data["items"]:
                item = _deserialize_item(si_data["item"])
                si = ShopItem(item, si_data["price"])
                si.sold = si_data.get("sold", False)
                shop_items.append(si)
            gs.shops.append((room, shop_items))
        return gs
    except (KeyError, TypeError, IndexError):
        return None


def delete_save() -> None:
    """Delete save file (on death — permadeath)."""
    try:
        os.remove(SAVE_FILE_PATH)
    except FileNotFoundError:
        pass


def save_exists() -> bool:
    """Check if a save file exists."""
    return os.path.exists(SAVE_FILE_PATH)


def _serialize_item(item: Item) -> dict[str, Any]:
    return {
        "x": item.x, "y": item.y, "item_type": item.item_type,
        "subtype": item.subtype if not isinstance(item.subtype, int) else item.subtype,
        "data": item.data, "identified": item.identified,
        "equipped": item.equipped, "count": item.count,
    }


def _serialize_item_on_ground(item: Item) -> dict[str, Any]:
    return _serialize_item(item)


def _serialize_enemy(e: Enemy) -> dict[str, Any]:
    d = {
        "x": e.x, "y": e.y, "etype": e.etype,
        "hp": e.hp, "max_hp": e.max_hp, "alerted": e.alerted,
        "alertness": e.alertness,
        "energy": e.energy, "frozen_turns": e.frozen_turns,
        "summon_cooldown": e.summon_cooldown,
        "patrol_dir": list(e.patrol_dir),
    }
    # D&D expansion fields (only save non-default)
    if e.disguised:
        d["disguised"] = True
    if e.phase_cooldown:
        d["phase_cooldown"] = e.phase_cooldown
    if e.poisoned_turns > 0:
        d["poisoned_turns"] = e.poisoned_turns
    if e.fleeing:
        d["fleeing"] = True
    if e.regen_suppressed > 0:
        d["regen_suppressed"] = e.regen_suppressed
    # Expansion phase fields
    if e.boss_phase > 1:
        d["boss_phase"] = e.boss_phase
    if e.boss_phase_turn > 0:
        d["boss_phase_turn"] = e.boss_phase_turn
    if e.bleed_stacks > 0:
        d["bleed_stacks"] = e.bleed_stacks
    if e.bleed_turns > 0:
        d["bleed_turns"] = e.bleed_turns
    if e.silenced_turns > 0:
        d["silenced_turns"] = e.silenced_turns
    # Apex enemy fields
    if e.breath_cooldown > 0:
        d["breath_cooldown"] = e.breath_cooldown
    return d


def _deserialize_item(d: dict[str, Any]) -> Item:
    item = Item(d["x"], d["y"], d["item_type"], d["subtype"], d["data"])
    item.identified = d.get("identified", False)
    item.equipped = d.get("equipped", False)
    item.count = d.get("count", 1)
    return item


def _deserialize_item_ground(d: dict[str, Any]) -> Item:
    return _deserialize_item(d)


def _deserialize_enemy(d: dict[str, Any]) -> Enemy:
    e = Enemy(d["x"], d["y"], d["etype"])
    e.hp = d["hp"]
    e.max_hp = d["max_hp"]
    e.alerted = d.get("alerted", False)
    e.alertness = d.get("alertness", "alert" if e.alerted else "unwary")
    e.energy = d.get("energy", 0)
    e.frozen_turns = d.get("frozen_turns", 0)
    e.summon_cooldown = d.get("summon_cooldown", 0)
    e.patrol_dir = tuple(d.get("patrol_dir", (0, 1)))
    # D&D expansion fields
    e.disguised = d.get("disguised", False)
    e.phase_cooldown = d.get("phase_cooldown", 0)
    e.poisoned_turns = d.get("poisoned_turns", 0)
    e.fleeing = d.get("fleeing", False)
    e.regen_suppressed = d.get("regen_suppressed", 0)
    # Expansion phase fields
    e.boss_phase = d.get("boss_phase", 1)
    e.boss_phase_turn = d.get("boss_phase_turn", 0)
    e.bleed_stacks = d.get("bleed_stacks", 0)
    e.bleed_turns = d.get("bleed_turns", 0)
    e.silenced_turns = d.get("silenced_turns", 0)
    # Apex enemy fields
    e.breath_cooldown = d.get("breath_cooldown", 0)
    return e


# ============================================================
# SESSION RECORDING
# ============================================================

class SessionRecorder:
    """Records game events to a JSONL file for later replay."""

    def __init__(self, seed: int, player_name: str = "Adventurer") -> None:
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath: str = os.path.join(RECORDINGS_DIR, f"{ts}_{seed}.jsonl")
        self._file = open(self.filepath, 'w')
        self._write({"event": "init", "seed": seed, "version": 1,
                      "date": ts, "player_name": player_name})
        self._turn: int = 0

    def _write(self, data: dict[str, Any]) -> None:
        self._file.write(json.dumps(data, separators=(',', ':')) + '\n')

    def record(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        entry: dict[str, Any] = {"event": event_type, "turn": self._turn}
        if data:
            entry.update(data)
        self._write(entry)

    def record_input(self, key_name: str, turn: int) -> None:
        self._turn = turn
        self._write({"event": "input", "key": key_name, "turn": turn})

    def record_state_snapshot(self, gs: GameState) -> None:
        p = gs.player
        self._write({"event": "state_snapshot", "turn": gs.turn_count,
                      "hp": p.hp, "max_hp": p.max_hp, "mana": p.mana,
                      "hunger": round(p.hunger, 1), "floor": p.floor,
                      "x": p.x, "y": p.y, "kills": p.kills, "gold": p.gold,
                      "level": p.level, "inventory_count": len(p.inventory)})

    def record_floor_change(self, gs: GameState) -> None:
        self._write({"event": "floor_change", "turn": gs.turn_count,
                      "floor": gs.player.floor,
                      "enemies": len(gs.enemies), "items": len(gs.items)})

    def record_combat(self, enemy_name: str, damage: int, result: str) -> None:
        self._write({"event": "combat", "turn": self._turn,
                      "enemy": enemy_name, "damage": damage, "result": result})

    def record_death(self, gs: GameState) -> None:
        from .ui import calculate_score
        p = gs.player
        self._write({"event": "death", "turn": gs.turn_count,
                      "cause": gs.death_cause or "unknown",
                      "floor": p.floor, "score": calculate_score(p, gs)})

    def record_victory(self, gs: GameState) -> None:
        from .ui import calculate_score
        p = gs.player
        self._write({"event": "victory", "turn": gs.turn_count,
                      "floor": p.floor, "score": calculate_score(p, gs)})

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()


def list_recordings() -> None:
    """List saved recording files with metadata."""
    if not os.path.isdir(RECORDINGS_DIR):
        print("No recordings found.")
        return
    files = sorted(Path(RECORDINGS_DIR).glob("*.jsonl"), reverse=True)
    if not files:
        print("No recordings found.")
        return
    print(f"{'#':<4} {'Date':<20} {'Seed':<12} {'Result':<10} {'Floor':<6} {'Score':<8} {'File'}")
    print("-" * 85)
    for i, f in enumerate(files[:20]):
        try:
            with open(f) as fh:
                first = json.loads(fh.readline())
                # Read last line for result
                fh.seek(0)
                lines = fh.readlines()
                last = json.loads(lines[-1]) if lines else {}
            date = first.get("date", "?")
            seed = first.get("seed", "?")
            result = last.get("event", "?")
            floor = last.get("floor", "?")
            score = last.get("score", "?")
            print(f"{i+1:<4} {date:<20} {seed:<12} {result:<10} {floor:<6} {score:<8} {f.name}")
        except (OSError, json.JSONDecodeError, KeyError):
            print(f"{i+1:<4} {'error reading':<20} {f.name}")


# ============================================================
# SESSION REPLAY
# ============================================================

def replay_session(scr: Any, filepath: str, speed: float = 1.0) -> None:
    """Replay a recorded session visually in the terminal."""
    from .combat import _stealth_detection, player_move, process_enemies, process_status
    from .game import GameState, _choose_branch_headless, _init_new_game
    from .ui import compute_fov, init_colors, render_game, safe_addstr
    curses.curs_set(0)
    scr.nodelay(False)
    scr.keypad(True)
    init_colors()

    with open(filepath) as f:
        lines = f.readlines()
    if not lines:
        return

    init_event = json.loads(lines[0])
    seed = init_event.get("seed", 0)

    # Collect all input events
    input_events = []
    for line in lines[1:]:
        evt = json.loads(line)
        if evt.get("event") == "input":
            input_events.append(evt)

    # Recreate the game with the same seed
    gs = GameState(seed=seed)
    gs._scr = scr
    _init_new_game(gs)

    MOVE_KEYS_BY_NAME = {
        'UP': (0,-1), 'DOWN': (0,1), 'LEFT': (-1,0), 'RIGHT': (1,0),
        'w': (0,-1), 's': (0,1), 'a': (-1,0), 'd': (1,0),
        'h': (-1,0), 'j': (0,1), 'k': (0,-1), 'l': (1,0),
        'y': (-1,-1), 'u': (1,-1), 'b': (-1,1), 'n': (1,1),
    }

    total = len(input_events)
    paused = False
    idx = 0
    base_delay = max(10, int(80 / speed))

    while idx < total and gs.running and not gs.game_over:
        if paused:
            scr.nodelay(False)
            key = scr.getch()
            if key == ord(' '):
                paused = False
            elif key == ord('q'):
                break
            continue

        evt = input_events[idx]
        key_name = evt.get("key", "")
        turn_spent = False

        if key_name in MOVE_KEYS_BY_NAME:
            dx, dy = MOVE_KEYS_BY_NAME[key_name]
            turn_spent = player_move(gs, dx, dy)
        elif key_name == '>':
            if gs.tiles[gs.player.y][gs.player.x] == T_STAIRS_DOWN:
                if gs.player.floor < MAX_FLOORS:
                    new_floor = gs.player.floor + 1
                    if new_floor in BRANCH_CHOICES and new_floor not in gs.branch_choices:
                        _choose_branch_headless(gs, new_floor)
                    gs.generate_floor(new_floor)
                    turn_spent = True
                elif not any(e.boss and e.etype == "dread_lord" and e.is_alive() for e in gs.enemies):
                    gs.victory = True
                    gs.game_over = True
        elif key_name == '.':
            p = gs.player
            if p.hp < p.max_hp and p.hunger > B["rest_hunger_threshold"]:
                p.hp = min(p.max_hp, p.hp + B["rest_hp_per_turn"])
            p.hunger = max(0, p.hunger - B["rest_wait_hunger_cost"])
            turn_spent = True
        elif key_name == ',':
            pickup = [i for i in gs.items if i.x == gs.player.x and i.y == gs.player.y]
            for item in pickup:
                if item.item_type == "gold":
                    gs.player.gold += item.data["amount"]
                    gs.items.remove(item)
                elif len(gs.player.inventory) < gs.player.carry_capacity:
                    gs.items.remove(item)
                    gs.player.inventory.append(item)
                    gs.player.items_found += 1
            turn_spent = bool(pickup)

        if turn_spent:
            gs.turn_count += 1
            if gs.last_noise > 0:
                _stealth_detection(gs, gs.last_noise)
            gs.last_noise = 0
            process_enemies(gs)
            process_status(gs)
            if gs.player.hp <= 0:
                gs.game_over = True

        # Render with replay overlay
        fov_radius = gs.player.get_torch_radius()
        if "Blindness" in gs.player.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        render_game(scr, gs)
        # Overlay
        progress = f"REPLAY [{idx+1}/{total}] Speed: {speed:.1f}x  [Space]=Pause [q]=Quit [+/-]=Speed"
        safe_addstr(scr, SCREEN_H - 1, 0, progress[:SCREEN_W-1],
                   curses.color_pair(C_CYAN) | curses.A_BOLD)
        scr.refresh()

        idx += 1

        # Check for user input (non-blocking)
        scr.nodelay(True)
        ck = scr.getch()
        scr.nodelay(False)
        if ck == ord('q'):
            break
        elif ck == ord(' '):
            paused = True
        elif ck == ord('+') or ck == ord('='):
            speed = min(16.0, speed * 2)
            base_delay = max(10, int(80 / speed))
        elif ck == ord('-'):
            speed = max(0.25, speed / 2)
            base_delay = max(10, int(80 / speed))

        curses.napms(base_delay)

    # Show final state
    render_game(scr, gs)
    msg = "REPLAY COMPLETE" if idx >= total else "REPLAY STOPPED"
    safe_addstr(scr, SCREEN_H - 1, 0, f"{msg} - Press any key",
               curses.color_pair(C_YELLOW) | curses.A_BOLD)
    scr.refresh()
    scr.nodelay(False)
    scr.getch()
