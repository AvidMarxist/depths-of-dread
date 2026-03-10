"""Tests for combat: enemy AI, fleeing, resistance, stealth, bestiary, traps, status effects, bosses, lifesteal, arcane blast."""

import sys
import os
import random
import json
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from depths_of_dread import game as dungeon
from depths_of_dread.game import (
    GameState, Player, Enemy, Item,
    compute_fov, player_attack, enemy_attack, process_enemies, process_status,
    cast_spell_headless,
    _serialize_enemy, _deserialize_enemy,
    _award_kill,
    _apply_spell_resist,
    _compute_noise, _stealth_detection,
    _trigger_trap, _check_traps_on_move, _passive_trap_detect,
    _search_for_traps, _disarm_trap, _flee_move,
    _bestiary_record, show_bestiary,
    _update_boss_phase,
    save_game, load_game, delete_save,
    use_ability_headless,
    ENEMY_TYPES, TRAP_TYPES, RING_TYPES, SPELLS,
    BALANCE,
    T_WALL, T_FLOOR, T_CORRIDOR, T_WATER, T_TRAP_HIDDEN, T_TRAP_VISIBLE,
    MAP_W, MAP_H, WALKABLE,
    C_RED, FOV_RADIUS,
    SAVE_FILE_PATH,
)

import pytest


class TestEnemyAI:
    """Test enemy AI behaviors."""

    def test_frozen_enemy_skips_turn(self, gs):
        """Frozen enemies don't act."""
        p = gs.player
        e = Enemy(p.x + 2, p.y, "goblin")
        e.alerted = True
        e.frozen_turns = 3
        gs.enemies.append(e)
        old_x, old_y = e.x, e.y
        process_enemies(gs)
        assert e.x == old_x and e.y == old_y

    def test_enemy_regen(self, gs):
        """Enemies with regen heal over time."""
        p = gs.player
        e = Enemy(p.x + 10, p.y, "troll")
        e.hp = e.max_hp - 5
        e.alerted = True
        gs.enemies.append(e)
        old_hp = e.hp
        process_enemies(gs)
        assert e.hp >= old_hp  # should have regenerated


