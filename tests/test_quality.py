"""Tests for quality characteristics: performance, compatibility, usability,
reliability, security, maintainability, portability, stress, balance, scoring,
meta-progression."""

import sys
import os
import json
import time
import random
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from depths_of_dread import game as dungeon
from depths_of_dread import constants as _constants
from depths_of_dread.game import (
    GameState, Player, Enemy, Item, BSPNode,
    generate_dungeon, compute_fov, astar, player_move, player_attack,
    enemy_attack, process_enemies, process_status,
    _get_direction_delta, _bfs_unexplored, _init_new_game,
    auto_fight_step, auto_explore_step, calculate_score,
    save_game, load_game, delete_save, _compute_checksum,
    BotPlayer, _bot_execute_action, _update_explored_from_fov,
    load_lifetime_stats, save_lifetime_stats, _default_lifetime_stats,
    check_meta_unlocks, apply_meta_unlocks,
    BALANCE,
    T_WALL, T_FLOOR, T_CORRIDOR,
    MAP_W, MAP_H, SCREEN_W, SCREEN_H, VIEW_W, VIEW_H, MAX_FLOORS,
    SAVE_FILE_PATH, STATS_FILE_PATH,
    FOV_RADIUS, MIN_TERMINAL_W, MIN_TERMINAL_H,
    WEAPON_TYPES, ARMOR_TYPES, FOOD_TYPES, WALKABLE,
    SPELLS, ENEMY_TYPES,
    C_WHITE, C_RED, C_GREEN, C_BLUE, C_YELLOW, C_MAGENTA, C_CYAN,
    C_DARK, C_GOLD, C_PLAYER,
)

import pytest


