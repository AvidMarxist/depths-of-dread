"""Tests for the v1.1 overhaul: Frozen Abyss / Sunken Library branches,
Kraken mechanics, floor caching, the Dread Lord stair seal, enemy speed,
save/load fidelity, and assorted bug-fix regressions."""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from depths_of_dread.combat import _award_kill, _kraken_move, process_enemies
from depths_of_dread.game import GameState, _choose_branch_headless
from depths_of_dread.items import (
    _cast_spell,
    player_move,
    process_status,
    use_scroll,
)
from depths_of_dread.persistence import delete_save, load_game, save_game
from depths_of_dread.constants import (
    B,
    BRANCH_CHOICES,
    BRANCH_DEFS,
    ENEMY_TYPES,
    MAP_H,
    MAP_W,
    SPELLS,
    THEME_PALETTE_256,
    T_FLOOR,
    T_ICE,
    T_STAIRS_DOWN,
    T_STAIRS_LOCKED,
    T_WALL,
    T_WATER,
    WALKABLE,
)
from depths_of_dread.entities import Enemy, Item


def _flat_map(gs, tile=T_FLOOR):
    """Replace the map with an open room bounded by walls."""
    gs.tiles = [[T_WALL] * MAP_W for _ in range(MAP_H)]
    for y in range(1, MAP_H - 1):
        for x in range(1, MAP_W - 1):
            gs.tiles[y][x] = tile
    gs.enemies = []
    gs.items = []
    gs.traps = []
    gs.vignettes = []
    gs.npcs = []


class TestNewBranches:
    def test_floor_17_branch_choice_exists(self):
        assert 17 in BRANCH_CHOICES
        a, b = BRANCH_CHOICES[17]
        assert a == "frozen_abyss" and b == "sunken_library"

    def test_branch_defs_reference_valid_enemies(self):
        for key in ("frozen_abyss", "sunken_library"):
            bdef = BRANCH_DEFS[key]
            for etype in bdef["enemy_pool"]:
                assert etype in ENEMY_TYPES, f"{key} pool has unknown {etype}"
            assert bdef["mini_boss"] in ENEMY_TYPES
            assert THEME_PALETTE_256.get(bdef["theme"]), f"no palette for {bdef['theme']}"

    def test_frozen_abyss_floor_has_ice(self):
        random.seed(7)
        gs = GameState(headless=True, seed=7)
        gs.branch_choices[17] = "frozen_abyss"
        gs.generate_floor(18)
        ice = sum(1 for row in gs.tiles for t in row if t == T_ICE)
        assert ice > 0

    def test_sunken_library_floor_has_heavy_water_and_scrolls(self):
        random.seed(11)
        gs = GameState(headless=True, seed=11)
        gs.branch_choices[17] = "sunken_library"
        gs.generate_floor(18)
        water = sum(1 for row in gs.tiles for t in row if t == T_WATER)
        assert water > 20
        assert sum(1 for i in gs.items if i.item_type == "scroll") >= BRANCH_DEFS["sunken_library"]["bonus_scrolls"]

    def test_mini_bosses_do_not_spawn_outside_their_branch(self):
        random.seed(3)
        gs = GameState(headless=True, seed=3)
        gs.branch_choices[17] = "frozen_abyss"
        gs.generate_floor(19)
        etypes = {e.etype for e in gs.enemies}
        assert "kraken" not in etypes  # kraken belongs to the other branch
        assert "frost_titan" in etypes


class TestIceSliding:
    def test_slide_until_wall(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs, T_ICE)
        p = gs.player
        p.x, p.y = 5, 5
        player_move(gs, 1, 0)
        # Slid all the way to the wall at MAP_W-2
        assert p.x == MAP_W - 2

    def test_slide_stops_on_floor(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs, T_ICE)
        gs.tiles[5][10] = T_FLOOR
        p = gs.player
        p.x, p.y = 5, 5
        player_move(gs, 1, 0)
        assert (p.x, p.y) == (10, 5)

    def test_slide_stops_at_enemy(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs, T_ICE)
        p = gs.player
        p.x, p.y = 5, 5
        gs.enemies.append(Enemy(9, 5, "goblin"))
        player_move(gs, 1, 0)
        assert p.x == 8  # stopped one short of the goblin


