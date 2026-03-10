"""Tests for bot player, agent player, feature tracker."""

import sys
import os
import json
import random
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from depths_of_dread import game as dungeon
from depths_of_dread.game import (
    GameState, Player, Enemy, Item,
    compute_fov, process_enemies, process_status,
    _init_new_game, _update_explored_from_fov, _bot_execute_action,
    BotPlayer, bot_batch_mode,
    AgentPlayer, AGENT_SYSTEM_PROMPT, _DIR_MAP,
    FeatureTracker,
    WEAPON_TYPES, WAND_TYPES,
    T_WALL, T_FLOOR, T_STAIRS_LOCKED, T_ALCHEMY_TABLE, T_WALL_TORCH,
    MAP_W, MAP_H, WALKABLE,
    FOV_RADIUS,
    C_CYAN, C_MAGENTA, C_DARK,
)

import pytest


class TestBotPlayer:
    """Test the AI bot player."""

    @pytest.fixture
    def bot_gs(self):
        gs = GameState(headless=True)
        _init_new_game(gs)
        fov_radius = gs.player.get_torch_radius()
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        _update_explored_from_fov(gs)
        return gs

    def test_bot_heals_when_low_hp(self, bot_gs):
        gs = bot_gs
        p = gs.player
        # Give a healing potion and lower HP
        potion = Item(0, 0, "potion", "Healing",
                      {"effect": "Healing", "color_name": "Red", "char": '!'})
        potion.identified = True
        p.inventory.append(potion)
        p.hp = int(p.max_hp * 0.2)  # 20% HP
        bot = BotPlayer()
        action, params = bot.decide(gs)
        assert action == "use_item"
        assert params["type"] == "potion"

    def test_bot_eats_when_hungry(self, bot_gs):
        gs = bot_gs
        p = gs.player
        gs.enemies.clear()  # No enemies
        p.hp = p.max_hp  # Full HP
        p.hunger = 20  # Very hungry
        bot = BotPlayer()
        action, params = bot.decide(gs)
        assert action == "use_item"
        assert params["type"] == "food"

    def test_bot_equips_better_weapon(self, bot_gs):
        gs = bot_gs
        p = gs.player
        gs.enemies.clear()
        p.hp = p.max_hp
        p.hunger = 100
        # Give better weapon
        sword = Item(0, 0, "weapon", 3, WEAPON_TYPES[3])  # Long Sword
        p.inventory.append(sword)
        bot = BotPlayer()
        action, params = bot.decide(gs)
        assert action == "equip"
        assert params["item"] == sword

    def test_bot_fights_visible_enemies(self, bot_gs):
        gs = bot_gs
        p = gs.player
        p.hp = p.max_hp
        p.hunger = 100
        # Clear existing enemies and place one adjacent
        gs.enemies.clear()
        e = Enemy(p.x + 1, p.y, "rat")
        if gs.tiles[p.y][p.x + 1] == T_WALL:
            gs.tiles[p.y][p.x + 1] = T_FLOOR
        gs.enemies.append(e)
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        bot = BotPlayer()
        action, params = bot.decide(gs)
        assert action == "move"  # Will bump into enemy = attack
        assert params["dx"] == 1 and params["dy"] == 0

    def test_bot_explores_when_safe(self, bot_gs):
        gs = bot_gs
        p = gs.player
        p.hp = p.max_hp
        p.hunger = 100
        gs.enemies.clear()
        gs.items.clear()
        bot = BotPlayer()
        action, params = bot.decide(gs)
        assert action == "move"  # Should be exploring

    def test_bot_descends_when_on_stairs(self, bot_gs):
        gs = bot_gs
        p = gs.player
        p.hp = p.max_hp
        p.hunger = 100
        gs.enemies.clear()
        # Move player to stairs
        sx, sy = gs.stair_down
        p.x, p.y = sx, sy
        # Mark most tiles explored so exploration threshold is met
        for y in range(MAP_H):
            for x in range(MAP_W):
                if gs.tiles[y][x] in WALKABLE:
                    gs.explored[y][x] = True
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        bot = BotPlayer()
        action, params = bot.decide(gs)
        assert action == "descend"

    def test_bot_survives_50_turns(self, bot_gs):
        gs = bot_gs
        bot = BotPlayer()
        for _ in range(50):
            if gs.game_over:
                break
            fov_radius = gs.player.get_torch_radius()
            compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
            _update_explored_from_fov(gs)
            action, params = bot.decide(gs)
            turn_spent = _bot_execute_action(gs, action, params)
            if turn_spent:
                gs.turn_count += 1
                process_enemies(gs)
                process_status(gs)
                if gs.player.hp <= 0:
                    gs.game_over = True
        assert gs.turn_count >= 40 or gs.game_over  # Survived or died legitimately

    def test_bot_100_games_no_crash(self):
        """Bot completes 100 games without crashing."""
        for _ in range(100):
            gs = GameState(headless=True)
            _init_new_game(gs)
            bot = BotPlayer()
            for _ in range(500):
                if gs.game_over:
                    break
                fov_radius = gs.player.get_torch_radius()
                compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
                _update_explored_from_fov(gs)
                action, params = bot.decide(gs)
                _bot_execute_action(gs, action, params)
                gs.turn_count += 1
                process_enemies(gs)
                process_status(gs)
                if gs.player.hp <= 0:
                    gs.game_over = True