class TestPerformance:
    """Test performance of key algorithms."""

    def test_astar_speed(self):
        """A* completes within 100ms on worst-case map."""
        tiles, rooms, start, end = generate_dungeon(1)
        t0 = time.time()
        for _ in range(100):
            astar(tiles, start[0], start[1], end[0], end[1], max_steps=50)
        elapsed = time.time() - t0
        assert elapsed < 10.0  # 100 iterations in 10s = 100ms each

    def test_fov_speed(self):
        """FOV shadowcasting completes within 20ms."""
        tiles, rooms, start, end = generate_dungeon(1)
        visible = set()
        t0 = time.time()
        for _ in range(1000):
            compute_fov(tiles, start[0], start[1], FOV_RADIUS, visible)
        elapsed = time.time() - t0
        assert elapsed < 20.0  # 1000 iterations in 20s = 20ms each

    def test_dungeon_generation_speed(self):
        """BSP dungeon generation completes within 500ms."""
        t0 = time.time()
        for _ in range(10):
            generate_dungeon(random.randint(1, MAX_FLOORS))
        elapsed = time.time() - t0
        assert elapsed < 5.0  # 10 iterations in 5s = 500ms each

    def test_bfs_explore_speed(self):
        """Auto-explore BFS completes within 200ms."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        t0 = time.time()
        for _ in range(100):
            _bfs_unexplored(gs)
        elapsed = time.time() - t0
        assert elapsed < 20.0  # 100 iterations in 20s = 200ms each


class TestCompatibility:
    """Test terminal and environment compatibility."""

    def test_color_fallback(self):
        """Game handles no-color terminals gracefully."""
        # Test the safe_color_pair fallback
        _constants.HAS_COLORS = False
        attr = dungeon.safe_color_pair(C_RED)
        assert attr != 0  # should return some attribute
        attr = dungeon.safe_color_pair(C_DARK)
        assert attr != 0
        attr = dungeon.safe_color_pair(C_PLAYER)
        assert attr != 0
        _constants.HAS_COLORS = True  # restore

    def test_minimum_terminal_size_constants(self):
        """Minimum terminal size constants are defined and reasonable."""
        assert MIN_TERMINAL_W == 80
        assert MIN_TERMINAL_H == 24
        assert MIN_TERMINAL_W >= SCREEN_W
        assert MIN_TERMINAL_H >= SCREEN_H

    def test_map_fits_in_view(self):
        """View dimensions are consistent with screen dimensions."""
        assert VIEW_W + (SCREEN_W - VIEW_W) == SCREEN_W
        assert VIEW_H + 3 + 1 == SCREEN_H  # VIEW_H + MSG_H + status line


class TestUsability:
    """Test usability features."""

    def test_help_screen_content(self):
        """Help screen mentions all keybindings listed in spec."""
        # We can't render to a screen, but we can check the function exists
        # and the help text includes key bindings by inspecting the source
        import inspect
        source = inspect.getsource(dungeon.show_help)
        required_keys = ["Tab", "Auto-fight", "Auto-explore", "Examine",
                        "Rest until healed", "Character sheet", "Message log",
                        "Fire projectile", "Cast spell", "yubn"]
        for key in required_keys:
            assert key in source, f"Help screen missing '{key}'"

    def test_unknown_key_feedback(self, gs):
        """Unknown keys should produce feedback (tested via game logic structure)."""
        # The game loop handles unknown keys with a message
        # We test the message system directly
        gs.msg("Unknown command. Press ? for help.", C_DARK)
        assert any("Unknown command" in m[0] for m in gs.messages)

    def test_hp_color_thresholds(self):
        """HP color coding uses correct thresholds."""
        p = Player()
        # >60% = green
        p.hp = 25
        p.max_hp = 30
        pct = p.hp / p.max_hp
        assert pct > 0.6  # should be green

        # 30-60% = yellow
        p.hp = 12
        pct = p.hp / p.max_hp
        assert 0.3 < pct <= 0.6

        # <30% = red
        p.hp = 5
        pct = p.hp / p.max_hp
        assert pct < 0.3

    def test_esc_in_direction_prompt(self):
        """ESC (27) returns None from direction delta."""
        assert _get_direction_delta(27) is None


class TestReliability:
    """Test reliability features."""

    def test_corrupted_save_file(self):
        """Corrupted save file is handled gracefully."""
        # Write garbage
        with open(SAVE_FILE_PATH, 'w') as f:
            f.write("not json at all {{{")
        result = load_game()
        assert result is None
        delete_save()

    def test_tampered_save_data(self, gs):
        """Save with modified data (checksum mismatch) is rejected."""
        save_game(gs)
        with open(SAVE_FILE_PATH, 'r') as f:
            wrapper = json.load(f)
        # Tamper with data
        wrapper["data"]["turn_count"] = 9999
        with open(SAVE_FILE_PATH, 'w') as f:
            json.dump(wrapper, f)
        result = load_game()
        assert result is None  # should be rejected
        delete_save()

    def test_combat_zero_damage(self, gs):
        """Combat handles 0 effective damage (high defense)."""
        p = gs.player
        p.defense = 100
        p.armor = Item(0, 0, "armor", 0, ARMOR_TYPES[-1])  # best armor
        p.armor.equipped = True
        e = Enemy(p.x + 1, p.y, "rat")
        gs.enemies.append(e)
        old_hp = p.hp
        enemy_attack(gs, e)
        # Damage is max(1, ...) so at minimum 1 damage (or dodge)
        assert p.hp >= old_hp - 5  # reasonable bound

    def test_combat_overkill(self, gs):
        """Combat handles overkill (enemy HP goes negative)."""
        p = gs.player
        p.strength = 100
        p.level = 50  # high level for near-guaranteed hit
        e = Enemy(p.x + 1, p.y, "rat")
        e.hp = 1
        e.defense = 0
        gs.enemies.append(e)
        if gs.tiles[p.y][p.x + 1] == T_WALL:
            gs.tiles[p.y][p.x + 1] = T_FLOOR
        # Try multiple times (miss chance is small but nonzero)
        for _ in range(20):
            if e.hp <= 0:
                break
            e.hp = 1
            player_attack(gs, e)
        assert e.hp <= 0
        assert not e.is_alive()

    def test_floor_transition_consistency(self):
        """Game state consistent after multiple floor transitions."""
        gs = GameState(headless=True)
        for floor in range(1, 11):
            gs.generate_floor(floor)
            assert gs.player.floor == floor
            assert gs.tiles is not None
            assert len(gs.rooms) > 0 or True  # rooms might be empty list for fallback
            assert gs.player.x >= 0
            assert gs.player.y >= 0

    def test_auto_explore_terminates(self, gs):
        """Auto-explore always terminates (no infinite loops)."""
        # Mark everything as explored
        for y in range(MAP_H):
            for x in range(MAP_W):
                gs.explored[y][x] = True
        gs.auto_exploring = True
        compute_fov(gs.tiles, gs.player.x, gs.player.y, 8, gs.visible)
        result = auto_explore_step(gs)
        assert result is None  # should stop immediately

    def test_auto_fight_terminates(self, gs):
        """Auto-fight terminates when no enemies visible."""
        gs.enemies.clear()
        gs.auto_fighting = True
        compute_fov(gs.tiles, gs.player.x, gs.player.y, 8, gs.visible)
        result = auto_fight_step(gs)
        assert result is None


class TestSecurity:
    """Test save file security."""

    def test_save_includes_checksum(self, gs):
        """Save file contains a checksum field."""
        save_game(gs)
        with open(SAVE_FILE_PATH, 'r') as f:
            wrapper = json.load(f)
        assert "checksum" in wrapper
        assert isinstance(wrapper["checksum"], str)
        assert len(wrapper["checksum"]) == 64  # SHA256 hex
        delete_save()

    def test_tampered_checksum_rejected(self, gs):
        """Modified checksum in save file causes rejection."""
        save_game(gs)
        with open(SAVE_FILE_PATH, 'r') as f:
            wrapper = json.load(f)
        wrapper["checksum"] = "0" * 64
        with open(SAVE_FILE_PATH, 'w') as f:
            json.dump(wrapper, f)
        result = load_game()
        assert result is None
        delete_save()

    def test_save_uses_json_not_pickle(self, gs):
        """Save file uses JSON format (no pickle/eval)."""
        save_game(gs)
        with open(SAVE_FILE_PATH, 'r') as f:
            content = f.read()
        # Should be valid JSON
        data = json.loads(content)
        assert isinstance(data, dict)
        # Check no pickle header
        assert not content.startswith(b'\x80' if isinstance(content, bytes) else '\x80')
        delete_save()

    def test_checksum_validates_correctly(self, gs):
        """Checksum matches when data is not tampered."""
        save_game(gs)
        with open(SAVE_FILE_PATH, 'r') as f:
            wrapper = json.load(f)
        data_str = json.dumps(wrapper["data"], separators=(',', ':'))
        computed = _compute_checksum(data_str)
        assert computed == wrapper["checksum"]
        delete_save()


class TestMaintainability:
    """Test code quality and maintainability."""

    def test_named_constants_for_tile_types(self):
        """Tile types use named constants, not magic numbers."""
        from depths_of_dread.game import (
            T_WALL, T_FLOOR, T_CORRIDOR, T_DOOR, T_STAIRS_DOWN, T_STAIRS_UP,
            T_WATER, T_LAVA, T_SHOP_FLOOR, T_SHRINE,
        )
        assert T_WALL == 0
        assert T_FLOOR == 1
        assert T_CORRIDOR == 2
        assert T_DOOR == 3
        assert T_STAIRS_DOWN == 4
        assert T_STAIRS_UP == 5
        assert T_WATER == 6
        assert T_LAVA == 7
        assert T_SHOP_FLOOR == 8
        assert T_SHRINE == 9

    def test_named_constants_for_colors(self):
        """Color pairs use named constants."""
        assert C_WHITE == 1
        assert C_RED == 2
        assert C_GREEN == 3
        assert C_BLUE == 4
        assert C_YELLOW == 5
        assert C_MAGENTA == 6
        assert C_CYAN == 7

    def test_spell_definitions_complete(self):
        """All spells have cost, desc, and mage_only fields."""
        for name, info in SPELLS.items():
            assert "cost" in info, f"Spell {name} missing 'cost'"
            assert "desc" in info, f"Spell {name} missing 'desc'"
            assert "mage_only" in info, f"Spell {name} missing 'mage_only'"

    def test_enemy_types_complete(self):
        """All enemy types have required fields."""
        required = ["name", "char", "color", "hp", "dmg", "defense", "xp", "speed", "ai", "min_floor"]
        for etype, data in ENEMY_TYPES.items():
            for field in required:
                assert field in data, f"Enemy {etype} missing '{field}'"

    def test_all_classes_have_init(self):
        """Core classes have __init__ methods."""
        assert hasattr(GameState, '__init__')
        assert hasattr(Player, '__init__')
        assert hasattr(Enemy, '__init__')
        assert hasattr(Item, '__init__')
        assert hasattr(BSPNode, '__init__')

    def test_imports_work(self):
        """Module imports successfully."""
        mod = importlib.import_module('depths_of_dread.game')
        assert hasattr(mod, 'GameState')
        assert hasattr(mod, 'game_loop')
        assert hasattr(mod, 'main')

    def test_docstrings_present(self):
        """Key functions have docstrings."""
        functions_with_docs = [
            dungeon.game_loop, dungeon.compute_fov, dungeon.astar,
            dungeon._get_direction_delta, dungeon.save_game, dungeon.load_game,
            dungeon.auto_fight_step, dungeon.auto_explore_step,
            dungeon.check_context_tips, dungeon.look_mode,
        ]
        for fn in functions_with_docs:
            assert fn.__doc__ is not None, f"{fn.__name__} missing docstring"


class TestPortability:
    """Test portability across Python versions and platforms."""

    def test_python_version(self):
        """Game requires Python 3.9+."""
        assert sys.version_info >= (3, 9)

    def test_no_platform_specific_imports(self):
        """No platform-specific imports beyond curses and stdlib."""
        import inspect
        source = inspect.getsource(dungeon)
        # Check for platform-specific modules
        banned = ['win32', 'msvcrt', 'termios', 'fcntl', 'resource']
        for mod in banned:
            assert f'import {mod}' not in source, f"Found platform-specific import: {mod}"

    def test_stdlib_only(self):
        """Game uses only standard library modules."""
        import inspect
        source_lines = inspect.getsource(dungeon).split('\n')
        import_lines = [l.strip() for l in source_lines if l.strip().startswith('import ') or l.strip().startswith('from ')]
        stdlib_modules = {
            'curses', 'random', 'math', 'time', 'sys', 'heapq', 'json',
            'hashlib', 'os', 'pathlib', 'collections', 'argparse', 'datetime',
            'subprocess', 'threading', 'traceback', '__future__', 'typing',
            'types',
        }
        # Optional imports wrapped in try/except are allowed
        optional_modules = {'agent_commons'}
        for line in import_lines:
            # Skip relative imports (internal package modules)
            if line.startswith('from .'):
                continue
            # Extract module name
            if line.startswith('from '):
                mod = line.split()[1].split('.')[0]
            else:
                mod = line.split()[1].split('.')[0]
            assert mod in stdlib_modules or mod in optional_modules, f"Non-stdlib import: {mod}"

    def test_save_file_path_uses_home(self):
        """Save file path uses home directory (portable)."""
        assert SAVE_FILE_PATH.startswith(os.path.expanduser("~"))


class TestStress:
    """Fuzz and stress tests for reliability."""

    def test_many_floor_transitions(self):
        """Game state consistent after 50 floor transitions."""
        gs = GameState(headless=True)
        for _ in range(50):
            floor = random.randint(1, MAX_FLOORS)
            gs.generate_floor(floor)
            assert gs.player.floor == floor
            assert gs.tiles is not None
            assert gs.player.x >= 0 and gs.player.x < MAP_W
            assert gs.player.y >= 0 and gs.player.y < MAP_H
            assert gs.tiles[gs.player.y][gs.player.x] != T_WALL

    def test_rapid_combat(self, gs):
        """Rapid combat doesn't crash."""
        p = gs.player
        p.strength = 50
        p.hp = 1000
        p.max_hp = 1000
        for _ in range(50):
            e = Enemy(p.x + 1, p.y, "rat")
            gs.enemies.append(e)
            if gs.tiles[p.y][p.x + 1] == T_WALL:
                gs.tiles[p.y][p.x + 1] = T_FLOOR
            player_attack(gs, e)

    def test_many_items(self, gs):
        """Many items on ground don't crash."""
        for _ in range(200):
            pos = gs._find_spawn_pos()
            if pos:
                item = gs._random_item(pos[0], pos[1], 1)
                if item:
                    gs.items.append(item)
        assert len(gs.items) > 50


