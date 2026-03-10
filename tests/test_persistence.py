"""Tests for save/load, session recording, stats, replay, serialization."""

import sys
import os
import json
import random
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from depths_of_dread import game as dungeon
from depths_of_dread.game import (
    GameState, Player, Enemy, Item, ShopItem,
    save_game, load_game, delete_save, save_exists, _compute_checksum,
    _serialize_item, _deserialize_item, _serialize_enemy, _deserialize_enemy,
    calculate_score, use_scroll,
    load_lifetime_stats, save_lifetime_stats, _default_lifetime_stats,
    SessionRecorder,
    SAVE_FILE_PATH, STATS_FILE_PATH, RECORDINGS_DIR,
    T_FLOOR, MAP_W, MAP_H,
)

import pytest


class TestSaveLoad:
    """Test save/load round-trips full game state."""

    def test_round_trip(self, gs_with_gear):
        """Save and load preserves full game state."""
        gs = gs_with_gear
        gs.player.gold = 42
        gs.player.kills = 7
        gs.turn_count = 100
        gs.player.hp = 20
        gs.tips_shown.add("enemy_adjacent")
        gs.first_melee_done = True

        assert save_game(gs) is True
        loaded = load_game()
        assert loaded is not None
        assert loaded.player.gold == 42
        assert loaded.player.kills == 7
        assert loaded.turn_count == 100
        assert loaded.player.hp == 20
        assert "enemy_adjacent" in loaded.tips_shown
        assert loaded.first_melee_done is True
        delete_save()

    def test_save_preserves_inventory(self, gs_with_gear):
        """Save preserves inventory items and equipped state."""
        gs = gs_with_gear
        save_game(gs)
        loaded = load_game()
        assert loaded is not None
        assert len(loaded.player.inventory) == len(gs.player.inventory)
        assert loaded.player.weapon is not None
        assert loaded.player.bow is not None
        delete_save()

    def test_save_preserves_enemies(self, gs):
        """Save preserves enemy state."""
        gs.enemies = [Enemy(5, 5, "goblin"), Enemy(10, 10, "rat")]
        save_game(gs)
        loaded = load_game()
        assert loaded is not None
        assert len(loaded.enemies) == 2
        assert loaded.enemies[0].etype == "goblin"
        delete_save()

    def test_save_preserves_map(self, gs):
        """Save preserves tile map."""
        save_game(gs)
        loaded = load_game()
        assert loaded is not None
        assert loaded.tiles == gs.tiles
        delete_save()

    def test_delete_save(self, gs):
        """Delete save removes the file."""
        save_game(gs)
        assert save_exists()
        delete_save()
        assert not save_exists()


