# Expert Security & Performance Audit: Depths of Dread

**Auditor:** Claude Opus 4.6 (External Expert Analysis)
**Date:** 2026-03-01
**Scope:** `dungeon.py` (~6,978 lines) — single-file terminal roguelike with agent mode
**Framework:** Python security best practices, subprocess security, file I/O security

---

## Table of Contents

1. [Subprocess Security Analysis](#1-subprocess-security-analysis)
2. [Save File Security Analysis](#2-save-file-security-analysis)
3. [File I/O Security Analysis](#3-file-io-security-analysis)
4. [Performance Analysis](#4-performance-analysis)
5. [Remediation Recommendations](#5-remediation-recommendations)

---

## 1. Subprocess Security Analysis

### Agent Mode — `_call_claude()` (line 5972)

**Implementation:**
```python
cmd = [
    CLAUDE_BIN,
    "-p", "-",
    "--output-format", "json",
    "--model", "haiku",
    "--system-prompt", AGENT_SYSTEM_PROMPT,
    "--max-turns", "1",
    "--setting-sources", "",
]
result = subprocess.run(
    cmd, input=state_text,
    capture_output=True, text=True, timeout=timeout, env=env,
)
```

### Assessment: PASS (Well-Designed)

| Check | Status | Details |
|-------|--------|---------|
| Shell injection | PASS | Uses list form of `subprocess.run()` — no shell interpretation. Arguments are passed directly to execvp, not through a shell. |
| Input injection | PASS | `state_text` is passed via `input=` parameter (stdin pipe), not as a command-line argument. This avoids arg length limits and shell escaping issues. |
| Environment isolation | PASS | `env = os.environ.copy()` with `env.pop("CLAUDECODE", None)` — prevents nested session errors. Clean env inheritance. |
| Timeout protection | PASS | Two-tier timeout (15s, 10s) with `subprocess.TimeoutExpired` handling. Prevents infinite hangs. |
| Output parsing | PASS | `json.loads()` on stdout — safe. JSON parsing cannot execute code in Python. |
| Error handling | PASS | Return code check, stderr logging (truncated to 200 chars), graceful fallback to BotPlayer. |
| Binary path | INFO | `CLAUDE_BIN` is likely resolved from PATH. If an attacker can modify PATH or place a malicious `claude` binary earlier in PATH, they could intercept. However, this requires local system access, which is already game-over. |

### Potential Concern: System Prompt Injection

The `AGENT_SYSTEM_PROMPT` constant contains instructions for Claude. The `state_text` sent via stdin contains game state including enemy names, item names, and room descriptions — all from hardcoded constants. **No user-controlled text is included in the prompt** (no player-named items, no custom messages). This means prompt injection from game data is not possible with the current design.

**If the game ever adds player-named items, custom messages, or mod support**, the state serialization would need sanitization before sending to Claude.

---

## 2. Save File Security Analysis

### Save Mechanism (line 4355)

**Implementation:**
- JSON serialization via `json.dumps()` with compact separators
- SHA256 checksum computed on the JSON string
- Wrapper format: `{"checksum": "<hash>", "data": {...}}`
- Written to `~/.depths_of_dread_save.json`

### Load Mechanism (line 4424)

**Implementation:**
- Read JSON file via `json.load()`
- Recompute checksum, compare with stored checksum
- If mismatch, return None (reject file)
- Reconstruct GameState from data fields

### Assessment: GOOD with Caveats

| Check | Status | Details |
|-------|--------|---------|
| Deserialization attacks | PASS | Uses `json.load()` not `pickle.load()`. JSON cannot execute arbitrary code during deserialization. No `eval()` on loaded data. |
| Prototype pollution | N/A | Python dicts don't have prototype chains. Not applicable. |
| Checksum integrity | PARTIAL | SHA256 checksum prevents accidental corruption, but the checksum algorithm is not keyed (no HMAC). An attacker who can edit the save file can also recompute the checksum. This makes the checksum a **corruption detector, not a tamper detector**. |
| Data validation | PARTIAL | Individual fields are accessed by key (`pd["x"]`, `pd["hp"]`, etc.) with `.get()` for optional fields. No type validation — if `pd["hp"]` is a string instead of int, the game may crash later. |
| Path traversal | PASS | Save file path is hardcoded to `~/.depths_of_dread_save.json` (expanded via `os.path.expanduser`). No user input in the path. |
| File permissions | INFO | File is created with default umask permissions. On multi-user systems, other users may be able to read the save file. Not a concern for a single-player game on a personal machine. |
| Save file deletion | PASS | After loading, the save file is deleted (`os.remove`) to enforce permadeath. Correct behavior. |

### Checksum Weakness Detail

The current checksum is:
```python
hashlib.sha256(data_str.encode('utf-8')).hexdigest()
```

This is a plain hash, not an HMAC. To cheat, a player would:
1. Edit the JSON data (give themselves 999 HP, etc.)
2. Recompute `sha256(modified_json)`
3. Replace the checksum

This is trivial. However, **this is a single-player game where the player is also the "attacker."** Cheating in your own single-player roguelike is a non-issue. The checksum serves its intended purpose: detecting accidental file corruption or partial writes.

**If competitive leaderboards or achievements are ever added**, the checksum would need to be upgraded to HMAC with a key (though even that is bypassable with decompilation).

### Recording Files (line 5057)

- JSONL format written to `~/.depths_of_dread_recordings/`
- Files contain game events (inputs, snapshots, deaths)
- **No sensitive data** — only game state
- **Replay reads files and feeds recorded inputs** — no code execution
- Path constructed from `RECORDINGS_DIR` constant + timestamp — no user input in paths
- **Assessment: PASS**

### Stats File (line 4267)

- JSON written to `~/.depths_of_dread_stats.json`
- Contains lifetime statistics (games played, total kills, etc.)
- `json.dump()` / `json.load()` — safe
- Corrupt file handling: caught by try/except, returns empty stats — PASS
- **Assessment: PASS**

---

## 3. File I/O Security Analysis

| File Operation | Path | User-Controlled? | Assessment |
|---------------|------|-------------------|------------|
| Save game | `~/.depths_of_dread_save.json` | No | SAFE |
| Load game | `~/.depths_of_dread_save.json` | No | SAFE |
| Stats read/write | `~/.depths_of_dread_stats.json` | No | SAFE |
| Agent log | `~/.depths_of_dread_agent.log` | No | SAFE |
| Recordings write | `~/.depths_of_dread_recordings/<timestamp>.jsonl` | No (timestamp auto-generated) | SAFE |
| Recordings read (replay) | User-specified via `--replay <path>` | YES | See below |

### Replay File Path (User-Controlled)

```python
# From argparse
parser.add_argument('--replay', type=str, help='...')
```

The `--replay` argument accepts an arbitrary file path from the command line. The file is opened with:
```python
with open(replay_path, 'r') as fh:
    first = json.loads(fh.readline())
```

**Risk assessment:**
- **Path traversal:** A user could specify `--replay /etc/passwd` — the file would be opened and the first line parsed as JSON. This would fail at `json.loads()` and be caught by the try/except. No data exfiltration occurs.
- **Arbitrary file read:** The replay function reads all lines and parses each as JSON. Non-JSON files simply fail to parse. No file contents are displayed to the user on parse failure.
- **Symlink attacks:** If a symlink at the recording path points to a sensitive file, the same JSON-parse-or-fail behavior applies.

**Assessment: LOW RISK** — The worst case is a confusing error message. No data exfiltration or code execution is possible. The user running the game already has full filesystem access.

---

## 4. Performance Analysis

### Enemy Iteration Patterns

| Operation | Complexity | Frequency | Concern |
|-----------|-----------|-----------|---------|
| `process_enemies()` | O(E) per turn where E = enemies | Every turn | ACCEPTABLE |
| Enemy A* pathfinding | O(V log V) per enemy per turn (V = walkable tiles) | Every turn for each chasing enemy | MEDIUM — see below |
| Pack AI (`_pack_move`) | O(E^2) — each pack enemy checks distance to all other enemies | Every turn for pack enemies | LOW — pack enemies typically 3-5 |
| Mind Flayer AI | O(1) — distance check to player | Every turn per mind flayer | ACCEPTABLE |
| Mimic AI | O(1) — proximity check | Every turn per mimic | ACCEPTABLE |
| Phase Spider AI | O(V) — BFS for teleport destination | Every 3 turns per phase spider | ACCEPTABLE |

#### A* Pathfinding Performance

Each enemy with `chase` AI runs A* to the player every turn. With:
- Map size: 80x40 = 3,200 tiles
- Walkable tiles: ~800-1,500 (BSP dungeons, ~30-45% open)
- Enemies per floor: 5 + 2*floor + random(3) = ~10-35 enemies

Worst case: 35 enemies x A* with 1,500 nodes = 35 * O(1500 * log(1500)) = ~35 * 16,000 = ~560,000 operations per turn.

**This was already optimized** by switching from `list.sort()` to `heapq` (bug fix from code review). Current implementation is efficient.

**Potential optimization:** Spatial hashing or a grid-based distance check before running A* — skip pathfinding for enemies far from the player (>FOV_RADIUS * 2). Currently, all enemies pathfind regardless of distance.

### FOV Computation

| Operation | Complexity | Frequency |
|-----------|-----------|-----------|
| Shadowcasting FOV | O(R^2) where R = FOV_RADIUS (8) | Every turn (via render) |

O(64) per turn for FOV — negligible. PASS.

### Memory Allocation in Hot Loops

| Pattern | Location | Concern |
|---------|----------|---------|
| List comprehensions in render | `render_map()` | Creates new lists each frame — acceptable for curses rendering |
| `explored[][]` — 80x40 bool array | Persistent | ~3.2KB — negligible |
| `tiles[][]` — 80x40 int array | Persistent | ~3.2KB — negligible |
| `fov_cache` set | Rebuilt each turn | ~200-300 entries (tiles in FOV) — negligible |
| Enemy list | Persistent, shrinks as enemies die | ~35 enemy objects max — negligible |
| Item list | Persistent | ~50 items max — negligible |
| A* open set (heapq) | Per pathfind call, GC'd after | ~100-500 entries — acceptable |
| Agent state serialization | Per Claude call (~every 3-5 turns) | String building, ~500 chars — negligible |
| Session recordings | JSONL append | ~100 bytes per event — negligible |

**No memory leaks detected.** Python's GC handles all temporary allocations. The game's memory footprint is trivially small (<10MB even on deep floors).

### Agent Mode Performance Bottleneck

The primary performance bottleneck in agent mode is **Claude API latency** (3-15 seconds per call), not computation. The game logic itself runs in microseconds between calls. This is inherent to the architecture and cannot be optimized without changing the approach (e.g., local model inference).

**Current optimizations already applied:**
- Compressed system prompt (65% reduction)
- Compressed state serialization (40% reduction)
- Stdin piping instead of command-line arguments
- Two-tier timeout with retry
- BotPlayer fallback on failure
- Health baselines with anomaly detection

---

## 5. Remediation Recommendations

### P0 — None Required

The game has no critical security vulnerabilities. It's a single-player terminal game with no network exposure, no user authentication, and no sensitive data handling.

### P1 — Recommended Improvements

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 1 | **Add type validation to `load_game()`** — verify `pd["hp"]` is int, `pd["x"]` is int, etc. A corrupted save file that passes checksum but has wrong types would crash the game instead of being rejected gracefully. | 30 min | Robustness |
| 2 | **Skip A* for distant enemies** — enemies beyond `FOV_RADIUS * 2` (16 tiles) could use simple direction-toward-player movement instead of full A*. Reduces pathfinding calls by ~50% on dense floors. | 30 min | Performance on deep floors |
| 3 | **Sanitize replay path** — validate that `--replay` path ends in `.jsonl` and is within `RECORDINGS_DIR`. Not a security risk but prevents confusing errors. | 10 min | UX |

### P2 — Optional Enhancements

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 4 | **HMAC for save integrity** — use a machine-specific key (e.g., derived from hostname + username) for save file checksums. Prevents trivial save editing. Only matters if leaderboards are added. | 20 min | Anti-cheat (if leaderboards exist) |
| 5 | **Restrict recording file permissions** — `os.chmod(recording_path, 0o600)` after creation. Not needed on single-user machines but good practice. | 5 min | Defense-in-depth |
| 6 | **Agent state sanitization hook** — add a comment/placeholder for sanitizing state text before sending to Claude, in case player-named items are ever added. | 5 min | Future-proofing |

### Overall Assessment

**The Depths of Dread codebase is well-secured for its threat model.** It's a single-player local game with:
- No network attack surface (agent mode calls `claude` binary locally)
- No user authentication or authorization
- No sensitive data beyond game state
- Hardcoded file paths (no path traversal)
- JSON-only serialization (no deserialization attacks)
- Proper subprocess handling (list form, stdin piping, timeouts)

The primary "attacker" is the player themselves (save editing), which is a design choice (permadeath) rather than a security concern. The SHA256 checksum is an appropriate deterrent for accidental corruption.

---

## Appendix: Files Analyzed

- `/Users/will/Scripts/dungeon.py` — Main game file (~6,978 lines)
- Agent mode: `AgentPlayer` class (line 5676), `_call_claude()` (line 5972)
- Save/load: `save_game()` (line 4355), `load_game()` (line 4424)
- Recordings: `SessionRecorder` class (line 5057)
- Stats: `_save_stats()` (line 4267)
