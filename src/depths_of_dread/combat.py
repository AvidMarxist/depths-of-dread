from __future__ import annotations

import random
import curses
from typing import Any, TYPE_CHECKING

from .constants import *
from .entities import Item, Enemy, Player
from .mapgen import astar, _has_los, compute_fov

if TYPE_CHECKING:
    from .game import GameState


def sound_alert(gs: GameState, event: str) -> None:
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
# COMBAT & ITEMS
# ============================================================

def _bestiary_record(gs: GameState, etype: str, event: str, value: int | str = 0) -> None:
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


def _award_kill(gs: GameState, enemy: Enemy, msg: str | bool | None = None, drops: bool = False) -> bool:
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
    # Pacifist challenge: killing enemies is forbidden
    if gs.challenge_pacifist and not enemy.boss:
        gs.msg("PACIFIST VIOLATION! You have killed a creature!", C_RED)
        gs.msg("The guilt overwhelms you...", C_RED)
        gs.game_over = True
        gs.death_cause = "broke the pacifist oath"
        return True
    p.xp += enemy.xp
    p.kills += 1
    p.kills_by_type[enemy.etype] = p.kills_by_type.get(enemy.etype, 0) + 1
    _bestiary_record(gs, enemy.etype, "kill")
    if enemy.boss:
        p.bosses_killed += 1
    if msg is not False:
        if msg is None:
            msg = f"You killed the {enemy.name}! (+{enemy.xp} XP)"
        gs.msg(msg, C_GREEN)
    # Dread Lord defeated — announce The Abyss
    if enemy.etype == "dread_lord":
        gs.msg("The Dread Lord falls... but the floor cracks open beneath!", C_RED)
        gs.msg("A stairway into THE ABYSS yawns before you. Dare you descend?", C_MAGENTA)
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
            amt = random.randint(B["gold_drop_min"], B["gold_drop_max"]) * min(p.floor, 5)
            gs.items.append(Item(enemy.x, enemy.y, "gold", 0, {"amount": amt, "name": f"{amt} gold"}))
    return True


def _check_levelups(gs: GameState) -> None:
    """Check and announce any pending level-ups after XP gain."""
    p = gs.player
    for lvl, hp_g, str_g, mp_g in p.check_level_up():
        gs.msg(f"*** LEVEL UP! Level {lvl}! +{hp_g} HP, +{str_g} STR, +{mp_g} MP ***", C_YELLOW)
        sound_alert(gs, "level_up")

def _trigger_trap(gs: GameState, trap: dict[str, Any], target_name: str = "You", target_hp_ref: list[int] | None = None, is_player: bool = True) -> int:
    """Trigger a trap on a target (player or enemy). Returns damage dealt."""
    tdata = TRAP_TYPES[trap["type"]]
    trap["triggered"] = True
    trap["visible"] = True
    lo, hi = tdata["damage"]
    floor_scale = 1.0 + gs.player.floor * B["trap_damage_scale_per_floor"]
    dmg = int(random.randint(lo, hi) * floor_scale) if hi > 0 else 0

    if is_player:
        p = gs.player
        p.traps_triggered += 1
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


def _check_traps_on_move(gs: GameState, nx: int, ny: int) -> bool:
    """Check if player steps on a trap at (nx, ny). Returns True if trap triggered."""
    for trap in gs.traps:
        if trap["x"] == nx and trap["y"] == ny and not trap["disarmed"] and not trap["triggered"]:
            if not trap["visible"]:  # Hidden trap always triggers
                _trigger_trap(gs, trap)
                return True
            # Visible traps: player steps over safely (standard roguelike behavior)
    return False


def _passive_trap_detect(gs: GameState) -> None:
    """Passive trap detection when moving adjacent to hidden traps.
    Rogues have a strong bonus; other classes have a small chance."""
    p = gs.player
    for trap in gs.traps:
        if trap["visible"] or trap["disarmed"] or trap["triggered"]:
            continue
        if abs(trap["x"] - p.x) <= B["trap_detect_radius"] and abs(trap["y"] - p.y) <= B["trap_detect_radius"]:
            chance = B["trap_rogue_detect_bonus"] if p.player_class == "rogue" else 5
            if random.randint(1, 100) <= chance:
                trap["visible"] = True
                tdata = TRAP_TYPES[trap["type"]]
                p.traps_found += 1
                gs.msg(f"You sense a {tdata['name']} nearby!", C_YELLOW)