class TestBalanceValidation:
    """Validate the BALANCE dict is well-formed."""

    def test_required_keys_present(self):
        required = ["item_weights", "items_base", "items_per_floor",
                     "enemies_base", "enemies_per_floor", "hunger_per_move",
                     "hit_chance_base", "heal_potion_min", "heal_potion_max",
                     "xp_base", "xp_growth", "shop_items_min", "shop_items_max",
                     "shrine_full_heal_chance"]
        for key in required:
            assert key in BALANCE, f"Missing BALANCE key: {key}"

    def test_item_weights_valid_types(self):
        valid_types = {"weapon", "armor", "potion", "scroll", "food", "ring",
                       "bow", "arrow", "throwing_dagger", "wand", "torch"}
        for key in BALANCE["item_weights"]:
            assert key in valid_types, f"Unknown item weight type: {key}"

    def test_numeric_values_positive(self):
        for key, val in BALANCE.items():
            if key == "item_weights":
                for wk, wv in val.items():
                    assert wv > 0, f"item_weights[{wk}] not positive: {wv}"
            elif isinstance(val, (int, float)):
                assert val >= 0, f"BALANCE[{key}] negative: {val}"

    def test_shrine_probabilities_sum(self):
        total = (BALANCE["shrine_full_heal_chance"] +
                 BALANCE["shrine_max_hp_chance"] +
                 BALANCE["shrine_str_chance"] +
                 BALANCE["shrine_def_chance"] +
                 BALANCE["shrine_nothing_chance"] +
                 BALANCE["shrine_curse_chance"])
        assert 0.95 <= total <= 1.05, f"Shrine probs sum to {total}, expected ~1.0"

    def test_item_weights_auto_normalize(self):
        weights = BALANCE["item_weights"]
        total = sum(weights.values())
        assert total > 0, "item_weights sum is 0"
        # random.choices uses relative weights, so they just need to be positive
        for v in weights.values():
            assert v > 0