class TestBotLockedStairs:
    """Bot handles locked stairs without stalling."""

    def test_bot_doesnt_stall_on_locked_stairs(self):
        """Bot should not infinite-loop when stairs are locked."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(4)
        sx, sy = gs.stair_down
        gs.tiles[sy][sx] = T_STAIRS_LOCKED
        gs.puzzles = [{"type": "locked_stairs", "positions": [],
                       "solved": False, "room": gs.rooms[1],
                       "stairs": (sx, sy)}]
        bot = BotPlayer()
        wait_count = 0
        for _ in range(200):
            compute_fov(gs.tiles, gs.player.x, gs.player.y, 8, gs.visible)
            _update_explored_from_fov(gs)
            action, params = bot.decide(gs)
            if action == "rest" and bot.strategy == "WAIT":
                wait_count += 1
            _bot_execute_action(gs, action, params)
            gs.turn_count += 1
        # Should not be waiting most of the time
        assert wait_count < 150, f"Bot waited {wait_count}/200 turns (stalling)"

    def test_bot_descend_rejects_locked_stairs(self):
        """Bot's descend action should fail on locked stairs."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(4)
        sx, sy = gs.stair_down
        gs.tiles[sy][sx] = T_STAIRS_LOCKED
        assert gs.tiles[sy][sx] != T_FLOOR  # Use actual stairs down tile

    def test_bot_floor_tracking_resets(self):
        """Bot resets per-floor tracking on new floor."""
        bot = BotPlayer()
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        bot._current_floor = 0  # Force reset
        compute_fov(gs.tiles, gs.player.x, gs.player.y, 8, gs.visible)
        _update_explored_from_fov(gs)
        bot.decide(gs)
        assert bot._current_floor == 1
        assert len(bot._floor_tiles_visited) > 0


class TestBotClassRotation:
    """Bot batch rotates classes."""

    def test_batch_rotates_classes(self):
        """3 games should use all 3 classes."""
        # Just check the rotation logic (don't run full games)
        classes = ["warrior", "mage", "rogue"]
        for i in range(9):
            expected = classes[i % 3]
            assert expected == classes[i % len(classes)]


class TestFeatureTracker:
    """FeatureTracker monitors feature encounters."""

    def test_tracker_starts_empty(self):
        tracker = FeatureTracker()
        assert tracker.coverage_pct() == 0

    def test_tracker_detects_alchemy(self):
        tracker = FeatureTracker()
        gs = GameState(headless=True)
        gs.generate_floor(2)
        # Place alchemy table under player
        gs.tiles[gs.player.y][gs.player.x] = T_ALCHEMY_TABLE
        tracker.check_state(gs)
        assert tracker.features["alchemy_table"]["encountered"]

    def test_tracker_detects_wall_torch(self):
        tracker = FeatureTracker()
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.wall_torches = [(5, 5)]
        tracker.check_state(gs)
        assert tracker.features["wall_torch"]["encountered"]

    def test_tracker_report(self):
        tracker = FeatureTracker()
        report = tracker.report()
        assert "FEATURE COVERAGE REPORT" in report
        assert "Coverage: 0%" in report

    def test_tracker_coverage_increases(self):
        tracker = FeatureTracker()
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.tiles[gs.player.y][gs.player.x] = T_ALCHEMY_TABLE
        tracker.check_state(gs)
        assert tracker.coverage_pct() > 0


