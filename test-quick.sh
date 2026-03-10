#!/bin/bash
# Quick test suite: lint + unit tests + built-in tests. Target: <30s.
set -e
cd "$(dirname "$0")"

SECONDS=0

echo "=== ruff ==="
python3 -m ruff check src/

echo "=== mypy ==="
python3 -m mypy src/depths_of_dread/

echo "=== pytest ==="
python3 -m pytest tests/ -q --tb=short

echo "=== built-in tests ==="
python3 src/depths_of_dread/game.py --test

echo ""
echo "=== ALL PASSED in ${SECONDS}s ==="
