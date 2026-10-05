#!/bin/zsh
# Launch the OpenJBL TUI from Terminal.app so macOS can grant it Bluetooth access.
cd "$(dirname "$0")"
source .venv/bin/activate
openjbl-tui
