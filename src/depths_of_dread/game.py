#!/usr/bin/env python3
"""
DEPTHS OF DREAD - A Terminal Roguelike
======================================
Fifteen floors of darkness beneath Thornhaven.
Slay the Dread Lord or die trying.

Built for someone who grew up on NetHack, Rogue, and BBS door games.
Pure Python curses. No external dependencies.

Controls: WASD / Arrows / hjklyubn (vi keys)
  f: Fire projectile (then direction)
  z: Cast spell
"""

import curses
import random
# math — available if needed but not currently used
import time
import sys
import heapq
import json
import hashlib
import os
from pathlib import Path
from collections import deque
import argparse
import datetime
import subprocess
# threading — available if needed but not currently used

# Agent-commons: universal agentic testing framework (optional)
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'agent-commons'))
    from agent_commons import (
        ProgressStallDetector, ActionRepetitionDetector, ResourceBudgetMonitor,
        DecisionTrace, StateSnapshotManager, ActionDistribution,
        StructuredOutputValidator, StallRecoveryManager,
        FeatureCoverageTracker, NoveltySeekerBias, DREAD_FEATURES,
        PostRunSummaryReport, DeathAutopsy,
        CallBudgetManager, TriggerDeduplicator,
    )
    HAS_AGENT_COMMONS = True
except ImportError:
    HAS_AGENT_COMMONS = False

# ============================================================
# CONSTANTS
# ============================================================

MAP_W = 80
MAP_H = 40
SCREEN_W = 80
SCREEN_H = 24
VIEW_W = 58
VIEW_H = 20
MSG_H = 3
STAT_X = 59
MAX_FLOORS = 15
MAX_MESSAGES = 50
FOV_RADIUS = 8
MAX_INVENTORY = 20
TORCH_MAX_FUEL = 200
TORCH_RADIUS_FULL = 8    # fuel > 50%
TORCH_RADIUS_HALF = 6    # fuel 25-50%
TORCH_RADIUS_QUARTER = 4 # fuel 1-25%
TORCH_RADIUS_EMPTY = 2   # fuel == 0
MANA_REGEN_INTERVAL = 5  # regen 1 mana every N turns
AUTO_FIGHT_HP_THRESHOLD = 0.3  # stop auto-fight when HP below 30% of max
AUTO_EXPLORE_HP_THRESHOLD = 0.5  # stop auto-explore when HP below 50%
REST_HUNGER_THRESHOLD = 20  # stop resting when hunger below 20%
SAVE_FILE_PATH = os.path.expanduser("~/.depths_of_dread_save.json")
STATS_FILE_PATH = os.path.expanduser("~/.depths_of_dread_stats.json")
RECORDINGS_DIR = os.path.expanduser("~/.depths_of_dread_recordings/")
AGENT_LOG_PATH = os.path.expanduser("~/.depths_of_dread_agent.log")
SIDEBAR_NAME_WIDTH = 18  # width for equipment names in sidebar
MIN_TERMINAL_W = 80
MIN_TERMINAL_H = 24

# ============================================================
# BALANCE TUNING — Edit these to adjust difficulty
# ============================================================
BALANCE = {
    # --- Item Spawn Weights (relative, auto-normalized) ---
    "item_weights": {
        "weapon": 14,
        "armor": 11,
        "potion": 18,
        "scroll": 14,
        "food": 22,        # Bumped from 17 — food was too scarce
        "ring": 8,         # Combined both ring slots (was 6+2)
        "bow": 4,
        "arrow": 4,
        "throwing_dagger": 3,
        "wand": 4,
        "torch": 3,
    },

    # --- Item Spawn Counts ---
    "items_base": 4,           # Base items per floor
    "items_per_floor": 1,      # Additional items per floor number
    "items_random_bonus": 3,   # Random 0..N extra items
    "guaranteed_food_min": 2,  # Guaranteed food per floor (was 1)
    "guaranteed_food_max": 3,  # Guaranteed food per floor (was 2)

    # --- Enemy Spawn Counts ---
    "enemies_base": 5,
    "enemies_per_floor": 2,
    "enemies_random_bonus": 3,
    "enemy_hp_scale_per_floor": 0.1,  # +10% HP per floor beyond min

    # --- Hunger System ---
    "hunger_per_move": 0.12,       # Was 0.15 — slightly slower depletion
    "hunger_curse_extra": 0.15,    # Extra depletion from Ring of Hunger
    "hunger_rest_cost": 0.1,       # Hunger lost per rest turn
    "starvation_damage": 1,        # HP per turn at hunger=0
    "rest_hunger_threshold": 20,   # Stop resting when hunger% < this

    # --- Combat ---
    "hit_chance_base": 75,
    "hit_chance_per_level": 2,
    "crit_chance_base": 0.10,
    "crit_chance_per_level": 0.02,
    "crit_multiplier": 1.8,
    "ranged_crit_chance": 0.08,
    "defense_divisor": 2,          # damage - (defense // divisor)
    "resistance_reduction": 2,     # Flat damage reduction from Resistance

    # --- Healing ---
    "heal_potion_min": 15,
    "heal_potion_max": 30,
    "heal_potion_level_scale": 2,  # +2 per level
    "heal_spell_min": 15,
    "heal_spell_max": 30,
    "heal_spell_level_scale": 2,

    # --- Rest ---
    "rest_hp_per_turn": 1,
    "rest_wait_hunger_cost": 0.1,  # Hunger cost per wait/rest turn

    # --- Spell Damage ---
    "fireball_min": 12,
    "fireball_max": 25,
    "fireball_level_scale": 1,
    "lightning_min": 15,
    "lightning_max": 30,
    "lightning_level_scale": 1,

    # --- Level Up ---
    "xp_base": 25,
    "xp_growth": 1.5,
    "hp_gain_min": 4,
    "hp_gain_max": 8,
    "mana_gain_min": 2,
    "mana_gain_max": 5,
    "str_gain": 1,
    "def_gain": 1,

    # --- Loot ---
    "enemy_item_drop_chance": 0.30,
    "enemy_gold_drop_chance": 0.50,
    "gold_drop_min": 3,
    "gold_drop_max": 10,
    "gold_per_floor_min": 5,      # Gold pile amounts
    "gold_per_floor_max": 15,
    "gold_piles_min": 2,
    "gold_piles_max": 5,

    # --- Shops ---
    "shop_items_min": 3,
    "shop_items_max": 5,
    "shop_food_price": 15,
    "shop_heal_base_price": 25,
    "shop_heal_floor_scale": 5,

    # --- Shrine ---
    "shrine_full_heal_chance": 0.30,
    "shrine_max_hp_chance": 0.20,
    "shrine_str_chance": 0.15,
    "shrine_def_chance": 0.15,
    "shrine_nothing_chance": 0.10,
    "shrine_curse_chance": 0.10,    # Remaining probability
    "shrine_curse_min_pct": 0.25,
    "shrine_curse_max_pct": 0.40,

    # --- Evasion ---
    "evasion_base": 5,
    "evasion_speed_bonus": 15,
    "evasion_cap": 40,

    # --- Status Effect Durations ---
    "strength_duration_base": 30,
    "strength_duration_level_scale": 5,
    "speed_duration_base": 20,
    "speed_duration_level_scale": 3,
    "blindness_duration": 15,
    "resistance_duration": 40,
    "berserk_duration": 20,
    "freeze_duration": 3,

    # --- New Status Effects (Phase 1: D&D Expansion) ---
    "poison_damage_per_tick": 2,
    "poison_duration": 8,
    "paralysis_duration": 3,
    "fear_duration": 6,

    # --- Mage-Exclusive Spells ---
    "chain_lightning_min": 10,
    "chain_lightning_max": 20,
    "chain_lightning_chain_range": 4,
    "chain_lightning_decay": 0.75,
    "meteor_min": 25,
    "meteor_max": 45,
    "meteor_level_scale": 2,
    "meteor_range": 4,
    "mana_shield_duration": 10,

    # --- Warrior Abilities ---
    "whirlwind_cost": 8,
    "cleaving_strike_cost": 10,
    "cleaving_strike_multiplier": 2.0,
    "shield_wall_cost": 6,
    "shield_wall_duration": 8,
    "shield_wall_reduction": 0.5,

    # --- Mage Class Ability (Arcane Blast) ---
    "arcane_blast_min": 15,
    "arcane_blast_max": 30,
    "battle_cry_cooldown": 15,
    "arcane_blast_cooldown": 12,
    "shadow_step_cooldown": 10,
    "ability_cooldown": 12,        # Default cooldown for class abilities (C key)

    # --- Rogue Abilities ---
    "backstab_cost": 6,
    "backstab_crit_multiplier": 2.5,
    "poison_blade_cost": 8,
    "poison_blade_duration": 10,
    "smoke_bomb_cost": 8,
    "smoke_bomb_blind_radius": 3,
    "smoke_bomb_blind_duration": 4,
    "smoke_bomb_evasion_duration": 6,
    "smoke_bomb_evasion_bonus": 20,

    # --- Wand Class Scaling (#8) ---
    "wand_mage_bonus_pct": 0.50,       # Mage: +50% wand damage
    "wand_mage_range_bonus": 2,        # Mage: +2 wand range
    "wand_warrior_penalty_pct": 0.25,  # Warrior: -25% wand damage

    # --- Boss Weapon Lifesteal (#20) ---
    "lifesteal_pct": 0.20,            # Heal 20% of damage dealt with lifesteal weapons

    # --- Elemental Resistance System ---
    "resist_reduction_pct": 0.50,     # 50% damage reduction when resistant
    "vulnerable_increase_pct": 1.50,  # 150% damage when vulnerable

    # --- Trap System ---
    "trap_base_count": 2,             # Min traps per floor
    "trap_per_floor": 0.5,            # Extra traps per floor depth
    "trap_detect_radius": 1,          # Tiles away for passive detection
    "trap_rogue_detect_bonus": 30,    # Rogue passive detect % bonus
    "trap_disarm_base": 40,           # Base disarm chance %
    "trap_disarm_dex_scale": 3,       # +3% per level for rogue

    # --- Stealth / Noise System ---
    "noise_floor_walk": 2,            # Walking on floor tile
    "noise_corridor_walk": 1,         # Walking on corridor
    "noise_door_open": 4,             # Opening a door
    "noise_combat": 8,                # Melee combat
    "noise_spell": 6,                 # Casting a spell
    "noise_rogue_reduction": 0.5,     # Rogue makes 50% less noise
    "noise_decay_per_tile": 1,        # Noise decays 1 per tile distance
    "stealth_asleep_crit_mult": 2.0,  # Backstab sleeping enemy = 2x damage
    "stealth_unwary_crit_mult": 1.5,  # Backstab unwary enemy = 1.5x damage
    "asleep_spawn_chance": 0.60,      # 60% of enemies spawn asleep
}

# Short alias for tight code paths
B = BALANCE

# Spell definitions
SPELLS = {
    "Fireball":          {"cost": 12, "desc": "3x3 AoE fire damage in a direction", "mage_only": False},
    "Lightning Bolt":    {"cost": 10, "desc": "Hits all enemies in a line", "mage_only": False},
    "Heal":              {"cost": 8,  "desc": "Restore HP", "mage_only": False},
    "Teleport":          {"cost": 6,  "desc": "Random safe tile on current floor", "mage_only": False},
    "Freeze":            {"cost": 10, "desc": "Target enemy skips 3 turns", "mage_only": False},
    "Chain Lightning":   {"cost": 14, "desc": "Hit nearest + chain to 2 more", "mage_only": True},
    "Meteor":            {"cost": 20, "desc": "5x5 AoE explosion at range", "mage_only": True},
    "Mana Shield":       {"cost": 10, "desc": "Absorb damage from mana (10 turns)", "mage_only": True},
}

# Base spells (non-mage-exclusive)
BASE_SPELLS = {name for name, info in SPELLS.items() if not info["mage_only"]}

# Default known spells per class
CLASS_KNOWN_SPELLS = {
    "warrior": {"Heal", "Teleport"},
    "mage":    {"Heal", "Teleport", "Fireball", "Lightning Bolt", "Freeze", "Chain Lightning"},
    "rogue":   {"Heal", "Teleport", "Fireball"},
}

# Spell unlock order when choosing Arcana at levelup
SPELL_UNLOCK_ORDER = {
    "warrior": ["Lightning Bolt", "Freeze"],
    "mage":    ["Meteor", "Mana Shield"],
    "rogue":   ["Lightning Bolt", "Freeze"],
    None:      [],  # classless already knows all base spells
}

# Class-exclusive combat abilities (Warrior/Rogue — parallel to Mage spells)
CLASS_ABILITIES = {
    "warrior": {
        "Whirlwind":       {"cost": 8,  "desc": "Hit all adjacent enemies"},
        "Cleaving Strike": {"cost": 10, "desc": "2x weapon damage, ignores defense"},
        "Shield Wall":     {"cost": 6,  "desc": "-50% incoming damage (8 turns)"},
    },
    "rogue": {
        "Backstab":        {"cost": 6,  "desc": "Next melee is guaranteed 2.5x crit"},
        "Poison Blade":    {"cost": 8,  "desc": "Melee attacks poison (10 turns)"},
        "Smoke Bomb":      {"cost": 8,  "desc": "Blind + freeze nearby, +evasion"},
    },
}

# Unlock order when choosing Cleave/Lethality at levelup
ABILITY_UNLOCK_ORDER = {
    "warrior": ["Whirlwind", "Cleaving Strike", "Shield Wall"],
    "rogue":   ["Backstab", "Poison Blade", "Smoke Bomb"],
    "mage":    [],
    None:      [],
}

# Character Classes (D&D Expansion Phase 1)
CHARACTER_CLASSES = {
    "warrior": {
        "name": "Warrior", "desc": "Tough frontline fighter with Battle Cry",
        "hp": 40, "mp": 10, "str": 7, "defense": 3,
        "crit_bonus": 0, "evasion_bonus": 0,
        "ability": "Battle Cry", "ability_desc": "Freeze all nearby enemies for 5 turns",
        "ability_cost": 8,
        "level_hp": (5, 10), "level_mp": (1, 3), "level_str": 2, "level_def": 1,
    },
    "mage": {
        "name": "Mage", "desc": "Glass cannon with powerful Arcane Blast",
        "hp": 20, "mp": 35, "str": 3, "defense": 0,
        "crit_bonus": 0, "evasion_bonus": 0,
        "ability": "Arcane Blast", "ability_desc": "3x3 AoE magical explosion at range",
        "ability_cost": 15,
        "level_hp": (2, 5), "level_mp": (3, 7), "level_str": 1, "level_def": 0,
    },
    "rogue": {
        "name": "Rogue", "desc": "Quick and deadly with Shadow Step",
        "hp": 25, "mp": 15, "str": 5, "defense": 1,
        "crit_bonus": 0.10, "evasion_bonus": 10,
        "ability": "Shadow Step", "ability_desc": "Teleport behind an enemy and auto-crit",
        "ability_cost": 10,
        "level_hp": (3, 6), "level_mp": (2, 4), "level_str": 1, "level_def": 1,
    },
}

# Tile types
T_WALL = 0
T_FLOOR = 1
T_CORRIDOR = 2
T_DOOR = 3
T_STAIRS_DOWN = 4
T_STAIRS_UP = 5
T_WATER = 6
T_LAVA = 7
T_SHOP_FLOOR = 8
T_SHRINE = 9
T_ALCHEMY_TABLE = 10
T_WALL_TORCH = 11
T_PEDESTAL_UNLIT = 12
T_PEDESTAL_LIT = 13
T_SWITCH_OFF = 14
T_SWITCH_ON = 15
T_STAIRS_LOCKED = 16
T_TRAP_HIDDEN = 17    # Invisible trap (renders as T_FLOOR)
T_TRAP_VISIBLE = 18   # Revealed trap (renders as '^')

TILE_CHARS = {
    T_WALL: '#', T_FLOOR: '.', T_CORRIDOR: '.', T_DOOR: '+',
    T_STAIRS_DOWN: '>', T_STAIRS_UP: '<', T_WATER: '~',
    T_LAVA: '~', T_SHOP_FLOOR: '.', T_SHRINE: '_',
    T_ALCHEMY_TABLE: '&', T_WALL_TORCH: '!',
    T_PEDESTAL_UNLIT: '*', T_PEDESTAL_LIT: '*',
    T_SWITCH_OFF: '!', T_SWITCH_ON: '$',
    T_STAIRS_LOCKED: 'X',
    T_TRAP_HIDDEN: '.',   # Looks like floor
    T_TRAP_VISIBLE: '^',  # Revealed trap
}

WALKABLE = {T_FLOOR, T_CORRIDOR, T_DOOR, T_STAIRS_DOWN, T_STAIRS_UP,
            T_WATER, T_SHOP_FLOOR, T_SHRINE, T_ALCHEMY_TABLE,
            T_PEDESTAL_UNLIT, T_PEDESTAL_LIT, T_SWITCH_OFF, T_SWITCH_ON,
            T_TRAP_HIDDEN, T_TRAP_VISIBLE}

THEMES = [
    "Dungeon", "Dungeon", "Dungeon",
    "Caverns", "Caverns", "Caverns",
    "Catacombs", "Catacombs", "Catacombs",
    "Hellvault", "Hellvault", "Hellvault",
    "Abyss", "Abyss", "The Throne of Dread",
]

# Dungeon Branch system — branching paths at floors 5 and 10
BRANCH_DEFS = {
    "flooded_crypts": {
        "name": "The Flooded Crypts",
        "desc": "Water-heavy, undead, cold damage",
        "theme": "Flooded Crypts",
        "floors": (6, 7, 8),
        "water_boost": 3.0,    # 3x more water tiles
        "lava_boost": 0.0,     # No lava
        "enemy_pool": ["skeleton", "wraith", "banshee", "rat", "bat"],
        "mini_boss_floor": 8,
        "mini_boss": "crypt_guardian",
    },
    "burning_pits": {
        "name": "The Burning Pits",
        "desc": "Lava-heavy, demons, fire damage",
        "theme": "Burning Pits",
        "floors": (6, 7, 8),
        "water_boost": 0.0,
        "lava_boost": 3.0,     # 3x more lava tiles
        "enemy_pool": ["demon", "fire_elemental", "orc", "goblin"],
        "mini_boss_floor": 8,
        "mini_boss": "flame_tyrant",
    },
    "mind_halls": {
        "name": "The Mind Halls",
        "desc": "Mind flayers, psychic, confusion",
        "theme": "Mind Halls",
        "floors": (11, 12, 13),
        "water_boost": 0.5,
        "lava_boost": 0.5,
        "enemy_pool": ["mind_flayer", "phase_spider", "wraith", "banshee"],
        "mini_boss_floor": 13,
        "mini_boss": "elder_brain",
    },
    "beast_warrens": {
        "name": "The Beast Warrens",
        "desc": "Pack enemies, traps, speed",
        "theme": "Beast Warrens",
        "floors": (11, 12, 13),
        "water_boost": 0.5,
        "lava_boost": 0.5,
        "enemy_pool": ["orc", "goblin", "rat", "centipede", "troll"],
        "extra_enemies": 5,     # More enemies per floor
        "extra_traps": 3,       # More traps per floor
        "mini_boss_floor": 13,
        "mini_boss": "beast_lord",
    },
}

# Branch choice mapping: floor → (branch_A, branch_B)
BRANCH_CHOICES = {
    5: ("flooded_crypts", "burning_pits"),
    10: ("mind_halls", "beast_warrens"),
}

# ============================================================
# COLOR PAIRS
# ============================================================
C_WHITE = 1
C_RED = 2
C_GREEN = 3
C_BLUE = 4
C_YELLOW = 5
C_MAGENTA = 6
C_CYAN = 7
C_DARK = 8
C_GOLD = 9
C_LAVA = 10
C_WATER = 11
C_PLAYER = 12
C_UI = 13
C_TITLE = 14
C_BOSS = 15
C_SHRINE = 16

HAS_COLORS = True  # set at runtime by init_colors

def init_colors():
    global HAS_COLORS
    if not curses.has_colors():
        HAS_COLORS = False
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_WHITE, curses.COLOR_WHITE, -1)
    curses.init_pair(C_RED, curses.COLOR_RED, -1)
    curses.init_pair(C_GREEN, curses.COLOR_GREEN, -1)
    curses.init_pair(C_BLUE, curses.COLOR_BLUE, -1)
    curses.init_pair(C_YELLOW, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_MAGENTA, curses.COLOR_MAGENTA, -1)
    curses.init_pair(C_CYAN, curses.COLOR_CYAN, -1)
    curses.init_pair(C_DARK, curses.COLOR_WHITE, -1)
    curses.init_pair(C_GOLD, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_LAVA, curses.COLOR_RED, -1)
    curses.init_pair(C_WATER, curses.COLOR_CYAN, -1)
    curses.init_pair(C_PLAYER, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(C_UI, curses.COLOR_CYAN, -1)
    curses.init_pair(C_TITLE, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_BOSS, curses.COLOR_RED, -1)
    curses.init_pair(C_SHRINE, curses.COLOR_YELLOW, -1)
    HAS_COLORS = True


def safe_color_pair(pair_num):
    """Return color pair attribute, falling back to A_BOLD/A_DIM when no colors."""
    if HAS_COLORS:
        return curses.color_pair(pair_num)
    # Fallback: map important pairs to bold/dim/underline
    if pair_num in (C_RED, C_BOSS, C_LAVA):
        return curses.A_BOLD
    elif pair_num in (C_DARK,):
        return curses.A_DIM
    elif pair_num in (C_TITLE, C_GOLD, C_YELLOW, C_SHRINE):
        return curses.A_UNDERLINE
    elif pair_num in (C_PLAYER,):
        return curses.A_REVERSE
    return curses.A_NORMAL

# ============================================================
# ITEM DATA
# ============================================================

WEAPON_TYPES = [
    {"name": "Rusty Dagger",    "char": ')', "dmg": (1,4),  "speed": 1.0, "bonus": 0, "desc": "Corroded but sharp.", "tier": 0},
    {"name": "Short Sword",     "char": ')', "dmg": (2,5),  "speed": 1.0, "bonus": 0, "desc": "A reliable sidearm.", "tier": 1},
    {"name": "Mace",            "char": ')', "dmg": (2,7),  "speed": 0.8, "bonus": 0, "desc": "Slow but crushing.", "tier": 1},
    {"name": "Long Sword",      "char": ')', "dmg": (3,8),  "speed": 1.0, "bonus": 1, "desc": "Well-balanced steel.", "tier": 2},
    {"name": "Battle Axe",      "char": ')', "dmg": (4,10), "speed": 0.7, "bonus": 1, "desc": "Cleaves through armor.", "tier": 2},
    {"name": "Rapier",          "char": ')', "dmg": (2,6),  "speed": 1.4, "bonus": 2, "desc": "Lightning-fast thrusts.", "tier": 2},
    {"name": "War Hammer",      "char": ')', "dmg": (5,12), "speed": 0.6, "bonus": 2, "desc": "Devastating but ponderous.", "tier": 3},
    {"name": "Katana",          "char": ')', "dmg": (4,9),  "speed": 1.2, "bonus": 3, "desc": "Folded steel, razor edge.", "tier": 3},
    {"name": "Flamebrand",      "char": ')', "dmg": (5,11), "speed": 1.0, "bonus": 4, "desc": "Burns with inner fire.", "tier": 4},
    {"name": "Vorpal Blade",    "char": ')', "dmg": (6,14), "speed": 1.1, "bonus": 5, "desc": "Snicker-snack.", "tier": 5},
]

# Boss-specific weapon drops (#20)
BOSS_DROPS = {
    "ogre_king": {"name": "Ogre King's Maul", "char": ')', "dmg": (8,16), "speed": 0.6, "bonus": 2, "desc": "Massive and devastating.", "tier": 5},
    "vampire_lord": {"name": "Vampiric Blade", "char": ')', "dmg": (6,14), "speed": 1.1, "bonus": 3, "desc": "Drains life with each strike.", "tier": 5, "lifesteal": True},
    "dread_lord": {"name": "Dread Lord's Bane", "char": ')', "dmg": (10,20), "speed": 1.0, "bonus": 5, "desc": "Forged from pure dread.", "tier": 5},
}

ARMOR_TYPES = [
    {"name": "Torn Rags",       "char": '[', "defense": 0,  "desc": "Barely clothing.", "tier": 0},
    {"name": "Leather Armor",   "char": '[', "defense": 2,  "desc": "Supple and light.", "tier": 1},
    {"name": "Studded Leather", "char": '[', "defense": 3,  "desc": "Reinforced with studs.", "tier": 1},
    {"name": "Chain Mail",      "char": '[', "defense": 5,  "desc": "Clinks with every step.", "tier": 2},
    {"name": "Scale Mail",      "char": '[', "defense": 6,  "desc": "Overlapping scales.", "tier": 2},
    {"name": "Plate Armor",     "char": '[', "defense": 8,  "desc": "Heavy but formidable.", "tier": 3},
    {"name": "Mithril Mail",    "char": '[', "defense": 7,  "desc": "Light as silk, hard as dragon scale.", "tier": 4},
    {"name": "Dread Plate",     "char": '[', "defense": 10, "desc": "Forged in the abyss.", "tier": 5},
]

POTION_EFFECTS = ["Healing", "Strength", "Speed", "Poison", "Blindness", "Experience", "Resistance", "Berserk"]
POTION_COLORS = ["Red", "Blue", "Green", "Murky", "Glowing", "Bubbling", "Shimmering", "Dark"]

SCROLL_EFFECTS = ["Identify", "Teleport", "Fireball", "Mapping", "Enchant", "Fear", "Summon", "Lightning"]
SCROLL_LABELS = ["XYZZY", "PLUGH", "ABRACADABRA", "KLAATU", "LOREM", "IPSUM", "NIHIL", "VERITAS"]

FOOD_TYPES = [
    {"name": "Stale Bread",   "char": '%', "nutrition": 15, "desc": "Hard but edible."},
    {"name": "Dried Meat",    "char": '%', "nutrition": 25, "desc": "Tough and salty."},
    {"name": "Elven Waybread","char": '%', "nutrition": 40, "desc": "Sustaining and light."},
    {"name": "Mystery Meat",  "char": '%', "nutrition": 20, "desc": "Don't ask."},
]

RING_TYPES = [
    {"name": "Ring of Protection", "char": '=', "effect": "defense", "value": 2, "desc": "+2 Defense"},
    {"name": "Ring of Strength",   "char": '=', "effect": "strength", "value": 2, "desc": "+2 Strength"},
    {"name": "Ring of Evasion",    "char": '=', "effect": "evasion", "value": 10, "desc": "+10% Evasion"},
    {"name": "Ring of Regeneration","char": '=', "effect": "regen", "value": 1, "desc": "Slow HP regen"},
    {"name": "Ring of Hunger",     "char": '=', "effect": "hunger", "value": -1, "desc": "Cursed! Faster hunger."},
    {"name": "Ring of Fire Resist",  "char": '=', "effect": "resist", "value": 0, "desc": "Resist fire damage.", "resists": ["fire"], "min_floor": 4},
    {"name": "Ring of Cold Resist",  "char": '=', "effect": "resist", "value": 0, "desc": "Resist cold damage.", "resists": ["cold"], "min_floor": 6},
    {"name": "Ring of Poison Resist","char": '=', "effect": "resist", "value": 0, "desc": "Resist poison damage.","resists": ["poison"], "min_floor": 3},
]

# Projectile / ranged item data
BOW_TYPES = [
    {"name": "Short Bow",   "char": '}', "dmg": (2,5),  "range": 6,  "bonus": 0, "desc": "Simple but functional.", "tier": 1},
    {"name": "Long Bow",    "char": '}', "dmg": (3,8),  "range": 8,  "bonus": 1, "desc": "Greater range and power.", "tier": 2},
    {"name": "Elven Bow",   "char": '}', "dmg": (4,10), "range": 10, "bonus": 3, "desc": "Whisper-light, deadly.", "tier": 4},
]

WAND_TYPES = [
    {"name": "Wand of Fire",      "char": '/', "dmg": (5,12),  "charges": 8,  "desc": "Shoots fire bolts.", "tier": 2},
    {"name": "Wand of Frost",     "char": '/', "dmg": (4,10),  "charges": 10, "desc": "Chilling bolts.", "tier": 2},
    {"name": "Wand of Lightning", "char": '/', "dmg": (6,15),  "charges": 5,  "desc": "Crackling energy.", "tier": 3},
]

TORCH_TYPES = [
    {"name": "Torch",        "char": '(', "fuel": 80,  "desc": "A wooden torch."},
    {"name": "Lantern Oil",  "char": '(', "fuel": 50,  "desc": "Oil for your light."},
    {"name": "Magic Candle", "char": '(', "fuel": 120, "desc": "Burns with arcane flame."},
]

THROWING_DAGGER = {"name": "Throwing Dagger", "char": ')', "dmg": (3,7), "desc": "Balanced for throwing.", "tier": 1}
ARROW_ITEM = {"name": "Arrow", "char": '|', "count": 5, "desc": "A bundle of arrows."}

# ============================================================
# ENEMY DATA
# ============================================================

ENEMY_TYPES = {
    "rat":         {"name": "Rat",          "char": 'r', "color": C_DARK,    "hp": 6,   "dmg": (1,3),  "defense": 0, "xp": 5,    "speed": 1.2, "ai": "chase",    "min_floor": 1,  "max_floor": 5,  "flee_threshold": 0.3},
    "bat":         {"name": "Bat",          "char": 'b', "color": C_MAGENTA, "hp": 4,   "dmg": (1,2),  "defense": 0, "xp": 3,    "speed": 1.5, "ai": "erratic",  "min_floor": 1,  "max_floor": 6,  "flee_threshold": 0.4},
    "goblin":      {"name": "Goblin",       "char": 'g', "color": C_GREEN,   "hp": 12,  "dmg": (2,5),  "defense": 1, "xp": 15,   "speed": 1.0, "ai": "chase",    "min_floor": 1,  "max_floor": 8,  "flee_threshold": 0.3},
    "skeleton":    {"name": "Skeleton",     "char": 's', "color": C_WHITE,   "hp": 18,  "dmg": (3,6),  "defense": 2, "xp": 25,   "speed": 0.8, "ai": "patrol",   "min_floor": 3,  "max_floor": 10, "flee_threshold": 0.0},
    "orc":         {"name": "Orc",          "char": 'o', "color": C_RED,     "hp": 25,  "dmg": (3,8),  "defense": 3, "xp": 35,   "speed": 0.9, "ai": "pack",     "min_floor": 4,  "max_floor": 11, "flee_threshold": 0.2},
    "wraith":      {"name": "Wraith",       "char": 'W', "color": C_CYAN,    "hp": 30,  "dmg": (4,8),  "defense": 2, "xp": 50,   "speed": 1.0, "ai": "ambush",   "min_floor": 6,  "max_floor": 13, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["cold", "poison"], "vulnerable": ["fire"]},
    "archer":      {"name": "Dark Archer",  "char": 'A', "color": C_YELLOW,  "hp": 20,  "dmg": (3,7),  "defense": 1, "xp": 40,   "speed": 1.0, "ai": "ranged",   "min_floor": 5,  "max_floor": 12, "flee_threshold": 0.35},
    "troll":       {"name": "Troll",        "char": 'T', "color": C_GREEN,   "hp": 45,  "dmg": (5,10), "defense": 4, "xp": 70,   "speed": 0.6, "ai": "chase",    "min_floor": 7,  "max_floor": 14, "regen": 1, "flee_threshold": 0.15, "vulnerable": ["fire"]},
    "demon":       {"name": "Demon",        "char": 'D', "color": C_RED,     "hp": 55,  "dmg": (6,12), "defense": 5, "xp": 100,  "speed": 1.0, "ai": "chase",    "min_floor": 10, "max_floor": 15, "flee_threshold": 0.1, "damage_type": "fire", "resists": ["fire"], "vulnerable": ["cold"]},
    "lich":        {"name": "Lich",         "char": 'L', "color": C_MAGENTA, "hp": 50,  "dmg": (5,10), "defense": 4, "xp": 120,  "speed": 0.9, "ai": "summoner", "min_floor": 11, "max_floor": 15, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["cold", "poison"]},
    "ogre_king":   {"name": "Ogre King",    "char": 'O', "color": C_BOSS,    "hp": 80,  "dmg": (6,14), "defense": 6, "xp": 200,  "speed": 0.7, "ai": "chase",    "min_floor": 5,  "max_floor": 5,  "boss": True, "flee_threshold": 0.0},
    "vampire_lord":{"name": "Vampire Lord", "char": 'V', "color": C_BOSS,    "hp": 100, "dmg": (7,13), "defense": 5, "xp": 350,  "speed": 1.1, "ai": "ambush",   "min_floor": 10, "max_floor": 10, "boss": True, "lifesteal": True, "flee_threshold": 0.0},
    "dread_lord":  {"name": "The Dread Lord","char": '&', "color": C_BOSS,    "hp": 200, "dmg": (10,20),"defense": 8, "xp": 1000, "speed": 1.0, "ai": "summoner", "min_floor": 15, "max_floor": 15, "boss": True, "regen": 2, "flee_threshold": 0.0},
    # --- Phase 1 D&D Expansion Monsters ---
    "centipede":     {"name": "Centipede",      "char": 'c', "color": C_GREEN,   "hp": 8,   "dmg": (1,3),  "defense": 0, "xp": 8,    "speed": 1.3, "ai": "chase",       "min_floor": 1,  "max_floor": 4,  "poison_chance": 0.30, "flee_threshold": 0.4, "damage_type": "poison", "resists": ["poison"]},
    "mimic":         {"name": "Mimic",          "char": '$', "color": C_GOLD,    "hp": 22,  "dmg": (3,7),  "defense": 2, "xp": 45,   "speed": 1.0, "ai": "mimic",       "min_floor": 3,  "max_floor": 10, "disguised": True, "flee_threshold": 0.0},
    "phase_spider":  {"name": "Phase Spider",   "char": 'S', "color": C_MAGENTA, "hp": 20,  "dmg": (3,6),  "defense": 1, "xp": 40,   "speed": 1.1, "ai": "phase",       "min_floor": 5,  "max_floor": 11, "poison_chance": 0.40, "phase_cooldown_max": 3, "flee_threshold": 0.25, "damage_type": "poison", "resists": ["poison"]},
    "fire_elemental":{"name": "Fire Elemental", "char": 'E', "color": C_LAVA,    "hp": 35,  "dmg": (4,9),  "defense": 3, "xp": 65,   "speed": 0.9, "ai": "chase",       "min_floor": 8,  "max_floor": 13, "fire_aura": True, "flee_threshold": 0.0, "damage_type": "fire", "resists": ["fire"], "vulnerable": ["cold"]},
    "banshee":       {"name": "Banshee",        "char": 'B', "color": C_CYAN,    "hp": 28,  "dmg": (4,8),  "defense": 2, "xp": 55,   "speed": 1.0, "ai": "ambush",      "min_floor": 7,  "max_floor": 12, "fear_chance": 0.50, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["cold"], "vulnerable": ["fire"]},
    "mind_flayer":   {"name": "Mind Flayer",    "char": 'M', "color": C_MAGENTA, "hp": 60,  "dmg": (5,11), "defense": 5, "xp": 130,  "speed": 0.9, "ai": "mind_flayer", "min_floor": 12, "max_floor": 15, "paralyze_chance": 0.30, "psychic_range": 6, "flee_threshold": 0.15, "resists": ["poison"]},
    # --- Branch Mini-Bosses ---
    "crypt_guardian":{"name": "Crypt Guardian", "char": 'G', "color": C_BOSS,  "hp": 90,  "dmg": (6,12), "defense": 6, "xp": 180,  "speed": 0.8, "ai": "chase",    "min_floor": 8,  "max_floor": 8,  "boss": True, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["cold", "poison"], "vulnerable": ["fire"]},
    "flame_tyrant":  {"name": "Flame Tyrant",  "char": 'F', "color": C_BOSS,  "hp": 95,  "dmg": (7,14), "defense": 5, "xp": 190,  "speed": 0.9, "ai": "chase",    "min_floor": 8,  "max_floor": 8,  "boss": True, "flee_threshold": 0.0, "fire_aura": True, "damage_type": "fire", "resists": ["fire"], "vulnerable": ["cold"]},
    "elder_brain":   {"name": "Elder Brain",   "char": 'B', "color": C_BOSS,  "hp": 110, "dmg": (6,13), "defense": 7, "xp": 220,  "speed": 0.7, "ai": "mind_flayer", "min_floor": 13, "max_floor": 13, "boss": True, "flee_threshold": 0.0, "paralyze_chance": 0.40, "psychic_range": 8, "resists": ["poison"]},
    "beast_lord":    {"name": "Beast Lord",    "char": 'B', "color": C_BOSS,  "hp": 100, "dmg": (7,15), "defense": 5, "xp": 200,  "speed": 1.2, "ai": "pack",     "min_floor": 13, "max_floor": 13, "boss": True, "flee_threshold": 0.0},
}

TRAP_TYPES = {
    "spike":    {"name": "Spike Trap",    "damage": (3, 8),  "effect": None,        "detect_dc": 12, "min_floor": 1},
    "dart":     {"name": "Dart Trap",     "damage": (2, 6),  "effect": "poison",    "detect_dc": 14, "min_floor": 3},
    "pit":      {"name": "Pit Trap",      "damage": (4, 10), "effect": "stun",      "detect_dc": 12, "min_floor": 2},
    "teleport": {"name": "Teleport Trap", "damage": (0, 0),  "effect": "teleport",  "detect_dc": 16, "min_floor": 5},
    "alarm":    {"name": "Alarm Trap",    "damage": (0, 0),  "effect": "alert_all", "detect_dc": 10, "min_floor": 1},
    "gas":      {"name": "Gas Trap",      "damage": (1, 3),  "effect": "confusion", "detect_dc": 18, "min_floor": 7},
}

DEATH_QUIPS = [
    "The dungeon claims another soul.",
    "Your bones join the countless others.",
    "Should have brought more potions.",
    "Another adventurer lost to hubris.",
    "The depths remain undefeated.",
    "Git gud.",
    "Perhaps the real treasure was the XP we lost along the way.",
    "You have been weighed, measured, and found wanting.",
]

# ============================================================
# CLASSES
# ============================================================

class Item:
    __slots__ = ['x', 'y', 'item_type', 'subtype', 'data', 'identified', 'equipped', 'count']
    def __init__(self, x, y, item_type, subtype, data):
        self.x = x
        self.y = y
        self.item_type = item_type
        self.subtype = subtype
        self.data = dict(data)
        self.identified = False
        self.equipped = False
        self.count = 1

    @property
    def char(self):
        if self.item_type == "gold":
            return '$'
        return self.data.get("char", '?')

    @property
    def color(self):
        return {"weapon": C_WHITE, "armor": C_BLUE, "potion": C_MAGENTA,
                "scroll": C_YELLOW, "gold": C_GOLD, "food": C_GREEN,
                "ring": C_CYAN, "bow": C_YELLOW, "arrow": C_WHITE,
                "throwing_dagger": C_WHITE, "wand": C_MAGENTA,
                "torch": C_YELLOW}.get(self.item_type, C_WHITE)

    @property
    def display_name(self):
        if self.item_type == "gold":
            return f"{self.data['amount']} gold"
        if self.item_type == "potion":
            if self.identified:
                return f"Potion of {self.data['effect']}"
            return f"{self.data['color_name']} Potion"
        if self.item_type == "scroll":
            if self.identified:
                return f"Scroll of {self.data['effect']}"
            return f"Scroll \"{self.data['label']}\""
        if self.item_type == "arrow":
            return f"Arrows (x{self.count})"
        if self.item_type == "throwing_dagger":
            return f"Throwing Dagger (x{self.count})"
        if self.item_type == "wand":
            charges = self.data.get("charges", 0)
            return f"{self.data.get('name', 'Wand')} [{charges}]"
        if self.item_type == "torch":
            return f"{self.data.get('name', 'Torch')} ({self.data.get('fuel', 0)} fuel)"
        return self.data.get("name", "???")

    @property
    def sell_value(self):
        """Gold value when selling to a shop (roughly 50% of buy price)."""
        if self.item_type == "gold":
            return 0
        if self.item_type == "weapon":
            tier = self.data.get("tier", 1)
            return max(5, (tier + 1) * 15)
        if self.item_type == "armor":
            return max(5, self.data.get("defense", 1) * 20)
        if self.item_type == "potion":
            return 8
        if self.item_type == "scroll":
            return 12
        if self.item_type == "food":
            return 3
        if self.item_type == "ring":
            return 25
        if self.item_type == "bow":
            return max(10, self.data.get("tier", 1) * 18)
        if self.item_type == "arrow":
            return max(2, self.count * 2)
        if self.item_type == "throwing_dagger":
            return max(3, self.count * 3)
        if self.item_type == "wand":
            return max(10, self.data.get("charges", 0) * 5)
        if self.item_type == "torch":
            return 5
        return 5


class Enemy:
    def __init__(self, x, y, etype):
        t = ENEMY_TYPES[etype]
        self.x = x
        self.y = y
        self.etype = etype
        self.name = t["name"]
        self.char = t["char"]
        self.color = t["color"]
        self.max_hp = t["hp"]
        self.hp = t["hp"]
        self.dmg = t["dmg"]
        self.defense = t["defense"]
        self.xp = t["xp"]
        self.speed = t["speed"]
        self.ai = t["ai"]
        self.boss = t.get("boss", False)
        self.regen = t.get("regen", 0)
        self.lifesteal = t.get("lifesteal", False)
        self.energy = 0.0
        self.alerted = False
        self.alertness = "unwary"  # "asleep", "unwary", or "alert"
        self.patrol_dir = random.choice([(0,1),(0,-1),(1,0),(-1,0)])
        self.summon_cooldown = 0
        self.frozen_turns = 0
        # D&D expansion fields
        self.poison_chance = t.get("poison_chance", 0)
        self.fear_chance = t.get("fear_chance", 0)
        self.paralyze_chance = t.get("paralyze_chance", 0)
        self.fire_aura = t.get("fire_aura", False)
        self.disguised = t.get("disguised", False)
        self.phase_cooldown = 0
        self.phase_cooldown_max = t.get("phase_cooldown_max", 3)
        self.psychic_range = t.get("psychic_range", 0)
        self.poisoned_turns = 0  # Poison from player's Poison Blade ability
        # Fleeing system
        self.fleeing = False
        self.flee_threshold = t.get("flee_threshold", 0.0)
        # Elemental resistance system
        self.damage_type = t.get("damage_type", "physical")
        self.resists = t.get("resists", [])
        self.vulnerable = t.get("vulnerable", [])
        self.regen_suppressed = 0  # Turns of regen suppression (e.g. fire vs troll)

    def is_alive(self):
        return self.hp > 0


class Player:
    def __init__(self, player_class=None):
        self.x = 0
        self.y = 0
        self.player_class = player_class  # None = classless adventurer (backward compat)
        if player_class and player_class in CHARACTER_CLASSES:
            cc = CHARACTER_CLASSES[player_class]
            self.hp = cc["hp"]
            self.max_hp = cc["hp"]
            self.mana = cc["mp"]
            self.max_mana = cc["mp"]
            self.strength = cc["str"]
            self.defense = cc["defense"]
        else:
            self.hp = 30
            self.max_hp = 30
            self.mana = 20
            self.max_mana = 20
            self.strength = 5
            self.defense = 1
        self.level = 1
        self.xp = 0
        self.xp_next = BALANCE["xp_base"]
        self.floor = 1
        self.gold = 0
        self.turns = 0
        self.kills = 0
        self.inventory = []
        self.weapon = None
        self.armor = None
        self.ring = None
        self.bow = None
        self.hunger = 100.0
        self.torch_fuel = TORCH_MAX_FUEL
        self.torch_lit = True  # Can toggle torch on/off to conserve fuel
        self.status_effects = {}
        self.frozen_enemies = {}  # enemy id -> turns remaining
        self.deepest_floor = 1
        self.potions_drunk = 0
        self.scrolls_read = 0
        self.items_found = 0
        self.damage_dealt = 0
        self.damage_taken = 0
        self.foods_eaten = 0
        self.bosses_killed = 0
        self.spells_cast = 0
        self.projectiles_fired = 0
        self.pending_levelups = []  # Deferred level-up choices
        self.ability_cooldown = 0   # Class ability cooldown
        # Known spells — class-specific starting sets
        if player_class and player_class in CLASS_KNOWN_SPELLS:
            self.known_spells = set(CLASS_KNOWN_SPELLS[player_class])
        else:
            self.known_spells = set(BASE_SPELLS)  # classless = all base spells
        self.known_abilities = set()  # Warrior/Rogue combat techniques (unlocked via Cleave/Lethality)

    @property
    def carry_capacity(self):
        """Inventory capacity scales with strength."""
        return 15 + self.strength

    def attack_damage(self):
        s = self.strength
        if "Berserk" in self.status_effects:
            s = int(s * 1.5)
        if "Strength" in self.status_effects:
            s += 3
        if self.ring and self.ring.data.get("effect") == "strength":
            s += self.ring.data["value"]
        if self.weapon:
            lo, hi = self.weapon.data["dmg"]
            b = self.weapon.data.get("bonus", 0)
            return random.randint(lo, hi) + b + s // 3
        return random.randint(1, 3) + s // 3

    def total_defense(self):
        d = self.defense
        if self.armor:
            d += self.armor.data["defense"]
        if self.ring and self.ring.data.get("effect") == "defense":
            d += self.ring.data["value"]
        if "Resistance" in self.status_effects:
            d += 3
        return d

    def evasion_chance(self):
        base = B["evasion_base"]
        if "Speed" in self.status_effects:
            base += B["evasion_speed_bonus"]
        if self.ring and self.ring.data.get("effect") == "evasion":
            base += self.ring.data["value"]
        # Rogue class evasion bonus
        if self.player_class and self.player_class in CHARACTER_CLASSES:
            base += CHARACTER_CLASSES[self.player_class].get("evasion_bonus", 0)
        # Levelup evasion bonus
        base += getattr(self, '_evasion_bonus', 0)
        # Smoke Evasion bonus (from Smoke Bomb ability)
        if "Smoke Evasion" in self.status_effects:
            base += B["smoke_bomb_evasion_bonus"]
        return min(base, B["evasion_cap"])

    def player_resists(self):
        """Return set of elements player currently resists."""
        r = set()
        if self.ring and "resists" in self.ring.data:
            r.update(self.ring.data["resists"])
        if self.armor and "resists" in self.armor.data:
            r.update(self.armor.data["resists"])
        return r

    def get_torch_radius(self):
        if not self.torch_lit or self.torch_fuel <= 0:
            return TORCH_RADIUS_EMPTY
        pct = self.torch_fuel / TORCH_MAX_FUEL
        if pct > 0.5:
            return TORCH_RADIUS_FULL
        elif pct > 0.25:
            return TORCH_RADIUS_HALF
        else:
            return TORCH_RADIUS_QUARTER

    def check_level_up(self):
        """Returns list of (level, hp_gain, str_gain, mp_gain) tuples.
        If pending_levelups system is active, defers stat application."""
        ups = []
        while self.xp >= self.xp_next:
            self.xp -= self.xp_next
            self.level += 1
            self.xp_next = int(B["xp_base"] * (B["xp_growth"] ** (self.level - 1)))
            # Use class-specific level gains if applicable
            if self.player_class and self.player_class in CHARACTER_CLASSES:
                cc = CHARACTER_CLASSES[self.player_class]
                hp_gain = random.randint(cc["level_hp"][0], cc["level_hp"][1])
                mana_gain = random.randint(cc["level_mp"][0], cc["level_mp"][1])
                str_gain = cc["level_str"]
                def_gain = cc["level_def"]
            else:
                hp_gain = random.randint(B["hp_gain_min"], B["hp_gain_max"])
                mana_gain = random.randint(B["mana_gain_min"], B["mana_gain_max"])
                str_gain = B["str_gain"]
                def_gain = B["def_gain"]
            # Defer to level-up choice system: store base gains, player picks bonus
            self.pending_levelups.append({
                "level": self.level,
                "base_hp": hp_gain, "base_mp": mana_gain,
                "base_str": str_gain, "base_def": def_gain,
            })
            ups.append((self.level, hp_gain, str_gain, mana_gain))
        return ups


# Level-up choice pool
LEVELUP_CHOICES = [
    {"name": "Might",     "desc": "+HP +STR",       "hp": 5,  "mp": 0, "str": 2, "def": 0, "evasion": 0},
    {"name": "Arcana",    "desc": "+MP, learn new spell", "hp": 0,  "mp": 5, "str": 0, "def": 0, "evasion": 0},
    {"name": "Fortitude", "desc": "+HP +DEF",        "hp": 6,  "mp": 0, "str": 0, "def": 2, "evasion": 0},
    {"name": "Agility",   "desc": "+evasion",        "hp": 2,  "mp": 0, "str": 0, "def": 0, "evasion": 5},
    {"name": "Vitality",  "desc": "+big HP",         "hp": 12, "mp": 0, "str": 0, "def": 0, "evasion": 0},
]

# Class-specific level-up bonuses (added to pool when class matches)
CLASS_LEVELUP_CHOICES = {
    "warrior": {"name": "Cleave",    "desc": "+STR +DEF, learn technique", "hp": 3, "mp": 0, "str": 3, "def": 1, "evasion": 0},
    "mage":    {"name": "Mana Well", "desc": "+big MP (Mage)",              "hp": 0, "mp": 10,"str": 0, "def": 0, "evasion": 0},
    "rogue":   {"name": "Lethality", "desc": "+STR +evasion, learn technique","hp": 0, "mp": 2, "str": 2, "def": 0, "evasion": 5},
}


def generate_levelup_choices(player):
    """Generate 3 random level-up options for the player to choose from."""
    pool = list(LEVELUP_CHOICES)
    if player.player_class and player.player_class in CLASS_LEVELUP_CHOICES:
        pool.append(CLASS_LEVELUP_CHOICES[player.player_class])
    random.shuffle(pool)
    return pool[:3]


def apply_levelup_choice(player, levelup_data, choice):
    """Apply base level-up gains plus the chosen bonus."""
    # Base gains from the level-up
    player.max_hp += levelup_data["base_hp"]
    player.hp = min(player.hp + levelup_data["base_hp"], player.max_hp)
    player.max_mana += levelup_data["base_mp"]
    player.mana = min(player.mana + levelup_data["base_mp"], player.max_mana)
    player.strength += levelup_data["base_str"]
    player.defense += levelup_data["base_def"]
    # Chosen bonus
    player.max_hp += choice["hp"]
    player.hp = min(player.hp + choice["hp"], player.max_hp)
    player.max_mana += choice["mp"]
    player.mana = min(player.mana + choice["mp"], player.max_mana)
    player.strength += choice["str"]
    player.defense += choice["def"]
    # Evasion bonus is permanent via a status-like approach — just add to defense for simplicity
    # Actually, store cumulative evasion bonus on player
    if not hasattr(player, '_evasion_bonus'):
        player._evasion_bonus = 0
    player._evasion_bonus += choice.get("evasion", 0)
    # Arcana unlocks the next spell in the class unlock order
    # Cleave/Lethality unlocks the next class ability
    learned = None
    if choice["name"] == "Arcana":
        learned = _unlock_next_spell(player)
    elif choice["name"] in ("Cleave", "Lethality"):
        learned = _unlock_next_ability(player)
    return learned


def _unlock_next_spell(player):
    """Unlock the next spell in the class-specific unlock order. Returns spell name or None."""
    unlock_list = SPELL_UNLOCK_ORDER.get(player.player_class, [])
    for spell_name in unlock_list:
        if spell_name not in player.known_spells:
            player.known_spells.add(spell_name)
            return spell_name
    return None  # All already known — just the MP bonus


def show_levelup_choice(scr, gs):
    """Show level-up choice screen for one pending levelup. Returns chosen index."""
    if not gs.player.pending_levelups:
        return
    levelup_data = gs.player.pending_levelups[0]
    choices = generate_levelup_choices(gs.player)

    scr.erase()
    safe_addstr(scr, 1, 20, f"LEVEL UP! (Level {levelup_data['level']})", curses.color_pair(C_YELLOW) | curses.A_BOLD)
    safe_addstr(scr, 2, 20, "=" * 22, curses.color_pair(C_DARK))
    safe_addstr(scr, 4, 5, f"Base: +{levelup_data['base_hp']} HP, +{levelup_data['base_mp']} MP, +{levelup_data['base_str']} STR, +{levelup_data['base_def']} DEF",
               curses.color_pair(C_UI))
    safe_addstr(scr, 5, 5, "Choose a bonus:", curses.color_pair(C_WHITE))

    row = 7
    colors = [C_RED, C_CYAN, C_GREEN]
    for i, ch in enumerate(choices):
        safe_addstr(scr, row, 5, f"[{i+1}] {ch['name']}", curses.color_pair(colors[i]) | curses.A_BOLD)
        details = []
        if ch["hp"]: details.append(f"+{ch['hp']} HP")
        if ch["mp"]: details.append(f"+{ch['mp']} MP")
        if ch["str"]: details.append(f"+{ch['str']} STR")
        if ch["def"]: details.append(f"+{ch['def']} DEF")
        if ch.get("evasion"): details.append(f"+{ch['evasion']}% Evasion")
        safe_addstr(scr, row, 25, ch["desc"] + " — " + ", ".join(details), curses.color_pair(C_WHITE))
        row += 2

    safe_addstr(scr, row + 1, 15, "Press 1-3 to choose", curses.color_pair(C_UI))
    scr.refresh()

    while True:
        key = scr.getch()
        if key == ord('1'):
            idx = 0
            break
        elif key == ord('2'):
            idx = 1
            break
        elif key == ord('3'):
            idx = 2
            break

    chosen = choices[idx]
    learned = apply_levelup_choice(gs.player, levelup_data, chosen)
    gs.player.pending_levelups.pop(0)
    gs.msg(f"Level {levelup_data['level']}! Chose {chosen['name']}: {chosen['desc']}", C_YELLOW)
    if learned:
        gs.msg(f"You learned {learned}!", C_CYAN)
    return idx


def auto_apply_levelup(player):
    """Auto-apply the best level-up choice (for bot/agent). Picks highest HP option."""
    if not player.pending_levelups:
        return
    levelup_data = player.pending_levelups[0]
    choices = generate_levelup_choices(player)
    # Bot heuristic: pick the choice with highest HP gain (survival-oriented)
    best = max(choices, key=lambda c: c["hp"] + c["def"] * 2)
    apply_levelup_choice(player, levelup_data, best)
    player.pending_levelups.pop(0)


class ShopItem:
    def __init__(self, item, price):
        self.item = item
        self.price = price
        self.sold = False


# ============================================================
# DUNGEON GENERATION (BSP)
# ============================================================

class BSPNode:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.left = None
        self.right = None
        self.room = None

    def split(self, min_size=8, max_depth=5, depth=0):
        if depth >= max_depth:
            return
        if self.w < min_size * 2 and self.h < min_size * 2:
            return
        if self.w > self.h * 1.25:
            horizontal = False
        elif self.h > self.w * 1.25:
            horizontal = True
        else:
            horizontal = random.random() < 0.5
        if horizontal:
            if self.h < min_size * 2:
                return
            s = random.randint(min_size, self.h - min_size)
            self.left = BSPNode(self.x, self.y, self.w, s)
            self.right = BSPNode(self.x, self.y + s, self.w, self.h - s)
        else:
            if self.w < min_size * 2:
                return
            s = random.randint(min_size, self.w - min_size)
            self.left = BSPNode(self.x, self.y, s, self.h)
            self.right = BSPNode(self.x + s, self.y, self.w - s, self.h)
        self.left.split(min_size, max_depth, depth + 1)
        self.right.split(min_size, max_depth, depth + 1)

    def get_rooms(self):
        if self.room:
            return [self.room]
        rooms = []
        if self.left:
            rooms.extend(self.left.get_rooms())
        if self.right:
            rooms.extend(self.right.get_rooms())
        return rooms

    def create_rooms(self, tiles, min_room=4, padding=1):
        if self.left is None and self.right is None:
            rw = random.randint(min_room, max(min_room, self.w - padding * 2))
            rh = random.randint(min_room, max(min_room, self.h - padding * 2))
            rx = self.x + random.randint(padding, max(padding, self.w - rw - padding))
            ry = self.y + random.randint(padding, max(padding, self.h - rh - padding))
            rx = max(1, min(rx, MAP_W - rw - 1))
            ry = max(1, min(ry, MAP_H - rh - 1))
            rw = min(rw, MAP_W - rx - 1)
            rh = min(rh, MAP_H - ry - 1)
            if rw < min_room or rh < min_room:
                return
            self.room = (rx, ry, rw, rh)
            for yy in range(ry, ry + rh):
                for xx in range(rx, rx + rw):
                    if 0 < xx < MAP_W - 1 and 0 < yy < MAP_H - 1:
                        tiles[yy][xx] = T_FLOOR
            return
        if self.left:
            self.left.create_rooms(tiles, min_room, padding)
        if self.right:
            self.right.create_rooms(tiles, min_room, padding)
        if self.left and self.right:
            lr = self.left.get_rooms()
            rr = self.right.get_rooms()
            if lr and rr:
                r1 = random.choice(lr)
                r2 = random.choice(rr)
                _carve_corridor(tiles, r1[0]+r1[2]//2, r1[1]+r1[3]//2,
                               r2[0]+r2[2]//2, r2[1]+r2[3]//2)


def _carve_corridor(tiles, x1, y1, x2, y2):
    x, y = x1, y1
    if random.random() < 0.5:
        while x != x2:
            if 0 < x < MAP_W-1 and 0 < y < MAP_H-1 and tiles[y][x] == T_WALL:
                tiles[y][x] = T_CORRIDOR
            x += 1 if x2 > x else -1
        while y != y2:
            if 0 < x < MAP_W-1 and 0 < y < MAP_H-1 and tiles[y][x] == T_WALL:
                tiles[y][x] = T_CORRIDOR
            y += 1 if y2 > y else -1
    else:
        while y != y2:
            if 0 < x < MAP_W-1 and 0 < y < MAP_H-1 and tiles[y][x] == T_WALL:
                tiles[y][x] = T_CORRIDOR
            y += 1 if y2 > y else -1
        while x != x2:
            if 0 < x < MAP_W-1 and 0 < y < MAP_H-1 and tiles[y][x] == T_WALL:
                tiles[y][x] = T_CORRIDOR
            x += 1 if x2 > x else -1
    if 0 < x2 < MAP_W-1 and 0 < y2 < MAP_H-1 and tiles[y2][x2] == T_WALL:
        tiles[y2][x2] = T_CORRIDOR


def flood_fill_count(tiles, sx, sy):
    visited = set()
    stack = [(sx, sy)]
    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in visited:
            continue
        if cx < 0 or cx >= MAP_W or cy < 0 or cy >= MAP_H:
            continue
        if tiles[cy][cx] == T_WALL:
            continue
        visited.add((cx, cy))
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            stack.append((cx+dx, cy+dy))
    return len(visited)


def count_walkable(tiles):
    c = 0
    for row in tiles:
        for t in row:
            if t != T_WALL:
                c += 1
    return c


def generate_dungeon(floor_num, retries=20):
    for attempt in range(retries):
        tiles = [[T_WALL]*MAP_W for _ in range(MAP_H)]
        root = BSPNode(0, 0, MAP_W, MAP_H)
        depth = random.randint(3, 5)
        min_sz = random.randint(7, 10)
        root.split(min_size=min_sz, max_depth=depth)
        root.create_rooms(tiles, min_room=4, padding=1)
        rooms = root.get_rooms()
        if len(rooms) < 4:
            continue

        # Extra corridors for loops
        for _ in range(random.randint(1, 3)):
            r1 = random.choice(rooms)
            r2 = random.choice(rooms)
            if r1 != r2:
                _carve_corridor(tiles, r1[0]+r1[2]//2, r1[1]+r1[3]//2,
                               r2[0]+r2[2]//2, r2[1]+r2[3]//2)

        # Add some doors
        for y in range(1, MAP_H-1):
            for x in range(1, MAP_W-1):
                if tiles[y][x] == T_CORRIDOR:
                    h_choke = (tiles[y][x-1] == T_WALL and tiles[y][x+1] == T_WALL and
                               tiles[y-1][x] != T_WALL and tiles[y+1][x] != T_WALL)
                    v_choke = (tiles[y-1][x] == T_WALL and tiles[y+1][x] == T_WALL and
                               tiles[y][x-1] != T_WALL and tiles[y][x+1] != T_WALL)
                    if (h_choke or v_choke) and random.random() < 0.3:
                        tiles[y][x] = T_DOOR

        # Cave features for deeper floors
        if floor_num >= 4:
            _add_cave_features(tiles, floor_num)

        # Place stairs - maximize distance
        best_dist = 0
        start_room = rooms[0]
        end_room = rooms[-1]
        for i, r1 in enumerate(rooms):
            for j, r2 in enumerate(rooms):
                if i != j:
                    d = abs(r1[0]-r2[0]) + abs(r1[1]-r2[1])
                    if d > best_dist:
                        best_dist = d
                        start_room = r1
                        end_room = r2

        px = start_room[0] + start_room[2]//2
        py = start_room[1] + start_room[3]//2
        sx = end_room[0] + end_room[2]//2
        sy = end_room[1] + end_room[3]//2

        if floor_num < MAX_FLOORS:
            tiles[sy][sx] = T_STAIRS_DOWN
        if floor_num > 1:
            tiles[py][px] = T_STAIRS_UP

        # Verify connectivity
        walkable = count_walkable(tiles)
        reachable = flood_fill_count(tiles, px, py)
        if walkable > 0 and reachable >= walkable * 0.95:
            return tiles, rooms, (px, py), (sx, sy)

    return _generate_fallback(floor_num)


def _add_cave_features(tiles, floor_num):
    for _ in range(min(floor_num - 3, 4)):
        for _ in range(50):
            cx = random.randint(3, MAP_W-4)
            cy = random.randint(3, MAP_H-4)
            if tiles[cy][cx] != T_WALL:
                break
        else:
            continue
        x, y = cx, cy
        for _ in range(random.randint(10, 30)):
            dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
            x = max(1, min(MAP_W-2, x+dx))
            y = max(1, min(MAP_H-2, y+dy))
            if tiles[y][x] == T_WALL:
                tiles[y][x] = T_FLOOR

    if floor_num >= 7:
        for _ in range(random.randint(1, 3)):
            cx = random.randint(5, MAP_W-6)
            cy = random.randint(5, MAP_H-6)
            tile_t = T_LAVA if floor_num >= 10 else T_WATER
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    if abs(dx)+abs(dy) <= 2 and random.random() < 0.6:
                        nx, ny = cx+dx, cy+dy
                        if 0 < nx < MAP_W-1 and 0 < ny < MAP_H-1:
                            if tiles[ny][nx] == T_FLOOR:
                                tiles[ny][nx] = tile_t


def _generate_fallback(floor_num):
    tiles = [[T_WALL]*MAP_W for _ in range(MAP_H)]
    rooms = []
    for gy in range(3):
        for gx in range(4):
            rx = 3 + gx*18
            ry = 3 + gy*12
            rw = random.randint(5, 10)
            rh = random.randint(4, 7)
            if rx+rw < MAP_W-1 and ry+rh < MAP_H-1:
                rooms.append((rx, ry, rw, rh))
                for yy in range(ry, ry+rh):
                    for xx in range(rx, rx+rw):
                        tiles[yy][xx] = T_FLOOR
    for i in range(len(rooms)-1):
        r1, r2 = rooms[i], rooms[i+1]
        _carve_corridor(tiles, r1[0]+r1[2]//2, r1[1]+r1[3]//2,
                       r2[0]+r2[2]//2, r2[1]+r2[3]//2)
    px = rooms[0][0]+rooms[0][2]//2
    py = rooms[0][1]+rooms[0][3]//2
    sx = rooms[-1][0]+rooms[-1][2]//2
    sy = rooms[-1][1]+rooms[-1][3]//2
    if floor_num < MAX_FLOORS:
        tiles[sy][sx] = T_STAIRS_DOWN
    if floor_num > 1:
        tiles[py][px] = T_STAIRS_UP
    return tiles, rooms, (px, py), (sx, sy)


# ============================================================
# FOV (Recursive Shadowcasting)
# ============================================================

_MULT = [
    [1,  0,  0, -1, -1,  0,  0,  1],
    [0,  1, -1,  0,  0, -1,  1,  0],
    [0,  1,  1,  0,  0, -1, -1,  0],
    [1,  0,  0,  1, -1,  0,  0, -1],
]

def compute_fov(tiles, px, py, radius, visible_set):
    """Compute field of view using recursive shadowcasting for 8 octants."""
    visible_set.clear()
    visible_set.add((px, py))
    for octant in range(8):
        _cast_light(tiles, px, py, radius, 1, 1.0, 0.0, octant, visible_set)

def _cast_light(tiles, cx, cy, radius, row, start, end, octant, visible):
    if start < end:
        return
    radius_sq = radius * radius
    for j in range(row, radius+1):
        dx = -j - 1
        dy = -j
        blocked = False
        new_start = start
        while dx <= 0:
            dx += 1
            mx = cx + dx*_MULT[0][octant] + dy*_MULT[1][octant]
            my = cy + dx*_MULT[2][octant] + dy*_MULT[3][octant]
            l_slope = (dx - 0.5) / (dy + 0.5)
            r_slope = (dx + 0.5) / (dy - 0.5)
            if start < r_slope:
                continue
            elif end > l_slope:
                break
            if dx*dx + dy*dy <= radius_sq:
                if 0 <= mx < MAP_W and 0 <= my < MAP_H:
                    visible.add((mx, my))
            if blocked:
                if 0 <= mx < MAP_W and 0 <= my < MAP_H and tiles[my][mx] == T_WALL:
                    new_start = r_slope
                    continue
                else:
                    blocked = False
                    start = new_start
            else:
                if 0 <= mx < MAP_W and 0 <= my < MAP_H and tiles[my][mx] == T_WALL and j < radius:
                    blocked = True
                    _cast_light(tiles, cx, cy, radius, j+1, start, l_slope, octant, visible)
                    new_start = r_slope
        if blocked:
            break


# ============================================================
# PATHFINDING
# ============================================================

def astar(tiles, sx, sy, gx, gy, max_steps=20):
    """A* pathfinding from (sx,sy) to (gx,gy). Returns (dx,dy) for first step or None."""
    if sx == gx and sy == gy:
        return (0, 0)
    open_set = [(0, sx, sy)]
    came_from = {}
    g_score = {(sx, sy): 0}
    closed = set()
    while open_set:
        _, cx, cy = heapq.heappop(open_set)
        if (cx, cy) in closed:
            continue
        closed.add((cx, cy))
        if cx == gx and cy == gy:
            path = []
            pos = (gx, gy)
            while pos in came_from:
                path.append(pos)
                pos = came_from[pos]
            if path:
                nx, ny = path[-1]
                return (nx - sx, ny - sy)
            return None
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = cx+ddx, cy+ddy
            if nx < 0 or nx >= MAP_W or ny < 0 or ny >= MAP_H:
                continue
            if tiles[ny][nx] == T_WALL or tiles[ny][nx] == T_LAVA:
                continue
            ng = g_score[(cx,cy)] + 1
            if ng > max_steps:
                continue
            if (nx,ny) not in g_score or ng < g_score[(nx,ny)]:
                g_score[(nx,ny)] = ng
                f = ng + abs(nx-gx) + abs(ny-gy)
                came_from[(nx,ny)] = (cx,cy)
                heapq.heappush(open_set, (f, nx, ny))
    return None


def _has_los(tiles, x1, y1, x2, y2):
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x2 > x1 else -1
    sy = 1 if y2 > y1 else -1
    err = dx - dy
    x, y = x1, y1
    while True:
        if x == x2 and y == y2:
            return True
        if 0 <= y < MAP_H and 0 <= x < MAP_W and tiles[y][x] == T_WALL:
            return False
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


# ============================================================
# GAME STATE
# ============================================================

class GameState:
    def __init__(self, headless=False, seed=None, player_class=None):
        self.seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        random.seed(self.seed)
        self.player = Player(player_class=player_class)
        self.tiles = None
        self.rooms = None
        self.enemies = []
        self.items = []
        self.shops = []
        self.messages = deque(maxlen=MAX_MESSAGES)
        self.visible = set()
        self.explored = [[False]*MAP_W for _ in range(MAP_H)]
        self.stair_down = (0, 0)
        self.running = True
        self.game_over = False
        self.victory = False
        self.turn_count = 0
        self.start_time = time.time()
        self._headless = headless
        self._scr = None  # set during game_loop for projectile animation
        self.death_cause = None
        self.recorder = None  # SessionRecorder, set during game init
        self.floors_explored = set()  # track unique floors visited
        # First-encounter tips tracking (Phase 5, item 25)
        self.tips_shown = set()
        # First melee attack tracking (Phase 3, item 14)
        self.first_melee_done = False
        # Shop discovery flag — message fires when FOV first sees shop tile (#10)
        self.shop_discovered = False
        # Journal — tracks identified item effects (#6)
        self.journal = {}
        # Alchemy tables used on this floor (#7)
        self.alchemy_used = set()
        # Puzzles on current floor (#9)
        self.puzzles = []
        # Wall torches on current floor (#1)
        self.wall_torches = []
        # Traps on current floor
        self.traps = []
        # Stealth system: noise generated this turn
        self.last_noise = 0
        # Dungeon branch system
        self.branch_choices = {}  # {floor_num: "branch_key"}
        self.active_branch = None  # Current branch key or None
        # Monster Memory / Bestiary
        self.bestiary = {}  # {etype: {"encountered": N, "killed": N, "dmg_dealt": N, "dmg_taken": N, "abilities": set()}}
        # Auto-fight / auto-explore state
        self.auto_fighting = False
        self.auto_exploring = False
        self.auto_fight_target = None
        # Shuffle potion/scroll identities per game
        self.potion_ids = {}
        self.scroll_ids = {}
        self.id_potions = set()
        self.id_scrolls = set()
        colors = list(POTION_COLORS)
        random.shuffle(colors)
        for i, eff in enumerate(POTION_EFFECTS):
            self.potion_ids[eff] = colors[i]
        labels = list(SCROLL_LABELS)
        random.shuffle(labels)
        for i, eff in enumerate(SCROLL_EFFECTS):
            self.scroll_ids[eff] = labels[i]

    def msg(self, text, color=C_WHITE):
        self.messages.append((text, color))

    def _get_active_branch(self, floor_num):
        """Determine if the given floor is in a branch. Returns branch key or None."""
        for choice_floor, (branch_a, branch_b) in BRANCH_CHOICES.items():
            chosen = self.branch_choices.get(choice_floor)
            if chosen:
                bdef = BRANCH_DEFS[chosen]
                if floor_num in bdef["floors"]:
                    return chosen
        return None

    def _apply_branch_terrain(self, floor_num, branch_key):
        """Modify terrain tiles for a branch (more water/lava)."""
        bdef = BRANCH_DEFS[branch_key]
        # Replace some floor tiles with water or lava based on branch
        floor_tiles = [(x, y) for y in range(MAP_H) for x in range(MAP_W)
                       if self.tiles[y][x] == T_FLOOR]
        random.shuffle(floor_tiles)
        water_count = int(len(floor_tiles) * 0.03 * bdef.get("water_boost", 1.0))
        lava_count = int(len(floor_tiles) * 0.03 * bdef.get("lava_boost", 1.0))
        idx = 0
        for _ in range(water_count):
            if idx < len(floor_tiles):
                x, y = floor_tiles[idx]
                # Don't replace player position or stairs
                if (x, y) != (self.player.x, self.player.y) and (x, y) != self.stair_down:
                    self.tiles[y][x] = T_WATER
                idx += 1
        for _ in range(lava_count):
            if idx < len(floor_tiles):
                x, y = floor_tiles[idx]
                if (x, y) != (self.player.x, self.player.y) and (x, y) != self.stair_down:
                    self.tiles[y][x] = T_LAVA
                idx += 1

    def generate_floor(self, floor_num):
        self.player.floor = floor_num
        if floor_num > self.player.deepest_floor:
            self.player.deepest_floor = floor_num
        self.floors_explored.add(floor_num)
        self.tiles, self.rooms, start, self.stair_down = generate_dungeon(floor_num)
        self.player.x, self.player.y = start
        self.explored = [[False]*MAP_W for _ in range(MAP_H)]
        self.enemies = []
        self.items = []
        self.shops = []
        self.shop_discovered = False
        self.alchemy_used = set()
        self.puzzles = []
        self.wall_torches = []
        self.traps = []
        # Determine active branch for this floor
        self.active_branch = self._get_active_branch(floor_num)
        # Apply branch-specific terrain modifications
        if self.active_branch:
            self._apply_branch_terrain(floor_num, self.active_branch)
        self._populate_enemies(floor_num)
        self._populate_items(floor_num)
        self._place_shop(floor_num)
        self._place_shrine(floor_num)
        self._place_alchemy_table(floor_num)
        self._place_wall_torches(floor_num)
        self._place_puzzle(floor_num)
        self._place_traps(floor_num)
        # Branch-specific extra traps
        if self.active_branch:
            bdef = BRANCH_DEFS[self.active_branch]
            extra_traps = bdef.get("extra_traps", 0)
            for _ in range(extra_traps):
                self._place_single_trap(floor_num)
        # Determine theme
        if self.active_branch:
            theme = BRANCH_DEFS[self.active_branch]["theme"]
        else:
            theme = THEMES[floor_num-1] if floor_num <= len(THEMES) else "The Abyss"
        self.msg(f"--- Floor {floor_num}: {theme} ---", C_YELLOW)
        if self.active_branch:
            bdef = BRANCH_DEFS[self.active_branch]
            self.msg(f"You are in {bdef['name']}.", C_CYAN)
        if floor_num == MAX_FLOORS:
            self.msg("You feel an overwhelming dread...", C_RED)

    def _populate_enemies(self, floor_num):
        num = B["enemies_base"] + floor_num * B["enemies_per_floor"] + random.randint(0, B["enemies_random_bonus"])
        # Branch-specific enemy pool override
        if self.active_branch:
            bdef = BRANCH_DEFS[self.active_branch]
            eligible = [k for k in bdef["enemy_pool"] if k in ENEMY_TYPES and not ENEMY_TYPES[k].get("boss")]
            num += bdef.get("extra_enemies", 0)
        else:
            eligible = [k for k, v in ENEMY_TYPES.items()
                        if v["min_floor"] <= floor_num <= v.get("max_floor", 99) and not v.get("boss")]
        # Bosses: standard bosses spawn on their designated floors
        for etype, tmpl in ENEMY_TYPES.items():
            if tmpl.get("boss") and tmpl["min_floor"] == floor_num:
                # Skip branch mini-bosses unless on correct branch floor
                if etype in ("crypt_guardian", "flame_tyrant", "elder_brain", "beast_lord"):
                    continue  # These are handled separately below
                pos = self._find_spawn_pos()
                if pos:
                    self.enemies.append(Enemy(pos[0], pos[1], etype))
                    self.msg("A powerful presence lurks on this floor...", C_RED)
        # Branch mini-boss
        if self.active_branch:
            bdef = BRANCH_DEFS[self.active_branch]
            if floor_num == bdef.get("mini_boss_floor"):
                mini_boss = bdef["mini_boss"]
                pos = self._find_spawn_pos()
                if pos:
                    self.enemies.append(Enemy(pos[0], pos[1], mini_boss))
                    self.msg(f"The {ENEMY_TYPES[mini_boss]['name']} guards this place!", C_RED)
        for _ in range(num):
            if not eligible:
                break
            etype = random.choice(eligible)
            pos = self._find_spawn_pos()
            if pos:
                e = Enemy(pos[0], pos[1], etype)
                scale = 1.0 + (floor_num - ENEMY_TYPES[etype]["min_floor"]) * B["enemy_hp_scale_per_floor"]
                e.max_hp = int(e.max_hp * scale)
                e.hp = e.max_hp
                # Stealth system: assign initial alertness
                e.alertness = "asleep" if random.random() < B["asleep_spawn_chance"] else "unwary"
                self.enemies.append(e)

    def _populate_items(self, floor_num):
        num = B["items_base"] + floor_num * B["items_per_floor"] + random.randint(0, B["items_random_bonus"])
        for _ in range(num):
            pos = self._find_spawn_pos()
            if pos:
                item = self._random_item(pos[0], pos[1], floor_num)
                if item:
                    self.items.append(item)
        # Guarantee food items per floor so starvation isn't RNG-dependent
        for _ in range(random.randint(B["guaranteed_food_min"], B["guaranteed_food_max"])):
            pos = self._find_spawn_pos()
            if pos:
                f = random.choice(FOOD_TYPES)
                self.items.append(Item(pos[0], pos[1], "food", f["name"], f))
        for _ in range(random.randint(B["gold_piles_min"], B["gold_piles_max"])):
            pos = self._find_spawn_pos()
            if pos:
                amt = random.randint(B["gold_per_floor_min"], B["gold_per_floor_max"]) * floor_num
                self.items.append(Item(pos[0], pos[1], "gold", 0, {"amount": amt, "name": f"{amt} gold"}))

    def _random_item(self, x, y, floor_num):
        weights = B["item_weights"]
        types = list(weights.keys())
        probs = list(weights.values())
        item_type = random.choices(types, weights=probs, k=1)[0]

        if item_type == "weapon":
            eligible = [w for w in WEAPON_TYPES if w["tier"] <= (floor_num//3)+1]
            if eligible:
                w = random.choice(eligible)
                return Item(x, y, "weapon", WEAPON_TYPES.index(w), w)
        elif item_type == "armor":
            eligible = [a for a in ARMOR_TYPES if a["tier"] <= (floor_num//3)+1]
            if eligible:
                a = random.choice(eligible)
                return Item(x, y, "armor", ARMOR_TYPES.index(a), a)
        elif item_type == "potion":
            eff = random.choice(POTION_EFFECTS)
            return Item(x, y, "potion", eff,
                       {"effect": eff, "color_name": self.potion_ids[eff], "char": '!'})
        elif item_type == "scroll":
            eff = random.choice(SCROLL_EFFECTS)
            return Item(x, y, "scroll", eff,
                       {"effect": eff, "label": self.scroll_ids[eff], "char": '?'})
        elif item_type == "food":
            f = random.choice(FOOD_TYPES)
            return Item(x, y, "food", f["name"], f)
        elif item_type == "ring":
            r = random.choice(RING_TYPES)
            return Item(x, y, "ring", r["name"], r)
        elif item_type == "bow":
            eligible = [b for b in BOW_TYPES if b["tier"] <= (floor_num//3)+1]
            if eligible:
                b = random.choice(eligible)
                return Item(x, y, "bow", b["name"], b)
            # Fallback to arrows
            it = Item(x, y, "arrow", "Arrow", dict(ARROW_ITEM))
            it.count = random.randint(3, 8)
            return it
        elif item_type == "arrow":
            it = Item(x, y, "arrow", "Arrow", dict(ARROW_ITEM))
            it.count = random.randint(3, 8)
            return it
        elif item_type == "throwing_dagger":
            it = Item(x, y, "throwing_dagger", "Throwing Dagger", dict(THROWING_DAGGER))
            it.count = random.randint(2, 5)
            return it
        elif item_type == "wand":
            eligible = [w for w in WAND_TYPES if w["tier"] <= (floor_num//3)+2]
            if eligible:
                w = random.choice(eligible)
                data = dict(w)
                return Item(x, y, "wand", w["name"], data)
        elif item_type == "torch":
            t = random.choice(TORCH_TYPES)
            return Item(x, y, "torch", t["name"], dict(t))

        # Fallback if nothing generated (e.g., no eligible weapons on early floors)
        f = random.choice(FOOD_TYPES)
        return Item(x, y, "food", f["name"], f)

    def _place_shop(self, floor_num):
        if floor_num % 2 == 0:  # Shops on odd floors: 1,3,5,7,9,11,13,15 (#19)
            return
        if len(self.rooms) < 3:
            return
        room = self.rooms[len(self.rooms)//2]
        rx, ry, rw, rh = room
        for yy in range(ry, ry+rh):
            for xx in range(rx, rx+rw):
                if 0 < xx < MAP_W-1 and 0 < yy < MAP_H-1:
                    if self.tiles[yy][xx] == T_FLOOR:
                        self.tiles[yy][xx] = T_SHOP_FLOOR
        shop_items = []
        for _ in range(random.randint(B["shop_items_min"], B["shop_items_max"])):
            item = self._random_item(rx+1, ry+1, floor_num)
            if item:
                item.identified = True
                price = (item.data.get("tier", 1)+1) * random.randint(20, 50)
                if item.item_type in ("potion", "scroll"):
                    price = random.randint(15, 60)
                elif item.item_type == "food":
                    price = random.randint(10, 25)
                elif item.item_type == "ring":
                    price = random.randint(50, 120)
                shop_items.append(ShopItem(item, price))
        # Always stock healing and food
        heal = Item(0, 0, "potion", "Healing",
                   {"effect": "Healing", "color_name": self.potion_ids["Healing"], "char": '!'})
        heal.identified = True
        shop_items.append(ShopItem(heal, B["shop_heal_base_price"] + floor_num * B["shop_heal_floor_scale"]))
        food = random.choice(FOOD_TYPES)
        fi = Item(0, 0, "food", food["name"], food)
        fi.identified = True
        shop_items.append(ShopItem(fi, B["shop_food_price"]))
        self.shops.append((room, shop_items))

    def _place_shrine(self, floor_num):
        if floor_num % 4 != 2:
            return
        if len(self.rooms) < 2:
            return
        room = self.rooms[random.randint(1, len(self.rooms)-1)]
        cx = room[0] + room[2]//2
        cy = room[1] + room[3]//2
        if 0 < cx < MAP_W-1 and 0 < cy < MAP_H-1:
            self.tiles[cy][cx] = T_SHRINE

    def _place_alchemy_table(self, floor_num):
        """Place alchemy table on specific floors (#7)."""
        if floor_num not in (2, 5, 8, 11, 14):
            return
        if len(self.rooms) < 2:
            return
        room = self.rooms[random.randint(1, len(self.rooms)-1)]
        cx = room[0] + room[2]//2
        cy = room[1] + room[3]//2 + 1  # offset from center
        if 0 < cx < MAP_W-1 and 0 < cy < MAP_H-1:
            if self.tiles[cy][cx] == T_FLOOR:
                self.tiles[cy][cx] = T_ALCHEMY_TABLE

    def _place_wall_torches(self, floor_num):
        """Place wall torches in rooms for environmental lighting (#1)."""
        if not self.rooms:
            return
        for room in self.rooms:
            if random.random() > 0.40:  # 40% of rooms get torches
                continue
            rx, ry, rw, rh = room
            # Deeper floors = fewer lit rooms
            if floor_num >= 10 and random.random() < 0.5:
                continue
            num_torches = random.randint(2, 4)
            placed = 0
            for _ in range(num_torches * 4):  # try multiple positions
                if placed >= num_torches:
                    break
                # Pick a wall position bordering the room
                side = random.randint(0, 3)
                if side == 0:  # top wall
                    tx = random.randint(rx, rx + rw - 1)
                    ty = ry - 1
                elif side == 1:  # bottom wall
                    tx = random.randint(rx, rx + rw - 1)
                    ty = ry + rh
                elif side == 2:  # left wall
                    tx = rx - 1
                    ty = random.randint(ry, ry + rh - 1)
                else:  # right wall
                    tx = rx + rw
                    ty = random.randint(ry, ry + rh - 1)
                if 0 < tx < MAP_W-1 and 0 < ty < MAP_H-1:
                    if self.tiles[ty][tx] == T_WALL:
                        self.tiles[ty][tx] = T_WALL_TORCH
                        self.wall_torches.append((tx, ty))
                        placed += 1

    def _place_puzzle(self, floor_num):
        """Place puzzle on floors 4+ with 25% chance (#9)."""
        if floor_num < 4 or random.random() > 0.25:
            return
        if len(self.rooms) < 4:
            return
        # Pick a room that isn't the start room or shop room
        start_room = self.rooms[0]
        shop_rooms = [r for r, _ in self.shops] if self.shops else []
        candidates = [r for r in self.rooms[1:] if r not in shop_rooms]
        if not candidates:
            return
        room = random.choice(candidates)
        rx, ry, rw, rh = room
        puzzle_type = random.choice(["torch", "switch", "locked_stairs"])

        if puzzle_type == "torch":
            # Place 3-4 pedestals to light
            count = random.randint(3, 4)
            positions = []
            for _ in range(count):
                px = random.randint(rx, rx + rw - 1)
                py = random.randint(ry, ry + rh - 1)
                if 0 < px < MAP_W-1 and 0 < py < MAP_H-1 and self.tiles[py][px] == T_FLOOR:
                    self.tiles[py][px] = T_PEDESTAL_UNLIT
                    positions.append((px, py))
            if positions:
                self.puzzles.append({"type": "torch", "positions": positions, "solved": False, "room": room})

        elif puzzle_type == "switch":
            # Place 3 switches — all must be ON
            count = 3
            positions = []
            for _ in range(count):
                px = random.randint(rx, rx + rw - 1)
                py = random.randint(ry, ry + rh - 1)
                if 0 < px < MAP_W-1 and 0 < py < MAP_H-1 and self.tiles[py][px] == T_FLOOR:
                    self.tiles[py][px] = T_SWITCH_OFF
                    positions.append((px, py))
            if positions:
                self.puzzles.append({"type": "switch", "positions": positions, "solved": False, "room": room})

        elif puzzle_type == "locked_stairs":
            # Lock the stairs, place switches to unlock
            sx, sy = self.stair_down
            if self.tiles[sy][sx] == T_STAIRS_DOWN:
                self.tiles[sy][sx] = T_STAIRS_LOCKED
                # Place 2 switches in the puzzle room
                positions = []
                for _ in range(2):
                    px = random.randint(rx, rx + rw - 1)
                    py = random.randint(ry, ry + rh - 1)
                    if 0 < px < MAP_W-1 and 0 < py < MAP_H-1 and self.tiles[py][px] == T_FLOOR:
                        self.tiles[py][px] = T_SWITCH_OFF
                        positions.append((px, py))
                if positions:
                    self.puzzles.append({"type": "locked_stairs", "positions": positions,
                                         "solved": False, "room": room, "stairs": (sx, sy)})

    def _place_traps(self, floor_num):
        """Place traps on floor tiles. Hidden overlay tracked in self.traps."""
        count = min(6, B["trap_base_count"] + int(floor_num * B["trap_per_floor"]))
        eligible_traps = [k for k, v in TRAP_TYPES.items() if v["min_floor"] <= floor_num]
        if not eligible_traps:
            return
        start_room = self.rooms[0] if self.rooms else None
        for _ in range(count):
            for attempt in range(50):
                x = random.randint(1, MAP_W - 2)
                y = random.randint(1, MAP_H - 2)
                if self.tiles[y][x] != T_FLOOR:
                    continue
                # Not in starting room
                if start_room:
                    sx, sy, sw, sh = start_room
                    if sx <= x < sx + sw and sy <= y < sy + sh:
                        continue
                # Not on stairs or shop
                if any(t["x"] == x and t["y"] == y for t in self.traps):
                    continue
                # Not near player start
                if abs(x - self.player.x) + abs(y - self.player.y) <= 3:
                    continue
                trap_type = random.choice(eligible_traps)
                self.traps.append({
                    "x": x, "y": y, "type": trap_type,
                    "visible": False, "triggered": False, "disarmed": False
                })
                break

    def _place_single_trap(self, floor_num):
        """Place a single additional trap (used by branch system)."""
        eligible_traps = [k for k, v in TRAP_TYPES.items() if v["min_floor"] <= floor_num]
        if not eligible_traps:
            return
        for _ in range(50):
            x = random.randint(1, MAP_W - 2)
            y = random.randint(1, MAP_H - 2)
            if self.tiles[y][x] != T_FLOOR:
                continue
            if any(t["x"] == x and t["y"] == y for t in self.traps):
                continue
            if abs(x - self.player.x) + abs(y - self.player.y) <= 3:
                continue
            trap_type = random.choice(eligible_traps)
            self.traps.append({
                "x": x, "y": y, "type": trap_type,
                "visible": False, "triggered": False, "disarmed": False
            })
            break

    def _find_spawn_pos(self):
        for _ in range(100):
            x = random.randint(1, MAP_W-2)
            y = random.randint(1, MAP_H-2)
            if self.tiles[y][x] in (T_FLOOR, T_CORRIDOR):
                if abs(x-self.player.x) + abs(y-self.player.y) > 5:
                    if not any(e.x == x and e.y == y for e in self.enemies):
                        return (x, y)
        return None

    def get_shop_at(self, x, y):
        for room, items in self.shops:
            rx, ry, rw, rh = room
            if rx <= x < rx+rw and ry <= y < ry+rh:
                return (room, items)
        return None


# ============================================================
# COMBAT & ITEMS
# ============================================================

def _bestiary_record(gs, etype, event, value=0):
    """Record a bestiary event for an enemy type.

    Args:
        gs: GameState
        etype: Enemy type key (e.g. "rat", "skeleton")
        event: One of "encounter", "kill", "dmg_dealt", "dmg_taken", "ability"
        value: Numeric value (damage amount) or string (ability name)
    """
    if etype not in gs.bestiary:
        gs.bestiary[etype] = {
            "encountered": 0, "killed": 0,
            "dmg_dealt": 0, "dmg_taken": 0,
            "abilities": [],
        }
    entry = gs.bestiary[etype]
    if event == "encounter":
        entry["encountered"] += 1
    elif event == "kill":
        entry["killed"] += 1
    elif event == "dmg_dealt":
        entry["dmg_dealt"] += value
    elif event == "dmg_taken":
        entry["dmg_taken"] += value
    elif event == "ability":
        if value not in entry["abilities"]:
            entry["abilities"].append(value)


def _award_kill(gs, enemy, msg=None, drops=False):
    """Centralized kill accounting. Call when enemy dies.

    Handles: XP award, kill count, boss tracking, damage stats cleanup.
    Optionally shows a kill message and spawns loot drops.

    Args:
        gs: GameState
        enemy: The dead Enemy
        msg: Optional kill message. If None, uses default. Pass False to suppress.
        drops: If True, roll for item/gold drops (melee kills only).

    Returns:
        True (for counting kills in AoE loops).
    """
    p = gs.player
    p.xp += enemy.xp
    p.kills += 1
    _bestiary_record(gs, enemy.etype, "kill")
    if enemy.boss:
        p.bosses_killed += 1
    if msg is not False:
        if msg is None:
            msg = f"You killed the {enemy.name}! (+{enemy.xp} XP)"
        gs.msg(msg, C_GREEN)
    # Boss-specific weapon drops (#20)
    if enemy.boss and enemy.etype in BOSS_DROPS:
        bd = BOSS_DROPS[enemy.etype]
        boss_wpn = Item(enemy.x, enemy.y, "weapon", bd["name"], dict(bd))
        boss_wpn.identified = True
        gs.items.append(boss_wpn)
        gs.msg(f"The {enemy.name} drops {bd['name']}!", C_GOLD)
    if drops:
        if random.random() < B["enemy_item_drop_chance"]:
            item = gs._random_item(enemy.x, enemy.y, p.floor)
            if item:
                gs.items.append(item)
        if random.random() < B["enemy_gold_drop_chance"]:
            amt = random.randint(B["gold_drop_min"], B["gold_drop_max"]) * p.floor
            gs.items.append(Item(enemy.x, enemy.y, "gold", 0, {"amount": amt, "name": f"{amt} gold"}))
    return True


def _check_levelups(gs):
    """Check and announce any pending level-ups after XP gain."""
    p = gs.player
    for lvl, hp_g, str_g, mp_g in p.check_level_up():
        gs.msg(f"*** LEVEL UP! Level {lvl}! +{hp_g} HP, +{str_g} STR, +{mp_g} MP ***", C_YELLOW)
        sound_alert(gs, "level_up")

def _trigger_trap(gs, trap, target_name="You", target_hp_ref=None, is_player=True):
    """Trigger a trap on a target (player or enemy). Returns damage dealt."""
    tdata = TRAP_TYPES[trap["type"]]
    trap["triggered"] = True
    trap["visible"] = True
    lo, hi = tdata["damage"]
    dmg = random.randint(lo, hi) if hi > 0 else 0

    if is_player:
        p = gs.player
        if dmg > 0:
            p.hp -= dmg
            p.damage_taken += dmg
            gs.msg(f"You step on a {tdata['name']}! (-{dmg} HP)", C_RED)
        else:
            gs.msg(f"You trigger a {tdata['name']}!", C_RED)
        # Apply trap effects
        eff = tdata["effect"]
        if eff == "poison" and "Poison" not in p.status_effects:
            p.status_effects["Poison"] = B["poison_duration"]
            gs.msg("You feel poison coursing through your veins!", C_GREEN)
        elif eff == "stun":
            p.status_effects["Paralysis"] = random.randint(1, 2)
            gs.msg("You fall into a pit! Stunned!", C_YELLOW)
        elif eff == "teleport":
            pos = gs._find_spawn_pos()
            if pos:
                p.x, p.y = pos
                gs.msg("You are teleported to a random location!", C_MAGENTA)
        elif eff == "alert_all":
            for e in gs.enemies:
                if e.is_alive():
                    e.alerted = True
            gs.msg("An alarm sounds! All enemies are alerted!", C_RED)
        elif eff == "confusion":
            if "Confusion" not in p.status_effects:
                p.status_effects["Confusion"] = 5
                gs.msg("Noxious gas fills the air! You are confused!", C_GREEN)
        if p.hp <= 0:
            gs.game_over = True
            gs.death_cause = f"killed by {tdata['name'].lower()}"
            sound_alert(gs, "death")
    else:
        # Enemy triggered the trap
        if dmg > 0 and target_hp_ref is not None:
            target_hp_ref[0] -= dmg
            gs.msg(f"A {target_name} triggers a {tdata['name']}! (-{dmg})", C_YELLOW)
        elif dmg == 0:
            gs.msg(f"A {target_name} triggers a {tdata['name']}!", C_YELLOW)
        if tdata["effect"] == "alert_all":
            for e in gs.enemies:
                if e.is_alive():
                    e.alerted = True
    return dmg


def _check_traps_on_move(gs, nx, ny):
    """Check if player steps on a trap at (nx, ny). Returns True if trap triggered."""
    for trap in gs.traps:
        if trap["x"] == nx and trap["y"] == ny and not trap["disarmed"] and not trap["triggered"]:
            if not trap["visible"]:  # Hidden trap always triggers
                _trigger_trap(gs, trap)
                return True
            # Visible traps: player steps over safely (standard roguelike behavior)
    return False


def _passive_trap_detect(gs):
    """Rogue passive trap detection when moving adjacent to hidden traps."""
    p = gs.player
    if p.player_class != "rogue":
        return
    for trap in gs.traps:
        if trap["visible"] or trap["disarmed"] or trap["triggered"]:
            continue
        if abs(trap["x"] - p.x) <= B["trap_detect_radius"] and abs(trap["y"] - p.y) <= B["trap_detect_radius"]:
            if random.randint(1, 100) <= B["trap_rogue_detect_bonus"]:
                trap["visible"] = True
                tdata = TRAP_TYPES[trap["type"]]
                gs.msg(f"You sense a {tdata['name']} nearby!", C_YELLOW)


def _search_for_traps(gs):
    """Active search: check 8 adjacent tiles for hidden traps ('s' key)."""
    p = gs.player
    found = 0
    for ddx in range(-1, 2):
        for ddy in range(-1, 2):
            if ddx == 0 and ddy == 0:
                continue
            tx, ty = p.x + ddx, p.y + ddy
            for trap in gs.traps:
                if trap["x"] == tx and trap["y"] == ty and not trap["visible"] and not trap["disarmed"]:
                    tdata = TRAP_TYPES[trap["type"]]
                    # Roll vs detect_dc
                    roll = p.level + random.randint(1, 20)
                    if p.player_class == "rogue":
                        roll += 5
                    if roll >= tdata["detect_dc"]:
                        trap["visible"] = True
                        gs.msg(f"Found a {tdata['name']}!", C_YELLOW)
                        found += 1
    if found == 0:
        gs.msg("You search but find nothing.", C_DARK)


def _disarm_trap(gs):
    """Disarm an adjacent visible trap ('d' key). Returns True if turn spent."""
    p = gs.player
    # Find nearest adjacent visible trap
    for ddx in range(-1, 2):
        for ddy in range(-1, 2):
            if ddx == 0 and ddy == 0:
                continue
            tx, ty = p.x + ddx, p.y + ddy
            for trap in gs.traps:
                if trap["x"] == tx and trap["y"] == ty and trap["visible"] and not trap["disarmed"] and not trap["triggered"]:
                    tdata = TRAP_TYPES[trap["type"]]
                    chance = B["trap_disarm_base"]
                    if p.player_class == "rogue":
                        chance += p.level * B["trap_disarm_dex_scale"]
                    if random.randint(1, 100) <= chance:
                        trap["disarmed"] = True
                        gs.msg(f"You disarm the {tdata['name']}!", C_GREEN)
                    else:
                        gs.msg(f"Disarm failed! The {tdata['name']} triggers!", C_RED)
                        _trigger_trap(gs, trap)
                    return True
    gs.msg("No visible traps nearby to disarm.", C_DARK)
    return False


def player_attack(gs, enemy):
    p = gs.player
    # First melee attack tip (Phase 3, item 14)
    if not gs.first_melee_done:
        gs.first_melee_done = True
        gs.msg(f"You attack the {enemy.name}!", C_YELLOW)
    hit_chance = B["hit_chance_base"] + p.level * B["hit_chance_per_level"]
    if random.randint(1, 100) > hit_chance:
        gs.msg(f"You miss the {enemy.name}!", C_WHITE)
        # Even a miss makes noise and alerts the enemy
        enemy.alertness = "alert"
        enemy.alerted = True
        return
    dmg = p.attack_damage()
    backstab = "Backstab" in p.status_effects
    # Stealth backstab: attacking asleep/unwary enemy = guaranteed crit
    stealth_backstab = enemy.alertness in ("asleep", "unwary")
    # Backstab ability: guaranteed crit at enhanced multiplier (consumed on use)
    if backstab:
        dmg = max(1, dmg - enemy.defense // B["defense_divisor"])
        dmg = int(dmg * B["backstab_crit_multiplier"])
        del p.status_effects["Backstab"]
        crit = True
    elif stealth_backstab:
        dmg = max(1, dmg - enemy.defense // B["defense_divisor"])
        mult = B["stealth_asleep_crit_mult"] if enemy.alertness == "asleep" else B["stealth_unwary_crit_mult"]
        dmg = int(dmg * mult)
        crit = True
    else:
        dmg = max(1, dmg - enemy.defense // B["defense_divisor"])
        crit = random.random() < B["crit_chance_base"] + (B["crit_chance_per_level"] * p.level)
        if crit:
            dmg = int(dmg * B["crit_multiplier"])
    # Determine weapon damage type for resistance checks
    wpn_dmg_type = "physical"
    if p.weapon:
        wname = p.weapon.data.get("name", "").lower()
        if "flame" in wname or "fire" in wname:
            wpn_dmg_type = "fire"
    # Apply enemy resistance/vulnerability
    if wpn_dmg_type != "physical":
        if wpn_dmg_type in enemy.resists:
            dmg = max(1, int(dmg * (1 - B["resist_reduction_pct"])))
            gs.msg(f"The {enemy.name} resists {wpn_dmg_type}!", C_CYAN)
        if wpn_dmg_type in enemy.vulnerable:
            dmg = int(dmg * B["vulnerable_increase_pct"])
            gs.msg(f"The {enemy.name} is vulnerable to {wpn_dmg_type}!", C_YELLOW)
    # Troll fire interaction: suppress regen
    if enemy.etype == "troll" and wpn_dmg_type == "fire":
        enemy.regen_suppressed = 5
        gs.msg("Fire suppresses the Troll's regeneration!", C_YELLOW)
    enemy.hp -= dmg
    p.damage_dealt += dmg
    _bestiary_record(gs, enemy.etype, "encounter")
    _bestiary_record(gs, enemy.etype, "dmg_dealt", dmg)
    if backstab:
        gs.msg(f"BACKSTAB! You strike {enemy.name} for {dmg}!", C_GREEN)
        sound_alert(gs, "critical_hit")
    elif stealth_backstab:
        state_word = "sleeping" if enemy.alertness == "asleep" else "unwary"
        gs.msg(f"You backstab the {state_word} {enemy.name}! Critical hit! ({dmg})", C_GREEN)
        sound_alert(gs, "critical_hit")
    elif crit:
        gs.msg(f"CRITICAL! You hit {enemy.name} for {dmg}!", C_YELLOW)
        sound_alert(gs, "critical_hit")
    else:
        gs.msg(f"You hit {enemy.name} for {dmg}.", C_WHITE)
    # Combat always alerts the target
    enemy.alertness = "alert"
    enemy.alerted = True
    # Lifesteal from boss weapons (#20)
    if p.weapon and p.weapon.data.get("lifesteal") and dmg > 0:
        heal_amt = max(1, int(dmg * B["lifesteal_pct"]))
        p.hp = min(p.max_hp, p.hp + heal_amt)
        gs.msg(f"Your blade drains {heal_amt} HP!", C_GREEN)
    # Poison Blade: apply poison to hit enemy
    if "Poison Blade" in p.status_effects and enemy.is_alive():
        if enemy.poisoned_turns <= 0:
            enemy.poisoned_turns = B["poison_duration"]
            gs.msg(f"Your poisoned blade infects the {enemy.name}!", C_GREEN)
    if not enemy.is_alive():
        _award_kill(gs, enemy, drops=True)
        _check_levelups(gs)
    enemy.alerted = True


def enemy_attack(gs, enemy):
    p = gs.player
    if random.randint(1, 100) <= p.evasion_chance():
        gs.msg(f"You dodge the {enemy.name}'s attack!", C_CYAN)
        return
    dmg = random.randint(enemy.dmg[0], enemy.dmg[1])
    dmg = max(1, dmg - p.total_defense() // B["defense_divisor"])
    if "Resistance" in p.status_effects:
        dmg = max(1, dmg - B["resistance_reduction"])
    # Elemental resistance: reduce elemental damage
    if enemy.damage_type != "physical" and enemy.damage_type in p.player_resists():
        dmg = max(1, int(dmg * (1 - B["resist_reduction_pct"])))
        gs.msg(f"Your {enemy.damage_type} resistance absorbs some damage!", C_CYAN)
    # Shield Wall: halve incoming damage
    if "Shield Wall" in p.status_effects:
        dmg = max(1, dmg // 2)
    # Mana Shield: absorb damage from mana first (1 mana = 1 damage)
    if "Mana Shield" in p.status_effects and p.mana > 0:
        absorbed = min(dmg, p.mana)
        p.mana -= absorbed
        dmg -= absorbed
        if absorbed > 0:
            gs.msg(f"Mana shield absorbs {absorbed} damage!", C_CYAN)
        if p.mana <= 0:
            del p.status_effects["Mana Shield"]
            gs.msg("Your mana shield shatters!", C_RED)
    p.hp -= dmg
    p.damage_taken += dmg
    _bestiary_record(gs, enemy.etype, "encounter")
    _bestiary_record(gs, enemy.etype, "dmg_taken", dmg)
    if dmg > 0:
        gs.msg(f"The {enemy.name} hits you for {dmg}!", C_RED)
    else:
        gs.msg(f"The {enemy.name}'s attack is fully absorbed!", C_CYAN)
    if enemy.lifesteal:
        enemy.hp = min(enemy.max_hp, enemy.hp + dmg//2)
        gs.msg(f"The {enemy.name} drains your life!", C_MAGENTA)
    # Status effect infliction (D&D expansion)
    if p.hp > 0 and enemy.poison_chance and random.random() < enemy.poison_chance:
        if "Poison" not in p.status_effects:
            p.status_effects["Poison"] = B["poison_duration"]
            gs.msg(f"The {enemy.name} poisons you!", C_GREEN)
            _bestiary_record(gs, enemy.etype, "ability", "poison")
    if p.hp > 0 and enemy.fear_chance and random.random() < enemy.fear_chance:
        if "Fear" not in p.status_effects:
            p.status_effects["Fear"] = B["fear_duration"]
            gs.msg(f"The {enemy.name}'s wail fills you with dread!", C_MAGENTA)
            _bestiary_record(gs, enemy.etype, "ability", "fear")
    if p.hp > 0 and enemy.paralyze_chance and random.random() < enemy.paralyze_chance:
        if "Paralysis" not in p.status_effects:
            p.status_effects["Paralysis"] = B["paralysis_duration"]
            gs.msg(f"The {enemy.name}'s psychic blast paralyzes you!", C_YELLOW)
            _bestiary_record(gs, enemy.etype, "ability", "paralyze")
    if p.hp > 0 and p.hp <= p.max_hp * 0.2:
        gs.msg("!! LOW HP !!", C_RED)
        sound_alert(gs, "low_hp")
    elif p.hp <= 20 and p.hp > 0:
        sound_alert(gs, "low_hp")
    if p.hp <= 0:
        gs.game_over = True
        gs.death_cause = f"slain by {enemy.name}"
        gs.msg(f"You have been slain by the {enemy.name}...", C_RED)
        sound_alert(gs, "death")


def _compute_noise(gs, noise_type="walk"):
    """Compute noise level at player position based on action type.

    Returns integer noise level after applying class reduction.
    """
    p = gs.player
    if gs.tiles is None:
        return 0
    tile = gs.tiles[p.y][p.x]
    if noise_type == "walk":
        if tile == T_CORRIDOR:
            noise = B["noise_corridor_walk"]
        elif tile == T_DOOR:
            noise = B["noise_door_open"]
        else:
            noise = B["noise_floor_walk"]
    elif noise_type == "combat":
        noise = B["noise_combat"]
    elif noise_type == "spell":
        noise = B["noise_spell"]
    else:
        noise = B["noise_floor_walk"]
    # Rogue class makes less noise
    if p.player_class == "rogue":
        noise = int(noise * B["noise_rogue_reduction"])
    return max(0, noise)


def _stealth_detection(gs, noise_level):
    """Run perception checks for non-alert enemies based on noise.

    For each sleeping/unwary enemy, check if noise at their position
    triggers an alertness upgrade.
    """
    p = gs.player
    for e in gs.enemies:
        if not e.is_alive() or e.alertness == "alert":
            continue
        dist = abs(e.x - p.x) + abs(e.y - p.y)
        noise_at_enemy = noise_level - dist * B["noise_decay_per_tile"]
        if noise_at_enemy <= 0:
            continue
        # Perception check: enemy level proxy + random(1,10) vs stealth threshold
        enemy_level = max(1, ENEMY_TYPES[e.etype].get("min_floor", 1))
        perception = enemy_level + random.randint(1, 10)
        stealth = noise_at_enemy
        if perception >= stealth:
            # Upgrade alertness
            if e.alertness == "asleep":
                e.alertness = "unwary"
                if (e.x, e.y) in gs.visible:
                    gs.msg(f"The {e.name} stirs...", C_DARK)
            elif e.alertness == "unwary":
                e.alertness = "alert"
                e.alerted = True
                if (e.x, e.y) in gs.visible:
                    gs.msg(f"The {e.name} is alerted!", C_YELLOW)


def process_enemies(gs):
    p = gs.player
    for e in gs.enemies:
        if not e.is_alive():
            continue
        # Enemy poison tick (from Poison Blade)
        if e.poisoned_turns > 0:
            poison_dmg = B["poison_damage_per_tick"]
            e.hp -= poison_dmg
            e.poisoned_turns -= 1
            if not e.is_alive():
                _award_kill(gs, e, msg=f"The {e.name} dies from poison! (+{e.xp} XP)")
                continue
        # Frozen enemies skip their turn
        if e.frozen_turns > 0:
            continue
        if e.regen_suppressed > 0:
            e.regen_suppressed -= 1
        elif e.regen and e.hp < e.max_hp:
            e.hp = min(e.max_hp, e.hp + e.regen)
        if e.summon_cooldown > 0:
            e.summon_cooldown -= 1
        # Sleeping enemies do nothing (stealth system)
        if e.alertness == "asleep":
            continue
        dist = abs(e.x - p.x) + abs(e.y - p.y)
        fov_radius = p.get_torch_radius()
        in_fov = (e.x, e.y) in gs.visible
        if in_fov and dist <= fov_radius:
            # Visual detection: unwary enemies become alert when they see player
            if e.alertness == "unwary":
                e.alertness = "alert"
                e.alerted = True
                gs.msg(f"A {e.name} spots you!", e.color)
                if e.boss:
                    sound_alert(gs, "boss_encounter")
            elif not e.alerted:
                gs.msg(f"A {e.name} spots you!", e.color)
                if e.boss:
                    sound_alert(gs, "boss_encounter")
                e.alerted = True
                e.alertness = "alert"
        if not e.alerted:
            if e.ai == "patrol":
                _patrol_move(gs, e)
            continue
        e.energy += e.speed
        if e.energy < 1.0:
            continue
        e.energy -= 1.0
        # Morale check: flee when HP drops below threshold
        if e.flee_threshold > 0 and e.hp <= e.max_hp * e.flee_threshold and not e.fleeing:
            e.fleeing = True
            gs.msg(f"The {e.name} turns to flee!", C_YELLOW)
        if e.fleeing:
            _flee_move(gs, e)
            continue
        if e.ai == "chase":
            _chase_move(gs, e)
        elif e.ai == "erratic":
            _erratic_move(gs, e)
        elif e.ai == "patrol":
            if dist <= 6:
                _chase_move(gs, e)
            else:
                _patrol_move(gs, e)
        elif e.ai == "pack":
            _pack_move(gs, e)
        elif e.ai == "ambush":
            _ambush_move(gs, e)
        elif e.ai == "ranged":
            _ranged_move(gs, e)
        elif e.ai == "summoner":
            _summoner_move(gs, e)
        elif e.ai == "mimic":
            _mimic_move(gs, e)
        elif e.ai == "phase":
            _phase_move(gs, e)
        elif e.ai == "mind_flayer":
            _mind_flayer_move(gs, e)
        else:
            _chase_move(gs, e)
        # Fire aura: deal damage to adjacent player after move
        if e.fire_aura and e.is_alive():
            if abs(e.x - p.x) + abs(e.y - p.y) <= 1:
                # Water blocks fire aura (steam)
                if gs.tiles[p.y][p.x] == T_WATER:
                    pass  # Steam blocks fire aura
                elif "fire" in p.player_resists():
                    pass  # Fire resistance blocks aura
                else:
                    aura_dmg = random.randint(1, 3)
                    p.hp -= aura_dmg
                    p.damage_taken += aura_dmg
                    if gs.turn_count % 2 == 0:
                        gs.msg(f"The {e.name}'s flames sear you! (-{aura_dmg})", C_LAVA)
                    if p.hp <= 0:
                        gs.game_over = True
                        gs.death_cause = f"burned by {e.name}"
                        sound_alert(gs, "death")
    gs.enemies = [e for e in gs.enemies if e.is_alive()]


def _try_enemy_move(gs, e, dx, dy):
    nx, ny = e.x + dx, e.y + dy
    if nx < 0 or nx >= MAP_W or ny < 0 or ny >= MAP_H:
        return
    if gs.tiles[ny][nx] not in WALKABLE:
        return
    if gs.tiles[ny][nx] == T_LAVA:
        return
    if nx == gs.player.x and ny == gs.player.y:
        enemy_attack(gs, e)
        return
    if any(o.x == nx and o.y == ny and o.is_alive() for o in gs.enemies if o is not e):
        return
    e.x = nx
    e.y = ny
    # Enemy trap check
    for trap in gs.traps:
        if trap["x"] == nx and trap["y"] == ny and not trap["disarmed"] and not trap["triggered"] and not trap["visible"]:
            hp_ref = [e.hp]
            _trigger_trap(gs, trap, target_name=e.name, target_hp_ref=hp_ref, is_player=False)
            e.hp = hp_ref[0]
            break


def _flee_move(gs, e):
    """Move enemy away from player. If cornered, stop fleeing and fight."""
    p = gs.player
    # Primary flee direction: away from player
    dx = 0 if e.x == p.x else (1 if e.x > p.x else -1)
    dy = 0 if e.y == p.y else (1 if e.y > p.y else -1)
    # Try flee directions in priority order
    candidates = [(dx, dy), (dx, 0), (0, dy), (-dx, dy), (dx, -dy), (0, -dy), (-dx, 0), (-dx, -dy)]
    for cdx, cdy in candidates:
        if cdx == 0 and cdy == 0:
            continue
        nx, ny = e.x + cdx, e.y + cdy
        if (0 <= nx < MAP_W and 0 <= ny < MAP_H
                and gs.tiles[ny][nx] in WALKABLE and gs.tiles[ny][nx] != T_LAVA
                and not (nx == p.x and ny == p.y)
                and not any(o.x == nx and o.y == ny and o.is_alive() for o in gs.enemies if o is not e)):
            e.x = nx
            e.y = ny
            return
    # Cornered: stop fleeing, fight to the death
    e.fleeing = False
    gs.msg(f"The {e.name} is cornered!", C_YELLOW)
    # Attack player if adjacent
    if abs(e.x - p.x) + abs(e.y - p.y) <= 1:
        enemy_attack(gs, e)


def _chase_move(gs, e):
    p = gs.player
    step = astar(gs.tiles, e.x, e.y, p.x, p.y)
    if step:
        _try_enemy_move(gs, e, step[0], step[1])
    else:
        dx = 0 if p.x == e.x else (1 if p.x > e.x else -1)
        dy = 0 if p.y == e.y else (1 if p.y > e.y else -1)
        if random.random() < 0.5:
            _try_enemy_move(gs, e, dx, 0)
        else:
            _try_enemy_move(gs, e, 0, dy)


def _erratic_move(gs, e):
    if random.random() < 0.5:
        _chase_move(gs, e)
    else:
        dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
        _try_enemy_move(gs, e, dx, dy)


def _patrol_move(gs, e):
    dx, dy = e.patrol_dir
    nx, ny = e.x + dx, e.y + dy
    if nx < 0 or nx >= MAP_W or ny < 0 or ny >= MAP_H or gs.tiles[ny][nx] == T_WALL:
        e.patrol_dir = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
    else:
        _try_enemy_move(gs, e, dx, dy)


def _pack_move(gs, e):
    pack_nearby = sum(1 for o in gs.enemies if o is not e and o.ai == "pack"
                      and abs(o.x-e.x)+abs(o.y-e.y) <= 5 and o.is_alive())
    p = gs.player
    dist = abs(e.x - p.x) + abs(e.y - p.y)
    if pack_nearby >= 1:
        _chase_move(gs, e)
    elif dist <= 1:
        enemy_attack(gs, e)
    elif dist > 4:
        _chase_move(gs, e)
    else:
        dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
        _try_enemy_move(gs, e, dx, dy)


def _ambush_move(gs, e):
    dist = abs(e.x - gs.player.x) + abs(e.y - gs.player.y)
    if dist <= 3:
        _chase_move(gs, e)


def _ranged_move(gs, e):
    p = gs.player
    dist = abs(e.x - p.x) + abs(e.y - p.y)
    if dist <= 1:
        enemy_attack(gs, e)
    elif dist <= 5 and _has_los(gs.tiles, e.x, e.y, p.x, p.y):
        dmg = random.randint(e.dmg[0], e.dmg[1])
        dmg = max(1, dmg - p.total_defense() // 3)
        if random.randint(1, 100) <= p.evasion_chance() + 10:
            gs.msg("An arrow whizzes past you!", C_YELLOW)
        else:
            p.hp -= dmg
            p.damage_taken += dmg
            gs.msg(f"The {e.name} shoots you for {dmg}!", C_RED)
            if p.hp <= 0:
                gs.game_over = True
                gs.death_cause = f"shot by {e.name}"
                sound_alert(gs, "death")
    elif dist < 3:
        dx = -1 if p.x > e.x else 1
        _try_enemy_move(gs, e, dx, 0)
    else:
        _chase_move(gs, e)


def _summoner_move(gs, e):
    p = gs.player
    dist = abs(e.x - p.x) + abs(e.y - p.y)
    if dist <= 1:
        enemy_attack(gs, e)
        return
    if e.summon_cooldown <= 0 and len(gs.enemies) < 25:
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            sx, sy = e.x+ddx, e.y+ddy
            if (0 < sx < MAP_W-1 and 0 < sy < MAP_H-1 and
                gs.tiles[sy][sx] in WALKABLE and
                not any(o.x == sx and o.y == sy for o in gs.enemies)):
                mt = random.choice(["rat", "bat", "skeleton", "goblin"])
                minion = Enemy(sx, sy, mt)
                minion.alerted = True
                gs.enemies.append(minion)
                gs.msg(f"The {e.name} summons a {minion.name}!", C_MAGENTA)
                e.summon_cooldown = 5
                break
    if dist < 4:
        dx = -1 if p.x > e.x else 1
        _try_enemy_move(gs, e, dx, 0)
    elif dist > 8:
        _chase_move(gs, e)


def _mimic_move(gs, e):
    """Mimic AI: stays disguised as gold until player is adjacent, then reveals and attacks."""
    p = gs.player
    dist = abs(e.x - p.x) + abs(e.y - p.y)
    if e.disguised:
        if dist <= 1:
            e.disguised = False
            e.char = ENEMY_TYPES[e.etype]["char"]
            gs.msg("The gold pile was a Mimic!", C_RED)
            sound_alert(gs, "boss_encounter")
            enemy_attack(gs, e)
        # Stay still when disguised
        return
    # Once revealed, chase aggressively
    if dist <= 1:
        enemy_attack(gs, e)
    else:
        _chase_move(gs, e)


def _phase_move(gs, e):
    """Phase Spider AI: teleports every N turns, then chases. Poison on hit handled by enemy_attack."""
    p = gs.player
    dist = abs(e.x - p.x) + abs(e.y - p.y)
    e.phase_cooldown -= 1
    if e.phase_cooldown <= 0 and dist > 2:
        # Teleport to a random walkable tile near the player
        candidates = []
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                nx, ny = p.x + dx, p.y + dy
                if (0 < nx < MAP_W-1 and 0 < ny < MAP_H-1 and
                    gs.tiles[ny][nx] in WALKABLE and
                    not (nx == p.x and ny == p.y) and
                    not any(o.x == nx and o.y == ny and o.is_alive() for o in gs.enemies if o is not e)):
                    candidates.append((nx, ny))
        if candidates:
            nx, ny = random.choice(candidates)
            e.x, e.y = nx, ny
            e.phase_cooldown = e.phase_cooldown_max
            if (e.x, e.y) in gs.visible:
                gs.msg(f"The {e.name} phases in nearby!", C_MAGENTA)
            return
    # Normal chase
    if dist <= 1:
        enemy_attack(gs, e)
    else:
        _chase_move(gs, e)


def _mind_flayer_move(gs, e):
    """Mind Flayer AI: psychic attack through walls at range, paralyze on hit."""
    p = gs.player
    dist = abs(e.x - p.x) + abs(e.y - p.y)
    if dist <= 1:
        enemy_attack(gs, e)
        return
    # Psychic blast: ignores walls, hits at range
    if dist <= e.psychic_range:
        dmg = random.randint(e.dmg[0], e.dmg[1])
        dmg = max(1, dmg - p.total_defense() // B["defense_divisor"])
        if random.randint(1, 100) <= p.evasion_chance():
            gs.msg(f"You resist the {e.name}'s psychic blast!", C_CYAN)
        else:
            p.hp -= dmg
            p.damage_taken += dmg
            gs.msg(f"The {e.name}'s psychic blast hits for {dmg}!", C_MAGENTA)
            # Paralyze chance on psychic attack
            if p.hp > 0 and e.paralyze_chance and random.random() < e.paralyze_chance:
                if "Paralysis" not in p.status_effects:
                    p.status_effects["Paralysis"] = B["paralysis_duration"]
                    gs.msg("Your mind goes blank! Paralyzed!", C_YELLOW)
            if p.hp <= 0:
                gs.game_over = True
                gs.death_cause = f"slain by {e.name}"
                sound_alert(gs, "death")
        return
    # Move closer if out of range
    _chase_move(gs, e)


# ============================================================
# ITEM USE
# ============================================================

def use_potion(gs, item):
    p = gs.player
    eff = item.data["effect"]
    p.potions_drunk += 1
    if eff not in gs.id_potions:
        gs.id_potions.add(eff)
        gs.msg(f"It was a Potion of {eff}!", C_MAGENTA)
        # Also identify any in inventory
        for inv in p.inventory:
            if inv.item_type == "potion" and inv.data.get("effect") == eff:
                inv.identified = True
    # Journal: record identified effect (#6)
    gs.journal[f"Potion of {eff}"] = _journal_potion_desc(eff)
    if eff == "Healing":
        h = random.randint(B["heal_potion_min"], B["heal_potion_max"]) + p.level * B["heal_potion_level_scale"]
        p.hp = min(p.max_hp, p.hp + h)
        gs.msg(f"You feel much better! (+{h} HP)", C_GREEN)
    elif eff == "Strength":
        p.status_effects["Strength"] = B["strength_duration_base"] + p.level * B["strength_duration_level_scale"]
        gs.msg("Power surges through your muscles!", C_YELLOW)
    elif eff == "Speed":
        p.status_effects["Speed"] = B["speed_duration_base"] + p.level * B["speed_duration_level_scale"]
        gs.msg("Everything seems to slow down!", C_CYAN)
    elif eff == "Poison":
        d = random.randint(5, 15)
        p.hp -= d
        gs.msg(f"Urgh! Poison! (-{d} HP)", C_RED)
        if p.hp <= 0:
            gs.game_over = True
            gs.death_cause = "poison"
            sound_alert(gs, "death")
    elif eff == "Blindness":
        p.status_effects["Blindness"] = B["blindness_duration"]
        gs.msg("Everything goes dark!", C_DARK)
    elif eff == "Experience":
        xp = p.xp_next // 2
        p.xp += xp
        gs.msg(f"Wisdom fills your mind! (+{xp} XP)", C_YELLOW)
        for lvl, hp_g, str_g, mp_g in p.check_level_up():
            gs.msg(f"*** LEVEL UP! Level {lvl}! +{hp_g} HP, +{str_g} STR, +{mp_g} MP ***", C_YELLOW)
    elif eff == "Resistance":
        p.status_effects["Resistance"] = B["resistance_duration"]
        gs.msg("Your skin hardens!", C_BLUE)
    elif eff == "Berserk":
        p.status_effects["Berserk"] = B["berserk_duration"]
        gs.msg("BLOOD RAGE! You see red!", C_RED)
    p.inventory.remove(item)


def use_scroll(gs, item):
    p = gs.player
    eff = item.data["effect"]
    p.scrolls_read += 1
    if eff not in gs.id_scrolls:
        gs.id_scrolls.add(eff)
        gs.msg(f"It was a Scroll of {eff}!", C_YELLOW)
        for inv in p.inventory:
            if inv.item_type == "scroll" and inv.data.get("effect") == eff:
                inv.identified = True
    # Journal: record identified effect (#6)
    gs.journal[f"Scroll of {eff}"] = _journal_scroll_desc(eff)
    if eff == "Identify":
        for inv in p.inventory:
            inv.identified = True
        gs.msg("Your possessions glow with knowledge!", C_CYAN)
    elif eff == "Teleport":
        pos = gs._find_spawn_pos()
        if pos:
            p.x, p.y = pos
            gs.msg("Reality blinks! You're somewhere else!", C_MAGENTA)
    elif eff == "Fireball":
        kills = 0
        for e in gs.enemies:
            if abs(e.x-p.x) + abs(e.y-p.y) <= 4:
                e.hp -= random.randint(15, 30)
                if not e.is_alive():
                    kills += _award_kill(gs, e, msg=False)
        gs.msg(f"FIRE ERUPTS! {kills} enemies caught in the blast!", C_RED)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
    elif eff == "Mapping":
        for y in range(MAP_H):
            for x in range(MAP_W):
                if gs.tiles[y][x] != T_WALL:
                    gs.explored[y][x] = True
        gs.msg("The entire floor is revealed!", C_CYAN)
    elif eff == "Enchant":
        if p.weapon:
            p.weapon.data["bonus"] = p.weapon.data.get("bonus", 0) + 2
            lo, hi = p.weapon.data["dmg"]
            p.weapon.data["dmg"] = (lo+1, hi+1)
            gs.msg(f"Your {p.weapon.display_name} glows with power!", C_YELLOW)
        elif p.armor:
            p.armor.data["defense"] += 2
            gs.msg(f"Your {p.armor.display_name} shimmers!", C_YELLOW)
        else:
            gs.msg("The magic dissipates uselessly.", C_DARK)
    elif eff == "Fear":
        c = 0
        for e in gs.enemies:
            if abs(e.x-p.x)+abs(e.y-p.y) <= 8 and not e.boss:
                e.alerted = False
                c += 1
        gs.msg(f"{c} enemies flee in terror!", C_MAGENTA)
    elif eff == "Summon":
        pos = gs._find_spawn_pos()
        if pos:
            mt = random.choice(["goblin", "skeleton", "orc"])
            m = Enemy(pos[0], pos[1], mt)
            m.alerted = True
            gs.enemies.append(m)
            gs.msg(f"A hostile {m.name} appears! Bad scroll!", C_RED)
    elif eff == "Lightning":
        nearest = None
        nd = 999
        for e in gs.enemies:
            d = abs(e.x-p.x) + abs(e.y-p.y)
            if d < nd:
                nearest = e
                nd = d
        if nearest and nd <= 10:
            dmg = random.randint(20, 40)
            nearest.hp -= dmg
            gs.msg(f"Lightning strikes {nearest.name} for {dmg}!", C_CYAN)
            if not nearest.is_alive():
                _award_kill(gs, nearest, msg=f"The {nearest.name} is destroyed!")
                gs.enemies = [e for e in gs.enemies if e.is_alive()]
        else:
            gs.msg("Lightning crackles harmlessly.", C_CYAN)
    p.inventory.remove(item)


def use_food(gs, item):
    p = gs.player
    n = item.data.get("nutrition", 20)
    p.hunger = min(100, p.hunger + n)
    p.foods_eaten += 1
    gs.msg(f"You eat the {item.display_name}. ({n} nutrition)", C_GREEN)
    if item.data.get("name") == "Mystery Meat" and random.random() < 0.2:
        d = random.randint(1, 5)
        gs.msg(f"Ugh, that tasted terrible! (-{d} HP)", C_RED)
        p.hp -= d
        if p.hp <= 0:
            gs.game_over = True
            gs.death_cause = "food poisoning"
            sound_alert(gs, "death")
    p.inventory.remove(item)


def pray_at_shrine(gs):
    p = gs.player
    roll = random.random()
    threshold_heal = B["shrine_full_heal_chance"]
    threshold_maxhp = threshold_heal + B["shrine_max_hp_chance"]
    threshold_str = threshold_maxhp + B["shrine_str_chance"]
    threshold_def = threshold_str + B["shrine_def_chance"]
    threshold_nothing = threshold_def + B["shrine_nothing_chance"]
    if roll < threshold_heal:
        p.hp = p.max_hp
        gs.msg("Divine light! Fully restored!", C_YELLOW)
    elif roll < threshold_maxhp:
        p.max_hp += 5
        p.hp += 5
        gs.msg("Vitality increases! (+5 max HP)", C_GREEN)
    elif roll < threshold_str:
        p.strength += 2
        gs.msg("Strength flows through you! (+2 STR)", C_YELLOW)
    elif roll < threshold_def:
        p.defense += 2
        gs.msg("Your body toughens! (+2 DEF)", C_BLUE)
    elif roll < threshold_nothing:
        gs.msg("The shrine is silent.", C_DARK)
    else:
        # Curse: lose some% of current HP, but never instakill
        pct = random.uniform(B["shrine_curse_min_pct"], B["shrine_curse_max_pct"])
        d = max(1, int(p.hp * pct))
        p.hp -= d
        gs.msg(f"A dark energy courses through you! (-{d} HP)", C_RED)
        if p.hp <= 0:
            p.hp = 1  # Shrine curse is punishing but not lethal
            gs.msg("You barely cling to life!", C_RED)
        sound_alert(gs, "low_hp")
    gs.tiles[p.y][p.x] = T_FLOOR


def process_status(gs):
    expired = []
    p = gs.player
    for eff, turns in list(p.status_effects.items()):
        # Poison tick damage
        if eff == "Poison":
            dmg = B["poison_damage_per_tick"]
            p.hp -= dmg
            p.damage_taken += dmg
            if gs.turn_count % 3 == 0:
                gs.msg(f"Poison courses through you! (-{dmg} HP)", C_GREEN)
            if p.hp <= 0:
                gs.game_over = True
                gs.death_cause = "poison"
                gs.msg("You succumb to poison...", C_GREEN)
                sound_alert(gs, "death")
                return
        p.status_effects[eff] = turns - 1
        if p.status_effects[eff] <= 0:
            expired.append(eff)
            del p.status_effects[eff]
    for eff in expired:
        gs.msg(f"{eff} wears off.", C_DARK)
    # Mana regen
    if gs.turn_count % MANA_REGEN_INTERVAL == 0 and gs.player.mana < gs.player.max_mana:
        gs.player.mana = min(gs.player.max_mana, gs.player.mana + 1)
    # Torch fuel burn (only when lit)
    if gs.player.torch_lit and gs.player.torch_fuel > 0:
        gs.player.torch_fuel -= 1
        if gs.player.torch_fuel == 50:
            gs.msg("Your torch flickers...", C_YELLOW)
        elif gs.player.torch_fuel == 0:
            gs.msg("Your torch goes out! Darkness closes in!", C_RED)
            sound_alert(gs, "low_torch")
    # Frozen enemy tick
    for e in gs.enemies:
        if e.frozen_turns > 0:
            e.frozen_turns -= 1
    # Class ability cooldown tick
    if p.ability_cooldown > 0:
        p.ability_cooldown -= 1


def sound_alert(gs, event):
    """Play terminal bell/flash for key events. Sparse — only critical moments."""
    if gs._headless:
        return
    try:
        if event == "level_up":
            curses.beep()
        elif event == "critical_hit":
            if gs._scr:
                curses.flash()
        elif event == "low_hp":
            curses.beep()
        elif event == "rare_item":
            curses.beep()
        elif event == "boss_encounter":
            curses.beep()
        elif event == "death":
            curses.beep()
        elif event == "low_torch":
            curses.beep()
    except Exception:
        pass


# ============================================================
# PROJECTILES
# ============================================================

def _get_direction_delta(key):
    """Convert a key to a (dx, dy) direction for projectiles/spells.
    Supports cardinal AND diagonal directions (yubn vi keys)."""
    DIR_KEYS = {
        curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
        curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
        ord('w'): (0,-1), ord('s'): (0,1),
        ord('a'): (-1,0), ord('d'): (1,0),
        ord('h'): (-1,0), ord('j'): (0,1),
        ord('k'): (0,-1), ord('l'): (1,0),
        # Diagonal support
        ord('y'): (-1,-1), ord('u'): (1,-1),
        ord('b'): (-1,1), ord('n'): (1,1),
    }
    return DIR_KEYS.get(key)


def _animate_projectile(gs, path, char='*', color=C_YELLOW):
    """Briefly flash the projectile along its path (skip in headless)."""
    if gs._headless or not gs._scr:
        return
    scr = gs._scr
    p = gs.player
    cam_x = max(0, min(p.x - VIEW_W//2, MAP_W - VIEW_W))
    cam_y = max(0, min(p.y - VIEW_H//2, MAP_H - VIEW_H))
    for (px, py) in path:
        sx = px - cam_x
        sy = py - cam_y
        if 0 <= sx < VIEW_W and 0 <= sy < VIEW_H:
            try:
                safe_addstr(scr, sy, sx, char, curses.color_pair(color) | curses.A_BOLD)
                scr.refresh()
                curses.napms(30)
            except Exception:
                pass


def fire_projectile(gs, scr):
    """Handle 'f' key — fire arrows, throw daggers, or zap wands."""
    p = gs.player
    # Determine what to fire
    options = []
    # Check for bow + arrows
    if p.bow:
        arrow_item = None
        for inv in p.inventory:
            if inv.item_type == "arrow" and inv.count > 0:
                arrow_item = inv
                break
        if arrow_item:
            options.append(("arrow", arrow_item))
    # Check for throwing daggers
    for inv in p.inventory:
        if inv.item_type == "throwing_dagger" and inv.count > 0:
            options.append(("dagger", inv))
            break
    # Check for wands
    for inv in p.inventory:
        if inv.item_type == "wand" and inv.data.get("charges", 0) > 0:
            options.append(("wand", inv))
            break

    if not options:
        gs.msg("Nothing to fire! Need bow+arrows, daggers, or a wand.", C_RED)
        return False

    # If multiple options, pick first available (arrows > daggers > wands)
    proj_type, proj_item = options[0]

    if scr:
        gs.msg("Fire direction? (wasd/arrows/hjkl/yubn, ESC cancel)", C_YELLOW)
        render_game(scr, gs)
        key = scr.getch()
    else:
        return False

    if key == 27:  # ESC
        gs.msg("Cancelled.", C_WHITE)
        return False
    direction = _get_direction_delta(key)
    if not direction:
        gs.msg("Cancelled (invalid direction).", C_WHITE)
        return False

    dx, dy = direction
    return _launch_projectile(gs, dx, dy, proj_type, proj_item)


def fire_projectile_headless(gs, dx, dy):
    """Fire projectile in headless mode (for testing)."""
    p = gs.player
    # Determine what to fire (same priority)
    if p.bow:
        for inv in p.inventory:
            if inv.item_type == "arrow" and inv.count > 0:
                return _launch_projectile(gs, dx, dy, "arrow", inv)
    for inv in p.inventory:
        if inv.item_type == "throwing_dagger" and inv.count > 0:
            return _launch_projectile(gs, dx, dy, "dagger", inv)
    for inv in p.inventory:
        if inv.item_type == "wand" and inv.data.get("charges", 0) > 0:
            return _launch_projectile(gs, dx, dy, "wand", inv)
    return False


def _launch_projectile(gs, dx, dy, proj_type, proj_item):
    """Actually fire the projectile along a line."""
    p = gs.player
    p.projectiles_fired += 1

    if proj_type == "arrow":
        max_range = p.bow.data.get("range", 6)
        base_dmg = p.bow.data["dmg"]
        bonus = p.bow.data.get("bonus", 0)
        proj_item.count -= 1
        if proj_item.count <= 0:
            p.inventory.remove(proj_item)
        char = '-' if dy == 0 else '|'
        color = C_YELLOW
    elif proj_type == "dagger":
        max_range = 5
        base_dmg = proj_item.data["dmg"]
        bonus = 0
        proj_item.count -= 1
        if proj_item.count <= 0:
            p.inventory.remove(proj_item)
        char = '/' if dx != 0 and dy != 0 else ('-' if dy == 0 else '|')
        color = C_WHITE
    elif proj_type == "wand":
        max_range = 8
        base_dmg = proj_item.data["dmg"]
        bonus = 0
        # Wand class scaling (#8)
        if p.player_class == "mage":
            max_range += B["wand_mage_range_bonus"]
        proj_item.data["charges"] -= 1
        if proj_item.data["charges"] <= 0:
            gs.msg(f"The {proj_item.data['name']} crumbles to dust!", C_DARK)
            if proj_item in p.inventory:
                p.inventory.remove(proj_item)
        char = '*'
        color = C_MAGENTA
    else:
        return False

    # Trace the path
    x, y = p.x, p.y
    path = []
    hit_enemy = None
    for _ in range(max_range):
        x += dx
        y += dy
        if x < 0 or x >= MAP_W or y < 0 or y >= MAP_H:
            break
        if gs.tiles[y][x] == T_WALL:
            break
        path.append((x, y))
        # Check for enemy
        for e in gs.enemies:
            if e.x == x and e.y == y and e.is_alive():
                hit_enemy = e
                break
        if hit_enemy:
            break

    _animate_projectile(gs, path, char, color)

    if hit_enemy:
        dmg = random.randint(base_dmg[0], base_dmg[1]) + bonus + p.strength // 4
        # Wand class scaling (#8)
        if proj_type == "wand":
            if p.player_class == "mage":
                dmg = int(dmg * (1 + B["wand_mage_bonus_pct"]))
            elif p.player_class == "warrior":
                dmg = int(dmg * (1 - B["wand_warrior_penalty_pct"]))
        dmg = max(1, dmg - hit_enemy.defense // B["defense_divisor"])
        crit = random.random() < B["ranged_crit_chance"]
        if crit:
            dmg = int(dmg * B["crit_multiplier"])
            gs.msg(f"CRITICAL SHOT! {hit_enemy.name} takes {dmg}!", C_YELLOW)
            sound_alert(gs, "critical_hit")
        else:
            gs.msg(f"You hit {hit_enemy.name} for {dmg}!", C_WHITE)
        hit_enemy.hp -= dmg
        p.damage_dealt += dmg
        if not hit_enemy.is_alive():
            _award_kill(gs, hit_enemy)
            gs.enemies = [e for e in gs.enemies if e.is_alive()]
            _check_levelups(gs)
    else:
        gs.msg("The shot flies into the darkness.", C_DARK)

    return True


# ============================================================
# SPELLS
# ============================================================

def cast_spell_menu(gs, scr):
    """Show spell menu, cast selected spell."""
    p = gs.player
    if scr is None:
        return False

    scr.erase()
    safe_addstr(scr, 0, 1, "SPELLS", curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 1, 1, f"Mana: {p.mana}/{p.max_mana}", curses.color_pair(C_CYAN))

    spell_list = [(name, info) for name, info in SPELLS.items() if name in p.known_spells]
    max_letter = chr(ord('a') + len(spell_list) - 1) if spell_list else 'a'
    for i, (name, info) in enumerate(spell_list):
        y = i + 3
        if y >= SCREEN_H - 2:
            break
        letter = chr(ord('a') + i)
        cost_color = C_CYAN if p.mana >= info["cost"] else C_RED
        safe_addstr(scr, y, 2, f"{letter}) {name}", curses.color_pair(C_WHITE))
        safe_addstr(scr, y, 22, f"[{info['cost']} MP]", curses.color_pair(cost_color))
        safe_addstr(scr, y, 32, info["desc"][:SCREEN_W-34], curses.color_pair(C_DARK))

    safe_addstr(scr, SCREEN_H-1, 1, f"[a-{max_letter}] Cast  [ESC] Cancel", curses.color_pair(C_DARK))
    scr.refresh()
    key = scr.getch()
    if key == 27:
        return False
    idx = key - ord('a')
    if idx < 0 or idx >= len(spell_list):
        return False

    spell_name, spell_info = spell_list[idx]
    if p.mana < spell_info["cost"]:
        gs.msg("Not enough mana!", C_RED)
        return False

    return _cast_spell(gs, scr, spell_name, spell_info)


def cast_spell_headless(gs, spell_name, direction=None, target_enemy=None):
    """Cast a spell in headless mode (for testing)."""
    p = gs.player
    if spell_name not in SPELLS:
        return False
    if spell_name not in p.known_spells:
        return False
    info = SPELLS[spell_name]
    if p.mana < info["cost"]:
        return False
    return _cast_spell(gs, None, spell_name, info, direction=direction, target_enemy=target_enemy)


def _apply_spell_resist(gs, enemy, dmg, element):
    """Apply elemental resistance/vulnerability to spell damage on an enemy.
    Returns adjusted damage and whether troll regen was suppressed."""
    if element and element != "physical":
        if element in enemy.resists:
            dmg = max(1, int(dmg * (1 - B["resist_reduction_pct"])))
        if element in enemy.vulnerable:
            dmg = int(dmg * B["vulnerable_increase_pct"])
        if enemy.etype == "troll" and element == "fire":
            enemy.regen_suppressed = 5
    return dmg


def _cast_spell(gs, scr, spell_name, spell_info, direction=None, target_enemy=None):
    """Execute the spell effect."""
    p = gs.player
    p.mana -= spell_info["cost"]
    # Spells generate noise (stealth system)
    gs.last_noise = max(gs.last_noise, _compute_noise(gs, "spell"))
    p.spells_cast += 1

    if spell_name == "Fireball":
        if direction is None and scr:
            gs.msg("Fireball direction? (wasd/arrows/hjkl)", C_YELLOW)
            render_game(scr, gs)
            key = scr.getch()
            direction = _get_direction_delta(key)
        if direction is None:
            p.mana += spell_info["cost"]  # refund
            p.spells_cast -= 1
            gs.msg("Cancelled.", C_WHITE)
            return False
        dx, dy = direction
        # Center of blast is 3 tiles away in that direction
        cx = p.x + dx * 3
        cy = p.y + dy * 3
        # Animate path
        path = []
        for i in range(1, 4):
            path.append((p.x + dx*i, p.y + dy*i))
        _animate_projectile(gs, path, '*', C_RED)
        # 3x3 AoE
        kills = 0
        total_dmg = 0
        for ey in range(cy-1, cy+2):
            for ex in range(cx-1, cx+2):
                for e in gs.enemies:
                    if e.x == ex and e.y == ey and e.is_alive():
                        dmg = random.randint(B["fireball_min"], B["fireball_max"]) + p.level * B["fireball_level_scale"]
                        dmg = _apply_spell_resist(gs, e, dmg, "fire")
                        e.hp -= dmg
                        total_dmg += dmg
                        p.damage_dealt += dmg
                        if not e.is_alive():
                            kills += _award_kill(gs, e, msg=False)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        gs.msg(f"FIREBALL! {kills} killed, {total_dmg} total damage!", C_RED)
        _check_levelups(gs)
        return True

    elif spell_name == "Lightning Bolt":
        if direction is None and scr:
            gs.msg("Lightning direction? (wasd/arrows/hjkl)", C_YELLOW)
            render_game(scr, gs)
            key = scr.getch()
            direction = _get_direction_delta(key)
        if direction is None:
            p.mana += spell_info["cost"]
            p.spells_cast -= 1
            gs.msg("Cancelled.", C_WHITE)
            return False
        dx, dy = direction
        # Hits ALL enemies in the line
        x, y = p.x, p.y
        path = []
        hits = 0
        total_dmg = 0
        for _ in range(12):
            x += dx
            y += dy
            if x < 0 or x >= MAP_W or y < 0 or y >= MAP_H:
                break
            if gs.tiles[y][x] == T_WALL:
                break
            path.append((x, y))
            for e in gs.enemies:
                if e.x == x and e.y == y and e.is_alive():
                    dmg = random.randint(B["lightning_min"], B["lightning_max"]) + p.level * B["lightning_level_scale"]
                    dmg = _apply_spell_resist(gs, e, dmg, "lightning")
                    e.hp -= dmg
                    total_dmg += dmg
                    p.damage_dealt += dmg
                    hits += 1
                    if not e.is_alive():
                        _award_kill(gs, e, msg=False)
        _animate_projectile(gs, path, '#', C_CYAN)
        # Lightning + Water AoE: if bolt hits a water tile, damage entities on nearby water
        for px2, py2 in path:
            if 0 <= px2 < MAP_W and 0 <= py2 < MAP_H and gs.tiles[py2][px2] == T_WATER:
                gs.msg("Lightning arcs through the water!", C_YELLOW)
                for e in gs.enemies:
                    if (e.is_alive() and gs.tiles[e.y][e.x] == T_WATER
                            and abs(e.x - px2) + abs(e.y - py2) <= 3):
                        water_dmg = random.randint(5, 15)
                        water_dmg = _apply_spell_resist(gs, e, water_dmg, "lightning")
                        e.hp -= water_dmg
                        total_dmg += water_dmg
                        p.damage_dealt += water_dmg
                        if not e.is_alive():
                            hits += 1
                            _award_kill(gs, e, msg=False)
                break  # Only trigger water AoE once
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        gs.msg(f"LIGHTNING! Hit {hits} enemies for {total_dmg} damage!", C_CYAN)
        _check_levelups(gs)
        return True

    elif spell_name == "Heal":
        heal_amt = random.randint(B["heal_spell_min"], B["heal_spell_max"]) + p.level * B["heal_spell_level_scale"]
        p.hp = min(p.max_hp, p.hp + heal_amt)
        gs.msg(f"Healing light! (+{heal_amt} HP)", C_GREEN)
        return True

    elif spell_name == "Teleport":
        pos = gs._find_spawn_pos()
        if pos:
            p.x, p.y = pos
            gs.msg("You blink across the dungeon!", C_MAGENTA)
        else:
            gs.msg("The spell fizzles.", C_DARK)
        return True

    elif spell_name == "Freeze":
        # Find nearest enemy in FOV
        nearest = target_enemy
        if nearest is None:
            nd = 999
            for e in gs.enemies:
                if e.is_alive() and (e.x, e.y) in gs.visible:
                    d = abs(e.x - p.x) + abs(e.y - p.y)
                    if d < nd:
                        nd = d
                        nearest = e
        if nearest and nearest.is_alive():
            nearest.frozen_turns = B["freeze_duration"]
            gs.msg(f"The {nearest.name} is frozen solid!", C_CYAN)
            return True
        else:
            gs.msg("No target in sight.", C_DARK)
            p.mana += spell_info["cost"]
            p.spells_cast -= 1
            return False

    elif spell_name == "Chain Lightning":
        # Find nearest visible enemy
        nearest = target_enemy
        if nearest is None:
            nd = 999
            for e in gs.enemies:
                if e.is_alive() and (e.x, e.y) in gs.visible:
                    d = abs(e.x - p.x) + abs(e.y - p.y)
                    if d < nd:
                        nd = d
                        nearest = e
        if nearest is None or not nearest.is_alive():
            gs.msg("No target in sight.", C_DARK)
            p.mana += spell_info["cost"]
            p.spells_cast -= 1
            return False
        # Hit primary target
        base_dmg = random.randint(B["chain_lightning_min"], B["chain_lightning_max"]) + p.level
        base_dmg = _apply_spell_resist(gs, nearest, base_dmg, "lightning")
        nearest.hp -= base_dmg
        p.damage_dealt += base_dmg
        total_dmg = base_dmg
        kills = 0
        chain_targets = [nearest]
        if not nearest.is_alive():
            kills += _award_kill(gs, nearest, msg=False)
        # Chain to up to 2 more enemies within range of each hit
        current_dmg = base_dmg
        last_hit = nearest
        for _ in range(2):
            current_dmg = int(current_dmg * B["chain_lightning_decay"])
            if current_dmg < 1:
                break
            best = None
            best_dist = 999
            for e in gs.enemies:
                if e.is_alive() and e not in chain_targets:
                    d = abs(e.x - last_hit.x) + abs(e.y - last_hit.y)
                    if d <= B["chain_lightning_chain_range"] and d < best_dist:
                        best_dist = d
                        best = e
            if best is None:
                break
            best.hp -= current_dmg
            p.damage_dealt += current_dmg
            total_dmg += current_dmg
            chain_targets.append(best)
            if not best.is_alive():
                kills += _award_kill(gs, best, msg=False)
            last_hit = best
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        gs.msg(f"CHAIN LIGHTNING! {len(chain_targets)} hit, {total_dmg} damage, {kills} killed!", C_CYAN)
        _check_levelups(gs)
        return True

    elif spell_name == "Meteor":
        if direction is None and scr:
            gs.msg("Meteor direction? (wasd/arrows/hjkl)", C_YELLOW)
            render_game(scr, gs)
            key = scr.getch()
            direction = _get_direction_delta(key)
        if direction is None:
            p.mana += spell_info["cost"]
            p.spells_cast -= 1
            gs.msg("Cancelled.", C_WHITE)
            return False
        dx, dy = direction
        # Blast center is meteor_range tiles in that direction
        cx = p.x + dx * B["meteor_range"]
        cy = p.y + dy * B["meteor_range"]
        # 5x5 AoE
        kills = 0
        total_dmg = 0
        for ey in range(cy - 2, cy + 3):
            for ex in range(cx - 2, cx + 3):
                for e in gs.enemies:
                    if e.x == ex and e.y == ey and e.is_alive():
                        dmg = random.randint(B["meteor_min"], B["meteor_max"]) + p.level * B["meteor_level_scale"]
                        dmg = _apply_spell_resist(gs, e, dmg, "fire")
                        e.hp -= dmg
                        total_dmg += dmg
                        p.damage_dealt += dmg
                        if not e.is_alive():
                            kills += _award_kill(gs, e, msg=False)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        gs.msg(f"METEOR! {kills} killed, {total_dmg} total damage!", C_RED)
        _check_levelups(gs)
        return True

    elif spell_name == "Mana Shield":
        p.status_effects["Mana Shield"] = B["mana_shield_duration"]
        gs.msg("A shimmering mana shield surrounds you!", C_CYAN)
        return True

    return False


# ============================================================
# PLAYER ACTIONS
# ============================================================

def use_class_ability(gs, scr=None):
    """Activate the player's class-specific ability. Returns True if turn spent."""
    p = gs.player
    if not p.player_class or p.player_class not in CHARACTER_CLASSES:
        gs.msg("You have no class ability.", C_DARK)
        return False
    cc = CHARACTER_CLASSES[p.player_class]
    if p.ability_cooldown > 0:
        gs.msg(f"{cc['ability']} is on cooldown ({p.ability_cooldown} turns).", C_DARK)
        return False
    if p.mana < cc["ability_cost"]:
        gs.msg(f"Not enough mana for {cc['ability']}! (need {cc['ability_cost']})", C_RED)
        return False

    p.mana -= cc["ability_cost"]

    if p.player_class == "warrior":
        # Battle Cry: freeze all enemies within FOV for 5 turns
        frozen_count = 0
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                dist = abs(e.x - p.x) + abs(e.y - p.y)
                if dist <= 6:
                    e.frozen_turns = max(e.frozen_turns, 5)
                    frozen_count += 1
        gs.msg(f"BATTLE CRY! {frozen_count} enemies frozen in terror!", C_RED)
        p.ability_cooldown = B["battle_cry_cooldown"]
        return True

    elif p.player_class == "mage":
        # Arcane Blast: 3x3 AoE at a chosen direction (like fireball but more damage)
        gs.msg("Arcane Blast direction? (movement key)", C_CYAN)
        if scr:
            render_game(scr, gs)
            key = scr.getch()
            MOVE_KEYS_LOCAL = {
                curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
                curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
                ord('w'): (0,-1), ord('s'): (0,1),
                ord('a'): (-1,0), ord('d'): (1,0),
                ord('h'): (-1,0), ord('j'): (0,1),
                ord('k'): (0,-1), ord('l'): (1,0),
                ord('y'): (-1,-1), ord('u'): (1,-1),
                ord('b'): (-1,1), ord('n'): (1,1),
            }
            if key == 27:
                p.mana += cc["ability_cost"]  # refund
                gs.msg("Cancelled.", C_DARK)
                return False
            if key not in MOVE_KEYS_LOCAL:
                p.mana += cc["ability_cost"]  # refund
                gs.msg("Invalid direction.", C_DARK)
                return False
            dx, dy = MOVE_KEYS_LOCAL[key]
        else:
            dx, dy = 1, 0  # default for headless
        # Hit 3x3 area, 5 tiles out
        cx, cy = p.x + dx * 5, p.y + dy * 5
        hit_count = 0
        kills = 0
        total_dmg = 0
        for e in gs.enemies:
            if e.is_alive() and abs(e.x - cx) <= 1 and abs(e.y - cy) <= 1:
                dmg = random.randint(B["arcane_blast_min"], B["arcane_blast_max"]) + p.strength
                e.hp -= dmg
                p.damage_dealt += dmg
                total_dmg += dmg
                hit_count += 1
                gs.msg(f"Arcane Blast hits {e.name} for {dmg}!", C_CYAN)
                if not e.is_alive():
                    kills += _award_kill(gs, e)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        gs.msg(f"Arcane Blast detonates! ({hit_count} hit, {kills} killed)", C_CYAN)
        _check_levelups(gs)
        p.ability_cooldown = B["ability_cooldown"]
        return True

    elif p.player_class == "rogue":
        # Shadow Step: teleport behind nearest enemy, auto-crit
        target = None
        min_dist = 999
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                d = abs(e.x - p.x) + abs(e.y - p.y)
                if d < min_dist:
                    min_dist = d
                    target = e
        if not target:
            p.mana += cc["ability_cost"]  # refund
            gs.msg("No visible enemy to Shadow Step to!", C_DARK)
            return False
        # Find tile behind enemy (opposite side from player)
        dx = 1 if target.x > p.x else (-1 if target.x < p.x else 0)
        dy = 1 if target.y > p.y else (-1 if target.y < p.y else 0)
        land_x, land_y = target.x + dx, target.y + dy
        # If landing spot is blocked, land on enemy's tile (attack from current)
        if (0 < land_x < MAP_W-1 and 0 < land_y < MAP_H-1 and
            gs.tiles[land_y][land_x] in WALKABLE and
            not any(e2.x == land_x and e2.y == land_y and e2.is_alive() for e2 in gs.enemies)):
            p.x, p.y = land_x, land_y
        gs.msg(f"You shadow step behind the {target.name}!", C_GREEN)
        # Auto-crit damage
        if p.weapon:
            lo, hi = p.weapon.data["dmg"]
            base_dmg = random.randint(lo, hi) + p.weapon.data.get("bonus", 0) + p.strength
        else:
            base_dmg = random.randint(1, 3) + p.strength
        crit_dmg = int(base_dmg * B["crit_multiplier"])
        target.hp -= crit_dmg
        p.damage_dealt += crit_dmg
        gs.msg(f"CRITICAL! Shadow Strike hits for {crit_dmg}!", C_YELLOW)
        if not target.is_alive():
            _award_kill(gs, target)
            gs.enemies = [e for e in gs.enemies if e.is_alive()]
            _check_levelups(gs)
        p.ability_cooldown = B["shadow_step_cooldown"]
        return True

    return False


# ============================================================
# CLASS TECHNIQUES (Warrior/Rogue abilities — parallel to spells)
# ============================================================

def use_technique_menu(gs, scr):
    """Show class technique menu, execute selected ability."""
    p = gs.player
    if scr is None:
        return False
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)

    if p.player_class == "mage":
        gs.msg("No class techniques. Use [z] for spells.", C_DARK)
        return False

    abilities = CLASS_ABILITIES.get(p.player_class, {})
    known = [(name, info) for name, info in abilities.items() if name in p.known_abilities]

    if not known:
        gs.msg("You haven't learned any techniques yet.", C_DARK)
        return False

    title = "COMBAT TECHNIQUES" if p.player_class == "warrior" else "TECHNIQUES"
    scr.erase()
    safe_addstr(scr, 0, 1, title, curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 1, 1, f"Mana: {p.mana}/{p.max_mana}", curses.color_pair(C_CYAN))

    max_letter = chr(ord('a') + len(known) - 1)
    for i, (name, info) in enumerate(known):
        y = i + 3
        if y >= SCREEN_H - 2:
            break
        letter = chr(ord('a') + i)
        cost_color = C_CYAN if p.mana >= info["cost"] else C_RED
        safe_addstr(scr, y, 2, f"{letter}) {name}", curses.color_pair(C_WHITE))
        safe_addstr(scr, y, 22, f"[{info['cost']} MP]", curses.color_pair(cost_color))
        safe_addstr(scr, y, 32, info["desc"][:SCREEN_W-34], curses.color_pair(C_DARK))

    safe_addstr(scr, SCREEN_H-1, 1, f"[a-{max_letter}] Use  [ESC] Cancel", curses.color_pair(C_DARK))
    scr.refresh()
    key = scr.getch()
    if key == 27:
        return False
    idx = key - ord('a')
    if idx < 0 or idx >= len(known):
        return False

    ability_name, ability_info = known[idx]
    if p.mana < ability_info["cost"]:
        gs.msg("Not enough mana!", C_RED)
        return False

    return _execute_ability(gs, scr, ability_name, ability_info)


def use_ability_headless(gs, ability_name):
    """Execute a class ability in headless mode (for bot/agent/tests)."""
    p = gs.player
    if ability_name not in p.known_abilities:
        return False
    abilities = CLASS_ABILITIES.get(p.player_class, {})
    if ability_name not in abilities:
        return False
    info = abilities[ability_name]
    if p.mana < info["cost"]:
        return False
    return _execute_ability(gs, None, ability_name, info)


def _execute_ability(gs, scr, ability_name, ability_info):
    """Execute the ability effect. Returns True if turn was spent."""
    p = gs.player
    p.mana -= ability_info["cost"]

    if ability_name == "Whirlwind":
        # Hit ALL adjacent enemies (8 directions)
        hit_count = 0
        total_dmg = 0
        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                if ddx == 0 and ddy == 0:
                    continue
                tx, ty = p.x + ddx, p.y + ddy
                for e in gs.enemies:
                    if e.x == tx and e.y == ty and e.is_alive():
                        dmg = p.attack_damage()
                        dmg = max(1, dmg - e.defense // B["defense_divisor"])
                        e.hp -= dmg
                        p.damage_dealt += dmg
                        total_dmg += dmg
                        hit_count += 1
                        if not e.is_alive():
                            _award_kill(gs, e)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        if hit_count > 0:
            gs.msg(f"WHIRLWIND! Hit {hit_count} enemies for {total_dmg} total damage!", C_YELLOW)
        else:
            gs.msg("WHIRLWIND! But no enemies were adjacent.", C_DARK)
        _check_levelups(gs)
        return True

    elif ability_name == "Cleaving Strike":
        # Auto-target nearest visible enemy, 2x damage ignoring defense
        target = None
        min_dist = 999
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                d = abs(e.x - p.x) + abs(e.y - p.y)
                if d < min_dist:
                    min_dist = d
                    target = e
        if not target:
            p.mana += ability_info["cost"]  # refund
            gs.msg("No visible enemy to strike!", C_DARK)
            return False
        dmg = int(p.attack_damage() * B["cleaving_strike_multiplier"])
        # Ignore enemy defense
        target.hp -= dmg
        p.damage_dealt += dmg
        gs.msg(f"CLEAVING STRIKE! Hit {target.name} for {dmg} damage, ignoring armor!", C_YELLOW)
        if not target.is_alive():
            _award_kill(gs, target)
        gs.enemies = [e for e in gs.enemies if e.is_alive()]
        _check_levelups(gs)
        return True

    elif ability_name == "Shield Wall":
        p.status_effects["Shield Wall"] = B["shield_wall_duration"]
        gs.msg(f"You raise your shield! Incoming damage halved for {B['shield_wall_duration']} turns.", C_CYAN)
        return True

    elif ability_name == "Backstab":
        # Buff: next melee is guaranteed 2.5x crit (consumed on use)
        p.status_effects["Backstab"] = 99  # effectively infinite, removed on use
        gs.msg("You prepare a deadly backstab...", C_GREEN)
        return True

    elif ability_name == "Poison Blade":
        p.status_effects["Poison Blade"] = B["poison_blade_duration"]
        gs.msg(f"You coat your blade with venom! ({B['poison_blade_duration']} turns)", C_GREEN)
        return True

    elif ability_name == "Smoke Bomb":
        # Freeze + blind all enemies within radius
        hit_count = 0
        for e in gs.enemies:
            if e.is_alive():
                dist = abs(e.x - p.x) + abs(e.y - p.y)
                if dist <= B["smoke_bomb_blind_radius"]:
                    e.frozen_turns = max(e.frozen_turns, B["smoke_bomb_blind_duration"])
                    hit_count += 1
        # Player evasion boost
        p.status_effects["Smoke Evasion"] = B["smoke_bomb_evasion_duration"]
        if hit_count > 0:
            gs.msg(f"SMOKE BOMB! {hit_count} enemies blinded and disoriented!", C_GREEN)
        else:
            gs.msg("SMOKE BOMB! +evasion but no enemies in range.", C_DARK)
        return True

    # Unknown ability
    p.mana += ability_info["cost"]  # refund
    return False


def _unlock_next_ability(player):
    """Unlock the next ability in the class-specific unlock order. Returns ability name or None."""
    unlock_list = ABILITY_UNLOCK_ORDER.get(player.player_class, [])
    for ability_name in unlock_list:
        if ability_name not in player.known_abilities:
            player.known_abilities.add(ability_name)
            return ability_name
    return None


def _journal_potion_desc(eff):
    """Return short description for journal entry (#6)."""
    return {"Healing": "Restores HP", "Strength": "Boost STR temporarily",
            "Speed": "Boost speed temporarily", "Poison": "Deals damage!",
            "Blindness": "Reduces vision!", "Experience": "Grants XP",
            "Resistance": "Reduces incoming damage", "Berserk": "Rage mode"}.get(eff, eff)

def _journal_scroll_desc(eff):
    return {"Identify": "Reveals all items", "Teleport": "Random teleport",
            "Fireball": "AoE fire damage", "Mapping": "Reveals floor map",
            "Enchant": "Upgrades weapon/armor", "Fear": "Scares enemies",
            "Summon": "Summons hostile enemy!", "Lightning": "Zaps nearest enemy"}.get(eff, eff)

def use_alchemy_table(gs):
    """Use alchemy table to identify a random unidentified item (#7)."""
    p = gs.player
    pos_key = (p.x, p.y)
    if gs.tiles[p.y][p.x] != T_ALCHEMY_TABLE:
        gs.msg("No alchemy table here.", C_DARK)
        return False
    if pos_key in gs.alchemy_used:
        gs.msg("This table has already been used.", C_DARK)
        return False
    # Find unidentified potions/scrolls in inventory
    unid = [it for it in p.inventory
            if it.item_type in ("potion", "scroll") and not it.identified]
    if not unid:
        gs.msg("Nothing to identify!", C_DARK)
        return False
    target = random.choice(unid)
    target.identified = True
    eff = target.data.get("effect", "")
    if target.item_type == "potion":
        gs.id_potions.add(eff)
        gs.journal[f"Potion of {eff}"] = _journal_potion_desc(eff)
        # Identify all matching in inventory
        for inv in p.inventory:
            if inv.item_type == "potion" and inv.data.get("effect") == eff:
                inv.identified = True
        gs.msg(f"The table reveals: {target.display_name} is a Potion of {eff}!", C_CYAN)
    else:
        gs.id_scrolls.add(eff)
        gs.journal[f"Scroll of {eff}"] = _journal_scroll_desc(eff)
        for inv in p.inventory:
            if inv.item_type == "scroll" and inv.data.get("effect") == eff:
                inv.identified = True
        gs.msg(f"The table reveals: {target.display_name} is a Scroll of {eff}!", C_CYAN)
    gs.alchemy_used.add(pos_key)
    return True

def _toggle_switch(gs, sx, sy):
    """Toggle a switch and check puzzle state (#9)."""
    tile = gs.tiles[sy][sx]
    if tile == T_SWITCH_OFF:
        gs.tiles[sy][sx] = T_SWITCH_ON
        gs.msg("Click! The switch activates.", C_YELLOW)
    elif tile == T_SWITCH_ON:
        gs.tiles[sy][sx] = T_SWITCH_OFF
        gs.msg("Click! The switch deactivates.", C_YELLOW)
    # Check if any puzzle is solved
    for puzzle in gs.puzzles:
        if puzzle["solved"]:
            continue
        if puzzle["type"] in ("switch", "locked_stairs"):
            all_on = all(gs.tiles[py][px] == T_SWITCH_ON for px, py in puzzle["positions"])
            if all_on:
                puzzle["solved"] = True
                if puzzle["type"] == "locked_stairs":
                    stx, sty = puzzle["stairs"]
                    gs.tiles[sty][stx] = T_STAIRS_DOWN
                    gs.msg("You hear a rumble... The stairs are unlocked!", C_YELLOW)
                else:
                    # Reward: spawn high-tier item
                    rx, ry, rw, rh = puzzle["room"]
                    item = gs._random_item(rx + rw//2, ry + rh//2, gs.player.floor + 2)
                    if item:
                        item.identified = True
                        gs.items.append(item)
                    gs.msg("All switches activated! A chest appears!", C_GOLD)

def _interact_pedestal(gs, px, py):
    """Light a pedestal (costs torch fuel) (#9)."""
    if gs.tiles[py][px] != T_PEDESTAL_UNLIT:
        return False
    if gs.player.torch_fuel < 10:
        gs.msg("Not enough torch fuel to light the pedestal!", C_RED)
        return False
    gs.player.torch_fuel -= 10
    gs.tiles[py][px] = T_PEDESTAL_LIT
    gs.msg("The pedestal flares to life!", C_YELLOW)
    # Check if torch puzzle is solved
    for puzzle in gs.puzzles:
        if puzzle["solved"] or puzzle["type"] != "torch":
            continue
        all_lit = all(gs.tiles[py2][px2] == T_PEDESTAL_LIT for px2, py2 in puzzle["positions"])
        if all_lit:
            puzzle["solved"] = True
            rx, ry, rw, rh = puzzle["room"]
            item = gs._random_item(rx + rw//2, ry + rh//2, gs.player.floor + 2)
            if item:
                item.identified = True
                gs.items.append(item)
            gs.msg("All pedestals lit! A chest materializes!", C_GOLD)
    return True

def show_journal(scr, gs):
    """Display journal of identified items (#6)."""
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    scr.erase()
    safe_addstr(scr, 0, 1, "JOURNAL", curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 1, 1, "Identified potions and scrolls:", curses.color_pair(C_DARK))
    row = 3
    if not gs.journal:
        safe_addstr(scr, row, 2, "Nothing discovered yet.", curses.color_pair(C_DARK))
    else:
        # Group by type
        potions = [(k, v) for k, v in sorted(gs.journal.items()) if k.startswith("Potion")]
        scrolls = [(k, v) for k, v in sorted(gs.journal.items()) if k.startswith("Scroll")]
        if potions:
            safe_addstr(scr, row, 2, "--- Potions ---", curses.color_pair(C_MAGENTA))
            row += 1
            for name, desc in potions:
                if row >= SCREEN_H - 2:
                    break
                color_name = gs.potion_ids.get(name.replace("Potion of ", ""), "?")
                safe_addstr(scr, row, 3, f"{color_name} = {name}: {desc}", curses.color_pair(C_MAGENTA))
                row += 1
        if scrolls:
            row += 1
            safe_addstr(scr, row, 2, "--- Scrolls ---", curses.color_pair(C_YELLOW))
            row += 1
            for name, desc in scrolls:
                if row >= SCREEN_H - 2:
                    break
                label = gs.scroll_ids.get(name.replace("Scroll of ", ""), "?")
                safe_addstr(scr, row, 3, f"{label} = {name}: {desc}", curses.color_pair(C_YELLOW))
                row += 1
    safe_addstr(scr, SCREEN_H - 1, 1, "[ Press any key ]", curses.color_pair(C_DARK))
    scr.refresh()
    scr.getch()


def player_move(gs, dx, dy):
    p = gs.player
    # Confusion: random movement direction
    if "Confusion" in p.status_effects:
        dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
        gs.msg("You stumble in confusion!", C_MAGENTA)
    nx, ny = p.x + dx, p.y + dy
    if nx < 0 or nx >= MAP_W or ny < 0 or ny >= MAP_H:
        return False
    tile = gs.tiles[ny][nx]
    if tile == T_WALL:
        gs.msg("Blocked!", C_DARK)
        return False
    if tile == T_LAVA:
        if "fire" in p.player_resists() or "cold" in p.player_resists():
            gs.msg("You endure the searing heat! (-2 HP)", C_RED)
            p.hp -= 2
            p.damage_taken += 2
            if p.hp <= 0:
                gs.game_over = True
                gs.death_cause = "burned by lava"
                sound_alert(gs, "death")
                return True
        else:
            gs.msg("The lava would burn you alive!", C_RED)
            return False
    # Fear: prevent moving closer to visible enemies
    if "Fear" in p.status_effects:
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                old_dist = abs(e.x - p.x) + abs(e.y - p.y)
                new_dist = abs(e.x - nx) + abs(e.y - ny)
                if new_dist < old_dist:
                    gs.msg("Fear grips you! You can't approach the enemy!", C_MAGENTA)
                    return False
    if tile == T_WATER:
        gs.msg("You splash through water.", C_WATER)
        if random.random() < 0.5:
            p.hunger = max(0, p.hunger - B["hunger_per_move"])  # Extra hunger cost
        # Water extinguishes burning/fire effects
        if "Burning" in p.status_effects:
            del p.status_effects["Burning"]
            gs.msg("The water extinguishes the flames!", C_CYAN)
    # Attack enemy
    for e in gs.enemies:
        if e.x == nx and e.y == ny and e.is_alive():
            player_attack(gs, e)
            gs.last_noise = max(gs.last_noise, _compute_noise(gs, "combat"))
            return True
    p.x = nx
    p.y = ny
    # Generate noise for movement (stealth system)
    gs.last_noise = max(gs.last_noise, _compute_noise(gs, "walk"))
    # Trap check
    _check_traps_on_move(gs, nx, ny)
    if gs.game_over:
        return True
    _passive_trap_detect(gs)
    # Hunger
    p.hunger = max(0, p.hunger - B["hunger_per_move"])
    if p.hunger <= 0:
        p.hp -= B["starvation_damage"]
        if gs.turn_count % 5 == 0:
            gs.msg("You are starving!", C_RED)
        if p.hp <= 0:
            gs.game_over = True
            gs.death_cause = "starvation"
            sound_alert(gs, "death")
    if p.ring and p.ring.data.get("effect") == "hunger":
        p.hunger = max(0, p.hunger - B["hunger_curse_extra"])
    if p.ring and p.ring.data.get("effect") == "regen":
        if gs.turn_count % 3 == 0 and p.hp < p.max_hp:
            p.hp = min(p.max_hp, p.hp + 1)
    # Auto-pickup
    pickup = [i for i in gs.items if i.x == nx and i.y == ny]
    for item in pickup:
        if item.item_type == "gold":
            p.gold += item.data["amount"]
            gs.msg(f"Picked up {item.data['amount']} gold.", C_GOLD)
            gs.items.remove(item)
        else:
            # Scrolls exempt from capacity (#16)
            capacity_ok = (item.item_type == "scroll" or
                           sum(1 for it in p.inventory if it.item_type != "scroll") < p.carry_capacity)
            if capacity_ok:
                gs.items.remove(item)
                p.inventory.append(item)
                p.items_found += 1
                gs.msg(f"Picked up {item.display_name}.", item.color)
                # Auto-equip better armor (#14)
                if item.item_type == "armor":
                    cur_def = p.armor.data["defense"] if p.armor else -1
                    if item.data["defense"] > cur_def:
                        if p.armor:
                            p.armor.equipped = False
                        item.equipped = True
                        p.armor = item
                        gs.msg(f"Auto-equipped {item.display_name}!", C_BLUE)
                # Auto-equip weapon if bare-fisted (#14)
                elif item.item_type == "weapon" and not p.weapon:
                    item.equipped = True
                    p.weapon = item
                    gs.msg(f"Auto-equipped {item.display_name}!", C_YELLOW)
            else:
                gs.msg("Inventory full!", C_RED)
    # Tile messages
    if tile == T_STAIRS_DOWN:
        gs.msg("Press > to descend.", C_YELLOW)
    elif tile == T_STAIRS_UP:
        gs.msg("Press < to ascend.", C_YELLOW)
    elif tile == T_SHRINE:
        gs.msg("A shrine glows. Press 'p' to pray.", C_SHRINE)
    elif tile == T_SHOP_FLOOR:
        if gs.get_shop_at(nx, ny):
            gs.msg("A shop! Press '$' to browse.", C_GOLD)
    elif tile == T_ALCHEMY_TABLE:
        gs.msg("An alchemy table! Press 'a' to identify.", C_CYAN)
    elif tile == T_PEDESTAL_UNLIT:
        gs.msg("An unlit pedestal. Step on it to light (costs torch fuel).", C_YELLOW)
    elif tile == T_SWITCH_OFF:
        _toggle_switch(gs, nx, ny)
    elif tile == T_SWITCH_ON:
        _toggle_switch(gs, nx, ny)
    elif tile == T_STAIRS_LOCKED:
        gs.msg("The stairs are sealed! Solve the puzzle to unlock.", C_RED)
    return True


# ============================================================
# RENDERING
# ============================================================

def safe_addstr(scr, y, x, s, attr=0):
    h, w = scr.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    s = s[:w - x]
    try:
        scr.addstr(y, x, s, attr)
    except curses.error:
        pass


def render_map(scr, gs):
    p = gs.player
    cam_x = max(0, min(p.x - VIEW_W//2, MAP_W - VIEW_W))
    cam_y = max(0, min(p.y - VIEW_H//2, MAP_H - VIEW_H))
    blind = "Blindness" in p.status_effects

    for sy in range(VIEW_H):
        for sx in range(VIEW_W):
            mx = cam_x + sx
            my = cam_y + sy
            if mx < 0 or mx >= MAP_W or my < 0 or my >= MAP_H:
                safe_addstr(scr, sy, sx, ' ')
                continue

            in_fov = (mx, my) in gs.visible and not blind

            if in_fov:
                gs.explored[my][mx] = True

            if mx == p.x and my == p.y:
                safe_addstr(scr, sy, sx, '@', curses.color_pair(C_PLAYER) | curses.A_BOLD)
                continue

            # Enemy
            if in_fov:
                enemy_here = None
                for e in gs.enemies:
                    if e.x == mx and e.y == my and e.is_alive():
                        enemy_here = e
                        break
                if enemy_here:
                    if enemy_here.disguised:
                        # Disguised mimic looks like gold
                        safe_addstr(scr, sy, sx, '$',
                                   curses.color_pair(C_GOLD) | curses.A_BOLD)
                    elif enemy_here.alertness == "asleep":
                        # Asleep enemies render with 'z' and dim
                        safe_addstr(scr, sy, sx, 'z',
                                   curses.color_pair(C_DARK) | curses.A_DIM)
                    else:
                        attr = curses.color_pair(enemy_here.color)
                        if enemy_here.boss:
                            attr |= curses.A_BOLD
                        elif enemy_here.alertness == "alert":
                            attr |= curses.A_BOLD
                        # unwary enemies render at normal brightness (no A_BOLD)
                        safe_addstr(scr, sy, sx, enemy_here.char, attr)
                    continue

            # Items
            if in_fov:
                item_here = None
                for it in gs.items:
                    if it.x == mx and it.y == my:
                        item_here = it
                        break
                if item_here:
                    safe_addstr(scr, sy, sx, item_here.char,
                               curses.color_pair(item_here.color) | curses.A_BOLD)
                    continue

            # Tiles
            if in_fov:
                _draw_tile(scr, sy, sx, gs.tiles[my][mx], True, p.floor)
            elif gs.explored[my][mx]:
                _draw_tile(scr, sy, sx, gs.tiles[my][mx], False, p.floor)
            else:
                safe_addstr(scr, sy, sx, ' ')


def _draw_tile(scr, sy, sx, tile, lit, floor_num):
    ch = TILE_CHARS.get(tile, ' ')
    if lit:
        if tile == T_WALL:
            if floor_num <= 3:
                a = curses.color_pair(C_WHITE) | curses.A_DIM
            elif floor_num <= 6:
                a = curses.color_pair(C_GREEN) | curses.A_DIM
            elif floor_num <= 9:
                a = curses.color_pair(C_DARK) | curses.A_DIM
            elif floor_num <= 12:
                a = curses.color_pair(C_RED) | curses.A_DIM
            else:
                a = curses.color_pair(C_MAGENTA) | curses.A_DIM
        elif tile in (T_FLOOR, T_CORRIDOR, T_SHOP_FLOOR):
            a = curses.color_pair(C_WHITE) | curses.A_DIM
        elif tile == T_DOOR:
            a = curses.color_pair(C_YELLOW) | curses.A_BOLD
        elif tile in (T_STAIRS_DOWN, T_STAIRS_UP):
            a = curses.color_pair(C_YELLOW) | curses.A_BOLD
        elif tile == T_WATER:
            a = curses.color_pair(C_WATER) | curses.A_BOLD
        elif tile == T_LAVA:
            a = curses.color_pair(C_LAVA) | curses.A_BOLD
        elif tile == T_SHRINE:
            a = curses.color_pair(C_SHRINE) | curses.A_BOLD
        elif tile == T_ALCHEMY_TABLE:
            a = curses.color_pair(C_CYAN) | curses.A_BOLD
        elif tile == T_WALL_TORCH:
            a = curses.color_pair(C_YELLOW) | curses.A_BOLD
        elif tile in (T_PEDESTAL_UNLIT, T_SWITCH_OFF):
            a = curses.color_pair(C_DARK) | curses.A_BOLD
        elif tile in (T_PEDESTAL_LIT, T_SWITCH_ON):
            a = curses.color_pair(C_YELLOW) | curses.A_BOLD
        elif tile == T_STAIRS_LOCKED:
            a = curses.color_pair(C_RED) | curses.A_BOLD
        elif tile == T_TRAP_HIDDEN:
            a = curses.color_pair(C_WHITE) | curses.A_DIM  # Looks like floor
        elif tile == T_TRAP_VISIBLE:
            a = curses.color_pair(C_RED) | curses.A_BOLD
        else:
            a = curses.color_pair(C_WHITE)
    else:
        a = curses.color_pair(C_DARK) | curses.A_DIM
        if tile in (T_STAIRS_DOWN, T_STAIRS_UP):
            a = curses.color_pair(C_YELLOW) | curses.A_DIM
    safe_addstr(scr, sy, sx, ch, a)


def render_sidebar(scr, gs):
    p = gs.player
    x = STAT_X
    sw = SCREEN_W - x - 1  # available sidebar width
    theme = THEMES[p.floor-1] if p.floor <= len(THEMES) else "Abyss"

    if gs.active_branch and gs.active_branch in BRANCH_DEFS:
        branch_name = BRANCH_DEFS[gs.active_branch]["name"]
        safe_addstr(scr, 0, x, f" {branch_name}", curses.color_pair(C_TITLE) | curses.A_BOLD)
    else:
        safe_addstr(scr, 0, x, f" {theme}", curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 1, x, f" Floor {p.floor}/{MAX_FLOORS}", curses.color_pair(C_UI))
    class_label = CHARACTER_CLASSES[p.player_class]["name"] if p.player_class and p.player_class in CHARACTER_CLASSES else ""
    if class_label:
        safe_addstr(scr, 2, x, f" Lv:{p.level} {class_label}", curses.color_pair(C_UI))
    else:
        safe_addstr(scr, 2, x, f" Lv:{p.level} XP:{p.xp}/{p.xp_next}", curses.color_pair(C_UI))

    # HP bar with color coding (Phase 2 item 9)
    hp_pct = max(0, p.hp / p.max_hp) if p.max_hp > 0 else 0
    hpc = C_GREEN if hp_pct > 0.6 else (C_YELLOW if hp_pct > 0.3 else C_RED)
    hp_attr = curses.color_pair(hpc)
    if hp_pct <= 0.2:
        hp_attr |= curses.A_BOLD  # Bold red when critically low
    bw = 12
    filled = int(hp_pct * bw)
    bar = '#' * filled + '-' * (bw - filled)
    safe_addstr(scr, 4, x, " HP:", curses.color_pair(C_WHITE))
    safe_addstr(scr, 4, x+4, bar, hp_attr)
    safe_addstr(scr, 5, x, f"    {p.hp}/{p.max_hp}", hp_attr)

    # Mana bar
    mana_pct = max(0, p.mana / p.max_mana) if p.max_mana > 0 else 0
    mc = C_CYAN if mana_pct > 0.3 else C_RED
    mfilled = int(mana_pct * bw)
    mbar = '#' * mfilled + '-' * (bw - mfilled)
    safe_addstr(scr, 6, x, " MP:", curses.color_pair(C_WHITE))
    safe_addstr(scr, 6, x+4, mbar, curses.color_pair(mc))
    safe_addstr(scr, 7, x, f"    {p.mana}/{p.max_mana}", curses.color_pair(mc))

    # Hunger
    hpct = p.hunger / 100.0
    hc = C_GREEN if hpct > 0.5 else (C_YELLOW if hpct > 0.2 else C_RED)
    hl = "Full" if hpct > 0.7 else ("Hungry" if hpct > 0.3 else "Starving!")
    safe_addstr(scr, 8, x, f" {hl}", curses.color_pair(hc))

    # Torch with current/max format (Phase 2 item 12) + lit/unlit status
    tpct = p.torch_fuel / TORCH_MAX_FUEL
    tc = C_YELLOW if tpct > 0.25 else (C_RED if tpct > 0 else C_DARK)
    torch_status = "" if p.torch_lit else "[OFF]"
    if not p.torch_lit:
        tc = C_DARK
    safe_addstr(scr, 9, x, f" Torch:{p.torch_fuel}/{TORCH_MAX_FUEL}{torch_status}", curses.color_pair(tc))

    # Ammo counter: show arrows and throwing daggers if carried
    row = 10
    ammo_parts = []
    for inv in p.inventory:
        if inv.item_type == "arrow" and inv.count > 0:
            ammo_parts.append(f"Arr:{inv.count}")
        elif inv.item_type == "throwing_dagger" and inv.count > 0:
            ammo_parts.append(f"Dgr:{inv.count}")
    if ammo_parts:
        safe_addstr(scr, row, x, f" {' '.join(ammo_parts)}", curses.color_pair(C_WHITE))
        row += 1

    safe_addstr(scr, row, x, f" STR:{p.strength} DEF:{p.total_defense()}", curses.color_pair(C_WHITE))
    row += 1

    # Equipment names with stats on HUD (#5, #22)
    row += 1  # blank line
    name_w = min(SIDEBAR_NAME_WIDTH, sw - 5)  # 5 chars for " Wpn:" prefix
    if p.weapon:
        lo, hi = p.weapon.data["dmg"]
        b = p.weapon.data.get("bonus", 0)
        wpn = f"{p.weapon.display_name[:name_w-6]} {lo}-{hi}"
        if b:
            wpn += f"+{b}"
    else:
        wpn = "Fists"
    safe_addstr(scr, row, x, f" Wpn:{wpn}", curses.color_pair(C_WHITE))
    row += 1
    if p.armor:
        arm = f"{p.armor.display_name[:name_w-4]} [{p.armor.data['defense']}]"
    else:
        arm = "None"
    safe_addstr(scr, row, x, f" Arm:{arm}", curses.color_pair(C_BLUE))
    row += 1
    rng = p.ring.display_name[:name_w] if p.ring else ""
    if rng:
        safe_addstr(scr, row, x, f" R:{rng}", curses.color_pair(C_CYAN))
        row += 1
    # Elemental resistances on HUD
    resists = p.player_resists()
    if resists:
        res_str = " ".join(sorted(resists))
        safe_addstr(scr, row, x, f" Res:{res_str}", curses.color_pair(C_CYAN))
        row += 1
    # Technique/skill hint on HUD (#2/#4)
    if p.player_class == "mage":
        safe_addstr(scr, row, x, " [z]Spells [C]Blast", curses.color_pair(C_CYAN))
        row += 1
    elif p.player_class and p.known_abilities:
        abilities_list = list(p.known_abilities)
        if len(abilities_list) == 1:
            ab_name = abilities_list[0][:12]
            cd_str = f" CD:{p.ability_cooldown}" if p.ability_cooldown > 0 else ""
            safe_addstr(scr, row, x, f" [t]{ab_name}{cd_str}", curses.color_pair(C_GREEN))
        else:
            safe_addstr(scr, row, x, f" [t]{len(abilities_list)} Techniques", curses.color_pair(C_GREEN))
        row += 1

    row += 1  # blank line
    safe_addstr(scr, row, x, f" Gold:{p.gold}", curses.color_pair(C_GOLD))
    row += 1
    safe_addstr(scr, row, x, f" Kills:{p.kills}", curses.color_pair(C_RED))
    row += 1
    # Turn counter in HUD (Phase 2 item 11)
    safe_addstr(scr, row, x, f" Turn:{gs.turn_count}", curses.color_pair(C_DARK))
    row += 1

    # Status effects with overflow cap (Phase 2 item 6)
    STATUS_COLORS = {"Poison": C_GREEN, "Paralysis": C_YELLOW, "Fear": C_MAGENTA,
                     "Berserk": C_RED, "Blindness": C_DARK, "Speed": C_CYAN,
                     "Strength": C_RED, "Resistance": C_BLUE, "Confusion": C_MAGENTA}
    y = row
    max_effect_lines = SCREEN_H - 1 - y  # lines available
    effects_list = list(p.status_effects.items())
    for i, (eff, turns) in enumerate(effects_list):
        if i >= max_effect_lines - 1 and len(effects_list) > max_effect_lines:
            remaining = len(effects_list) - i
            safe_addstr(scr, y, x, f" +{remaining} more", curses.color_pair(C_MAGENTA))
            break
        if y < SCREEN_H - 1:
            eff_color = STATUS_COLORS.get(eff, C_MAGENTA)
            safe_addstr(scr, y, x, f" {eff}({turns})", curses.color_pair(eff_color))
            y += 1


def render_messages(scr, gs):
    msgs = list(gs.messages)
    start_y = VIEW_H
    # Build display lines with word-wrap (Phase 2 item 8)
    display_lines = []
    for text, color in msgs:
        if len(text) <= VIEW_W:
            display_lines.append((text, color))
        else:
            # Word-wrap long messages
            words = text.split(' ')
            line = ''
            for word in words:
                if len(line) + len(word) + 1 <= VIEW_W:
                    line = line + ' ' + word if line else word
                else:
                    if line:
                        display_lines.append((line, color))
                    line = word[:VIEW_W]  # truncate single long words
            if line:
                display_lines.append((line, color))
    # Show last MSG_H lines
    for i in range(min(MSG_H, len(display_lines))):
        idx = len(display_lines) - MSG_H + i
        if idx < 0:
            continue
        text, color = display_lines[idx]
        safe_addstr(scr, start_y + i, 0, text[:VIEW_W], curses.color_pair(color))


def render_game(scr, gs):
    scr.erase()
    fov_radius = gs.player.get_torch_radius()
    if "Blindness" in gs.player.status_effects:
        fov_radius = 1
    compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
    # Wall torch lighting (#1): tiles near wall torches are also visible if in LOS
    if gs.wall_torches:
        wall_torch_radius = 5
        for wtx, wty in gs.wall_torches:
            if abs(wtx - gs.player.x) + abs(wty - gs.player.y) <= fov_radius + wall_torch_radius:
                # Add tiles lit by this torch that are in LOS from player
                for dy2 in range(-wall_torch_radius, wall_torch_radius + 1):
                    for dx2 in range(-wall_torch_radius, wall_torch_radius + 1):
                        lx, ly = wtx + dx2, wty + dy2
                        if 0 <= lx < MAP_W and 0 <= ly < MAP_H:
                            if dx2*dx2 + dy2*dy2 <= wall_torch_radius * wall_torch_radius:
                                if _has_los(gs.tiles, gs.player.x, gs.player.y, lx, ly):
                                    gs.visible.add((lx, ly))
    # Lava light: lava tiles emit light radius 3
    lava_radius = 3
    for ly2 in range(max(0, gs.player.y - fov_radius - lava_radius),
                      min(MAP_H, gs.player.y + fov_radius + lava_radius + 1)):
        for lx2 in range(max(0, gs.player.x - fov_radius - lava_radius),
                          min(MAP_W, gs.player.x + fov_radius + lava_radius + 1)):
            if gs.tiles[ly2][lx2] == T_LAVA:
                for dy3 in range(-lava_radius, lava_radius + 1):
                    for dx3 in range(-lava_radius, lava_radius + 1):
                        nlx, nly = lx2 + dx3, ly2 + dy3
                        if (0 <= nlx < MAP_W and 0 <= nly < MAP_H
                                and dx3*dx3 + dy3*dy3 <= lava_radius * lava_radius):
                            if _has_los(gs.tiles, gs.player.x, gs.player.y, nlx, nly):
                                gs.visible.add((nlx, nly))
    # Shop discovery: fire message when player first sees a shop tile (#10)
    if not gs.shop_discovered and gs.shops:
        for vx, vy in gs.visible:
            if gs.tiles[vy][vx] == T_SHOP_FLOOR:
                gs.shop_discovered = True
                gs.msg("You see a merchant's stall nearby.", C_GOLD)
                break
    render_map(scr, gs)
    render_sidebar(scr, gs)
    render_messages(scr, gs)
    safe_addstr(scr, SCREEN_H-1, 0,
               " ?:Help i:Inv f:Fire z:Spell j:Journal T:Torch >:Down",
               curses.color_pair(C_DARK) | curses.A_DIM)
    scr.refresh()


# ============================================================
# UI SCREENS
# ============================================================

def show_title(scr):
    scr.erase()
    h, w = scr.getmaxyx()
    art = [
        " ____  _____ ____ _____ _   _ ____",
        "|  _ \\| ____|  _ \\_   _| | | / ___|",
        "| | | |  _| | |_) || | | |_| \\___ \\",
        "| |_| | |___|  __/ | | |  _  |___) |",
        "|____/|_____|_|    |_| |_| |_|____/",
        "",
        "  ___  _____   ____  ____  _____    _    ____",
        " / _ \\|  ___| |  _ \\|  _ \\| ____|  / \\  |  _ \\",
        "| | | | |_    | | | | |_) |  _|   / _ \\ | | | |",
        "| |_| |  _|   | |_| |  _ <| |___ / ___ \\| |_| |",
        " \\___/|_|     |____/|_| \\_\\_____/_/   \\_\\____/",
    ]
    sy = max(0, h//2 - 12)
    for i, line in enumerate(art):
        x = max(0, (w - len(line))//2)
        safe_addstr(scr, sy+i, x, line, curses.color_pair(C_RED) | curses.A_BOLD)

    sub = "A Terminal Roguelike"
    safe_addstr(scr, sy+12, max(0,(w-len(sub))//2), sub, curses.color_pair(C_YELLOW))

    flavor = [
        "Thornhaven is doomed. Beneath the old keep,",
        "fifteen floors of darkness hide the Dread Lord.",
        "You are the last one foolish enough to descend.",
    ]
    for i, line in enumerate(flavor):
        safe_addstr(scr, sy+14+i, max(0,(w-len(line))//2), line, curses.color_pair(C_WHITE))

    prompt = "[ Press any key to begin ]"
    safe_addstr(scr, sy+19, max(0,(w-len(prompt))//2), prompt,
               curses.color_pair(C_YELLOW) | curses.A_BOLD)
    ctrl = "Move: WASD / Arrows / hjklyubn"
    safe_addstr(scr, sy+21, max(0,(w-len(ctrl))//2), ctrl, curses.color_pair(C_DARK))

    scr.refresh()
    scr.getch()


def show_help(scr):
    """Show comprehensive help screen with categories (Phase 5, item 24)."""
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    pages = [
        [
            ("DEPTHS OF DREAD - Help (1/2)", C_TITLE),
            ("", C_WHITE),
            ("=== Movement ===", C_YELLOW),
            ("Arrow keys / WASD / hjkl  Move (cardinal)", C_WHITE),
            ("yubn                      Move (diagonal)", C_WHITE),
            ("", C_WHITE),
            ("=== Combat ===", C_YELLOW),
            ("[Walk into enemy]  Melee attack", C_WHITE),
            ("f  Fire projectile (arrows, daggers, wands)", C_WHITE),
            ("z  Cast spell      (opens spell menu)", C_WHITE),
            ("t  Techniques      (class combat abilities)", C_WHITE),
            ("Tab  Auto-fight    (attack nearest enemy)", C_WHITE),
            ("", C_WHITE),
            ("=== Items ===", C_YELLOW),
            (",  Pick up item    i  Open inventory", C_WHITE),
            ("x+letter  Drop     $  Browse shop", C_WHITE),
            ("", C_WHITE),
            ("=== Exploration ===", C_YELLOW),
            ("o  Auto-explore    x  Examine/look", C_WHITE),
            (">  Descend stairs  <  Ascend stairs", C_WHITE),
            (".  Wait/rest       R  Rest until healed", C_WHITE),
            ("T  Toggle torch    p  Pray at shrine", C_WHITE),
            ("/  Search for traps  D  Disarm trap", C_WHITE),
        ],
        [
            ("DEPTHS OF DREAD - Help (2/2)", C_TITLE),
            ("", C_WHITE),
            ("=== Info ===", C_YELLOW),
            ("c  Character sheet  m  Message log", C_WHITE),
            ("M  Bestiary (Monster Memory)", C_WHITE),
            ("S  Lifetime stats   Q  Quit (Shift+Q)", C_WHITE),
            ("?  This help screen", C_WHITE),
            ("", C_WHITE),
            ("=== Symbols ===", C_YELLOW),
            (") Weapon  [ Armor  ! Potion  ? Scroll", C_WHITE),
            ("% Food    = Ring   } Bow     / Wand", C_WHITE),
            ("> Down    < Up     + Door    ~ Water", C_WHITE),
            ("_ Shrine  $ Gold   @ You     & Alchemy", C_WHITE),
            ("! Wall Torch  * Pedestal  X Locked Stairs", C_WHITE),
            ("^ Trap (visible)                       ", C_WHITE),
            ("", C_WHITE),
            ("=== Game Mechanics ===", C_YELLOW),
            ("Hunger: Depletes each turn. Eat food (%) to restore.", C_WHITE),
            ("Torches: Light fades. Wall torches (!) light rooms.", C_WHITE),
            ("  Grab wall torches with ,  Puzzles: * and switches.", C_WHITE),
            ("Shrines: Prayer grants boons, but beware curses.", C_WHITE),
            ("Shops on odd floors (1,3,5,7,...). Press $ to browse.", C_WHITE),
            ("j=Journal  &=Alchemy table (identifies items)", C_WHITE),
            ("Inventory: [/] scroll, S sort. Better armor auto-equips.", C_WHITE),
            ("Traps: Hidden traps hurt. / to search. D to disarm.", C_WHITE),
            ("Resist: Rings grant fire/cold/poison resistance.", C_WHITE),
            ("Water: Blocks fire aura. Lightning arcs in water.", C_WHITE),
            ("Stealth: Enemies spawn asleep(z) or unwary.", C_WHITE),
            ("  Noise wakes them. Rogue=50% less noise.", C_WHITE),
            ("  Attack sleeping/unwary = guaranteed crit!", C_WHITE),
            ("Q=Save & Quit (auto-loads). S=Lifetime stats.", C_WHITE),
        ],
    ]
    for page in pages:
        scr.erase()
        for i, (t, c) in enumerate(page):
            if i >= SCREEN_H - 1:
                break
            safe_addstr(scr, i, 1, t, curses.color_pair(c))
        safe_addstr(scr, SCREEN_H-1, 1, "[ Press any key for next / ESC to close ]",
                   curses.color_pair(C_YELLOW))
        scr.refresh()
        key = scr.getch()
        if key == 27:
            return


def _inv_letter(idx):
    """Map inventory index to display letter: a-z then A-Z."""
    if idx < 26:
        return chr(ord('a') + idx)
    elif idx < 52:
        return chr(ord('A') + idx - 26)
    return '?'

def _inv_key_to_idx(key, scroll_offset=0):
    """Convert keypress to inventory index (accounting for scroll)."""
    if ord('a') <= key <= ord('z'):
        return key - ord('a') + scroll_offset
    elif ord('A') <= key <= ord('Z'):
        return key - ord('A') + 26 + scroll_offset
    return -1

def show_bestiary(scr, gs):
    """Show the Monster Memory / Bestiary screen (M key)."""
    # Flush buffered keypresses
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)

    # Collect encountered monster types sorted by encounters (desc)
    entries = []
    for etype, data in gs.bestiary.items():
        if etype in ENEMY_TYPES and data["encountered"] > 0:
            entries.append((etype, data))
    entries.sort(key=lambda x: x[1]["encountered"], reverse=True)

    if not entries:
        scr.erase()
        safe_addstr(scr, 2, 4, "BESTIARY - Monster Memory", curses.color_pair(C_TITLE) | curses.A_BOLD)
        safe_addstr(scr, 4, 4, "No monsters encountered yet.", curses.color_pair(C_DARK))
        safe_addstr(scr, 6, 4, "Press any key to return.", curses.color_pair(C_WHITE))
        scr.refresh()
        scr.getch()
        return

    # Pagination
    page_size = max(1, SCREEN_H - 6)
    page = 0
    total_pages = max(1, (len(entries) + page_size - 1) // page_size)

    while True:
        scr.erase()
        safe_addstr(scr, 0, 4, f"BESTIARY - Monster Memory (Page {page+1}/{total_pages})",
                    curses.color_pair(C_TITLE) | curses.A_BOLD)
        safe_addstr(scr, 1, 4, "Knowledge grows with each encounter.", curses.color_pair(C_DARK))

        y = 3
        start = page * page_size
        end = min(start + page_size, len(entries))
        for i in range(start, end):
            etype, data = entries[i]
            edef = ENEMY_TYPES[etype]
            enc = data["encountered"]
            killed = data["killed"]

            # Progressive reveal based on encounter count
            name = edef["name"]
            char = edef.get("char", '?')
            # Tier 1: 1+ encounters — name and basic description
            line = f" {char} {name}"
            if enc >= 1:
                line += f"  (Seen: {enc}, Killed: {killed})"
            safe_addstr(scr, y, 2, line, curses.color_pair(C_WHITE))
            y += 1

            # Tier 2: 3+ encounters — show HP and damage range
            if enc >= 3:
                hp_str = f"HP: ~{edef['hp']}"
                dmg_lo, dmg_hi = edef.get("dmg", (0, 0))
                dmg_str = f"DMG: {dmg_lo}-{dmg_hi}"
                def_str = f"DEF: {edef.get('defense', 0)}"
                safe_addstr(scr, y, 6, f"{hp_str}  {dmg_str}  {def_str}", curses.color_pair(C_UI))
                y += 1

            # Tier 3: 5+ encounters — show observed abilities
            if enc >= 5 and data["abilities"]:
                ab_str = ", ".join(data["abilities"])
                safe_addstr(scr, y, 6, f"Abilities: {ab_str}", curses.color_pair(C_YELLOW))
                y += 1

            # Tier 4: 10+ encounters — show damage stats and resistances
            if enc >= 10:
                avg_dealt = data["dmg_dealt"] // max(1, enc)
                avg_taken = data["dmg_taken"] // max(1, enc)
                safe_addstr(scr, y, 6, f"Avg dmg dealt: {avg_dealt}  Avg dmg taken: {avg_taken}",
                            curses.color_pair(C_CYAN))
                y += 1
                # Resistances/vulnerabilities from definition
                resists = edef.get("resists", [])
                vulns = edef.get("vulnerable", [])
                if resists or vulns:
                    rv_parts = []
                    if resists:
                        rv_parts.append(f"Resists: {', '.join(resists)}")
                    if vulns:
                        rv_parts.append(f"Weak to: {', '.join(vulns)}")
                    safe_addstr(scr, y, 6, "  ".join(rv_parts), curses.color_pair(C_GREEN))
                    y += 1

            if y >= SCREEN_H - 2:
                break

        nav = "[ESC/q] Close"
        if total_pages > 1:
            nav += "  [n] Next  [p] Prev"
        safe_addstr(scr, SCREEN_H - 1, 4, nav, curses.color_pair(C_DARK))
        scr.refresh()

        key = scr.getch()
        if key in (27, ord('q'), ord('Q'), ord('m'), ord('M')):
            break
        elif key == ord('n') and page < total_pages - 1:
            page += 1
        elif key == ord('p') and page > 0:
            page -= 1


def show_inventory(scr, gs):
    p = gs.player
    scroll_offset = 0
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    while True:
        scr.erase()
        safe_addstr(scr, 0, 1, "INVENTORY", curses.color_pair(C_TITLE) | curses.A_BOLD)
        # Stats header (#23)
        hp_pct = p.hp / p.max_hp if p.max_hp > 0 else 0
        hpc = C_GREEN if hp_pct > 0.6 else (C_YELLOW if hp_pct > 0.3 else C_RED)
        safe_addstr(scr, 1, 1, f"HP:{p.hp}/{p.max_hp} MP:{p.mana}/{p.max_mana} Hunger:{int(p.hunger)}%",
                   curses.color_pair(hpc))
        scroll_count = sum(1 for it in p.inventory if it.item_type == "scroll")
        non_scroll = sum(1 for it in p.inventory if it.item_type != "scroll")
        if scroll_count > 0:
            cap_str = f"({non_scroll}/{p.carry_capacity} items + {scroll_count} scrolls, {p.gold}g)"
        else:
            cap_str = f"({len(p.inventory)}/{p.carry_capacity}, {p.gold}g)"
        wpn_str = p.weapon.display_name if p.weapon else "Fists"
        arm_str = p.armor.display_name if p.armor else "None"
        safe_addstr(scr, 2, 1, f"Wpn:{wpn_str}  Arm:{arm_str}  {cap_str}",
                   curses.color_pair(C_DARK))
        header_rows = 3
        visible_rows = SCREEN_H - header_rows - 2  # leave room for footer
        if not p.inventory:
            safe_addstr(scr, header_rows + 1, 2, "Your pack is empty.", curses.color_pair(C_DARK))
        else:
            # Clamp scroll offset
            max_offset = max(0, len(p.inventory) - visible_rows)
            scroll_offset = max(0, min(scroll_offset, max_offset))
            # Show scroll indicators
            if scroll_offset > 0:
                safe_addstr(scr, header_rows, SCREEN_W - 12, "^ more above", curses.color_pair(C_DARK))
            if scroll_offset + visible_rows < len(p.inventory):
                safe_addstr(scr, SCREEN_H - 3, SCREEN_W - 12, "v more below", curses.color_pair(C_DARK))
            for vi, i in enumerate(range(scroll_offset, min(len(p.inventory), scroll_offset + visible_rows))):
                item = p.inventory[i]
                letter = _inv_letter(i)
                prefix = "(E) " if item.equipped else ""
                name = f"{letter}) {prefix}{item.display_name}"
                if item.item_type == "weapon":
                    lo, hi = item.data["dmg"]
                    b = item.data.get("bonus", 0)
                    name += f" [{lo}-{hi}+{b}]"
                elif item.item_type == "armor":
                    name += f" [Def:{item.data['defense']}]"
                elif item.item_type == "bow":
                    lo, hi = item.data["dmg"]
                    name += f" [{lo}-{hi} rng:{item.data.get('range',6)}]"
                elif item.item_type == "wand":
                    name += f" [{item.data.get('charges',0)} chg]"
                # Journal hint for identified potions/scrolls (#6)
                if item.item_type == "potion" and item.identified:
                    hint = gs.journal.get(f"Potion of {item.data['effect']}", "")
                    if hint:
                        name += f" ({hint[:20]})"
                elif item.item_type == "scroll" and item.identified:
                    hint = gs.journal.get(f"Scroll of {item.data['effect']}", "")
                    if hint:
                        name += f" ({hint[:20]})"
                safe_addstr(scr, header_rows + vi, 2, name[:SCREEN_W-14], curses.color_pair(item.color))

        footer = "[a-z/A-Z] Use  [x] Drop  [S] Sort  [PgUp/Dn] Scroll  [ESC] Close"
        safe_addstr(scr, SCREEN_H-1, 1, footer[:SCREEN_W-2], curses.color_pair(C_DARK))
        scr.refresh()
        key = scr.getch()
        if key == 27:
            return False
        elif key == curses.KEY_PPAGE or key == ord('['):
            scroll_offset = max(0, scroll_offset - visible_rows)
        elif key == curses.KEY_NPAGE or key == ord(']'):
            scroll_offset = min(max(0, len(p.inventory) - visible_rows), scroll_offset + visible_rows)
        elif key == curses.KEY_UP:
            scroll_offset = max(0, scroll_offset - 1)
        elif key == curses.KEY_DOWN:
            scroll_offset = min(max(0, len(p.inventory) - visible_rows), scroll_offset + 1)
        elif key == ord('x'):
            safe_addstr(scr, SCREEN_H-1, 1, "Drop which? (letter)    ", curses.color_pair(C_YELLOW))
            scr.refresh()
            dk = scr.getch()
            idx = _inv_key_to_idx(dk, 0)
            if 0 <= idx < len(p.inventory):
                item = p.inventory[idx]
                if item.equipped:
                    item.equipped = False
                    if item.item_type == "weapon":
                        p.weapon = None
                    elif item.item_type == "armor":
                        p.armor = None
                    elif item.item_type == "ring":
                        p.ring = None
                    elif item.item_type == "bow":
                        p.bow = None
                item.x = p.x
                item.y = p.y
                gs.items.append(item)
                p.inventory.remove(item)
                gs.msg(f"Dropped {item.display_name}.", C_WHITE)
        elif key == ord('S'):
            # Inventory sort cycling (#12)
            sort_mode = getattr(gs, '_inv_sort_mode', 0)
            sort_mode = (sort_mode + 1) % 3
            gs._inv_sort_mode = sort_mode
            if sort_mode == 1:
                p.inventory.sort(key=lambda it: (it.item_type, it.display_name))
                gs.msg("Sorted by type.", C_WHITE)
            elif sort_mode == 2:
                p.inventory.sort(key=lambda it: it.display_name)
                gs.msg("Sorted by name.", C_WHITE)
            else:
                gs.msg("Default order.", C_WHITE)
            # Re-link equipped references after sort
            for it in p.inventory:
                if it.equipped:
                    if it.item_type == "weapon":
                        p.weapon = it
                    elif it.item_type == "armor":
                        p.armor = it
                    elif it.item_type == "ring":
                        p.ring = it
                    elif it.item_type == "bow":
                        p.bow = it
        else:
            idx = _inv_key_to_idx(key, 0)
            if 0 <= idx < len(p.inventory):
                item = p.inventory[idx]
                if item.item_type == "weapon":
                    if item.equipped:
                        item.equipped = False
                        p.weapon = None
                        gs.msg(f"Unequipped {item.display_name}.", C_WHITE)
                    else:
                        if p.weapon:
                            p.weapon.equipped = False
                        item.equipped = True
                        p.weapon = item
                        gs.msg(f"Equipped {item.display_name}.", C_YELLOW)
                    return True
                elif item.item_type == "armor":
                    if item.equipped:
                        item.equipped = False
                        p.armor = None
                        gs.msg(f"Removed {item.display_name}.", C_WHITE)
                    else:
                        if p.armor:
                            p.armor.equipped = False
                        item.equipped = True
                        p.armor = item
                        gs.msg(f"Donned {item.display_name}.", C_BLUE)
                    return True
                elif item.item_type == "ring":
                    if item.equipped:
                        item.equipped = False
                        p.ring = None
                        gs.msg(f"Removed {item.display_name}.", C_WHITE)
                    else:
                        if p.ring:
                            p.ring.equipped = False
                        item.equipped = True
                        p.ring = item
                        gs.msg(f"Put on {item.display_name}.", C_CYAN)
                    return True
                elif item.item_type == "bow":
                    if item.equipped:
                        item.equipped = False
                        p.bow = None
                        gs.msg(f"Unequipped {item.display_name}.", C_WHITE)
                    else:
                        if p.bow:
                            p.bow.equipped = False
                        item.equipped = True
                        p.bow = item
                        gs.msg(f"Equipped {item.display_name}.", C_YELLOW)
                    return True
                elif item.item_type == "potion":
                    use_potion(gs, item)
                    return True
                elif item.item_type == "scroll":
                    use_scroll(gs, item)
                    return True
                elif item.item_type == "food":
                    use_food(gs, item)
                    return True
                elif item.item_type == "torch":
                    fuel = item.data.get("fuel", 50)
                    p.torch_fuel = min(TORCH_MAX_FUEL, p.torch_fuel + fuel)
                    gs.msg(f"Refueled torch! (+{fuel} fuel)", C_YELLOW)
                    p.inventory.remove(item)
                    return True
                elif item.item_type == "wand":
                    # Use wand from inventory (#13)
                    charges = item.data.get("charges", 0)
                    if charges <= 0:
                        gs.msg("The wand is empty.", C_DARK)
                    else:
                        gs.msg("Fire wand which direction?", C_CYAN)
                        if scr:
                            render_game(scr, gs)
                            dk = scr.getch()
                            DIR_KEYS = {
                                curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
                                curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
                                ord('w'): (0,-1), ord('s'): (0,1),
                                ord('a'): (-1,0), ord('d'): (1,0),
                                ord('h'): (-1,0), ord('j'): (0,1),
                                ord('k'): (0,-1), ord('l'): (1,0),
                                ord('y'): (-1,-1), ord('u'): (1,-1),
                                ord('b'): (-1,1), ord('n'): (1,1),
                            }
                            if dk == 27:
                                gs.msg("Cancelled.", C_DARK)
                            elif dk in DIR_KEYS:
                                ddx, ddy = DIR_KEYS[dk]
                                _launch_projectile(gs, ddx, ddy, "wand", item)
                                return True
                            else:
                                gs.msg("Invalid direction.", C_DARK)
    return False


def show_character(scr, gs):
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    p = gs.player
    scr.erase()
    safe_addstr(scr, 0, 1, "CHARACTER SHEET", curses.color_pair(C_TITLE) | curses.A_BOLD)
    lines = [
        (f"Level: {p.level}  XP: {p.xp}/{p.xp_next}", C_WHITE),
        (f"Floor: {p.floor}  Deepest: {p.deepest_floor}", C_WHITE),
        ("", C_WHITE),
        (f"HP: {p.hp}/{p.max_hp}  MP: {p.mana}/{p.max_mana}", C_GREEN),
        (f"STR: {p.strength}  DEF: {p.total_defense()}  Evasion: {p.evasion_chance()}%", C_WHITE),
        (f"Hunger: {int(p.hunger)}%  Torch: {p.torch_fuel}/{TORCH_MAX_FUEL} {'[LIT]' if p.torch_lit else '[OFF]'}", C_YELLOW),
        ("", C_WHITE),
        (f"Weapon: {p.weapon.display_name if p.weapon else 'Fists'}", C_WHITE),
        (f"Armor:  {p.armor.display_name if p.armor else 'None'}", C_BLUE),
        (f"Ring:   {p.ring.display_name if p.ring else 'None'}", C_CYAN),
        ("", C_WHITE),
        (f"Gold: {p.gold}  Kills: {p.kills}  Turns: {gs.turn_count}", C_GOLD),
        ("", C_WHITE),
        ("Identified Potions:", C_MAGENTA),
    ]
    for eff in gs.id_potions:
        lines.append((f"  {gs.potion_ids[eff]} = {eff}", C_MAGENTA))
    lines.append(("Identified Scrolls:", C_YELLOW))
    for eff in gs.id_scrolls:
        lines.append((f"  {gs.scroll_ids[eff]} = {eff}", C_YELLOW))
    for i, (t, c) in enumerate(lines):
        if i+2 >= SCREEN_H-1:
            break
        safe_addstr(scr, i+2, 2, t, curses.color_pair(c))
    safe_addstr(scr, SCREEN_H-1, 1, "[ Press any key ]", curses.color_pair(C_YELLOW))
    scr.refresh()
    scr.getch()


def show_shop(scr, gs):
    # Flush buffered keypresses (#17)
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    p = gs.player
    shop = gs.get_shop_at(p.x, p.y)
    if not shop:
        gs.msg("No shop here.", C_WHITE)
        return
    _, shop_items = shop
    sell_mode = False
    while True:
        scr.erase()
        safe_addstr(scr, 0, 1, "THE MERCHANT'S STALL", curses.color_pair(C_GOLD) | curses.A_BOLD)
        safe_addstr(scr, 1, 1, f"Your gold: {p.gold}", curses.color_pair(C_GOLD))

        if not sell_mode:
            # --- BUY MODE ---
            safe_addstr(scr, 2, 1, '"Fair prices, friend."', curses.color_pair(C_WHITE))
            for i, si in enumerate(shop_items):
                if i+4 >= SCREEN_H-2:
                    break
                letter = chr(ord('a')+i)
                if si.sold:
                    safe_addstr(scr, i+4, 2, f"{letter}) [SOLD]", curses.color_pair(C_DARK))
                else:
                    pc = C_GREEN if p.gold >= si.price else C_RED
                    safe_addstr(scr, i+4, 2, f"{letter}) {si.item.display_name}",
                               curses.color_pair(si.item.color))
                    safe_addstr(scr, i+4, 34, f"{si.price}g", curses.color_pair(pc))
            safe_addstr(scr, SCREEN_H-1, 1, "[a-z] Buy  [s] Sell  [ESC] Leave", curses.color_pair(C_DARK))
        else:
            # --- SELL MODE ---
            safe_addstr(scr, 2, 1, '"What have you got for me?"', curses.color_pair(C_WHITE))
            sellable = [(i, item) for i, item in enumerate(p.inventory) if not item.equipped]
            if not sellable:
                safe_addstr(scr, 4, 2, "(nothing to sell — unequip items first)", curses.color_pair(C_DARK))
            for si_idx, (inv_idx, item) in enumerate(sellable):
                if si_idx+4 >= SCREEN_H-2:
                    break
                letter = chr(ord('a') + si_idx)
                val = item.sell_value
                safe_addstr(scr, si_idx+4, 2, f"{letter}) {item.display_name}",
                           curses.color_pair(item.color))
                safe_addstr(scr, si_idx+4, 34, f"+{val}g", curses.color_pair(C_GOLD))
            safe_addstr(scr, SCREEN_H-1, 1, "[a-z] Sell  [b] Buy  [ESC] Leave", curses.color_pair(C_DARK))

        scr.refresh()
        key = scr.getch()
        if key == 27:
            return
        if not sell_mode and key == ord('s'):
            sell_mode = True
            continue
        if sell_mode and key == ord('b'):
            sell_mode = False
            continue

        if not sell_mode:
            # BUY
            idx = key - ord('a')
            if 0 <= idx < len(shop_items):
                si = shop_items[idx]
                if si.sold:
                    gs.msg("Already sold.", C_DARK)
                elif p.gold < si.price:
                    gs.msg("Can't afford that.", C_RED)
                elif (si.item.item_type != "scroll" and
                      sum(1 for it in p.inventory if it.item_type != "scroll") >= p.carry_capacity):
                    gs.msg("Inventory full!", C_RED)
                else:
                    p.gold -= si.price
                    ic = Item(0, 0, si.item.item_type, si.item.subtype, si.item.data)
                    ic.identified = True
                    p.inventory.append(ic)
                    si.sold = True
                    gs.msg(f"Bought {ic.display_name} for {si.price}g.", C_GOLD)
        else:
            # SELL
            sellable = [(i, item) for i, item in enumerate(p.inventory) if not item.equipped]
            idx = key - ord('a')
            if 0 <= idx < len(sellable):
                inv_idx, item = sellable[idx]
                val = item.sell_value
                p.gold += val
                p.inventory.pop(inv_idx)
                gs.msg(f"Sold {item.display_name} for {val}g.", C_GOLD)


def show_messages(scr, gs):
    scr.erase()
    safe_addstr(scr, 0, 1, "MESSAGE LOG", curses.color_pair(C_TITLE) | curses.A_BOLD)
    msgs = list(gs.messages)
    start = max(0, len(msgs) - (SCREEN_H-3))
    for i, (t, c) in enumerate(msgs[start:]):
        if i+2 >= SCREEN_H-1:
            break
        safe_addstr(scr, i+2, 1, t[:SCREEN_W-2], curses.color_pair(c))
    safe_addstr(scr, SCREEN_H-1, 1, "[ Press any key ]", curses.color_pair(C_YELLOW))
    scr.refresh()
    scr.getch()


def calculate_score(p, gs):
    """Calculate final score."""
    score = p.gold + p.kills * 50 + p.deepest_floor * 200 + p.damage_dealt
    if gs.victory:
        score += 5000
    return score


def show_death(scr, gs):
    p = gs.player
    elapsed = int(time.time() - gs.start_time)
    m, s = elapsed // 60, elapsed % 60
    scr.erase()
    _, w = scr.getmaxyx()
    tomb = [
        "      _______",
        "     /       \\",
        "    /  R.I.P  \\",
        "   /           \\",
        "  | HERE LIES A  |",
        "  | BRAVE BUT    |",
        "  | FOOLISH      |",
        "  | ADVENTURER   |",
        "  |______________|",
        "  |______________|",
    ]
    sy = 1
    for i, line in enumerate(tomb):
        safe_addstr(scr, sy+i, max(0,(w-len(line))//2), line, curses.color_pair(C_RED))
    quip = random.choice(DEATH_QUIPS)
    safe_addstr(scr, sy+11, max(0,(w-len(quip))//2), f'"{quip}"', curses.color_pair(C_MAGENTA))
    cause = gs.death_cause or "unknown causes"
    safe_addstr(scr, sy+12, max(0,(w-len(cause)-10)//2), f"Cause: {cause}", curses.color_pair(C_RED))
    stats = [
        f"Floor: {p.deepest_floor}/{MAX_FLOORS}  Level: {p.level}  Kills: {p.kills}",
        f"Gold: {p.gold}  Turns: {gs.turn_count}  Time: {m}m{s}s",
        f"Items: {p.items_found}  Spells: {p.spells_cast}  Shots: {p.projectiles_fired}",
        f"Damage dealt: {p.damage_dealt}  Taken: {p.damage_taken}",
    ]
    for i, line in enumerate(stats):
        safe_addstr(scr, sy+14+i, max(0,(w-len(line))//2), line, curses.color_pair(C_YELLOW))
    score = calculate_score(p, gs)
    sc = f"SCORE: {score}"
    safe_addstr(scr, sy+19, max(0,(w-len(sc))//2), sc, curses.color_pair(C_GOLD) | curses.A_BOLD)
    pr = "[ Press any key ]"
    safe_addstr(scr, min(SCREEN_H-1, sy+21), max(0,(w-len(pr))//2), pr, curses.color_pair(C_DARK))
    scr.refresh()
    scr.getch()


def show_victory(scr, gs):
    p = gs.player
    elapsed = int(time.time() - gs.start_time)
    m, s = elapsed // 60, elapsed % 60
    scr.erase()
    _, w = scr.getmaxyx()
    art = [
        "  *  .  *  .  *  .  *  .  *",
        "    ___________________",
        "   /                   \\",
        "  /   VICTORY!!!        \\",
        " /  THE DREAD LORD       \\",
        "|   IS VANQUISHED         |",
        "|  THORNHAVEN IS SAVED!   |",
        "|_________________________|",
        "  *  .  *  .  *  .  *  .  *",
    ]
    sy = 1
    for i, line in enumerate(art):
        safe_addstr(scr, sy+i, max(0,(w-len(line))//2), line,
                   curses.color_pair(C_YELLOW) | curses.A_BOLD)
    stats = [
        f"Level: {p.level}   Kills: {p.kills}   Bosses: {p.bosses_killed}",
        f"Gold: {p.gold}   Turns: {gs.turn_count}   Time: {m}m{s}s",
        f"Items: {p.items_found}  Potions: {p.potions_drunk}  Scrolls: {p.scrolls_read}",
        f"Damage dealt: {p.damage_dealt}  Taken: {p.damage_taken}",
        "",
        "You are a true hero of Thornhaven!",
    ]
    for i, line in enumerate(stats):
        safe_addstr(scr, sy+11+i, max(0,(w-len(line))//2), line, curses.color_pair(C_GREEN))
    score = calculate_score(p, gs)
    sc = f"SCORE: {score}"
    safe_addstr(scr, sy+18, max(0,(w-len(sc))//2), sc, curses.color_pair(C_GOLD) | curses.A_BOLD)
    pr = "[ Press any key ]"
    safe_addstr(scr, min(SCREEN_H-1, sy+20), max(0,(w-len(pr))//2), pr, curses.color_pair(C_DARK))
    scr.refresh()
    scr.getch()


# ============================================================
# CONTEXT TIPS (Phase 5, item 25)
# ============================================================

def check_context_tips(gs):
    """Fire first-encounter tips. Each tip shows exactly once."""
    p = gs.player
    # First enemy adjacent
    if "enemy_adjacent" not in gs.tips_shown:
        for e in gs.enemies:
            if e.is_alive() and abs(e.x - p.x) + abs(e.y - p.y) == 1:
                gs.tips_shown.add("enemy_adjacent")
                gs.msg("Tip: Walk into enemies to attack them!", C_MAGENTA)
                break
    # First shrine seen
    if "shrine" not in gs.tips_shown:
        for (mx, my) in gs.visible:
            if 0 <= mx < MAP_W and 0 <= my < MAP_H and gs.tiles[my][mx] == T_SHRINE:
                gs.tips_shown.add("shrine")
                gs.msg("Tip: Press 'p' to pray. Shrines grant boons... but some are cursed.", C_MAGENTA)
                break
    # First unidentified potion in inventory
    if "unid_potion" not in gs.tips_shown:
        for inv in p.inventory:
            if inv.item_type == "potion" and not inv.identified:
                gs.tips_shown.add("unid_potion")
                gs.msg("Tip: This potion is unidentified. Use it to discover its effect, or find an Identify scroll.", C_MAGENTA)
                break
    # First closed door seen
    if "door" not in gs.tips_shown:
        for (mx, my) in gs.visible:
            if 0 <= mx < MAP_W and 0 <= my < MAP_H and gs.tiles[my][mx] == T_DOOR:
                gs.tips_shown.add("door")
                gs.msg("Tip: Walk into doors to open them.", C_MAGENTA)
                break
    # First shop
    if "shop" not in gs.tips_shown:
        if gs.tiles[p.y][p.x] == T_SHOP_FLOOR and gs.get_shop_at(p.x, p.y):
            gs.tips_shown.add("shop")
            gs.msg("Tip: Press '$' to browse the merchant's wares.", C_MAGENTA)
    # First projectile weapon found
    if "projectile" not in gs.tips_shown:
        for inv in p.inventory:
            if inv.item_type in ("bow", "wand", "throwing_dagger"):
                gs.tips_shown.add("projectile")
                gs.msg("Tip: Press 'f' to fire projectiles. You need ammo!", C_MAGENTA)
                break


# ============================================================
# LOOK/EXAMINE MODE (Phase 4, item 23)
# ============================================================

def look_mode(gs, scr):
    """Enter cursor mode to examine tiles."""
    if scr is None:
        return
    cx, cy = gs.player.x, gs.player.y
    gs.msg("Look mode: move cursor, ESC to exit.", C_CYAN)
    LOOK_KEYS = {
        curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
        curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
        ord('w'): (0,-1), ord('s'): (0,1),
        ord('a'): (-1,0), ord('d'): (1,0),
        ord('h'): (-1,0), ord('j'): (0,1),
        ord('k'): (0,-1), ord('l'): (1,0),
        ord('y'): (-1,-1), ord('u'): (1,-1),
        ord('b'): (-1,1), ord('n'): (1,1),
    }
    while True:
        # Render game with cursor
        render_game(scr, gs)
        # Draw cursor
        cam_x = max(0, min(gs.player.x - VIEW_W//2, MAP_W - VIEW_W))
        cam_y = max(0, min(gs.player.y - VIEW_H//2, MAP_H - VIEW_H))
        scr_cx = cx - cam_x
        scr_cy = cy - cam_y
        if 0 <= scr_cx < VIEW_W and 0 <= scr_cy < VIEW_H:
            try:
                scr.addstr(scr_cy, scr_cx, 'X', curses.color_pair(C_YELLOW) | curses.A_BLINK)
            except curses.error:
                pass
        # Build description
        desc = _describe_tile(gs, cx, cy)
        safe_addstr(scr, SCREEN_H-1, 0, desc[:SCREEN_W-1], curses.color_pair(C_CYAN))
        scr.refresh()
        key = scr.getch()
        if key == 27:
            return
        if key in LOOK_KEYS:
            dx, dy = LOOK_KEYS[key]
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H:
                cx, cy = nx, ny


def _describe_tile(gs, x, y):
    """Return description string for tile at (x, y)."""
    if not (0 <= x < MAP_W and 0 <= y < MAP_H):
        return "Out of bounds"
    if (x, y) not in gs.visible:
        if gs.explored[y][x]:
            return "Explored but not visible"
        return "Unknown"
    # Check for player
    if x == gs.player.x and y == gs.player.y:
        return "You (@)"
    # Check for enemy
    for e in gs.enemies:
        if e.x == x and e.y == y and e.is_alive():
            boss_str = " (BOSS)" if e.boss else " (hostile)"
            return f"{e.name}{boss_str} HP: {e.hp}/{e.max_hp}"
    # Check for items
    for it in gs.items:
        if it.x == x and it.y == y:
            return it.display_name
    # Tile description
    tile = gs.tiles[y][x]
    TILE_NAMES = {
        T_WALL: "Wall", T_FLOOR: "Floor tile", T_CORRIDOR: "Corridor",
        T_DOOR: "Door", T_STAIRS_DOWN: "Stairs down (>)",
        T_STAIRS_UP: "Stairs up (<)", T_WATER: "Water (shallow)",
        T_LAVA: "Lava (deadly!)", T_SHOP_FLOOR: "Shop floor",
        T_SHRINE: "Shrine (press 'p' to pray)",
        T_ALCHEMY_TABLE: "Alchemy table (press 'a')",
        T_WALL_TORCH: "Wall torch (light source)",
        T_PEDESTAL_UNLIT: "Unlit pedestal (press 'a')",
        T_PEDESTAL_LIT: "Lit pedestal",
        T_SWITCH_OFF: "Switch (OFF)",
        T_SWITCH_ON: "Switch (ON)",
        T_STAIRS_LOCKED: "Sealed stairs (solve puzzle)",
    }
    return TILE_NAMES.get(tile, "Unknown tile")


# ============================================================
# AUTO-FIGHT (Phase 4, item 20)
# ============================================================

def auto_fight_step(gs):
    """Execute one step of auto-fight. Returns True if a turn was spent, None to stop."""
    p = gs.player
    # Stop conditions
    if p.hp < p.max_hp * AUTO_FIGHT_HP_THRESHOLD:
        gs.msg("Auto-fight stopped: low HP!", C_YELLOW)
        gs.auto_fighting = False
        return None
    # Find nearest visible enemy
    nearest = None
    nd = 999
    for e in gs.enemies:
        if e.is_alive() and (e.x, e.y) in gs.visible:
            d = abs(e.x - p.x) + abs(e.y - p.y)
            if d < nd:
                nd = d
                nearest = e
    if nearest is None:
        gs.msg("Auto-fight stopped: no enemies visible.", C_YELLOW)
        gs.auto_fighting = False
        return None
    # Check if a new enemy appeared that wasn't the target
    if gs.auto_fight_target and nearest is not gs.auto_fight_target:
        if gs.auto_fight_target.is_alive() and (gs.auto_fight_target.x, gs.auto_fight_target.y) in gs.visible:
            pass  # original target still visible, keep going
        else:
            gs.auto_fight_target = nearest
    else:
        gs.auto_fight_target = nearest
    target = gs.auto_fight_target
    if not target.is_alive():
        gs.msg("Auto-fight: target defeated.", C_GREEN)
        gs.auto_fight_target = None
        gs.auto_fighting = False
        return None
    # If adjacent, attack
    if abs(target.x - p.x) + abs(target.y - p.y) == 1:
        player_attack(gs, target)
        return True
    # Otherwise, pathfind toward
    step = astar(gs.tiles, p.x, p.y, target.x, target.y, max_steps=30)
    if step:
        return player_move(gs, step[0], step[1])
    gs.msg("Auto-fight stopped: can't reach target.", C_YELLOW)
    gs.auto_fighting = False
    return None


# ============================================================
# AUTO-EXPLORE (Phase 4, item 21)
# ============================================================

def auto_explore_step(gs):
    """Execute one step of auto-explore using BFS. Returns True if turn spent, None to stop."""
    p = gs.player
    # Stop conditions
    if p.hp < p.max_hp * AUTO_EXPLORE_HP_THRESHOLD:
        gs.msg("Exploring stopped: low HP!", C_YELLOW)
        gs.auto_exploring = False
        return None
    # Enemy in FOV?
    for e in gs.enemies:
        if e.is_alive() and (e.x, e.y) in gs.visible:
            gs.msg("Exploring stopped: enemy spotted!", C_YELLOW)
            gs.auto_exploring = False
            return None
    # Item on current tile?
    for it in gs.items:
        if it.x == p.x and it.y == p.y:
            gs.msg("Exploring stopped: item found!", C_YELLOW)
            gs.auto_exploring = False
            return None
    # Stairs on current tile?
    if gs.tiles[p.y][p.x] in (T_STAIRS_DOWN, T_STAIRS_UP):
        gs.msg("Exploring stopped: stairs found!", C_YELLOW)
        gs.auto_exploring = False
        return None
    # BFS to nearest unexplored walkable tile
    target = _bfs_unexplored(gs)
    if target is None:
        gs.msg("Exploring stopped: fully explored.", C_YELLOW)
        gs.auto_exploring = False
        return None
    tx, ty = target
    step = astar(gs.tiles, p.x, p.y, tx, ty, max_steps=50)
    if step:
        return player_move(gs, step[0], step[1])
    gs.msg("Exploring stopped: can't reach target.", C_YELLOW)
    gs.auto_exploring = False
    return None


def _bfs_unexplored(gs):
    """BFS from player position to find nearest unexplored walkable tile."""
    p = gs.player
    visited = set()
    queue = deque([(p.x, p.y)])
    visited.add((p.x, p.y))
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in visited:
                continue
            if nx < 0 or nx >= MAP_W or ny < 0 or ny >= MAP_H:
                continue
            if gs.tiles[ny][nx] not in WALKABLE:
                continue
            visited.add((nx, ny))
            if not gs.explored[ny][nx]:
                return (nx, ny)
            queue.append((nx, ny))
    return None


# ============================================================
# REST UNTIL HEALED (Phase 4, item 22)
# ============================================================

def rest_until_healed(gs, scr):
    """Skip turns until HP == max_hp. Returns total turns rested."""
    p = gs.player
    if p.hp >= p.max_hp:
        gs.msg("You are already at full health.", C_WHITE)
        return 0
    turns_rested = 0
    gs.msg("Resting...", C_CYAN)
    while p.hp < p.max_hp and gs.running and not gs.game_over:
        # Stop if enemy in FOV
        fov_radius = p.get_torch_radius()
        if "Blindness" in p.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, p.x, p.y, fov_radius, gs.visible)
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                gs.msg(f"Resting interrupted! {e.name} spotted! (Rested {turns_rested} turns)", C_RED)
                return turns_rested
        # Stop if hunger too low
        if p.hunger <= REST_HUNGER_THRESHOLD:
            gs.msg(f"Too hungry to rest! (Rested {turns_rested} turns)", C_YELLOW)
            return turns_rested
        # Rest one turn
        if p.hunger > B["rest_hunger_threshold"]:
            p.hp = min(p.max_hp, p.hp + B["rest_hp_per_turn"])
        p.hunger = max(0, p.hunger - B["hunger_rest_cost"])
        gs.turn_count += 1
        turns_rested += 1
        process_enemies(gs)
        process_status(gs)
        if p.hp <= 0:
            gs.game_over = True
            break
        # Render periodically
        if scr and turns_rested % 5 == 0:
            render_game(scr, gs)
    if p.hp >= p.max_hp:
        gs.msg(f"Rested for {turns_rested} turns. Fully healed!", C_GREEN)
    return turns_rested


# ============================================================
# ENHANCED DEATH & VICTORY SCREENS (Phase 6)
# ============================================================

def show_enhanced_death(scr, gs):
    """Enhanced death screen with full statistics (Phase 6, item 27)."""
    # Flush any buffered keypresses so death screen isn't dismissed instantly
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)
    curses.napms(500)  # Brief pause before showing death stats

    p = gs.player
    elapsed = int(time.time() - gs.start_time)
    m, s = elapsed // 60, elapsed % 60
    scr.erase()
    h, w = scr.getmaxyx()

    lines = [
        ("+" + "=" * 36 + "+", C_RED),
        ("|      REST IN PEACE               |", C_RED),
        ("|                                   |", C_RED),
        (f"|   Level {p.level} {CHARACTER_CLASSES[p.player_class]['name'] if p.player_class and p.player_class in CHARACTER_CLASSES else 'Adventurer'}{' ' * max(0, 24 - len(f'Level {p.level} ' + (CHARACTER_CLASSES.get(p.player_class, {}).get('name', 'Adventurer') if p.player_class else 'Adventurer')))}|", C_RED),
        ("|                                   |", C_RED),
    ]
    cause = gs.death_cause or "unknown causes"
    cause_line = f"|   Slain by: {cause}"
    cause_line = cause_line[:36] + " " * max(0, 37 - len(cause_line)) + "|"
    lines.append((cause_line, C_RED))
    floor_line = f"|   on Floor {p.floor}, Turn {gs.turn_count}"
    floor_line = floor_line[:36] + " " * max(0, 37 - len(floor_line)) + "|"
    lines.append((floor_line, C_RED))
    lines.append(("+" + "=" * 36 + "+", C_RED))
    # Stats section
    wpn_name = p.weapon.display_name[:14] if p.weapon else "Fists"
    arm_name = p.armor.display_name[:14] if p.armor else "None"
    ring_name = p.ring.display_name[:14] if p.ring else "None"
    lines.extend([
        (f"  HP: {p.hp}/{p.max_hp}  STR: {p.strength}  DEF: {p.total_defense()}", C_YELLOW),
        (f"  Wpn: {wpn_name}  Arm: {arm_name}", C_WHITE),
        (f"  Ring: {ring_name}  Gold: {p.gold}", C_CYAN),
        ("", C_WHITE),
        (f"  Enemies killed: {p.kills}", C_GREEN),
        (f"  Floors explored: {len(gs.floors_explored)}", C_GREEN),
        (f"  Deepest floor: {p.deepest_floor}", C_GREEN),
        (f"  Spells cast: {p.spells_cast}  Potions: {p.potions_drunk}", C_GREEN),
        (f"  Time: {m}m{s}s  Damage dealt: {p.damage_dealt}", C_GREEN),
    ])
    # Last messages
    lines.append(("", C_WHITE))
    lines.append(("  Last words:", C_MAGENTA))
    last_msgs = list(gs.messages)[-3:]
    for msg_text, _ in last_msgs:
        lines.append((f'  "{msg_text[:34]}"', C_MAGENTA))

    quip = random.choice(DEATH_QUIPS)
    lines.append(("", C_WHITE))
    lines.append((f'  "{quip}"', C_DARK))

    score = calculate_score(p, gs)
    lines.append(("", C_WHITE))
    lines.append((f"  SCORE: {score}", C_GOLD))

    # Lifetime stats
    lifetime = update_lifetime_stats(gs)
    lines.extend(_format_lifetime_stats_lines(lifetime))

    sy = max(0, (h - len(lines) - 2) // 2)
    for i, (text, color) in enumerate(lines):
        if sy + i >= h - 1:
            break
        cx = max(0, (w - len(text)) // 2)
        safe_addstr(scr, sy + i, cx, text, curses.color_pair(color))

    pr = "[ Press ENTER or SPACE to continue ]"
    safe_addstr(scr, min(h - 1, sy + len(lines) + 1), max(0, (w - len(pr)) // 2),
               pr, curses.color_pair(C_DARK))
    scr.refresh()
    while True:
        k = scr.getch()
        if k in (10, 13, 32):  # Enter or Space (#24)
            break


def show_enhanced_victory(scr, gs):
    """Enhanced victory screen with celebration art (Phase 6, item 28)."""
    p = gs.player
    elapsed = int(time.time() - gs.start_time)
    m, s = elapsed // 60, elapsed % 60
    scr.erase()
    h, w = scr.getmaxyx()

    lines = [
        ("*  .  *  .  *  .  *  .  *  .  *", C_YELLOW),
        ("", C_WHITE),
        ("     V I C T O R Y ! ! !", C_YELLOW),
        ("", C_WHITE),
        ("  THE DREAD LORD IS VANQUISHED", C_GREEN),
        ("  THORNHAVEN IS SAVED!", C_GREEN),
        ("", C_WHITE),
        ("*  .  *  .  *  .  *  .  *  .  *", C_YELLOW),
        ("", C_WHITE),
        (f"  Class: {CHARACTER_CLASSES[p.player_class]['name'] if p.player_class and p.player_class in CHARACTER_CLASSES else 'Adventurer'}  Level: {p.level}", C_GREEN),
        (f"  Kills: {p.kills}  Bosses: {p.bosses_killed}", C_GREEN),
        (f"  Gold: {p.gold}  Turns: {gs.turn_count}  Time: {m}m{s}s", C_GREEN),
        (f"  Floors explored: {len(gs.floors_explored)}", C_GREEN),
        (f"  Items: {p.items_found}  Potions: {p.potions_drunk}  Scrolls: {p.scrolls_read}", C_GREEN),
        (f"  Spells cast: {p.spells_cast}  Shots: {p.projectiles_fired}", C_GREEN),
        (f"  Damage dealt: {p.damage_dealt}  Taken: {p.damage_taken}", C_GREEN),
        ("", C_WHITE),
        ("  You are a true hero of Thornhaven!", C_YELLOW),
    ]

    score = calculate_score(p, gs)
    lines.extend([
        ("", C_WHITE),
        (f"  SCORE: {score}", C_GOLD),
        ("  (Base + 5000 victory bonus!)", C_GOLD),
    ])

    # Lifetime stats
    lifetime = update_lifetime_stats(gs)
    lines.extend(_format_lifetime_stats_lines(lifetime))

    sy = max(0, (h - len(lines) - 2) // 2)
    for i, (text, color) in enumerate(lines):
        if sy + i >= h - 1:
            break
        cx = max(0, (w - len(text)) // 2)
        safe_addstr(scr, sy + i, cx, text,
                   curses.color_pair(color) | (curses.A_BOLD if color == C_YELLOW else 0))

    pr = "[ Press ENTER or SPACE to continue ]"
    safe_addstr(scr, min(h - 1, sy + len(lines) + 1), max(0, (w - len(pr)) // 2),
               pr, curses.color_pair(C_DARK))
    scr.refresh()
    while True:
        k = scr.getch()
        if k in (10, 13, 32):  # Enter or Space (#24)
            break


# ============================================================
# PERSISTENT LIFETIME STATS
# ============================================================

def _default_lifetime_stats():
    """Return a fresh lifetime stats dictionary."""
    return {
        "total_games": 0,
        "total_wins": 0,
        "total_deaths": 0,
        "highest_floor": 0,
        "highest_level": 0,
        "longest_run_turns": 0,
        "total_turns": 0,
        "total_kills": 0,
        "most_kills_single_run": 0,
    }


def load_lifetime_stats():
    """Load lifetime stats from disk. Returns defaults if missing/corrupt."""
    try:
        with open(STATS_FILE_PATH, 'r') as f:
            data = json.load(f)
        # Validate it's a dict with expected keys; fill missing keys with defaults
        if not isinstance(data, dict):
            return _default_lifetime_stats()
        defaults = _default_lifetime_stats()
        for key in defaults:
            if key not in data or not isinstance(data[key], (int, float)):
                data[key] = defaults[key]
        return data
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return _default_lifetime_stats()


def save_lifetime_stats(stats):
    """Save lifetime stats to disk."""
    try:
        with open(STATS_FILE_PATH, 'w') as f:
            json.dump(stats, f, indent=2)
    except OSError:
        pass  # Silently fail if we can't write


def update_lifetime_stats(gs):
    """Update lifetime stats at end of a game (death or victory). Returns updated stats."""
    stats = load_lifetime_stats()
    p = gs.player
    # Increment game count (was already incremented at game start)
    if gs.victory:
        stats["total_wins"] += 1
    else:
        stats["total_deaths"] += 1
    stats["highest_floor"] = max(stats["highest_floor"], p.deepest_floor)
    stats["highest_level"] = max(stats["highest_level"], p.level)
    stats["longest_run_turns"] = max(stats["longest_run_turns"], gs.turn_count)
    stats["total_turns"] += gs.turn_count
    stats["total_kills"] += p.kills
    stats["most_kills_single_run"] = max(stats["most_kills_single_run"], p.kills)
    save_lifetime_stats(stats)
    return stats


def show_lifetime_stats(scr):
    """Display lifetime stats overlay."""
    stats = load_lifetime_stats()
    scr.erase()
    h, w = scr.getmaxyx()
    title = "LIFETIME STATS"
    safe_addstr(scr, 1, max(0, (w - len(title)) // 2), title,
               curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 2, max(0, (w - 30) // 2), "=" * 30, curses.color_pair(C_DARK))

    win_rate = f"{stats['total_wins']/stats['total_games']*100:.0f}%" if stats['total_games'] > 0 else "N/A"
    lines = [
        (f"  Games Played:          {stats['total_games']}", C_WHITE),
        (f"  Wins:                  {stats['total_wins']}", C_GREEN),
        (f"  Deaths:                {stats['total_deaths']}", C_RED),
        (f"  Win Rate:              {win_rate}", C_YELLOW),
        ("", C_WHITE),
        (f"  Highest Floor:         {stats['highest_floor']}", C_CYAN),
        (f"  Highest Level:         {stats['highest_level']}", C_CYAN),
        (f"  Longest Run (turns):   {stats['longest_run_turns']}", C_CYAN),
        ("", C_WHITE),
        (f"  Total Turns Played:    {stats['total_turns']}", C_GOLD),
        (f"  Total Enemies Killed:  {stats['total_kills']}", C_GOLD),
        (f"  Most Kills (one run):  {stats['most_kills_single_run']}", C_GOLD),
    ]

    sy = 4
    for i, (text, color) in enumerate(lines):
        if sy + i >= h - 2:
            break
        cx = max(0, (w - len(text)) // 2)
        safe_addstr(scr, sy + i, cx, text, curses.color_pair(color))

    pr = "[ Press any key ]"
    safe_addstr(scr, min(h - 1, sy + len(lines) + 1), max(0, (w - len(pr)) // 2),
               pr, curses.color_pair(C_DARK))
    scr.refresh()
    scr.getch()


def _format_lifetime_stats_lines(stats):
    """Format lifetime stats as lines for embedding in death/victory screens."""
    win_rate = f"{stats['total_wins']/stats['total_games']*100:.0f}%" if stats['total_games'] > 0 else "N/A"
    return [
        ("", C_WHITE),
        ("  --- Lifetime Stats ---", C_UI),
        (f"  Games: {stats['total_games']}  Wins: {stats['total_wins']}  Deaths: {stats['total_deaths']}  ({win_rate})", C_DARK),
        (f"  Best Floor: {stats['highest_floor']}  Best Lv: {stats['highest_level']}  Best Kills: {stats['most_kills_single_run']}", C_DARK),
        (f"  Total Kills: {stats['total_kills']}  Total Turns: {stats['total_turns']}", C_DARK),
    ]


# ============================================================
# SAVE/LOAD SYSTEM (Phase 7, item 33)
# ============================================================

def _compute_checksum(data_str):
    """Compute SHA256 checksum for save data integrity."""
    return hashlib.sha256(data_str.encode('utf-8')).hexdigest()


def save_game(gs):
    """Save game state to JSON file."""
    p = gs.player
    save_data = {
        "version": 5,
        "player": {
            "x": p.x, "y": p.y, "hp": p.hp, "max_hp": p.max_hp,
            "mana": p.mana, "max_mana": p.max_mana,
            "strength": p.strength, "defense": p.defense,
            "level": p.level, "xp": p.xp, "xp_next": p.xp_next,
            "floor": p.floor, "gold": p.gold, "turns": p.turns,
            "kills": p.kills, "hunger": p.hunger,
            "torch_fuel": p.torch_fuel,
            "torch_lit": p.torch_lit,
            "deepest_floor": p.deepest_floor,
            "potions_drunk": p.potions_drunk, "scrolls_read": p.scrolls_read,
            "items_found": p.items_found, "damage_dealt": p.damage_dealt,
            "damage_taken": p.damage_taken, "foods_eaten": p.foods_eaten,
            "bosses_killed": p.bosses_killed, "spells_cast": p.spells_cast,
            "projectiles_fired": p.projectiles_fired,
            "player_class": p.player_class,
            "pending_levelups": p.pending_levelups,
            "ability_cooldown": p.ability_cooldown,
            "evasion_bonus": getattr(p, '_evasion_bonus', 0),
            "known_spells": sorted(p.known_spells),
            "known_abilities": sorted(p.known_abilities),
            "status_effects": dict(p.status_effects),
            "inventory": [_serialize_item(it) for it in p.inventory],
            "weapon_idx": p.inventory.index(p.weapon) if p.weapon and p.weapon in p.inventory else -1,
            "armor_idx": p.inventory.index(p.armor) if p.armor and p.armor in p.inventory else -1,
            "ring_idx": p.inventory.index(p.ring) if p.ring and p.ring in p.inventory else -1,
            "bow_idx": p.inventory.index(p.bow) if p.bow and p.bow in p.inventory else -1,
        },
        "turn_count": gs.turn_count,
        "tiles": [[gs.tiles[y][x] for x in range(MAP_W)] for y in range(MAP_H)],
        "explored": [[gs.explored[y][x] for x in range(MAP_W)] for y in range(MAP_H)],
        "stair_down": list(gs.stair_down),
        "enemies": [_serialize_enemy(e) for e in gs.enemies if e.is_alive()],
        "items": [_serialize_item_on_ground(it) for it in gs.items],
        "potion_ids": gs.potion_ids,
        "scroll_ids": gs.scroll_ids,
        "id_potions": list(gs.id_potions),
        "id_scrolls": list(gs.id_scrolls),
        "tips_shown": list(gs.tips_shown),
        "first_melee_done": gs.first_melee_done,
        "floors_explored": list(gs.floors_explored),
        "death_cause": gs.death_cause,
        "shop_discovered": gs.shop_discovered,
        "journal": gs.journal,
        "alchemy_used": [list(p) for p in gs.alchemy_used],
        "wall_torches": gs.wall_torches,
        "puzzles": gs.puzzles,
        "traps": gs.traps,
        "branch_choices": gs.branch_choices,
        "active_branch": gs.active_branch,
        "bestiary": gs.bestiary,
        "shops": [
            {
                "room": list(room),
                "items": [
                    {"item": _serialize_item(si.item), "price": si.price, "sold": si.sold}
                    for si in shop_items
                ],
            }
            for room, shop_items in gs.shops
        ],
    }
    data_str = json.dumps(save_data, separators=(',', ':'))
    checksum = _compute_checksum(data_str)
    wrapper = {"checksum": checksum, "data": save_data}
    try:
        with open(SAVE_FILE_PATH, 'w') as f:
            json.dump(wrapper, f)
        return True
    except Exception:
        return False


def load_game():
    """Load game state from JSON file. Returns GameState or None."""
    try:
        with open(SAVE_FILE_PATH, 'r') as f:
            wrapper = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    # Verify checksum
    stored_checksum = wrapper.get("checksum", "")
    data = wrapper.get("data", {})
    data_str = json.dumps(data, separators=(',', ':'))
    computed = _compute_checksum(data_str)
    if stored_checksum != computed:
        return None  # tampered or corrupted

    try:
        gs = GameState(headless=True)
        pd = data["player"]
        p = gs.player
        p.x, p.y = pd["x"], pd["y"]
        p.hp, p.max_hp = pd["hp"], pd["max_hp"]
        p.mana, p.max_mana = pd["mana"], pd["max_mana"]
        p.strength, p.defense = pd["strength"], pd["defense"]
        p.level, p.xp, p.xp_next = pd["level"], pd["xp"], pd["xp_next"]
        p.floor, p.gold = pd["floor"], pd["gold"]
        p.turns = pd.get("turns", 0)
        p.kills = pd["kills"]
        p.hunger = pd["hunger"]
        p.torch_fuel = pd["torch_fuel"]
        p.torch_lit = pd.get("torch_lit", True)
        p.deepest_floor = pd["deepest_floor"]
        p.potions_drunk = pd["potions_drunk"]
        p.scrolls_read = pd["scrolls_read"]
        p.items_found = pd["items_found"]
        p.damage_dealt = pd["damage_dealt"]
        p.damage_taken = pd["damage_taken"]
        p.foods_eaten = pd["foods_eaten"]
        p.bosses_killed = pd["bosses_killed"]
        p.spells_cast = pd["spells_cast"]
        p.projectiles_fired = pd["projectiles_fired"]
        # v2 fields (class system) — v1 saves get defaults
        p.player_class = pd.get("player_class", None)
        p.pending_levelups = pd.get("pending_levelups", [])
        p.ability_cooldown = pd.get("ability_cooldown", 0)
        p._evasion_bonus = pd.get("evasion_bonus", 0)
        # Migrate known_spells: old saves default to all base spells
        if "known_spells" in pd:
            p.known_spells = set(pd["known_spells"])
        else:
            p.known_spells = set(BASE_SPELLS)
        p.known_abilities = set(pd.get("known_abilities", []))
        p.status_effects = pd.get("status_effects", {})
        # Restore inventory
        p.inventory = [_deserialize_item(d) for d in pd.get("inventory", [])]
        if pd.get("weapon_idx", -1) >= 0 and pd["weapon_idx"] < len(p.inventory):
            p.weapon = p.inventory[pd["weapon_idx"]]
        if pd.get("armor_idx", -1) >= 0 and pd["armor_idx"] < len(p.inventory):
            p.armor = p.inventory[pd["armor_idx"]]
        if pd.get("ring_idx", -1) >= 0 and pd["ring_idx"] < len(p.inventory):
            p.ring = p.inventory[pd["ring_idx"]]
        if pd.get("bow_idx", -1) >= 0 and pd["bow_idx"] < len(p.inventory):
            p.bow = p.inventory[pd["bow_idx"]]

        gs.turn_count = data["turn_count"]
        gs.tiles = data["tiles"]
        gs.explored = data["explored"]
        gs.stair_down = tuple(data["stair_down"])
        gs.enemies = [_deserialize_enemy(d) for d in data.get("enemies", [])]
        gs.items = [_deserialize_item_ground(d) for d in data.get("items", [])]
        gs.potion_ids = data.get("potion_ids", gs.potion_ids)
        gs.scroll_ids = data.get("scroll_ids", gs.scroll_ids)
        gs.id_potions = set(data.get("id_potions", []))
        gs.id_scrolls = set(data.get("id_scrolls", []))
        gs.tips_shown = set(data.get("tips_shown", []))
        gs.first_melee_done = data.get("first_melee_done", False)
        gs.floors_explored = set(data.get("floors_explored", []))
        gs.death_cause = data.get("death_cause")
        gs.shop_discovered = data.get("shop_discovered", False)
        gs.journal = data.get("journal", {})
        gs.alchemy_used = set(tuple(p) for p in data.get("alchemy_used", []))
        gs.wall_torches = data.get("wall_torches", [])
        gs.puzzles = data.get("puzzles", [])
        gs.traps = data.get("traps", [])
        gs.branch_choices = {int(k): v for k, v in data.get("branch_choices", {}).items()}
        gs.active_branch = data.get("active_branch", None)
        gs.bestiary = data.get("bestiary", {})
        gs.rooms = []  # rooms not needed after generation
        # Restore shops
        gs.shops = []
        for shop_data in data.get("shops", []):
            room = tuple(shop_data["room"])
            shop_items = []
            for si_data in shop_data["items"]:
                item = _deserialize_item(si_data["item"])
                si = ShopItem(item, si_data["price"])
                si.sold = si_data.get("sold", False)
                shop_items.append(si)
            gs.shops.append((room, shop_items))
        return gs
    except (KeyError, TypeError, IndexError):
        return None


def delete_save():
    """Delete save file (on death — permadeath)."""
    try:
        os.remove(SAVE_FILE_PATH)
    except FileNotFoundError:
        pass


def save_exists():
    """Check if a save file exists."""
    return os.path.exists(SAVE_FILE_PATH)


def _serialize_item(item):
    return {
        "x": item.x, "y": item.y, "item_type": item.item_type,
        "subtype": item.subtype if not isinstance(item.subtype, int) else item.subtype,
        "data": item.data, "identified": item.identified,
        "equipped": item.equipped, "count": item.count,
    }


def _serialize_item_on_ground(item):
    return _serialize_item(item)


def _serialize_enemy(e):
    d = {
        "x": e.x, "y": e.y, "etype": e.etype,
        "hp": e.hp, "max_hp": e.max_hp, "alerted": e.alerted,
        "alertness": e.alertness,
        "energy": e.energy, "frozen_turns": e.frozen_turns,
        "summon_cooldown": e.summon_cooldown,
        "patrol_dir": list(e.patrol_dir),
    }
    # D&D expansion fields (only save non-default)
    if e.disguised:
        d["disguised"] = True
    if e.phase_cooldown:
        d["phase_cooldown"] = e.phase_cooldown
    if e.poisoned_turns > 0:
        d["poisoned_turns"] = e.poisoned_turns
    if e.fleeing:
        d["fleeing"] = True
    if e.regen_suppressed > 0:
        d["regen_suppressed"] = e.regen_suppressed
    return d


def _deserialize_item(d):
    item = Item(d["x"], d["y"], d["item_type"], d["subtype"], d["data"])
    item.identified = d.get("identified", False)
    item.equipped = d.get("equipped", False)
    item.count = d.get("count", 1)
    return item


def _deserialize_item_ground(d):
    return _deserialize_item(d)


def _deserialize_enemy(d):
    e = Enemy(d["x"], d["y"], d["etype"])
    e.hp = d["hp"]
    e.max_hp = d["max_hp"]
    e.alerted = d.get("alerted", False)
    e.alertness = d.get("alertness", "alert" if e.alerted else "unwary")
    e.energy = d.get("energy", 0)
    e.frozen_turns = d.get("frozen_turns", 0)
    e.summon_cooldown = d.get("summon_cooldown", 0)
    e.patrol_dir = tuple(d.get("patrol_dir", (0, 1)))
    # D&D expansion fields
    e.disguised = d.get("disguised", False)
    e.phase_cooldown = d.get("phase_cooldown", 0)
    e.poisoned_turns = d.get("poisoned_turns", 0)
    e.fleeing = d.get("fleeing", False)
    e.regen_suppressed = d.get("regen_suppressed", 0)
    return e


# ============================================================
# MAIN GAME LOOP
# ============================================================

def show_class_select(scr):
    """Show class selection screen. Returns class key or None for classless."""
    scr.erase()
    safe_addstr(scr, 1, 20, "CHOOSE YOUR CLASS", curses.color_pair(C_TITLE) | curses.A_BOLD)
    safe_addstr(scr, 2, 20, "=" * 17, curses.color_pair(C_DARK))
    row = 4
    classes = list(CHARACTER_CLASSES.items())
    for i, (key, cc) in enumerate(classes):
        color = [C_RED, C_CYAN, C_GREEN][i]
        safe_addstr(scr, row, 5, f"[{i+1}] {cc['name']}", curses.color_pair(color) | curses.A_BOLD)
        safe_addstr(scr, row, 25, cc['desc'], curses.color_pair(C_WHITE))
        row += 1
        safe_addstr(scr, row, 9, f"HP:{cc['hp']} MP:{cc['mp']} STR:{cc['str']} DEF:{cc['defense']}", curses.color_pair(C_DARK))
        row += 1
        safe_addstr(scr, row, 9, f"Ability: {cc['ability']} — {cc['ability_desc']}", curses.color_pair(C_DARK))
        row += 2
    safe_addstr(scr, row, 5, "[4] Adventurer", curses.color_pair(C_YELLOW) | curses.A_BOLD)
    safe_addstr(scr, row, 25, "Classic mode — no class, balanced stats", curses.color_pair(C_WHITE))
    row += 2
    safe_addstr(scr, row + 1, 15, "Press 1-4 to choose", curses.color_pair(C_UI))
    scr.refresh()
    while True:
        key = scr.getch()
        if key == ord('1'):
            return classes[0][0]
        elif key == ord('2'):
            return classes[1][0]
        elif key == ord('3'):
            return classes[2][0]
        elif key == ord('4'):
            return None


def _show_branch_choice(scr, gs, floor_num):
    """Show branch selection screen (curses UI) when descending to a branch floor."""
    if floor_num not in BRANCH_CHOICES:
        return None
    branch_a_key, branch_b_key = BRANCH_CHOICES[floor_num]
    branch_a = BRANCH_DEFS[branch_a_key]
    branch_b = BRANCH_DEFS[branch_b_key]

    # Flush buffered keypresses
    scr.nodelay(True)
    while scr.getch() != -1:
        pass
    scr.nodelay(False)

    scr.erase()
    y = 2
    safe_addstr(scr, y, 4, "THE PATH BRANCHES", curses.color_pair(C_TITLE) | curses.A_BOLD)
    y += 2
    safe_addstr(scr, y, 4, f"As you descend to floor {floor_num}, two passages open before you.", curses.color_pair(C_WHITE))
    y += 2

    # Branch A
    safe_addstr(scr, y, 4, f"[1] {branch_a['name']}", curses.color_pair(C_YELLOW) | curses.A_BOLD)
    y += 1
    safe_addstr(scr, y, 8, f"Floors {branch_a['floors'][0]}-{branch_a['floors'][-1]}", curses.color_pair(C_UI))
    y += 1
    enemies_a = [ENEMY_TYPES[e]["name"] for e in branch_a["enemy_pool"][:3]]
    safe_addstr(scr, y, 8, f"Denizens: {', '.join(enemies_a)}", curses.color_pair(C_DARK))
    y += 1
    mini_a = ENEMY_TYPES[branch_a["mini_boss"]]["name"]
    safe_addstr(scr, y, 8, f"Guardian: {mini_a}", curses.color_pair(C_RED))
    y += 2

    # Branch B
    safe_addstr(scr, y, 4, f"[2] {branch_b['name']}", curses.color_pair(C_YELLOW) | curses.A_BOLD)
    y += 1
    safe_addstr(scr, y, 8, f"Floors {branch_b['floors'][0]}-{branch_b['floors'][-1]}", curses.color_pair(C_UI))
    y += 1
    enemies_b = [ENEMY_TYPES[e]["name"] for e in branch_b["enemy_pool"][:3]]
    safe_addstr(scr, y, 8, f"Denizens: {', '.join(enemies_b)}", curses.color_pair(C_DARK))
    y += 1
    mini_b = ENEMY_TYPES[branch_b["mini_boss"]]["name"]
    safe_addstr(scr, y, 8, f"Guardian: {mini_b}", curses.color_pair(C_RED))
    y += 2

    safe_addstr(scr, y, 4, "Choose your path (1 or 2):", curses.color_pair(C_WHITE) | curses.A_BOLD)
    scr.refresh()

    while True:
        key = scr.getch()
        if key == ord('1'):
            gs.branch_choices[floor_num] = branch_a_key
            gs.msg(f"You enter {branch_a['name']}...", C_YELLOW)
            return branch_a_key
        elif key == ord('2'):
            gs.branch_choices[floor_num] = branch_b_key
            gs.msg(f"You enter {branch_b['name']}...", C_YELLOW)
            return branch_b_key


def _choose_branch_headless(gs, floor_num):
    """Auto-choose a branch for bot/headless modes (random pick)."""
    if floor_num not in BRANCH_CHOICES:
        return None
    branch_a_key, branch_b_key = BRANCH_CHOICES[floor_num]
    choice = random.choice([branch_a_key, branch_b_key])
    gs.branch_choices[floor_num] = choice
    gs.msg(f"You enter {BRANCH_DEFS[choice]['name']}...", C_YELLOW)
    return choice


def _init_new_game(gs):
    """Set up starter gear for a new game."""
    pc = gs.player.player_class
    if pc == "warrior":
        # Long Sword + standard gear
        sw = Item(0, 0, "weapon", 3, WEAPON_TYPES[3])  # Long Sword
        sw.identified = True
        sw.equipped = True
        gs.player.weapon = sw
        gs.player.inventory.append(sw)
    elif pc == "mage":
        # Rusty Dagger + mana potion
        sw = Item(0, 0, "weapon", 0, WEAPON_TYPES[0])
        sw.identified = True
        sw.equipped = True
        gs.player.weapon = sw
        gs.player.inventory.append(sw)
        # Extra mana — mage starts with full (already set by class stats)
    elif pc == "rogue":
        # Short Sword + throwing daggers
        sw = Item(0, 0, "weapon", 1, WEAPON_TYPES[1])  # Short Sword
        sw.identified = True
        sw.equipped = True
        gs.player.weapon = sw
        gs.player.inventory.append(sw)
        daggers = Item(0, 0, "throwing_dagger", "Throwing Dagger", dict(THROWING_DAGGER))
        daggers.count = 8
        gs.player.inventory.append(daggers)
    else:
        # Classic adventurer
        sw = Item(0, 0, "weapon", 0, WEAPON_TYPES[0])
        sw.identified = True
        sw.equipped = True
        gs.player.weapon = sw
        gs.player.inventory.append(sw)
    # Common starter items for all classes
    for fd in [FOOD_TYPES[0], FOOD_TYPES[1]]:
        fi = Item(0, 0, "food", fd["name"], fd)
        gs.player.inventory.append(fi)
    hp = Item(0, 0, "potion", "Healing",
             {"effect": "Healing", "color_name": gs.potion_ids["Healing"], "char": '!'})
    gs.player.inventory.append(hp)
    sb = Item(0, 0, "bow", "Short Bow", dict(BOW_TYPES[0]))
    sb.identified = True
    sb.equipped = True
    gs.player.bow = sb
    gs.player.inventory.append(sb)
    arrows = Item(0, 0, "arrow", "Arrow", dict(ARROW_ITEM))
    arrows.count = 10
    gs.player.inventory.append(arrows)
    gs.generate_floor(1)
    # Increment lifetime game counter
    lt = load_lifetime_stats()
    lt["total_games"] += 1
    save_lifetime_stats(lt)
    # Start session recording
    try:
        gs.recorder = SessionRecorder(gs.seed)
        gs.recorder.record_floor_change(gs)
    except Exception:
        gs.recorder = None
    gs.msg("You descend into the darkness beneath Thornhaven...", C_YELLOW)
    gs.msg("Press ? for help.", C_DARK)


def game_loop(scr):
    """Main game loop. Handles input, rendering, and game state updates."""
    curses.curs_set(0)
    scr.nodelay(False)
    scr.keypad(True)
    init_colors()

    # Terminal size check (Phase 7, item 31)
    h, w = scr.getmaxyx()
    if h < MIN_TERMINAL_H or w < MIN_TERMINAL_W:
        scr.erase()
        safe_addstr(scr, 0, 0,
                   f"Terminal too small. Need {MIN_TERMINAL_W}x{MIN_TERMINAL_H}, currently {w}x{h}. Please resize.",
                   0)
        scr.refresh()
        scr.getch()
        return

    show_title(scr)

    # Check for saved game (Phase 7, item 33)
    gs = None
    if save_exists():
        scr.erase()
        safe_addstr(scr, 10, 20, "Saved game found.", curses.color_pair(C_YELLOW) | curses.A_BOLD)
        safe_addstr(scr, 12, 20, "Continue saved game? (y/n)", curses.color_pair(C_WHITE))
        scr.refresh()
        while True:
            key = scr.getch()
            if key == ord('y') or key == ord('Y'):
                gs = load_game()
                if gs:
                    gs._headless = False
                    gs._scr = scr
                    gs.msg("Game loaded.", C_GREEN)
                else:
                    scr.erase()
                    safe_addstr(scr, 10, 20, "Save file corrupted or tampered.",
                               curses.color_pair(C_RED))
                    safe_addstr(scr, 12, 20, "Starting new game...",
                               curses.color_pair(C_WHITE))
                    scr.refresh()
                    curses.napms(1500)
                    delete_save()
                break
            elif key == ord('n') or key == ord('N'):
                delete_save()
                break

    if gs is None:
        chosen_class = show_class_select(scr)
        gs = GameState(player_class=chosen_class)
        gs._scr = scr
        _init_new_game(gs)

    MOVE_KEYS = {
        curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
        curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
        ord('w'): (0,-1), ord('s'): (0,1),
        ord('a'): (-1,0), ord('d'): (1,0),
        ord('h'): (-1,0), ord('j'): (0,1),
        ord('k'): (0,-1), ord('l'): (1,0),
        ord('y'): (-1,-1), ord('u'): (1,-1),
        ord('b'): (-1,1), ord('n'): (1,1),
    }

    while gs.running and not gs.game_over:
        # Terminal resize detection (Phase 7, item 30)
        cur_h, cur_w = scr.getmaxyx()
        if cur_h < MIN_TERMINAL_H or cur_w < MIN_TERMINAL_W:
            scr.erase()
            safe_addstr(scr, 0, 0,
                       f"Terminal too small! Need {MIN_TERMINAL_W}x{MIN_TERMINAL_H} (currently {cur_w}x{cur_h})",
                       curses.A_BOLD)
            scr.refresh()
            curses.napms(200)
            continue

        # Paralysis: skip player's turn entirely
        if "Paralysis" in gs.player.status_effects:
            render_game(scr, gs)
            gs.msg("You are paralyzed!", C_YELLOW)
            gs.turn_count += 1
            process_enemies(gs)
            process_status(gs)
            if gs.player.hp <= 0:
                gs.game_over = True
            curses.napms(200)
            continue

        # Auto-fight loop (Phase 4, item 20)
        if gs.auto_fighting:
            render_game(scr, gs)
            result = auto_fight_step(gs)
            if result is None:
                gs.auto_fighting = False
                continue
            if result:
                gs.turn_count += 1
                if gs.last_noise > 0:
                    _stealth_detection(gs, gs.last_noise)
                gs.last_noise = 0
                process_enemies(gs)
                process_status(gs)
                check_context_tips(gs)
                if gs.player.hp <= 0:
                    gs.game_over = True
            curses.napms(80)
            continue

        # Auto-explore loop (Phase 4, item 21)
        if gs.auto_exploring:
            render_game(scr, gs)
            result = auto_explore_step(gs)
            if result is None:
                gs.auto_exploring = False
                continue
            if result:
                gs.turn_count += 1
                if gs.last_noise > 0:
                    _stealth_detection(gs, gs.last_noise)
                gs.last_noise = 0
                process_enemies(gs)
                process_status(gs)
                check_context_tips(gs)
                if gs.player.hp <= 0:
                    gs.game_over = True
            curses.napms(40)
            # Check for keypress to cancel
            scr.nodelay(True)
            cancel_key = scr.getch()
            scr.nodelay(False)
            if cancel_key != -1:
                gs.auto_exploring = False
                gs.msg("Exploring cancelled.", C_WHITE)
            continue

        # Pending level-up choices
        while gs.player.pending_levelups:
            show_levelup_choice(scr, gs)

        render_game(scr, gs)
        key = scr.getch()
        turn_spent = False

        # Record input for session replay
        if gs.recorder and key != -1:
            key_name = None
            if key in MOVE_KEYS:
                # Map key to character name for replay
                for ch in 'wasdhljkyubn':
                    if key == ord(ch):
                        key_name = ch
                        break
                if key_name is None:
                    for name, code in [('UP', curses.KEY_UP), ('DOWN', curses.KEY_DOWN),
                                        ('LEFT', curses.KEY_LEFT), ('RIGHT', curses.KEY_RIGHT)]:
                        if key == code:
                            key_name = name
                            break
            elif key == ord('>'):
                key_name = '>'
            elif key == ord('<'):
                key_name = '<'
            elif key == ord('.') or key == ord('5'):
                key_name = '.'
            elif key == ord(','):
                key_name = ','
            elif key == ord('f'):
                key_name = 'f'
            elif key == ord('z'):
                key_name = 'z'
            elif key == ord('p'):
                key_name = 'p'
            if key_name:
                gs.recorder.record_input(key_name, gs.turn_count)

        if key in MOVE_KEYS:
            dx, dy = MOVE_KEYS[key]
            turn_spent = player_move(gs, dx, dy)
        elif key == ord('>'):
            if gs.player.floor == MAX_FLOORS:
                boss_alive = any(e.boss and e.etype == "dread_lord" and e.is_alive()
                                for e in gs.enemies)
                if boss_alive:
                    gs.msg("The Dread Lord still lives!", C_RED)
                else:
                    gs.victory = True
                    gs.game_over = True
            else:
                if gs.tiles[gs.player.y][gs.player.x] == T_STAIRS_DOWN:
                    new_floor = gs.player.floor + 1
                    # Branch selection at branch floors
                    if new_floor in BRANCH_CHOICES and new_floor not in gs.branch_choices:
                        _show_branch_choice(scr, gs, new_floor)
                    # Floor transition message (Phase 3, item 17)
                    gs.msg(f"Descending to floor {new_floor}...", C_YELLOW)
                    render_game(scr, gs)
                    curses.napms(500)
                    gs.generate_floor(new_floor)
                    if gs.recorder:
                        gs.recorder.record_floor_change(gs)
                    # Boss floor warning (Phase 6, item 29)
                    if new_floor == MAX_FLOORS:
                        gs.msg("A terrible darkness fills this place...", C_RED)
                        gs.msg("The Dread Lord awaits.", C_RED)
                        render_game(scr, gs)
                        curses.napms(1000)
                    turn_spent = True
                else:
                    gs.msg("No stairs here.", C_WHITE)
        elif key == ord('<'):
            if gs.tiles[gs.player.y][gs.player.x] == T_STAIRS_UP:
                if gs.player.floor > 1:
                    new_floor = gs.player.floor - 1
                    gs.msg(f"Ascending to floor {new_floor}...", C_YELLOW)
                    render_game(scr, gs)
                    curses.napms(500)
                    gs.generate_floor(new_floor)
                    turn_spent = True
                else:
                    gs.msg("You can't leave yet.", C_WHITE)
            else:
                gs.msg("No stairs here.", C_WHITE)
        elif key == ord('.') or key == ord('5'):
            # Wait/rest one turn
            p = gs.player
            if p.hp < p.max_hp and p.hunger > B["rest_hunger_threshold"]:
                p.hp = min(p.max_hp, p.hp + B["rest_hp_per_turn"])
            p.hunger = max(0, p.hunger - B["rest_wait_hunger_cost"])
            turn_spent = True
        elif key == ord('i'):
            turn_spent = show_inventory(scr, gs)
        elif key == ord('c'):
            show_character(scr, gs)
        elif key == ord('C'):
            # Class ability
            turn_spent = use_class_ability(gs, scr)
        elif key == ord('?'):
            show_help(scr)
        elif key == ord('m'):
            show_messages(scr, gs)
        elif key == ord('j'):
            show_journal(scr, gs)
        elif key == ord('M'):
            show_bestiary(scr, gs)
        elif key == ord('$'):
            show_shop(scr, gs)
        elif key == ord('p'):
            if gs.tiles[gs.player.y][gs.player.x] == T_SHRINE:
                pray_at_shrine(gs)
                turn_spent = True
            else:
                gs.msg("Nothing to pray to here.", C_WHITE)
        elif key == ord('f'):
            turn_spent = fire_projectile(gs, scr)
        elif key == ord('z'):
            turn_spent = cast_spell_menu(gs, scr)
        elif key == ord('t'):
            turn_spent = use_technique_menu(gs, scr)
        elif key == ord('x'):
            # Look/examine mode (Phase 4, item 23)
            look_mode(gs, scr)
        elif key == 9:  # Tab key = auto-fight (Phase 4, item 20)
            gs.auto_fighting = True
            gs.auto_fight_target = None
            gs.msg("Auto-fighting...", C_YELLOW)
        elif key == ord('o'):
            # Auto-explore (Phase 4, item 21)
            gs.auto_exploring = True
            gs.msg("Exploring...", C_YELLOW)
        elif key == ord('R'):
            # Rest until healed (Phase 4, item 22)
            rest_until_healed(gs, scr)
        elif key == ord('S'):
            # Lifetime stats overlay
            show_lifetime_stats(scr)
        elif key == ord('a'):
            # Alchemy table (#7) or light pedestal (#9)
            px, py = gs.player.x, gs.player.y
            if gs.tiles[py][px] == T_ALCHEMY_TABLE:
                turn_spent = use_alchemy_table(gs)
            elif gs.tiles[py][px] == T_PEDESTAL_UNLIT:
                turn_spent = _interact_pedestal(gs, px, py)
            else:
                gs.msg("Nothing to interact with here.", C_DARK)
        elif key == ord('T'):
            # Toggle torch on/off to conserve fuel
            p = gs.player
            if p.torch_fuel <= 0:
                gs.msg("No torch fuel to light!", C_RED)
            else:
                p.torch_lit = not p.torch_lit
                if p.torch_lit:
                    gs.msg("You light your torch.", C_YELLOW)
                else:
                    gs.msg("You extinguish your torch to save fuel.", C_DARK)
        elif key == ord('Q'):
            # Save and quit (Phase 7, item 33)
            scr.erase()
            safe_addstr(scr, 10, 20, "Save and quit? (y/n/c)", curses.color_pair(C_YELLOW))
            safe_addstr(scr, 12, 20, "y=Save & Quit  n=Quit without saving  c=Cancel",
                       curses.color_pair(C_DARK))
            scr.refresh()
            while True:
                qk = scr.getch()
                if qk == ord('y') or qk == ord('Y'):
                    if save_game(gs):
                        gs.msg("Game saved.", C_GREEN)
                    gs.running = False
                    break
                elif qk == ord('n') or qk == ord('N'):
                    gs.running = False
                    break
                elif qk == ord('c') or qk == ord('C') or qk == 27:
                    break
        elif key == ord('q'):
            # Lowercase q hint (Phase 1, item 5)
            gs.msg("Press Q (shift) to quit.", C_DARK)
        elif key == ord('/'):
            # Search for traps
            _search_for_traps(gs)
            turn_spent = True
        elif key == ord('D'):
            # Disarm adjacent trap
            turn_spent = _disarm_trap(gs)
        elif key == ord(','):
            pickup = [i for i in gs.items if i.x == gs.player.x and i.y == gs.player.y]
            for item in pickup:
                if item.item_type == "gold":
                    gs.player.gold += item.data["amount"]
                    gs.msg(f"Picked up {item.data['amount']} gold.", C_GOLD)
                    gs.items.remove(item)
                else:
                    capacity_ok = (item.item_type == "scroll" or
                                   sum(1 for it in gs.player.inventory if it.item_type != "scroll") < gs.player.carry_capacity)
                    if capacity_ok:
                        gs.items.remove(item)
                        gs.player.inventory.append(item)
                        gs.player.items_found += 1
                        gs.msg(f"Picked up {item.display_name}.", item.color)
                    else:
                        gs.msg("Inventory full!", C_RED)
            # Grab adjacent wall torch (#1)
            if not pickup:
                grabbed_torch = False
                for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    tx, ty = gs.player.x + ddx, gs.player.y + ddy
                    if 0 <= tx < MAP_W and 0 <= ty < MAP_H and gs.tiles[ty][tx] == T_WALL_TORCH:
                        gs.tiles[ty][tx] = T_WALL
                        if (tx, ty) in gs.wall_torches:
                            gs.wall_torches.remove((tx, ty))
                        torch_item = Item(0, 0, "torch", "Torch", {"name": "Torch", "char": '(', "fuel": 60, "desc": "Taken from a wall."})
                        gs.player.inventory.append(torch_item)
                        gs.msg("You take a torch from the wall.", C_YELLOW)
                        grabbed_torch = True
                        break
                turn_spent = grabbed_torch or bool(pickup)
            else:
                turn_spent = bool(pickup)
        else:
            # Unknown command feedback (Phase 1, item 1)
            if key != -1 and key != 27:  # ignore resize events and ESC
                gs.msg("Unknown command. Press ? for help.", C_DARK)

        if turn_spent:
            gs.turn_count += 1
            # Stealth detection: check noise before enemies act
            if gs.last_noise > 0:
                _stealth_detection(gs, gs.last_noise)
            gs.last_noise = 0
            process_enemies(gs)
            process_status(gs)
            check_context_tips(gs)
            # Record state snapshot every 10 turns
            if gs.recorder and gs.turn_count % 10 == 0:
                gs.recorder.record_state_snapshot(gs)
            if gs.player.hp <= 0:
                gs.game_over = True

    render_game(scr, gs)
    replay_path = None
    if gs.recorder:
        replay_path = gs.recorder.filepath
    if gs.victory:
        if gs.recorder:
            gs.recorder.record_victory(gs)
            gs.recorder.close()
        show_enhanced_victory(scr, gs)
        delete_save()  # Permadeath: delete save on win too
    elif gs.game_over:
        if gs.recorder:
            gs.recorder.record_death(gs)
            gs.recorder.close()
        show_enhanced_death(scr, gs)
        delete_save()  # Permadeath: delete save on death
    # Auto-replay prompt (#3)
    if replay_path and os.path.exists(replay_path) and (gs.victory or gs.game_over):
        scr.erase()
        safe_addstr(scr, 10, 20, "Watch replay? (y/n)", curses.color_pair(C_YELLOW))
        scr.refresh()
        while True:
            rk = scr.getch()
            if rk == ord('y') or rk == ord('Y'):
                replay_session(scr, replay_path, speed=2.0)
                break
            elif rk == ord('n') or rk == ord('N') or rk == 27:
                break


def main(stdscr=None):
    if stdscr is None:
        curses.wrapper(game_loop)
    else:
        game_loop(stdscr)


# ============================================================
# SESSION RECORDING
# ============================================================

class SessionRecorder:
    """Records game events to a JSONL file for later replay."""

    def __init__(self, seed, player_name="Adventurer"):
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(RECORDINGS_DIR, f"{ts}_{seed}.jsonl")
        self._file = open(self.filepath, 'w')
        self._write({"event": "init", "seed": seed, "version": 1,
                      "date": ts, "player_name": player_name})
        self._turn = 0

    def _write(self, data):
        self._file.write(json.dumps(data, separators=(',', ':')) + '\n')

    def record(self, event_type, data=None):
        entry = {"event": event_type, "turn": self._turn}
        if data:
            entry.update(data)
        self._write(entry)

    def record_input(self, key_name, turn):
        self._turn = turn
        self._write({"event": "input", "key": key_name, "turn": turn})

    def record_state_snapshot(self, gs):
        p = gs.player
        self._write({"event": "state_snapshot", "turn": gs.turn_count,
                      "hp": p.hp, "max_hp": p.max_hp, "mana": p.mana,
                      "hunger": round(p.hunger, 1), "floor": p.floor,
                      "x": p.x, "y": p.y, "kills": p.kills, "gold": p.gold,
                      "level": p.level, "inventory_count": len(p.inventory)})

    def record_floor_change(self, gs):
        self._write({"event": "floor_change", "turn": gs.turn_count,
                      "floor": gs.player.floor,
                      "enemies": len(gs.enemies), "items": len(gs.items)})

    def record_combat(self, enemy_name, damage, result):
        self._write({"event": "combat", "turn": self._turn,
                      "enemy": enemy_name, "damage": damage, "result": result})

    def record_death(self, gs):
        p = gs.player
        self._write({"event": "death", "turn": gs.turn_count,
                      "cause": gs.death_cause or "unknown",
                      "floor": p.floor, "score": calculate_score(p, gs)})

    def record_victory(self, gs):
        p = gs.player
        self._write({"event": "victory", "turn": gs.turn_count,
                      "floor": p.floor, "score": calculate_score(p, gs)})

    def close(self):
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()


def list_recordings():
    """List saved recording files with metadata."""
    if not os.path.isdir(RECORDINGS_DIR):
        print("No recordings found.")
        return
    files = sorted(Path(RECORDINGS_DIR).glob("*.jsonl"), reverse=True)
    if not files:
        print("No recordings found.")
        return
    print(f"{'#':<4} {'Date':<20} {'Seed':<12} {'Result':<10} {'Floor':<6} {'Score':<8} {'File'}")
    print("-" * 85)
    for i, f in enumerate(files[:20]):
        try:
            with open(f, 'r') as fh:
                first = json.loads(fh.readline())
                # Read last line for result
                fh.seek(0)
                lines = fh.readlines()
                last = json.loads(lines[-1]) if lines else {}
            date = first.get("date", "?")
            seed = first.get("seed", "?")
            result = last.get("event", "?")
            floor = last.get("floor", "?")
            score = last.get("score", "?")
            print(f"{i+1:<4} {date:<20} {seed:<12} {result:<10} {floor:<6} {score:<8} {f.name}")
        except Exception:
            print(f"{i+1:<4} {'error reading':<20} {f.name}")


# ============================================================
# SESSION REPLAY
# ============================================================

def replay_session(scr, filepath, speed=1.0):
    """Replay a recorded session visually in the terminal."""
    curses.curs_set(0)
    scr.nodelay(False)
    scr.keypad(True)
    init_colors()

    with open(filepath, 'r') as f:
        lines = f.readlines()
    if not lines:
        return

    init_event = json.loads(lines[0])
    seed = init_event.get("seed", 0)

    # Collect all input events
    input_events = []
    for line in lines[1:]:
        evt = json.loads(line)
        if evt.get("event") == "input":
            input_events.append(evt)

    # Recreate the game with the same seed
    gs = GameState(seed=seed)
    gs._scr = scr
    _init_new_game(gs)

    MOVE_KEYS_BY_NAME = {
        'UP': (0,-1), 'DOWN': (0,1), 'LEFT': (-1,0), 'RIGHT': (1,0),
        'w': (0,-1), 's': (0,1), 'a': (-1,0), 'd': (1,0),
        'h': (-1,0), 'j': (0,1), 'k': (0,-1), 'l': (1,0),
        'y': (-1,-1), 'u': (1,-1), 'b': (-1,1), 'n': (1,1),
    }

    total = len(input_events)
    paused = False
    idx = 0
    base_delay = max(10, int(80 / speed))

    while idx < total and gs.running and not gs.game_over:
        if paused:
            scr.nodelay(False)
            key = scr.getch()
            if key == ord(' '):
                paused = False
            elif key == ord('q'):
                break
            continue

        evt = input_events[idx]
        key_name = evt.get("key", "")
        turn_spent = False

        if key_name in MOVE_KEYS_BY_NAME:
            dx, dy = MOVE_KEYS_BY_NAME[key_name]
            turn_spent = player_move(gs, dx, dy)
        elif key_name == '>':
            if gs.tiles[gs.player.y][gs.player.x] == T_STAIRS_DOWN:
                if gs.player.floor < MAX_FLOORS:
                    new_floor = gs.player.floor + 1
                    if new_floor in BRANCH_CHOICES and new_floor not in gs.branch_choices:
                        _choose_branch_headless(gs, new_floor)
                    gs.generate_floor(new_floor)
                    turn_spent = True
                elif not any(e.boss and e.etype == "dread_lord" and e.is_alive() for e in gs.enemies):
                    gs.victory = True
                    gs.game_over = True
        elif key_name == '.':
            p = gs.player
            if p.hp < p.max_hp and p.hunger > B["rest_hunger_threshold"]:
                p.hp = min(p.max_hp, p.hp + B["rest_hp_per_turn"])
            p.hunger = max(0, p.hunger - B["rest_wait_hunger_cost"])
            turn_spent = True
        elif key_name == ',':
            pickup = [i for i in gs.items if i.x == gs.player.x and i.y == gs.player.y]
            for item in pickup:
                if item.item_type == "gold":
                    gs.player.gold += item.data["amount"]
                    gs.items.remove(item)
                elif len(gs.player.inventory) < gs.player.carry_capacity:
                    gs.items.remove(item)
                    gs.player.inventory.append(item)
                    gs.player.items_found += 1
            turn_spent = bool(pickup)

        if turn_spent:
            gs.turn_count += 1
            if gs.last_noise > 0:
                _stealth_detection(gs, gs.last_noise)
            gs.last_noise = 0
            process_enemies(gs)
            process_status(gs)
            if gs.player.hp <= 0:
                gs.game_over = True

        # Render with replay overlay
        fov_radius = gs.player.get_torch_radius()
        if "Blindness" in gs.player.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        render_game(scr, gs)
        # Overlay
        progress = f"REPLAY [{idx+1}/{total}] Speed: {speed:.1f}x  [Space]=Pause [q]=Quit [+/-]=Speed"
        safe_addstr(scr, SCREEN_H - 1, 0, progress[:SCREEN_W-1],
                   curses.color_pair(C_CYAN) | curses.A_BOLD)
        scr.refresh()

        idx += 1

        # Check for user input (non-blocking)
        scr.nodelay(True)
        ck = scr.getch()
        scr.nodelay(False)
        if ck == ord('q'):
            break
        elif ck == ord(' '):
            paused = True
        elif ck == ord('+') or ck == ord('='):
            speed = min(16.0, speed * 2)
            base_delay = max(10, int(80 / speed))
        elif ck == ord('-'):
            speed = max(0.25, speed / 2)
            base_delay = max(10, int(80 / speed))

        curses.napms(base_delay)

    # Show final state
    render_game(scr, gs)
    msg = "REPLAY COMPLETE" if idx >= total else "REPLAY STOPPED"
    safe_addstr(scr, SCREEN_H - 1, 0, f"{msg} - Press any key",
               curses.color_pair(C_YELLOW) | curses.A_BOLD)
    scr.refresh()
    scr.nodelay(False)
    scr.getch()


# ============================================================
# BOT PLAYER (AI Auto-Play)
# ============================================================

class BotPlayer:
    """AI bot that plays the game using a priority-based decision tree."""

    def __init__(self):
        self.strategy = "INIT"
        self.target_desc = ""
        self.items_used = 0
        self.potions_saved = 0
        self.decisions = 0
        self._explore_target = None  # Committed exploration target (x, y)
        self._explore_stuck = 0      # Counter for detecting oscillation
        self._last_positions = []     # Recent positions for loop detection
        self._floor_tiles_visited = set()  # Unique tiles visited on current floor
        self._floor_start_turn = 0         # Turn when we entered this floor
        self._current_floor = 0            # Track floor for reset

    def decide(self, gs):
        """Returns (action, params) tuple. Deterministic given same state."""
        self.decisions += 1
        p = gs.player

        # Paralysis: can't do anything, just wait
        if "Paralysis" in p.status_effects:
            self.strategy = "PARALYZED"
            self.target_desc = "can't move"
            return ("rest", {})

        # Fear: move away from enemies (can't approach them)
        if "Fear" in p.status_effects:
            flee_dir = self._flee_direction(gs)
            if flee_dir:
                self.strategy = "FEARED"
                self.target_desc = "fleeing in terror"
                return ("move", {"dx": flee_dir[0], "dy": flee_dir[1]})
            self.strategy = "FEARED"
            self.target_desc = "cowering"
            return ("rest", {})

        # Confusion: movement is randomized, just try to move
        if "Confusion" in p.status_effects:
            self.strategy = "CONFUSED"
            self.target_desc = "stumbling"
            dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
            return ("move", {"dx": dx, "dy": dy})

        # Floor change detection — reset per-floor tracking
        if p.floor != self._current_floor:
            self._current_floor = p.floor
            self._floor_tiles_visited = set()
            self._floor_start_turn = gs.turn_count
            self._explore_target = None
            self._explore_stuck = 0

        # Track unique tiles visited on this floor
        self._floor_tiles_visited.add((p.x, p.y))

        # Loop detection: track last 6 positions, detect oscillation
        self._last_positions.append((p.x, p.y))
        if len(self._last_positions) > 6:
            self._last_positions.pop(0)
        if len(self._last_positions) >= 6:
            unique = set(self._last_positions)
            if len(unique) <= 2:
                self._explore_stuck += 1
                self._explore_target = None  # Force new target
            else:
                self._explore_stuck = 0

        # --- Layer 1: Survival ---
        hp_pct = p.hp / p.max_hp if p.max_hp > 0 else 0
        hunger_pct = p.hunger

        # Urgent heal if poisoned and HP getting low
        if "Poison" in p.status_effects and hp_pct < 0.5:
            for item in p.inventory:
                if item.item_type == "potion" and item.identified and item.data.get("effect") == "Healing":
                    self.strategy = "HEAL"
                    self.target_desc = "poisoned! healing"
                    return ("use_item", {"item": item, "type": "potion"})
            if p.mana >= SPELLS["Heal"]["cost"]:
                self.strategy = "HEAL"
                self.target_desc = "poisoned! heal spell"
                return ("cast_spell", {"spell": "Heal"})

        # Heal if HP < 40%
        if hp_pct < 0.4:
            # Try healing potion
            for item in p.inventory:
                if item.item_type == "potion":
                    if item.identified and item.data.get("effect") == "Healing":
                        self.strategy = "HEAL"
                        self.target_desc = "potion"
                        return ("use_item", {"item": item, "type": "potion"})
                    elif not item.identified and hp_pct < 0.25:
                        self.strategy = "HEAL"
                        self.target_desc = "unknown potion (desperate)"
                        return ("use_item", {"item": item, "type": "potion"})
            # Try Heal spell
            if p.mana >= SPELLS["Heal"]["cost"]:
                self.strategy = "HEAL"
                self.target_desc = "spell"
                return ("cast_spell", {"spell": "Heal"})
            # Eat food if it restores some HP via hunger
            if hunger_pct < 60:
                for item in p.inventory:
                    if item.item_type == "food":
                        self.strategy = "HEAL"
                        self.target_desc = "food"
                        return ("use_item", {"item": item, "type": "food"})
            # Rest if no enemies visible and hunger ok
            if hunger_pct > 30 and not self._enemies_visible(gs):
                self.strategy = "REST"
                self.target_desc = "resting"
                return ("rest", {})

        # Eat food if hunger < 30%
        if hunger_pct < 30:
            for item in p.inventory:
                if item.item_type == "food":
                    self.strategy = "EAT"
                    self.target_desc = item.display_name
                    return ("use_item", {"item": item, "type": "food"})

        # Equip better gear immediately
        equip_action = self._check_equipment_upgrade(gs)
        if equip_action:
            return equip_action

        # Flee if HP < 20% and enemies visible
        if hp_pct < 0.2 and self._enemies_visible(gs):
            flee_dir = self._flee_direction(gs)
            if flee_dir:
                self.strategy = "FLEE"
                self.target_desc = "running away"
                return ("move", {"dx": flee_dir[0], "dy": flee_dir[1]})

        # --- Layer 2: Combat ---
        nearest_enemy = self._nearest_visible_enemy(gs)
        if nearest_enemy:
            dist = abs(nearest_enemy.x - p.x) + abs(nearest_enemy.y - p.y)

            # Warrior: Whirlwind when 3+ adjacent enemies
            if (p.player_class == "warrior" and "Whirlwind" in p.known_abilities
                    and p.mana >= B["whirlwind_cost"]):
                adj_count = sum(1 for e in gs.enemies
                               if e.is_alive() and abs(e.x - p.x) <= 1 and abs(e.y - p.y) <= 1
                               and (e.x != p.x or e.y != p.y))
                if adj_count >= 3:
                    self.strategy = "COMBAT"
                    self.target_desc = f"whirlwind ({adj_count} adjacent)"
                    return ("use_ability", {"ability": "Whirlwind"})

            # Warrior: Shield Wall when HP < 30% and no heal available
            if (p.player_class == "warrior" and "Shield Wall" in p.known_abilities
                    and p.mana >= B["shield_wall_cost"] and "Shield Wall" not in p.status_effects
                    and hp_pct < 0.3):
                has_heal = any(it.item_type == "potion" and it.identified and it.data.get("effect") == "Healing"
                              for it in p.inventory)
                if not has_heal:
                    self.strategy = "COMBAT"
                    self.target_desc = "shield wall (low HP)"
                    return ("use_ability", {"ability": "Shield Wall"})

            # Rogue: Backstab before engaging bosses
            if (p.player_class == "rogue" and "Backstab" in p.known_abilities
                    and p.mana >= B["backstab_cost"] and nearest_enemy.boss
                    and "Backstab" not in p.status_effects):
                self.strategy = "COMBAT"
                self.target_desc = f"backstab -> {nearest_enemy.name}"
                return ("use_ability", {"ability": "Backstab"})

            # Rogue: Smoke Bomb when HP < 30% and 2+ enemies visible
            if (p.player_class == "rogue" and "Smoke Bomb" in p.known_abilities
                    and p.mana >= B["smoke_bomb_cost"] and hp_pct < 0.3):
                visible_count = sum(1 for e in gs.enemies
                                   if e.is_alive() and (e.x, e.y) in gs.visible)
                if visible_count >= 2:
                    self.strategy = "COMBAT"
                    self.target_desc = f"smoke bomb ({visible_count} visible)"
                    return ("use_ability", {"ability": "Smoke Bomb"})

            # Ranged attack if enemy > 2 tiles away
            if dist > 2:
                # Try wand
                for item in p.inventory:
                    if item.item_type == "wand" and item.data.get("charges", 0) > 0:
                        dx = 1 if nearest_enemy.x > p.x else (-1 if nearest_enemy.x < p.x else 0)
                        dy = 1 if nearest_enemy.y > p.y else (-1 if nearest_enemy.y < p.y else 0)
                        if dx != 0 or dy != 0:
                            self.strategy = "COMBAT"
                            self.target_desc = f"wand -> {nearest_enemy.name}"
                            return ("fire", {"dx": dx, "dy": dy})
                # Try bow
                if p.bow:
                    for item in p.inventory:
                        if item.item_type == "arrow" and item.count > 0:
                            dx = 1 if nearest_enemy.x > p.x else (-1 if nearest_enemy.x < p.x else 0)
                            dy = 1 if nearest_enemy.y > p.y else (-1 if nearest_enemy.y < p.y else 0)
                            if dx != 0 or dy != 0:
                                self.strategy = "COMBAT"
                                self.target_desc = f"arrow -> {nearest_enemy.name}"
                                return ("fire", {"dx": dx, "dy": dy})

            # Mage: Cast Chain Lightning on 2+ visible enemies
            if (p.player_class == "mage" and "Chain Lightning" in p.known_spells
                    and p.mana >= SPELLS["Chain Lightning"]["cost"] and p.mana > p.max_mana * 0.5):
                visible_enemies = sum(1 for e in gs.enemies
                                     if e.is_alive() and (e.x, e.y) in gs.visible)
                if visible_enemies >= 2:
                    self.strategy = "COMBAT"
                    self.target_desc = f"chain lightning ({visible_enemies} visible)"
                    return ("cast_spell", {"spell": "Chain Lightning", "target": nearest_enemy})

            # Cast Fireball on 2+ clustered enemies
            if ("Fireball" in p.known_spells and p.mana >= SPELLS["Fireball"]["cost"]
                    and p.mana > p.max_mana * 0.5):
                clustered = sum(1 for e in gs.enemies
                               if e.is_alive() and (e.x, e.y) in gs.visible
                               and abs(e.x - nearest_enemy.x) + abs(e.y - nearest_enemy.y) <= 2)
                if clustered >= 2:
                    self.strategy = "COMBAT"
                    self.target_desc = f"fireball ({clustered} targets)"
                    dx = 1 if nearest_enemy.x > p.x else (-1 if nearest_enemy.x < p.x else 0)
                    dy = 1 if nearest_enemy.y > p.y else (-1 if nearest_enemy.y < p.y else 0)
                    return ("cast_spell", {"spell": "Fireball", "dx": dx, "dy": dy})

            # Cast Freeze on bosses
            if ("Freeze" in p.known_spells and nearest_enemy.boss
                    and p.mana >= SPELLS["Freeze"]["cost"] and nearest_enemy.frozen_turns <= 0):
                self.strategy = "COMBAT"
                self.target_desc = f"freeze -> {nearest_enemy.name}"
                return ("cast_spell", {"spell": "Freeze", "target": nearest_enemy})

            # Melee: auto-fight step (move toward or attack)
            if dist == 1:
                self.strategy = "COMBAT"
                self.target_desc = nearest_enemy.name
                return ("move", {"dx": nearest_enemy.x - p.x, "dy": nearest_enemy.y - p.y})
            else:
                step = astar(gs.tiles, p.x, p.y, nearest_enemy.x, nearest_enemy.y, max_steps=30)
                if step:
                    self.strategy = "COMBAT"
                    self.target_desc = f"approaching {nearest_enemy.name}"
                    return ("move", {"dx": step[0], "dy": step[1]})

        # --- Layer 3: Exploration ---
        # Pick up items on current tile
        items_here = [i for i in gs.items if i.x == p.x and i.y == p.y]
        if items_here:
            self.strategy = "LOOT"
            self.target_desc = "pickup"
            return ("pickup", {})

        # Pray at shrine if HP > 60%
        if gs.tiles[p.y][p.x] == T_SHRINE and hp_pct > 0.6:
            self.strategy = "EXPLORE"
            self.target_desc = "praying"
            return ("pray", {})

        # Descend stairs when floor is explored enough
        if gs.tiles[p.y][p.x] == T_STAIRS_DOWN:
            explored_pct = self._floor_explored_pct(gs)
            if explored_pct > 0.4 or (explored_pct > 0.2 and hp_pct > 0.5):
                self.strategy = "DESCEND"
                self.target_desc = f"floor {p.floor + 1}"
                return ("descend", {})

        # After 150+ turns on a floor, prioritize finding stairs
        if gs.turn_count > 150 * p.floor and p.floor < MAX_FLOORS:
            sx, sy = gs.stair_down
            if gs.tiles[sy][sx] == T_STAIRS_DOWN:
                step = astar(gs.tiles, p.x, p.y, sx, sy, max_steps=80)
                if step:
                    self.strategy = "DESCEND"
                    self.target_desc = "urgently seeking stairs"
                    return ("move", {"dx": step[0], "dy": step[1]})
            elif gs.tiles[sy][sx] == T_STAIRS_LOCKED:
                # Stairs are locked — keep exploring (walk on switches naturally)
                self.strategy = "EXPLORE"
                self.target_desc = "stairs locked, exploring"
                # Don't try to pathfind to locked stairs

        # Auto-explore with committed target (prevents oscillation)
        # Invalidate target if we reached it or it's now explored
        if self._explore_target:
            tx, ty = self._explore_target
            if (p.x == tx and p.y == ty) or gs.explored[ty][tx]:
                self._explore_target = None

        # If stuck in a loop, pick a random walkable neighbor to break out
        if self._explore_stuck >= 3:
            self._explore_stuck = 0
            self._explore_target = None
            neighbors = []
            for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1),(1,1),(1,-1),(-1,1),(-1,-1)]:
                nx, ny = p.x + ddx, p.y + ddy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
                    if not any(e.x == nx and e.y == ny and e.is_alive() for e in gs.enemies):
                        neighbors.append((ddx, ddy))
            if neighbors:
                # Pick the neighbor closest to stairs to make progress
                sx, sy = gs.stair_down
                neighbors.sort(key=lambda d: abs(p.x+d[0]-sx) + abs(p.y+d[1]-sy))
                dx, dy = neighbors[0]
                self.strategy = "UNSTICK"
                self.target_desc = "breaking loop"
                return ("move", {"dx": dx, "dy": dy})

        if not self._explore_target:
            self._explore_target = _bfs_unexplored(gs)

        if self._explore_target:
            tx, ty = self._explore_target
            step = astar(gs.tiles, p.x, p.y, tx, ty, max_steps=50)
            if step:
                self.strategy = "EXPLORE"
                self.target_desc = "unexplored"
                return ("move", {"dx": step[0], "dy": step[1]})
            else:
                self._explore_target = None  # Unreachable, pick new target

        # Find stairs if fully explored
        sx, sy = gs.stair_down
        if gs.tiles[sy][sx] == T_STAIRS_DOWN and p.floor < MAX_FLOORS:
            step = astar(gs.tiles, p.x, p.y, sx, sy, max_steps=80)
            if step:
                self.strategy = "DESCEND"
                self.target_desc = "heading to stairs"
                return ("move", {"dx": step[0], "dy": step[1]})

        # Floor-level stall detection: if 500+ turns on this floor and barely moving,
        # bias movement toward stairs coordinates (random walk, not pathfind)
        floor_turns = gs.turn_count - self._floor_start_turn
        if floor_turns > 500 and len(self._floor_tiles_visited) < 30:
            sx, sy = gs.stair_down
            dx = 1 if sx > p.x else (-1 if sx < p.x else 0)
            dy = 1 if sy > p.y else (-1 if sy < p.y else 0)
            # Try biased direction first, then any walkable neighbor
            for ddx, ddy in [(dx, dy), (dx, 0), (0, dy), (-dx, 0), (0, -dy)]:
                if ddx == 0 and ddy == 0:
                    continue
                nx, ny = p.x + ddx, p.y + ddy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
                    self.strategy = "FORCE_MOVE"
                    self.target_desc = "stall break, toward stairs"
                    return ("move", {"dx": ddx, "dy": ddy})

        # --- Layer 4: Resource Management ---
        # Toggle torch
        if p.torch_lit and not self._enemies_visible(gs) and p.torch_fuel < TORCH_MAX_FUEL * 0.25:
            self.strategy = "MANAGE"
            self.target_desc = "conserve torch"
            return ("toggle_torch", {})
        if not p.torch_lit and self._enemies_visible(gs) and p.torch_fuel > 0:
            self.strategy = "MANAGE"
            self.target_desc = "light torch"
            return ("toggle_torch", {})

        # Fallback: wait
        self.strategy = "WAIT"
        self.target_desc = "waiting"
        return ("rest", {})

    def _enemies_visible(self, gs):
        return any(e.is_alive() and (e.x, e.y) in gs.visible and not e.disguised for e in gs.enemies)

    def _nearest_visible_enemy(self, gs):
        p = gs.player
        nearest = None
        nd = 999
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                d = abs(e.x - p.x) + abs(e.y - p.y)
                if d < nd:
                    nd = d
                    nearest = e
        return nearest

    def _flee_direction(self, gs):
        """Move away from nearest enemy."""
        p = gs.player
        nearest = self._nearest_visible_enemy(gs)
        if not nearest:
            return None
        # Move in opposite direction
        dx = -1 if nearest.x > p.x else (1 if nearest.x < p.x else 0)
        dy = -1 if nearest.y > p.y else (1 if nearest.y < p.y else 0)
        nx, ny = p.x + dx, p.y + dy
        if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
            return (dx, dy)
        # Try cardinal directions
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = p.x + ddx, p.y + ddy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] in WALKABLE:
                if not any(e.x == nx and e.y == ny and e.is_alive() for e in gs.enemies):
                    return (ddx, ddy)
        return None

    def _check_equipment_upgrade(self, gs):
        """Check if we have better unequipped gear."""
        p = gs.player
        for item in p.inventory:
            if item.equipped:
                continue
            if item.item_type == "weapon":
                if not p.weapon or item.data.get("dmg", (0,0))[1] > p.weapon.data.get("dmg", (0,0))[1]:
                    self.strategy = "EQUIP"
                    self.target_desc = item.display_name
                    return ("equip", {"item": item})
            elif item.item_type == "armor":
                if not p.armor or item.data.get("defense", 0) > p.armor.data.get("defense", 0):
                    self.strategy = "EQUIP"
                    self.target_desc = item.display_name
                    return ("equip", {"item": item})
            elif item.item_type == "ring" and not p.ring:
                if item.data.get("effect") != "hunger":  # Don't equip cursed ring
                    self.strategy = "EQUIP"
                    self.target_desc = item.display_name
                    return ("equip", {"item": item})
            elif item.item_type == "bow":
                if not p.bow or item.data.get("dmg", (0,0))[1] > p.bow.data.get("dmg", (0,0))[1]:
                    self.strategy = "EQUIP"
                    self.target_desc = item.display_name
                    return ("equip", {"item": item})
        return None

    def _floor_explored_pct(self, gs):
        explored = sum(1 for row in gs.explored for c in row if c)
        total = count_walkable(gs.tiles)
        return explored / total if total > 0 else 1.0


def _update_explored_from_fov(gs):
    """Mark all visible tiles as explored (needed for headless/bot mode)."""
    for (mx, my) in gs.visible:
        if 0 <= mx < MAP_W and 0 <= my < MAP_H:
            gs.explored[my][mx] = True


# ============================================================
# AGENT PLAYER — Claude-powered hybrid AI
# ============================================================

class FeatureTracker:
    """Track which game features the agent encounters and interacts with."""

    def __init__(self):
        self.features = {
            "puzzle_torch": {"encountered": False, "solved": False},
            "puzzle_switch": {"encountered": False, "solved": False},
            "puzzle_locked": {"encountered": False, "solved": False},
            "alchemy_table": {"encountered": False, "used": False},
            "journal": {"opened": False, "entries": 0},
            "wall_torch": {"encountered": False, "grabbed": False},
            "boss_weapon_drop": {"dropped": False, "equipped": False},
            "lifesteal": {"triggered": False, "total_healed": 0},
            "shop": {"encountered": False, "bought": False},
            "shrine": {"encountered": False, "prayed": False},
            "wand_used": {"used": False},
        }
        self.classes_played = set()
        self.spells_cast = set()
        self.abilities_used = set()

    def check_state(self, gs, action_str=""):
        """Call every turn to update tracking."""
        p = gs.player
        tile = gs.tiles[p.y][p.x]

        if tile == T_ALCHEMY_TABLE:
            self.features["alchemy_table"]["encountered"] = True
        if tile in (T_PEDESTAL_UNLIT, T_PEDESTAL_LIT):
            self.features["puzzle_torch"]["encountered"] = True
        if tile in (T_SWITCH_OFF, T_SWITCH_ON):
            self.features["puzzle_switch"]["encountered"] = True
        if tile == T_STAIRS_LOCKED:
            self.features["puzzle_locked"]["encountered"] = True

        for puzzle in gs.puzzles:
            if puzzle["solved"]:
                ptype = puzzle["type"]
                key = f"puzzle_{ptype}" if f"puzzle_{ptype}" in self.features else None
                if key:
                    self.features[key]["solved"] = True

        if gs.journal:
            self.features["journal"]["entries"] = len(gs.journal)
        if gs.wall_torches:
            self.features["wall_torch"]["encountered"] = True

        # Track action-based features
        if action_str in ("use_alchemy", "alchemy", "identify"):
            self.features["alchemy_table"]["used"] = True
        if action_str in ("grab_wall_torch", "grab_torch"):
            self.features["wall_torch"]["grabbed"] = True
        if action_str in ("open_journal", "journal"):
            self.features["journal"]["opened"] = True

        # Boss weapon
        if p.weapon and p.weapon.data.get("boss_drop"):
            self.features["boss_weapon_drop"]["equipped"] = True

        # Shop/shrine
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = p.x + ddx, p.y + ddy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] == T_SHOP_FLOOR:
                self.features["shop"]["encountered"] = True

    def coverage_pct(self):
        """Return overall feature coverage as a percentage."""
        total = 0
        covered = 0
        for val in self.features.values():
            for subval in val.values():
                if isinstance(subval, bool):
                    total += 1
                    if subval:
                        covered += 1
        return covered / total if total > 0 else 0

    def report(self):
        """Return human-readable feature coverage report."""
        lines = ["FEATURE COVERAGE REPORT", "=" * 40]
        for key, val in sorted(self.features.items()):
            parts = []
            for k, v in val.items():
                if isinstance(v, bool):
                    parts.append(f"{k}:{'YES' if v else 'no'}")
                else:
                    parts.append(f"{k}:{v}")
            lines.append(f"  {key:25s} {' | '.join(parts)}")
        lines.append(f"\n  Coverage: {self.coverage_pct():.0%}")
        if self.classes_played:
            lines.append(f"  Classes: {', '.join(sorted(self.classes_played))}")
        if self.spells_cast:
            lines.append(f"  Spells: {', '.join(sorted(self.spells_cast))}")
        if self.abilities_used:
            lines.append(f"  Abilities: {', '.join(sorted(self.abilities_used))}")
        return "\n".join(lines)


AGENT_SYSTEM_PROMPT = """Roguelike AI. Respond ONLY with JSON: {"action":"<act>","reason":"<short>"}
Actions: move_north/south/east/west/ne/nw/se/sw, attack, fire_north/south/east/west, cast_heal, cast_fireball_<dir>, cast_freeze, cast_lightning_<dir>, cast_teleport, cast_chain_lightning, cast_meteor_<dir>, cast_mana_shield, use_whirlwind, use_cleaving_strike, use_shield_wall, use_backstab, use_poison_blade, use_smoke_bomb, use_potion, eat_food, equip <name>, descend, rest, wait, pickup, pray, toggle_torch, use_alchemy, light_pedestal, grab_wall_torch, search_traps, disarm_trap
Combat: Flee HP<20%. Eat hunger<30%. Fireball groups (fire element). Freeze bosses. Chain Lightning 2+ (lightning). Meteor big AoE (fire). Mana Shield tough fights. Whirlwind 3+ adj. Shield Wall low HP. Backstab bosses. Smoke Bomb escape.
Explore: 40%+ before descend. Conserve torch/arrows.
Puzzles: F4+ may have puzzles. Pedestals(*) step on+light_pedestal(costs torch). Switches walk over to toggle. All ON=solved=reward. Locked stairs(X) toggle switches to unlock. Always solve for loot.
Alchemy: Tables(&) F2,5,8,11,14. Step on+use_alchemy=identify 1 potion/scroll. Use before drinking unknowns. Single use.
Wall torches: ! on walls. grab_wall_torch when adjacent=torch fuel. Light radius 5.
Boss weapons: Unique drops. Vampiric Blade=lifesteal 20%. Always equip.
Wands: Mage+50%dmg+2range. Warrior-25%. Prioritize as Mage.
Scrolls: Don't count toward capacity. Always pick up.
Traps: Hidden traps trigger on step. search_traps reveals adjacent. disarm_trap (Rogue bonus). Visible(^) traps safe to walk over. Enemies trigger traps too — lure them!
Resistances: Rings grant fire/cold/poison resist (50% reduction). Some enemies resist/vulnerable to elements. Fire suppresses Troll regen. Use element advantage.
Environment: Water blocks fire aura. Lightning in water=AoE. Lava passable with fire/cold resist (-2HP/step). Enemies flee when wounded (chase them down).
Stealth: Enemies spawn asleep(z) or unwary. Asleep=skip turns, unwary=patrol only. Movement makes noise (corridors=1, floor=2, doors=4, combat=8, spells=6). Rogue=50% less noise. Noise wakes sleeping enemies nearby. Attacking asleep/unwary=guaranteed crit (2x asleep, 1.5x unwary). Rogue class is ideal for stealth play.
Branches: At floor 5 and 10, path branches. Each branch has themed enemies, terrain, and a mini-boss guardian. Flooded Crypts=more water, undead. Burning Pits=lava, fire enemies. Mind Halls=psychic enemies, paralyze. Beast Warrens=fast beasts. Branch choice is permanent for that run. Adapt strategy to branch hazards.
Bestiary: Monster Memory tracks encounters, kills, abilities for each enemy type. Use past knowledge to choose tactics.
Stuck: If you're stuck (repeating same positions), try a different direction. Move toward unexplored areas (shown as ?) or toward stairs (>). If on a puzzle floor, look for switches or pedestals. Cast teleport to escape dead ends."""

CLAUDE_BIN = "/Users/will/.local/bin/claude"

# Direction mappings for action parsing
_DIR_MAP = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
    "ne": (1, -1), "nw": (-1, -1), "se": (1, 1), "sw": (-1, 1),
    "n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0),
}


class AgentPlayer:
    """Hybrid AI: BotPlayer for routine turns, Claude (Haiku) for tactical decisions."""

    def __init__(self, game_id=1):
        self.bot = BotPlayer()  # Fallback for non-triggered turns
        self.strategy = "INIT"
        self.target_desc = ""
        self.reason = ""        # Last Claude reasoning
        self.claude_calls = 0
        self.total_latency = 0.0
        self.fallbacks = 0
        self.items_used = 0
        self._thinking = False   # True while waiting for Claude
        self._last_floor = 0
        self._last_call_latency = 0.0  # Latency of most recent Claude call
        self._consulted_shop = False    # Only consult Claude about shop once per floor
        self._consulted_shrine = False  # Only consult Claude about shrine once per floor
        self._consulted_locked_stairs = False
        self._seen_wall_torch = False
        self._last_consult_turn = 0     # Cooldown: min turns between non-critical calls
        self._last_state_hash = None    # State dedup: skip if unchanged
        # --- Health monitoring ---
        self._health_interval = 10          # Check every N turns
        self._health_warnings = []          # Accumulated warnings
        self._window_calls = 0              # Claude calls in current window
        self._window_start_turn = 0         # Turn at start of current window
        self._floor_start_turn = 0          # Turn when current floor started
        self._action_window = deque(maxlen=20)  # Recent actions for distribution check
        self._hp_samples = deque(maxlen=10)     # Recent HP readings for trend
        self._trigger_counts = {}           # Track what's triggering Claude calls
        # --- Stuck detection ---
        self._position_history = deque(maxlen=20)  # Last 20 positions
        self._last_stuck_turn = 0                  # Turn when last stuck trigger fired
        self._game_id = game_id
        self._log_file = None
        # --- Agent-commons integration ---
        if HAS_AGENT_COMMONS:
            log_dir = os.path.expanduser("~/.depths_of_dread_agent_traces")
            os.makedirs(log_dir, exist_ok=True)
            trace_path = os.path.join(log_dir, f"game_{game_id}.jsonl")
            self._ac_trace = DecisionTrace(trace_path)
            self._ac_snapshots = StateSnapshotManager(
                snapshot_dir=log_dir, every_n_turns=25)
            self._ac_actions = ActionDistribution()
            self._ac_stall = ProgressStallDetector(threshold=20)
            self._ac_rep = ActionRepetitionDetector(window=20, repeat_threshold=5)
            self._ac_coverage = FeatureCoverageTracker()
            self._ac_coverage.register_features(DREAD_FEATURES)
            self._ac_novelty = NoveltySeekerBias(weight=0.3)
            self._ac_budget = CallBudgetManager(per_game=300, per_batch=1800)
            self._ac_validator = StructuredOutputValidator()
            self._ac_recovery = StallRecoveryManager(
                valid_actions=["move_north", "move_south", "move_east", "move_west",
                               "attack", "wait", "use_potion", "descend"])
            self._ac_dedup = TriggerDeduplicator()
            for trig, cd, crit in [
                ("enemies_visible", 0, False), ("low_hp", 3, True),
                ("boss", 0, True), ("new_floor", 0, True),
                ("shop", 10, False), ("shrine", 10, False),
                ("alchemy_table", 0, False), ("pedestal", 0, False),
                ("locked_stairs", 0, False), ("wall_torch", 10, False),
                ("stuck", 0, True), ("inventory_full", 5, False),
            ]:
                self._ac_dedup.register_trigger(trig, cooldown_turns=cd, critical=crit)
        else:
            self._ac_trace = None

    def _open_log(self):
        """Open the agent log file for real-time JSONL streaming."""
        if self._log_file is None:
            self._log_file = open(AGENT_LOG_PATH, 'a')

    def _log(self, event_type, data=None):
        """Write a JSONL event to the agent log (flushed immediately)."""
        self._open_log()
        entry = {
            "ts": time.time(),
            "game": self._game_id,
            "event": event_type,
        }
        if data:
            entry.update(data)
        self._log_file.write(json.dumps(entry) + "\n")
        self._log_file.flush()

    def close_log(self):
        """Close the log file."""
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def _serialize_state(self, gs):
        """Compact game state text for Claude (~300 chars target)."""
        p = gs.player
        hp_pct = int(p.hp / p.max_hp * 100) if p.max_hp > 0 else 0

        # Weapon/armor — short form
        wpn = f"{p.weapon.display_name}(atk{p.weapon.data.get('dmg', (0,0))[1]})" if p.weapon else "Fists"
        arm = f"{p.armor.display_name}(def{p.armor.data.get('defense', 0)})" if p.armor else "None"
        torch_pct = int(p.torch_fuel / TORCH_MAX_FUEL * 100) if TORCH_MAX_FUEL > 0 else 0

        # Inventory — just counts by type
        inv_counts = {}
        for item in p.inventory:
            if item.equipped:
                continue
            t = item.item_type
            inv_counts[t] = inv_counts.get(t, 0) + (item.count if hasattr(item, 'count') else 1)
        inv_str = " ".join(f"{k}:{v}" for k, v in inv_counts.items()) if inv_counts else "empty"

        # Visible enemies — compact
        enemy_parts = []
        for e in gs.enemies:
            if e.is_alive() and (e.x, e.y) in gs.visible:
                dx, dy = e.x - p.x, e.y - p.y
                dist = abs(dx) + abs(dy)
                d = ""
                if dy < 0: d += "N"
                if dy > 0: d += "S"
                if dx > 0: d += "E"
                if dx < 0: d += "W"
                boss = "!" if e.boss else ""
                alert_tag = f"[{e.alertness[0]}]" if e.alertness != "alert" else ""
                enemy_parts.append(f"{e.name}{boss}{alert_tag} hp{e.hp} {dist}{d}")
        enemies_str = ", ".join(enemy_parts) if enemy_parts else "none"

        # Visible items on ground — compact, limit to 3
        item_parts = []
        for item in gs.items:
            if (item.x, item.y) in gs.visible:
                dist = abs(item.x - p.x) + abs(item.y - p.y)
                if dist <= 8:
                    item_parts.append(f"{item.display_name}({dist})")
        items_str = ", ".join(item_parts[:3]) if item_parts else "none"

        # Nearby features — compact
        features = []
        sx, sy = gs.stair_down
        if (sx, sy) in gs.visible:
            features.append(f"stairs({abs(sx - p.x) + abs(sy - p.y)})")
        if gs.tiles[p.y][p.x] == T_SHRINE:
            features.append("ON_SHRINE")
        if gs.tiles[p.y][p.x] == T_STAIRS_DOWN:
            features.append("ON_STAIRS")
        if gs.tiles[p.y][p.x] == T_ALCHEMY_TABLE:
            used = "used" if (p.x, p.y) in gs.alchemy_used else "available"
            features.append(f"ALCHEMY({used})")
        if gs.tiles[p.y][p.x] in (T_PEDESTAL_UNLIT, T_PEDESTAL_LIT):
            state = "unlit" if gs.tiles[p.y][p.x] == T_PEDESTAL_UNLIT else "lit"
            features.append(f"PEDESTAL({state})")
        if gs.tiles[gs.stair_down[1]][gs.stair_down[0]] == T_STAIRS_LOCKED:
            features.append("STAIRS_LOCKED")
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = p.x + ddx, p.y + ddy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] == T_SHOP_FLOOR:
                features.append("SHOP_ADJ")
                break
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] == T_WALL_TORCH:
                features.append("WALL_TORCH_ADJ")
                break
        features_str = " ".join(features) if features else ""

        explored_pct = self.bot._floor_explored_pct(gs)

        class_str = CHARACTER_CLASSES[p.player_class]["name"] if p.player_class and p.player_class in CHARACTER_CLASSES else "Adv"
        status_str = " ".join(f"{k}({v})" for k, v in p.status_effects.items()) if p.status_effects else ""
        line = (f"F{p.floor}/{MAX_FLOORS} {class_str} HP{p.hp}/{p.max_hp}({hp_pct}%) MP{p.mana}/{p.max_mana} "
                f"Hng{p.hunger:.0f}% G{p.gold} T{gs.turn_count} Exp{explored_pct:.0%}\n"
                f"Wpn:{wpn} Arm:{arm} Torch:{torch_pct}%{'lit' if p.torch_lit else 'off'}\n"
                f"Inv({len(p.inventory)}/{p.carry_capacity}): {inv_str}\n"
                f"Enemies: {enemies_str}\n"
                f"Items: {items_str}")
        if status_str:
            line += f"\nStatus: {status_str}"
        # Include known spells and abilities so Claude can see what's available
        spells_str = ", ".join(sorted(p.known_spells))
        line += f"\nSpells: {spells_str}"
        if p.known_abilities:
            abilities_str = ", ".join(sorted(p.known_abilities))
            line += f"\nAbilities: {abilities_str}"
        if features_str:
            line += f"\nNear: {features_str}"
        if gs.puzzles:
            pz_parts = [f"{pz['type']}({'SOLVED' if pz['solved'] else 'active'})" for pz in gs.puzzles]
            line += f"\nPuzzles: {', '.join(pz_parts)}"
        if gs.journal:
            line += f"\nJournal: {len(gs.journal)} identified"
        if p.weapon and p.weapon.data.get("lifesteal"):
            line += "\nLifesteal weapon equipped"
        if gs.active_branch and gs.active_branch in BRANCH_DEFS:
            line += f"\nBranch: {BRANCH_DEFS[gs.active_branch]['name']}"
        # Stuck context: tell Claude where we've been
        if len(self._position_history) >= 15 and len(set(self._position_history)) <= 4:
            recent = list(set(self._position_history))
            line += f"\n!! STUCK — repeating positions {recent}. Try a NEW direction or teleport."
        return line

    def _state_hash(self, gs):
        """Quick hash of game state for dedup."""
        p = gs.player
        enemies = tuple(sorted((e.x, e.y, e.hp) for e in gs.enemies
                               if e.is_alive() and (e.x, e.y) in gs.visible))
        return hash((p.x, p.y, p.hp, p.mana, int(p.hunger), p.floor, enemies))

    def _should_consult(self, gs):
        """Check if this turn warrants a Claude call. Tracks trigger reasons for health monitoring."""
        p = gs.player
        reason = None

        # Enemies visible — combat decisions
        if self.bot._enemies_visible(gs):
            reason = "enemies_visible"

        # Low HP (< 40%) with meaningful choices to make
        elif p.max_hp > 0 and p.hp / p.max_hp < 0.4:
            reason = "low_hp"

        # Full inventory + item on ground
        elif len(p.inventory) >= gs.player.carry_capacity:
            items_here = [i for i in gs.items if i.x == p.x and i.y == p.y and i.item_type != "gold"]
            if items_here:
                reason = "inventory_full"

        # Shop adjacent (only consult once per floor)
        if reason is None and not self._consulted_shop:
            for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                nx, ny = p.x + ddx, p.y + ddy
                if 0 <= nx < MAP_W and 0 <= ny < MAP_H and gs.tiles[ny][nx] == T_SHOP_FLOOR:
                    self._consulted_shop = True
                    reason = "shop"
                    break

        # Boss visible
        if reason is None:
            for e in gs.enemies:
                if e.is_alive() and e.boss and (e.x, e.y) in gs.visible:
                    reason = "boss"
                    break

        # New floor (just descended) — reset per-floor flags
        if reason is None and p.floor != self._last_floor:
            self._last_floor = p.floor
            self._consulted_shop = False
            self._consulted_shrine = False
            self._consulted_locked_stairs = False
            self._seen_wall_torch = False
            reason = "new_floor"

        # Shrine — standing on one (only consult once per floor)
        if reason is None and gs.tiles[p.y][p.x] == T_SHRINE and not self._consulted_shrine:
            self._consulted_shrine = True
            reason = "shrine"

        # Alchemy table — standing on one (consult once)
        if reason is None and gs.tiles[p.y][p.x] == T_ALCHEMY_TABLE:
            if (p.x, p.y) not in gs.alchemy_used:
                reason = "alchemy_table"

        # Puzzle pedestal — standing on unlit one
        if reason is None and gs.tiles[p.y][p.x] == T_PEDESTAL_UNLIT:
            reason = "pedestal"

        # Locked stairs visible (consult once per floor)
        if reason is None and not getattr(self, '_consulted_locked_stairs', False):
            sx, sy = gs.stair_down
            if gs.tiles[sy][sx] == T_STAIRS_LOCKED and (sx, sy) in gs.visible:
                self._consulted_locked_stairs = True
                reason = "locked_stairs"

        # Wall torch adjacent (first encounter per floor)
        if reason is None and not getattr(self, '_seen_wall_torch', False):
            for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                tx, ty = p.x + ddx, p.y + ddy
                if 0 <= tx < MAP_W and 0 <= ty < MAP_H and gs.tiles[ty][tx] == T_WALL_TORCH:
                    self._seen_wall_torch = True
                    reason = "wall_torch"
                    break

        # Stuck detection: player hasn't moved meaningfully in 15 turns
        if reason is None:
            self._position_history.append((p.x, p.y))
            if len(self._position_history) >= 15 and gs.turn_count - self._last_stuck_turn >= 20:
                unique_positions = len(set(self._position_history))
                if unique_positions <= 4:  # Bouncing between 4 or fewer tiles
                    self._last_stuck_turn = gs.turn_count
                    reason = "stuck"

        if reason:
            # Cooldown: skip non-critical triggers if consulted recently
            critical = reason in ("boss", "low_hp", "new_floor", "alchemy_table", "pedestal", "locked_stairs", "stuck")
            if not critical and self._last_consult_turn and gs.turn_count - self._last_consult_turn < 3:
                return False

            # State dedup: skip if state unchanged since last call (non-critical only)
            if not critical:
                state_hash = self._state_hash(gs)
                if state_hash == self._last_state_hash:
                    return False
                self._last_state_hash = state_hash

            self._last_consult_turn = gs.turn_count
            self._window_calls += 1
            self._trigger_counts[reason] = self._trigger_counts.get(reason, 0) + 1
            return True

        return False

    # --- Health monitoring baselines ---
    HEALTH_BASELINES = {
        "calls_per_turn_max": 0.5,       # Expected: ~0.3, alert if >0.5 sustained
        "fallback_rate_max": 0.25,        # Expected: <10%, alert if >25%
        "avg_latency_max": 15.0,          # Expected: ~5-8s, alert if >15s
        "turns_per_floor_max": 600,       # Expected: 200-400, alert if >600
        "action_monotony_max": 0.80,      # Alert if >80% of recent actions are identical
        "hp_loss_no_enemies_max": 5,      # Alert if losing HP with no visible enemies (per window)
    }

    def _health_check(self, gs):
        """Run every _health_interval turns. Compares runtime metrics against baselines.
        Logs warnings and returns list of active warnings."""
        warnings = []
        turn = gs.turn_count
        window_turns = turn - self._window_start_turn

        if window_turns < self._health_interval:
            return warnings

        # --- Calls/turn ratio ---
        if window_turns > 0:
            ratio = self._window_calls / window_turns
            if ratio > self.HEALTH_BASELINES["calls_per_turn_max"]:
                w = f"HEALTH: calls/turn={ratio:.2f} (max {self.HEALTH_BASELINES['calls_per_turn_max']})"
                warnings.append(w)
                # Log trigger distribution to help diagnose
                if self._trigger_counts:
                    top = sorted(self._trigger_counts.items(), key=lambda x: -x[1])[:3]
                    w += f" triggers={top}"
                    warnings[-1] = w

        # --- Fallback rate ---
        if self.claude_calls > 5:
            fb_rate = self.fallbacks / self.claude_calls
            if fb_rate > self.HEALTH_BASELINES["fallback_rate_max"]:
                warnings.append(f"HEALTH: fallback_rate={fb_rate:.0%} (max {self.HEALTH_BASELINES['fallback_rate_max']:.0%})")

        # --- Average latency ---
        if self.claude_calls > 0:
            avg_lat = self.total_latency / self.claude_calls
            if avg_lat > self.HEALTH_BASELINES["avg_latency_max"]:
                warnings.append(f"HEALTH: avg_latency={avg_lat:.1f}s (max {self.HEALTH_BASELINES['avg_latency_max']}s)")

        # --- Turns per floor (stuck detection) ---
        floor_turns = turn - self._floor_start_turn
        if floor_turns > self.HEALTH_BASELINES["turns_per_floor_max"]:
            warnings.append(f"HEALTH: turns_on_floor={floor_turns} (max {self.HEALTH_BASELINES['turns_per_floor_max']})")

        # --- Action monotony (same action repeated) ---
        if len(self._action_window) >= 10:
            from collections import Counter
            counts = Counter(self._action_window)
            most_common_action, most_common_count = counts.most_common(1)[0]
            monotony = most_common_count / len(self._action_window)
            if monotony > self.HEALTH_BASELINES["action_monotony_max"]:
                warnings.append(f"HEALTH: action_monotony={monotony:.0%} action='{most_common_action}' (max {self.HEALTH_BASELINES['action_monotony_max']:.0%})")

        # --- HP loss without visible enemies ---
        if len(self._hp_samples) >= 2:
            hp_loss = self._hp_samples[0] - self._hp_samples[-1]
            if hp_loss > self.HEALTH_BASELINES["hp_loss_no_enemies_max"]:
                enemies_visible = any(e.is_alive() and (e.x, e.y) in gs.visible and not e.disguised for e in gs.enemies)
                if not enemies_visible:
                    warnings.append(f"HEALTH: hp_loss={hp_loss} with no visible enemies (poison? fire_aura? starvation?)")

        # Log warnings
        for w in warnings:
            self._log("health_warning", {"turn": turn, "warning": w})

        # Reset window counters
        self._window_calls = 0
        self._window_start_turn = turn
        self._hp_samples.clear()
        self._trigger_counts.clear()
        self._health_warnings = warnings
        return warnings

    def _post_game_report(self, gs):
        """Post-game health summary. Call after game ends. Returns dict of metrics + flags."""
        p = gs.player
        report = {
            "turns": gs.turn_count,
            "floor": p.floor,
            "kills": p.kills,
            "victory": gs.victory,
            "claude_calls": self.claude_calls,
            "fallbacks": self.fallbacks,
            "avg_latency": self.total_latency / self.claude_calls if self.claude_calls > 0 else 0,
            "calls_per_turn": self.claude_calls / gs.turn_count if gs.turn_count > 0 else 0,
            "fallback_rate": self.fallbacks / self.claude_calls if self.claude_calls > 0 else 0,
            "warnings_total": len(self._health_warnings),
        }
        # Flag anomalies
        flags = []
        if report["calls_per_turn"] > self.HEALTH_BASELINES["calls_per_turn_max"]:
            flags.append(f"HIGH calls/turn: {report['calls_per_turn']:.2f}")
        if report["fallback_rate"] > self.HEALTH_BASELINES["fallback_rate_max"]:
            flags.append(f"HIGH fallback rate: {report['fallback_rate']:.0%}")
        if report["avg_latency"] > self.HEALTH_BASELINES["avg_latency_max"]:
            flags.append(f"HIGH latency: {report['avg_latency']:.1f}s")
        if gs.turn_count > 0 and not gs.victory and p.floor <= 2 and gs.turn_count > 1000:
            flags.append(f"STUCK: {gs.turn_count} turns, only floor {p.floor}")
        report["flags"] = flags
        self._log("post_game_report", report)

        # Agent-commons: generate detailed summary and autopsy
        if HAS_AGENT_COMMONS and self._ac_trace is not None:
            try:
                summary_gen = PostRunSummaryReport()
                game_stats = {
                    "floor": p.floor, "score": calculate_score(gs) if hasattr(gs, 'player') else 0,
                    "turns": gs.turn_count,
                    "outcome": "victory" if gs.victory else "death",
                    "cause": getattr(p, 'death_cause', 'unknown'),
                    "hp": p.hp,
                    "duration_s": report.get("game_time_s", 0),
                    "stalls_recovered": self._ac_recovery.total_recoveries if hasattr(self, '_ac_recovery') else 0,
                }
                summary_text = summary_gen.generate(
                    trace=self._ac_trace, coverage=self._ac_coverage,
                    actions=self._ac_actions, game_stats=game_stats)
                self._log("ac_summary", {"text": summary_text})
                report["ac_summary"] = summary_text

                # Coverage report
                report["ac_coverage_pct"] = round(self._ac_coverage.coverage_pct(), 1)
                report["ac_covered"] = self._ac_coverage.covered()
                report["ac_uncovered"] = self._ac_coverage.uncovered()

                # Action distribution
                report["ac_action_dist"] = self._ac_actions.percentages()

                # Death autopsy if not victory
                if not gs.victory:
                    autopsy_gen = DeathAutopsy()
                    potions = sum(1 for i in p.inventory if i.item_type == "potion")
                    food = sum(1 for i in p.inventory if i.item_type == "food")
                    autopsy_text = autopsy_gen.generate(
                        trace=self._ac_trace,
                        final_state={
                            "cause": getattr(p, 'death_cause', 'unknown'),
                            "hp": p.hp, "potions": potions, "food": food,
                            "mana": p.mana,
                        })
                    self._log("ac_autopsy", {"text": autopsy_text})
                    report["ac_autopsy"] = autopsy_text

                # Save coverage for cross-run analysis
                cov_path = os.path.expanduser(f"~/.depths_of_dread_agent_traces/coverage_game_{self._game_id}.json")
                self._ac_coverage.save(cov_path)
            except Exception as e:
                self._log("ac_error", {"error": str(e)[:200]})

        return report

    def _call_claude(self, state_text):
        """Call claude via stdin with game state, return parsed action dict or None.

        Uses stdin pipe instead of -p arg to avoid shell escaping issues and
        arg length limits.  Retries once on failure with a shorter timeout.
        """
        cmd = [
            CLAUDE_BIN,
            "-p", "-",        # Read prompt from stdin
            "--output-format", "json",
            "--model", "haiku",
            "--system-prompt", AGENT_SYSTEM_PROMPT,
            "--max-turns", "1",
            "--setting-sources", "",  # Skip CLAUDE.md — saves ~19K tokens & halves latency
        ]
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # Avoid nested-session error

        timeouts = [30, 20]  # First attempt 30s, retry 20s
        for attempt, timeout in enumerate(timeouts):
            try:
                start = time.time()
                result = subprocess.run(
                    cmd, input=state_text,
                    capture_output=True, text=True, timeout=timeout, env=env,
                )
                elapsed = time.time() - start
                self.total_latency += elapsed
                self._last_call_latency = elapsed
                self.claude_calls += 1

                if result.returncode != 0:
                    self._log("claude_error", {
                        "returncode": result.returncode,
                        "stderr": result.stderr[:200],
                        "attempt": attempt + 1,
                    })
                    if attempt < len(timeouts) - 1:
                        continue  # Retry
                    return None

                # Use agent-commons validator if available, else legacy parser
                parsed = None
                if HAS_AGENT_COMMONS and self._ac_trace is not None:
                    from agent_commons.reliability import ACTION_SCHEMA
                    val_parsed, val_errors = self._ac_validator.validate(result.stdout, ACTION_SCHEMA)
                    if val_parsed and not val_errors:
                        parsed = val_parsed
                    elif val_parsed and val_errors:
                        # Partial parse — try legacy as fallback
                        parsed = self._parse_response(result.stdout)
                    else:
                        parsed = self._parse_response(result.stdout)
                else:
                    parsed = self._parse_response(result.stdout)

                self._log("claude_call", {
                    "latency": round(elapsed, 2),
                    "action": parsed.get("action") if parsed else None,
                    "reason": parsed.get("reason", "") if parsed else None,
                    "state_preview": state_text[:120],
                    "attempt": attempt + 1,
                })
                # Agent-commons: log to decision trace
                if HAS_AGENT_COMMONS and self._ac_trace is not None:
                    trigger = self._trigger_counts.copy()
                    last_trigger = max(trigger, key=trigger.get) if trigger else "unknown"
                    self._ac_trace.log_decision(
                        turn=0,  # Will be set by caller context
                        trigger=last_trigger,
                        parsed_action=parsed.get("action") if parsed else None,
                        latency_ms=round(elapsed * 1000),
                        fallback_used=parsed is None,
                    )
                if parsed:
                    return parsed
                # Parseable failure — retry
                if attempt < len(timeouts) - 1:
                    self._log("claude_error", {"error": "unparseable_response", "attempt": attempt + 1, "raw": result.stdout[:300]})
                    continue
                self._log("claude_error", {"error": "unparseable_response_final", "attempt": attempt + 1, "raw": result.stdout[:300]})
                return None
            except subprocess.TimeoutExpired:
                self._log("claude_error", {"error": f"timeout_{timeout}s", "attempt": attempt + 1})
                if attempt < len(timeouts) - 1:
                    continue  # Retry with shorter timeout
                return None
            except Exception as exc:
                self._log("claude_error", {"error": str(exc)[:200], "attempt": attempt + 1})
                return None
        return None

    def _parse_response(self, raw):
        """Extract action JSON from Claude's response.

        Claude --output-format json returns: {"type":"result","result":"..."}
        The result field contains the actual response text which should be
        our action JSON, possibly wrapped in markdown fences.
        """
        try:
            envelope = json.loads(raw)
            inner = envelope.get("result", "")
        except (json.JSONDecodeError, AttributeError):
            inner = raw

        # Strip markdown code fences if present
        inner = inner.strip()
        if inner.startswith("```"):
            lines = inner.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            inner = "\n".join(lines).strip()

        try:
            data = json.loads(inner)
            if "action" in data:
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        return None

    def _action_to_command(self, action_str, gs):
        """Map Claude's action string → (action, params) for _bot_execute_action.

        Handles common Claude response variations:
        - 'move north' vs 'move_north'
        - 'heal' vs 'cast_heal'
        - 'potion' vs 'use_potion'
        - 'eat' vs 'eat_food'
        """
        action_str = action_str.strip().lower()
        # Normalize: replace spaces with underscores, strip quotes
        action_str = action_str.replace(" ", "_").strip('"\'')
        p = gs.player

        # Movement — handle 'move_north', 'north', 'go_north', 'move_n'
        move_match = None
        if action_str.startswith("move_"):
            move_match = action_str[5:]
        elif action_str.startswith("go_"):
            move_match = action_str[3:]
        elif action_str in _DIR_MAP:
            move_match = action_str
        if move_match and move_match in _DIR_MAP:
            dx, dy = _DIR_MAP[move_match]
            return ("move", {"dx": dx, "dy": dy})

        # Attack (move toward nearest enemy) — handle 'attack', 'melee', 'attack_nearest'
        if action_str in ("attack", "melee", "attack_nearest"):
            nearest = self.bot._nearest_visible_enemy(gs)
            if nearest:
                dx = nearest.x - p.x
                dy = nearest.y - p.y
                dx = max(-1, min(1, dx))
                dy = max(-1, min(1, dy))
                return ("move", {"dx": dx, "dy": dy})

        # Fire projectile — handle 'fire_east', 'shoot_east'
        fire_match = None
        if action_str.startswith("fire_"):
            fire_match = action_str[5:]
        elif action_str.startswith("shoot_"):
            fire_match = action_str[6:]
        if fire_match and fire_match in _DIR_MAP:
            dx, dy = _DIR_MAP[fire_match]
            return ("fire", {"dx": dx, "dy": dy})

        # Spells — handle 'cast_heal', 'heal'
        if action_str in ("cast_heal", "heal"):
            return ("cast_spell", {"spell": "Heal"})
        if action_str.startswith("cast_fireball") or action_str.startswith("fireball"):
            parts = action_str.split("_")
            dir_name = parts[-1] if len(parts) > 1 else ""
            dx, dy = _DIR_MAP.get(dir_name, (0, 0))
            if dx == 0 and dy == 0:
                nearest = self.bot._nearest_visible_enemy(gs)
                if nearest:
                    dx = 1 if nearest.x > p.x else (-1 if nearest.x < p.x else 0)
                    dy = 1 if nearest.y > p.y else (-1 if nearest.y < p.y else 0)
            return ("cast_spell", {"spell": "Fireball", "dx": dx, "dy": dy})
        if action_str in ("cast_freeze", "freeze"):
            nearest = self.bot._nearest_visible_enemy(gs)
            return ("cast_spell", {"spell": "Freeze", "target": nearest})
        if action_str.startswith("cast_lightning") or action_str.startswith("lightning"):
            parts = action_str.split("_")
            dir_name = parts[-1] if len(parts) > 1 else ""
            dx, dy = _DIR_MAP.get(dir_name, (0, 0))
            return ("cast_spell", {"spell": "Lightning Bolt", "dx": dx, "dy": dy})
        if action_str in ("cast_teleport", "teleport"):
            return ("cast_spell", {"spell": "Teleport"})
        if action_str in ("cast_chain_lightning", "chain_lightning"):
            nearest = self.bot._nearest_visible_enemy(gs)
            return ("cast_spell", {"spell": "Chain Lightning", "target": nearest})
        if action_str.startswith("cast_meteor") or action_str.startswith("meteor"):
            parts = action_str.split("_")
            dir_name = parts[-1] if len(parts) > 1 else ""
            dx, dy = _DIR_MAP.get(dir_name, (0, 0))
            if dx == 0 and dy == 0:
                nearest = self.bot._nearest_visible_enemy(gs)
                if nearest:
                    dx = 1 if nearest.x > p.x else (-1 if nearest.x < p.x else 0)
                    dy = 1 if nearest.y > p.y else (-1 if nearest.y < p.y else 0)
            return ("cast_spell", {"spell": "Meteor", "dx": dx, "dy": dy})
        if action_str in ("cast_mana_shield", "mana_shield"):
            return ("cast_spell", {"spell": "Mana Shield"})

        # Class abilities — handle 'use_whirlwind', 'whirlwind', etc.
        _ABILITY_MAP = {
            "use_whirlwind": "Whirlwind", "whirlwind": "Whirlwind",
            "use_cleaving_strike": "Cleaving Strike", "cleaving_strike": "Cleaving Strike",
            "use_shield_wall": "Shield Wall", "shield_wall": "Shield Wall",
            "use_backstab": "Backstab", "backstab": "Backstab",
            "use_poison_blade": "Poison Blade", "poison_blade": "Poison Blade",
            "use_smoke_bomb": "Smoke Bomb", "smoke_bomb": "Smoke Bomb",
        }
        if action_str in _ABILITY_MAP:
            return ("use_ability", {"ability": _ABILITY_MAP[action_str]})

        # Items — handle 'use_potion', 'potion', 'drink_potion'
        if action_str in ("use_potion", "potion", "drink_potion"):
            for item in p.inventory:
                if item.item_type == "potion":
                    return ("use_item", {"item": item, "type": "potion"})
        if action_str in ("eat_food", "eat", "food"):
            for item in p.inventory:
                if item.item_type == "food":
                    return ("use_item", {"item": item, "type": "food"})

        # Equip — handle 'equip_<name>' and 'equip <name>'
        if action_str.startswith("equip_") or action_str.startswith("equip "):
            equip_name = action_str.split("_", 1)[-1].strip().lower() if "_" in action_str else action_str[6:].strip().lower()
            for item in p.inventory:
                if equip_name in item.display_name.lower() and not item.equipped:
                    return ("equip", {"item": item})

        # Other actions — handle variations
        if action_str in ("descend", "go_down", "stairs", "go_downstairs"):
            return ("descend", {})
        if action_str in ("rest", "wait", "pass", "skip", "do_nothing"):
            return ("rest", {})
        # New feature actions
        if action_str in ("use_alchemy", "alchemy", "identify"):
            if gs.tiles[p.y][p.x] == T_ALCHEMY_TABLE:
                return ("use_alchemy", {})
        if action_str in ("light_pedestal", "pedestal"):
            if gs.tiles[p.y][p.x] == T_PEDESTAL_UNLIT:
                return ("interact_pedestal", {})
        if action_str in ("grab_wall_torch", "grab_torch", "take_torch"):
            return ("grab_wall_torch", {})

        if action_str in ("pickup", "pick_up", "grab", "get", "take"):
            return ("pickup", {})
        if action_str in ("pray", "use_shrine"):
            return ("pray", {})
        if action_str in ("toggle_torch", "torch"):
            return ("toggle_torch", {})

        return None  # Unparseable

    def _track_coverage(self, gs, action_str=""):
        """Track feature coverage events from game state and action."""
        if not HAS_AGENT_COMMONS or self._ac_trace is None:
            return
        p = gs.player
        cov = self._ac_coverage
        a = action_str.lower()
        # Action-based coverage
        if "potion" in a or "heal" in a:
            cov.mark("used_potion")
        if "eat" in a or "food" in a:
            cov.mark("ate_food")
        if "equip" in a and "weapon" in a:
            cov.mark("equipped_weapon")
        if "equip" in a and "armor" in a:
            cov.mark("equipped_armor")
        if "equip" in a and "ring" in a:
            cov.mark("equipped_ring")
        if "cast" in a or "spell" in a:
            cov.mark("cast_spell")
        if "fireball" in a:
            cov.mark("cast_fireball")
        if a in ("cast_heal", "heal"):
            cov.mark("cast_heal")
        if "lightning" in a:
            cov.mark("cast_lightning")
        if "teleport" in a:
            cov.mark("cast_teleport")
        if "pray" in a or "shrine" in a:
            cov.mark("used_shrine")
        if "alchemy" in a or "identify" in a:
            cov.mark("used_alchemy_table")
        if "torch" in a:
            cov.mark("toggled_torch")
        if "fire" in a and "ball" not in a:
            cov.mark("fired_projectile")
        if "scroll" in a:
            cov.mark("used_scroll")
        if "pickup" in a or "pick_up" in a:
            cov.mark("picked_up_item")
        if "search" in a or "trap" in a:
            cov.mark("searched_for_traps")
        if "disarm" in a:
            cov.mark("disarmed_trap")
        if "descend" in a:
            cov.mark("descended_stairs")
        # State-based coverage
        if p.floor >= 5:
            cov.mark("reached_floor_5")
        if p.floor >= 10:
            cov.mark("reached_floor_10")
        if p.floor >= 15:
            cov.mark("reached_floor_15")
        if gs.active_branch:
            cov.mark("entered_branch")

    def decide(self, gs):
        """Returns (action, params) — consults Claude for tactical decisions, BotPlayer otherwise."""
        p = gs.player

        # Track floor changes for health monitoring
        if p.floor != self._last_floor:
            self._floor_start_turn = gs.turn_count

        # HP sampling for health monitoring
        self._hp_samples.append(p.hp)

        # Log game state snapshot every 25 turns
        if gs.turn_count % 25 == 0:
            self._log("snapshot", {
                "turn": gs.turn_count, "floor": p.floor,
                "hp": p.hp, "max_hp": p.max_hp,
                "mana": p.mana, "hunger": round(p.hunger, 1),
                "kills": p.kills, "gold": p.gold,
                "inventory": len(p.inventory),
            })
            # Agent-commons: state snapshot at periodic intervals
            if HAS_AGENT_COMMONS and self._ac_trace is not None:
                if self._ac_snapshots.should_snapshot("periodic", gs.turn_count):
                    self._ac_snapshots.save_snapshot({
                        "turn": gs.turn_count, "floor": p.floor,
                        "hp": p.hp, "max_hp": p.max_hp,
                        "mana": p.mana, "hunger": round(p.hunger, 1),
                        "kills": p.kills, "gold": p.gold,
                        "inventory": len(p.inventory),
                        "explored": round(self.bot._floor_explored_pct(gs), 2),
                    }, "periodic", gs.turn_count)

        # Run health check periodically
        if gs.turn_count > 0 and gs.turn_count % self._health_interval == 0:
            self._health_check(gs)

        # Agent-commons: stall detection (progress = floor * 1000 + kills)
        ac_stalled = False
        ac_repeated = False
        if HAS_AGENT_COMMONS and self._ac_trace is not None:
            progress = p.floor * 1000 + p.kills
            ac_stalled = self._ac_stall.update(progress)

        if self._should_consult(gs):
            # Agent-commons: check call budget
            if HAS_AGENT_COMMONS and self._ac_trace is not None:
                if not self._ac_budget.spend():
                    # Budget exhausted — use bot only
                    self._log("budget_exhausted", {"turn": gs.turn_count})
                    action, params = self.bot.decide(gs)
                    self.strategy = self.bot.strategy
                    self.target_desc = self.bot.target_desc
                    self._action_window.append(self.strategy)
                    return (action, params)

            state_text = self._serialize_state(gs)
            # Agent-commons: append novelty hint to state
            if HAS_AGENT_COMMONS and self._ac_trace is not None:
                hint = self._ac_novelty.generate_exploration_hint(self._ac_coverage)
                if self._ac_coverage.coverage_pct() < 60:
                    state_text += f"\n{hint}"

            self._thinking = True
            response = self._call_claude(state_text)
            self._thinking = False

            if response and "action" in response:
                self.reason = response.get("reason", "")
                cmd = self._action_to_command(response["action"], gs)
                if cmd:
                    action, params = cmd
                    # Determine strategy label from action
                    action_str = response["action"].lower()
                    if "fire" in action_str or "attack" in action_str or "cast" in action_str:
                        self.strategy = "COMBAT"
                    elif "heal" in action_str or "potion" in action_str:
                        self.strategy = "HEAL"
                    elif "move" in action_str:
                        self.strategy = "TACTICAL"
                    elif "descend" in action_str:
                        self.strategy = "DESCEND"
                    else:
                        self.strategy = "CLAUDE"
                    self.target_desc = response["action"]
                    self._action_window.append(self.strategy)
                    # Agent-commons: record action + coverage
                    if HAS_AGENT_COMMONS and self._ac_trace is not None:
                        self._ac_actions.record(self.strategy)
                        ac_repeated = self._ac_rep.record(self.strategy)
                        self._track_coverage(gs, response["action"])
                    return (action, params)

            # Claude failed — fallback to bot
            self.fallbacks += 1
            self.reason = "(fallback to bot)"
            self._log("fallback", {"turn": gs.turn_count, "reason": "claude_failed"})

        # Agent-commons: attempt stall recovery if stalled or repeating
        if HAS_AGENT_COMMONS and self._ac_trace is not None and (ac_stalled or ac_repeated):
            recovery_action = self._ac_recovery.attempt_recovery(
                state_text=self._serialize_state(gs),
                action_history=self._ac_rep.history,
                call_fn=None,  # Skip LLM reflection for now — use random action
            )
            if recovery_action:
                cmd = self._action_to_command(recovery_action, gs)
                if cmd:
                    self._log("ac_recovery", {"turn": gs.turn_count, "action": recovery_action})
                    self.strategy = "RECOVERY"
                    self.target_desc = f"recovery:{recovery_action}"
                    self._action_window.append(self.strategy)
                    return cmd

        # Non-triggered turn or fallback: use BotPlayer
        action, params = self.bot.decide(gs)
        self.strategy = self.bot.strategy
        self.target_desc = self.bot.target_desc
        self._action_window.append(self.strategy)
        # Agent-commons: record bot action
        if HAS_AGENT_COMMONS and self._ac_trace is not None:
            self._ac_actions.record(self.strategy)
            self._ac_rep.record(self.strategy)
        return (action, params)


AGENT_PANEL_X = 82  # Right panel starts 2 cols after game area (col 80)
AGENT_PANEL_MIN_W = 50  # Minimum panel width to be useful
AGENT_SPLIT_MIN_COLS = AGENT_PANEL_X + AGENT_PANEL_MIN_W  # 132 cols needed


def _render_agent_panel(scr, agent, gs, decision_log):
    """Render the split-screen decision panel to the right of the game."""
    term_h, term_w = scr.getmaxyx()
    panel_w = term_w - AGENT_PANEL_X - 1
    if panel_w < AGENT_PANEL_MIN_W:
        return  # Terminal too narrow

    px = AGENT_PANEL_X
    p = gs.player

    # Draw vertical separator
    for row in range(min(term_h - 1, SCREEN_H)):
        safe_addstr(scr, row, px - 1, "|", curses.color_pair(C_DARK))

    y = 0

    # --- Header ---
    header = " CLAUDE AGENT "
    pad = (panel_w - len(header)) // 2
    safe_addstr(scr, y, px, " " * panel_w, curses.color_pair(C_MAGENTA))
    safe_addstr(scr, y, px + max(0, pad), header,
               curses.color_pair(C_MAGENTA) | curses.A_BOLD)
    y += 1

    # --- Stats row ---
    avg_lat = agent.total_latency / agent.claude_calls if agent.claude_calls > 0 else 0
    safe_addstr(scr, y, px, f"Calls:{agent.claude_calls:<4} Avg:{avg_lat:.1f}s "
               f"Falls:{agent.fallbacks} Err:{getattr(agent, '_error_count', 0)}",
               curses.color_pair(C_CYAN))
    y += 1

    # --- Current strategy ---
    safe_addstr(scr, y, px, f"Mode: {agent.strategy:<10} Floor {p.floor}/{MAX_FLOORS}  "
               f"Turn {gs.turn_count}",
               curses.color_pair(C_YELLOW))
    y += 1

    # --- HP bar ---
    hp_pct = p.hp / p.max_hp if p.max_hp > 0 else 0
    bar_w = min(20, panel_w - 16)
    filled = int(hp_pct * bar_w)
    hp_bar = "#" * filled + "-" * (bar_w - filled)
    hp_cp = C_GREEN if hp_pct > 0.6 else (C_YELLOW if hp_pct > 0.3 else C_RED)
    safe_addstr(scr, y, px, f"HP [{hp_bar}] {p.hp}/{p.max_hp}",
               curses.color_pair(hp_cp))
    y += 1

    # --- Hunger bar ---
    hunger_pct = p.hunger / 100.0
    hfilled = int(hunger_pct * bar_w)
    hunger_bar = "#" * hfilled + "-" * (bar_w - hfilled)
    hg_cp = C_GREEN if p.hunger > 50 else (C_YELLOW if p.hunger > 20 else C_RED)
    safe_addstr(scr, y, px, f"HG [{hunger_bar}] {p.hunger:.0f}%",
               curses.color_pair(hg_cp))
    y += 1

    # --- Calls/turn ratio (live health indicator) ---
    cpt = agent.claude_calls / gs.turn_count if gs.turn_count > 0 else 0
    cpt_cp = C_GREEN if cpt <= 0.3 else (C_YELLOW if cpt <= 0.5 else C_RED)
    safe_addstr(scr, y, px, f"C/T: {cpt:.2f}  ", curses.color_pair(cpt_cp))
    fb_rate = agent.fallbacks / agent.claude_calls if agent.claude_calls > 0 else 0
    fb_cp = C_GREEN if fb_rate <= 0.1 else (C_YELLOW if fb_rate <= 0.25 else C_RED)
    safe_addstr(scr, y, px + 10, f"FB: {fb_rate:.0%}", curses.color_pair(fb_cp))
    y += 1

    # --- Health warnings (most recent) ---
    if agent._health_warnings:
        recent = agent._health_warnings[-min(2, len(agent._health_warnings)):]
        for warn in recent:
            if y >= term_h - 3:
                break
            safe_addstr(scr, y, px, warn[:panel_w], curses.color_pair(C_RED))
            y += 1

    # --- Separator ---
    safe_addstr(scr, y, px, "-" * panel_w, curses.color_pair(C_DARK))
    y += 1

    # --- Decision log header ---
    safe_addstr(scr, y, px, "DECISION LOG", curses.color_pair(C_CYAN) | curses.A_BOLD)
    y += 1

    # --- Decision entries (newest first, fill remaining space) ---
    max_rows = min(len(decision_log), term_h - y - 2)
    entries = list(decision_log)[-max_rows:] if max_rows > 0 else []
    for i, entry in enumerate(reversed(entries)):
        if y >= term_h - 1:
            break
        action = entry.get("action", "?")
        if action is None:
            action = "ERR"
        latency = entry.get("latency", 0)
        reason = entry.get("reason", "")

        # First line: action + latency
        lat_cp = C_GREEN if latency < 3 else (C_YELLOW if latency < 8 else C_RED)
        action_str = f"{action[:18]:<18}"
        safe_addstr(scr, y, px, action_str,
                   curses.color_pair(C_MAGENTA) | (curses.A_BOLD if i == 0 else 0))
        safe_addstr(scr, y, px + 19, f"{latency:.1f}s", curses.color_pair(lat_cp))
        y += 1

        # Second line: reason (wrapped if needed)
        if reason and y < term_h - 1:
            reason_w = panel_w - 2
            reason_display = reason[:reason_w]
            safe_addstr(scr, y, px + 1, reason_display,
                       curses.color_pair(C_WHITE) if i == 0 else curses.color_pair(C_DARK))
            y += 1

    # --- Footer ---
    if term_h > 1:
        safe_addstr(scr, term_h - 1, px, "[q]uit [space]pause [+/-]speed [t]panel [P]ilot",
                   curses.color_pair(C_DARK))


_PILOT_MOVE_KEYS = {
    curses.KEY_UP: (0,-1), curses.KEY_DOWN: (0,1),
    curses.KEY_LEFT: (-1,0), curses.KEY_RIGHT: (1,0),
    ord('w'): (0,-1), ord('s'): (0,1),
    ord('a'): (-1,0), ord('d'): (1,0),
    ord('h'): (-1,0), ord('j'): (0,1),
    ord('k'): (0,-1), ord('l'): (1,0),
    ord('y'): (-1,-1), ord('u'): (1,-1),
    ord('b'): (-1,1), ord('n'): (1,1),
}

def _pilot_process_key(gs, scr, key):
    """Process a single keypress during pilot mode. Returns True if turn was spent."""
    p = gs.player
    if key in _PILOT_MOVE_KEYS:
        dx, dy = _PILOT_MOVE_KEYS[key]
        return player_move(gs, dx, dy)
    elif key == ord('>'):
        if p.floor == MAX_FLOORS:
            boss_alive = any(e.boss and e.etype == "dread_lord" and e.is_alive() for e in gs.enemies)
            if boss_alive:
                gs.msg("The Dread Lord still lives!", C_RED)
            else:
                gs.victory = True
                gs.game_over = True
            return False
        if gs.tiles[p.y][p.x] == T_STAIRS_DOWN:
            new_floor = p.floor + 1
            if new_floor in BRANCH_CHOICES and new_floor not in gs.branch_choices:
                _show_branch_choice(scr, gs, new_floor)
            gs.msg(f"Descending to floor {new_floor}...", C_YELLOW)
            gs.generate_floor(new_floor)
            return True
        gs.msg("No stairs here.", C_WHITE)
        return False
    elif key == ord('.') or key == ord('5'):
        return True  # Rest/wait
    elif key == ord(',') or key == ord('g'):
        # Pickup items at player position
        items_here = [i for i in gs.items if i.x == p.x and i.y == p.y]
        for it in items_here:
            if it.item_type == "gold":
                p.gold += it.count
                gs.msg(f"Picked up {it.count} gold.", C_GOLD)
                gs.items.remove(it)
            elif len(p.inventory) < p.carry_capacity or it.item_type == "scroll":
                p.inventory.append(it)
                gs.msg(f"Picked up {it.display_name}.", C_WHITE)
                gs.items.remove(it)
            else:
                gs.msg("Inventory full!", C_RED)
        return False
    elif key == ord('e'):
        # Use first potion in inventory
        potions = [i for i in p.inventory if i.item_type == "potion" and not i.equipped]
        if potions:
            use_potion(gs, potions[0])
            return True
        gs.msg("No potions.", C_WHITE)
        return False
    elif key == ord('E'):
        # Eat food
        food = [i for i in p.inventory if i.item_type == "food" and not i.equipped]
        if food:
            p.hunger = min(100.0, p.hunger + B["food_restore"])
            p.inventory.remove(food[0])
            gs.msg("You eat some food.", C_GREEN)
            return True
        gs.msg("No food.", C_WHITE)
        return False
    elif key == ord('f'):
        fire_projectile(gs, scr)
        return True
    elif key == ord('z'):
        cast_spell_menu(gs, scr)
        return False
    elif key == ord('p'):
        pray_at_shrine(gs)
        return True
    elif key == ord('i'):
        show_inventory(scr, gs)
        return False
    elif key == ord('s'):
        _search_for_traps(gs)
        return True
    elif key == ord('D'):
        _disarm_trap(gs)
        return True
    elif key == ord('T'):
        p.torch_lit = not p.torch_lit
        gs.msg(f"Torch {'lit' if p.torch_lit else 'extinguished'}.", C_YELLOW)
        return False
    elif key == ord('M'):
        show_bestiary(scr, gs)
        return False
    return False


def agent_game_loop(scr, speed=0.15, max_turns=10000):
    """Run a Claude-powered agent game visually in the terminal."""
    curses.curs_set(0)
    scr.nodelay(False)
    scr.keypad(True)
    init_colors()

    # Clear agent log for fresh session
    try:
        open(AGENT_LOG_PATH, 'w').close()
    except OSError:
        pass

    gs = GameState(player_class="warrior")
    gs._scr = scr
    _init_new_game(gs)
    agent = AgentPlayer(game_id=1)
    agent._log("game_start", {"seed": gs.seed, "mode": "visual", "class": "warrior"})
    show_panel = True
    paused = False
    delay_ms = max(10, int(speed * 1000))
    decision_log = deque(maxlen=50)  # Rolling log of Claude decisions
    pilot_mode = False  # Player takes manual control when True

    while gs.running and not gs.game_over and gs.turn_count < max_turns:
        fov_radius = gs.player.get_torch_radius()
        if "Blindness" in gs.player.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        _update_explored_from_fov(gs)

        # Auto-apply pending level-ups
        while gs.player.pending_levelups:
            auto_apply_levelup(gs.player)

        if pilot_mode:
            # Player manual control — same keys as interactive game
            safe_addstr(scr, 0, SCREEN_W // 2 - 6, " PILOT MODE ",
                       curses.color_pair(C_YELLOW) | curses.A_BOLD | curses.A_REVERSE)
            safe_addstr(scr, SCREEN_H - 1, 0, " Shift+P to release back to agent ",
                       curses.color_pair(C_YELLOW))
            scr.refresh()
            scr.nodelay(False)
            key = scr.getch()
            if key == ord('P'):
                pilot_mode = False
                continue
            turn_spent = _pilot_process_key(gs, scr, key)
            was_claude = False
        else:
            pre_calls = agent.claude_calls
            action, params = agent.decide(gs)
            was_claude = agent.claude_calls > pre_calls

            # Capture Claude decision into the rolling log
            if was_claude and agent.reason and agent.reason != "(fallback to bot)":
                decision_log.append({
                    "action": agent.target_desc,
                    "reason": agent.reason,
                    "latency": agent._last_call_latency,
                    "turn": gs.turn_count,
                })

            turn_spent = _bot_execute_action(gs, action, params)

        if turn_spent:
            gs.turn_count += 1
            if gs.last_noise > 0:
                _stealth_detection(gs, gs.last_noise)
            gs.last_noise = 0
            process_enemies(gs)
            process_status(gs)
            if gs.player.hp <= 0:
                gs.game_over = True

        # Re-compute FOV after action for rendering
        fov_radius = gs.player.get_torch_radius()
        if "Blindness" in gs.player.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        _update_explored_from_fov(gs)
        render_game(scr, gs)

        # Split-screen: decision panel on the right (if terminal is wide enough)
        _, term_w = scr.getmaxyx()
        if show_panel and term_w >= AGENT_SPLIT_MIN_COLS:
            _render_agent_panel(scr, agent, gs, decision_log)
        elif show_panel:
            # Narrow terminal fallback: compact overlay in top-right of game area
            p = gs.player
            hp_pct = int(p.hp / p.max_hp * 100) if p.max_hp > 0 else 0
            avg_lat = agent.total_latency / agent.claude_calls if agent.claude_calls > 0 else 0
            reason_display = agent.reason[:36] if agent.reason else ""
            tlines = [
                "AGENT (Claude-powered)",
                f"Strategy: {agent.strategy:<10} Turn: {gs.turn_count}",
                f'"{reason_display}"',
                f"Calls: {agent.claude_calls:<4} Avg: {avg_lat:.1f}s Falls: {agent.fallbacks}",
                f"HP: {p.hp}/{p.max_hp} ({hp_pct}%) Hunger: {p.hunger:.0f}%",
                f"F{p.floor} K{p.kills} Score:{calculate_score(p, gs):,}",
                "[t]panel [+/-]speed [space]pause [q]uit",
            ]
            for i, line in enumerate(tlines):
                safe_addstr(scr, i, SCREEN_W - len(line) - 1, line,
                           curses.color_pair(C_MAGENTA) if i == 0 else
                           curses.color_pair(C_CYAN))
        scr.refresh()

        # Handle user input
        scr.nodelay(True)
        ck = scr.getch()
        scr.nodelay(False)
        if ck == ord('q'):
            break
        elif ck == ord(' '):
            paused = not paused
            if paused:
                safe_addstr(scr, SCREEN_H // 2, SCREEN_W // 2 - 4, "PAUSED",
                           curses.color_pair(C_YELLOW) | curses.A_BOLD)
                scr.refresh()
                scr.nodelay(False)
                while True:
                    pk = scr.getch()
                    if pk == ord(' ') or pk == ord('q'):
                        paused = False
                        if pk == ord('q'):
                            gs.running = False
                        break
        elif ck == ord('+') or ck == ord('='):
            delay_ms = max(10, delay_ms // 2)
        elif ck == ord('-'):
            delay_ms = min(2000, delay_ms * 2)
        elif ck == ord('t'):
            show_panel = not show_panel
        elif ck == ord('P'):
            pilot_mode = not pilot_mode
            if pilot_mode:
                agent._log("pilot_mode", {"action": "engaged", "turn": gs.turn_count})
            else:
                agent._log("pilot_mode", {"action": "released", "turn": gs.turn_count})

        if not pilot_mode:
            curses.napms(delay_ms)

    # Log game end + health report
    p = gs.player
    agent._post_game_report(gs)
    agent._log("game_end", {
        "victory": gs.victory, "floor": p.floor, "kills": p.kills,
        "turns": gs.turn_count, "score": calculate_score(p, gs),
        "claude_calls": agent.claude_calls, "fallbacks": agent.fallbacks,
        "avg_latency": round(agent.total_latency / agent.claude_calls, 2) if agent.claude_calls > 0 else 0,
        "death_cause": gs.death_cause or ("victory" if gs.victory else "stopped"),
    })
    agent.close_log()

    # Show final screen
    render_game(scr, gs)
    if gs.victory:
        show_enhanced_victory(scr, gs)
    elif gs.game_over:
        show_enhanced_death(scr, gs)
    else:
        safe_addstr(scr, SCREEN_H // 2, 10, f"Agent stopped at turn {gs.turn_count}",
                   curses.color_pair(C_YELLOW) | curses.A_BOLD)
        scr.refresh()
        scr.nodelay(False)
        scr.getch()


def agent_batch_mode(num_games=10, player_class=None):
    """Run multiple agent games headless and print summary stats.

    Args:
        num_games: Number of games to play.
        player_class: Force a class or None for rotation across warrior/mage/rogue.
    """
    CLASSES = ["warrior", "mage", "rogue"]
    # Clear agent log for fresh batch
    try:
        open(AGENT_LOG_PATH, 'w').close()
    except OSError:
        pass

    results = []
    total_claude_calls = 0
    total_claude_latency = 0.0
    total_fallbacks = 0
    batch_tracker = FeatureTracker()

    for i in range(num_games):
        game_class = player_class or CLASSES[i % len(CLASSES)]
        tracker = FeatureTracker()
        tracker.classes_played.add(game_class)
        batch_tracker.classes_played.add(game_class)

        gs = GameState(headless=True, player_class=game_class)
        _init_new_game(gs)
        agent = AgentPlayer(game_id=i + 1)
        agent._log("game_start", {"seed": gs.seed, "mode": "batch", "game_num": i + 1, "total_games": num_games, "class": game_class})
        max_turns = 10000
        max_iterations = max_turns * 3  # Safety: prevent infinite no-turn loops
        iterations = 0

        while gs.running and not gs.game_over and gs.turn_count < max_turns and iterations < max_iterations:
            iterations += 1
            fov_radius = gs.player.get_torch_radius()
            if "Blindness" in gs.player.status_effects:
                fov_radius = 1
            compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
            _update_explored_from_fov(gs)

            # Auto-apply pending level-ups
            while gs.player.pending_levelups:
                auto_apply_levelup(gs.player)

            action, params = agent.decide(gs)
            turn_spent = _bot_execute_action(gs, action, params)

            # Track feature interactions
            action_str = agent.action if hasattr(agent, 'action') else ""
            tracker.check_state(gs, action_str)

            if turn_spent:
                gs.turn_count += 1
                if gs.last_noise > 0:
                    _stealth_detection(gs, gs.last_noise)
                gs.last_noise = 0
                process_enemies(gs)
                process_status(gs)
                if gs.player.hp <= 0:
                    gs.game_over = True

        p = gs.player
        total_claude_calls += agent.claude_calls
        total_claude_latency += agent.total_latency
        total_fallbacks += agent.fallbacks
        avg_lat = agent.total_latency / agent.claude_calls if agent.claude_calls > 0 else 0

        health_report = agent._post_game_report(gs)
        agent._log("game_end", {
            "victory": gs.victory, "floor": p.floor, "kills": p.kills,
            "turns": gs.turn_count, "score": calculate_score(p, gs),
            "claude_calls": agent.claude_calls, "fallbacks": agent.fallbacks,
            "avg_latency": round(avg_lat, 2),
            "death_cause": gs.death_cause or ("victory" if gs.victory else "timeout"),
            "feature_coverage": tracker.coverage_pct(),
        })
        agent.close_log()

        # Merge per-game tracker into batch tracker
        for key, val in tracker.features.items():
            for subkey, subval in val.items():
                if isinstance(subval, bool) and subval:
                    batch_tracker.features[key][subkey] = True
                elif isinstance(subval, int) and subval > batch_tracker.features[key].get(subkey, 0):
                    batch_tracker.features[key][subkey] = subval

        results.append({
            "game": i + 1,
            "class": game_class,
            "victory": gs.victory,
            "floor": p.floor,
            "level": p.level,
            "kills": p.kills,
            "turns": gs.turn_count,
            "score": calculate_score(p, gs),
            "death_cause": gs.death_cause or ("victory" if gs.victory else "timeout"),
            "claude_calls": agent.claude_calls,
            "avg_latency": avg_lat,
            "fallbacks": agent.fallbacks,
            "health_flags": health_report.get("flags", []),
            "calls_per_turn": health_report.get("calls_per_turn", 0),
            "feature_coverage": f"{tracker.coverage_pct():.0%}",
        })
        status = "WIN!" if gs.victory else f"Died F{p.floor}"
        cls_tag = game_class[0].upper()
        flag_str = f"  !! {', '.join(health_report['flags'])}" if health_report.get("flags") else ""
        print(f"  Game {i+1:3d}: [{cls_tag}] {status:<12} Lv{p.level} T{gs.turn_count:5d} K{p.kills:3d} "
              f"Score:{calculate_score(p, gs):5d} Claude:{agent.claude_calls:3d} Avg:{avg_lat:.1f}s "
              f"C/T:{health_report.get('calls_per_turn', 0):.2f}{flag_str}")

    # Summary
    print("\n" + "=" * 60)
    print("AGENT BATCH SUMMARY (Claude-powered)")
    print("=" * 60)
    wins = sum(1 for r in results if r["victory"])
    avg_floor = sum(r["floor"] for r in results) / len(results)
    avg_kills = sum(r["kills"] for r in results) / len(results)
    avg_turns = sum(r["turns"] for r in results) / len(results)
    avg_score = sum(r["score"] for r in results) / len(results)
    max_floor = max(r["floor"] for r in results)
    crash_count = sum(1 for r in results if r["death_cause"] == "timeout")
    avg_calls = total_claude_calls / len(results)
    avg_total_lat = total_claude_latency / total_claude_calls if total_claude_calls > 0 else 0
    print(f"  Games: {num_games}  Wins: {wins}  Win rate: {wins/num_games*100:.0f}%")
    print(f"  Avg floor: {avg_floor:.1f}  Max floor: {max_floor}  Avg kills: {avg_kills:.1f}")
    print(f"  Avg turns: {avg_turns:.0f}  Avg score: {avg_score:.0f}")
    print(f"  Timeouts: {crash_count}")
    print(f"  Claude calls/game: {avg_calls:.0f}  Avg latency: {avg_total_lat:.1f}s  Fallbacks: {total_fallbacks}")
    causes = {}
    for r in results:
        c = r["death_cause"]
        causes[c] = causes.get(c, 0) + 1
    print(f"  Death causes: {causes}")
    # Health monitoring summary
    avg_cpt = sum(r.get("calls_per_turn", 0) for r in results) / len(results)
    flagged_games = [r for r in results if r.get("health_flags")]
    cpt_status = "OK" if avg_cpt <= 0.5 else "HIGH"
    print(f"\n  HEALTH: Avg calls/turn: {avg_cpt:.2f} [{cpt_status}]")
    if flagged_games:
        print(f"  HEALTH: {len(flagged_games)}/{num_games} games flagged:")
        for r in flagged_games:
            print(f"    Game {r['game']} [{r.get('class', '?')[0].upper()}]: {', '.join(r['health_flags'])}")
    else:
        print("  HEALTH: All games clean — no anomalies detected")
    # Feature coverage
    print(f"\n{batch_tracker.report()}")
    return results


def _bot_execute_action(gs, action, params):
    """Execute a bot action on the game state. Returns True if turn was spent."""
    p = gs.player
    if action == "move":
        return player_move(gs, params["dx"], params["dy"])
    elif action == "rest":
        if p.hp < p.max_hp and p.hunger > B["rest_hunger_threshold"]:
            p.hp = min(p.max_hp, p.hp + B["rest_hp_per_turn"])
        p.hunger = max(0, p.hunger - B["rest_wait_hunger_cost"])
        return True
    elif action == "use_item":
        item = params["item"]
        if params["type"] == "potion":
            use_potion(gs, item)
        elif params["type"] == "food":
            use_food(gs, item)
        return True
    elif action == "cast_spell":
        spell = params["spell"]
        if spell == "Heal":
            cast_spell_headless(gs, "Heal")
        elif spell == "Fireball":
            cast_spell_headless(gs, "Fireball", direction=(params.get("dx", 0), params.get("dy", 0)))
        elif spell == "Freeze":
            cast_spell_headless(gs, "Freeze", target_enemy=params.get("target"))
        elif spell == "Lightning Bolt":
            cast_spell_headless(gs, "Lightning Bolt", direction=(params.get("dx", 0), params.get("dy", 0)))
        elif spell == "Chain Lightning":
            cast_spell_headless(gs, "Chain Lightning", target_enemy=params.get("target"))
        elif spell == "Meteor":
            cast_spell_headless(gs, "Meteor", direction=(params.get("dx", 0), params.get("dy", 0)))
        elif spell == "Mana Shield":
            cast_spell_headless(gs, "Mana Shield")
        elif spell == "Teleport":
            cast_spell_headless(gs, "Teleport")
        return True
    elif action == "fire":
        return fire_projectile_headless(gs, params["dx"], params["dy"])
    elif action == "descend":
        if p.floor < MAX_FLOORS:
            new_floor = p.floor + 1
            if new_floor in BRANCH_CHOICES and new_floor not in gs.branch_choices:
                _choose_branch_headless(gs, new_floor)
            gs.generate_floor(new_floor)
            return True
        elif p.floor == MAX_FLOORS:
            if not any(e.boss and e.etype == "dread_lord" and e.is_alive() for e in gs.enemies):
                gs.victory = True
                gs.game_over = True
                return True
        return False
    elif action == "pickup":
        pickup = [i for i in gs.items if i.x == p.x and i.y == p.y]
        for item in pickup:
            if item.item_type == "gold":
                p.gold += item.data["amount"]
                gs.items.remove(item)
            elif len(p.inventory) < p.carry_capacity:
                gs.items.remove(item)
                p.inventory.append(item)
                p.items_found += 1
        return bool(pickup)
    elif action == "pray":
        pray_at_shrine(gs)
        return True
    elif action == "equip":
        item = params["item"]
        if item.item_type == "weapon":
            if p.weapon:
                p.weapon.equipped = False
            item.equipped = True
            p.weapon = item
        elif item.item_type == "armor":
            if p.armor:
                p.armor.equipped = False
            item.equipped = True
            p.armor = item
        elif item.item_type == "ring":
            if p.ring:
                p.ring.equipped = False
            item.equipped = True
            p.ring = item
        elif item.item_type == "bow":
            if p.bow:
                p.bow.equipped = False
            item.equipped = True
            p.bow = item
        return False  # Equipping doesn't spend a turn
    elif action == "toggle_torch":
        p.torch_lit = not p.torch_lit
        return False
    elif action == "use_ability":
        return use_ability_headless(gs, params["ability"])
    elif action == "use_alchemy":
        return use_alchemy_table(gs)
    elif action == "interact_pedestal":
        return _interact_pedestal(gs, p.x, p.y)
    elif action == "grab_wall_torch":
        for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
            tx, ty = p.x + ddx, p.y + ddy
            if 0 <= tx < MAP_W and 0 <= ty < MAP_H and gs.tiles[ty][tx] == T_WALL_TORCH:
                gs.tiles[ty][tx] = T_WALL
                if (tx, ty) in gs.wall_torches:
                    gs.wall_torches.remove((tx, ty))
                torch_item = Item(0, 0, "torch", "Torch",
                                {"name": "Torch", "char": '(', "fuel": 60, "desc": "Taken from wall."})
                p.inventory.append(torch_item)
                gs.msg("You take a torch from the wall.", C_YELLOW)
                return True
        return False
    return False


def bot_game_loop(scr, speed=0.08, max_turns=5000):
    """Run a bot-controlled game visually in the terminal."""
    curses.curs_set(0)
    scr.nodelay(False)
    scr.keypad(True)
    init_colors()

    gs = GameState(player_class="warrior")
    gs._scr = scr
    _init_new_game(gs)
    bot = BotPlayer()
    show_telemetry = True
    paused = False
    delay_ms = max(10, int(speed * 1000))

    while gs.running and not gs.game_over and gs.turn_count < max_turns:
        fov_radius = gs.player.get_torch_radius()
        if "Blindness" in gs.player.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        _update_explored_from_fov(gs)

        # Auto-apply pending level-ups
        while gs.player.pending_levelups:
            auto_apply_levelup(gs.player)

        action, params = bot.decide(gs)
        turn_spent = _bot_execute_action(gs, action, params)

        if turn_spent:
            gs.turn_count += 1
            if gs.last_noise > 0:
                _stealth_detection(gs, gs.last_noise)
            gs.last_noise = 0
            process_enemies(gs)
            process_status(gs)
            if gs.player.hp <= 0:
                gs.game_over = True

        # Re-compute FOV after action for rendering
        fov_radius = gs.player.get_torch_radius()
        if "Blindness" in gs.player.status_effects:
            fov_radius = 1
        compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
        _update_explored_from_fov(gs)
        render_game(scr, gs)

        # Telemetry overlay
        if show_telemetry:
            p = gs.player
            hp_pct = int(p.hp / p.max_hp * 100) if p.max_hp > 0 else 0
            tlines = [
                "BOT TELEMETRY",
                f"Turn: {gs.turn_count:<6} Speed: {1000/max(1,delay_ms):.0f} fps",
                f"Strategy: {bot.strategy:<10} Target: {bot.target_desc[:14]}",
                f"HP: {p.hp}/{p.max_hp} ({hp_pct}%) Hunger: {p.hunger:.0f}%",
                f"Floor: {p.floor}  Kills: {p.kills}  Lv: {p.level}",
                f"Gold: {p.gold}  Items: {len(p.inventory)}/{p.carry_capacity}",
                "[t]elemetry [+/-]speed [space]pause [q]uit",
            ]
            for i, line in enumerate(tlines):
                safe_addstr(scr, i, SCREEN_W - len(line) - 1, line,
                           curses.color_pair(C_CYAN) if i > 0 else
                           curses.color_pair(C_CYAN) | curses.A_BOLD)
        scr.refresh()

        # Handle user input
        scr.nodelay(True)
        ck = scr.getch()
        scr.nodelay(False)
        if ck == ord('q'):
            break
        elif ck == ord(' '):
            paused = not paused
            if paused:
                safe_addstr(scr, SCREEN_H // 2, SCREEN_W // 2 - 4, "PAUSED",
                           curses.color_pair(C_YELLOW) | curses.A_BOLD)
                scr.refresh()
                scr.nodelay(False)
                while True:
                    pk = scr.getch()
                    if pk == ord(' ') or pk == ord('q'):
                        paused = False
                        if pk == ord('q'):
                            gs.running = False
                        break
        elif ck == ord('+') or ck == ord('='):
            delay_ms = max(10, delay_ms // 2)
        elif ck == ord('-'):
            delay_ms = min(1000, delay_ms * 2)
        elif ck == ord('t'):
            show_telemetry = not show_telemetry

        curses.napms(delay_ms)

    # Show final screen
    render_game(scr, gs)
    if gs.victory:
        show_enhanced_victory(scr, gs)
    elif gs.game_over:
        show_enhanced_death(scr, gs)
    else:
        safe_addstr(scr, SCREEN_H // 2, 10, f"Bot stopped at turn {gs.turn_count}",
                   curses.color_pair(C_YELLOW) | curses.A_BOLD)
        scr.refresh()
        scr.nodelay(False)
        scr.getch()


def bot_batch_mode(num_games=10, player_class=None):
    """Run multiple bot games headless and print summary stats.

    Args:
        num_games: Number of games to play.
        player_class: Force a class ("warrior"/"mage"/"rogue") or None for rotation.
    """
    CLASSES = ["warrior", "mage", "rogue"]
    results = []
    crashes = []
    for i in range(num_games):
        game_class = player_class or CLASSES[i % len(CLASSES)]
        try:
            gs = GameState(headless=True, player_class=game_class)
            _init_new_game(gs)
            bot = BotPlayer()
            max_turns = 10000
            max_iterations = max_turns * 3  # Safety: prevent infinite no-turn loops

            iterations = 0
            while gs.running and not gs.game_over and gs.turn_count < max_turns and iterations < max_iterations:
                iterations += 1
                fov_radius = gs.player.get_torch_radius()
                if "Blindness" in gs.player.status_effects:
                    fov_radius = 1
                compute_fov(gs.tiles, gs.player.x, gs.player.y, fov_radius, gs.visible)
                _update_explored_from_fov(gs)

                # Auto-apply pending level-ups
                while gs.player.pending_levelups:
                    auto_apply_levelup(gs.player)

                action, params = bot.decide(gs)
                turn_spent = _bot_execute_action(gs, action, params)

                if turn_spent:
                    gs.turn_count += 1
                    if gs.last_noise > 0:
                        _stealth_detection(gs, gs.last_noise)
                    gs.last_noise = 0
                    process_enemies(gs)
                    process_status(gs)
                    if gs.player.hp <= 0:
                        gs.game_over = True

            p = gs.player
            result = {
                "game": i + 1,
                "class": game_class,
                "victory": gs.victory,
                "floor": p.floor,
                "level": p.level,
                "kills": p.kills,
                "turns": gs.turn_count,
                "score": calculate_score(p, gs),
                "death_cause": gs.death_cause or ("victory" if gs.victory else "timeout"),
                "locked_stairs": gs.tiles[gs.stair_down[1]][gs.stair_down[0]] == T_STAIRS_LOCKED,
                "puzzles": len(gs.puzzles),
                "puzzles_solved": sum(1 for pz in gs.puzzles if pz["solved"]),
            }
            results.append(result)
            cls_tag = game_class[0].upper()
            status = "WIN!" if gs.victory else f"Died F{p.floor}"
            flags = ""
            if result["locked_stairs"]:
                flags += " [LOCKED]"
            print(f"  Game {i+1:3d}: [{cls_tag}] {status:<12} Lv{p.level} T{gs.turn_count:5d} K{p.kills:3d} Score:{calculate_score(p, gs)}{flags}")

        except Exception as exc:
            import traceback
            crash = {
                "game": i + 1,
                "class": game_class,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            crashes.append(crash)
            print(f"  Game {i+1:3d}: [{game_class[0].upper()}] CRASH: {exc}")

    # Summary
    print("\n" + "=" * 50)
    print("BOT BATCH SUMMARY")
    print("=" * 50)
    if results:
        wins = sum(1 for r in results if r["victory"])
        avg_floor = sum(r["floor"] for r in results) / len(results)
        avg_kills = sum(r["kills"] for r in results) / len(results)
        avg_turns = sum(r["turns"] for r in results) / len(results)
        avg_score = sum(r["score"] for r in results) / len(results)
        max_floor = max(r["floor"] for r in results)
        timeout_count = sum(1 for r in results if r["death_cause"] == "timeout")
        locked_count = sum(1 for r in results if r.get("locked_stairs"))
        print(f"  Games: {num_games}  Wins: {wins}  Win rate: {wins/len(results)*100:.0f}%")
        print(f"  Avg floor: {avg_floor:.1f}  Max floor: {max_floor}  Avg kills: {avg_kills:.1f}")
        print(f"  Avg turns: {avg_turns:.0f}  Avg score: {avg_score:.0f}")
        print(f"  Timeouts: {timeout_count}  Locked stairs encounters: {locked_count}")
        # Per-class breakdown
        for cls in CLASSES:
            cls_results = [r for r in results if r["class"] == cls]
            if cls_results:
                cls_avg_floor = sum(r["floor"] for r in cls_results) / len(cls_results)
                cls_avg_kills = sum(r["kills"] for r in cls_results) / len(cls_results)
                print(f"    {cls.capitalize():8s}: {len(cls_results)} games, avg F{cls_avg_floor:.1f}, avg K{cls_avg_kills:.0f}")
        # Death causes
        causes = {}
        for r in results:
            c = r["death_cause"]
            causes[c] = causes.get(c, 0) + 1
        print(f"  Death causes: {causes}")
    if crashes:
        print(f"  CRASHES: {len(crashes)}")
        for c in crashes:
            print(f"    Game {c['game']} [{c['class']}]: {c['error']}")
    return results


# ============================================================
# TESTS
# ============================================================

def test_connectivity(n=50):
    print(f"[1] Dungeon Connectivity ({n} dungeons)...")
    fails = 0
    for _ in range(n):
        floor = random.randint(1, MAX_FLOORS)
        tiles, _, start, _ = generate_dungeon(floor)
        w = count_walkable(tiles)
        r = flood_fill_count(tiles, start[0], start[1])
        if w == 0 or r / w < 0.95:
            fails += 1
            print(f"  FAIL floor {floor}: {r}/{w} ({r/w:.1%})")
    print(f"  Result: {n-fails}/{n} passed")
    return fails == 0


def test_enemies():
    print("[2] Enemy Spawning...")
    gs = GameState()
    seen = set()
    for f in range(1, MAX_FLOORS+1):
        gs.generate_floor(f)
        for e in gs.enemies:
            seen.add(e.etype)
    non_boss = {k for k, v in ENEMY_TYPES.items() if not v.get("boss")}
    missing = non_boss - seen
    print(f"  Spawned: {len(seen)}/{len(ENEMY_TYPES)} types")
    if missing:
        print(f"  FAIL: Missing non-boss: {missing}")
        return False
    print("  Result: PASS")
    return True


def test_items():
    print("[3] Item Generation...")
    gs = GameState()
    seen = set()
    for f in range(1, MAX_FLOORS+1):
        gs.generate_floor(f)
        for item in gs.items:
            seen.add(item.item_type)
        for _, si_list in gs.shops:
            for si in si_list:
                seen.add(si.item.item_type)
    expected = {"weapon", "armor", "potion", "scroll", "gold", "food", "ring"}
    missing = expected - seen
    print(f"  Types: {len(seen & expected)}/{len(expected)}")
    if missing:
        print(f"  FAIL: Missing: {missing}")
        return False
    print("  Result: PASS")
    return True


def run_tests():
    print("=" * 50)
    print("DEPTHS OF DREAD - Test Suite")
    print("=" * 50)
    t1 = test_connectivity(50)
    t2 = test_enemies()
    t3 = test_items()
    print("=" * 50)
    print("ALL TESTS PASSED" if all([t1, t2, t3]) else "SOME TESTS FAILED")
    print("=" * 50)
    return all([t1, t2, t3])


def _parse_args():
    parser = argparse.ArgumentParser(description="Depths of Dread - A Terminal Roguelike")
    parser.add_argument("--test", action="store_true", help="Run built-in tests")
    parser.add_argument("--bot", action="store_true", help="Watch AI bot play")
    parser.add_argument("--agent", action="store_true", help="Watch Claude-powered agent play")
    parser.add_argument("--games", type=int, default=0, help="Bot/agent batch mode: run N games headless")
    parser.add_argument("--replay", type=str, default="", help="Replay a recorded session")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay/bot speed multiplier")
    parser.add_argument("--recordings", action="store_true", help="List saved recordings")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.test:
        sys.exit(0 if run_tests() else 1)
    elif args.recordings:
        list_recordings()
    elif args.agent:
        if args.games > 0:
            agent_batch_mode(args.games)
        else:
            curses.wrapper(lambda scr: agent_game_loop(scr, speed=args.speed))
    elif args.bot:
        if args.games > 0:
            bot_batch_mode(args.games)
        else:
            curses.wrapper(lambda scr: bot_game_loop(scr, speed=args.speed))
    elif args.replay:
        filepath = args.replay
        if not os.path.exists(filepath):
            # Try in recordings dir
            alt = os.path.join(RECORDINGS_DIR, filepath)
            if os.path.exists(alt):
                filepath = alt
            else:
                print(f"Recording not found: {filepath}")
                sys.exit(1)
        curses.wrapper(lambda scr: replay_session(scr, filepath, speed=args.speed))
    else:
        main()
