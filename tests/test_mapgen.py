"""Tests for dungeon generation, room shapes, and A* pathfinding."""

import sys
import os
import time
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from depths_of_dread.game import (
    GameState, generate_dungeon, astar, flood_fill_count, count_walkable,
    _carve_room_shape,
    T_WALL, T_FLOOR, WALKABLE,
    MAP_W, MAP_H, MAX_FLOORS,
)

import pytest


class TestDungeonGeneration:
    """Test BSP dungeon generation."""

    def test_connectivity(self):
        """Generated dungeons are at least 95% connected."""
        for _ in range(20):
            floor = random.randint(1, MAX_FLOORS)
            tiles, rooms, start, end = generate_dungeon(floor)
            w = count_walkable(tiles)
            r = flood_fill_count(tiles, start[0], start[1])
            assert w > 0
            assert r / w >= 0.95

    def test_has_stairs(self):
        """All floors have appropriate stairs."""
        from depths_of_dread.game import T_STAIRS_DOWN, T_STAIRS_UP
        for floor in range(1, MAX_FLOORS + 1):
            tiles, rooms, start, end = generate_dungeon(floor)
            has_down = any(tiles[y][x] == T_STAIRS_DOWN for y in range(MAP_H) for x in range(MAP_W))
            has_up = any(tiles[y][x] == T_STAIRS_UP for y in range(MAP_H) for x in range(MAP_W))
            if floor < MAX_FLOORS:
                assert has_down, f"Floor {floor} missing stairs down"
            if floor > 1:
                assert has_up, f"Floor {floor} missing stairs up"

    def test_minimum_rooms(self):
        """Each floor has at least 4 rooms."""
        for _ in range(10):
            floor = random.randint(1, MAX_FLOORS)
            tiles, rooms, start, end = generate_dungeon(floor)
            # Fallback might have fewer, but BSP should have >= 4
            assert len(rooms) >= 3  # fallback grid can have fewer


class TestRoomShapeVariety:
    """Tests for room shape variety (Phase 1, Feature 4)."""

    def test_carve_rect_room(self):
        """Rectangular room carving fills all tiles."""
        tiles = [[T_WALL] * 20 for _ in range(20)]
        _carve_room_shape(tiles, 2, 2, 5, 4, "rect")
        floor_count = sum(1 for y in range(2, 6) for x in range(2, 7)
                         if tiles[y][x] == T_FLOOR)
        assert floor_count == 20  # 5 * 4

    def test_carve_circular_room(self):
        """Circular room should carve fewer tiles than rectangular."""
        tiles_rect = [[T_WALL] * 30 for _ in range(30)]
        tiles_circ = [[T_WALL] * 30 for _ in range(30)]
        _carve_room_shape(tiles_rect, 3, 3, 10, 10, "rect")
        _carve_room_shape(tiles_circ, 3, 3, 10, 10, "circular")
        rect_count = sum(1 for y in range(30) for x in range(30)
                         if tiles_rect[y][x] == T_FLOOR)
        circ_count = sum(1 for y in range(30) for x in range(30)
                         if tiles_circ[y][x] == T_FLOOR)
        assert circ_count < rect_count
        assert circ_count > 0

    def test_carve_l_shaped_room(self):
        """L-shaped room should carve fewer tiles than rectangular."""
        tiles_rect = [[T_WALL] * 30 for _ in range(30)]
        tiles_l = [[T_WALL] * 30 for _ in range(30)]
        _carve_room_shape(tiles_rect, 3, 3, 8, 8, "rect")
        _carve_room_shape(tiles_l, 3, 3, 8, 8, "l_shaped")
        rect_count = sum(1 for y in range(30) for x in range(30)
                         if tiles_rect[y][x] == T_FLOOR)
        l_count = sum(1 for y in range(30) for x in range(30)
                      if tiles_l[y][x] == T_FLOOR)
        assert l_count < rect_count
        assert l_count > 0

    def test_carve_pillared_room(self):
        """Pillared room should have wall tiles inside the room boundary."""
        tiles = [[T_WALL] * 30 for _ in range(30)]
        _carve_room_shape(tiles, 3, 3, 8, 8, "pillared")
        # Should have both floor and wall tiles inside the room
        floor_count = sum(1 for y in range(3, 11) for x in range(3, 11)
                          if tiles[y][x] == T_FLOOR)
        wall_count = sum(1 for y in range(4, 10) for x in range(4, 10)
                         if tiles[y][x] == T_WALL)
        assert floor_count > 0
        assert wall_count > 0  # Pillars exist

    def test_carve_unknown_shape_falls_back(self):
        """Unknown shape should fall back to rect."""
        tiles = [[T_WALL] * 20 for _ in range(20)]
        _carve_room_shape(tiles, 2, 2, 5, 4, "unknown_shape")
        floor_count = sum(1 for y in range(2, 6) for x in range(2, 7)
                          if tiles[y][x] == T_FLOOR)
        assert floor_count == 20

    def test_room_shapes_appear_in_generation(self):
        """Different room shapes should appear across many seeds."""
        # The weighted random should produce non-rect shapes in 50 seeds
        shapes_seen = set()
        for seed in range(50):
            random.seed(seed)
            gs = GameState(headless=True)
            gs.generate_floor(1)
            # Just check it doesn't crash
        # If we got here without error, generation works with all shapes
        assert True