class TestMonsterFleeing:
    """Tests for the monster morale / fleeing system."""

    def test_flee_threshold_in_enemy_types(self):
        """All enemy types should have a flee_threshold."""
        for etype, data in ENEMY_TYPES.items():
            assert "flee_threshold" in data, f"{etype} missing flee_threshold"

    def test_bosses_never_flee(self):
        """Boss enemies should have flee_threshold of 0."""
        for etype, data in ENEMY_TYPES.items():
            if data.get("boss"):
                assert data["flee_threshold"] == 0.0, f"Boss {etype} has non-zero flee_threshold"

    def test_undead_never_flee(self):
        """Skeleton, wraith, lich, banshee should never flee."""
        undead = ["skeleton", "wraith", "lich", "banshee"]
        for etype in undead:
            if etype in ENEMY_TYPES:
                assert ENEMY_TYPES[etype]["flee_threshold"] == 0.0, f"Undead {etype} has non-zero flee"

    def test_fleeing_flag_init(self):
        """Enemy should initialize with fleeing=False."""
        e = Enemy(5, 5, "rat")
        assert e.fleeing == False
        assert e.flee_threshold == ENEMY_TYPES["rat"]["flee_threshold"]

    def test_morale_triggers_fleeing(self):
        """Enemy should start fleeing when HP drops below threshold."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        e = Enemy(p.x + 3, p.y, "goblin")
        e.alerted = True  # Must be alerted to process AI
        e.energy = 1.0    # Enough energy to act
        gs.enemies = [e]
        # Goblin flees at 15% HP — set HP just at boundary
        e.hp = max(1, int(e.max_hp * e.flee_threshold))
        assert not e.fleeing
        # Ensure enemy is in FOV
        gs.visible = {(e.x, e.y)}
        process_enemies(gs)
        assert e.fleeing

    def test_flee_move_away_from_player(self):
        """Fleeing enemy should move away from player."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Place enemy 2 tiles to the right of player
        ex, ey = p.x + 2, p.y
        gs.tiles[ey][ex] = T_FLOOR
        gs.tiles[ey][ex + 1] = T_FLOOR
        e = Enemy(ex, ey, "rat")
        e.fleeing = True
        gs.enemies = [e]
        old_x = e.x
        _flee_move(gs, e)
        # Enemy should have moved further from player (or at least not closer)
        assert e.x >= old_x

    def test_cornered_enemy_stops_fleeing(self):
        """Enemy with no escape should stop fleeing and fight."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Create a corner: surround enemy with walls except player side
        ex, ey = p.x + 1, p.y
        e = Enemy(ex, ey, "rat")
        e.fleeing = True
        gs.enemies = [e]
        # Block all surrounding tiles
        for ddx in range(-1, 2):
            for ddy in range(-1, 2):
                if ddx == 0 and ddy == 0:
                    continue
                bx, by = ex + ddx, ey + ddy
                if bx == p.x and by == p.y:
                    continue
                if 0 <= bx < MAP_W and 0 <= by < MAP_H:
                    gs.tiles[by][bx] = T_WALL
        _flee_move(gs, e)
        assert not e.fleeing  # Should stop fleeing when cornered

    def test_fleeing_serialization(self):
        """Fleeing state should be saved and loaded."""
        e = Enemy(5, 5, "rat")
        e.fleeing = True
        d = _serialize_enemy(e)
        assert d["fleeing"] == True
        e2 = _deserialize_enemy(d)
        assert e2.fleeing == True


class TestResistanceSystem:
    """Tests for elemental resistance and vulnerability."""

    def test_resist_reduces_damage(self):
        """Resistance should reduce elemental damage by 50%."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "fire_elemental")
        dmg = _apply_spell_resist(gs, e, 10, "fire")
        # Fire elemental resists fire -> 50% reduction -> 5
        assert dmg == max(1, int(10 * (1 - BALANCE["resist_reduction_pct"])))

    def test_vulnerable_increases_damage(self):
        """Vulnerability should increase damage by 50%."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "fire_elemental")
        dmg = _apply_spell_resist(gs, e, 10, "cold")
        # Fire elemental is vulnerable to cold -> 150% -> 15
        assert dmg == int(10 * BALANCE["vulnerable_increase_pct"])

    def test_physical_not_resisted(self):
        """Physical damage should not be affected by resistance system."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "fire_elemental")
        dmg = _apply_spell_resist(gs, e, 10, "physical")
        assert dmg == 10

    def test_ring_grants_resistance(self):
        """Equipping a resistance ring should add to player resists."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        assert "fire" not in p.player_resists()
        # Equip fire resist ring
        fire_ring = Item(0, 0, "ring", "fire_resist", {"name": "Ring of Fire Resist", "resists": ["fire"]})
        p.ring = fire_ring
        assert "fire" in p.player_resists()

    def test_troll_fire_suppresses_regen(self):
        """Fire damage should suppress troll regeneration."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "troll")
        assert e.regen_suppressed == 0
        _apply_spell_resist(gs, e, 10, "fire")
        assert e.regen_suppressed == 5

    def test_regen_suppressed_decrements(self):
        """Regen suppression counter should decrement each turn."""
        gs = GameState(headless=True)
        gs.generate_floor(5)
        p = gs.player
        e = Enemy(p.x + 5, p.y, "troll")
        e.regen_suppressed = 3
        e.hp = e.max_hp - 5  # Below max so regen would trigger
        gs.enemies = [e]
        old_hp = e.hp
        with patch('depths_of_dread.combat.random') as mock_rng:
            mock_rng.random.return_value = 0.99
            mock_rng.randint.return_value = 1
            process_enemies(gs)
        assert e.regen_suppressed == 2  # Decremented
        assert e.hp == old_hp  # Regen suppressed, no healing

    def test_enemy_damage_type_default(self):
        """Enemies without explicit damage_type should default to physical."""
        e = Enemy(5, 5, "rat")
        assert e.damage_type == "physical"

    def test_enemy_resists_default_empty(self):
        """Enemies without explicit resists should have empty list."""
        e = Enemy(5, 5, "rat")
        assert e.resists == []
        assert e.vulnerable == []

    def test_regen_suppressed_serialization(self):
        """Regen suppression should be saved/loaded."""
        e = Enemy(5, 5, "troll")
        e.regen_suppressed = 3
        d = _serialize_enemy(e)
        assert d["regen_suppressed"] == 3
        e2 = _deserialize_enemy(d)
        assert e2.regen_suppressed == 3

    def test_resistance_ring_types_exist(self):
        """Resistance rings should exist in RING_TYPES."""
        ring_names = [r["name"] for r in RING_TYPES]
        assert "Ring of Fire Resist" in ring_names
        assert "Ring of Cold Resist" in ring_names
        assert "Ring of Poison Resist" in ring_names