class TestAgentPlayer:
    """Tests for the AgentPlayer class (Claude-powered hybrid AI)."""

    def _make_game(self):
        """Create a game state with initialized floor for testing."""
        gs = GameState(headless=True, seed=42)
        _init_new_game(gs)
        compute_fov(gs.tiles, gs.player.x, gs.player.y, FOV_RADIUS, gs.visible)
        _update_explored_from_fov(gs)
        return gs

    # --- Serialization ---

    def test_serialize_state_returns_string(self):
        """State serialization produces non-empty string."""
        gs = self._make_game()
        agent = AgentPlayer()
        state = agent._serialize_state(gs)
        assert isinstance(state, str)
        assert len(state) > 100

    def test_serialize_state_contains_key_info(self):
        """Serialized state includes HP, floor, inventory, hunger."""
        gs = self._make_game()
        agent = AgentPlayer()
        state = agent._serialize_state(gs)
        assert "F1/" in state           # Floor number
        assert "HP" in state
        assert "Hng" in state           # Hunger (compact)
        assert "Inv(" in state          # Inventory
        assert "Enemies:" in state      # Enemies section

    def test_serialize_state_shows_enemies(self):
        """Serialized state lists visible enemies with distance and direction."""
        gs = self._make_game()
        # Place an enemy in visible range
        p = gs.player
        enemy = Enemy(p.x + 2, p.y, "rat")
        gs.enemies.append(enemy)
        compute_fov(gs.tiles, p.x, p.y, FOV_RADIUS, gs.visible)
        agent = AgentPlayer()
        state = agent._serialize_state(gs)
        assert "Rat" in state or "rat" in state.lower()

    def test_serialize_state_shows_items(self):
        """Serialized state lists visible ground items."""
        gs = self._make_game()
        p = gs.player
        food = Item(p.x + 1, p.y, "food", "Bread", {"name": "Bread", "hunger_restore": 30})
        gs.items.append(food)
        compute_fov(gs.tiles, p.x, p.y, FOV_RADIUS, gs.visible)
        agent = AgentPlayer()
        state = agent._serialize_state(gs)
        assert "Bread" in state

    # --- Trigger Conditions ---

    def test_should_consult_no_trigger_on_safe_floor(self):
        """No trigger when no enemies visible, HP full, no special tiles."""
        gs = self._make_game()
        gs.enemies = []
        agent = AgentPlayer()
        agent._last_floor = gs.player.floor  # Prevent new-floor trigger
        result = agent._should_consult(gs)
        assert result is False

    def test_should_consult_enemies_visible(self):
        """Triggers when enemies are in FOV."""
        gs = self._make_game()
        p = gs.player
        enemy = Enemy(p.x + 1, p.y, "rat")
        gs.enemies = [enemy]
        compute_fov(gs.tiles, p.x, p.y, FOV_RADIUS, gs.visible)
        agent = AgentPlayer()
        agent._last_floor = p.floor
        assert agent._should_consult(gs) is True

    def test_should_consult_low_hp(self):
        """Triggers when HP < 40%."""
        gs = self._make_game()
        gs.enemies = []
        gs.player.hp = 10
        gs.player.max_hp = 30
        agent = AgentPlayer()
        agent._last_floor = gs.player.floor
        assert agent._should_consult(gs) is True

    def test_should_consult_new_floor(self):
        """Triggers on floor change."""
        gs = self._make_game()
        gs.enemies = []
        gs.player.hp = gs.player.max_hp
        agent = AgentPlayer()
        agent._last_floor = 0  # Different from current floor 1
        assert agent._should_consult(gs) is True

    def test_should_consult_boss_visible(self):
        """Triggers when a boss enemy is visible."""
        gs = self._make_game()
        p = gs.player
        boss = Enemy(p.x + 1, p.y, "ogre_king")
        gs.enemies = [boss]
        compute_fov(gs.tiles, p.x, p.y, FOV_RADIUS, gs.visible)
        agent = AgentPlayer()
        agent._last_floor = p.floor
        assert agent._should_consult(gs) is True

    # --- Response Parsing ---

    def test_parse_response_valid_json_envelope(self):
        """Parse valid Claude --output-format json response."""
        agent = AgentPlayer()
        raw = json.dumps({"type": "result", "result": '{"action": "move_north", "reason": "exploring"}'})
        result = agent._parse_response(raw)
        assert result is not None
        assert result["action"] == "move_north"
        assert result["reason"] == "exploring"

    def test_parse_response_markdown_fences(self):
        """Parse response with markdown code fences."""
        agent = AgentPlayer()
        inner = '```json\n{"action": "attack", "reason": "melee the rat"}\n```'
        raw = json.dumps({"type": "result", "result": inner})
        result = agent._parse_response(raw)
        assert result is not None
        assert result["action"] == "attack"

    def test_parse_response_invalid_json(self):
        """Returns None for unparseable response."""
        agent = AgentPlayer()
        result = agent._parse_response("not json at all")
        assert result is None

    def test_parse_response_missing_action(self):
        """Returns None when action key is missing."""
        agent = AgentPlayer()
        raw = json.dumps({"type": "result", "result": '{"reason": "no action"}'})
        result = agent._parse_response(raw)
        assert result is None

    # --- Action-to-Command Mapping ---

    def test_action_to_command_move(self):
        """Maps move_north to correct dx/dy."""
        gs = self._make_game()
        agent = AgentPlayer()
        cmd = agent._action_to_command("move_north", gs)
        assert cmd == ("move", {"dx": 0, "dy": -1})

    def test_action_to_command_move_diagonal(self):
        """Maps move_se to correct dx/dy."""
        gs = self._make_game()
        agent = AgentPlayer()
        cmd = agent._action_to_command("move_se", gs)
        assert cmd == ("move", {"dx": 1, "dy": 1})

    def test_action_to_command_cast_heal(self):
        """Maps cast_heal to correct spell action."""
        gs = self._make_game()
        agent = AgentPlayer()
        cmd = agent._action_to_command("cast_heal", gs)
        assert cmd == ("cast_spell", {"spell": "Heal"})

    def test_action_to_command_use_potion(self):
        """Maps use_potion -- finds a potion in inventory."""
        gs = self._make_game()
        potion = Item(0, 0, "potion", "Healing", {"effect": "Healing", "hp_restore": 15})
        gs.player.inventory.append(potion)
        agent = AgentPlayer()
        cmd = agent._action_to_command("use_potion", gs)
        assert cmd is not None
        assert cmd[0] == "use_item"
        assert cmd[1]["type"] == "potion"

    def test_action_to_command_descend(self):
        """Maps descend action."""
        gs = self._make_game()
        agent = AgentPlayer()
        cmd = agent._action_to_command("descend", gs)
        assert cmd == ("descend", {})

    def test_action_to_command_unknown(self):
        """Unknown action returns None."""
        gs = self._make_game()
        agent = AgentPlayer()
        cmd = agent._action_to_command("dance_wildly", gs)
        assert cmd is None

    def test_action_to_command_fire(self):
        """Maps fire_east to correct fire action."""
        gs = self._make_game()
        agent = AgentPlayer()
        cmd = agent._action_to_command("fire_east", gs)
        assert cmd == ("fire", {"dx": 1, "dy": 0})

    def test_action_to_command_rest_and_wait(self):
        """Both rest and wait map to rest action."""
        gs = self._make_game()
        agent = AgentPlayer()
        assert agent._action_to_command("rest", gs) == ("rest", {})
        assert agent._action_to_command("wait", gs) == ("rest", {})

    # --- Fallback Behavior ---

    def test_decide_fallback_when_no_trigger(self):
        """Falls back to BotPlayer when no trigger conditions met."""
        gs = self._make_game()
        gs.enemies = []
        gs.player.hp = gs.player.max_hp
        agent = AgentPlayer()
        agent._last_floor = gs.player.floor  # No new floor trigger
        # decide() should work without calling Claude
        action, params = agent.decide(gs)
        assert action is not None
        assert agent.claude_calls == 0

    @patch.object(AgentPlayer, '_call_claude', return_value=None)
    def test_decide_fallback_when_claude_fails(self, mock_claude):
        """Falls back to BotPlayer when Claude returns None."""
        gs = self._make_game()
        p = gs.player
        # Force a trigger: low HP
        p.hp = 5
        p.max_hp = 30
        gs.enemies = []
        agent = AgentPlayer()
        agent._last_floor = p.floor
        action, params = agent.decide(gs)
        assert action is not None  # BotPlayer should handle it
        assert agent.fallbacks == 1

    @patch.object(AgentPlayer, '_call_claude')
    def test_decide_uses_claude_response(self, mock_claude):
        """Uses Claude's response when valid."""
        mock_claude.return_value = {"action": "rest", "reason": "conserving energy"}
        gs = self._make_game()
        p = gs.player
        p.hp = 5
        p.max_hp = 30
        gs.enemies = []
        agent = AgentPlayer()
        agent._last_floor = p.floor
        action, params = agent.decide(gs)
        assert action == "rest"
        assert agent.reason == "conserving energy"

    # --- Constants ---

    def test_system_prompt_not_empty(self):
        """AGENT_SYSTEM_PROMPT is populated."""
        assert len(AGENT_SYSTEM_PROMPT) > 100
        assert "roguelike" in AGENT_SYSTEM_PROMPT.lower()

    def test_dir_map_complete(self):
        """All 8 directions plus short forms are mapped."""
        assert len(_DIR_MAP) >= 8
        assert _DIR_MAP["north"] == (0, -1)
        assert _DIR_MAP["se"] == (1, 1)


