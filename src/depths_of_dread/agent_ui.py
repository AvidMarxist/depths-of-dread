"""
Agent UI module for Depths of Dread.

Contains FeatureTracker, the split-screen agent panel renderer,
and pilot mode key processing.
"""
from __future__ import annotations

import curses
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import AgentPlayer
    from .game import GameState

from .combat import *
from .combat import (
    _award_kill,
    _bestiary_record,
    _chase_move,
    _check_levelups,
    _check_traps_on_move,
    _compute_noise,
    _disarm_trap,
    _flee_move,
    _passive_trap_detect,
    _search_for_traps,
    _stealth_detection,
    _trigger_trap,
    _try_enemy_move,
    _update_boss_phase,
)
from .constants import *
from .constants import _CHALLENGE_MODES, _DIR_MAP
from .entities import *
from .entities import _unlock_next_ability, _unlock_next_spell
from .items import *
from .items import (
    _animate_projectile,
    _apply_spell_resist,
    _cast_spell,
    _execute_ability,
    _get_direction_delta,
    _interact_npc,
    _interact_pedestal,
    _journal_potion_desc,
    _journal_scroll_desc,
    _launch_projectile,
    _process_branch_effects,
    _toggle_switch,
)
from .mapgen import *
from .mapgen import _has_los, astar, compute_fov
from .persistence import *
from .persistence import (
    _compute_checksum,
    _default_lifetime_stats,
    _deserialize_enemy,
    _deserialize_item,
    _deserialize_item_ground,
    _format_lifetime_stats_lines,
    _serialize_enemy,
    _serialize_item,
    _serialize_item_on_ground,
)
from .ui import *
from .ui import _bfs_unexplored, _describe_tile, _draw_tile, _inv_key_to_idx, _inv_letter


def _get_game() -> Any:
    from . import game
    return game


class FeatureTracker:
    """Track which game features the agent encounters and interacts with."""

    def __init__(self) -> None:
        self.features: dict[str, dict[str, Any]] = {
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
        self.classes_played: set[str] = set()
        self.spells_cast: set[str] = set()
        self.abilities_used: set[str] = set()

    def check_state(self, gs: GameState, action_str: str = "") -> None:
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

    def coverage_pct(self) -> float:
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

    def report(self) -> str:
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


AGENT_PANEL_X = 82  # Right panel starts 2 cols after game area (col 80)
AGENT_PANEL_MIN_W = 50  # Minimum panel width to be useful
AGENT_SPLIT_MIN_COLS = AGENT_PANEL_X + AGENT_PANEL_MIN_W  # 132 cols needed


def _render_agent_panel(scr: Any, agent: AgentPlayer, gs: GameState, decision_log: deque[dict[str, Any]]) -> None:
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

def _pilot_process_key(gs: GameState, scr: Any, key: int) -> bool:
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
                _get_game()._show_branch_choice(scr, gs, new_floor)
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
    elif key == ord('/'):
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