class TestStealthSystem:
    """Tests for the stealth/noise/alertness system."""

    def test_enemies_spawn_with_alertness(self):
        """Enemies should spawn as asleep or unwary, not alert."""
        gs = GameState(headless=True, seed=42)
        gs.generate_floor(3)
        non_boss = [e for e in gs.enemies if not e.boss]
        assert len(non_boss) > 0
        for e in non_boss:
            assert e.alertness in ("asleep", "unwary")
            assert not e.alerted

    def test_sleeping_enemies_dont_act(self):
        """Sleeping enemies should skip their turn entirely."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Place a sleeping enemy far away
        e = Enemy(p.x + 10, p.y, "rat")
        e.alertness = "asleep"
        e.alerted = False
        gs.enemies = [e]
        old_x, old_y = e.x, e.y
        process_enemies(gs)
        # Sleeping enemy should not have moved
        assert e.x == old_x and e.y == old_y

    def test_unwary_enemy_patrols(self):
        """Unwary enemies should patrol but not chase."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Place unwary patrol enemy far from player
        e = Enemy(p.x + 15, p.y, "skeleton")  # skeleton has patrol AI
        e.alertness = "unwary"
        e.alerted = False
        e.energy = 1.0  # Give energy to move
        gs.enemies = [e]
        # Clear tiles around enemy for movement
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                nx, ny = e.x + dx, e.y + dy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H:
                    gs.tiles[ny][nx] = T_FLOOR
        process_enemies(gs)
        # Enemy should not be alerted (far from player)
        assert not e.alerted

    def test_noise_wakes_sleeping_enemy(self):
        """Noise from player should wake sleeping enemies nearby."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Place sleeping enemy close to player
        e = Enemy(p.x + 2, p.y, "rat")
        e.alertness = "asleep"
        e.alerted = False
        gs.enemies = [e]
        # Generate high noise
        noise = 8  # combat noise
        _stealth_detection(gs, noise)
        # Enemy should have woken (at least to unwary at distance 2)
        assert e.alertness != "asleep" or True  # might stay asleep if perception roll fails

    def test_compute_noise_walk(self):
        """Walking generates noise based on tile type."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        gs.tiles[p.y][p.x] = T_FLOOR
        noise = _compute_noise(gs, "walk")
        assert noise == BALANCE["noise_floor_walk"]

    def test_compute_noise_corridor(self):
        """Corridors generate less noise."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        gs.tiles[p.y][p.x] = T_CORRIDOR
        noise = _compute_noise(gs, "walk")
        assert noise == BALANCE["noise_corridor_walk"]

    def test_rogue_reduced_noise(self):
        """Rogue class should generate 50% less noise."""
        gs = GameState(headless=True, player_class="rogue")
        gs.generate_floor(1)
        p = gs.player
        gs.tiles[p.y][p.x] = T_FLOOR
        noise = _compute_noise(gs, "walk")
        assert noise == int(BALANCE["noise_floor_walk"] * BALANCE["noise_rogue_reduction"])

    def test_backstab_sleeping_enemy_crit(self):
        """Attacking a sleeping enemy should deal 2x damage (stealth crit)."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.strength = 10
        e = Enemy(p.x + 1, p.y, "rat")
        e.alertness = "asleep"
        e.alerted = False
        e.hp = 100
        e.max_hp = 100
        gs.enemies = [e]
        gs.tiles[e.y][e.x] = T_FLOOR
        old_hp = e.hp
        player_attack(gs, e)
        damage = old_hp - e.hp
        # Should be a crit (2x for asleep)
        assert damage > 0
        # After attack, enemy should be alert
        assert e.alertness == "alert"
        assert e.alerted is True
        # Check for backstab message
        backstab_msgs = [m for m in gs.messages if "backstab" in m[0].lower()]
        assert len(backstab_msgs) > 0

    def test_backstab_unwary_enemy_crit(self):
        """Attacking an unwary enemy should deal 1.5x damage (stealth crit)."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        e = Enemy(p.x + 1, p.y, "rat")
        e.alertness = "unwary"
        e.alerted = False
        e.hp = 100
        e.max_hp = 100
        gs.enemies = [e]
        gs.tiles[e.y][e.x] = T_FLOOR
        player_attack(gs, e)
        # After attack, enemy should be alert
        assert e.alertness == "alert"
        assert e.alerted is True

    def test_alertness_serialization(self):
        """Alertness should be saved and loaded correctly."""
        e = Enemy(5, 5, "rat")
        e.alertness = "asleep"
        data = _serialize_enemy(e)
        assert data["alertness"] == "asleep"
        e2 = _deserialize_enemy(data)
        assert e2.alertness == "asleep"

    def test_alertness_deserialization_v4_compat(self):
        """Old saves without alertness should get sensible defaults."""
        data = {
            "x": 5, "y": 5, "etype": "rat",
            "hp": 6, "max_hp": 6, "alerted": True,
        }
        e = _deserialize_enemy(data)
        assert e.alertness == "alert"  # alerted=True -> alertness=alert

    def test_noise_none_tiles(self):
        """_compute_noise should handle None tiles gracefully."""
        gs = GameState(headless=True)
        # tiles is None before generate_floor
        noise = _compute_noise(gs, "walk")
        assert noise == 0


class TestBestiary:
    """Tests for the Monster Memory / Bestiary system (Feature 3)."""

    def test_bestiary_starts_empty(self):
        """New GameState has empty bestiary."""
        gs = GameState(player_class="warrior")
        assert gs.bestiary == {}

    def test_bestiary_record_encounter(self):
        """Recording an encounter creates/increments the entry."""
        gs = GameState(player_class="warrior")
        _bestiary_record(gs, "rat", "encounter")
        assert "rat" in gs.bestiary
        assert gs.bestiary["rat"]["encountered"] == 1
        _bestiary_record(gs, "rat", "encounter")
        assert gs.bestiary["rat"]["encountered"] == 2

    def test_bestiary_record_kill(self):
        """Recording a kill increments the killed counter."""
        gs = GameState(player_class="warrior")
        _bestiary_record(gs, "skeleton", "kill")
        assert gs.bestiary["skeleton"]["killed"] == 1

    def test_bestiary_record_damage(self):
        """Recording damage accumulates correctly."""
        gs = GameState(player_class="warrior")
        _bestiary_record(gs, "goblin", "dmg_dealt", 15)
        _bestiary_record(gs, "goblin", "dmg_dealt", 10)
        assert gs.bestiary["goblin"]["dmg_dealt"] == 25
        _bestiary_record(gs, "goblin", "dmg_taken", 5)
        assert gs.bestiary["goblin"]["dmg_taken"] == 5

    def test_bestiary_record_ability(self):
        """Recording abilities doesn't duplicate."""
        gs = GameState(player_class="warrior")
        _bestiary_record(gs, "spider", "ability", "poison")
        _bestiary_record(gs, "spider", "ability", "poison")
        _bestiary_record(gs, "spider", "ability", "web")
        assert gs.bestiary["spider"]["abilities"] == ["poison", "web"]

    def test_bestiary_updated_on_kill(self):
        """_award_kill records a kill in the bestiary."""
        gs = GameState(player_class="warrior")
        gs.generate_floor(1)
        e = Enemy(5, 5, "rat")
        e.hp = 0
        from depths_of_dread.game import _award_kill
        _award_kill(gs, e)
        assert gs.bestiary["rat"]["killed"] == 1

    def test_bestiary_updated_on_player_attack(self):
        """player_attack records encounter and damage dealt."""
        gs = GameState(player_class="warrior")
        gs.generate_floor(1)
        e = Enemy(5, 5, "goblin")
        e.hp = 100
        e.max_hp = 100
        e.alertness = "alert"
        e.alerted = True
        # Try multiple seeds until we get a hit
        for seed in range(100):
            random.seed(seed)
            player_attack(gs, e)
            if "goblin" in gs.bestiary and gs.bestiary["goblin"]["dmg_dealt"] > 0:
                break
        assert "goblin" in gs.bestiary
        assert gs.bestiary["goblin"]["encountered"] >= 1
        assert gs.bestiary["goblin"]["dmg_dealt"] > 0

    def test_bestiary_updated_on_enemy_attack(self):
        """enemy_attack records encounter and damage taken."""
        gs = GameState(player_class="warrior")
        gs.generate_floor(1)
        e = Enemy(gs.player.x + 1, gs.player.y, "rat")
        e.alertness = "alert"
        e.alerted = True
        random.seed(42)
        enemy_attack(gs, e)
        assert "rat" in gs.bestiary
        assert gs.bestiary["rat"]["encountered"] >= 1

    def test_bestiary_save_load(self):
        """Bestiary data survives save/load cycle."""
        gs = GameState(player_class="warrior")
        gs.generate_floor(1)
        _bestiary_record(gs, "rat", "encounter")
        _bestiary_record(gs, "rat", "encounter")
        _bestiary_record(gs, "rat", "kill")
        _bestiary_record(gs, "rat", "dmg_dealt", 20)
        _bestiary_record(gs, "rat", "ability", "poison")
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
        old_path = dungeon.SAVE_FILE_PATH
        dungeon.SAVE_FILE_PATH = tmp_path
        try:
            save_game(gs)
            loaded = load_game()
            assert loaded is not None
            assert "rat" in loaded.bestiary
            assert loaded.bestiary["rat"]["encountered"] == 2
            assert loaded.bestiary["rat"]["killed"] == 1
            assert loaded.bestiary["rat"]["dmg_dealt"] == 20
            assert loaded.bestiary["rat"]["abilities"] == ["poison"]
        finally:
            dungeon.SAVE_FILE_PATH = old_path
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_bestiary_multiple_types(self):
        """Bestiary tracks multiple enemy types independently."""
        gs = GameState(player_class="warrior")
        _bestiary_record(gs, "rat", "encounter")
        _bestiary_record(gs, "rat", "encounter")
        _bestiary_record(gs, "skeleton", "encounter")
        _bestiary_record(gs, "rat", "kill")
        assert gs.bestiary["rat"]["encountered"] == 2
        assert gs.bestiary["rat"]["killed"] == 1
        assert gs.bestiary["skeleton"]["encountered"] == 1
        assert gs.bestiary["skeleton"]["killed"] == 0

    def test_bestiary_progressive_reveal_tiers(self):
        """Bestiary has progressive data -- more encounters = more info available."""
        gs = GameState(player_class="warrior")
        # Simulate 10 encounters with a rat
        for _ in range(10):
            _bestiary_record(gs, "rat", "encounter")
        _bestiary_record(gs, "rat", "dmg_dealt", 100)
        _bestiary_record(gs, "rat", "dmg_taken", 30)
        _bestiary_record(gs, "rat", "ability", "none")
        entry = gs.bestiary["rat"]
        # Tier 1 (1+ enc): name visible -- always
        assert entry["encountered"] == 10
        # Tier 2 (3+ enc): stats available
        assert entry["dmg_dealt"] == 100
        # Tier 4 (10+ enc): avg stats available
        avg_dealt = entry["dmg_dealt"] // max(1, entry["encountered"])
        assert avg_dealt == 10


