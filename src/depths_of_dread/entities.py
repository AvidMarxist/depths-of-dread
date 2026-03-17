from __future__ import annotations

import curses
import random
from typing import TYPE_CHECKING, Any

from .constants import *

if TYPE_CHECKING:
    from .game import GameState


class Item:
    __slots__ = ['x', 'y', 'item_type', 'subtype', 'data', 'identified', 'equipped', 'count']
    def __init__(self, x: int, y: int, item_type: str, subtype: str | int, data: dict[str, Any]) -> None:
        self.x: int = x
        self.y: int = y
        self.item_type: str = item_type
        self.subtype: str | int = subtype
        self.data: dict[str, Any] = dict(data)
        self.identified: bool = False
        self.equipped: bool = False
        self.count: int = 1

    @property
    def char(self) -> str:
        if self.item_type == "gold":
            return '$'
        return self.data.get("char", '?')

    @property
    def color(self) -> int:
        return {"weapon": C_WHITE, "armor": C_BLUE, "potion": C_MAGENTA,
                "scroll": C_YELLOW, "gold": C_GOLD, "food": C_GREEN,
                "ring": C_CYAN, "bow": C_YELLOW, "arrow": C_WHITE,
                "throwing_dagger": C_WHITE, "wand": C_MAGENTA,
                "torch": C_YELLOW}.get(self.item_type, C_WHITE)

    @property
    def display_name(self) -> str:
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
    def sell_value(self) -> int:
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
    def __init__(self, x: int, y: int, etype: str) -> None:
        t = ENEMY_TYPES[etype]
        self.x: int = x
        self.y: int = y
        self.etype: str = etype
        self.name: str = t["name"]
        self.char: str = t["char"]
        self.color: int = t["color"]
        self.max_hp: int = t["hp"]
        self.hp: int = t["hp"]
        self.dmg: int = t["dmg"]
        self.defense: int = t["defense"]
        self.xp: int = t["xp"]
        self.speed: float = t["speed"]
        self.ai: str = t["ai"]
        self.boss: bool = t.get("boss", False)
        self.regen: int = t.get("regen", 0)
        self.lifesteal: bool = t.get("lifesteal", False)
        self.energy: float = 0.0
        self.alerted: bool = False
        self.alertness: str = "unwary"  # "asleep", "unwary", or "alert"
        self.patrol_dir: tuple[int, int] = random.choice([(0,1),(0,-1),(1,0),(-1,0)])
        self.summon_cooldown: int = 0
        self.frozen_turns: int = 0
        # D&D expansion fields
        self.poison_chance: int = t.get("poison_chance", 0)
        self.fear_chance: int = t.get("fear_chance", 0)
        self.paralyze_chance: int = t.get("paralyze_chance", 0)
        self.fire_aura: bool = t.get("fire_aura", False)
        self.disguised: bool = t.get("disguised", False)
        self.phase_cooldown: int = 0
        self.phase_cooldown_max: int = t.get("phase_cooldown_max", 3)
        self.psychic_range: int = t.get("psychic_range", 0)
        self.bleed_chance: int = t.get("bleed_chance", 0)
        self.freeze_status_chance: int = t.get("freeze_status_chance", 0)
        self.silence_chance: int = t.get("silence_chance", 0)
        self.poisoned_turns: int = 0  # Poison from player's Poison Blade ability
        # Fleeing system
        self.fleeing: bool = False
        self.flee_threshold: float = t.get("flee_threshold", 0.0)
        # Elemental resistance system
        self.damage_type: str = t.get("damage_type", "physical")
        self.resists: list[str] = t.get("resists", [])
        self.vulnerable: list[str] = t.get("vulnerable", [])
        self.regen_suppressed: int = 0  # Turns of regen suppression (e.g. fire vs troll)
        # Apex enemy fields
        self.apex: bool = t.get("apex", False)
        self.breath_weapon: str | None = t.get("breath_weapon", None)
        self.breath_range: int = t.get("breath_range", 0)
        self.breath_cooldown_max: int = t.get("breath_cooldown_max", 0)
        self.breath_cooldown: int = 0
        self.multi_attack: int = t.get("multi_attack", 1)
        self.stun_on_hit: int = t.get("stun_on_hit", 0)
        # Boss phase tracking
        self.boss_phase: int = 1
        self.boss_phase_turn: int = 0  # Turns since last phase action (e.g., bat summon)
        # Expansion status effects on enemies
        self.bleed_stacks: int = 0
        self.bleed_turns: int = 0
        self.silenced_turns: int = 0

    def is_alive(self) -> bool:
        return self.hp > 0