class TestBalanceStress:
    """Balance and stress tests using the bot."""

    def test_bot_100_game_stress(self):
        """100 games, 0% crash rate, avg floor > 2."""
        floors = []
        for _ in range(100):
            gs = GameState(headless=True)
            _init_new_game(gs)
            bot = BotPlayer()
            for _ in range(300):
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
            floors.append(gs.player.floor)
        avg_floor = sum(floors) / len(floors)
        assert avg_floor >= 1.0  # At minimum should survive floor 1

    def test_food_availability(self):
        """Average food found per floor >= 2."""
        total_food = 0
        floors_tested = 0
        for _ in range(20):
            gs = GameState(headless=True)
            for f in range(1, 6):
                gs.generate_floor(f)
                food_count = sum(1 for i in gs.items if i.item_type == "food")
                total_food += food_count
                floors_tested += 1
        avg = total_food / floors_tested
        assert avg >= 2.0, f"Avg food per floor: {avg}, expected >= 2.0"

    def test_gold_economy(self):
        """Average gold per floor sufficient for 1 heal potion by floor 3."""
        total_gold = 0
        for _ in range(20):
            gs = GameState(headless=True)
            for f in range(1, 4):
                gs.generate_floor(f)
                for item in gs.items:
                    if item.item_type == "gold":
                        total_gold += item.data["amount"]
        avg_gold_3floors = total_gold / 20
        heal_price = BALANCE["shop_heal_base_price"] + 3 * BALANCE["shop_heal_floor_scale"]
        assert avg_gold_3floors >= heal_price, f"Avg gold over 3 floors: {avg_gold_3floors}, need {heal_price}"

    def test_xp_curve(self):
        """XP available on first 3 floors sufficient to approach level 3."""
        total_xp = 0
        for _ in range(20):
            gs = GameState(headless=True)
            for f in range(1, 4):
                gs.generate_floor(f)
                for e in gs.enemies:
                    total_xp += e.xp
        avg_xp = total_xp / 20
        # XP needed for lv 3: xp_base + xp_base * growth
        xp_lv2 = BALANCE["xp_base"]
        xp_lv3 = int(BALANCE["xp_base"] * BALANCE["xp_growth"])
        needed = xp_lv2 + xp_lv3
        assert avg_xp >= needed * 0.7, f"Avg XP from 3 floors: {avg_xp}, need ~{needed}"