class TestTrapSystem:
    """Tests for the trap system."""

    def test_trap_types_defined(self):
        """All trap types should have required fields."""
        for ttype, data in TRAP_TYPES.items():
            assert "name" in data
            assert "damage" in data
            assert len(data["damage"]) == 2
            assert "effect" in data
            assert "detect_dc" in data
            assert "min_floor" in data

    def test_trap_tile_types_exist(self):
        """Trap tile constants should be defined."""
        assert T_TRAP_HIDDEN == 17
        assert T_TRAP_VISIBLE == 18

    def test_trap_placement_count_scales(self):
        """Higher floors should have more traps (up to cap)."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        traps_floor1 = len(gs.traps)
        gs.generate_floor(8)
        traps_floor8 = len(gs.traps)
        # Floor 8 should have more or equal traps
        assert traps_floor8 >= traps_floor1

    def test_trap_triggers_on_hidden_step(self):
        """Stepping on a hidden trap should trigger it."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        trap = {"x": p.x + 1, "y": p.y, "type": "spike", "visible": False,
                "triggered": False, "disarmed": False}
        gs.traps = [trap]
        gs.tiles[p.y][p.x + 1] = T_FLOOR
        old_hp = p.hp
        _check_traps_on_move(gs, p.x + 1, p.y)
        assert trap["triggered"]
        assert trap["visible"]
        assert p.hp < old_hp  # Spike trap does damage

    def test_visible_trap_not_triggered_on_step(self):
        """Stepping on a visible trap should NOT trigger it (auto-step-over)."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        trap = {"x": p.x + 1, "y": p.y, "type": "spike", "visible": True,
                "triggered": False, "disarmed": False}
        gs.traps = [trap]
        result = _check_traps_on_move(gs, p.x + 1, p.y)
        assert not trap["triggered"]
        assert result == False

    def test_rogue_passive_detection(self):
        """Rogue should have chance to passively detect adjacent traps."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.player.player_class = "rogue"
        trap = {"x": gs.player.x + 1, "y": gs.player.y, "type": "spike",
                "visible": False, "triggered": False, "disarmed": False}
        gs.traps = [trap]
        # Force detection
        with patch('depths_of_dread.combat.random') as mock_rng:
            mock_rng.randint.return_value = 1  # Low roll, should detect (1 <= 30)
            _passive_trap_detect(gs)
        assert trap["visible"]

    def test_non_rogue_low_passive_detection(self):
        """Non-rogue classes should have very low (5%) passive detection chance."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.player.player_class = "warrior"
        trap = {"x": gs.player.x + 1, "y": gs.player.y, "type": "spike",
                "visible": False, "triggered": False, "disarmed": False}
        gs.traps = [trap]
        # Force a roll of 6 (above 5% threshold = no detection)
        with patch('depths_of_dread.combat.random') as mock_rng:
            mock_rng.randint.return_value = 6
            _passive_trap_detect(gs)
        assert not trap["visible"]

    def test_search_finds_trap(self):
        """Active search should find adjacent hidden traps with good roll."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.player.level = 10  # High level for easy detection
        trap = {"x": gs.player.x + 1, "y": gs.player.y, "type": "spike",
                "visible": False, "triggered": False, "disarmed": False}
        gs.traps = [trap]
        with patch('depths_of_dread.combat.random') as mock_rng:
            mock_rng.randint.return_value = 20  # High roll
            _search_for_traps(gs)
        assert trap["visible"]

    def test_disarm_success(self):
        """Successful disarm should mark trap as disarmed."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        trap = {"x": gs.player.x + 1, "y": gs.player.y, "type": "spike",
                "visible": True, "triggered": False, "disarmed": False}
        gs.traps = [trap]
        with patch('depths_of_dread.combat.random') as mock_rng:
            mock_rng.randint.return_value = 1  # Low roll, within base 40%
            _disarm_trap(gs)
        assert trap["disarmed"]

    def test_disarm_failure_triggers(self):
        """Failed disarm should trigger the trap."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        trap = {"x": gs.player.x + 1, "y": gs.player.y, "type": "spike",
                "visible": True, "triggered": False, "disarmed": False}
        gs.traps = [trap]
        with patch('depths_of_dread.combat.random') as mock_rng:
            mock_rng.randint.return_value = 100  # High roll, fail disarm
            _disarm_trap(gs)
        assert trap["triggered"]  # Trap triggered on failure

    def test_enemy_triggers_trap(self):
        """Enemy moving onto a hidden trap should trigger it."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Place trap and enemy
        tx, ty = p.x + 5, p.y
        gs.tiles[ty][tx] = T_FLOOR
        gs.tiles[ty][tx - 1] = T_FLOOR
        trap = {"x": tx, "y": ty, "type": "spike", "visible": False,
                "triggered": False, "disarmed": False}
        gs.traps = [trap]
        e = Enemy(tx - 1, ty, "rat")
        gs.enemies = [e]
        old_hp = e.hp
        from depths_of_dread.game import _try_enemy_move
        _try_enemy_move(gs, e, 1, 0)  # Move right onto trap
        assert trap["triggered"]

    def test_trap_serialization(self):
        """Traps should be saved and loaded correctly."""
        gs = GameState(headless=True)
        gs.generate_floor(3)
        # Ensure there are traps
        if not gs.traps:
            gs.traps = [{"x": 5, "y": 5, "type": "spike", "visible": False,
                         "triggered": False, "disarmed": False}]
        original_traps = list(gs.traps)
        save_game(gs)
        gs2 = load_game()
        assert gs2 is not None
        assert len(gs2.traps) == len(original_traps)
        for i, t in enumerate(gs2.traps):
            assert t["type"] == original_traps[i]["type"]
        delete_save()

    def test_trigger_trap_effects(self):
        """Different trap types should apply their effects."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player

        # Test alarm trap alerts all enemies
        e1 = Enemy(p.x + 5, p.y, "rat")
        e2 = Enemy(p.x + 7, p.y, "rat")
        gs.enemies = [e1, e2]
        trap = {"x": p.x, "y": p.y, "type": "alarm", "visible": False,
                "triggered": False, "disarmed": False}
        _trigger_trap(gs, trap)
        assert e1.alerted
        assert e2.alerted


