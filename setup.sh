#!/bin/bash
echo "Setting up runtime-draft on macOS/Linux..."

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Setup complete. To run the project:"
echo "  source .venv/bin/activate"
echo "  python scripts/batch_run.py"
