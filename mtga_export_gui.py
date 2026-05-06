"""MTGA Collection Exporter GUI.

Cross-platform companion to mtg.py. Loads an mtga_collection.json export,
fetches color data from Scryfall (cached locally), and lets you filter the
collection by color before re-exporting to txt / json / Moxfield csv.

Runs on macOS, Linux, and Windows. Requires Python 3.8+ with tkinter and the
`requests` package.
"""

import csv
import glob
import json
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import requests

if getattr(sys, "frozen", False):
    SCRIPT_DIR = Path(sys.executable).parent
else:
    SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_COLLECTION = SCRIPT_DIR / "mtga_collection.json"
COLOR_CACHE = SCRIPT_DIR / "color_cache.json"
ARENA_ID_CACHE = SCRIPT_DIR / "arena_id_cache.json"

# Where MTGA's Player.log shows up across the various Mac wrappers (and
# Windows, for completeness). Globs are expanded relative to the user's home.
MTGA_LOG_PATTERNS = [
    # Whisky (free, Apple Silicon)
    "~/Library/Containers/com.isaacmarovitz.Whisky/Bottles/*/drive_c/users/crossover/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
    # CrossOver
    "~/Library/Application Support/CrossOver/Bottles/*/drive_c/users/crossover/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
    # Wineskin-style standalone .app
    "/Applications/MTG Arena.app/Contents/Resources/drive_c/users/*/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
    "/Applications/MTGA.app/Contents/Resources/drive_c/users/*/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
    # Plain Wine (~/.wine prefix)
    "~/.wine/drive_c/users/*/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
    # Linux Lutris/PlayOnLinux (best-effort)
    "~/Games/*/drive_c/users/*/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
    # Windows native (in case the GUI is run on Windows too)
    "~/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log",
]

COLORS = [
    ("W", "White"),
    ("U", "Blue"),
    ("B", "Black"),
    ("R", "Red"),
    ("G", "Green"),
    ("C", "Colorless"),
]


def card_key(card):
    return f"{(card.get('set') or '').upper()}|{card.get('cn') or ''}|{card.get('name') or ''}"


def card_colors_from_scryfall(entry):
    """Pull a color list from a Scryfall card record, handling DFCs."""
    colors = entry.get("colors")
    if colors is None and "card_faces" in entry:
        faces = entry.get("card_faces") or []
        seen = []
        for face in faces:
            for c in face.get("colors", []) or []:
                if c not in seen:
                    seen.append(c)
        colors = seen
    if not colors:
        return ["C"]
    return list(colors)


def autodetect_mtga_logs():
    """Return likely Player.log paths, newest first."""
    found = []
    for pat in MTGA_LOG_PATTERNS:
        for p in glob.glob(str(Path(pat).expanduser())):
            path = Path(p)
            if path.is_file():
                found.append(path)
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found


def _matching_brace(text, start):
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_inventory_from_log(log_path):
    """Find the most recent player-cards dict in an MTGA Player.log.

    Returns dict[arena_id:int -> qty:int] or None if nothing usable is found.
    The function tries the known event markers first; if none match it falls
    back to scanning every {...} block and picking the one that looks most
    like a card collection (lots of arena_id-shaped int keys).
    """
    text = Path(log_path).read_text(encoding="utf-8", errors="replace")

    markers = [
        "PlayerInventory.GetPlayerCardsV3",
        "InventoryInfo",
        '"PlayerCards"',
    ]

    # Try marker-driven extraction, looking from newest occurrence backwards.
    candidates = []
    for marker in markers:
        idx = text.rfind(marker)
        if idx == -1:
            continue
        json_start = text.find("{", idx)
        if json_start == -1:
            continue
        end = _matching_brace(text, json_start)
        if end == -1:
            continue
        try:
            payload = json.loads(text[json_start:end + 1])
        except json.JSONDecodeError:
            continue
        candidates.append(payload)

    def extract_inventory(payload):
        # Unwrap common wrappers
        if isinstance(payload, dict):
            if "payload" in payload and isinstance(payload["payload"], dict):
                payload = payload["payload"]
            if "PlayerCards" in payload and isinstance(payload["PlayerCards"], dict):
                payload = payload["PlayerCards"]
        if not isinstance(payload, dict):
            return None
        out = {}
        for k, v in payload.items():
            try:
                aid = int(k)
                qty = int(v)
            except (ValueError, TypeError):
                continue
            if 1000 <= aid < 10_000_000 and 1 <= qty <= 1000:
                out[aid] = qty
        return out if len(out) >= 20 else None

    for payload in candidates:
        inv = extract_inventory(payload)
        if inv:
            return inv

    # Last resort: scan every '{' block in the log and pick the largest one
    # that decodes to an arena_id->qty map.
    best = None
    pos = 0
    while True:
        pos = text.find("{", pos)
        if pos == -1:
            break
        end = _matching_brace(text, pos)
        if end == -1:
            break
        chunk = text[pos:end + 1]
        # Cheap pre-filter to avoid parsing every junk block
        if chunk.count(":") >= 50 and len(chunk) < 5_000_000:
            try:
                payload = json.loads(chunk)
            except json.JSONDecodeError:
                payload = None
            if payload is not None:
                inv = extract_inventory(payload)
                if inv and (best is None or len(inv) > len(best)):
                    best = inv
        pos = end + 1
    return best


class ExporterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MTGA Collection Exporter")
        self.root.geometry("780x460")

        self.collection = []
        self.collection_path = None
        self.color_cache = {}

        self._load_color_cache()
        self._build_ui()

        if DEFAULT_COLLECTION.exists():
            self._load_collection_file(DEFAULT_COLLECTION)

    def _load_color_cache(self):
        if COLOR_CACHE.exists():
            try:
                with COLOR_CACHE.open(encoding="utf-8") as f:
                    self.color_cache = json.load(f)
            except Exception:
                self.color_cache = {}

    def _save_color_cache(self):
        try:
            with COLOR_CACHE.open("w", encoding="utf-8") as f:
                json.dump(self.color_cache, f)
        except Exception:
            pass

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Button(top, text="Load collection (JSON)…", command=self._on_load).pack(side="left")
        ttk.Button(top, text="Import from MTGA log…", command=self._on_import_log).pack(side="left", padx=6)
        ttk.Button(top, text="Refresh color data", command=self._on_refresh_colors).pack(side="left", padx=6)
        self.file_label = ttk.Label(top, text="No collection loaded")
        self.file_label.pack(side="left", padx=10)

        clr = ttk.LabelFrame(self.root, text="Colors to include", padding=10)
        clr.pack(fill="x", padx=10, pady=5)
        self.color_vars = {}
        for code, name in COLORS:
            v = tk.BooleanVar(value=True)
            self.color_vars[code] = v
            ttk.Checkbutton(clr, text=f"{name} ({code})", variable=v, command=self._update_count).pack(side="left", padx=6)
        ttk.Button(clr, text="All", command=self._select_all, width=5).pack(side="left", padx=(12, 2))
        ttk.Button(clr, text="None", command=self._select_none, width=5).pack(side="left")

        mode = ttk.LabelFrame(self.root, text="Match mode", padding=10)
        mode.pack(fill="x", padx=10, pady=5)
        self.mode_var = tk.StringVar(value="any")
        for value, label in [
            ("any", "Any selected color  (W ticked → mono-white plus any multicolor with white)"),
            ("only", "Only selected colors  (cards never use a color you didn't tick)"),
            ("exact", "Exactly the ticked colors  (e.g. W+U → strictly Azorius)"),
        ]:
            ttk.Radiobutton(mode, text=label, value=value, variable=self.mode_var, command=self._update_count).pack(anchor="w")

        ex = ttk.LabelFrame(self.root, text="Export filtered list", padding=10)
        ex.pack(fill="x", padx=10, pady=5)
        ttk.Button(ex, text="TXT", command=lambda: self._export("txt")).pack(side="left", padx=4)
        ttk.Button(ex, text="JSON", command=lambda: self._export("json")).pack(side="left", padx=4)
        ttk.Button(ex, text="CSV (Moxfield)", command=lambda: self._export("csv")).pack(side="left", padx=4)

        self.status = ttk.Label(self.root, text="Ready. Load an mtga_collection.json to begin.", relief="sunken", anchor="w", padding=5)
        self.status.pack(fill="x", side="bottom")

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.config(text=text))

    def _on_load(self):
        path = filedialog.askopenfilename(
            title="Select mtga_collection.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            initialdir=str(SCRIPT_DIR),
            initialfile="mtga_collection.json",
        )
        if path:
            self._load_collection_file(Path(path))

    def _on_import_log(self):
        candidates = autodetect_mtga_logs()
        log_path = None
        if candidates:
            newest = candidates[0]
            mtime = newest.stat().st_mtime
            from datetime import datetime
            stamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            extra = ""
            if len(candidates) > 1:
                extra = f"\n\n({len(candidates) - 1} more older log(s) detected; pick manually if this is wrong.)"
            if messagebox.askyesno(
                "Use detected MTGA log?",
                f"Found:\n{newest}\n\nLast modified: {stamp}{extra}\n\nImport from this file?",
            ):
                log_path = newest

        if log_path is None:
            chosen = filedialog.askopenfilename(
                title="Select MTGA Player.log",
                filetypes=[("Log files", "Player.log *.log"), ("All files", "*.*")],
            )
            if not chosen:
                return
            log_path = Path(chosen)

        threading.Thread(target=self._import_log_thread, args=(log_path,), daemon=True).start()

    def _load_arena_id_cache(self):
        if ARENA_ID_CACHE.exists():
            try:
                with ARENA_ID_CACHE.open(encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_arena_id_cache(self, db):
        try:
            with ARENA_ID_CACHE.open("w", encoding="utf-8") as f:
                json.dump(db, f)
        except Exception:
            pass

    def _import_log_thread(self, log_path):
        self._set_status(f"Reading {log_path.name}…")
        try:
            inv = parse_inventory_from_log(log_path)
        except Exception as e:
            self._set_status(f"Failed to read log: {e}")
            self.root.after(0, lambda: messagebox.showerror("Import failed", str(e)))
            return

        if not inv:
            self._set_status("No inventory found in log.")
            self.root.after(0, lambda: messagebox.showwarning(
                "No inventory in log",
                "Could not find a player-cards snapshot in this log.\n\n"
                "Open MTG Arena, sign in, visit the Decks or Collection tab and "
                "scroll for ~30 seconds, then try importing again.",
            ))
            return

        self._set_status(f"Found {len(inv)} unique cards. Resolving names via Scryfall…")
        arena_db = self._load_arena_id_cache()
        if not arena_db or not all(str(aid) in arena_db for aid in inv):
            try:
                self._set_status("Downloading Scryfall bulk catalog (~80 MB, one-time)…")
                meta = requests.get("https://api.scryfall.com/bulk-data/default-cards", timeout=30).json()
                url = meta.get("download_uri")
                if not url:
                    raise RuntimeError("Scryfall response missing download_uri")
                payload = requests.get(url, timeout=300).json()
            except Exception as e:
                self._set_status(f"Scryfall download failed: {e}")
                return

            self._set_status("Indexing Scryfall data…")
            arena_db = {}
            for c in payload:
                aid = c.get("arena_id")
                if not aid:
                    continue
                arena_db[str(int(aid))] = {
                    "name": c.get("name", ""),
                    "set": (c.get("set") or "").upper(),
                    "cn": c.get("collector_number") or "",
                    "colors": card_colors_from_scryfall(c),
                }
            self._save_arena_id_cache(arena_db)

        collection = []
        for aid, qty in inv.items():
            info = arena_db.get(str(aid)) or {}
            entry = {
                "count": qty,
                "name": info.get("name") or f"Unknown Arena #{aid}",
                "set": info.get("set", ""),
                "cn": info.get("cn", ""),
            }
            collection.append(entry)
            colors = info.get("colors")
            if colors:
                self.color_cache[card_key(entry)] = colors
        self._save_color_cache()

        try:
            with DEFAULT_COLLECTION.open("w", encoding="utf-8") as f:
                json.dump(collection, f, indent=2)
        except Exception as e:
            self._set_status(f"Could not write {DEFAULT_COLLECTION.name}: {e}")
            return

        self.root.after(0, lambda: self._load_collection_file(DEFAULT_COLLECTION))
        self._set_status(f"Imported {len(collection)} cards from {log_path.name}.")

    def _load_collection_file(self, path):
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("Expected a JSON list of cards")
        except Exception as e:
            messagebox.showerror("Load failed", f"Could not read {path.name}:\n{e}")
            return

        self.collection = data
        self.collection_path = path
        self.file_label.config(text=f"{path.name}  ({len(data)} entries)")
        self._maybe_fetch_colors()
        self._update_count()

    def _maybe_fetch_colors(self):
        missing = [c for c in self.collection if card_key(c) not in self.color_cache]
        if not missing:
            return
        if not messagebox.askyesno(
            "Color data needed",
            f"{len(missing)} of {len(self.collection)} cards have no cached color info.\n\n"
            "Download the Scryfall bulk catalog now? (one-time ~80 MB download, cached locally)",
        ):
            return
        threading.Thread(target=self._download_colors, args=(self.collection,), daemon=True).start()

    def _on_refresh_colors(self):
        if not self.collection:
            messagebox.showwarning("No collection", "Load a collection first.")
            return
        if not messagebox.askyesno("Refresh", "Re-download color data from Scryfall?"):
            return
        self.color_cache = {}
        threading.Thread(target=self._download_colors, args=(self.collection,), daemon=True).start()

    def _download_colors(self, cards):
        try:
            self._set_status("Fetching Scryfall bulk-data catalog…")
            meta = requests.get("https://api.scryfall.com/bulk-data/default-cards", timeout=30).json()
            url = meta.get("download_uri")
            if not url:
                raise RuntimeError("Scryfall response missing download_uri")
            self._set_status("Downloading Scryfall card data (~80 MB)…")
            payload = requests.get(url, timeout=300).json()
        except Exception as e:
            self._set_status(f"Color download failed: {e}")
            return

        self._set_status("Indexing Scryfall data…")
        by_set_cn = {}
        by_name = {}
        for entry in payload:
            colors = card_colors_from_scryfall(entry)
            set_code = (entry.get("set") or "").upper()
            cn = entry.get("collector_number") or ""
            name = entry.get("name") or ""
            if set_code and cn:
                by_set_cn[(set_code, cn)] = colors
            if name and name not in by_name:
                by_name[name] = colors
                # Also index DFC front-face name to help with split cards
                if "//" in name:
                    by_name.setdefault(name.split("//")[0].strip(), colors)

        matched = 0
        for card in cards:
            set_code = (card.get("set") or "").upper()
            cn = card.get("cn") or ""
            name = card.get("name") or ""
            colors = by_set_cn.get((set_code, cn)) or by_name.get(name) or []
            self.color_cache[card_key(card)] = colors
            if colors:
                matched += 1

        self._save_color_cache()
        self.root.after(0, self._update_count)
        self._set_status(f"Color data ready ({matched}/{len(cards)} cards matched).")

    def _select_all(self):
        for v in self.color_vars.values():
            v.set(True)
        self._update_count()

    def _select_none(self):
        for v in self.color_vars.values():
            v.set(False)
        self._update_count()

    def _selected_colors(self):
        return {code for code, v in self.color_vars.items() if v.get()}

    def _filter(self):
        selected = self._selected_colors()
        mode = self.mode_var.get()
        out = []
        for card in self.collection:
            colors = set(self.color_cache.get(card_key(card)) or [])
            if not colors:
                colors = {"C"}
            if mode == "any":
                if colors & selected:
                    out.append(card)
            elif mode == "only":
                if selected and colors.issubset(selected):
                    out.append(card)
            elif mode == "exact":
                if colors == selected:
                    out.append(card)
        return out

    def _update_count(self):
        if not self.collection:
            return
        filt = self._filter()
        unique = len(filt)
        total = sum(c.get("count", 0) for c in filt)
        self._set_status(f"{unique} unique cards / {total} copies match the current filter.")

    def _export(self, fmt):
        if not self.collection:
            messagebox.showwarning("No collection", "Load a collection first.")
            return
        rows = self._filter()
        if not rows:
            messagebox.showwarning("Nothing to export", "No cards match the current filter.")
            return

        ext = {"txt": ".txt", "json": ".json", "csv": ".csv"}[fmt]
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            initialdir=str(SCRIPT_DIR),
            initialfile=f"mtga_filtered{ext}",
            filetypes=[(fmt.upper(), f"*{ext}"), ("All files", "*.*")],
        )
        if not path:
            return

        rows = sorted(rows, key=lambda c: (c.get("name", ""), c.get("set", "")))
        try:
            if fmt == "txt":
                with open(path, "w", encoding="utf-8") as f:
                    for c in rows:
                        s = f" ({c['set']})" if c.get("set") else ""
                        f.write(f"{c.get('count', 0)} {c.get('name', '')}{s}\n")
            elif fmt == "json":
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(rows, f, indent=2)
            elif fmt == "csv":
                with open(path, "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(["Count", "Name", "Edition", "Condition", "Language", "Foil", "Tag"])
                    for c in rows:
                        w.writerow([c.get("count", 0), c.get("name", ""), c.get("set", ""), "Near Mint", "English", "", ""])
            messagebox.showinfo("Exported", f"Wrote {len(rows)} cards to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))


def main():
    root = tk.Tk()
    ExporterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