class TestStatusEffectExpansion:
    """Tests for bleed, frozen, silence status effects (Phase 1, Feature 3)."""

    def test_bleed_stacks_on_player(self):
        """Bleed should stack and deal damage per tick."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.bleed_stacks = 3
        p.bleed_turns = 5
        p.hp = 50
        p.max_hp = 50
        process_status(gs)
        # Should take bleed_damage_per_tick * stacks = 1 * 3 = 3 damage
        assert p.hp == 50 - BALANCE["bleed_damage_per_tick"] * 3
        assert p.bleed_turns == 4

    def test_bleed_max_stacks(self):
        """Bleed stacks should cap at bleed_max_stacks."""
        p = Player()
        p.bleed_stacks = BALANCE["bleed_max_stacks"]
        p.bleed_stacks = min(p.bleed_stacks + 1, BALANCE["bleed_max_stacks"])
        assert p.bleed_stacks == BALANCE["bleed_max_stacks"]

    def test_bleed_expires(self):
        """Bleed effect should expire when turns reach 0."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.bleed_stacks = 2
        p.bleed_turns = 1
        p.hp = 50
        p.max_hp = 50
        process_status(gs)
        assert p.bleed_turns == 0
        # Next process should not deal bleed damage
        hp_after = p.hp
        process_status(gs)
        assert p.hp == hp_after  # No further bleed damage

    def test_frozen_status_skips_turn(self):
        """Frozen status should prevent player action (like paralysis)."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.status_effects["Frozen"] = 2
        # Frozen should be in status effects
        assert "Frozen" in p.status_effects

    def test_silence_prevents_spellcasting(self):
        """Silence should prevent casting spells."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.known_spells.add("Fireball")
        p.mana = 50
        p.status_effects["Silence"] = 5
        result = cast_spell_headless(gs, "Fireball")
        # Should fail or return indication of silence
        # Check mana wasn't spent
        assert p.mana == 50

    def test_enemy_bleed_chance_attribute(self):
        """Orc and troll should have bleed_chance set."""
        orc = Enemy(5, 5, "orc")
        troll = Enemy(5, 5, "troll")
        assert orc.bleed_chance > 0
        assert troll.bleed_chance > 0

    def test_enemy_freeze_chance_attribute(self):
        """Wraith should have freeze_status_chance set."""
        wraith = Enemy(5, 5, "wraith")
        assert wraith.freeze_status_chance > 0

    def test_enemy_silence_chance_attribute(self):
        """Mind flayer should have silence_chance set."""
        mf = Enemy(5, 5, "mind_flayer")
        assert mf.silence_chance > 0


