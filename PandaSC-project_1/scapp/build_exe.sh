#!/usr/bin/env bash
# Build a standalone PandaSC binary on macOS or Linux.
# Run this from the project root. Requires Python 3.11 or 3.12.
set -e

echo "Installing dependencies..."
python3 -m pip install -r requirements.txt

echo
echo "Building PandaSC (this can take a few minutes)..."
python3 -m PyInstaller build.spec --noconfirm

echo
echo "Done. Your executable is at dist/PandaSC"
echo "Copy that single file to give to a customer -- it needs nothing else installed."