class Player:
    def __init__(self, player_class: str | None = None) -> None:
        self.x: int = 0
        self.y: int = 0
        self.player_class: str | None = player_class  # None = classless adventurer (backward compat)
        if player_class and player_class in CHARACTER_CLASSES:
            cc = CHARACTER_CLASSES[player_class]
            self.hp: int = cc["hp"]
            self.max_hp: int = cc["hp"]
            self.mana: int = cc["mp"]
            self.max_mana: int = cc["mp"]
            self.strength: int = cc["str"]
            self.defense: int = cc["defense"]
        else:
            self.hp = 30
            self.max_hp = 30
            self.mana = 20
            self.max_mana = 20
            self.strength = 5
            self.defense = 1
        self.level: int = 1
        self.xp: int = 0
        self.xp_next: int = BALANCE["xp_base"]
        self.floor: int = 1
        self.gold: int = 0
        self.turns: int = 0
        self.kills: int = 0
        self.inventory: list[Item] = []
        self.weapon: Item | None = None
        self.armor: Item | None = None
        self.ring: Item | None = None
        self.bow: Item | None = None
        self.hunger: float = 100.0
        self.torch_fuel: int = TORCH_MAX_FUEL
        self.torch_lit: bool = True  # Can toggle torch on/off to conserve fuel
        self.status_effects: dict[str, int] = {}
        self.frozen_enemies: dict[int, int] = {}  # enemy id -> turns remaining
        self.deepest_floor: int = 1
        self.potions_drunk: int = 0
        self.scrolls_read: int = 0
        self.items_found: int = 0
        self.damage_dealt: int = 0
        self.damage_taken: int = 0
        self.foods_eaten: int = 0
        self.bosses_killed: int = 0
        self.spells_cast: int = 0
        self.projectiles_fired: int = 0
        self.pending_levelups: list[dict[str, Any]] = []  # Deferred level-up choices
        self.ability_cooldown: int = 0   # Class ability cooldown
        # Telemetry counters
        self.gold_earned: int = 0
        self.gold_spent: int = 0
        self.torches_grabbed: int = 0
        self.traps_triggered: int = 0
        self.traps_found: int = 0
        self.traps_disarmed: int = 0
        self.fountains_used: int = 0
        self.secrets_found: int = 0
        self.kills_by_type: dict[str, int] = {}     # {enemy_type: count}
        self.items_by_type: dict[str, int] = {}     # {item_type: count}
        # Known spells — class-specific starting sets
        if player_class and player_class in CLASS_KNOWN_SPELLS:
            self.known_spells: set[str] = set(CLASS_KNOWN_SPELLS[player_class])
        else:
            self.known_spells = set(BASE_SPELLS)  # classless = all base spells
        self.known_abilities: set[str] = set()  # Warrior/Rogue combat techniques (unlocked via Cleave/Lethality)
        # Expansion status effects
        self.bleed_stacks: int = 0
        self.bleed_turns: int = 0

    @property
    def carry_capacity(self) -> int:
        """Inventory capacity scales with strength."""
        return 15 + self.strength

    def attack_damage(self) -> int:
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

    def total_defense(self) -> int:
        d = self.defense
        if self.armor:
            d += self.armor.data["defense"]
        if self.ring and self.ring.data.get("effect") == "defense":
            d += self.ring.data["value"]
        if "Resistance" in self.status_effects:
            d += 3
        return d

    def evasion_chance(self) -> float:
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

    def player_resists(self) -> set[str]:
        """Return set of elements player currently resists."""
        r: set[str] = set()
        if self.ring and "resists" in self.ring.data:
            r.update(self.ring.data["resists"])
        if self.armor and "resists" in self.armor.data:
            r.update(self.armor.data["resists"])
        return r

    def get_torch_radius(self) -> int:
        if not self.torch_lit or self.torch_fuel <= 0:
            return TORCH_RADIUS_EMPTY
        pct = self.torch_fuel / TORCH_MAX_FUEL
        if pct > 0.5:
            return TORCH_RADIUS_FULL
        elif pct > 0.25:
            return TORCH_RADIUS_HALF
        else:
            return TORCH_RADIUS_QUARTER

    def check_level_up(self) -> list[tuple[int, int, int, int]]:
        """Returns list of (level, hp_gain, str_gain, mp_gain) tuples.
        If pending_levelups system is active, defers stat application."""
        ups: list[tuple[int, int, int, int]] = []
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