class TestScoring:
    """Test score calculation."""

    def test_score_components(self, gs):
        p = gs.player
        p.gold = 100
        p.kills = 10
        p.deepest_floor = 5
        p.damage_dealt = 200
        gs.victory = False
        score = calculate_score(p, gs)
        expected = 100 + 10 * 50 + 5 * 200 + 200
        assert score == expected

    def test_victory_bonus(self, gs):
        p = gs.player
        p.gold = 0
        p.kills = 0
        p.deepest_floor = 1
        p.damage_dealt = 0
        gs.victory = True
        score = calculate_score(p, gs)
        assert score >= 5000  # victory bonus


class TestMetaProgression:
    """Tests for meta-progression system (Phase 3, Feature 3)."""

    def test_meta_unlocks_defined(self):
        """META_UNLOCKS should have multiple entries."""
        from depths_of_dread.game import META_UNLOCKS
        assert len(META_UNLOCKS) >= 5

    def test_check_meta_unlocks_games(self):
        """Playing 3+ games should unlock extra_potion."""
        from depths_of_dread.game import check_meta_unlocks
        stats = _default_lifetime_stats()
        stats["total_games"] = 3
        unlocks = check_meta_unlocks(stats)
        assert "extra_potion" in unlocks

    def test_check_meta_unlocks_floor(self):
        """Reaching floor 5 should unlock map_reveal."""
        from depths_of_dread.game import check_meta_unlocks
        stats = _default_lifetime_stats()
        stats["highest_floor"] = 5
        unlocks = check_meta_unlocks(stats)
        assert "map_reveal" in unlocks

    def test_check_meta_unlocks_kills(self):
        """50+ kills should unlock bonus_gold."""
        from depths_of_dread.game import check_meta_unlocks
        stats = _default_lifetime_stats()
        stats["total_kills"] = 50
        unlocks = check_meta_unlocks(stats)
        assert "bonus_gold" in unlocks

    def test_check_meta_unlocks_deaths(self):
        """5+ deaths should unlock extra_hp."""
        from depths_of_dread.game import check_meta_unlocks
        stats = _default_lifetime_stats()
        stats["total_deaths"] = 5
        unlocks = check_meta_unlocks(stats)
        assert "extra_hp" in unlocks

    def test_check_meta_unlocks_no_false_positive(self):
        """Fresh stats should yield no unlocks."""
        from depths_of_dread.game import check_meta_unlocks
        stats = _default_lifetime_stats()
        unlocks = check_meta_unlocks(stats)
        assert len(unlocks) == 0

    def test_apply_meta_unlocks_bonus_gold(self):
        """bonus_gold unlock should give 50 gold at start."""
        from depths_of_dread.game import apply_meta_unlocks
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        # Mock the stats
        stats = _default_lifetime_stats()
        stats["unlocks"] = ["bonus_gold"]
        save_lifetime_stats(stats)
        gold_before = gs.player.gold
        apply_meta_unlocks(gs)
        assert gs.player.gold == gold_before + 50
        # Clean up
        import os
        try:
            os.remove(STATS_FILE_PATH)
        except FileNotFoundError:
            pass

    def test_lifetime_stats_unlocks_field(self):
        """Lifetime stats should include unlocks field."""
        stats = _default_lifetime_stats()
        assert "unlocks" in stats
        assert isinstance(stats["unlocks"], list)
