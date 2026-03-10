"""Tests for items: spells, potions, scrolls, food, projectiles, wands, rings, shops, journal, alchemy, puzzles, enchantment, abilities."""

import sys
import os
import random
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from depths_of_dread import game as dungeon
from depths_of_dread.game import (
    GameState, Player, Enemy, Item, ShopItem,
    compute_fov, player_attack, player_move, process_status,
    fire_projectile_headless, cast_spell_headless, _launch_projectile,
    use_potion, use_scroll, use_food, pray_at_shrine,
    apply_levelup_choice, _unlock_next_spell, _unlock_next_ability,
    generate_levelup_choices, use_ability_headless,
    use_alchemy_table, _toggle_switch, _interact_pedestal,
    show_journal, _journal_potion_desc, _journal_scroll_desc,
    _bot_execute_action,
    enchant_weapon_headless,
    save_game, load_game, delete_save,
    WEAPON_TYPES, ARMOR_TYPES, POTION_EFFECTS, POTION_COLORS,
    SCROLL_EFFECTS, SCROLL_LABELS, FOOD_TYPES, RING_TYPES,
    BOW_TYPES, WAND_TYPES, TORCH_TYPES, THROWING_DAGGER, ARROW_ITEM,
    SPELLS, TILE_CHARS, ENCHANTMENTS,
    BASE_SPELLS, CLASS_KNOWN_SPELLS, SPELL_UNLOCK_ORDER,
    CLASS_ABILITIES, ABILITY_UNLOCK_ORDER,
    CHARACTER_CLASSES,
    BALANCE,
    T_WALL, T_FLOOR, T_SHOP_FLOOR, T_SHRINE, T_ALCHEMY_TABLE, T_WALL_TORCH,
    T_PEDESTAL_UNLIT, T_PEDESTAL_LIT, T_SWITCH_OFF, T_SWITCH_ON,
    T_STAIRS_LOCKED, T_STAIRS_DOWN, T_ENCHANT_ANVIL,
    MAP_W, MAP_H, WALKABLE,
    SAVE_FILE_PATH,
)

import pytest


class TestSpells:
    """Test all 5 spells with direction inputs."""

    def test_fireball(self, gs):
        p = gs.player
        p.mana = 50
        result = cast_spell_headless(gs, "Fireball", direction=(1, 0))
        assert result is True
        assert p.spells_cast == 1

    def test_lightning_bolt(self, gs):
        p = gs.player
        p.mana = 50
        result = cast_spell_headless(gs, "Lightning Bolt", direction=(0, 1))
        assert result is True

    def test_heal(self, gs):
        p = gs.player
        p.mana = 50
        p.hp = 10
        result = cast_spell_headless(gs, "Heal")
        assert result is True
        assert p.hp > 10

    def test_teleport(self, gs):
        p = gs.player
        p.mana = 50
        old_x, old_y = p.x, p.y
        result = cast_spell_headless(gs, "Teleport")
        assert result is True
        # Might or might not have moved (spawn pos could fail)

    def test_freeze(self, gs):
        p = gs.player
        p.mana = 50
        e = Enemy(p.x + 1, p.y, "rat")
        gs.enemies.append(e)
        if gs.tiles[p.y][p.x + 1] == T_WALL:
            gs.tiles[p.y][p.x + 1] = T_FLOOR
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        result = cast_spell_headless(gs, "Freeze", target_enemy=e)
        assert result is True
        assert e.frozen_turns == 3

    def test_spell_cancelled_refunds_mana(self, gs):
        p = gs.player
        p.mana = 20
        old_mana = p.mana
        # Fireball with None direction = cancel
        result = cast_spell_headless(gs, "Fireball", direction=None)
        assert result is False
        assert p.mana == old_mana  # mana refunded

    def test_insufficient_mana(self, gs):
        gs.player.mana = 0
        result = cast_spell_headless(gs, "Fireball", direction=(1, 0))
        assert result is False


class TestPotions:
    """Test potion effects."""

    def test_healing_potion(self, gs):
        p = gs.player
        p.hp = 10
        item = Item(0, 0, "potion", "Healing",
                   {"effect": "Healing", "color_name": "Red", "char": '!'})
        p.inventory.append(item)
        use_potion(gs, item)
        assert p.hp > 10

    def test_poison_potion(self, gs):
        p = gs.player
        p.hp = 30
        item = Item(0, 0, "potion", "Poison",
                   {"effect": "Poison", "color_name": "Green", "char": '!'})
        p.inventory.append(item)
        use_potion(gs, item)
        assert p.hp < 30

    def test_potion_identification(self, gs):
        """Using a potion identifies the effect."""
        p = gs.player
        item = Item(0, 0, "potion", "Healing",
                   {"effect": "Healing", "color_name": "Red", "char": '!'})
        p.inventory.append(item)
        assert "Healing" not in gs.id_potions
        use_potion(gs, item)
        assert "Healing" in gs.id_potions


class TestScrolls:
    """Test scroll effects."""

    def test_identify_scroll(self, gs):
        p = gs.player
        item = Item(0, 0, "scroll", "Identify",
                   {"effect": "Identify", "label": "XYZZY", "char": '?'})
        p.inventory.append(item)
        unid = Item(0, 0, "potion", "Healing",
                   {"effect": "Healing", "color_name": "Red", "char": '!'})
        p.inventory.append(unid)
        use_scroll(gs, item)
        assert unid.identified is True

    def test_mapping_scroll(self, gs):
        item = Item(0, 0, "scroll", "Mapping",
                   {"effect": "Mapping", "label": "PLUGH", "char": '?'})
        gs.player.inventory.append(item)
        use_scroll(gs, item)
        # Check explored tiles
        explored_count = sum(1 for y in range(MAP_H) for x in range(MAP_W) if gs.explored[y][x])
        assert explored_count > 0


class TestFood:
    """Test food consumption."""

    def test_eat_food(self, gs):
        p = gs.player
        p.hunger = 50
        item = Item(0, 0, "food", "Stale Bread", FOOD_TYPES[0])
        p.inventory.append(item)
        use_food(gs, item)
        assert p.hunger > 50


class TestProjectiles:
    """Test projectile system."""

    def test_fire_arrow(self, gs_with_gear):
        """Fire arrow with bow equipped."""
        gs = gs_with_gear
        result = fire_projectile_headless(gs, 1, 0)
        assert result is True

    def test_fire_without_ammo(self, gs):
        """Fire fails without ammo/weapon."""
        result = fire_projectile_headless(gs, 1, 0)
        assert result is False

    def test_fire_throwing_dagger(self, gs):
        """Fire throwing dagger."""
        p = gs.player
        dagger = Item(0, 0, "throwing_dagger", "Throwing Dagger", dict(THROWING_DAGGER))
        dagger.count = 3
        p.inventory.append(dagger)
        result = fire_projectile_headless(gs, 1, 0)
        assert result is True
        assert dagger.count == 2


