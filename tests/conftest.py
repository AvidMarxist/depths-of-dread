"""Shared fixtures and imports for the Depths of Dread test suite."""

import sys
import os

# Import game module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from depths_of_dread.game import (
    GameState, Player, Enemy, Item,
    generate_dungeon, compute_fov,
    player_move,
    WEAPON_TYPES, FOOD_TYPES, BOW_TYPES, ARROW_ITEM,
    T_WALL, T_FLOOR,
    MAP_W, MAP_H,
)


@pytest.fixture
def gs():
    """Create a fresh headless GameState with floor 1 generated."""
    state = GameState(headless=True)
    state.generate_floor(1)
    return state


@pytest.fixture
def gs_with_gear():
    """Create a GameState with starter gear (like a real new game)."""
    state = GameState(headless=True)
    # Add starter gear
    sw = Item(0, 0, "weapon", 0, WEAPON_TYPES[0])
    sw.identified = True
    sw.equipped = True
    state.player.weapon = sw
    state.player.inventory.append(sw)
    for fd in [FOOD_TYPES[0], FOOD_TYPES[1]]:
        fi = Item(0, 0, "food", fd["name"], fd)
        state.player.inventory.append(fi)
    sb = Item(0, 0, "bow", "Short Bow", dict(BOW_TYPES[0]))
    sb.identified = True
    sb.equipped = True
    state.player.bow = sb
    state.player.inventory.append(sb)
    arrows = Item(0, 0, "arrow", "Arrow", dict(ARROW_ITEM))
    arrows.count = 10
    state.player.inventory.append(arrows)
    state.generate_floor(1)
    return state


@pytest.fixture
def gs_with_enemy(gs):
    """Create a GameState with an enemy adjacent to player."""
    p = gs.player
    # Place a goblin adjacent
    e = Enemy(p.x + 1, p.y, "goblin")
    gs.enemies.append(e)
    # Make the tile walkable
    if gs.tiles[p.y][p.x + 1] == T_WALL:
        gs.tiles[p.y][p.x + 1] = T_FLOOR
    return gs, e