def generate_levelup_choices(player: Player) -> list[dict[str, Any]]:
    """Generate 3 random level-up options for the player to choose from."""
    pool = list(LEVELUP_CHOICES)
    if player.player_class and player.player_class in CLASS_LEVELUP_CHOICES:
        pool.append(CLASS_LEVELUP_CHOICES[player.player_class])
    random.shuffle(pool)
    return pool[:3]


def apply_levelup_choice(player: Player, levelup_data: dict[str, Any], choice: dict[str, Any]) -> str | None:
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
    learned: str | None = None
    if choice["name"] == "Arcana":
        learned = _unlock_next_spell(player)
    elif choice["name"] in ("Cleave", "Lethality"):
        learned = _unlock_next_ability(player)
    return learned


def _unlock_next_spell(player: Player) -> str | None:
    """Unlock the next spell in the class-specific unlock order. Returns spell name or None."""
    unlock_list = SPELL_UNLOCK_ORDER.get(player.player_class, [])
    for spell_name in unlock_list:
        if spell_name not in player.known_spells:
            player.known_spells.add(spell_name)
            return spell_name
    return None  # All already known — just the MP bonus


def _unlock_next_ability(player: Player) -> str | None:
    """Unlock the next ability in the class-specific unlock order. Returns ability name or None."""
    unlock_list = ABILITY_UNLOCK_ORDER.get(player.player_class, [])
    for ability_name in unlock_list:
        if ability_name not in player.known_abilities:
            player.known_abilities.add(ability_name)
            return ability_name
    return None


def show_levelup_choice(scr: Any, gs: GameState) -> int | None:
    """Show level-up choice screen for one pending levelup. Returns chosen index."""
    if not gs.player.pending_levelups:
        return None
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


def auto_apply_levelup(player: Player) -> None:
    """Auto-apply the best level-up choice (for bot/agent).

    Strategy: maximize survivability (HP + DEF) while learning key abilities.
    Pick Cleave/Lethality when offered AND the next ability is high-value,
    otherwise tank up. Always learn Heal spell (Arcana) first if available.
    """
    if not player.pending_levelups:
        return
    levelup_data = player.pending_levelups[0]
    choices = generate_levelup_choices(player)

    # Smart ability scoring: weight each choice by combat value
    def score_choice(c: dict) -> float:
        s = c["hp"] + c["def"] * 2 + c["str"] * 1.5
        # Bonus for learning spells via Arcana
        if c["name"] == "Arcana":
            spell_list = SPELL_UNLOCK_ORDER.get(player.player_class, [])
            for spell in spell_list:
                if spell not in player.known_spells:
                    if spell == "Heal":
                        s += 15  # Heal is extremely valuable
                    elif spell == "Freeze":
                        s += 12  # Freeze is critical for boss fights
                    elif spell in ("Fireball", "Chain Lightning", "Lightning Bolt"):
                        s += 6   # Offensive spells have moderate value
                    else:
                        s += 3
                    break
        # Bonus for learning class abilities
        if c["name"] in ("Cleave", "Lethality"):
            ability_list = ABILITY_UNLOCK_ORDER.get(player.player_class, [])
            for ability in ability_list:
                if ability not in player.known_abilities:
                    if ability in ("Backstab", "Cleaving Strike"):
                        s += 12  # High-value combat abilities
                    elif ability in ("Shield Wall", "Whirlwind"):
                        s += 6   # Moderate value
                    else:
                        s += 3   # Low value
                    break
        return s

    best = max(choices, key=score_choice)
    apply_levelup_choice(player, levelup_data, best)
    player.pending_levelups.pop(0)


class ShopItem:
    def __init__(self, item: Item, price: int) -> None:
        self.item: Item = item
        self.price: int = price
        self.sold: bool = False