class TestKraken:
    def _kraken_setup(self, dist):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs)
        p = gs.player
        p.x, p.y = 10, 10
        k = Enemy(10 + dist, 10, "kraken")
        k.alerted = True
        k.alertness = "alert"
        gs.enemies.append(k)
        gs.visible = {(k.x, k.y), (p.x, p.y)}
        return gs, k

    def test_ink_cloud_blinds_at_range(self):
        gs, k = self._kraken_setup(4)
        _kraken_move(gs, k)
        assert "Blindness" in gs.player.status_effects
        assert k.ink_cooldown == k.ink_cooldown_max

    def test_constrict_applies_adjacent(self):
        gs, k = self._kraken_setup(1)
        k.ink_cooldown = 5  # ink not ready
        random.seed(0)
        for _ in range(30):
            _kraken_move(gs, k)
            if "Constricted" in gs.player.status_effects:
                break
        assert "Constricted" in gs.player.status_effects

    def test_constricted_player_move_spends_turn_without_moving(self):
        gs, k = self._kraken_setup(3)
        p = gs.player
        p.status_effects["Constricted"] = 4
        random.seed(1)  # struggle may or may not free — either way turn spent
        ox, oy = p.x, p.y
        spent = player_move(gs, -1, 0)
        assert spent is True
        assert (p.x, p.y) == (ox, oy)

    def test_constricted_player_can_still_attack(self):
        gs, k = self._kraken_setup(1)
        p = gs.player
        p.status_effects["Constricted"] = 4
        hp_before = k.hp
        random.seed(2)
        for _ in range(20):
            player_move(gs, 1, 0)  # attack the kraken
            if k.hp < hp_before:
                break
        assert k.hp < hp_before


class TestScrollSoak:
    def test_water_can_dissolve_scroll_in_sunken_library(self):
        gs = GameState(headless=True)
        gs.branch_choices[17] = "sunken_library"
        gs.generate_floor(18)
        _flat_map(gs)
        gs.active_branch = "sunken_library"
        p = gs.player
        p.x, p.y = 10, 10
        gs.tiles[10][11] = T_WATER
        scroll = Item(0, 0, "scroll", "Mapping",
                      {"effect": "Mapping", "label": "XYZZY", "char": '?'})
        p.inventory.append(scroll)
        random.seed(0)
        destroyed = False
        for _ in range(60):
            p.x, p.y = 10, 10
            player_move(gs, 1, 0)
            if scroll not in p.inventory:
                destroyed = True
                break
        assert destroyed

    def test_no_soak_outside_branch(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs)
        gs.active_branch = None
        p = gs.player
        p.x, p.y = 10, 10
        scroll = Item(0, 0, "scroll", "Mapping",
                      {"effect": "Mapping", "label": "XYZZY", "char": '?'})
        p.inventory.append(scroll)
        random.seed(0)
        for _ in range(60):
            gs.tiles[10][11] = T_WATER
            p.x, p.y = 10, 10
            player_move(gs, 1, 0)
        assert scroll in p.inventory


class TestDreadLordSeal:
    def test_floor_15_stairs_locked(self):
        random.seed(5)
        gs = GameState(headless=True, seed=5)
        gs.generate_floor(15)
        sx, sy = gs.stair_down
        assert gs.tiles[sy][sx] == T_STAIRS_LOCKED

    def test_killing_dread_lord_unlocks(self):
        random.seed(5)
        gs = GameState(headless=True, seed=5)
        gs.generate_floor(15)
        dl = next((e for e in gs.enemies if e.etype == "dread_lord"), None)
        assert dl is not None
        dl.hp = 0
        _award_kill(gs, dl)
        sx, sy = gs.stair_down
        assert gs.tiles[sy][sx] == T_STAIRS_DOWN


class TestFloorCaching:
    def test_revisited_floor_is_restored_not_regenerated(self):
        gs = GameState(headless=True, seed=42)
        gs.generate_floor(1)
        gs.generate_floor(2)
        tiles_before = [row[:] for row in gs.tiles]
        items_before = len(gs.items)
        # Consume something so we can detect a fresh roll
        if gs.items:
            gs.items.pop()
        gs.generate_floor(1)   # ascend
        gs.generate_floor(2)   # descend again
        assert gs.tiles == tiles_before
        assert len(gs.items) == items_before - 1  # not restocked

    def test_ascend_restores_prior_floor(self):
        gs = GameState(headless=True, seed=43)
        gs.generate_floor(1)
        tiles_f1 = [row[:] for row in gs.tiles]
        gs.generate_floor(2)
        gs.generate_floor(1)
        assert gs.tiles == tiles_f1


