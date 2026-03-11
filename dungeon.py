#!/usr/bin/env python3
"""Depths of Dread — launch wrapper.

Usage:
    python3 dungeon.py              # Interactive play
    python3 dungeon.py --bot        # Watch the AI bot play
    python3 dungeon.py --ascii      # Old School ASCII graphics
    python3 dungeon.py --help       # All options
"""
import runpy
import sys
import os

# Ensure src/ is on the path so the package resolves
src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if src not in sys.path:
    sys.path.insert(0, src)

runpy.run_module("depths_of_dread", run_name="__main__", alter_sys=True)