def _search_for_traps(gs: GameState) -> None:
    """Active search: check 2-tile radius for hidden traps and secret walls ('/' key)."""
    p = gs.player
    found = 0
    for ddx in range(-2, 3):
        for ddy in range(-2, 3):
            if ddx == 0 and ddy == 0:
                continue
            tx, ty = p.x + ddx, p.y + ddy
            if tx < 0 or tx >= MAP_W or ty < 0 or ty >= MAP_H:
                continue
            for trap in gs.traps:
                if trap["x"] == tx and trap["y"] == ty and not trap["visible"] and not trap["disarmed"]:
                    tdata = TRAP_TYPES[trap["type"]]
                    roll = p.level + random.randint(1, 20)
                    if p.player_class == "rogue":
                        roll += 5
                    if roll >= tdata["detect_dc"]:
                        trap["visible"] = True
                        p.traps_found += 1
                        gs.msg(f"Found a {tdata['name']}!", C_YELLOW)
                        found += 1
            # Check for secret walls (added with secret rooms feature)
            if 0 <= tx < MAP_W and 0 <= ty < MAP_H:
                if gs.tiles[ty][tx] == T_SECRET_WALL:
                    roll = p.level + random.randint(1, 20)
                    if p.player_class == "rogue":
                        roll += 5
                    if roll >= 15:  # DC 15 to find secret passage
                        gs.tiles[ty][tx] = T_DOOR
                        p.secrets_found += 1
                        gs.msg("You discover a hidden passage!", C_YELLOW)
                        found += 1
    if found == 0:
        gs.msg("You search carefully but find nothing.", C_DARK)


def _disarm_trap(gs: GameState) -> bool:
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
                        gs.player.traps_disarmed += 1
                        gs.msg(f"You disarm the {tdata['name']}!", C_GREEN)
                    else:
                        gs.msg(f"Disarm failed! The {tdata['name']} triggers!", C_RED)
                        _trigger_trap(gs, trap)
                    return True
    gs.msg("No visible traps nearby to disarm.", C_DARK)
    return False


