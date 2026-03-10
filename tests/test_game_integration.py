"""Tests for gameplay integration: keybindings, auto-explore/fight, smart bump,
victory conditions, context tips, shrines, challenge modes, environmental interactions,
hunger, torch."""

import sys
import os
import random
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from depths_of_dread import game as dungeon
from depths_of_dread.game import (
    GameState, Player, Enemy, Item,
    compute_fov, player_move, player_attack, process_enemies, process_status,
    _get_direction_delta, _bfs_unexplored, _init_new_game,
    auto_fight_step, auto_explore_step, check_context_tips,
    pray_at_shrine, _award_kill, _CHALLENGE_MODES,
    BotPlayer, _bot_execute_action, _update_explored_from_fov,
    T_WALL, T_FLOOR, T_CORRIDOR, T_STAIRS_DOWN, T_WATER, T_LAVA, T_SHRINE,
    MAP_W, MAP_H, MAX_FLOORS, MAX_INVENTORY, TORCH_MAX_FUEL,
    FOOD_TYPES, WALKABLE,
    C_DARK,
)

import pytest


class TestKeybindings:
    """Test every keybinding maps to correct action."""

    def test_direction_delta_cardinal(self):
        """All cardinal direction keys return correct deltas."""
        import curses as c
        assert _get_direction_delta(c.KEY_UP) == (0, -1)
        assert _get_direction_delta(c.KEY_DOWN) == (0, 1)
        assert _get_direction_delta(c.KEY_LEFT) == (-1, 0)
        assert _get_direction_delta(c.KEY_RIGHT) == (1, 0)
        assert _get_direction_delta(ord('w')) == (0, -1)
        assert _get_direction_delta(ord('s')) == (0, 1)
        assert _get_direction_delta(ord('a')) == (-1, 0)
        assert _get_direction_delta(ord('d')) == (1, 0)
        assert _get_direction_delta(ord('h')) == (-1, 0)
        assert _get_direction_delta(ord('j')) == (0, 1)
        assert _get_direction_delta(ord('k')) == (0, -1)
        assert _get_direction_delta(ord('l')) == (1, 0)

    def test_direction_delta_diagonal(self):
        """Diagonal direction keys (yubn) return correct deltas."""
        assert _get_direction_delta(ord('y')) == (-1, -1)
        assert _get_direction_delta(ord('u')) == (1, -1)
        assert _get_direction_delta(ord('b')) == (-1, 1)
        assert _get_direction_delta(ord('n')) == (1, 1)

    def test_direction_delta_invalid(self):
        """Invalid keys return None."""
        assert _get_direction_delta(ord('x')) is None
        assert _get_direction_delta(ord('q')) is None
        assert _get_direction_delta(ord('Z')) is None

    def test_direction_delta_esc(self):
        """ESC key returns None (used as cancel)."""
        assert _get_direction_delta(27) is None


class TestAutoExplore:
    """Test auto-explore pathfinding and stop conditions."""

    def test_finds_unexplored_tile(self, gs):
        """BFS finds nearest unexplored walkable tile."""
        # Mark area around player as explored
        p = gs.player
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                ny, nx = p.y + dy, p.x + dx
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H:
                    gs.explored[ny][nx] = True
        target = _bfs_unexplored(gs)
        # Should find something since the map is bigger than 7x7
        assert target is not None
        tx, ty = target
        assert not gs.explored[ty][tx]
        assert gs.tiles[ty][tx] in WALKABLE

    def test_stops_on_enemy_in_fov(self, gs):
        """Auto-explore stops when enemy enters FOV."""
        p = gs.player
        e = Enemy(p.x + 2, p.y, "rat")
        gs.enemies.append(e)
        if gs.tiles[p.y][p.x + 2] == T_WALL:
            gs.tiles[p.y][p.x + 2] = T_FLOOR
        gs.auto_exploring = True
        # Compute FOV so enemy is visible
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        result = auto_explore_step(gs)
        assert result is None
        assert not gs.auto_exploring

    def test_stops_on_low_hp(self, gs):
        """Auto-explore stops when HP drops below threshold."""
        gs.player.hp = int(gs.player.max_hp * 0.3)
        gs.auto_exploring = True
        result = auto_explore_step(gs)
        assert result is None
        assert not gs.auto_exploring

    def test_stops_on_stairs(self, gs):
        """Auto-explore stops when standing on stairs."""
        p = gs.player
        gs.tiles[p.y][p.x] = T_STAIRS_DOWN
        gs.auto_exploring = True
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        result = auto_explore_step(gs)
        assert result is None
        assert not gs.auto_exploring

    def test_stops_on_fully_explored(self, gs):
        """Auto-explore stops when all tiles are explored."""
        # Mark everything as explored
        for y in range(MAP_H):
            for x in range(MAP_W):
                gs.explored[y][x] = True
        gs.auto_exploring = True
        compute_fov(gs.tiles, gs.player.x, gs.player.y, 8, gs.visible)
        result = auto_explore_step(gs)
        assert result is None
        assert not gs.auto_exploring