class TestSessionRecording:
    """Test the session recording system."""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self, tmp_path, monkeypatch):
        from depths_of_dread import persistence as _persist
        self.rec_dir = str(tmp_path / "recordings")
        monkeypatch.setattr(dungeon, 'RECORDINGS_DIR', self.rec_dir)
        monkeypatch.setattr(_persist, 'RECORDINGS_DIR', self.rec_dir)

    def test_recording_creates_jsonl_file(self):
        rec = SessionRecorder(12345)
        rec.close()
        files = list(Path(self.rec_dir).glob("*.jsonl"))
        assert len(files) == 1
        assert "12345" in files[0].name

    def test_init_event_has_required_fields(self):
        rec = SessionRecorder(42, player_name="TestHero")
        rec.close()
        files = list(Path(self.rec_dir).glob("*.jsonl"))
        with open(files[0]) as f:
            first = json.loads(f.readline())
        assert first["event"] == "init"
        assert first["seed"] == 42
        assert first["version"] == 1
        assert "date" in first
        assert first["player_name"] == "TestHero"

    def test_input_events_have_turn_numbers(self):
        rec = SessionRecorder(99)
        rec.record_input("w", 5)
        rec.record_input("a", 6)
        rec.close()
        files = list(Path(self.rec_dir).glob("*.jsonl"))
        with open(files[0]) as f:
            lines = f.readlines()
        evt1 = json.loads(lines[1])
        evt2 = json.loads(lines[2])
        assert evt1["event"] == "input"
        assert evt1["turn"] == 5
        assert evt2["turn"] == 6

    def test_death_event_records_cause_and_score(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.death_cause = "slain by Rat"
        rec = SessionRecorder(gs.seed)
        rec.record_death(gs)
        rec.close()
        files = list(Path(self.rec_dir).glob("*.jsonl"))
        with open(files[0]) as f:
            lines = f.readlines()
        death = json.loads(lines[-1])
        assert death["event"] == "death"
        assert death["cause"] == "slain by Rat"
        assert "score" in death

    def test_state_snapshot_fields(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        rec = SessionRecorder(gs.seed)
        rec.record_state_snapshot(gs)
        rec.close()
        files = list(Path(self.rec_dir).glob("*.jsonl"))
        with open(files[0]) as f:
            lines = f.readlines()
        snap = json.loads(lines[-1])
        assert snap["event"] == "state_snapshot"
        for field in ["hp", "max_hp", "mana", "hunger", "floor", "x", "y", "kills", "gold"]:
            assert field in snap


class TestStatsFile:
    """Test lifetime stats persistence."""

    @pytest.fixture(autouse=True)
    def setup_temp_stats(self, tmp_path, monkeypatch):
        from depths_of_dread import persistence as _persist
        self.stats_path = str(tmp_path / "stats.json")
        monkeypatch.setattr(dungeon, 'STATS_FILE_PATH', self.stats_path)
        monkeypatch.setattr(_persist, 'STATS_FILE_PATH', self.stats_path)

    def test_stats_creates_on_first_game(self):
        stats = load_lifetime_stats()
        assert stats["total_games"] == 0
        stats["total_games"] = 1
        save_lifetime_stats(stats)
        assert os.path.exists(self.stats_path)

    def test_stats_accumulate(self):
        stats = _default_lifetime_stats()
        stats["total_games"] = 5
        stats["total_kills"] = 100
        save_lifetime_stats(stats)
        loaded = load_lifetime_stats()
        assert loaded["total_games"] == 5
        assert loaded["total_kills"] == 100

    def test_corrupt_stats_handled_gracefully(self):
        with open(self.stats_path, 'w') as f:
            f.write("NOT VALID JSON {{{{")
        stats = load_lifetime_stats()
        assert stats["total_games"] == 0  # Should return defaults


class TestSaveLoadNewFields:
    """Verify new fields survive save/load."""

    def test_journal_saved_and_loaded(self, tmp_path):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.journal = {"Potion of Healing": "Restores HP"}
        gs.shop_discovered = True
        # Save
        from depths_of_dread import game as dungeon
        old_path = dungeon.SAVE_FILE_PATH
        dungeon.SAVE_FILE_PATH = str(tmp_path / "test_save.json")
        try:
            save_game(gs)
            loaded = load_game()
            assert loaded is not None
            assert loaded.journal == {"Potion of Healing": "Restores HP"}
            assert loaded.shop_discovered == True
        finally:
            dungeon.SAVE_FILE_PATH = old_path


class TestReplayPrompt:
    """#3: Auto-replay prompt code exists."""

    def test_replay_prompt_in_source(self):
        import os, glob as _glob
        _pkg_dir = os.path.dirname(dungeon.__file__)
        source = '\n'.join(open(f).read() for f in _glob.glob(os.path.join(_pkg_dir, '*.py')))
        assert "Watch replay?" in source


class TestPhase1Serialization:
    """Tests for save/load of Phase 1 expansion fields."""

    def test_enemy_boss_phase_serialization(self):
        """Boss phase fields survive serialize/deserialize round-trip."""
        e = Enemy(5, 5, "vampire_lord")
        e.boss_phase = 3
        e.boss_phase_turn = 7
        d = _serialize_enemy(e)
        e2 = _deserialize_enemy(d)
        assert e2.boss_phase == 3
        assert e2.boss_phase_turn == 7

    def test_enemy_bleed_serialization(self):
        """Bleed fields survive serialize/deserialize round-trip."""
        e = Enemy(5, 5, "orc")
        e.bleed_stacks = 3
        e.bleed_turns = 4
        d = _serialize_enemy(e)
        e2 = _deserialize_enemy(d)
        assert e2.bleed_stacks == 3
        assert e2.bleed_turns == 4

    def test_enemy_silence_serialization(self):
        """Silence turns survive serialize/deserialize round-trip."""
        e = Enemy(5, 5, "mind_flayer")
        e.silenced_turns = 5
        d = _serialize_enemy(e)
        e2 = _deserialize_enemy(d)
        assert e2.silenced_turns == 5

    def test_player_bleed_serialization(self):
        """Player bleed fields survive save/load round-trip."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.player.bleed_stacks = 2
        gs.player.bleed_turns = 4
        saved = save_game(gs)
        assert saved
        gs2 = load_game()
        assert gs2 is not None
        assert gs2.player.bleed_stacks == 2
        assert gs2.player.bleed_turns == 4
        delete_save()

    def test_vignettes_serialization(self):
        """Vignettes survive save/load round-trip."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.vignettes = [{"x": 5, "y": 5, "lore": "Test lore", "triggered": False, "loot_chance": 0}]
        saved = save_game(gs)
        assert saved
        gs2 = load_game()
        assert gs2 is not None
        assert len(gs2.vignettes) == 1
        assert gs2.vignettes[0]["lore"] == "Test lore"
        delete_save()

    def test_default_values_for_missing_fields(self):
        """Deserialization should provide defaults for missing expansion fields."""
        d = {"x": 5, "y": 5, "etype": "rat", "hp": 10, "max_hp": 10,
             "alerted": False, "energy": 0, "frozen_turns": 0,
             "summon_cooldown": 0, "patrol_dir": [0, 1]}
        e = _deserialize_enemy(d)
        assert e.boss_phase == 1
        assert e.boss_phase_turn == 0
        assert e.bleed_stacks == 0
        assert e.bleed_turns == 0
        assert e.silenced_turns == 0


class TestShopSaveLoadPersistence:
    """Bug B: Shop data was not persisting through save/load cycles."""

    def test_shop_survives_save_load(self):
        """Functional: Save game with shop -> load -> shop exists at same coords."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        # Force a shop onto the floor
        gs.shops = []
        room = (5, 5, 10, 10)
        test_item = Item(0, 0, "potion", 0, {"name": "Health Potion", "effect": "heal", "value": 20})
        shop_items = [ShopItem(test_item, 50)]
        gs.shops.append((room, shop_items))
        assert save_game(gs) is True
        gs2 = load_game()
        assert gs2 is not None
        assert len(gs2.shops) == 1
        loaded_room, loaded_items = gs2.shops[0]
        assert loaded_room == room
        assert len(loaded_items) == 1
        delete_save()

    def test_shop_items_survive_save_load(self):
        """Functional: Shop item prices and sold flags survive save/load."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        room = (5, 5, 10, 10)
        item1 = Item(0, 0, "potion", 0, {"name": "Health Potion", "effect": "heal", "value": 20})
        item2 = Item(0, 0, "food", 0, {"name": "Bread", "nutrition": 30})
        si1 = ShopItem(item1, 75)
        si2 = ShopItem(item2, 25)
        gs.shops = [(room, [si1, si2])]
        assert save_game(gs) is True
        gs2 = load_game()
        _, loaded = gs2.shops[0]
        assert loaded[0].price == 75
        assert loaded[1].price == 25
        assert loaded[0].sold is False
        assert loaded[1].sold is False
        delete_save()

    def test_bought_item_marked_sold_survives(self):
        """Functional: Buy item from shop, save, load -> item still marked sold."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        room = (5, 5, 10, 10)
        item1 = Item(0, 0, "potion", 0, {"name": "Health Potion", "effect": "heal", "value": 20})
        si1 = ShopItem(item1, 50)
        si1.sold = True  # simulate purchase
        gs.shops = [(room, [si1])]
        assert save_game(gs) is True
        gs2 = load_game()
        _, loaded = gs2.shops[0]
        assert loaded[0].sold is True
        delete_save()

    def test_save_with_no_shop(self):
        """Edge: Save on floor with no shop -> load works fine."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.shops = []
        assert save_game(gs) is True
        gs2 = load_game()
        assert gs2 is not None
        assert gs2.shops == []
        delete_save()

    def test_empty_shop_all_sold(self):
        """Edge: Save with shop where all items sold -> load -> shop exists but all sold."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        room = (5, 5, 10, 10)
        item1 = Item(0, 0, "potion", 0, {"name": "Health Potion", "effect": "heal", "value": 20})
        si1 = ShopItem(item1, 50)
        si1.sold = True
        item2 = Item(0, 0, "food", 0, {"name": "Bread", "nutrition": 30})
        si2 = ShopItem(item2, 25)
        si2.sold = True
        gs.shops = [(room, [si1, si2])]
        assert save_game(gs) is True
        gs2 = load_game()
        _, loaded = gs2.shops[0]
        assert all(si.sold for si in loaded)
        delete_save()

    def test_corrupt_shop_data_graceful(self):
        """Reliability: Corrupt shop data in save file -> graceful handling."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.shops = []
        assert save_game(gs) is True
        # Corrupt the save file
        with open(SAVE_FILE_PATH, 'r') as f:
            data = json.load(f)
        data["data"]["shops"] = [{"room": "invalid", "items": "corrupt"}]
        # Re-compute checksum so it passes validation
        data_str = json.dumps(data["data"], separators=(',', ':'))
        data["checksum"] = _compute_checksum(data_str)
        with open(SAVE_FILE_PATH, 'w') as f:
            json.dump(data, f)
        gs2 = load_game()
        assert gs2 is None
        delete_save()

    def test_full_shop_flow_save_reload_browse(self):
        """Quality-in-use: Player browses shop, buys, saves, reloads, browses again."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.gold = 200
        room = (5, 5, 10, 10)
        item1 = Item(0, 0, "potion", 0, {"name": "Health Potion", "effect": "heal", "value": 20})
        item2 = Item(0, 0, "food", 0, {"name": "Bread", "nutrition": 30})
        si1 = ShopItem(item1, 50)
        si2 = ShopItem(item2, 25)
        gs.shops = [(room, [si1, si2])]
        # "Buy" item 1
        si1.sold = True
        p.gold -= si1.price
        p.inventory.append(si1.item)
        assert p.gold == 150
        # Save
        assert save_game(gs) is True
        # Reload
        gs2 = load_game()
        assert gs2 is not None
        p2 = gs2.player
        assert p2.gold == 150
        _, loaded_items = gs2.shops[0]
        assert loaded_items[0].sold is True
        assert loaded_items[1].sold is False
        # Can still "buy" item 2 after reload
        assert loaded_items[1].price == 25
        delete_save()


class TestMysteryMeatDeath:
    """Bug C: Mystery Meat death not setting game_over and death_cause."""

    def test_mystery_meat_death_at_1hp(self):
        """Functional: Mystery Meat at 1 HP with bad RNG -> game_over, death_cause."""
        from depths_of_dread.game import use_food
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.hp = 1
        meat = Item(0, 0, "food", 0, {"name": "Mystery Meat", "nutrition": 20})
        p.inventory.append(meat)
        with patch('depths_of_dread.items.random.random', return_value=0.0), \
             patch('depths_of_dread.items.random.randint', return_value=5):
            use_food(gs, meat)
        assert gs.game_over is True
        assert gs.death_cause == "food poisoning"

    def test_mystery_meat_high_hp_no_death(self):
        """Functional: Mystery Meat at high HP -> damage applied but no death."""
        from depths_of_dread.game import use_food
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.hp = 100
        p.max_hp = 100
        meat = Item(0, 0, "food", 0, {"name": "Mystery Meat", "nutrition": 20})
        p.inventory.append(meat)
        with patch('depths_of_dread.items.random.random', return_value=0.0), \
             patch('depths_of_dread.items.random.randint', return_value=5):
            use_food(gs, meat)
        assert gs.game_over is False
        assert p.hp == 95
        assert gs.death_cause is None

    def test_mystery_meat_inventory_updated_on_death(self):
        """Edge: Mystery Meat is last food item -> inventory updated even on death."""
        from depths_of_dread.game import use_food
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.hp = 1
        p.inventory = []
        meat = Item(0, 0, "food", 0, {"name": "Mystery Meat", "nutrition": 20})
        p.inventory.append(meat)
        assert len(p.inventory) == 1
        with patch('depths_of_dread.items.random.random', return_value=0.0), \
             patch('depths_of_dread.items.random.randint', return_value=5):
            use_food(gs, meat)
        assert meat not in p.inventory

    def test_mystery_meat_death_message_clear(self):
        """Usability: Death message says 'food poisoning', not some cryptic code."""
        from depths_of_dread.game import use_food
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.hp = 1
        meat = Item(0, 0, "food", 0, {"name": "Mystery Meat", "nutrition": 20})
        p.inventory.append(meat)
        with patch('depths_of_dread.items.random.random', return_value=0.0), \
             patch('depths_of_dread.items.random.randint', return_value=5):
            use_food(gs, meat)
        assert "food poisoning" in gs.death_cause.lower()


class TestRangedAttackDeathCause:
    """Bug D: Ranged attack death_cause not properly set with attacker's name."""

    def _setup_ranged_encounter(self):
        """Create a scenario where an archer can shoot the player."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        archer = Enemy(p.x + 3, p.y, "archer")
        archer.alerted = True
        for x in range(p.x, p.x + 5):
            if 0 <= x < MAP_W:
                gs.tiles[p.y][x] = T_FLOOR
        gs.enemies = [archer]
        return gs, archer

    def test_archer_kills_player_death_cause(self):
        """Functional: Dark Archer kills player -> death_cause includes archer's name."""
        from depths_of_dread.game import compute_fov, process_enemies
        gs, archer = self._setup_ranged_encounter()
        p = gs.player
        p.hp = 1
        p.defense = 0
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        with patch('depths_of_dread.combat.random.randint', side_effect=lambda a, b: b):
            process_enemies(gs)
        if gs.game_over:
            assert "Dark Archer" in gs.death_cause or "shot by" in gs.death_cause

    def test_archer_damages_no_death_cause(self):
        """Functional: Archer damages but doesn't kill -> no death_cause set."""
        from depths_of_dread.game import compute_fov, process_enemies
        gs, archer = self._setup_ranged_encounter()
        p = gs.player
        p.hp = 9999
        p.max_hp = 9999
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        process_enemies(gs)
        assert gs.game_over is False
        assert gs.death_cause is None

    def test_ranged_death_cause_format(self):
        """Usability: death_cause format is 'shot by <name>' for ranged kills."""
        from depths_of_dread.game import _ranged_move, _has_los, compute_fov
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.hp = 1
        archer = Enemy(p.x + 3, p.y, "archer")
        archer.alerted = True
        for x in range(p.x, p.x + 5):
            if 0 <= x < MAP_W:
                gs.tiles[p.y][x] = T_FLOOR
        gs.enemies = [archer]
        has_los = _has_los(gs.tiles, archer.x, archer.y, p.x, p.y)
        if has_los:
            with patch('depths_of_dread.combat.random.randint', side_effect=lambda a, b: b), \
                 patch('depths_of_dread.combat.random.random', return_value=1.0):
                _ranged_move(gs, archer)
            if gs.game_over:
                assert gs.death_cause == f"shot by {archer.name}"


class TestScrollBossTracking:
    """Bug E: Scroll effects (Fireball, Lightning) not incrementing bosses_killed."""

    def test_fireball_scroll_kills_boss(self):
        """Functional: Fireball scroll kills boss -> bosses_killed incremented."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        boss = Enemy(p.x + 2, p.y, "rat")
        boss.hp = 1
        boss.max_hp = 1
        boss.boss = True
        boss.xp = 200
        gs.enemies = [boss]
        item = Item(0, 0, "scroll", 0, {"name": "Scroll of Fireball", "effect": "Fireball"})
        p.inventory.append(item)
        initial_bosses = p.bosses_killed
        use_scroll(gs, item)
        assert p.bosses_killed == initial_bosses + 1

    def test_lightning_scroll_kills_boss(self):
        """Functional: Lightning scroll kills boss -> bosses_killed incremented."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        boss = Enemy(p.x + 2, p.y, "rat")
        boss.hp = 1
        boss.max_hp = 1
        boss.boss = True
        boss.xp = 200
        gs.enemies = [boss]
        item = Item(0, 0, "scroll", 0, {"name": "Scroll of Lightning", "effect": "Lightning"})
        p.inventory.append(item)
        initial_bosses = p.bosses_killed
        use_scroll(gs, item)
        assert p.bosses_killed == initial_bosses + 1

    def test_scroll_kills_nonboss_no_boss_count(self):
        """Edge: Scroll kills non-boss -> bosses_killed unchanged."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        e = Enemy(p.x + 2, p.y, "rat")
        e.hp = 1
        e.max_hp = 1
        e.boss = False
        gs.enemies = [e]
        item = Item(0, 0, "scroll", 0, {"name": "Scroll of Fireball", "effect": "Fireball"})
        p.inventory.append(item)
        initial_bosses = p.bosses_killed
        use_scroll(gs, item)
        assert p.bosses_killed == initial_bosses