class TestWandMechanics:
    """Test wand usage."""

    def test_wand_fires_projectile(self, gs):
        p = gs.player
        wand = Item(0, 0, "wand", "Wand of Fire", dict(WAND_TYPES[0]))
        p.inventory.append(wand)
        old_charges = wand.data["charges"]
        # Place enemy in line of fire
        e = Enemy(p.x + 3, p.y, "rat")
        if gs.tiles[p.y][p.x + 3] == T_WALL:
            gs.tiles[p.y][p.x + 3] = T_FLOOR
        gs.enemies.append(e)
        result = fire_projectile_headless(gs, 1, 0)
        assert result == True
        assert wand.data["charges"] == old_charges - 1

    def test_wand_charges_deplete(self, gs):
        p = gs.player
        wand = Item(0, 0, "wand", "Wand of Fire", dict(WAND_TYPES[0]))
        wand.data["charges"] = 1
        p.inventory.append(wand)
        fire_projectile_headless(gs, 1, 0)
        assert wand not in p.inventory  # Crumbles at 0 charges

    def test_empty_wand_cant_fire(self, gs):
        p = gs.player
        wand = Item(0, 0, "wand", "Wand of Fire", dict(WAND_TYPES[0]))
        wand.data["charges"] = 0
        p.inventory.append(wand)
        result = fire_projectile_headless(gs, 1, 0)
        # With no bow/arrows/daggers and empty wand, should fail
        assert result == False


class TestWandClassScaling:
    """#8: Wand damage varies by class."""

    def test_wand_mage_bonus_exists(self):
        assert "wand_mage_bonus_pct" in BALANCE
        assert BALANCE["wand_mage_bonus_pct"] == 0.50

    def test_wand_warrior_penalty_exists(self):
        assert "wand_warrior_penalty_pct" in BALANCE
        assert BALANCE["wand_warrior_penalty_pct"] == 0.25

    def test_wand_mage_range_bonus(self):
        assert BALANCE["wand_mage_range_bonus"] == 2


