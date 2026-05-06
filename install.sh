#!/usr/bin/env bash
# Installs dependencies for the MTGA Collection Exporter GUI on macOS / Linux.
# Uses a local virtual environment (.venv) to satisfy PEP 668 on Homebrew /
# python.org / Debian-managed Python installs.
set -e

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 not found." >&2
    echo "Install Python 3 first:" >&2
    echo "  macOS (Homebrew): brew install python-tk" >&2
    echo "  Linux (Debian/Ubuntu): sudo apt install python3 python3-venv python3-tk" >&2
    exit 1
fi

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "Error: tkinter is not available for your Python install." >&2
    echo "  macOS (Homebrew): brew install python-tk" >&2
    echo "  Linux (Debian/Ubuntu): sudo apt install python3-tk" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment in $VENV ..."
    python3 -m venv "$VENV"
fi

echo "Installing Python dependencies (requests) into $VENV ..."
"$VENV/bin/python3" -m pip install --upgrade pip >/dev/null
"$VENV/bin/python3" -m pip install requests

echo
echo "Done. Launch the GUI with:"
echo "  $VENV/bin/python3 mtga_export_gui.py"
echo
echo "(or activate the venv first:  source $VENV/bin/activate  &&  python3 mtga_export_gui.py)"
echo
echo "Note: MTG Arena does not run natively on macOS/Linux, so the live memory"
echo "scanner (mtg.py) is Windows-only. Run the scanner on a Windows machine to"
echo "produce mtga_collection.json, then use this GUI on any platform to filter"
echo "by color and re-export."