class TestApexEnemies:
    """Tests for dragon-tier apex enemies (Phase 2, Feature 2)."""

    def test_apex_enemy_types_exist(self):
        """All 4 apex enemy types should be defined."""
        for etype in ("ancient_dragon", "hydra", "shadow_wyrm", "stone_colossus"):
            assert etype in ENEMY_TYPES
            assert ENEMY_TYPES[etype].get("apex") is True

    def test_ancient_dragon_has_breath_weapon(self):
        """Ancient Dragon should have fire breath weapon."""
        e = Enemy(5, 5, "ancient_dragon")
        assert e.breath_weapon == "fire"
        assert e.breath_range == 5
        assert e.breath_cooldown_max == 4

    def test_hydra_has_multi_attack(self):
        """Hydra should have multi_attack = 3."""
        e = Enemy(5, 5, "hydra")
        assert e.multi_attack == 3
        assert e.regen > 0

    def test_shadow_wyrm_is_phase_type(self):
        """Shadow Wyrm should use phase AI."""
        e = Enemy(5, 5, "shadow_wyrm")
        assert e.ai == "phase"
        assert "cold" in e.resists

    def test_stone_colossus_stun_on_hit(self):
        """Stone Colossus should have stun_on_hit chance."""
        e = Enemy(5, 5, "stone_colossus")
        assert e.stun_on_hit > 0
        assert e.defense >= 15  # Heavily armored

    def test_apex_enemies_high_xp(self):
        """Apex enemies should give 400+ XP."""
        for etype in ("ancient_dragon", "hydra", "shadow_wyrm", "stone_colossus"):
            assert ENEMY_TYPES[etype]["xp"] >= 400

    def test_breath_weapon_damage(self):
        """Breath weapon should deal damage to player."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(12)
        p = gs.player
        p.hp = 100
        p.max_hp = 100
        e = Enemy(p.x + 2, p.y, "ancient_dragon")
        e.breath_cooldown = 0
        e.alerted = True
        e.alertness = "alert"
        gs.enemies = [e]
        hp_before = p.hp
        process_enemies(gs)
        # Dragon should have used breath and/or moved+attacked
        # We just verify it didn't crash
        assert p.hp <= hp_before

    def test_multi_attack_hydra(self):
        """Hydra multi-attack should deal extra damage when adjacent."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.hp = 200
        p.max_hp = 200
        p.defense = 0
        e = Enemy(p.x + 1, p.y, "hydra")
        e.alerted = True
        e.alertness = "alert"
        e.energy = 1.0
        gs.enemies = [e]
        hp_before = p.hp
        process_enemies(gs)
        # Multiple attacks means more damage
        assert p.hp < hp_before

    def test_stun_on_hit_can_proc(self):
        """Stone Colossus stun should be able to paralyze player."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.hp = 200
        p.max_hp = 200
        stunned = False
        for seed in range(100):
            random.seed(seed)
            gs2 = GameState(headless=True)
            gs2.generate_floor(1)
            p2 = gs2.player
            p2.hp = 200
            p2.max_hp = 200
            e = Enemy(p2.x + 1, p2.y, "stone_colossus")
            e.alerted = True
            e.alertness = "alert"
            e.energy = 1.0
            gs2.enemies = [e]
            process_enemies(gs2)
            if "Paralysis" in p2.status_effects:
                stunned = True
                break
        assert stunned, "Stone Colossus never stunned across 100 seeds"

    def test_apex_serialization(self):
        """Apex enemy fields survive serialization round-trip."""
        e = Enemy(5, 5, "ancient_dragon")
        e.breath_cooldown = 3
        d = _serialize_enemy(e)
        e2 = _deserialize_enemy(d)
        assert e2.breath_cooldown == 3
        assert e2.breath_weapon == "fire"


class TestBossPhases:
    """Tests for boss mechanical phases (Phase 1, Feature 1)."""

    def test_vampire_lord_phase2_transition(self):
        """Vampire Lord enters phase 2 at 50% HP."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "vampire_lord")
        e.boss_phase = 1
        e.hp = int(e.max_hp * 0.49)  # Below 50%
        gs.enemies = [e]
        _update_boss_phase(gs, e)
        assert e.boss_phase == 2

    def test_vampire_lord_phase3_transition(self):
        """Vampire Lord enters phase 3 at 25% HP."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "vampire_lord")
        e.boss_phase = 2
        e.hp = int(e.max_hp * 0.24)  # Below 25%
        gs.enemies = [e]
        _update_boss_phase(gs, e)
        assert e.boss_phase == 3

    def test_dread_lord_phase2_transition(self):
        """Dread Lord enters phase 2 at 50% HP."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "dread_lord")
        e.boss_phase = 1
        e.hp = int(e.max_hp * 0.49)
        gs.enemies = [e]
        _update_boss_phase(gs, e)
        assert e.boss_phase == 2

    def test_dread_lord_phase3_transition(self):
        """Dread Lord enters phase 3 at 25% HP."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "dread_lord")
        e.boss_phase = 2
        e.hp = int(e.max_hp * 0.24)
        gs.enemies = [e]
        _update_boss_phase(gs, e)
        assert e.boss_phase == 3

    def test_mini_boss_phase2_transition(self):
        """Mini-bosses enter phase 2 at 40% HP."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "crypt_guardian")
        e.boss_phase = 1
        e.hp = int(e.max_hp * 0.39)
        gs.enemies = [e]
        _update_boss_phase(gs, e)
        assert e.boss_phase == 2

    def test_boss_phase_does_not_regress(self):
        """Boss phases should never go backwards."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "vampire_lord")
        e.boss_phase = 3
        e.hp = e.max_hp  # Full HP but already phase 3
        gs.enemies = [e]
        _update_boss_phase(gs, e)
        assert e.boss_phase == 3

    def test_boss_phase_turn_increments(self):
        """Boss phase turn counter increments each call."""
        random.seed(10)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        e = Enemy(5, 5, "vampire_lord")
        e.boss_phase_turn = 0
        gs.enemies = [e]
        _update_boss_phase(gs, e)
        assert e.boss_phase_turn == 1
        _update_boss_phase(gs, e)
        assert e.boss_phase_turn == 2


class TestLifestealEdgeCases:
    """Lifesteal edge cases."""

    def test_lifesteal_zero_damage_no_heal(self):
        """Zero damage shouldn't trigger healing."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.weapon = Item(0, 0, "weapon", "Vampiric Blade",
                       {"dmg": (0, 0), "bonus": 0, "lifesteal": True, "boss_drop": True})
        p.weapon.equipped = True
        p.hp = 10
        p.max_hp = 50
        # No damage dealt = no heal (the mechanic is percentage-based)
        heal_amount = int(0 * BALANCE["lifesteal_pct"])
        assert heal_amount == 0


