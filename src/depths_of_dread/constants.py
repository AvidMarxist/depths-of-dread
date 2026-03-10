from __future__ import annotations

import curses
import os
from typing import Any

# ============================================================
# CONSTANTS
# ============================================================

MAP_W: int = 80
MAP_H: int = 40
SCREEN_W: int = 80
SCREEN_H: int = 24
VIEW_W: int = 58
VIEW_H: int = 20
MSG_H: int = 3
STAT_X: int = 59
MAX_FLOORS: int = 20
MAX_MESSAGES: int = 50
FOV_RADIUS: int = 8
MAX_INVENTORY: int = 20
TORCH_MAX_FUEL: int = 200
TORCH_RADIUS_FULL: int = 8    # fuel > 50%
TORCH_RADIUS_HALF: int = 6    # fuel 25-50%
TORCH_RADIUS_QUARTER: int = 4 # fuel 1-25%
TORCH_RADIUS_EMPTY: int = 2   # fuel == 0
MANA_REGEN_INTERVAL: int = 3  # regen 1 mana every N turns (was 5)
AUTO_FIGHT_HP_THRESHOLD: float = 0.3  # stop auto-fight when HP below 30% of max
AUTO_EXPLORE_HP_THRESHOLD: float = 0.5  # stop auto-explore when HP below 50%
REST_HUNGER_THRESHOLD: int = 20  # stop resting when hunger below 20%
SAVE_FILE_PATH: str = os.path.expanduser("~/.depths_of_dread_save.json")
STATS_FILE_PATH: str = os.path.expanduser("~/.depths_of_dread_stats.json")
RECORDINGS_DIR: str = os.path.expanduser("~/.depths_of_dread_recordings/")
AGENT_LOG_PATH: str = os.path.expanduser("~/.depths_of_dread_agent.log")
SIDEBAR_NAME_WIDTH: int = 18  # width for equipment names in sidebar
MIN_TERMINAL_W: int = 80
MIN_TERMINAL_H: int = 24