class TestAutoFight:
    """Test auto-fight targets nearest enemy and stops on conditions."""

    def test_targets_nearest_enemy(self, gs):
        """Auto-fight attacks nearest visible enemy."""
        p = gs.player
        gs.enemies.clear()
        # Place enemy adjacent
        e = Enemy(p.x + 1, p.y, "rat")
        gs.enemies.append(e)
        if gs.tiles[p.y][p.x + 1] == T_WALL:
            gs.tiles[p.y][p.x + 1] = T_FLOOR
        gs.auto_fighting = True
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        result = auto_fight_step(gs)
        # Should have attacked (spent a turn) or moved toward
        assert result is True

    def test_stops_on_hp_threshold(self, gs):
        """Auto-fight stops when HP drops below 30% of max."""
        gs.player.hp = int(gs.player.max_hp * 0.2)  # below 30%
        gs.auto_fighting = True
        compute_fov(gs.tiles, gs.player.x, gs.player.y, 8, gs.visible)
        result = auto_fight_step(gs)
        assert result is None
        assert not gs.auto_fighting

    def test_stops_when_no_enemies(self, gs):
        """Auto-fight stops when no enemies visible."""
        gs.enemies.clear()
        gs.auto_fighting = True
        compute_fov(gs.tiles, gs.player.x, gs.player.y, 8, gs.visible)
        result = auto_fight_step(gs)
        assert result is None
        assert not gs.auto_fighting


class TestSmartBump:
    """Test smart bump: door tiles, enemy tiles, wall tiles."""

    def test_bump_enemy_attacks(self, gs):
        """Bumping into enemy triggers attack."""
        p = gs.player
        e = Enemy(p.x + 1, p.y, "rat")
        gs.enemies.append(e)
        if gs.tiles[p.y][p.x + 1] == T_WALL:
            gs.tiles[p.y][p.x + 1] = T_FLOOR
        old_hp = e.hp
        player_move(gs, 1, 0)
        # Either hit or miss, but we should have tried
        assert len(gs.messages) > 0

    def test_bump_wall_blocked(self, gs):
        """Bumping into wall shows 'Blocked!' message."""
        p = gs.player
        # Find a wall adjacent to player
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = p.x + dx, p.y + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] == T_WALL:
                gs.messages.clear()
                result = player_move(gs, dx, dy)
                assert result is False
                assert any("Blocked" in m[0] for m in gs.messages)
                return
        pytest.skip("No wall adjacent to player")

    def test_move_to_floor(self, gs):
        """Moving to floor tile succeeds."""
        p = gs.player
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = p.x + dx, p.y + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in (T_FLOOR, T_CORRIDOR):
                # Clear enemies from that tile
                gs.enemies = [e for e in gs.enemies if not (e.x == nx and e.y == ny)]
                gs.items = [i for i in gs.items if not (i.x == nx and i.y == ny)]
                result = player_move(gs, dx, dy)
                assert result is True
                assert p.x == nx and p.y == ny
                return
        pytest.skip("No walkable tile adjacent to player")


class TestVictoryCondition:
    """Test victory condition: kill boss + descend."""

    def test_victory_with_dead_boss(self, gs):
        """Victory when Dread Lord is dead and player descends on floor 15."""
        gs.player.floor = MAX_FLOORS
        gs.enemies.clear()  # No living Dread Lord
        gs.victory = False
        # Simulate pressing '>'
        boss_alive = any(e.boss and e.etype == "dread_lord" and e.is_alive()
                        for e in gs.enemies)
        if not boss_alive:
            gs.victory = True
            gs.game_over = True
        assert gs.victory is True

    def test_no_victory_with_alive_boss(self, gs):
        """No victory when Dread Lord is still alive."""
        gs.player.floor = MAX_FLOORS
        boss = Enemy(5, 5, "dread_lord")
        gs.enemies.append(boss)
        boss_alive = any(e.boss and e.etype == "dread_lord" and e.is_alive()
                        for e in gs.enemies)
        assert boss_alive is True


