# Changelog - V1.2

- added priority for local card sql database, scryfall used as backup

- added progress bar for mem searching

- removed redundant comments on source code

- fixed issue where the .txt would list items multiple times

- added csv exports for Moxfield

- added card set identifiers to the .txt 

- and more small changes

imported collection to moxfield:
<img width="1901" height="962" alt="image" src="https://github.com/user-attachments/assets/4f784272-e2fc-4521-8aa1-9137c1029aa4" />

Better text file
- before: 
<img width="1080" height="467" alt="image" src="https://github.com/user-attachments/assets/c0bb05cd-4996-4b2a-8c12-7b4bba20aabe" />

- after: 
<img width="1112" height="480" alt="image" src="https://github.com/user-attachments/assets/9609dd74-69c2-4c85-9ea1-8a9c35aa7d6e" />

Progress bars: 
<img width="388" height="96" alt="image" src="https://github.com/user-attachments/assets/ccc5c324-3f62-430b-bc74-366c4f9314d9" />

# MTG Arena Collection Exporter

This tool scans your game memory while MTG Arena is running to export your entire card collection.
It outputs two files:
- `mtga_collection.json`: Full data including card IDs and quantities.
- `mtga_collection.txt`: A readable list of your cards (Count + Name).

## How to use

### Option 1: Run the Executable (Simplest)
1. Navigate to **Releases**
2. Download and extract the **zip**
4. Navigate inside the extradted folder
5. Ensure **MTG Arena is running**.
6. Go to the **Decks** or **Collection** tab in-game, scroll for 30 secs through your collection (important so your collection loads into memory).
7. Run `MTGA_Exporter.exe`.
8. Follow the prompts to allow the tool do find and export your collection.

### Option 2: Run from Python Source
1. Download and extract zip
3. navigate inside folder
4. Install Python 3.x.
5. Run `install.bat` to install dependencies (`pymem`, `requests`).
6. Run `python mtg.py`.

## Troubleshooting
- If the tool cannot find your collection, ensure you have visited the Collection/Decks tab.
- Try providing different anchor cards if the first attempt fails (rarer anchor cards such as [O:legendary] work better, as they are more unique to your collection).
- Run as Administrator if you encounter permission errors.

## Filter & re-export by color (cross-platform GUI)

`mtga_export_gui.py` is a small Tkinter app that loads or generates an
`mtga_collection.json`, lets you tick which colors (W/U/B/R/G/Colorless) to
include, and re-exports to TXT, JSON, or Moxfield-style CSV. It runs on
**macOS, Linux, and Windows**.

Two ways to feed it your collection:

1. **Load collection (JSON)…** — point it at an `mtga_collection.json`
   produced by `mtg.py` on Windows. Best when you already have one or are
   running both tools on the same Windows box.
2. **Import from MTGA log…** — point it at MTGA's `Player.log`. The GUI parses
   the most recent inventory snapshot, fetches arena-id → name/set/colors
   from Scryfall (cached), and writes a fresh `mtga_collection.json` for you.
   This is the path to use on a Mac.

### Producing the log on macOS (no Windows machine needed)

MTG Arena has no native Mac client, but it runs through Wine-based wrappers.
Any of these work — install MTGA inside one and sign in once so the
collection syncs and the log file is created:

| Wrapper | Cost | Apple Silicon | Notes |
| --- | --- | --- | --- |
| [Whisky](https://getwhisky.app/) | Free | ✓ | Easiest free option. |
| [CrossOver](https://www.codeweavers.com/crossover) | Paid (free trial) | ✓ | Most polished commercial Wine. |
| Parallels / UTM + Windows | Paid / free | ✓ | Heavier, but works. |

Once MTGA is running, open the **Decks** or **Collection** tab and scroll for
~30 seconds so the inventory loads, then quit MTGA and click
**Import from MTGA log…** in the GUI. Common Player.log locations are
auto-detected:

- Whisky:  `~/Library/Containers/com.isaacmarovitz.Whisky/Bottles/<id>/drive_c/users/crossover/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log`
- CrossOver: `~/Library/Application Support/CrossOver/Bottles/<bottle>/drive_c/users/crossover/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log`
- Wineskin app: `/Applications/MTG Arena.app/Contents/Resources/drive_c/users/<user>/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log`
- Plain Wine: `~/.wine/drive_c/users/<user>/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log`

If the log lives somewhere else, the file picker lets you point at it
manually.

### Workflow summary

- **On a Windows PC:** run `mtg.py` (or `MTGA_Exporter.exe`) → produces
  `mtga_collection.json` → optionally use the GUI to filter by color.
- **On a Mac (or Linux):** install MTGA via Whisky/CrossOver, sign in, scroll
  the collection, quit, then in the GUI click *Import from MTGA log…* →
  filter and export.

### macOS / Linux setup

```bash
./install.sh
.venv/bin/python3 mtga_export_gui.py
```

`install.sh` creates a local `.venv/` (required on modern macOS/Linux because
the system Python refuses pip installs — PEP 668) and installs `requests` into
it. To launch later, either run the GUI through the venv's Python directly as
above, or activate the venv first:

```bash
source .venv/bin/activate
python3 mtga_export_gui.py
```

If `tkinter` is missing (common with Homebrew Python), install it first and
re-run `./install.sh`:
- macOS: `brew install python-tk`
- Debian/Ubuntu: `sudo apt install python3-tk python3-venv`

### Windows

After running `install.bat` you can also launch the GUI:

```bat
python mtga_export_gui.py
```

### Match modes

- **Any selected color** — include cards that have at least one ticked color
  (e.g. ticking just W picks up mono-white *and* multicolor cards containing
  white).
- **Only selected colors** — include cards whose colors are a subset of the
  ticked colors (good for building a guild/shard pool).
- **Exactly the ticked colors** — strict match, e.g. W+U returns only
  Azorius cards.

Color data is fetched once from Scryfall's bulk catalog and cached in
`color_cache.json`; arena-id → card resolution (used by the log importer) is
cached in `arena_id_cache.json`. Both make subsequent runs instant.

## Files
- `MTGA_Exporter.exe`: The standalone Windows application.
- `mtg.py`: Windows memory-scan exporter (source).
- `mtga_export_gui.py`: Cross-platform GUI for color filtering & re-export.
- `requirements.txt`: Python dependencies (`pymem` is installed on Windows only).
- `install.bat`: Setup script for Windows.
- `install.sh`: Setup script for macOS/Linux.