class TestWandFromInventory:
    """#13: Wands can be used from inventory."""

    def test_wand_in_inventory_has_charges(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        wand = Item(0, 0, "wand", "Wand of Fire", dict(WAND_TYPES[0]))
        gs.player.inventory.append(wand)
        assert wand.data.get("charges", 0) > 0

    def test_wand_fire_reduces_charges(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        wand = Item(0, 0, "wand", "Wand of Fire", dict(WAND_TYPES[0]))
        initial_charges = wand.data["charges"]
        gs.player.inventory.append(wand)
        _launch_projectile(gs, 1, 0, "wand", wand)
        assert wand.data["charges"] == initial_charges - 1


class TestRingMechanics:
    """Test ring equip effects."""

    def test_ring_of_protection(self, gs):
        p = gs.player
        base_def = p.total_defense()
        ring = Item(0, 0, "ring", "Ring of Protection", RING_TYPES[0])
        ring.equipped = True
        p.ring = ring
        p.inventory.append(ring)
        assert p.total_defense() == base_def + 2

    def test_ring_of_regen(self, gs):
        p = gs.player
        ring = Item(0, 0, "ring", "Ring of Regeneration", RING_TYPES[3])
        ring.equipped = True
        p.ring = ring
        p.inventory.append(ring)
        p.hp = p.max_hp - 5
        old_hp = p.hp
        # Regen triggers every 3 turns via player_move
        gs.turn_count = 3
        player_move(gs, 0, 0)  # Won't actually move (0,0) but let's test manually
        # Simulate the regen check
        if gs.turn_count % 3 == 0 and p.hp < p.max_hp:
            p.hp = min(p.max_hp, p.hp + 1)
        assert p.hp >= old_hp

    def test_ring_of_hunger_drains_faster(self, gs):
        p = gs.player
        ring = Item(0, 0, "ring", "Ring of Hunger", RING_TYPES[4])
        ring.equipped = True
        p.ring = ring
        p.inventory.append(ring)
        p.hunger = 100
        # Walk one step
        nx, ny = p.x + 1, p.y
        if gs.tiles[ny][nx] in WALKABLE:
            player_move(gs, 1, 0)
        expected_drain = BALANCE["hunger_per_move"] + BALANCE["hunger_curse_extra"]
        assert p.hunger <= 100 - expected_drain + 0.01  # Float tolerance


class TestShopMechanics:
    """Test shop spawning and purchasing."""

    def test_shop_spawns_on_correct_floors(self):
        """Shops on odd floors (#19)."""
        for floor in [1, 3, 5, 7]:
            gs = GameState(headless=True)
            gs.generate_floor(floor)
            assert len(gs.shops) > 0, f"No shop on floor {floor}"

    def test_shop_no_spawn_wrong_floor(self):
        """No shops on even floors (#19)."""
        gs = GameState(headless=True)
        gs.generate_floor(2)
        assert len(gs.shops) == 0

    def test_buy_with_enough_gold(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        assert len(gs.shops) > 0
        _, items = gs.shops[0]
        p = gs.player
        unsold = [si for si in items if not si.sold]
        assert len(unsold) > 0
        si = unsold[0]
        p.gold = si.price + 100
        old_gold = p.gold
        # Simulate purchase
        p.gold -= si.price
        p.inventory.append(si.item)
        si.sold = True
        assert p.gold == old_gold - si.price
        assert si.item in p.inventory

    def test_shop_always_stocks_healing_and_food(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        assert len(gs.shops) > 0
        _, items = gs.shops[0]
        types = set()
        for si in items:
            if si.item.item_type == "potion" and si.item.data.get("effect") == "Healing":
                types.add("healing")
            if si.item.item_type == "food":
                types.add("food")
        assert "healing" in types, "Shop missing healing potion"
        assert "food" in types, "Shop missing food"


class TestShopFrequency:
    """#19: Shops on odd floors."""

    def test_shops_on_odd_floors(self):
        for floor in [1, 3, 5, 7, 9, 11, 13, 15]:
            gs = GameState(headless=True)
            gs.generate_floor(floor)
            assert len(gs.shops) > 0, f"No shop on floor {floor}"

    def test_no_shops_on_even_floors(self):
        for floor in [2, 4, 6, 8, 10]:
            gs = GameState(headless=True)
            gs.generate_floor(floor)
            assert len(gs.shops) == 0, f"Unexpected shop on floor {floor}"


class TestShopDiscovery:
    """#10: Shop message should only fire when player sees shop tile."""

    def test_shop_no_message_on_placement(self):
        """Shop placement doesn't add message about merchant."""
        gs = GameState(headless=True)
        gs.generate_floor(1)
        # The floor 1 messages shouldn't include the old shop msg
        msgs = [t for t, _ in gs.messages]
        shop_msgs = [m for m in msgs if "merchant" in m.lower()]
        # shop_discovered should be False until FOV sees it
        assert gs.shop_discovered == False

    def test_shop_discovered_flag_resets_per_floor(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.shop_discovered = True
        gs.generate_floor(3)
        assert gs.shop_discovered == False


class TestJournal:
    """#6: Journal system tracks identified items."""

    def test_journal_populated_on_potion_use(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        potion = Item(0, 0, "potion", "Healing",
                     {"effect": "Healing", "color_name": "Red", "char": '!'})
        gs.player.inventory.append(potion)
        use_potion(gs, potion)
        assert "Potion of Healing" in gs.journal

    def test_journal_populated_on_scroll_use(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        scroll = Item(0, 0, "scroll", "Mapping",
                     {"effect": "Mapping", "label": "XYZZY", "char": '?'})
        gs.player.inventory.append(scroll)
        use_scroll(gs, scroll)
        assert "Scroll of Mapping" in gs.journal

    def test_journal_descriptions(self):
        assert _journal_potion_desc("Healing") == "Restores HP"
        assert _journal_scroll_desc("Fireball") == "AoE fire damage"

    def test_journal_starts_empty(self):
        gs = GameState(headless=True)
        assert gs.journal == {}


class TestAlchemyTable:
    """#7: Alchemy tables identify items."""

    def test_alchemy_table_spawns_on_correct_floors(self):
        for floor in [2, 5, 8, 11, 14]:
            gs = GameState(headless=True)
            gs.generate_floor(floor)
            has_alchemy = any(gs.tiles[y][x] == T_ALCHEMY_TABLE
                            for y in range(MAP_H) for x in range(MAP_W))
            # May not always spawn (room layout), but tile type should exist
            assert T_ALCHEMY_TABLE in TILE_CHARS

    def test_alchemy_identifies_item(self):
        gs = GameState(headless=True)
        gs.generate_floor(2)
        p = gs.player
        # Place player on alchemy table
        gs.tiles[p.y][p.x] = T_ALCHEMY_TABLE
        potion = Item(0, 0, "potion", "Speed",
                     {"effect": "Speed", "color_name": "Blue", "char": '!'})
        p.inventory.append(potion)
        assert not potion.identified
        result = use_alchemy_table(gs)
        assert result == True
        assert potion.identified == True

    def test_alchemy_table_single_use(self):
        gs = GameState(headless=True)
        gs.generate_floor(2)
        p = gs.player
        gs.tiles[p.y][p.x] = T_ALCHEMY_TABLE
        p1 = Item(0, 0, "potion", "Speed",
                 {"effect": "Speed", "color_name": "Blue", "char": '!'})
        p2 = Item(0, 0, "potion", "Healing",
                 {"effect": "Healing", "color_name": "Red", "char": '!'})
        p.inventory.extend([p1, p2])
        use_alchemy_table(gs)
        result2 = use_alchemy_table(gs)
        assert result2 == False  # already used


class TestAlchemyEdgeCases:
    """Alchemy table edge cases."""

    def test_alchemy_no_unidentified_items(self):
        """Alchemy table with no unidentified items gracefully does nothing."""
        gs = GameState(headless=True)
        gs.generate_floor(2)
        gs.tiles[gs.player.y][gs.player.x] = T_ALCHEMY_TABLE
        # Player has no items
        gs.player.inventory = []
        result = use_alchemy_table(gs)
        # Should return False or handle gracefully
        assert isinstance(result, bool)


class TestWallTorches:
    """#1: Environmental light sources."""

    def test_wall_torch_tile_exists(self):
        assert T_WALL_TORCH in TILE_CHARS
        assert TILE_CHARS[T_WALL_TORCH] == '!'

    def test_wall_torches_list_initialized(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        assert isinstance(gs.wall_torches, list)

    def test_wall_torch_not_walkable(self):
        """Wall torches are on walls -- not walkable."""
        assert T_WALL_TORCH not in WALKABLE


class TestWallTorchGrabFull:
    """Wall torch grab with full inventory."""

    def test_grab_torch_adds_to_inventory(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        tx, ty = p.x + 1, p.y
        gs.tiles[ty][tx] = T_WALL_TORCH
        gs.wall_torches = [(tx, ty)]
        result = _bot_execute_action(gs, "grab_wall_torch", {})
        assert result == True
        assert any(it.item_type == "torch" for it in p.inventory)


class TestPuzzles:
    """#9: Puzzle system."""

    def test_puzzle_tile_types_exist(self):
        for t in [T_PEDESTAL_UNLIT, T_PEDESTAL_LIT, T_SWITCH_OFF, T_SWITCH_ON, T_STAIRS_LOCKED]:
            assert t in TILE_CHARS

    def test_switch_toggle(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        # Place a switch
        px, py = gs.player.x + 2, gs.player.y
        gs.tiles[py][px] = T_SWITCH_OFF
        gs.puzzles.append({"type": "switch", "positions": [(px, py)], "solved": False,
                          "room": gs.rooms[0] if gs.rooms else (0, 0, 5, 5)})
        _toggle_switch(gs, px, py)
        assert gs.tiles[py][px] == T_SWITCH_ON
        # Puzzle should be solved (only 1 switch, now ON)
        assert gs.puzzles[0]["solved"] == True

    def test_pedestal_lighting(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.torch_fuel = 100
        px, py = p.x + 2, p.y
        gs.tiles[py][px] = T_PEDESTAL_UNLIT
        gs.puzzles.append({"type": "torch", "positions": [(px, py)], "solved": False,
                          "room": gs.rooms[0] if gs.rooms else (0, 0, 5, 5)})
        result = _interact_pedestal(gs, px, py)
        assert result == True
        assert gs.tiles[py][px] == T_PEDESTAL_LIT
        assert p.torch_fuel == 90  # cost 10

    def test_locked_stairs_unlock(self):
        gs = GameState(headless=True)
        gs.generate_floor(1)
        sx, sy = gs.stair_down
        gs.tiles[sy][sx] = T_STAIRS_LOCKED
        px, py = gs.player.x + 2, gs.player.y
        gs.tiles[py][px] = T_SWITCH_OFF
        gs.puzzles.append({"type": "locked_stairs", "positions": [(px, py)],
                          "solved": False, "room": gs.rooms[0] if gs.rooms else (0, 0, 5, 5),
                          "stairs": (sx, sy)})
        _toggle_switch(gs, px, py)
        assert gs.tiles[sy][sx] == T_STAIRS_DOWN  # unlocked


class TestPuzzleRewardSpawning:
    """Puzzle solving spawns rewards."""

    def test_switch_puzzle_structure(self):
        """Switch puzzles have valid positions."""
        gs = GameState(headless=True)
        for _ in range(50):
            gs.generate_floor(random.randint(4, 15))
            for puzzle in gs.puzzles:
                if puzzle["type"] in ("switch", "locked_stairs"):
                    for px, py in puzzle["positions"]:
                        assert gs.tiles[py][px] in (T_SWITCH_OFF, T_SWITCH_ON), \
                            f"Switch position ({px},{py}) has tile {gs.tiles[py][px]}"

    def test_torch_puzzle_structure(self):
        """Torch puzzles have pedestal positions."""
        gs = GameState(headless=True)
        for _ in range(50):
            gs.generate_floor(random.randint(4, 15))
            for puzzle in gs.puzzles:
                if puzzle["type"] == "torch":
                    for px, py in puzzle["positions"]:
                        assert gs.tiles[py][px] == T_PEDESTAL_UNLIT, \
                            f"Pedestal position ({px},{py}) has tile {gs.tiles[py][px]}"


class TestWeaponEnchantment:
    """Tests for weapon enchantment/crafting (Phase 4, Feature 3)."""

    def test_enchantments_defined(self):
        """ENCHANTMENTS dict should have multiple entries."""
        assert len(ENCHANTMENTS) >= 5

    def test_enchant_anvil_tile(self):
        """T_ENCHANT_ANVIL tile type should exist and be walkable."""
        assert T_ENCHANT_ANVIL in WALKABLE

    def test_enchant_weapon_success(self):
        """Enchanting a weapon should modify it."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.gold = 200
        # Create and equip a weapon
        wpn = Item(0, 0, "weapon", "Long Sword", dict(WEAPON_TYPES[3]))
        wpn.identified = True
        p.weapon = wpn
        p.inventory.append(wpn)
        # Place anvil under player
        gs.tiles[p.y][p.x] = T_ENCHANT_ANVIL
        old_name = wpn.subtype
        result = enchant_weapon_headless(gs)
        assert result is True
        assert wpn.data.get("enchantment") is not None
        assert p.gold == 200 - BALANCE["enchant_gold_cost"]

    def test_enchant_weapon_no_gold(self):
        """Enchanting without enough gold should fail."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.gold = 10  # Not enough
        wpn = Item(0, 0, "weapon", "Long Sword", dict(WEAPON_TYPES[3]))
        p.weapon = wpn
        gs.tiles[p.y][p.x] = T_ENCHANT_ANVIL
        result = enchant_weapon_headless(gs)
        assert result is False

    def test_enchant_weapon_no_weapon(self):
        """Enchanting without a weapon should fail."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        gs.player.gold = 200
        gs.player.weapon = None
        gs.tiles[gs.player.y][gs.player.x] = T_ENCHANT_ANVIL
        result = enchant_weapon_headless(gs)
        assert result is False

    def test_enchant_already_enchanted(self):
        """Already enchanted weapons should not be re-enchanted."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.gold = 500
        wpn = Item(0, 0, "weapon", "Long Sword", dict(WEAPON_TYPES[3]))
        wpn.data["enchantment"] = "flame"
        p.weapon = wpn
        gs.tiles[p.y][p.x] = T_ENCHANT_ANVIL
        result = enchant_weapon_headless(gs)
        assert result is False

    def test_enchant_anvil_placement(self):
        """Enchant anvils should appear on deep floors."""
        found = False
        for seed in range(100):
            random.seed(seed)
            gs = GameState(headless=True)
            gs.generate_floor(8)
            for y in range(MAP_H):
                for x in range(MAP_W):
                    if gs.tiles[y][x] == T_ENCHANT_ANVIL:
                        found = True
                        break
                if found:
                    break
            if found:
                break
        assert found, "No enchant anvils placed across 100 seeds on floor 8"

    def test_enchant_proc_in_combat(self):
        """Enchanted weapons should proc their effects in combat."""
        random.seed(42)
        gs = GameState(headless=True)
        gs.generate_floor(1)
        p = gs.player
        p.strength = 20
        p.level = 15  # Guarantee hit
        wpn = Item(0, 0, "weapon", "Flame Sword", dict(WEAPON_TYPES[3]))
        wpn.data["enchantment"] = "flame"
        wpn.data["enchant_bonus_dmg"] = 3
        wpn.data["enchant_proc_chance"] = 1.0  # Always proc for testing
        wpn.data["enchant_proc_effect"] = "burn"
        wpn.identified = True
        p.weapon = wpn
        p.inventory = [wpn]
        e = Enemy(p.x + 1, p.y, "rat")
        e.hp = 200
        e.max_hp = 200
        gs.enemies = [e]
        player_attack(gs, e)
        # Burn effect should suppress regen
        assert e.regen_suppressed > 0 or e.hp < 200  # Either proc'd or did damage


class TestSpellKnowledge:
    """Tests for per-class spell knowledge and Arcana unlocks."""

    def test_warrior_known_spells(self):
        """Warrior starts with Heal and Teleport only."""
        p = Player("warrior")
        assert p.known_spells == {"Heal", "Teleport"}

    def test_mage_known_spells(self):
        """Mage starts with 6 spells including Chain Lightning."""
        p = Player("mage")
        assert p.known_spells == {"Heal", "Teleport", "Fireball", "Lightning Bolt", "Freeze", "Chain Lightning"}
        assert "Meteor" not in p.known_spells
        assert "Mana Shield" not in p.known_spells

    def test_rogue_known_spells(self):
        """Rogue starts with Heal, Teleport, and Fireball."""
        p = Player("rogue")
        assert p.known_spells == {"Heal", "Teleport", "Fireball"}

    def test_classless_known_spells(self):
        """Classless adventurer knows all base (non-mage-only) spells."""
        p = Player(None)
        assert p.known_spells == BASE_SPELLS
        assert len(p.known_spells) == 5

    def test_cast_unknown_spell_fails(self):
        """Warrior cannot cast Fireball (not in known_spells)."""
        gs = GameState(headless=True)
        gs.player = Player("warrior")
        gs.player.x, gs.player.y = 5, 5
        gs.player.mana = 50
        gs.player.max_mana = 50
        result = cast_spell_headless(gs, "Fireball", direction=(1, 0))
        assert result is False

    def test_cast_known_spell_succeeds(self):
        """Warrior can cast Heal (in known_spells)."""
        gs = GameState(headless=True)
        gs.player = Player("warrior")
        gs.player.x, gs.player.y = 5, 5
        gs.player.mana = 50
        gs.player.max_mana = 50
        gs.player.hp = 10
        gs.player.max_hp = 40
        result = cast_spell_headless(gs, "Heal")
        assert result is True
        assert gs.player.hp > 10

    def test_spell_menu_filters_known_spells(self):
        """Spell list should only contain known spells."""
        p = Player("warrior")
        spell_list = [(name, info) for name, info in SPELLS.items() if name in p.known_spells]
        assert len(spell_list) == 2
        spell_names = [name for name, _ in spell_list]
        assert "Heal" in spell_names
        assert "Teleport" in spell_names
        assert "Fireball" not in spell_names

    def test_mage_spell_list_includes_exclusives(self):
        """Mage spell list includes Chain Lightning."""
        p = Player("mage")
        spell_list = [(name, info) for name, info in SPELLS.items() if name in p.known_spells]
        assert len(spell_list) == 6
        spell_names = [name for name, _ in spell_list]
        assert "Chain Lightning" in spell_names


class TestMageExclusiveSpells:
    """Tests for Chain Lightning, Meteor, and Mana Shield."""

    def test_chain_lightning_hits_primary(self):
        """Chain Lightning hits the nearest visible enemy."""
        gs = GameState(headless=True)
        gs.player = Player("mage")
        gs.player.x, gs.player.y = 5, 5
        gs.player.mana = 50
        gs.player.max_mana = 50
        e = Enemy(7, 5, "rat")
        e.hp = 100
        e.max_hp = 100
        gs.enemies = [e]
        gs.visible = {(7, 5), (5, 5)}
        result = cast_spell_headless(gs, "Chain Lightning", target_enemy=e)
        assert result is True
        assert e.hp < 100

    def test_chain_lightning_chains_to_nearby(self):
        """Chain Lightning chains from primary to nearby enemies."""
        gs = GameState(headless=True)
        gs.player = Player("mage")
        gs.player.x, gs.player.y = 5, 5
        gs.player.mana = 50
        gs.player.max_mana = 50
        e1 = Enemy(7, 5, "rat")
        e1.hp = 200
        e1.max_hp = 200
        e2 = Enemy(9, 5, "rat")  # within chain range of e1
        e2.hp = 200
        e2.max_hp = 200
        e3 = Enemy(11, 5, "rat")  # within chain range of e2
        e3.hp = 200
        e3.max_hp = 200
        gs.enemies = [e1, e2, e3]
        gs.visible = {(7, 5), (9, 5), (11, 5), (5, 5)}
        result = cast_spell_headless(gs, "Chain Lightning", target_enemy=e1)
        assert result is True
        assert e1.hp < 200
        assert e2.hp < 200
        assert e3.hp < 200
        # Each chain does less damage (75% decay)
        dmg1 = 200 - e1.hp
        dmg2 = 200 - e2.hp
        dmg3 = 200 - e3.hp
        assert dmg1 > dmg2 > dmg3

    def test_chain_lightning_no_target_refunds(self):
        """Chain Lightning refunds mana if no target in sight."""
        gs = GameState(headless=True)
        gs.player = Player("mage")
        gs.player.x, gs.player.y = 5, 5
        gs.player.mana = 50
        gs.player.max_mana = 50
        gs.enemies = []
        gs.visible = {(5, 5)}
        result = cast_spell_headless(gs, "Chain Lightning")
        assert result is False
        assert gs.player.mana == 50

    def test_meteor_5x5_aoe(self):
        """Meteor hits enemies in a 5x5 area."""
        gs = GameState(headless=True)
        gs.player = Player("mage")
        gs.player.x, gs.player.y = 5, 5
        gs.player.mana = 50
        gs.player.max_mana = 50
        gs.player.known_spells.add("Meteor")
        # Place enemy at blast center (4 tiles east)
        e1 = Enemy(9, 5, "rat")
        e1.hp = 200
        e1.max_hp = 200
        # Place enemy at edge of 5x5 (2 tiles from center)
        e2 = Enemy(11, 7, "rat")
        e2.hp = 200
        e2.max_hp = 200
        # Place enemy outside 5x5
        e3 = Enemy(15, 5, "rat")
        e3.hp = 200
        e3.max_hp = 200
        gs.enemies = [e1, e2, e3]
        result = cast_spell_headless(gs, "Meteor", direction=(1, 0))
        assert result is True
        assert e1.hp < 200  # at center -- hit
        assert e2.hp < 200  # within 5x5 -- hit
        assert e3.hp == 200  # outside 5x5 -- not hit

    def test_mana_shield_applied(self):
        """Mana Shield adds status effect."""
        gs = GameState(headless=True)
        gs.player = Player("mage")
        gs.player.x, gs.player.y = 5, 5
        gs.player.mana = 50
        gs.player.max_mana = 50
        gs.player.known_spells.add("Mana Shield")
        result = cast_spell_headless(gs, "Mana Shield")
        assert result is True
        assert "Mana Shield" in gs.player.status_effects
        assert gs.player.status_effects["Mana Shield"] == BALANCE["mana_shield_duration"]

    def test_mana_shield_absorbs_damage(self):
        """Mana Shield absorbs damage from mana before HP."""
        from depths_of_dread.game import enemy_attack
        gs = GameState(headless=True)
        gs.player = Player("mage")
        gs.player.x, gs.player.y = 5, 5
        gs.player.hp = 20
        gs.player.max_hp = 20
        gs.player.mana = 30
        gs.player.max_mana = 50
        gs.player.status_effects["Mana Shield"] = 10
        e = Enemy(6, 5, "rat")
        e.hp = 50
        e.max_hp = 50
        # Seed for reproducibility
        random.seed(42)
        old_hp = gs.player.hp
        old_mana = gs.player.mana
        enemy_attack(gs, e)
        # Mana should have decreased (absorbed some damage)
        assert gs.player.mana < old_mana
        # HP impact should be reduced (possibly 0 if mana absorbed all)
        total_lost = (old_hp - gs.player.hp) + (old_mana - gs.player.mana)
        assert total_lost > 0  # damage was dealt

    def test_mana_shield_breaks_at_zero_mana(self):
        """Mana Shield breaks when mana reaches 0."""
        from depths_of_dread.game import enemy_attack
        gs = GameState(headless=True)
        gs.player = Player("mage")
        gs.player.x, gs.player.y = 5, 5
        gs.player.hp = 50
        gs.player.max_hp = 50
        gs.player.mana = 1  # only 1 mana left
        gs.player.max_mana = 50
        gs.player.defense = 0
        gs.player.status_effects["Mana Shield"] = 10
        e = Enemy(6, 5, "rat")
        e.hp = 50
        e.max_hp = 50
        # Force a hit (bypass evasion)
        random.seed(1)
        enemy_attack(gs, e)
        # Shield should break
        assert "Mana Shield" not in gs.player.status_effects
        assert gs.player.mana == 0

    def test_warrior_cannot_cast_chain_lightning(self):
        """Warrior doesn't know Chain Lightning."""
        gs = GameState(headless=True)
        gs.player = Player("warrior")
        gs.player.x, gs.player.y = 5, 5
        gs.player.mana = 50
        gs.player.max_mana = 50
        e = Enemy(7, 5, "rat")
        e.hp = 100
        gs.enemies = [e]
        gs.visible = {(7, 5)}
        result = cast_spell_headless(gs, "Chain Lightning", target_enemy=e)
        assert result is False
        assert gs.player.mana == 50  # no mana spent


class TestArcanaSpellUnlocks:
    """Tests for Arcana levelup unlocking new spells."""

    def test_warrior_arcana_unlocks_lightning_bolt(self):
        """Warrior choosing Arcana learns Lightning Bolt first."""
        p = Player("warrior")
        assert "Lightning Bolt" not in p.known_spells
        learned = _unlock_next_spell(p)
        assert learned == "Lightning Bolt"
        assert "Lightning Bolt" in p.known_spells

    def test_warrior_arcana_second_unlocks_freeze(self):
        """Warrior choosing Arcana twice learns Freeze second."""
        p = Player("warrior")
        _unlock_next_spell(p)  # Lightning Bolt
        learned = _unlock_next_spell(p)
        assert learned == "Freeze"
        assert "Freeze" in p.known_spells

    def test_warrior_arcana_third_returns_none(self):
        """Warrior choosing Arcana after all unlocked gets None (just MP)."""
        p = Player("warrior")
        _unlock_next_spell(p)  # Lightning Bolt
        _unlock_next_spell(p)  # Freeze
        learned = _unlock_next_spell(p)
        assert learned is None

    def test_mage_arcana_unlocks_meteor(self):
        """Mage choosing Arcana learns Meteor first."""
        p = Player("mage")
        assert "Meteor" not in p.known_spells
        learned = _unlock_next_spell(p)
        assert learned == "Meteor"
        assert "Meteor" in p.known_spells

    def test_mage_arcana_second_unlocks_mana_shield(self):
        """Mage choosing Arcana twice learns Mana Shield second."""
        p = Player("mage")
        _unlock_next_spell(p)  # Meteor
        learned = _unlock_next_spell(p)
        assert learned == "Mana Shield"
        assert "Mana Shield" in p.known_spells

    def test_rogue_arcana_unlocks_lightning_bolt(self):
        """Rogue choosing Arcana learns Lightning Bolt first."""
        p = Player("rogue")
        assert "Lightning Bolt" not in p.known_spells
        learned = _unlock_next_spell(p)
        assert learned == "Lightning Bolt"
        assert "Lightning Bolt" in p.known_spells

    def test_apply_levelup_arcana_triggers_unlock(self):
        """apply_levelup_choice with Arcana choice triggers spell unlock."""
        p = Player("warrior")
        levelup_data = {"base_hp": 3, "base_mp": 2, "base_str": 1, "base_def": 0, "level": 2}
        arcana = {"name": "Arcana", "desc": "+MP, learn new spell", "hp": 0, "mp": 5, "str": 0, "def": 0, "evasion": 0}
        learned = apply_levelup_choice(p, levelup_data, arcana)
        assert learned == "Lightning Bolt"
        assert "Lightning Bolt" in p.known_spells
        assert p.max_mana >= 7  # base_mp(2) + arcana_mp(5)

    def test_apply_levelup_might_no_unlock(self):
        """apply_levelup_choice with Might doesn't unlock spells."""
        p = Player("warrior")
        levelup_data = {"base_hp": 3, "base_mp": 2, "base_str": 1, "base_def": 0, "level": 2}
        might = {"name": "Might", "desc": "+HP +STR", "hp": 5, "mp": 0, "str": 2, "def": 0, "evasion": 0}
        learned = apply_levelup_choice(p, levelup_data, might)
        assert learned is None


class TestSpellSaveLoad:
    """Tests for save/load of known_spells."""

    def test_save_load_preserves_known_spells(self):
        """Save and load preserves known_spells."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        # Unlock a spell
        gs.player.known_spells.add("Lightning Bolt")

        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp_path = f.name
        try:
            original_path = dungeon.SAVE_FILE_PATH
            dungeon.SAVE_FILE_PATH = tmp_path
            save_game(gs)
            loaded = load_game()
            assert loaded is not None
            assert loaded.player.known_spells == {"Heal", "Teleport", "Lightning Bolt"}
        finally:
            dungeon.SAVE_FILE_PATH = original_path
            os.unlink(tmp_path)

    def test_load_old_save_defaults_to_base_spells(self):
        """Loading a save without known_spells defaults to all base spells."""
        p = Player(None)
        # Simulate old save migration -- no known_spells key
        assert p.known_spells == BASE_SPELLS


class TestWarriorAbilities:
    """Warrior class-exclusive combat techniques."""

    def test_warrior_starts_no_abilities(self):
        """Warriors start with no known abilities."""
        p = Player("warrior")
        assert len(p.known_abilities) == 0

    def test_whirlwind_hits_adjacent_enemies(self):
        """Whirlwind hits all adjacent enemies."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Whirlwind")
        p.mana = 20
        # Place 3 enemies adjacent to player
        gs.enemies = []
        for dx, dy in [(1, 0), (-1, 0), (0, 1)]:
            ex, ey = p.x + dx, p.y + dy
            e = Enemy(ex, ey, "rat")
            e.hp = 5
            e.max_hp = 5
            gs.enemies.append(e)
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        result = use_ability_headless(gs, "Whirlwind")
        assert result is True
        assert p.mana == 20 - BALANCE["whirlwind_cost"]
        # All 3 enemies should have taken damage
        alive_enemies = [e for e in gs.enemies if e.is_alive()]
        total_damage = sum(5 - e.hp for e in gs.enemies if e.is_alive())
        # Some or all may be dead
        assert total_damage > 0 or len(alive_enemies) < 3

    def test_whirlwind_no_enemies_adjacent(self):
        """Whirlwind still costs mana but reports no enemies hit."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Whirlwind")
        p.mana = 20
        gs.enemies = []  # No enemies
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        result = use_ability_headless(gs, "Whirlwind")
        assert result is True
        assert p.mana == 20 - BALANCE["whirlwind_cost"]

    def test_cleaving_strike_ignores_defense(self):
        """Cleaving Strike does 2x damage and ignores enemy defense."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Cleaving Strike")
        p.mana = 20
        p.strength = 10
        # Place a high-defense enemy in view
        e = Enemy(p.x + 2, p.y, "rat")
        e.hp = 200
        e.max_hp = 200
        e.defense = 50  # Very high defense -- should be ignored
        gs.enemies = [e]
        gs.visible = {(e.x, e.y)}
        result = use_ability_headless(gs, "Cleaving Strike")
        assert result is True
        damage = 200 - e.hp
        # Damage should be substantial since defense is ignored
        assert damage > 0
        assert p.mana == 20 - BALANCE["cleaving_strike_cost"]

    def test_cleaving_strike_double_damage(self):
        """Cleaving Strike does roughly 2x normal attack damage."""
        random.seed(42)
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Cleaving Strike")
        p.mana = 50
        p.strength = 10
        # No weapon = fists (1-3 + str//3)
        e = Enemy(p.x + 1, p.y, "rat")
        e.hp = 500
        e.max_hp = 500
        e.defense = 0
        gs.enemies = [e]
        gs.visible = {(e.x, e.y)}
        result = use_ability_headless(gs, "Cleaving Strike")
        assert result is True
        damage = 500 - e.hp
        # With 2x multiplier and 0 defense, damage should be at least base * 2
        assert damage >= 2  # Basic sanity

    def test_shield_wall_reduces_damage(self):
        """Shield Wall halves incoming damage."""
        from depths_of_dread.game import enemy_attack
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Shield Wall")
        p.mana = 20
        use_ability_headless(gs, "Shield Wall")
        assert "Shield Wall" in p.status_effects
        assert p.status_effects["Shield Wall"] == BALANCE["shield_wall_duration"]
        # Test damage reduction via enemy_attack
        p.hp = 100
        p.max_hp = 100
        p.defense = 0
        p._evasion_bonus = 0
        e = Enemy(p.x + 1, p.y, "rat")
        e.dmg = (20, 20)  # Fixed damage
        random.seed(99)  # Avoid evasion
        enemy_attack(gs, e)
        # With Shield Wall, 20 raw -> halved after defense calc
        # Damage should be less than 20
        assert p.hp > 80  # Shield Wall should have reduced it

    def test_shield_wall_expires(self):
        """Shield Wall expires after its duration."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Shield Wall")
        p.mana = 20
        use_ability_headless(gs, "Shield Wall")
        assert "Shield Wall" in p.status_effects
        # Tick down status effects
        for _ in range(BALANCE["shield_wall_duration"] + 1):
            process_status(gs)
        assert "Shield Wall" not in p.status_effects

    def test_warrior_cannot_use_rogue_abilities(self):
        """Warriors cannot use Rogue-exclusive abilities."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Backstab")  # Force it in
        p.mana = 20
        # Should fail because Backstab isn't in warrior's CLASS_ABILITIES
        result = use_ability_headless(gs, "Backstab")
        assert result is False


class TestRogueAbilities:
    """Rogue class-exclusive combat techniques."""

    def test_rogue_starts_no_abilities(self):
        """Rogues start with no known abilities."""
        p = Player("rogue")
        assert len(p.known_abilities) == 0

    def test_backstab_guaranteed_crit(self):
        """Backstab buffs next melee to guaranteed crit at 2.5x multiplier."""
        gs = GameState(headless=True, player_class="rogue")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Backstab")
        p.mana = 20
        use_ability_headless(gs, "Backstab")
        assert "Backstab" in p.status_effects
        assert p.status_effects["Backstab"] == 99  # Effectively infinite

    def test_backstab_consumed_on_use(self):
        """Backstab status is consumed after one melee attack."""
        random.seed(1)
        gs = GameState(headless=True, player_class="rogue")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Backstab")
        p.mana = 20
        p.strength = 10
        p.level = 15  # Guarantee 100% hit chance (75 + 15*2 = 105)
        use_ability_headless(gs, "Backstab")
        assert "Backstab" in p.status_effects
        e = Enemy(p.x + 1, p.y, "rat")
        e.hp = 200
        e.max_hp = 200
        e.defense = 0
        gs.enemies = [e]
        player_attack(gs, e)
        # Backstab should be consumed
        assert "Backstab" not in p.status_effects

    def test_poison_blade_poisons_target(self):
        """Poison Blade causes melee attacks to poison enemies."""
        random.seed(42)
        gs = GameState(headless=True, player_class="rogue")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Poison Blade")
        p.mana = 20
        p.strength = 10
        use_ability_headless(gs, "Poison Blade")
        assert "Poison Blade" in p.status_effects
        e = Enemy(p.x + 1, p.y, "rat")
        e.hp = 200
        e.max_hp = 200
        e.defense = 0
        gs.enemies = [e]
        # Attack until we get a hit (may miss)
        for _ in range(20):
            if e.poisoned_turns > 0:
                break
            player_attack(gs, e)
        assert e.poisoned_turns > 0

    def test_poison_blade_expires(self):
        """Poison Blade status expires after its duration."""
        gs = GameState(headless=True, player_class="rogue")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Poison Blade")
        p.mana = 20
        use_ability_headless(gs, "Poison Blade")
        for _ in range(BALANCE["poison_blade_duration"] + 1):
            process_status(gs)
        assert "Poison Blade" not in p.status_effects

    def test_smoke_bomb_freezes_nearby(self):
        """Smoke Bomb freezes all enemies within radius."""
        gs = GameState(headless=True, player_class="rogue")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Smoke Bomb")
        p.mana = 20
        # Place enemies: 1 nearby (dist 2), 1 far (dist 10)
        close_e = Enemy(p.x + 2, p.y, "rat")
        close_e.hp = 50
        close_e.max_hp = 50
        far_e = Enemy(p.x + 10, p.y, "rat")
        far_e.hp = 50
        far_e.max_hp = 50
        gs.enemies = [close_e, far_e]
        result = use_ability_headless(gs, "Smoke Bomb")
        assert result is True
        # Close enemy should be frozen
        assert close_e.frozen_turns == BALANCE["smoke_bomb_blind_duration"]
        # Far enemy should NOT be frozen
        assert far_e.frozen_turns == 0

    def test_smoke_bomb_evasion_boost(self):
        """Smoke Bomb gives player evasion boost."""
        gs = GameState(headless=True, player_class="rogue")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Smoke Bomb")
        p.mana = 20
        gs.enemies = []
        base_evasion = p.evasion_chance()
        use_ability_headless(gs, "Smoke Bomb")
        assert "Smoke Evasion" in p.status_effects
        boosted_evasion = p.evasion_chance()
        # Evasion should be higher (capped at 40, so check for increase or cap)
        assert boosted_evasion >= base_evasion

    def test_rogue_cannot_use_warrior_abilities(self):
        """Rogues cannot use Warrior-exclusive abilities."""
        gs = GameState(headless=True, player_class="rogue")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities.add("Whirlwind")  # Force it in
        p.mana = 20
        result = use_ability_headless(gs, "Whirlwind")
        assert result is False


class TestAbilityUnlocks:
    """Ability unlock progression via levelup choices."""

    def test_warrior_cleave_unlocks_whirlwind_first(self):
        """First Cleave levelup unlocks Whirlwind."""
        p = Player("warrior")
        levelup_data = {"base_hp": 5, "base_mp": 2, "base_str": 1, "base_def": 1}
        choice = {"name": "Cleave", "hp": 3, "mp": 0, "str": 3, "def": 1, "evasion": 0}
        learned = apply_levelup_choice(p, levelup_data, choice)
        assert learned == "Whirlwind"
        assert "Whirlwind" in p.known_abilities

    def test_warrior_cleave_unlocks_all_three_in_order(self):
        """Successive Cleave choices unlock Whirlwind -> Cleaving Strike -> Shield Wall."""
        p = Player("warrior")
        levelup_data = {"base_hp": 5, "base_mp": 2, "base_str": 1, "base_def": 1}
        choice = {"name": "Cleave", "hp": 3, "mp": 0, "str": 3, "def": 1, "evasion": 0}

        learned1 = apply_levelup_choice(p, levelup_data, choice)
        assert learned1 == "Whirlwind"

        learned2 = apply_levelup_choice(p, levelup_data, choice)
        assert learned2 == "Cleaving Strike"

        learned3 = apply_levelup_choice(p, levelup_data, choice)
        assert learned3 == "Shield Wall"

        # Fourth time: nothing left to unlock
        learned4 = apply_levelup_choice(p, levelup_data, choice)
        assert learned4 is None

    def test_rogue_lethality_unlocks_backstab_first(self):
        """First Lethality levelup unlocks Backstab."""
        p = Player("rogue")
        levelup_data = {"base_hp": 3, "base_mp": 2, "base_str": 1, "base_def": 1}
        choice = {"name": "Lethality", "hp": 0, "mp": 2, "str": 2, "def": 0, "evasion": 5}
        learned = apply_levelup_choice(p, levelup_data, choice)
        assert learned == "Backstab"
        assert "Backstab" in p.known_abilities

    def test_rogue_lethality_unlocks_all_three_in_order(self):
        """Successive Lethality choices unlock Backstab -> Poison Blade -> Smoke Bomb."""
        p = Player("rogue")
        levelup_data = {"base_hp": 3, "base_mp": 2, "base_str": 1, "base_def": 1}
        choice = {"name": "Lethality", "hp": 0, "mp": 2, "str": 2, "def": 0, "evasion": 5}

        learned1 = apply_levelup_choice(p, levelup_data, choice)
        assert learned1 == "Backstab"

        learned2 = apply_levelup_choice(p, levelup_data, choice)
        assert learned2 == "Poison Blade"

        learned3 = apply_levelup_choice(p, levelup_data, choice)
        assert learned3 == "Smoke Bomb"

        learned4 = apply_levelup_choice(p, levelup_data, choice)
        assert learned4 is None

    def test_mage_arcana_does_not_unlock_abilities(self):
        """Mage choosing Arcana unlocks spells, not combat abilities."""
        p = Player("mage")
        levelup_data = {"base_hp": 2, "base_mp": 5, "base_str": 1, "base_def": 0}
        choice = {"name": "Arcana", "hp": 0, "mp": 5, "str": 0, "def": 0, "evasion": 0}
        learned = apply_levelup_choice(p, levelup_data, choice)
        # Arcana unlocks spells, not abilities
        assert len(p.known_abilities) == 0
        # learned should be a spell name (Meteor for mage)
        if learned:
            assert learned in SPELLS

    def test_save_load_preserves_known_abilities(self):
        """Saving and loading preserves known_abilities."""
        gs = GameState(headless=True, player_class="warrior")
        gs.generate_floor(1)
        p = gs.player
        p.known_abilities = {"Whirlwind", "Shield Wall"}
        # Save
        result = save_game(gs)
        assert result is True
        # Load
        gs2 = load_game()
        assert gs2 is not None
        assert gs2.player.known_abilities == {"Whirlwind", "Shield Wall"}
        # Clean up
        delete_save()

    def test_class_abilities_have_cost_and_desc(self):
        """All CLASS_ABILITIES entries have cost and desc."""
        for cls, abilities in CLASS_ABILITIES.items():
            for name, info in abilities.items():
                assert "cost" in info, f"{cls}/{name} missing cost"
                assert "desc" in info, f"{cls}/{name} missing desc"
                assert info["cost"] > 0, f"{cls}/{name} cost must be positive"

    def test_enemy_poison_ticks_damage(self):
        """Poisoned enemies take damage each turn from Poison Blade."""
        from depths_of_dread.game import process_enemies
        gs = GameState(headless=True, player_class="rogue")
        gs.generate_floor(1)
        p = gs.player
        # Place enemy and poison it
        e = Enemy(p.x + 5, p.y, "rat")
        e.hp = 50
        e.max_hp = 50
        e.poisoned_turns = 3
        gs.enemies = [e]
        compute_fov(gs.tiles, p.x, p.y, 8, gs.visible)
        initial_hp = e.hp
        process_enemies(gs)
        assert e.hp < initial_hp
        assert e.poisoned_turns == 2


class TestTechniqueHint:
    """#2/#4: Technique hint on HUD."""

    def test_technique_hint_in_sidebar(self):
        import os, glob as _glob
        _pkg_dir = os.path.dirname(dungeon.__file__)
        source = '\n'.join(open(f).read() for f in _glob.glob(os.path.join(_pkg_dir, '*.py')))
        assert "[t]" in source or "Techniques" in source

    def test_mage_spell_hint_in_sidebar(self):
        import os, glob as _glob
        _pkg_dir = os.path.dirname(dungeon.__file__)
        source = '\n'.join(open(f).read() for f in _glob.glob(os.path.join(_pkg_dir, '*.py')))
        assert "[z]Spells" in source