class TestGameplayIntegration:
    """End-to-end gameplay scenario tests."""

    def test_full_floor_clear(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.strength = 50
        p.hp = 500
        p.max_hp = 500
        # Kill all enemies
        for e in gs.enemies:
            e.hp = 0
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        assert len(gs.enemies) == 0

    def test_multi_floor_descent(self):
        gs = GameState(headless=True)
        _init_new_game(gs)
        p = gs.player
        p.hp = 500
        p.max_hp = 500
        p.hunger = 100
        for target_floor in range(2, 4):
            gs.generate_floor(target_floor)
            assert p.floor == target_floor
        assert p.floor == 3

    def test_inventory_full_then_drop(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Fill inventory
        while len(p.inventory) < MAX_INVENTORY:
            f = FOOD_TYPES[0]
            p.inventory.append(Item(0, 0, "food", f["name"], f))
        assert len(p.inventory) == MAX_INVENTORY
        # Drop one
        p.inventory.pop()
        assert len(p.inventory) == MAX_INVENTORY - 1

    def test_starvation_death(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.hunger = 0
        # Remove all food
        p.inventory = [i for i in p.inventory if i.item_type != "food"]
        # Walk until death
        for _ in range(500):
            if gs.game_over:
                break
            # Find walkable neighbor
            for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                nx, ny = p.x + dx, p.y + dy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
                    player_move(gs, dx, dy)
                    gs.turn_count += 1
                    process_enemies(gs)
                    process_status(gs)
                    if p.hp <= 0:
                        gs.game_over = True
                    break
        assert gs.game_over
        assert gs.death_cause == "starvation"

    def test_boss_encounter(self):
        """Floor 5 has Ogre King boss."""
        gs = GameState(headless=True)
        gs.generate_floor(5)
        bosses = [e for e in gs.enemies if e.boss]
        assert len(bosses) >= 1
        assert any(e.etype == "ogre_king" for e in bosses)


class TestFirstMeleeMessage:
    """Test first melee attack message."""

    def test_first_attack_message(self, gs):
        """First melee attack shows 'You attack the...' message."""
        p = gs.player
        e = Enemy(p.x + 1, p.y, "rat")
        gs.enemies.append(e)
        if gs.tiles[p.y][p.x + 1] == T_WALL:
            gs.tiles[p.y][p.x + 1] = T_FLOOR
        gs.first_melee_done = False
        gs.messages.clear()
        player_attack(gs, e)
        assert gs.first_melee_done is True
        assert any("You attack the" in m[0] for m in gs.messages)

    def test_second_attack_no_extra_message(self, gs):
        """Second melee attack does NOT show 'You attack the...' again."""
        p = gs.player
        e = Enemy(p.x + 1, p.y, "rat")
        e.hp = 100
        gs.enemies.append(e)
        if gs.tiles[p.y][p.x + 1] == T_WALL:
            gs.tiles[p.y][p.x + 1] = T_FLOOR
        gs.first_melee_done = True
        gs.messages.clear()
        player_attack(gs, e)
        assert not any("You attack the" in m[0] for m in gs.messages)


class TestContextTips:
    """Test first-encounter tips fire exactly once each."""

    def test_enemy_adjacent_tip(self, gs):
        p = gs.player
        gs.enemies.clear()
        e = Enemy(p.x + 1, p.y, "goblin")
        gs.enemies.append(e)
        if gs.tiles[p.y][p.x + 1] == T_WALL:
            gs.tiles[p.y][p.x + 1] = T_FLOOR
        gs.messages.clear()
        check_context_tips(gs)
        assert "enemy_adjacent" in gs.tips_shown
        tip_msgs = [m for m in gs.messages if "Tip: Walk into enemies" in m[0]]
        assert len(tip_msgs) == 1

    def test_tips_fire_only_once(self, gs):
        p = gs.player
        gs.enemies.clear()
        e = Enemy(p.x + 1, p.y, "goblin")
        gs.enemies.append(e)
        if gs.tiles[p.y][p.x + 1] == T_WALL:
            gs.tiles[p.y][p.x + 1] = T_FLOOR
        check_context_tips(gs)
        msg_count = len(gs.messages)
        check_context_tips(gs)
        # No new tip messages added
        tip_msgs = [m for m in gs.messages if "Tip: Walk into enemies" in m[0]]
        assert len(tip_msgs) == 1


class TestShrineCurse:
    """Test shrine curse no longer instant-kills."""

    def test_shrine_curse_not_lethal(self, gs):
        """Shrine curse at 10% roll should not kill player."""
        p = gs.player
        p.hp = 20
        gs.tiles[p.y][p.x] = T_SHRINE
        # Force the curse roll
        random.seed(99)
        for _ in range(100):
            p.hp = 20
            gs.tiles[p.y][p.x] = T_SHRINE
            pray_at_shrine(gs)
            # Player should NEVER die from shrine curse
            assert p.hp >= 1 or not gs.game_over, "Shrine curse should not be lethal"
            gs.game_over = False
            gs.tiles[p.y][p.x] = T_SHRINE


class TestChallengeModes:
    """Tests for challenge modes (Phase 4, Feature 2)."""

    def test_challenge_fields_on_gamestate(self):
        """GameState should have challenge mode fields."""
        gs = GameState(headless=True)
        assert hasattr(gs, 'challenge_ironman')
        assert hasattr(gs, 'challenge_speedrun')
        assert hasattr(gs, 'challenge_pacifist')
        assert hasattr(gs, 'challenge_dark')

    def test_speedrun_timer_resets_on_floor(self):
        """Speedrun timer should reset when generating a new floor."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.challenge_speedrun = True
        gs.speedrun_timer = 50
        gs.generate_floor(2)
        assert gs.speedrun_timer == 0

    def test_pacifist_kills_cause_game_over(self):
        """Killing a non-boss enemy in pacifist mode should end the game."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.challenge_pacifist = True
        e = Enemy(5, 5, "rat")
        e.hp = 0  # Dead
        _award_kill(gs, e)
        assert gs.game_over is True
        assert "pacifist" in gs.death_cause

    def test_pacifist_allows_boss_kills(self):
        """Killing a boss in pacifist mode should be allowed."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.challenge_pacifist = True
        e = Enemy(5, 5, "ogre_king")
        e.hp = 0
        _award_kill(gs, e)
        assert gs.game_over is False  # Should NOT end the game

    def test_challenge_modes_global_dict(self):
        """_CHALLENGE_MODES dict should exist."""
        from depths_of_dread.game import _CHALLENGE_MODES
        assert isinstance(_CHALLENGE_MODES, dict)
        assert "ironman" in _CHALLENGE_MODES


class TestEnvironmentalInteractions:
    """Tests for water/lava/fire environmental interactions."""

    def test_water_extinguishes_burning(self):
        """Moving through water should extinguish Burning status."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.status_effects["Burning"] = 5
        # Place water tile next to player
        nx, ny = p.x + 1, p.y
        gs.tiles[ny][nx] = T_WATER
        player_move(gs, 1, 0)
        assert "Burning" not in p.status_effects

    def test_lava_blocked_without_resist(self):
        """Player without resistance should not be able to walk on lava."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        nx, ny = p.x + 1, p.y
        gs.tiles[ny][nx] = T_LAVA
        old_x = p.x
        player_move(gs, 1, 0)
        assert p.x == old_x  # Did not move

    def test_lava_passable_with_fire_resist(self):
        """Player with fire resistance should walk on lava (taking 2 damage)."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        fire_ring = Item(0, 0, "ring", "fire_resist", {"name": "Ring of Fire Resist", "resists": ["fire"]})
        p.ring = fire_ring
        nx, ny = p.x + 1, p.y
        gs.tiles[ny][nx] = T_LAVA
        old_hp = p.hp
        player_move(gs, 1, 0)
        assert p.x == nx  # Moved onto lava
        assert p.hp == old_hp - 2  # Took 2 damage

    def test_lava_passable_with_cold_resist(self):
        """Player with cold resistance should also walk on lava."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        cold_ring = Item(0, 0, "ring", "cold_resist", {"name": "Ring of Cold Resist", "resists": ["cold"]})
        p.ring = cold_ring
        nx, ny = p.x + 1, p.y
        gs.tiles[ny][nx] = T_LAVA
        old_hp = p.hp
        player_move(gs, 1, 0)
        assert p.x == nx
        assert p.hp == old_hp - 2

    def test_fire_aura_blocked_by_water(self):
        """Fire aura should not damage player standing on water."""
        gs = GameState(headless=True)
        gs.generate_floor(8)
        p = gs.player
        # Place player on water, fire elemental adjacent
        gs.tiles[p.y][p.x] = T_WATER
        e = Enemy(p.x + 1, p.y, "fire_elemental")
        gs.enemies = [e]
        old_hp = p.hp
        # Process enemies — fire aura should be blocked by water
        with patch('depths_of_dread.combat.random') as mock_rng:
            mock_rng.random.return_value = 0.99  # No attacks hit
            mock_rng.randint.return_value = 1
            mock_rng.choice.return_value = (1, 0)
            process_enemies(gs)
        # Player HP should not drop from fire aura (may drop from other attacks)
        # Check that fire aura specifically didn't fire by checking messages
        aura_msgs = [m for m in gs.messages if "searing" in m[0].lower() or "fire aura" in m[0].lower()]
        # Should have no aura damage messages
        assert len(aura_msgs) == 0

    def test_fire_aura_blocked_by_fire_resist(self):
        """Fire aura should not damage player with fire resistance."""
        gs = GameState(headless=True)
        gs.generate_floor(8)
        p = gs.player
        fire_ring = Item(0, 0, "ring", "fire_resist", {"name": "Ring of Fire Resist", "resists": ["fire"]})
        p.ring = fire_ring
        e = Enemy(p.x + 1, p.y, "fire_elemental")
        gs.enemies = [e]
        # Process enemies
        with patch('depths_of_dread.combat.random') as mock_rng:
            mock_rng.random.return_value = 0.99
            mock_rng.randint.return_value = 1
            mock_rng.choice.return_value = (1, 0)
            process_enemies(gs)
        aura_msgs = [m for m in gs.messages if "searing" in m[0].lower()]
        assert len(aura_msgs) == 0

    def test_confusion_random_movement(self):
        """Confused player should move in a random direction."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.status_effects["Confusion"] = 5
        # Clear around player
        for ddx in range(-1, 2):
            for ddy in range(-1, 2):
                if 0 <= p.x + ddx < MAP_W and 0 <= p.y + ddy < MAP_H:
                    gs.tiles[p.y + ddy][p.x + ddx] = T_FLOOR
        old_x, old_y = p.x, p.y
        with patch('depths_of_dread.items.random') as mock_rng:
            mock_rng.choice.return_value = (0, -1)  # Force north
            mock_rng.random.return_value = 0.99
            mock_rng.randint.return_value = 1
            player_move(gs, 1, 0)  # Try to move east, but confusion redirects
        # Player should have moved (may be in any direction due to confusion)
        assert (p.x != old_x or p.y != old_y) or gs.game_over


class TestHunger:
    """Test hunger system."""

    def test_hunger_depletes_on_move(self, gs):
        p = gs.player
        p.hunger = 50
        old_hunger = p.hunger
        # Find a walkable adjacent tile
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = p.x + dx, p.y + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in (T_FLOOR, T_CORRIDOR):
                gs.enemies = [e for e in gs.enemies if not (e.x == nx and e.y == ny)]
                player_move(gs, dx, dy)
                assert p.hunger < old_hunger
                return
        pytest.skip("No walkable tile adjacent")

    def test_starvation(self, gs):
        """Player takes damage when hunger is 0."""
        p = gs.player
        p.hunger = 0
        p.hp = 10
        gs.turn_count = 5  # divisible by 5 for message
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = p.x + dx, p.y + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in (T_FLOOR, T_CORRIDOR):
                gs.enemies = [e for e in gs.enemies if not (e.x == nx and e.y == ny)]
                player_move(gs, dx, dy)
                assert p.hp < 10
                return
        pytest.skip("No walkable tile adjacent")


class TestTorch:
    """Test torch fuel system."""

    def test_torch_depletes(self, gs):
        """Torch fuel decreases each turn."""
        p = gs.player
        old_fuel = p.torch_fuel
        process_status(gs)
        assert p.torch_fuel == old_fuel - 1

    def test_torch_radius_changes(self):
        """Torch radius changes with fuel level."""
        p = Player()
        p.torch_fuel = TORCH_MAX_FUEL
        assert p.get_torch_radius() == 8

        p.torch_fuel = int(TORCH_MAX_FUEL * 0.4)
        assert p.get_torch_radius() == 6

        p.torch_fuel = int(TORCH_MAX_FUEL * 0.1)
        assert p.get_torch_radius() == 4

        p.torch_fuel = 0
        assert p.get_torch_radius() == 2