class TestEnemySpeed:
    def test_fast_enemy_acts_twice(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs)
        p = gs.player
        p.x, p.y = 10, 10
        e = Enemy(20, 10, "rat")
        e.speed = 2.0
        e.energy = 0.0
        e.alerted = True
        e.alertness = "alert"
        gs.enemies = [e]
        gs.visible = set()
        process_enemies(gs)
        # Speed 2.0 → two chase steps toward the player
        assert e.x == 18

    def test_slow_enemy_skips_turns(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs)
        p = gs.player
        p.x, p.y = 10, 10
        e = Enemy(20, 10, "rat")
        e.speed = 0.5
        e.energy = 0.0
        e.alerted = True
        e.alertness = "alert"
        gs.enemies = [e]
        gs.visible = set()
        process_enemies(gs)
        assert e.x == 20  # first turn: accumulating energy
        process_enemies(gs)
        assert e.x == 19


class TestSaveLoadFidelity:
    def test_enemy_stats_and_difficulty_roundtrip(self):
        gs = GameState(headless=True, difficulty="hard", seed=9)
        gs.generate_floor(12)
        gs.challenge_pacifist = True
        live = [e for e in gs.enemies if e.is_alive()]
        assert live
        stats_before = {(e.x, e.y): (e.dmg, e.defense, e.speed, e.ai) for e in live}
        assert save_game(gs)
        loaded = load_game()
        delete_save()
        assert loaded is not None
        assert loaded.difficulty == "hard"
        assert loaded.challenge_pacifist is True
        for e in loaded.enemies:
            assert stats_before[(e.x, e.y)] == (e.dmg, e.defense, e.speed, e.ai)

    def test_puzzle_positions_are_tuples_after_load(self):
        gs = GameState(headless=True, seed=1)
        gs.generate_floor(1)
        gs.puzzles = [{"type": "pressure", "positions": [(3, 4), (5, 6)],
                       "activated": [(3, 4)], "solved": False, "room": (1, 1, 4, 4),
                       "timer": 0, "timer_max": 15}]
        gs.wall_torches = [(7, 8)]
        assert save_game(gs)
        loaded = load_game()
        delete_save()
        assert loaded is not None
        puz = loaded.puzzles[0]
        assert puz["positions"] == [(3, 4), (5, 6)]
        assert (3, 4) in puz["activated"]
        assert (7, 8) in loaded.wall_torches


class TestBugfixRegressions:
    def test_silence_blocks_cast_spell(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.known_spells.add("Heal")
        p.mana = 20
        p.hp = 1
        p.status_effects["Silence"] = 3
        result = _cast_spell(gs, None, "Heal", SPELLS["Heal"])
        assert result is False
        assert p.hp == 1

    def test_fear_scroll_sets_fleeing(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs)
        p = gs.player
        p.x, p.y = 10, 10
        e = Enemy(12, 10, "goblin")
        gs.enemies = [e]
        scroll = Item(0, 0, "scroll", "Fear",
                      {"effect": "Fear", "label": "ZZZ", "char": '?'})
        scroll.identified = True
        p.inventory.append(scroll)
        use_scroll(gs, scroll)
        assert e.fleeing is True
        assert e.fleeing_turns == B["scroll_fear_duration"]

    def test_starvation_ticks_without_moving(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.hunger = 0
        hp = p.hp
        process_status(gs)
        assert p.hp < hp

    def test_secret_wall_blocks_movement(self):
        from depths_of_dread.constants import T_SECRET_WALL
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs)
        p = gs.player
        p.x, p.y = 10, 10
        gs.tiles[10][11] = T_SECRET_WALL
        moved = player_move(gs, 1, 0)
        assert moved is False
        assert (p.x, p.y) == (10, 10)

    def test_secret_wall_blocks_fov(self):
        from depths_of_dread.constants import T_SECRET_WALL
        from depths_of_dread.mapgen import compute_fov
        gs = GameState(headless=True)
        gs.generate_floor(1)
        _flat_map(gs)
        # Wall of secret tiles at x=12
        for y in range(MAP_H):
            gs.tiles[y][12] = T_SECRET_WALL
        vis = set()
        compute_fov(gs.tiles, 10, 10, 8, vis)
        assert (14, 10) not in vis

    def test_headless_branch_choice_records_nothing_without_recorder(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.recorder = None
        choice = _choose_branch_headless(gs, 5)
        assert choice in BRANCH_CHOICES[5]
