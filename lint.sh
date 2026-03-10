#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=== ruff ==="
python3 -m ruff check src/
echo "=== mypy ==="
python3 -m mypy src/depths_of_dread/
echo "=== All clean ==="