# ============================================================
# BALANCE TUNING — Edit these to adjust difficulty
# ============================================================
BALANCE: dict[str, Any] = {
    # --- Item Spawn Weights (relative, auto-normalized) ---
    "item_weights": {
        "weapon": 14,
        "armor": 11,
        "potion": 15,      # was 18, briefly 12 (too harsh early game)
        "scroll": 10,      # was 14
        "food": 20,        # was 22, briefly 15 (too harsh — floor 1-2 starvation)
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
    "guaranteed_food_min": 2,  # Restored from 1 — floor 1-2 starvation
    "guaranteed_food_max": 3,  # Restored from 2

    # --- Enemy Spawn Counts ---
    "enemies_base": 5,
    "enemies_per_floor": 2,
    "enemies_random_bonus": 3,
    "enemy_hp_scale_per_floor": 0.18,  # +18% HP per floor beyond min (was 0.10)
    "enemy_dmg_scale_per_floor": 0.08, # +8% damage per floor beyond min (NEW)
    "enemy_def_scale_per_floor": 0.3,  # +0.3 defense per floor beyond min (NEW)

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
    "heal_potion_min": 10,    # was 15
    "heal_potion_max": 20,    # was 30
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
    "enemy_gold_drop_chance": 0.30,  # was 0.50
    "gold_drop_min": 2,              # was 3
    "gold_drop_max": 6,              # was 10
    "gold_per_floor_min": 3,         # was 5
    "gold_per_floor_max": 8,         # was 15
    "gold_piles_min": 1,             # was 2
    "gold_piles_max": 3,             # was 5

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

    # --- Expansion Status Effects ---
    "bleed_damage_per_tick": 1,
    "bleed_duration": 6,
    "bleed_max_stacks": 5,
    "frozen_status_duration": 2,
    "frozen_shatter_bonus": 2.0,
    "silence_duration": 8,
    "blindness_fov_override": 1,

    # --- Boss Phase Thresholds ---
    "boss_phase2_threshold": 0.50,
    "boss_phase3_threshold": 0.25,
    "vampire_phase2_lifesteal_mult": 2.0,
    "vampire_phase3_bat_interval": 4,
    "dread_phase2_dmg_mult": 2.0,
    "dread_phase3_aoe_damage": 5,
    "mini_boss_phase2_threshold": 0.40,
    # --- Apex Enemy Balance ---
    "apex_spawn_chance": 0.15,           # Chance for apex enemy on eligible floors
    "breath_weapon_damage_base": 12,
    "breath_weapon_damage_per_floor": 2,
    "stun_duration": 2,
    "hydra_multi_attack_dmg_mult": 0.6,  # Each hydra head does 60% damage
    # --- Branch Floor Mechanics ---
    "flooded_crypts_water_dmg": 1,       # Cold damage per turn in water
    "burning_pits_lava_proximity": 2,    # Lava hurts at this Manhattan distance
    "burning_pits_heat_dmg": 2,          # Heat damage per turn near lava
    "mind_halls_confusion_chance": 0.08, # Per-turn confusion chance in Mind Halls
    "beast_warrens_trap_detect_penalty": 4, # Harder to detect traps
    # --- Puzzle Room Rewards ---
    "puzzle_room_gold_min": 30,
    "puzzle_room_gold_max": 80,
    # --- Enchantment System ---
    "enchant_gold_cost": 100,
    "enchant_anvil_min_floor": 6,
    "enchant_anvil_chance": 0.20,

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
    "trap_damage_scale_per_floor": 0.15,  # +15% trap damage per floor

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

# Difficulty presets — multipliers applied to BALANCE values
DIFFICULTY_PRESETS: dict[str, dict[str, float]] = {
    "easy":   {"enemy_hp_mult": 0.7, "enemy_dmg_mult": 0.7, "item_mult": 1.3, "food_mult": 1.5, "xp_mult": 1.3, "gold_mult": 1.5},
    "normal": {"enemy_hp_mult": 1.0, "enemy_dmg_mult": 1.0, "item_mult": 1.0, "food_mult": 1.0, "xp_mult": 1.0, "gold_mult": 1.0},
    "hard":   {"enemy_hp_mult": 1.4, "enemy_dmg_mult": 1.3, "item_mult": 0.8, "food_mult": 0.7, "xp_mult": 0.8, "gold_mult": 0.7},
}

# Short alias for tight code paths
B: dict[str, Any] = BALANCE

# Spell definitions
SPELLS: dict[str, dict[str, Any]] = {
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
BASE_SPELLS: set[str] = {name for name, info in SPELLS.items() if not info["mage_only"]}

# Default known spells per class
CLASS_KNOWN_SPELLS: dict[str, set[str]] = {
    "warrior": {"Heal", "Teleport"},
    "mage":    {"Heal", "Teleport", "Fireball", "Lightning Bolt", "Freeze", "Chain Lightning"},
    "rogue":   {"Heal", "Teleport", "Fireball"},
}

# Spell unlock order when choosing Arcana at levelup
SPELL_UNLOCK_ORDER: dict[str | None, list[str]] = {
    "warrior": ["Lightning Bolt", "Freeze"],
    "mage":    ["Meteor", "Mana Shield"],
    "rogue":   ["Lightning Bolt", "Freeze"],
    None:      [],  # classless already knows all base spells
}

# Class-exclusive combat abilities (Warrior/Rogue — parallel to Mage spells)
CLASS_ABILITIES: dict[str, dict[str, dict[str, Any]]] = {
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
ABILITY_UNLOCK_ORDER: dict[str | None, list[str]] = {
    "warrior": ["Whirlwind", "Cleaving Strike", "Shield Wall"],
    "rogue":   ["Backstab", "Poison Blade", "Smoke Bomb"],
    "mage":    [],
    None:      [],
}

# Character Classes (D&D Expansion Phase 1)
CHARACTER_CLASSES: dict[str, dict[str, Any]] = {
    "warrior": {
        "name": "Warrior", "desc": "Tough frontline fighter with Battle Cry",
        "hp": 40, "mp": 10, "str": 7, "defense": 3,
        "crit_bonus": 0, "evasion_bonus": 0,
        "ability": "Battle Cry", "ability_desc": "Freeze all nearby enemies for 5 turns",
        "ability_cost": 8,
        "level_hp": (3, 7), "level_mp": (1, 3), "level_str": 1, "level_def": 1,
    },
    "mage": {
        "name": "Mage", "desc": "Glass cannon with powerful Arcane Blast",
        "hp": 20, "mp": 35, "str": 3, "defense": 0,
        "crit_bonus": 0, "evasion_bonus": 0,
        "ability": "Arcane Blast", "ability_desc": "3x3 AoE magical explosion at range",
        "ability_cost": 15,
        "level_hp": (3, 6), "level_mp": (3, 7), "level_str": 1, "level_def": 0,
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
T_WALL: int = 0
T_FLOOR: int = 1
T_CORRIDOR: int = 2
T_DOOR: int = 3
T_STAIRS_DOWN: int = 4
T_STAIRS_UP: int = 5
T_WATER: int = 6
T_LAVA: int = 7
T_SHOP_FLOOR: int = 8
T_SHRINE: int = 9
T_ALCHEMY_TABLE: int = 10
T_WALL_TORCH: int = 11
T_PEDESTAL_UNLIT: int = 12
T_PEDESTAL_LIT: int = 13
T_SWITCH_OFF: int = 14
T_SWITCH_ON: int = 15
T_STAIRS_LOCKED: int = 16
T_TRAP_HIDDEN: int = 17    # Invisible trap (renders as T_FLOOR)
T_TRAP_VISIBLE: int = 18   # Revealed trap (renders as '^')
T_ENCHANT_ANVIL: int = 19  # Enchanting station (Phase 4)
T_FOUNTAIN: int = 20       # Healing fountain
T_SECRET_WALL: int = 21    # Hidden wall (looks like T_WALL until searched)

TILE_CHARS: dict[int, str] = {
    T_WALL: '#', T_FLOOR: '.', T_CORRIDOR: '.', T_DOOR: '+',
    T_STAIRS_DOWN: '>', T_STAIRS_UP: '<', T_WATER: '~',
    T_LAVA: '~', T_SHOP_FLOOR: '.', T_SHRINE: '_',
    T_ALCHEMY_TABLE: '&', T_WALL_TORCH: '!',
    T_PEDESTAL_UNLIT: '*', T_PEDESTAL_LIT: '*',
    T_SWITCH_OFF: '!', T_SWITCH_ON: '$',
    T_STAIRS_LOCKED: 'X',
    T_TRAP_HIDDEN: '.',   # Looks like floor
    T_TRAP_VISIBLE: '^',  # Revealed trap
    T_ENCHANT_ANVIL: '&', # Enchanting station
    T_FOUNTAIN: '{',      # Healing fountain
    T_SECRET_WALL: '#',   # Looks like a normal wall
}

WALKABLE: set[int] = {T_FLOOR, T_CORRIDOR, T_DOOR, T_STAIRS_DOWN, T_STAIRS_UP,
            T_WATER, T_SHOP_FLOOR, T_SHRINE, T_ALCHEMY_TABLE,
            T_PEDESTAL_UNLIT, T_PEDESTAL_LIT, T_SWITCH_OFF, T_SWITCH_ON,
            T_TRAP_HIDDEN, T_TRAP_VISIBLE, T_ENCHANT_ANVIL, T_FOUNTAIN}

THEMES: list[str] = [
    "Dungeon", "Dungeon", "Dungeon",
    "Caverns", "Caverns", "Caverns",
    "Catacombs", "Catacombs", "Catacombs",
    "Hellvault", "Hellvault", "Hellvault",
    "Abyss", "Abyss", "The Throne of Dread",
    # Post-boss Abyss floors (Phase 4)
    "The Shattered Depths", "The Void Between",
    "The Forgotten Realm", "The Final Descent",
    "The Heart of Darkness",
]

# Dungeon Branch system — branching paths at floors 5 and 10
BRANCH_DEFS: dict[str, dict[str, Any]] = {
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
    # --- Phase 3 New Branch Pairs ---
    "fungal_depths": {
        "name": "The Fungal Depths",
        "desc": "Poisonous spores, mushroom enemies, low visibility",
        "theme": "Fungal Depths",
        "floors": (3, 4),
        "water_boost": 1.0,
        "lava_boost": 0.0,
        "enemy_pool": ["centipede", "rat", "phase_spider"],
        "mini_boss_floor": 4,
        "mini_boss": "fungal_queen",
    },
    "trapped_halls": {
        "name": "The Trapped Halls",
        "desc": "Dense traps, mechanical enemies, hidden passages",
        "theme": "Trapped Halls",
        "floors": (3, 4),
        "water_boost": 0.0,
        "lava_boost": 0.0,
        "enemy_pool": ["goblin", "skeleton", "archer"],
        "extra_traps": 5,
        "mini_boss_floor": 4,
        "mini_boss": "trap_master",
    },
    "void_rift": {
        "name": "The Void Rift",
        "desc": "Reality tears, psychic storms, teleporting enemies",
        "theme": "Void Rift",
        "floors": (14,),
        "water_boost": 0.5,
        "lava_boost": 0.5,
        "enemy_pool": ["mind_flayer", "wraith", "phase_spider", "shadow_wyrm"],
        "mini_boss_floor": 14,
        "mini_boss": "void_herald",
    },
    "infernal_forge": {
        "name": "The Infernal Forge",
        "desc": "Molten metal, fire damage, powerful but slow enemies",
        "theme": "Infernal Forge",
        "floors": (14,),
        "water_boost": 0.0,
        "lava_boost": 4.0,
        "enemy_pool": ["demon", "fire_elemental", "troll", "ancient_dragon"],
        "mini_boss_floor": 14,
        "mini_boss": "inferno_king",
    },
}

# Branch choice mapping: floor → (branch_A, branch_B)
BRANCH_CHOICES: dict[int, tuple[str, str]] = {
    2: ("fungal_depths", "trapped_halls"),
    5: ("flooded_crypts", "burning_pits"),
    10: ("mind_halls", "beast_warrens"),
    13: ("void_rift", "infernal_forge"),
}

# ============================================================
# COLOR PAIRS
# ============================================================
C_WHITE: int = 1
C_RED: int = 2
C_GREEN: int = 3
C_BLUE: int = 4
C_YELLOW: int = 5
C_MAGENTA: int = 6
C_CYAN: int = 7
C_DARK: int = 8
C_GOLD: int = 9
C_LAVA: int = 10
C_WATER: int = 11
C_PLAYER: int = 12
C_UI: int = 13
C_TITLE: int = 14
C_BOSS: int = 15
C_SHRINE: int = 16

# Challenge mode configuration (Phase 4)
_CHALLENGE_MODES: dict[str, bool] = {"ironman": False, "speedrun": False, "pacifist": False, "dark": False}

HAS_COLORS: bool = True  # set at runtime by init_colors

def init_colors() -> None:
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


def safe_color_pair(pair_num: int) -> int:
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

WEAPON_TYPES: list[dict[str, Any]] = [
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
BOSS_DROPS: dict[str, dict[str, Any]] = {
    "ogre_king": {"name": "Ogre King's Maul", "char": ')', "dmg": (8,16), "speed": 0.6, "bonus": 2, "desc": "Massive and devastating.", "tier": 5},
    "vampire_lord": {"name": "Vampiric Blade", "char": ')', "dmg": (6,14), "speed": 1.1, "bonus": 3, "desc": "Drains life with each strike.", "tier": 5, "lifesteal": True},
    "dread_lord": {"name": "Dread Lord's Bane", "char": ')', "dmg": (10,20), "speed": 1.0, "bonus": 5, "desc": "Forged from pure dread.", "tier": 5},
    "abyssal_horror": {"name": "Void Reaver", "char": ')', "dmg": (14,28), "speed": 1.0, "bonus": 7, "desc": "A blade forged from collapsed reality.", "tier": 6},
}

ARMOR_TYPES: list[dict[str, Any]] = [
    {"name": "Torn Rags",       "char": '[', "defense": 0,  "desc": "Barely clothing.", "tier": 0},
    {"name": "Leather Armor",   "char": '[', "defense": 2,  "desc": "Supple and light.", "tier": 1},
    {"name": "Studded Leather", "char": '[', "defense": 3,  "desc": "Reinforced with studs.", "tier": 1},
    {"name": "Chain Mail",      "char": '[', "defense": 5,  "desc": "Clinks with every step.", "tier": 2},
    {"name": "Scale Mail",      "char": '[', "defense": 6,  "desc": "Overlapping scales.", "tier": 2},
    {"name": "Plate Armor",     "char": '[', "defense": 8,  "desc": "Heavy but formidable.", "tier": 3},
    {"name": "Mithril Mail",    "char": '[', "defense": 7,  "desc": "Light as silk, hard as dragon scale.", "tier": 4},
    {"name": "Dread Plate",     "char": '[', "defense": 10, "desc": "Forged in the abyss.", "tier": 5},
]

POTION_EFFECTS: list[str] = ["Healing", "Strength", "Speed", "Poison", "Blindness", "Experience", "Resistance", "Berserk", "Mana"]
POTION_COLORS: list[str] = ["Red", "Blue", "Green", "Murky", "Glowing", "Bubbling", "Shimmering", "Dark", "Azure"]

SCROLL_EFFECTS: list[str] = ["Identify", "Teleport", "Fireball", "Mapping", "Enchant", "Fear", "Summon", "Lightning"]
SCROLL_LABELS: list[str] = ["XYZZY", "PLUGH", "ABRACADABRA", "KLAATU", "LOREM", "IPSUM", "NIHIL", "VERITAS"]

FOOD_TYPES: list[dict[str, Any]] = [
    {"name": "Stale Bread",   "char": '%', "nutrition": 15, "desc": "Hard but edible."},
    {"name": "Dried Meat",    "char": '%', "nutrition": 25, "desc": "Tough and salty."},
    {"name": "Elven Waybread","char": '%', "nutrition": 40, "desc": "Sustaining and light."},
    {"name": "Mystery Meat",  "char": '%', "nutrition": 20, "desc": "Don't ask."},
]

RING_TYPES: list[dict[str, Any]] = [
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
BOW_TYPES: list[dict[str, Any]] = [
    {"name": "Short Bow",   "char": '}', "dmg": (2,5),  "range": 6,  "bonus": 0, "desc": "Simple but functional.", "tier": 1},
    {"name": "Long Bow",    "char": '}', "dmg": (3,8),  "range": 8,  "bonus": 1, "desc": "Greater range and power.", "tier": 2},
    {"name": "Elven Bow",   "char": '}', "dmg": (4,10), "range": 10, "bonus": 3, "desc": "Whisper-light, deadly.", "tier": 4},
]

WAND_TYPES: list[dict[str, Any]] = [
    {"name": "Wand of Fire",      "char": '/', "dmg": (5,12),  "charges": 8,  "desc": "Shoots fire bolts.", "tier": 2},
    {"name": "Wand of Frost",     "char": '/', "dmg": (4,10),  "charges": 10, "desc": "Chilling bolts.", "tier": 2},
    {"name": "Wand of Lightning", "char": '/', "dmg": (6,15),  "charges": 5,  "desc": "Crackling energy.", "tier": 3},
]

TORCH_TYPES: list[dict[str, Any]] = [
    {"name": "Torch",        "char": '(', "fuel": 80,  "desc": "A wooden torch."},
    {"name": "Lantern Oil",  "char": '(', "fuel": 50,  "desc": "Oil for your light."},
    {"name": "Magic Candle", "char": '(', "fuel": 120, "desc": "Burns with arcane flame."},
]

THROWING_DAGGER: dict[str, Any] = {"name": "Throwing Dagger", "char": ')', "dmg": (3,7), "desc": "Balanced for throwing.", "tier": 1}
ARROW_ITEM: dict[str, Any] = {"name": "Arrow", "char": '|', "count": 5, "desc": "A bundle of arrows."}

# ============================================================
# ENEMY DATA
# ============================================================

ENEMY_TYPES: dict[str, dict[str, Any]] = {
    "rat":         {"name": "Rat",          "char": 'r', "color": C_DARK,    "hp": 6,   "dmg": (1,3),  "defense": 0, "xp": 5,    "speed": 1.2, "ai": "chase",    "min_floor": 1,  "max_floor": 5,  "flee_threshold": 0.15},
    "bat":         {"name": "Bat",          "char": 'b', "color": C_MAGENTA, "hp": 4,   "dmg": (1,2),  "defense": 0, "xp": 3,    "speed": 1.5, "ai": "erratic",  "min_floor": 1,  "max_floor": 6,  "flee_threshold": 0.2},
    "goblin":      {"name": "Goblin",       "char": 'g', "color": C_GREEN,   "hp": 12,  "dmg": (2,5),  "defense": 1, "xp": 15,   "speed": 1.0, "ai": "chase",    "min_floor": 1,  "max_floor": 8,  "flee_threshold": 0.15},
    "skeleton":    {"name": "Skeleton",     "char": 's', "color": C_WHITE,   "hp": 18,  "dmg": (3,6),  "defense": 2, "xp": 25,   "speed": 0.8, "ai": "patrol",   "min_floor": 3,  "max_floor": 10, "flee_threshold": 0.0},
    "orc":         {"name": "Orc",          "char": 'o', "color": C_RED,     "hp": 25,  "dmg": (3,8),  "defense": 3, "xp": 35,   "speed": 0.9, "ai": "pack",     "min_floor": 4,  "max_floor": 11, "flee_threshold": 0.2, "bleed_chance": 0.20},
    "wraith":      {"name": "Wraith",       "char": 'W', "color": C_CYAN,    "hp": 30,  "dmg": (4,8),  "defense": 2, "xp": 50,   "speed": 1.0, "ai": "ambush",   "min_floor": 6,  "max_floor": 13, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["cold", "poison"], "vulnerable": ["fire"], "freeze_status_chance": 0.25},
    "archer":      {"name": "Dark Archer",  "char": 'A', "color": C_YELLOW,  "hp": 20,  "dmg": (3,7),  "defense": 1, "xp": 40,   "speed": 1.0, "ai": "ranged",   "min_floor": 5,  "max_floor": 12, "flee_threshold": 0.35},
    "troll":       {"name": "Troll",        "char": 'T', "color": C_GREEN,   "hp": 45,  "dmg": (5,10), "defense": 4, "xp": 70,   "speed": 0.6, "ai": "chase",    "min_floor": 7,  "max_floor": 14, "regen": 1, "flee_threshold": 0.15, "vulnerable": ["fire"], "bleed_chance": 0.30},
    "demon":       {"name": "Demon",        "char": 'D', "color": C_RED,     "hp": 55,  "dmg": (6,12), "defense": 5, "xp": 100,  "speed": 1.0, "ai": "chase",    "min_floor": 10, "max_floor": 15, "flee_threshold": 0.1, "damage_type": "fire", "resists": ["fire"], "vulnerable": ["cold"]},
    "lich":        {"name": "Lich",         "char": 'L', "color": C_MAGENTA, "hp": 50,  "dmg": (5,10), "defense": 4, "xp": 120,  "speed": 0.9, "ai": "summoner", "min_floor": 11, "max_floor": 15, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["cold", "poison"]},
    "ogre_king":   {"name": "Ogre King",    "char": 'O', "color": C_BOSS,    "hp": 80,  "dmg": (6,14), "defense": 6, "xp": 200,  "speed": 0.7, "ai": "chase",    "min_floor": 5,  "max_floor": 5,  "boss": True, "flee_threshold": 0.0},
    "vampire_lord":{"name": "Vampire Lord", "char": 'V', "color": C_BOSS,    "hp": 150, "dmg": (9,16), "defense": 7, "xp": 350,  "speed": 1.1, "ai": "ambush",   "min_floor": 10, "max_floor": 10, "boss": True, "lifesteal": True, "flee_threshold": 0.0},
    "dread_lord":  {"name": "The Dread Lord","char": '&', "color": C_BOSS,    "hp": 300, "dmg": (12,24),"defense": 12, "xp": 1000, "speed": 1.0, "ai": "summoner", "min_floor": 15, "max_floor": 15, "boss": True, "regen": 3, "flee_threshold": 0.0},
    # Phase 4: Abyss Final Boss (floor 20)
    "abyssal_horror":{"name": "The Abyssal Horror","char": '&', "color": C_BOSS, "hp": 500, "dmg": (15,30),"defense": 15, "xp": 2000, "speed": 1.0, "ai": "summoner", "min_floor": 20, "max_floor": 20, "boss": True, "regen": 5, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["fire", "cold", "poison"], "paralyze_chance": 0.20, "psychic_range": 8},
    # --- Phase 1 D&D Expansion Monsters ---
    "centipede":     {"name": "Centipede",      "char": 'c', "color": C_GREEN,   "hp": 8,   "dmg": (1,3),  "defense": 0, "xp": 8,    "speed": 1.3, "ai": "chase",       "min_floor": 1,  "max_floor": 4,  "poison_chance": 0.30, "flee_threshold": 0.2, "damage_type": "poison", "resists": ["poison"]},
    "mimic":         {"name": "Mimic",          "char": '$', "color": C_GOLD,    "hp": 22,  "dmg": (3,7),  "defense": 2, "xp": 45,   "speed": 1.0, "ai": "mimic",       "min_floor": 3,  "max_floor": 10, "disguised": True, "flee_threshold": 0.0},
    "phase_spider":  {"name": "Phase Spider",   "char": 'S', "color": C_MAGENTA, "hp": 20,  "dmg": (3,6),  "defense": 1, "xp": 40,   "speed": 1.1, "ai": "phase",       "min_floor": 5,  "max_floor": 11, "poison_chance": 0.40, "phase_cooldown_max": 3, "flee_threshold": 0.25, "damage_type": "poison", "resists": ["poison"]},
    "fire_elemental":{"name": "Fire Elemental", "char": 'E', "color": C_LAVA,    "hp": 35,  "dmg": (4,9),  "defense": 3, "xp": 65,   "speed": 0.9, "ai": "chase",       "min_floor": 8,  "max_floor": 13, "fire_aura": True, "flee_threshold": 0.0, "damage_type": "fire", "resists": ["fire"], "vulnerable": ["cold"]},
    "banshee":       {"name": "Banshee",        "char": 'B', "color": C_CYAN,    "hp": 28,  "dmg": (4,8),  "defense": 2, "xp": 55,   "speed": 1.0, "ai": "ambush",      "min_floor": 7,  "max_floor": 12, "fear_chance": 0.50, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["cold"], "vulnerable": ["fire"]},
    "mind_flayer":   {"name": "Mind Flayer",    "char": 'M', "color": C_MAGENTA, "hp": 60,  "dmg": (5,11), "defense": 5, "xp": 130,  "speed": 0.9, "ai": "mind_flayer", "min_floor": 12, "max_floor": 15, "paralyze_chance": 0.30, "psychic_range": 6, "flee_threshold": 0.15, "resists": ["poison"], "silence_chance": 0.25},
    # --- Branch Mini-Bosses ---
    "crypt_guardian":{"name": "Crypt Guardian", "char": 'G', "color": C_BOSS,  "hp": 90,  "dmg": (6,12), "defense": 6, "xp": 180,  "speed": 0.8, "ai": "chase",    "min_floor": 8,  "max_floor": 8,  "boss": True, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["cold", "poison"], "vulnerable": ["fire"]},
    "flame_tyrant":  {"name": "Flame Tyrant",  "char": 'F', "color": C_BOSS,  "hp": 95,  "dmg": (7,14), "defense": 5, "xp": 190,  "speed": 0.9, "ai": "chase",    "min_floor": 8,  "max_floor": 8,  "boss": True, "flee_threshold": 0.0, "fire_aura": True, "damage_type": "fire", "resists": ["fire"], "vulnerable": ["cold"]},
    "elder_brain":   {"name": "Elder Brain",   "char": 'B', "color": C_BOSS,  "hp": 110, "dmg": (6,13), "defense": 7, "xp": 220,  "speed": 0.7, "ai": "mind_flayer", "min_floor": 13, "max_floor": 13, "boss": True, "flee_threshold": 0.0, "paralyze_chance": 0.40, "psychic_range": 8, "resists": ["poison"]},
    "beast_lord":    {"name": "Beast Lord",    "char": 'B', "color": C_BOSS,  "hp": 100, "dmg": (7,15), "defense": 5, "xp": 200,  "speed": 1.2, "ai": "pack",     "min_floor": 13, "max_floor": 13, "boss": True, "flee_threshold": 0.0},
    # --- Phase 3 Branch Mini-Bosses ---
    "fungal_queen":  {"name": "Fungal Queen",  "char": 'Q', "color": C_GREEN,   "hp": 70,  "dmg": (4,9),  "defense": 4, "xp": 140,  "speed": 0.7, "ai": "summoner", "min_floor": 4,  "max_floor": 4,  "boss": True, "flee_threshold": 0.0, "poison_chance": 0.40, "damage_type": "poison", "resists": ["poison"]},
    "trap_master":   {"name": "Trap Master",   "char": 'X', "color": C_YELLOW,  "hp": 65,  "dmg": (5,10), "defense": 3, "xp": 130,  "speed": 1.1, "ai": "ranged",   "min_floor": 4,  "max_floor": 4,  "boss": True, "flee_threshold": 0.0},
    "void_herald":   {"name": "Void Herald",   "char": 'V', "color": C_MAGENTA, "hp": 180, "dmg": (10,18),"defense": 10,"xp": 400,  "speed": 1.0, "ai": "mind_flayer","min_floor": 14,"max_floor": 14, "boss": True, "flee_threshold": 0.0, "paralyze_chance": 0.35, "psychic_range": 7, "resists": ["cold", "poison"]},
    "inferno_king":  {"name": "Inferno King",  "char": 'K', "color": C_LAVA,    "hp": 190, "dmg": (11,20),"defense": 9, "xp": 420,  "speed": 0.9, "ai": "chase",    "min_floor": 14, "max_floor": 14, "boss": True, "flee_threshold": 0.0, "fire_aura": True, "damage_type": "fire", "resists": ["fire"], "vulnerable": ["cold"]},
    # --- Phase 2 Apex Enemies (rare, powerful late-game) ---
    "ancient_dragon":{"name": "Ancient Dragon", "char": 'D', "color": C_LAVA,    "hp": 200, "dmg": (10,20), "defense": 10, "xp": 500,  "speed": 0.8, "ai": "chase",    "min_floor": 12, "max_floor": 15, "flee_threshold": 0.0, "fire_aura": True, "breath_weapon": "fire", "breath_range": 5, "breath_cooldown_max": 4, "damage_type": "fire", "resists": ["fire"], "vulnerable": ["cold"], "apex": True},
    "hydra":         {"name": "Hydra",          "char": 'H', "color": C_GREEN,   "hp": 180, "dmg": (8,16),  "defense": 7,  "xp": 450,  "speed": 0.7, "ai": "chase",    "min_floor": 11, "max_floor": 15, "flee_threshold": 0.0, "regen": 3, "multi_attack": 3, "damage_type": "poison", "resists": ["poison"], "vulnerable": ["fire"], "apex": True},
    "shadow_wyrm":   {"name": "Shadow Wyrm",    "char": 'Y', "color": C_DARK,    "hp": 160, "dmg": (9,18),  "defense": 8,  "xp": 480,  "speed": 1.1, "ai": "phase",    "min_floor": 12, "max_floor": 15, "flee_threshold": 0.0, "phase_cooldown_max": 2, "damage_type": "cold", "resists": ["cold", "poison"], "apex": True},
    "stone_colossus":{"name": "Stone Colossus", "char": 'C', "color": C_WHITE,   "hp": 250, "dmg": (12,22), "defense": 15, "xp": 550,  "speed": 0.4, "ai": "chase",    "min_floor": 13, "max_floor": 15, "flee_threshold": 0.0, "resists": ["fire", "cold", "poison"], "stun_on_hit": 0.25, "apex": True},
    # Phase 4: Abyss enemies (floors 16-20)
    "void_stalker":  {"name": "Void Stalker",  "char": 'v', "color": C_DARK,    "hp": 80,  "dmg": (8,16), "defense": 8,  "xp": 160,  "speed": 1.3, "ai": "ambush",   "min_floor": 16, "max_floor": 20, "flee_threshold": 0.0, "damage_type": "cold", "resists": ["cold"]},
    "chaos_spawn":   {"name": "Chaos Spawn",   "char": 'c', "color": C_MAGENTA, "hp": 100, "dmg": (9,18), "defense": 7,  "xp": 180,  "speed": 1.0, "ai": "erratic",  "min_floor": 16, "max_floor": 20, "flee_threshold": 0.0, "poison_chance": 0.30, "fear_chance": 0.20, "resists": ["poison"]},
    "abyss_knight":  {"name": "Abyss Knight",  "char": 'K', "color": C_RED,     "hp": 120, "dmg": (10,20),"defense": 10, "xp": 220,  "speed": 0.9, "ai": "chase",    "min_floor": 17, "max_floor": 20, "flee_threshold": 0.0, "bleed_chance": 0.35, "resists": ["fire"]},
    "entropy_mage":  {"name": "Entropy Mage",  "char": 'E', "color": C_CYAN,    "hp": 90,  "dmg": (8,15), "defense": 6,  "xp": 200,  "speed": 0.8, "ai": "ranged",   "min_floor": 17, "max_floor": 20, "flee_threshold": 0.0, "silence_chance": 0.30, "damage_type": "cold", "resists": ["cold", "fire"]},
}

TRAP_TYPES: dict[str, dict[str, Any]] = {
    "spike":    {"name": "Spike Trap",    "damage": (3, 8),  "effect": None,        "detect_dc": 12, "min_floor": 1},
    "dart":     {"name": "Dart Trap",     "damage": (2, 6),  "effect": "poison",    "detect_dc": 14, "min_floor": 3},
    "pit":      {"name": "Pit Trap",      "damage": (4, 10), "effect": "stun",      "detect_dc": 12, "min_floor": 2},
    "teleport": {"name": "Teleport Trap", "damage": (0, 0),  "effect": "teleport",  "detect_dc": 16, "min_floor": 5},
    "alarm":    {"name": "Alarm Trap",    "damage": (0, 0),  "effect": "alert_all", "detect_dc": 10, "min_floor": 1},
    "gas":      {"name": "Gas Trap",      "damage": (1, 3),  "effect": "confusion", "detect_dc": 18, "min_floor": 7},
}

# ============================================================
# ENVIRONMENTAL VIGNETTES
# ============================================================
VIGNETTE_TEMPLATES: list[dict[str, Any]] = [
    {"name": "Fallen Adventurer", "char": '&', "lore": "A skeleton clutches a faded journal: 'Day 7... the walls are closing in.'", "loot_chance": 0.40, "loot_tier": 1},
    {"name": "Barricaded Room", "char": '#', "lore": "Scratch marks cover the inside of a hastily barricaded door. Whatever was here... got out.", "loot_chance": 0.25, "loot_tier": 2},
    {"name": "Ritual Circle", "char": '*', "lore": "Melted candles surround a circle of strange symbols etched in blood.", "loot_chance": 0.50, "loot_tier": 2},
    {"name": "Abandoned Camp", "char": '%', "lore": "A cold campfire and an empty bedroll. Someone left in a hurry.", "loot_chance": 0.60, "loot_tier": 1},
    {"name": "Shrine of Offerings", "char": '_', "lore": "Withered flowers and small coins lie before a crumbling idol.", "loot_chance": 0.30, "loot_tier": 1},
    {"name": "Empty Potion Lab", "char": '&', "lore": "Broken vials and a skeleton. The last experiment went wrong.", "loot_chance": 0.50, "loot_tier": 2},
    {"name": "Collapsed Tunnel", "char": '#', "lore": "Rubble blocks a passage. Through a crack, you see bones.", "loot_chance": 0.15, "loot_tier": 1},
    {"name": "Blood Trail", "char": '.', "lore": "A trail of dried blood leads to a dark alcove... and stops.", "loot_chance": 0.20, "loot_tier": 1},
    {"name": "Throne of Dust", "char": '_', "lore": "A crumbling stone throne. Whoever sat here ruled nothing but dust.", "loot_chance": 0.35, "loot_tier": 3},
    {"name": "Weeping Statue", "char": '*', "lore": "A marble face with tear-stained cheeks. The eyes seem to follow you.", "loot_chance": 0.30, "loot_tier": 1},
    {"name": "Prison Cell", "char": '#', "lore": "Chains hang from the wall. Tally marks cover every surface.", "loot_chance": 0.25, "loot_tier": 1},
    {"name": "Mushroom Garden", "char": '%', "lore": "Bioluminescent fungi light a small grotto. Some look edible... maybe.", "loot_chance": 0.50, "loot_tier": 1},
    {"name": "Ancient Library", "char": '?', "lore": "Rotting bookshelves. One tome catches your eye: 'On the Nature of Dread.'", "loot_chance": 0.45, "loot_tier": 2},
    {"name": "Forge Remnants", "char": ')', "lore": "A cold anvil and scattered tools. Someone was crafting weapons here.", "loot_chance": 0.55, "loot_tier": 2},
    {"name": "Well of Whispers", "char": '~', "lore": "You lean over the well. Faint whispers rise from the depths.", "loot_chance": 0.30, "loot_tier": 1},
    {"name": "Cocoon Chamber", "char": 'S', "lore": "Silken cocoons hang from the ceiling. Something moves inside one.", "loot_chance": 0.20, "loot_tier": 2},
    {"name": "Treasure Hoard", "char": '$', "lore": "A pile of coins surrounds a skeleton still clutching a bag.", "loot_chance": 0.80, "loot_tier": 2},
    {"name": "War Memorial", "char": '|', "lore": "Names are carved into a stone pillar. Many are scratched out.", "loot_chance": 0.15, "loot_tier": 1},
    {"name": "Alchemist's Grave", "char": '!', "lore": "A headstone reads: 'Here lies one who sought the elixir of life. He found death.'", "loot_chance": 0.45, "loot_tier": 2},
    {"name": "Dragon Scale", "char": '=', "lore": "A single massive scale, bigger than your shield. What creature left this?", "loot_chance": 0.35, "loot_tier": 3},
    {"name": "Broken Mirror", "char": '*', "lore": "Shattered glass reflects a hundred fractured images of yourself.", "loot_chance": 0.20, "loot_tier": 1},
    {"name": "Last Stand", "char": ')', "lore": "Three skeletons in formation, weapons drawn. They died fighting back-to-back.", "loot_chance": 0.60, "loot_tier": 2},
    {"name": "Cursed Altar", "char": '_', "lore": "Dark stains on an obsidian altar. The air feels wrong here.", "loot_chance": 0.40, "loot_tier": 3},
    {"name": "Frozen Warrior", "char": '@', "lore": "An adventurer encased in ice, expression frozen in horror.", "loot_chance": 0.50, "loot_tier": 2},
    {"name": "Rat King", "char": 'r', "lore": "A mass of rat bones fused together. Nature is not kind here.", "loot_chance": 0.25, "loot_tier": 1},
]

# ============================================================
# NPC ENCOUNTERS (Phase 3)
# ============================================================
NPC_TYPES: dict[str, dict[str, Any]] = {
    "wandering_merchant": {
        "name": "Wandering Merchant",
        "char": '@',
        "color": C_GOLD,
        "dialogue": "Psst! Want to trade? I have rare wares...",
        "interaction": "shop",  # Opens a mini shop
        "min_floor": 2,
        "max_floor": 14,
    },
    "lost_adventurer": {
        "name": "Lost Adventurer",
        "char": '@',
        "color": C_CYAN,
        "dialogue": "Thank the gods! Another living soul! Take this — I have no use for it now.",
        "interaction": "gift",  # Gives a random item
        "min_floor": 1,
        "max_floor": 10,
    },
    "old_sage": {
        "name": "Old Sage",
        "char": '@',
        "color": C_MAGENTA,
        "dialogue": "I sense great potential in you. Let me share my knowledge...",
        "interaction": "buff",  # Temporary stat buff
        "min_floor": 4,
        "max_floor": 15,
    },
    "wounded_knight": {
        "name": "Wounded Knight",
        "char": '@',
        "color": C_RED,
        "dialogue": "Beware... a terrible beast guards the next floor. Here, take my blade.",
        "interaction": "warning",  # Reveals enemy info + weapon gift
        "min_floor": 4,
        "max_floor": 14,
    },
    "ghost_guide": {
        "name": "Ghost Guide",
        "char": '@',
        "color": C_DARK,
        "dialogue": "I once walked these halls alive. Let me show you the hidden paths...",
        "interaction": "reveal",  # Reveals map
        "min_floor": 3,
        "max_floor": 15,
    },
}

# ============================================================
# WEAPON ENCHANTMENTS (Phase 4)
# ============================================================
ENCHANTMENTS: dict[str, dict[str, Any]] = {
    "flame": {"name": "Flame", "desc": "+fire damage, ignite chance", "bonus_dmg": 3, "element": "fire", "proc_chance": 0.20, "proc_effect": "burn"},
    "frost": {"name": "Frost", "desc": "+cold damage, slow chance", "bonus_dmg": 2, "element": "cold", "proc_chance": 0.25, "proc_effect": "slow"},
    "venom": {"name": "Venom", "desc": "+poison damage, poison chance", "bonus_dmg": 2, "element": "poison", "proc_chance": 0.30, "proc_effect": "poison"},
    "lightning": {"name": "Lightning", "desc": "+shock damage, stun chance", "bonus_dmg": 4, "element": "lightning", "proc_chance": 0.15, "proc_effect": "stun"},
    "vampiric": {"name": "Vampiric", "desc": "Lifesteal on hit", "bonus_dmg": 1, "element": "physical", "proc_chance": 0.40, "proc_effect": "lifesteal"},
    "keen": {"name": "Keen", "desc": "+crit chance and damage", "bonus_dmg": 0, "element": "physical", "proc_chance": 0.25, "proc_effect": "crit"},
}

DEATH_QUIPS: list[str] = [
    "The dungeon claims another soul.",
    "Your bones join the countless others.",
    "Should have brought more potions.",
    "Another adventurer lost to hubris.",
    "The depths remain undefeated.",
    "Git gud.",
    "Perhaps the real treasure was the XP we lost along the way.",
    "You have been weighed, measured, and found wanting.",
]

# Level-up choice pool
LEVELUP_CHOICES: list[dict[str, Any]] = [
    {"name": "Might",     "desc": "+HP +STR",       "hp": 3,  "mp": 0, "str": 1, "def": 0, "evasion": 0},
    {"name": "Arcana",    "desc": "+MP, learn new spell", "hp": 0,  "mp": 5, "str": 0, "def": 0, "evasion": 0},
    {"name": "Fortitude", "desc": "+HP +DEF",        "hp": 4,  "mp": 0, "str": 0, "def": 1, "evasion": 0},
    {"name": "Agility",   "desc": "+evasion",        "hp": 2,  "mp": 0, "str": 0, "def": 0, "evasion": 5},
    {"name": "Vitality",  "desc": "+big HP",         "hp": 8,  "mp": 0, "str": 0, "def": 0, "evasion": 0},
]

# Class-specific level-up bonuses (added to pool when class matches)
CLASS_LEVELUP_CHOICES: dict[str, dict[str, Any]] = {
    "warrior": {"name": "Cleave",    "desc": "+STR +DEF, learn technique", "hp": 2, "mp": 0, "str": 2, "def": 1, "evasion": 0},
    "mage":    {"name": "Mana Well", "desc": "+big MP (Mage)",              "hp": 0, "mp": 10,"str": 0, "def": 0, "evasion": 0},
    "rogue":   {"name": "Lethality", "desc": "+STR +evasion, learn technique","hp": 0, "mp": 2, "str": 2, "def": 0, "evasion": 5},
}

def safe_addstr(scr: Any, y: int, x: int, s: str, attr: int = 0) -> None:
    h, w = scr.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    s = s[:w - x]
    try:
        scr.addstr(y, x, s, attr)
    except curses.error:
        pass

# Meta-progression unlock definitions
META_UNLOCKS: dict[str, dict[str, str]] = {
    "extra_potion": {"name": "Potion Affinity", "desc": "Start with an extra potion", "req": "total_games >= 3"},
    "map_reveal": {"name": "Cartographer", "desc": "Start with partial map reveal", "req": "highest_floor >= 5"},
    "bonus_gold": {"name": "Inheritance", "desc": "Start with 50 bonus gold", "req": "total_kills >= 50"},
    "extra_hp": {"name": "Hardy Constitution", "desc": "Start with +10 max HP", "req": "total_deaths >= 5"},
    "torch_bonus": {"name": "Prepared Explorer", "desc": "Start with extra torch fuel", "req": "highest_floor >= 10"},
    "mana_bonus": {"name": "Magical Aptitude", "desc": "Start with +5 max mana", "req": "total_wins >= 1"},
    "starting_weapon": {"name": "Armed & Ready", "desc": "Start with a tier 2 weapon", "req": "most_kills_single_run >= 30"},
}

AGENT_SYSTEM_PROMPT: str = """Roguelike AI. Respond ONLY with JSON: {"action":"<act>","reason":"<short>"}
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

CLAUDE_BIN: str = "/Users/will/.local/bin/claude"

# Direction mappings for action parsing
_DIR_MAP: dict[str, tuple[int, int]] = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
    "ne": (1, -1), "nw": (-1, -1), "se": (1, 1), "sw": (-1, 1),
    "n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0),
}