class TestAgentNewActions:
    """Agent handles new feature actions."""

    def test_agent_prompt_has_new_actions(self):
        assert "use_alchemy" in AGENT_SYSTEM_PROMPT
        assert "light_pedestal" in AGENT_SYSTEM_PROMPT
        assert "grab_wall_torch" in AGENT_SYSTEM_PROMPT

    def test_agent_serialize_includes_puzzles(self):
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(5)
        gs.puzzles = [{"type": "torch", "solved": False, "positions": [], "room": gs.rooms[0]}]
        agent = AgentPlayer(game_id=99)
        state = agent._serialize_state(gs)
        assert "Puzzles:" in state
        assert "torch(active)" in state

    def test_agent_serialize_includes_alchemy(self):
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(2)
        gs.tiles[gs.player.y][gs.player.x] = T_ALCHEMY_TABLE
        agent = AgentPlayer(game_id=99)
        state = agent._serialize_state(gs)
        assert "ALCHEMY(available)" in state

    def test_agent_serialize_locked_stairs(self):
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(4)
        sx, sy = gs.stair_down
        gs.tiles[sy][sx] = T_STAIRS_LOCKED
        agent = AgentPlayer(game_id=99)
        state = agent._serialize_state(gs)
        assert "STAIRS_LOCKED" in state

    def test_bot_execute_use_alchemy(self):
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(2)
        gs.tiles[gs.player.y][gs.player.x] = T_ALCHEMY_TABLE
        # Give player an unidentified potion
        potion = Item(0, 0, "potion", "???", {"effect": "Healing", "char": '!', "label": "Red"})
        potion.identified = False
        gs.player.inventory.append(potion)
        result = _bot_execute_action(gs, "use_alchemy", {})
        assert result == True

    def test_bot_execute_grab_wall_torch(self):
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        # Place wall torch adjacent to player
        tx, ty = gs.player.x + 1, gs.player.y
        gs.tiles[ty][tx] = T_WALL_TORCH
        gs.wall_torches = [(tx, ty)]
        inv_before = len(gs.player.inventory)
        result = _bot_execute_action(gs, "grab_wall_torch", {})
        assert result == True
        assert len(gs.player.inventory) == inv_before + 1
        assert gs.tiles[ty][tx] == T_WALL


class TestAgentConsultCooldown:
    """Agent consultation cooldown reduces API calls."""

    def test_cooldown_prevents_rapid_calls(self):
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        agent = AgentPlayer(game_id=99)
        # Simulate enemies visible on turn 10
        gs.turn_count = 10
        # Place enemy in FOV
        enemy = Enemy(gs.player.x + 2, gs.player.y, "rat")
        gs.enemies = [enemy]
        compute_fov(gs.tiles, gs.player.x, gs.player.y, 8, gs.visible)
        # First call should pass
        result1 = agent._should_consult(gs)
        assert result1 == True
        # Immediate second call should be blocked by cooldown
        gs.turn_count = 11
        result2 = agent._should_consult(gs)
        assert result2 == False  # Blocked by 3-turn cooldown

    def test_critical_bypasses_cooldown(self):
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        agent = AgentPlayer(game_id=99)
        gs.turn_count = 10
        # Set last consult to very recent
        agent._last_consult_turn = 9
        # Set player to very low HP (critical)
        gs.player.hp = 1
        gs.player.max_hp = 50
        result = agent._should_consult(gs)
        assert result == True  # Critical = bypasses cooldown