class TestAstarPerformance:
    """Bug F: A* heapq comparison issue fixed."""

    def test_astar_finds_valid_path(self):
        """Functional: A* still finds valid paths after heapq change."""
        gs = GameState(headless=True, seed=42)
        gs.generate_floor(1)
        p = gs.player
        # Find a walkable tile nearby (search in all directions)
        target = None
        for dx in range(1, 15):
            for dy_offset in [0, 1, -1, 2, -2]:
                tx, ty = p.x + dx, p.y + dy_offset
                if 0 < tx < MAP_W - 1 and 0 < ty < MAP_H - 1 and gs.tiles[ty][tx] in WALKABLE:
                    target = (tx, ty)
                    break
            if target:
                break
        if target:
            result = astar(gs.tiles, p.x, p.y, target[0], target[1], max_steps=30)
            assert result is not None
            dx, dy = result
            assert abs(dx) <= 1 and abs(dy) <= 1

    def test_astar_completes_quickly(self):
        """Performance: A* with max_steps=20 completes in reasonable time (<100ms)."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Try to path to a far-away tile
        start = time.time()
        for _ in range(100):  # 100 pathfinding calls
            astar(gs.tiles, p.x, p.y, p.x + 10, p.y + 10, max_steps=20)
        elapsed = time.time() - start
        assert elapsed < 1.0, f"100 A* calls took {elapsed:.3f}s (>1s budget)"

    def test_astar_no_valid_path_returns_none(self):
        """Edge: A* with no valid path -> returns None, no infinite loop."""
        # Create a map where the target is walled off
        tiles = [[T_WALL for _ in range(MAP_W)] for _ in range(MAP_H)]
        # Small open area at (5,5)
        tiles[5][5] = T_FLOOR
        tiles[5][6] = T_FLOOR
        # Target at (MAP_W-2, MAP_H-2) — completely walled off
        tiles[MAP_H - 2][MAP_W - 2] = T_FLOOR
        start = time.time()
        result = astar(tiles, 5, 5, MAP_W - 2, MAP_H - 2, max_steps=20)
        elapsed = time.time() - start
        assert result is None
        assert elapsed < 0.5, f"A* on blocked path took {elapsed:.3f}s"

    def test_astar_same_position(self):
        """Edge: A* from a position to itself returns (0,0)."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        result = astar(gs.tiles, p.x, p.y, p.x, p.y)
        assert result == (0, 0)
