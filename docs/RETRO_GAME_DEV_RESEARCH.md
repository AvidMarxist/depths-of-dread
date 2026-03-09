# Retro Game Development Research: Can Claude Help Build an NES/SNES Game?

**Research Date:** March 5, 2026
**Author:** Will Rompf + Claude

---

## Table of Contents

1. [NES Game Development](#1-nes-game-development)
2. [SNES Game Development](#2-snes-game-development)
3. [Modern Retro Dev Tools](#3-modern-retro-dev-tools)
4. [What Makes Sense for Will + Claude](#4-what-makes-sense-for-will--claude)
5. [The Coolest Option](#5-the-coolest-option)
6. [Recommendation & Action Plan](#6-recommendation--action-plan)

---

## 1. NES Game Development

### Languages & Tools

| Tool | Type | Notes |
|------|------|-------|
| **cc65** (ca65 + ld65) | C compiler + assembler + linker | The dominant toolchain. Compiles C and 6502 assembly to .nes ROMs |
| **NESFab** | Custom language + IDE | Purpose-built NES language with asset management and level editing |
| **NESmaker** ($36) | GUI-based, no-code | Drag-and-drop game maker, generates 6502 assembly behind the scenes. Rebranding as "Retro Game Forge" with SNES support coming |
| **NESASM (MagicKit)** | Assembler | Alternative to ca65, simpler but less flexible |
| **Mesen** | Emulator + debugger | Best-in-class for testing, has memory viewer, breakpoints, PPU viewer |
| **FCEUX** | Emulator + debugger | Older but solid, extensive debugging tools |

**The standard workflow is:** Write C or 6502 assembly --> Compile with cc65/ca65 --> Link with ld65 using a .cfg memory map --> Test in Mesen emulator --> Iterate --> Flash to physical cart

The most popular modern approach is **C with neslib** via cc65. You write C, call neslib functions for sprites/backgrounds/input, and the compiler handles the 6502 translation. Pure assembly gives you more control and performance, but C gets you to a working game faster.

### Technical Constraints (This Is Where It Gets Real)

| Spec | Value | What This Means |
|------|-------|-----------------|
| **CPU** | Ricoh 2A03, 1.79 MHz (NTSC) | Custom 6502 variant. Roughly 30,000 cycles per frame at 60fps |
| **RAM** | 2 KB | Yes, two kilobytes. Total. For everything. |
| **VRAM** | 2 KB | For nametables (background tile maps) |
| **PRG ROM** | 32 KB (no mapper) / up to 512 KB+ (with mapper) | Your code and data. Mappers bank-switch to access more |
| **CHR ROM** | 8 KB (no mapper) / up to 256 KB+ (with mapper) | All your sprite and background tile graphics |
| **Resolution** | 256 x 240 pixels | Fixed, no changing this |
| **Colors** | 64 total palette, **25 on screen** | 4 background palettes (3 colors + shared BG each), 4 sprite palettes (3 colors + transparent each) |
| **Background tiles** | 256 unique 8x8 tiles | Each 16x16 area locked to one of 4 palettes |
| **Sprites** | 64 total, max **8 per scanline** | More than 8 on same horizontal line = flicker |
| **Sprite sizes** | 8x8 or 8x16 pixels | One mode per frame, applies to ALL sprites |
| **Sound** | 2 pulse, 1 triangle, 1 noise, 1 DPCM | Five channels, that's it |

**The 2 KB RAM limit is the brutal one.** Your entire game state -- player position, enemy positions, score, level data, animation frames, input buffers -- all fits in 2,048 bytes. Mappers on the cartridge add more ROM (for code and assets), but RAM stays at 2 KB unless the cart has extra RAM chips.

The **attribute table** constraint is why NES games look "blocky" -- every 16x16 pixel area of the background must share the same 3-color palette. You cannot have pixel-level palette control on backgrounds.

### Can Claude Write 6502 Assembly or C for NES?

**Short answer: Yes, with caveats.**

Claude can write 6502 assembly code. The 6502 instruction set is well-documented, extensively discussed online, and relatively simple (56 instructions). Claude handles small, well-defined routines well -- multiplication routines, sprite movement, input handling, collision detection.

**What Claude is good at:**
- Writing individual 6502 routines (sprite update logic, math, input polling)
- C code targeting cc65/neslib (higher-level game logic)
- Explaining NES hardware registers and PPU behavior
- Generating boilerplate (iNES headers, memory maps, init code)
- Debugging assembly logic

**What Claude struggles with:**
- Large-scale 6502 architecture decisions (bank switching strategies, memory layout)
- PPU timing-critical code (mid-frame palette swaps, raster effects)
- Optimizing for the 2 KB RAM constraint (this requires deep NES knowledge)
- Pixel art and CHR ROM data (Claude can describe but not visually design)

**Real-world evidence:** Developers have used LLMs to generate working 6502 code for Commodore 64 sprite routines. Amazon Q Developer was tested writing 6502 assembly. Results are promising for small tasks, mediocre for full system architecture. Claude (Opus) would do better than most LLMs here given its reasoning capabilities, but NES dev has enough hardware-specific gotchas that it would require significant human oversight.

### Dev Workflow

```
1. Write code (C or 6502 ASM, or mix)
2. Create graphics in a tile editor (YY-CHR, NES Screen Tool, Aseprite)
3. Create music/SFX (FamiTracker, FamiStudio)
4. Compile: ca65 source.s -o source.o
5. Link:    ld65 source.o -C nes.cfg -o game.nes
6. Test in Mesen (debug, memory inspect, PPU viewer)
7. Iterate steps 1-6 approximately 500 times
8. Flash to physical cartridge (see below)
```

A Makefile automates steps 4-5. The compile-test cycle is fast (sub-second builds).

### How Hard Is It Really?

**Difficulty: 7/10 for a simple game, 9/10 for anything complex.**

- A developer with no prior 6502 experience built a simple game in **3 weekends**
- A professional game programmer spent **2 weeks** getting basic gameplay for a Tetris clone
- One developer planned a "small game in about a month" and it took **nearly 2 years**
- Code is nearly always the bottleneck, not graphics or music

**Realistic first project:** A Tetris clone or a simple single-screen action game (think early arcade: dodge enemies, collect items, score counter). Tetris is the canonical NES first project because it exercises all the basics (input, rendering, game logic, sound) without requiring scrolling or complex AI.

**What makes NES dev hard:**
- The PPU (graphics chip) is a separate processor with its own rules and timing
- You cannot access VRAM while the PPU is rendering -- only during VBlank (~2,270 CPU cycles)
- The attribute table system makes colorful backgrounds surprisingly complex
- 2 KB RAM forces you to think about every single byte
- No floating point, limited multiplication/division (the 6502 has no multiply instruction)

### Flashing to Physical Cartridge

**Yes, you can absolutely make a real NES cart.** Several options:

| Method | Cost | Difficulty | Notes |
|--------|------|------------|-------|
| **Donor cart + EPROM** | ~$10-20 + $50 programmer | Medium | Buy a cheap NES game, replace ROM chip with programmed EPROM. Need soldering skills and a compatible mapper. |
| **INLretro USB programmer** | ~$60-80 | Easy | USB device from Infinite NES Lives. Program flash carts directly from your computer. Purpose-built for homebrew. |
| **RetroUSB blank PCBs** | ~$15-25/board | Medium | Blank NES PCBs designed for homebrew. Populate with flash chips and program. |
| **Custom PCB** | ~$5-50 depending on quantity | Hard | Design your own PCB (KiCad), order from JLCPCB/PCBWay. Full control but requires electronics knowledge. |
| **Everdrive N8** | ~$100-170 | Trivial | Flash cart that plays any ROM. Great for testing, but it's not YOUR cartridge with YOUR label. |

For a complete "boxed" release (cart + label + box + manual), services exist in the homebrew community, or you can DIY with a donor cart, custom label printing, and a Universal Game Case.

### Notable Homebrew NES Games

- **Micro Mages** -- 4-player co-op platformer that fits in 40 KB. Available on NES cart, Steam, and Evercade. Widely considered the gold standard of NES homebrew.
- **From Below** -- Tetris variant where you fight a Kraken. Modern mechanics (wall kicks, hard drops) + creative twist.
- **Nebs 'n Debs** -- Challenging platformer with a dash mechanic, secrets, and a second quest.
- **Spacegulls** -- Co-op platformer, won the 2020/21 NESDev Competition.
- **Anguna: Goblin King** -- Action RPG with quality comparable to official Nintendo releases.
- **The Legends of Owlia** -- Zelda-like adventure, full cartridge release with box and manual.
- **Battle Kid** -- Infamously difficult platformer, multiple physical releases.

The NES homebrew scene is thriving. There are annual competitions (NESDev Compo) and a ranked list of 250+ homebrew titles.

---

## 2. SNES Game Development

### Languages & Tools

| Tool | Type | Notes |
|------|------|-------|
| **PVSnesLib** | C library + toolchain | The cc65 equivalent for SNES. Uses 816-tcc compiler, wla-65816 assembler |
| **SNES-IDE** | IDE for PVSnesLib | Cross-platform IDE with templates and build automation (2025) |
| **bsnes-plus** | Emulator + debugger | Fork of bsnes with debugging tools (breakpoints, memory viewer, VRAM viewer) |
| **Mesen-S** | Emulator + debugger | Mesen's SNES variant, excellent debugging |
| **wla-65816** | Assembler | Standalone 65816 assembler, also used within PVSnesLib |
| **64tass** | Assembler | Another 65816 cross-assembler option |

### Technical Specs

| Spec | NES | SNES | Improvement |
|------|-----|------|-------------|
| **CPU** | 6502, 1.79 MHz | 65816, 3.58 MHz | 2x clock, 16-bit capable |
| **RAM** | 2 KB | 128 KB | **64x more RAM** |
| **VRAM** | 2 KB | 64 KB | 32x more VRAM |
| **Resolution** | 256x240 | 256x224 to 512x448 | Multiple modes |
| **Colors** | 25 on screen / 64 total | 256 on screen / 32,768 total | Massively more color |
| **BG layers** | 1 | Up to 4 | Parallax scrolling, transparency |
| **Sprites on screen** | 64 | 128 | 2x more sprites |
| **Sprites per scanline** | 8 | 32 | 4x more before flicker |
| **Sprite size** | 8x8 or 8x16 | 8x8 to 64x64 | Much larger sprites |
| **Sound** | 5 channels (synthesis) | 8 channels (16-bit PCM, 32 kHz) | Sample-based audio |
| **Special** | Nothing | **Mode 7** (rotation, scaling) | Pseudo-3D effects |

**The SNES is dramatically more capable.** 128 KB of RAM vs 2 KB is the single biggest difference -- you can actually have complex game state, larger levels, more enemy types. Mode 7 enables rotation and scaling effects (F-Zero, Mario Kart, Pilotwings).

### SNES Dev Difficulty

**Harder than NES in some ways, easier in others.**

The 65816 CPU is backward-compatible with the 6502 but adds 16-bit operations, more addressing modes, and a more complex register model. PVSnesLib lets you write C, which helps enormously, but the library has quirks and the documentation is thinner than NES resources.

The SNES homebrew community is smaller than NES. There's an annual SNESDEV game jam on itch.io (SNESDEV 2025 ran recently), but the volume of tutorials, examples, and community support is noticeably less than NES.

**Bottom line:** If you're going to invest in learning retro console dev, NES has better resources and community support. SNES gives you more hardware headroom but a lonelier development experience.

---

## 3. Modern Retro Dev Tools

### Tier 1: Actual Retro Hardware Targets

| Tool | Platform | Language | Price | Output | Difficulty |
|------|----------|----------|-------|--------|------------|
| **GB Studio** | Game Boy / GBC | Visual scripting (no code) | Free | .gb ROM, .pocket, web | 2/10 |
| **cc65 + neslib** | NES | C / 6502 ASM | Free | .nes ROM | 7/10 |
| **PVSnesLib** | SNES | C / 65816 ASM | Free | .sfc ROM | 8/10 |
| **NESmaker** | NES | GUI + 6502 ASM | $36 | .nes ROM | 5/10 |
| **GBDK-2020** | Game Boy | C | Free | .gb ROM | 6/10 |

### Tier 2: Fantasy Consoles (Retro Constraints, Modern Convenience)

| Tool | Resolution | Colors | Language | Price | Distribution |
|------|-----------|--------|----------|-------|--------------|
| **PICO-8** | 128x128 | 16 | Lua (subset) | $15 | Web, exe, .png carts |
| **TIC-80** | 240x136 | 16 | Lua, JS, Python, Ruby, + more | Free / $5 pro | Web, exe |
| **Pyxel** | Configurable | 16 | Python | Free | Web, exe |

### Tier 3: Retro-Aesthetic Modern Engines

| Tool | Style | Language | Notes |
|------|-------|----------|-------|
| **Love2D** | Any (often pixel art) | Lua | Full-featured 2D engine, no constraints |
| **Pyxel** | 8-bit aesthetic | Python | Retro constraints baked in, Python-native |
| **Bitsy** | 1-bit, tiny | Visual | Narrative micro-games |
| **Pulp** | Playdate | Visual + PulpScript | For Playdate handheld specifically |
| **RPG Maker** | JRPG | Ruby/JS | Pixel art RPGs, massive community |
| **Godot** | Any | GDScript/C# | Can do retro, but it's a full modern engine |

### Deep Dive: The Most Relevant Options

#### PICO-8 -- The Sweet Spot

PICO-8 is a "fantasy console" -- it doesn't correspond to real hardware, but its constraints are carefully designed to feel like an 8-bit system:

- 128x128 pixel display
- 16 fixed colors
- 256 8x8 sprites
- 128 8x8 map tiles (128x32 map)
- 4-channel sound
- 8,192 token code limit (~5-10 KB of Lua)
- 32 KB total cart size
- Built-in sprite editor, map editor, sound editor, music tracker

**Why PICO-8 matters:** It strips away all the hardware complexity of real NES/SNES dev (no PPU timing, no bank switching, no memory maps) while preserving the creative constraint that makes retro dev fun. You focus on game design, not hardware registers.

**Claude + PICO-8 is a proven combination.** Developers have built complete games (Mastermind clones, platformers, puzzle games) using Claude to generate all the Lua code via natural language prompts. There's even a thread on the Lexaloffle BBS specifically about "Claude Code and PICO-8."

#### GB Studio -- The Easiest Path to Real Hardware

GB Studio produces actual Game Boy ROMs that run on real Game Boy hardware and Analogue Pocket. No coding required -- you use a visual event system to script game logic. Supports:

- Top-down RPGs, platformers, adventure games, shmups
- Built-in music editor (GBT Player)
- Export to .gb ROM, .pocket format, or web
- Over 1,000 games made with GB Studio

The catch: you're limited to what GB Studio's scripting system can express. Complex game logic requires workarounds. If you want full control, you'd use GBDK-2020 (C) instead.

#### Pyxel -- Python Retro Engine

This is the most natural fit for a Python developer:

- Write games in Python
- PICO-8-inspired constraints (16 colors, built-in editors)
- `pip install pyxel` and you're running
- Web export (runs in browser without Python)
- No real hardware target, but the games look and feel retro

---

## 4. What Makes Sense for Will + Claude

### Your Profile

- Strong Python developer
- Comfortable with technical depth (you wrote a 9,100-line roguelike)
- Experience with game AI (BotPlayer, AgentPlayer in Depths of Dread)
- You enjoy systems design and understanding "why"
- You have Claude Max (parallel agents, background tasks)
- You appreciate constraints that drive creativity

### Option Matrix

| Path | Fun Factor | Impressiveness | Claude Leverage | Time to First Result | Physical Artifact |
|------|-----------|---------------|-----------------|---------------------|-------------------|
| **PICO-8 game** | 9/10 | 6/10 | 10/10 | 1-2 weekends | No (digital only) |
| **Pyxel game** | 8/10 | 5/10 | 10/10 | 1 weekend | No (digital only) |
| **GB Studio game** | 7/10 | 8/10 | 3/10 | 2-3 weekends | Yes (GB cart, Analogue Pocket) |
| **NES game (C/cc65)** | 8/10 | 10/10 | 7/10 | 4-8 weekends | Yes (NES cartridge) |
| **NES game (NESmaker)** | 6/10 | 8/10 | 2/10 | 2-4 weekends | Yes (NES cartridge) |
| **SNES game** | 7/10 | 9/10 | 6/10 | 8-16 weekends | Yes (SNES cartridge) |

### Can We Port Depths of Dread to NES?

**No.** Not even close to a direct port. Here's why:

- Depths of Dread uses ~9,100 lines of Python with complex data structures (dictionaries, lists, classes)
- The NES has 2 KB of RAM. A single floor of your dungeon (BSP-generated, 80x25 tiles) would need 2,000 bytes just for the tile map -- that's your entire RAM budget
- Shadowcasting FOV, A* pathfinding, 23 enemy types with distinct AI -- none of this fits
- The NES can display 256 unique 8x8 tiles. Your game needs far more visual variety

**BUT -- a simplified "NES Depths of Dread" is totally viable:**

- Smaller maps (16x15 tiles, one screen, no scrolling)
- 3-4 enemy types instead of 23
- Simplified combat (no status effects, no elemental system)
- Pre-generated levels stored in ROM instead of runtime BSP
- Single character class
- Think "NES roguelike" not "Depths of Dread port"

This would be more like creating a new game inspired by Depths of Dread that fits NES constraints. Games like Fatal Labyrinth (Genesis) and Dragon Crystal (Game Gear) prove roguelikes can work on limited hardware.

### What About a NEW Game Designed for NES?

This is the right approach. Design for the constraints from the start:

**A single-screen action game** (like Bubble Bobble, Snow Bros, or Clu Clu Land):
- One screen, no scrolling (eliminates the hardest NES programming challenge)
- 2-4 enemy types
- Simple scoring mechanics
- Playable in 2-3 minutes per game
- 20-30 levels stored in ROM

**A simple roguelike-lite:**
- One-screen dungeon rooms
- Turn-based (no real-time pressure on CPU)
- 4-5 enemy types, simple AI
- Procedural generation via lookup tables (not runtime algorithms)
- Would be unique in the NES homebrew space

---

## 5. The Coolest Option

### Ranking by "Wow Factor"

**1. A physical NES cartridge with a custom game (10/10 cool)**

Nothing beats handing someone a real NES cartridge with your name on it, popping it into a console, and playing YOUR game. The homebrew community has well-established paths for producing carts with custom labels, boxes, and even instruction booklets. A small run of 5-10 carts costs maybe $150-300 total.

Estimated timeline: 3-6 months of weekend work for a polished single-screen game.

**2. A Game Boy ROM playable on Analogue Pocket (9/10 cool)**

GB Studio makes this the most accessible path. Build a game with visual scripting, export as .gb ROM, load it on Analogue Pocket via the .pocket format. You could also flash it to a physical Game Boy cartridge.

Estimated timeline: 2-4 weekends for a simple adventure/RPG, 4-8 weekends for something polished.

**3. A PICO-8 game (7/10 cool, but fastest)**

Highest Claude leverage, fastest to a playable result. PICO-8 games are shareable as PNG images (the cartridge IS the image file), playable in any browser, and have an active community. But no physical artifact.

Estimated timeline: 1-2 weekends for a complete, polished game.

### The Most IMPRESSIVE Thing We Could Build

**A turn-based roguelike NES cartridge.**

Here's why this is the play:

1. **Unique in the NES homebrew space** -- there are very few roguelikes for NES. It would stand out.
2. **Plays to your strengths** -- you already built a roguelike. You understand the design patterns.
3. **Turn-based = NES-friendly** -- no real-time performance pressure. Each turn can take as many CPU cycles as needed.
4. **Claude can handle the C code** -- game logic in C via cc65 is well within Claude's capabilities. The NES-specific parts (PPU setup, sprite handling) are well-documented patterns.
5. **Physical cartridge as the end goal** -- design, play, then flash to a cart.

**Scope for an NES roguelike:**
- 16x12 tile dungeon rooms (single screen, no scrolling)
- 4 enemy types with simple AI (approach player, random walk, ranged attack, stationary)
- Turn-based movement and combat
- 5-10 procedurally-selected rooms per run
- HP, attack power, maybe one item slot
- Permadeath (obviously)
- Target: 32 KB PRG ROM, no mapper (simplest cart hardware)

---

## 6. Recommendation & Action Plan

### The Recommended Path: Two-Phase Approach

**Phase 1: PICO-8 Prototype (1-2 weekends)**

Build the roguelike concept in PICO-8 first:
- Claude writes all the Lua code
- You iterate on game design without fighting hardware
- Validate that the core loop is fun
- PICO-8's 128x128 display is close to NES single-screen constraints
- Cost: $15 for PICO-8

**Phase 2: NES Port (2-4 months of weekends)**

Once the design is proven, port to NES:
- Set up cc65 toolchain (Claude helps with Makefile, config)
- Claude translates game logic from Lua to C
- You learn NES-specific parts (PPU, sprites) incrementally
- Test in Mesen emulator throughout
- Final step: flash to physical cartridge

**Why this approach:**
- You get a playable game in days, not months
- You validate game design before committing to NES constraints
- The PICO-8 version is shareable and fun on its own
- Phase 2 is optional -- you only do it if Phase 1 is satisfying
- If you go to Phase 2, you already have a proven design

### Shopping List

| Item | Cost | When |
|------|------|------|
| PICO-8 license | $15 | Phase 1, Day 1 |
| cc65 toolchain | Free | Phase 2 |
| Mesen emulator | Free | Phase 2 |
| NES Screen Tool | Free | Phase 2 |
| FamiStudio (music) | Free | Phase 2 |
| INLretro USB programmer | ~$65 | Phase 2, end |
| Flash cart + donor shell | ~$20-30 | Phase 2, end |
| Custom label printing | ~$10-15 | Phase 2, end |

**Total cost to physical NES cartridge: ~$125-140**

### What Claude Brings to the Table

- Write all PICO-8 Lua code from game design descriptions
- Translate Lua game logic to C for cc65
- Generate 6502 assembly for performance-critical routines
- Help with NES memory layout and bank configuration
- Debug hardware register issues by analyzing symptoms
- Explain PPU behavior, sprite limitations, palette constraints
- Generate Makefiles and build configurations
- Cannot: create pixel art, compose music (describe/suggest only)

### Honest Assessment

| Claim | Reality |
|-------|---------|
| "Claude can build an NES game" | Claude can write most of the code, but you need to understand NES hardware to debug and optimize. It's a collaboration, not autopilot. |
| "It'll take a weekend" | A PICO-8 game, yes. An NES game, no. Budget 3-6 months of casual weekend work for something polished. |
| "Anyone can do it" | NES dev requires patience with arcane hardware. The PPU will make you question your life choices at least twice. C via cc65 softens this considerably. |
| "The physical cart is easy" | The ROM-to-cart step is actually straightforward with an INLretro. The hard part is making the ROM. |
| "SNES is better" | More capable hardware, but worse tooling and community. NES is the better investment of your time. |

---

## Sources

- [NESdev Wiki - Tools](https://www.nesdev.org/wiki/Tools)
- [NESdev Wiki - Limitations](https://www.nesdev.org/wiki/Limitations)
- [nesdoug - NES Programming with cc65](https://nesdoug.com/)
- [Building NES Games with C (2025)](https://blog.shellnetsecurity.com/posts/2025/building-nes-games-with-c/)
- [PVSnesLib on GitHub](https://github.com/alekmaul/pvsneslib)
- [SNES-IDE on GitHub](https://github.com/BrunoRNS/SNES-IDE)
- [SNESdev Wiki - Tools](https://snes.nesdev.org/wiki/Tools)
- [GB Studio](https://www.gbstudio.dev/)
- [Creating for the Game Boy in 2025](https://handheldlegend.com/blogs/news/creating-for-the-game-boy-in-2025-no-coding-required)
- [PICO-8 Official](https://www.lexaloffle.com/pico-8.php)
- [Claude Code and PICO-8 (Lexaloffle BBS)](https://www.lexaloffle.com/bbs/?tid=153543)
- [Code-Vibing with AI: Building a Pico-8 Game](https://lgallardo.com/2025/11/09/pico8-ai-game-development/)
- [Using AI to Help with Assembly (Hackaday)](https://hackaday.com/2024/11/07/using-ai-to-help-with-assembly/)
- [Pyxel on GitHub](https://github.com/kitao/pyxel)
- [NES Graphical Specs](https://bitbeamcannon.com/nes-graphical-specs/)
- [Mouse Bite Labs - How to Make an NES Cartridge](https://mousebitelabs.com/2017/06/25/how-to-make-an-nes-reproduction-cartridge/)
- [INLretro / Infinite NES Lives](https://www.infiniteneslives.com/nesmaker.php)
- [NESmaker Official](https://www.thenew8bitheroes.com)
- [Craft Cart Culture: NES Homebrew in 2025 (Tedium)](https://tedium.co/2025/04/24/homebrew-nes-games-guide/)
- [Matt Hughson - Making an NES Game in 2020](https://www.matthughson.com/2020/12/07/from-completely-in-the-dark-to-complete-in-box-making-an-nes-game-in-2020/)
- [NESdev Forum - Timeline for Full Game Development](https://forums.nesdev.org/viewtopic.php?t=13065)
- [TIC-80 on Wikipedia](https://en.wikipedia.org/wiki/TIC-80)
- [Analogue Pocket Developer Docs](https://www.analogue.co/developer/docs/getting-started)
- [Analogue Pocket Homebrew ROMs on itch.io](https://itch.io/c/1961483/analogue-pocket-games-homebrew-roms-pocket)
- [SNESDEV 2025 Game Jam](https://itch.io/jam/snesdev-2025)
- [Mode 7 on Wikipedia](https://en.wikipedia.org/wiki/Mode_7)