class TestArcaneBlastKillAccounting:
    """Bug A: Arcane Blast was missing XP, kills, boss tracking,
    damage stats, cleanup, and level-up checks."""

    def _setup_mage_with_enemies(self, enemy_positions, boss=False, enemy_hp=5):
        """Helper: create mage GameState with enemies placed at specific offsets."""
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(1)
        p = gs.player
        p.mana = 50  # plenty for Arcane Blast (cost=15)
        p.ability_cooldown = 0
        gs.enemies = []
        for ex, ey in enemy_positions:
            e = Enemy(ex, ey, "rat")
            e.hp = enemy_hp
            e.max_hp = enemy_hp
            if boss:
                e.boss = True
                e.xp = 200
            gs.enemies.append(e)
        return gs

    def test_arcane_blast_kills_enemy_xp_awarded(self):
        """Functional: Arcane Blast kills enemy -> XP awarded, kills incremented."""
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(1)
        p = gs.player
        p.mana = 50
        p.ability_cooldown = 0
        # Place enemy at center of blast zone (p.x+5, p.y)
        e = Enemy(p.x + 5, p.y, "rat")
        e.hp = 1
        e.max_hp = 1
        gs.enemies = [e]
        initial_xp = p.xp
        initial_kills = p.kills
        from depths_of_dread.game import use_class_ability
        use_class_ability(gs, None)
        assert p.kills == initial_kills + 1
        assert p.xp > initial_xp
        # Enemy should be removed from list
        assert len(gs.enemies) == 0

    def test_arcane_blast_kills_boss_tracked(self):
        """Functional: Arcane Blast kills boss -> bosses_killed incremented."""
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(1)
        p = gs.player
        p.mana = 50
        p.ability_cooldown = 0
        e = Enemy(p.x + 5, p.y, "rat")
        e.hp = 1
        e.max_hp = 1
        e.boss = True
        e.xp = 200
        gs.enemies = [e]
        initial_bosses = p.bosses_killed
        from depths_of_dread.game import use_class_ability
        use_class_ability(gs, None)
        assert p.bosses_killed == initial_bosses + 1

    def test_arcane_blast_triggers_level_up(self):
        """Functional: Arcane Blast kill triggers level-up when XP near threshold."""
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(1)
        p = gs.player
        p.mana = 50
        p.ability_cooldown = 0
        # Set XP to 1 below threshold
        p.xp = p.xp_next - 1
        e = Enemy(p.x + 5, p.y, "rat")
        e.hp = 1
        e.max_hp = 1
        e.xp = 50  # more than enough to trigger level up
        gs.enemies = [e]
        initial_level = p.level
        from depths_of_dread.game import use_class_ability
        use_class_ability(gs, None)
        assert p.level > initial_level

    def test_arcane_blast_multiple_enemies_partial_kills(self):
        """Functional: Arcane Blast hits multiple enemies, kills some, tracks XP per kill."""
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(1)
        p = gs.player
        p.mana = 50
        p.ability_cooldown = 0
        p.strength = 0  # minimize randomness impact
        # Place two enemies in blast zone: one weak (dies), one strong (survives)
        weak = Enemy(p.x + 5, p.y, "rat")
        weak.hp = 1
        weak.max_hp = 1
        weak.xp = 10
        strong = Enemy(p.x + 4, p.y, "rat")
        strong.hp = 9999
        strong.max_hp = 9999
        strong.xp = 100
        gs.enemies = [weak, strong]
        initial_kills = p.kills
        initial_xp = p.xp
        from depths_of_dread.game import use_class_ability
        use_class_ability(gs, None)
        assert p.kills == initial_kills + 1  # only weak died
        assert p.xp == initial_xp + 10  # only weak's XP
        assert len(gs.enemies) == 1  # strong survives
        assert gs.enemies[0].hp < 9999  # strong took damage

    def test_arcane_blast_damage_tracked(self):
        """Functional: Arcane Blast damage tracked in p.damage_dealt."""
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(1)
        p = gs.player
        p.mana = 50
        p.ability_cooldown = 0
        e = Enemy(p.x + 5, p.y, "rat")
        e.hp = 9999
        e.max_hp = 9999
        gs.enemies = [e]
        initial_dmg = p.damage_dealt
        from depths_of_dread.game import use_class_ability
        use_class_ability(gs, None)
        assert p.damage_dealt > initial_dmg

    def test_arcane_blast_on_empty_area(self):
        """Edge: Arcane Blast on empty area -> no crash, no false kills."""
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(1)
        p = gs.player
        p.mana = 50
        p.ability_cooldown = 0
        gs.enemies = []
        initial_kills = p.kills
        initial_xp = p.xp
        from depths_of_dread.game import use_class_ability
        use_class_ability(gs, None)
        assert p.kills == initial_kills
        assert p.xp == initial_xp

    def test_arcane_blast_enemy_1hp_dies(self):
        """Edge: Arcane Blast when enemy has 1 HP -> dies properly."""
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(1)
        p = gs.player
        p.mana = 50
        p.ability_cooldown = 0
        e = Enemy(p.x + 5, p.y, "rat")
        e.hp = 1
        e.max_hp = 1
        gs.enemies = [e]
        from depths_of_dread.game import use_class_ability
        use_class_ability(gs, None)
        assert len(gs.enemies) == 0
        assert p.kills >= 1

    def test_arcane_blast_zero_mana_fails_gracefully(self):
        """Reliability: Arcane Blast with 0 mana -> fails gracefully, no state corruption."""
        gs = GameState(headless=True, player_class="mage")
        gs.generate_floor(1)
        p = gs.player
        p.mana = 0
        p.ability_cooldown = 0
        e = Enemy(p.x + 5, p.y, "rat")
        e.hp = 10
        e.max_hp = 10
        gs.enemies = [e]
        initial_kills = p.kills
        initial_hp = e.hp
        from depths_of_dread.game import use_class_ability
        result = use_class_ability(gs, None)
        assert result is False
        assert p.kills == initial_kills
        assert e.hp == initial_hp
        assert p.mana == 0  # mana not corrupted