def player_attack(gs: GameState, enemy: Enemy) -> None:
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
    # Weapon enchantment proc (Phase 4)
    if p.weapon and p.weapon.data.get("enchantment") and dmg > 0 and enemy.is_alive():
        enchant_key = p.weapon.data["enchantment"]
        if enchant_key in ENCHANTMENTS:
            ench = ENCHANTMENTS[enchant_key]
            # Bonus flat damage
            bonus = p.weapon.data.get("enchant_bonus_dmg", 0)
            if bonus > 0:
                enemy.hp -= bonus
                dmg += bonus
            # Proc effect
            proc_chance = p.weapon.data.get("enchant_proc_chance", 0)
            proc_effect = p.weapon.data.get("enchant_proc_effect", "")
            if random.random() < proc_chance:
                if proc_effect == "burn":
                    enemy.regen_suppressed = max(enemy.regen_suppressed, 5)
                    gs.msg(f"Your weapon ignites the {enemy.name}!", C_LAVA)
                elif proc_effect == "slow":
                    enemy.frozen_turns = max(enemy.frozen_turns, 2)
                    gs.msg(f"Frost slows the {enemy.name}!", C_CYAN)
                elif proc_effect == "poison":
                    if enemy.poisoned_turns <= 0:
                        enemy.poisoned_turns = B["poison_duration"]
                        gs.msg(f"Venom seeps into the {enemy.name}!", C_GREEN)
                elif proc_effect == "stun":
                    enemy.frozen_turns = max(enemy.frozen_turns, 1)
                    gs.msg(f"Lightning stuns the {enemy.name}!", C_YELLOW)
                elif proc_effect == "lifesteal":
                    heal_amt = max(1, dmg // 4)
                    p.hp = min(p.max_hp, p.hp + heal_amt)
                    gs.msg(f"Your vampiric blade drains {heal_amt} HP!", C_GREEN)
                elif proc_effect == "crit":
                    crit_bonus = max(1, dmg // 2)
                    enemy.hp -= crit_bonus
                    gs.msg(f"Keen edge! Extra {crit_bonus} damage!", C_YELLOW)
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


def enemy_attack(gs: GameState, enemy: Enemy) -> None:
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
    # Frozen shatter: bonus damage when hit while frozen
    if "Frozen" in p.status_effects:
        dmg = int(dmg * B["frozen_shatter_bonus"])
        gs.msg("SHATTER! The ice amplifies the blow!", C_CYAN)
        del p.status_effects["Frozen"]
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
    # Bleed: stacking damage over time
    if p.hp > 0 and enemy.bleed_chance and random.random() < enemy.bleed_chance:
        p.bleed_stacks = min(p.bleed_stacks + 1, B["bleed_max_stacks"])
        p.bleed_turns = B["bleed_duration"]
        gs.msg(f"The {enemy.name}'s attack causes bleeding! ({p.bleed_stacks} stacks)", C_RED)
        _bestiary_record(gs, enemy.etype, "ability", "bleed")
    # Freeze status: skip turn, vulnerable to shatter
    if p.hp > 0 and enemy.freeze_status_chance and random.random() < enemy.freeze_status_chance:
        if "Frozen" not in p.status_effects:
            p.status_effects["Frozen"] = B["frozen_status_duration"]
            gs.msg(f"The {enemy.name}'s cold freezes you solid!", C_CYAN)
            _bestiary_record(gs, enemy.etype, "ability", "freeze")
    # Stun on hit (Stone Colossus)
    if p.hp > 0 and enemy.stun_on_hit and random.random() < enemy.stun_on_hit:
        if "Paralysis" not in p.status_effects:
            p.status_effects["Paralysis"] = B["stun_duration"]
            gs.msg(f"The {enemy.name}'s crushing blow stuns you!", C_YELLOW)
            _bestiary_record(gs, enemy.etype, "ability", "stun")
    # Silence: no spells or wands
    if p.hp > 0 and enemy.silence_chance and random.random() < enemy.silence_chance:
        if "Silence" not in p.status_effects:
            p.status_effects["Silence"] = B["silence_duration"]
            gs.msg(f"The {enemy.name} silences your magic!", C_MAGENTA)
            _bestiary_record(gs, enemy.etype, "ability", "silence")
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


def _compute_noise(gs: GameState, noise_type: str = "walk") -> int:
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


def _stealth_detection(gs: GameState, noise_level: int) -> None:
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

def process_enemies(gs: GameState) -> None:
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
        # Boss phase transitions
        if e.boss:
            _update_boss_phase(gs, e)
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
        # Breath weapon (Ancient Dragon): ranged line attack on cooldown
        if e.breath_weapon and e.is_alive() and not gs.game_over:
            if e.breath_cooldown > 0:
                e.breath_cooldown -= 1
            elif abs(e.x - p.x) + abs(e.y - p.y) <= e.breath_range:
                # Fire breath in a line towards the player
                floor_num = p.floor
                breath_dmg = B["breath_weapon_damage_base"] + floor_num * B["breath_weapon_damage_per_floor"]
                if e.breath_weapon in p.player_resists():
                    breath_dmg = max(1, int(breath_dmg * (1 - B["resist_reduction_pct"])))
                    gs.msg(f"Your {e.breath_weapon} resistance reduces the breath damage!", C_CYAN)
                p.hp -= breath_dmg
                p.damage_taken += breath_dmg
                gs.msg(f"The {e.name} unleashes a {e.breath_weapon} breath! (-{breath_dmg})", C_LAVA)
                _bestiary_record(gs, e.etype, "ability", "breath_weapon")
                e.breath_cooldown = e.breath_cooldown_max
                if p.hp <= 0:
                    gs.game_over = True
                    gs.death_cause = f"incinerated by {e.name}'s breath"
                    sound_alert(gs, "death")
        # Multi-attack (Hydra): extra attacks when adjacent
        if e.multi_attack > 1 and e.is_alive() and not gs.game_over:
            if abs(e.x - p.x) + abs(e.y - p.y) <= 1:
                extra_attacks = e.multi_attack - 1  # First attack already handled by AI
                for _ in range(extra_attacks):
                    if gs.game_over or not e.is_alive():
                        break
                    if random.randint(1, 100) <= p.evasion_chance():
                        gs.msg(f"You dodge a {e.name} head strike!", C_CYAN)
                        continue
                    extra_dmg = random.randint(e.dmg[0], e.dmg[1])
                    extra_dmg = int(extra_dmg * B["hydra_multi_attack_dmg_mult"])
                    extra_dmg = max(1, extra_dmg - p.total_defense() // B["defense_divisor"])
                    if "Shield Wall" in p.status_effects:
                        extra_dmg = max(1, extra_dmg // 2)
                    p.hp -= extra_dmg
                    p.damage_taken += extra_dmg
                    gs.msg(f"A {e.name} head bites for {extra_dmg}!", C_RED)
                    if p.hp <= 0:
                        gs.game_over = True
                        gs.death_cause = f"torn apart by {e.name}"
                        sound_alert(gs, "death")
    gs.enemies = [e for e in gs.enemies if e.is_alive()]


def _update_boss_phase(gs: GameState, e: Enemy) -> None:
    """Update boss phase based on HP thresholds. Triggers phase transition effects."""
    hp_pct = e.hp / e.max_hp if e.max_hp > 0 else 1.0
    p = gs.player
    e.boss_phase_turn += 1

    if e.etype == "vampire_lord":
        if hp_pct <= B["boss_phase3_threshold"] and e.boss_phase < 3:
            e.boss_phase = 3
            gs.msg("The Vampire Lord screams! Bats swarm from the shadows!", C_RED)
            _bestiary_record(gs, e.etype, "ability", "bat_swarm")
        elif hp_pct <= B["boss_phase2_threshold"] and e.boss_phase < 2:
            e.boss_phase = 2
            e.speed = ENEMY_TYPES[e.etype]["speed"] * 2.0
            gs.msg("The Vampire Lord ENRAGES! Its attacks accelerate!", C_RED)
            _bestiary_record(gs, e.etype, "ability", "enrage")
        # Phase 3: summon bats periodically
        if e.boss_phase >= 3 and e.boss_phase_turn % B["vampire_phase3_bat_interval"] == 0:
            if len(gs.enemies) < 25:
                pos = gs._find_spawn_pos()
                if pos:
                    bat = Enemy(pos[0], pos[1], "bat")
                    bat.alerted = True
                    bat.alertness = "alert"
                    gs.enemies.append(bat)
                    if (pos[0], pos[1]) in gs.visible:
                        gs.msg("A bat swarm appears!", C_MAGENTA)
        # Phase 2+: enhanced lifesteal
        if e.boss_phase >= 2:
            e.lifesteal = True

    elif e.etype == "dread_lord":
        if hp_pct <= B["boss_phase3_threshold"] and e.boss_phase < 3:
            e.boss_phase = 3
            gs.msg("The Dread Lord unleashes a wave of darkness!", C_RED)
            _bestiary_record(gs, e.etype, "ability", "aoe_darkness")
        elif hp_pct <= B["boss_phase2_threshold"] and e.boss_phase < 2:
            e.boss_phase = 2
            e.ai = "chase"  # Stop summoning, switch to aggressive chase
            e.dmg = (e.dmg[0] * 2, e.dmg[1] * 2)
            gs.msg("The Dread Lord ENRAGES! It charges at you with terrible fury!", C_RED)
            _bestiary_record(gs, e.etype, "ability", "enrage_charge")
        # Phase 3: AOE darkness damage to adjacent tiles
        if e.boss_phase >= 3:
            if abs(e.x - p.x) + abs(e.y - p.y) <= 2:
                aoe_dmg = B["dread_phase3_aoe_damage"]
                p.hp -= aoe_dmg
                p.damage_taken += aoe_dmg
                if gs.turn_count % 2 == 0:
                    gs.msg(f"Darkness burns you! (-{aoe_dmg} HP)", C_RED)
                if p.hp <= 0:
                    gs.game_over = True
                    gs.death_cause = f"consumed by {e.name}'s darkness"
                    sound_alert(gs, "death")

    # Mini-boss phases (2 phases: normal and enraged)
    elif e.etype in ("crypt_guardian", "flame_tyrant", "elder_brain", "beast_lord"):
        if hp_pct <= B["mini_boss_phase2_threshold"] and e.boss_phase < 2:
            e.boss_phase = 2
            # Enrage: boost speed and damage
            e.speed = ENEMY_TYPES[e.etype]["speed"] * 1.5
            lo, hi = e.dmg
            e.dmg = (int(lo * 1.3), int(hi * 1.3))
            gs.msg(f"The {e.name} ENRAGES!", C_RED)
            _bestiary_record(gs, e.etype, "ability", "enrage")
            # Type-specific phase 2 effects
            if e.etype == "elder_brain":
                e.paralyze_chance = min(0.60, e.paralyze_chance + 0.20)
                gs.msg("Psychic energy intensifies!", C_MAGENTA)
            elif e.etype == "flame_tyrant":
                e.fire_aura = True
                gs.msg("Flames erupt around the Flame Tyrant!", C_LAVA)
            elif e.etype == "crypt_guardian":
                e.regen = 2
                gs.msg("The Crypt Guardian draws power from the dead!", C_CYAN)
            elif e.etype == "beast_lord":
                # Summon pack allies
                for _ in range(2):
                    pos = gs._find_spawn_pos()
                    if pos and len(gs.enemies) < 25:
                        wolf = Enemy(pos[0], pos[1], "rat")
                        wolf.alerted = True
                        wolf.alertness = "alert"
                        gs.enemies.append(wolf)
                gs.msg("The Beast Lord howls! Pack allies arrive!", C_YELLOW)

    elif e.etype == "abyssal_horror":
        if hp_pct <= B["boss_phase3_threshold"] and e.boss_phase < 3:
            e.boss_phase = 3
            e.regen = 8
            e.speed = ENEMY_TYPES[e.etype]["speed"] * 1.5
            gs.msg("The Abyssal Horror tears reality apart! The void consumes all!", C_RED)
            _bestiary_record(gs, e.etype, "ability", "void_rage")
        elif hp_pct <= B["boss_phase2_threshold"] and e.boss_phase < 2:
            e.boss_phase = 2
            e.ai = "chase"
            lo, hi = e.dmg
            e.dmg = (int(lo * 1.5), int(hi * 1.5))
            gs.msg("The Abyssal Horror ENRAGES! Tentacles lash in all directions!", C_RED)
            _bestiary_record(gs, e.etype, "ability", "enrage")
        # Phase 3: AOE void damage
        if e.boss_phase >= 3:
            if abs(e.x - p.x) + abs(e.y - p.y) <= 3:
                void_dmg = B["dread_phase3_aoe_damage"] + 3
                p.hp -= void_dmg
                p.damage_taken += void_dmg
                if gs.turn_count % 2 == 0:
                    gs.msg(f"The void tears at your soul! (-{void_dmg} HP)", C_MAGENTA)
                if p.hp <= 0:
                    gs.game_over = True
                    gs.death_cause = "consumed by the Abyssal Horror"
                    sound_alert(gs, "death")
        # Phase 2+: summon void stalkers
        if e.boss_phase >= 2 and e.boss_phase_turn % 5 == 0:
            if len(gs.enemies) < 25:
                pos = gs._find_spawn_pos()
                if pos:
                    minion = Enemy(pos[0], pos[1], "void_stalker")
                    minion.alerted = True
                    minion.alertness = "alert"
                    gs.enemies.append(minion)
                    if (pos[0], pos[1]) in gs.visible:
                        gs.msg("A Void Stalker materializes!", C_DARK)

    # Generic mini-boss fallback for new branch bosses
    elif e.etype in ("fungal_queen", "trap_master", "void_herald", "inferno_king"):
        if hp_pct <= B["mini_boss_phase2_threshold"] and e.boss_phase < 2:
            e.boss_phase = 2
            e.speed = ENEMY_TYPES[e.etype]["speed"] * 1.5
            lo, hi = e.dmg
            e.dmg = (int(lo * 1.3), int(hi * 1.3))
            gs.msg(f"The {e.name} ENRAGES!", C_RED)
            _bestiary_record(gs, e.etype, "ability", "enrage")


def _try_enemy_move(gs: GameState, e: Enemy, dx: int, dy: int) -> None:
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


def _flee_move(gs: GameState, e: Enemy) -> None:
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


def _chase_move(gs: GameState, e: Enemy) -> None:
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


def _erratic_move(gs: GameState, e: Enemy) -> None:
    if random.random() < 0.5:
        _chase_move(gs, e)
    else:
        dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
        _try_enemy_move(gs, e, dx, dy)


def _patrol_move(gs: GameState, e: Enemy) -> None:
    dx, dy = e.patrol_dir
    nx, ny = e.x + dx, e.y + dy
    if nx < 0 or nx >= MAP_W or ny < 0 or ny >= MAP_H or gs.tiles[ny][nx] == T_WALL:
        e.patrol_dir = random.choice([(-1,0),(1,0),(0,-1),(0,1)])
    else:
        _try_enemy_move(gs, e, dx, dy)


def _pack_move(gs: GameState, e: Enemy) -> None:
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


def _ambush_move(gs: GameState, e: Enemy) -> None:
    dist = abs(e.x - gs.player.x) + abs(e.y - gs.player.y)
    if dist <= 3:
        _chase_move(gs, e)


def _ranged_move(gs: GameState, e: Enemy) -> None:
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


def _summoner_move(gs: GameState, e: Enemy) -> None:
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


def _mimic_move(gs: GameState, e: Enemy) -> None:
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


def _phase_move(gs: GameState, e: Enemy) -> None:
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


def _mind_flayer_move(gs: GameState, e: Enemy) -> None:
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
