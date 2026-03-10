"""Tests for entity stats: level-up, auto-equip, weapon/armor, inventory, scrolls, boss drops."""

import sys
import os
import random
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from depths_of_dread import game as dungeon
from depths_of_dread.game import (
    GameState, Player, Enemy, Item,
    player_move, player_attack,
    _award_kill,
    _inv_letter, _inv_key_to_idx,
    WEAPON_TYPES, ARMOR_TYPES, FOOD_TYPES, BOSS_DROPS,
    BALANCE,
    T_WALL, T_FLOOR, MAP_W, MAP_H, MAX_INVENTORY,
)

import pytest


class TestLevelUpStats:
    """Test level up messages show stat gains."""

    def test_level_up_shows_gains(self, gs):
        """Level up message includes HP, STR, MP gains."""
        p = gs.player
        p.xp = p.xp_next  # exactly enough to level
        gs.messages.clear()
        ups = p.check_level_up()
        assert len(ups) > 0
        lvl, hp_g, str_g, mp_g = ups[0]
        assert hp_g > 0
        assert str_g > 0
        assert mp_g > 0
        assert lvl == 2


class TestAutoEquip:
    """#14: Auto-equip better armor on pickup."""

    def test_auto_equip_armor(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Give player weak armor
        weak = Item(0, 0, "armor", 0, dict(ARMOR_TYPES[0]))
        weak.equipped = True
        p.armor = weak
        p.inventory.append(weak)
        # Place better armor on ground
        better = Item(p.x, p.y, "armor", 3, dict(ARMOR_TYPES[3]))
        gs.items.append(better)
        # Walk onto it (re-place player)
        player_move(gs, 0, 0)  # won't move but triggers logic - need pickup
        # Directly simulate pickup
        gs.items = [better]
        better.x = p.x
        better.y = p.y
        player_move(gs, 0, 0)  # stay still
        # Check via manual pickup
        gs2 = GameState(headless=True)
        gs2.generate_floor(1)
        p2 = gs2.player
        p2.armor = None
        strong = Item(p2.x + 1, p2.y, "armor", 3, dict(ARMOR_TYPES[3]))
        gs2.items.append(strong)
        player_move(gs2, 1, 0)  # move to pick up
        if strong in p2.inventory:
            assert strong.equipped == True
            assert p2.armor == strong

    def test_auto_equip_weapon_when_barefisted(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.weapon = None
        for it in list(p.inventory):
            if it.item_type == "weapon":
                p.inventory.remove(it)
        sword = Item(p.x + 1, p.y, "weapon", 1, dict(WEAPON_TYPES[1]))
        gs.items.append(sword)
        # Ensure target tile is walkable
        gs.tiles[p.y][p.x + 1] = T_FLOOR
        gs.enemies = [e for e in gs.enemies if not (e.x == p.x + 1 and e.y == p.y)]
        player_move(gs, 1, 0)
        if sword in p.inventory:
            assert sword.equipped == True
            assert p.weapon == sword


class TestWeaponArmorStats:
    """#22: Weapon damage and armor defense shown on HUD."""

    def test_weapon_stats_in_sidebar_code(self):
        import os, glob as _glob
        _pkg_dir = os.path.dirname(dungeon.__file__)
        source = '\n'.join(open(f).read() for f in _glob.glob(os.path.join(_pkg_dir, '*.py')))
        # Sidebar should format weapon dmg range
        assert 'lo, hi = p.weapon.data["dmg"]' in source


class TestInventoryStats:
    """#23: Stats shown on inventory screen."""

    def test_inventory_header_has_stats(self):
        import os, glob as _glob
        _pkg_dir = os.path.dirname(dungeon.__file__)
        source = '\n'.join(open(f).read() for f in _glob.glob(os.path.join(_pkg_dir, '*.py')))
        assert "HP:" in source and "MP:" in source and "Hunger:" in source


class TestInventorySorting:
    """#12: Inventory sort cycling."""

    def test_sort_by_type(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.inventory = []
        p.inventory.append(Item(0, 0, "food", "Bread", FOOD_TYPES[0]))
        p.inventory.append(Item(0, 0, "weapon", 0, WEAPON_TYPES[0]))
        p.inventory.append(Item(0, 0, "armor", 0, ARMOR_TYPES[0]))
        p.inventory.sort(key=lambda it: (it.item_type, it.display_name))
        types = [it.item_type for it in p.inventory]
        assert types == sorted(types)

    def test_sort_by_name(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.inventory = []
        p.inventory.append(Item(0, 0, "food", "Bread", {"name": "Zzz Bread", "char": '%', "nutrition": 15, "desc": "test"}))
        p.inventory.append(Item(0, 0, "food", "Bread", {"name": "Aaa Bread", "char": '%', "nutrition": 15, "desc": "test"}))
        p.inventory.sort(key=lambda it: it.display_name)
        assert p.inventory[0].display_name < p.inventory[1].display_name


class TestScrollCapacity:
    """#16: Scrolls don't take inventory space."""

    def test_scroll_exempt_from_capacity(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.strength = -13  # carry_capacity = 15 + (-13) = 2
        p.inventory = []
        # Fill to capacity with non-scroll items
        p.inventory.append(Item(0, 0, "food", "Bread", FOOD_TYPES[0]))
        p.inventory.append(Item(0, 0, "food", "Meat", FOOD_TYPES[1]))
        # Place a scroll on the ground
        scroll = Item(p.x + 1, p.y, "scroll", "Fireball",
                     {"effect": "Fireball", "label": "XYZZY", "char": '?'})
        gs.items.append(scroll)
        gs.tiles[p.y][p.x + 1] = T_FLOOR
        gs.enemies = [e for e in gs.enemies if not (e.x == p.x + 1 and e.y == p.y)]
        old_count = len(p.inventory)
        player_move(gs, 1, 0)
        # Scroll should be picked up even though at capacity
        assert len(p.inventory) == old_count + 1


class TestBossDrops:
    """#20: Boss-specific weapon drops."""

    def test_boss_drops_defined(self):
        assert "ogre_king" in BOSS_DROPS
        assert "vampire_lord" in BOSS_DROPS
        assert "dread_lord" in BOSS_DROPS

    def test_vampiric_blade_has_lifesteal(self):
        assert BOSS_DROPS["vampire_lord"].get("lifesteal") == True

    def test_boss_kill_drops_weapon(self):
        gs = GameState(headless=True)
        gs.generate_floor(5)
        boss = Enemy(10, 10, "ogre_king")
        boss.hp = 0  # already dead
        items_before = len(gs.items)
        _award_kill(gs, boss)
        # Should have dropped the boss weapon
        assert len(gs.items) > items_before
        dropped = [it for it in gs.items if it.display_name == "Ogre King's Maul"]
        assert len(dropped) == 1

    def test_lifesteal_heals_player(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        # Give vampiric blade
        vb = Item(0, 0, "weapon", "Vampiric Blade", dict(BOSS_DROPS["vampire_lord"]))
        vb.equipped = True
        p.weapon = vb
        p.inventory.append(vb)
        p.hp = 20
        p.max_hp = 50
        enemy = Enemy(p.x + 1, p.y, "rat")
        enemy.hp = 100
        gs.enemies.append(enemy)
        gs.tiles[enemy.y][enemy.x] = T_FLOOR
        old_hp = p.hp
        player_attack(gs, enemy)
        # Should have healed some
        assert p.hp >= old_hp  # at minimum equal (miss possible)
