import argparse
import csv
import itertools
import json
import os
import platform
import re
import readline
import shlex
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from gui_server import AlexandriaGUIServer, SharedRuntime
from system import (
    ALLOWED_COVERS,
    ALLOWED_ITEM_TYPES,
    ALLOWED_LANGUAGES,
    ALLOWED_LOCATIONS,
    ALLOWED_PRACTICE_STATUSES,
    Book,
    Library,
    StorageError,
)

ASCII_BANNER = r"""
                         ,--,                                                                                  
                      ,---.'|                                                                                  
                      |   | :                                                                                  
                      :   : |     ,--,     ,---,                                                               
                      |   ' :   ,--.'|   ,---.'|     __  ,-.            __  ,-.                                
                      ;   ; '   |  |,    |   | :   ,' ,'/ /|          ,' ,'/ /|                                
                      '   | |__ `--'_    :   : :   '  | |' | ,--.--.  '  | |' |   .--,                         
                      |   | :.'|,' ,'|   :     |,-.|  |   ,'/       \ |  |   ,' /_ ./|                         
                      '   :    ;'  | |   |   : '  |'  :  / .--.  .-. |'  :  /, ' , ' :                         
                      |   |  ./ |  | :   |   |  / :|  | '   \__\/: . .|  | '/___/ \: |                         
                      ;   : ;   '  : |__ '   : |: |;  : |   ," .--.; |;  : | .  \  ' |                         
                      |   ,/    |  | '.'||   | '/ :|  , ;  /  /  ,.  ||  , ;  \  ;   :                         
                      '---'     ;  :    ;|   :    | ---'  ;  :   .'   \---'    \  \  ;                         
                                |  ,   / /    \  /        |  ,     .-./         :  \  \                        
                                 ---`-'  `-'----'          `--`---'              \  ' ;                        
                                               ,----..                            `--`                         
                                              /   /   \                                                        
                                             /   .     :   .--.,                                               
                                            .   /   ;.  \,--.'  \                                              
                                           .   ;   /  ` ;|  | /\/                                              
                                           ;   |  ; \ ; |:  : :                                                
                                           |   :  | ; | ':  | |-,                                              
                                           .   |  ' ' ' :|  : :/|                                              
                                           '   ;  \; /  ||  |  .'                                              
                                            \   \  ',  / '  : '                                                
                                             ;   :    /  |  | |                                                
   ,---,        ,--,                          \   \ .'   |  : \                                                
  '  .' \     ,--.'|                           `---`     |  |,'            ,---,           ,--,                
 /  ;    '.   |  | :                                     `--'  ,---,     ,---.'|  __  ,-.,--.'|                
:  :       \  :  : '              ,--,  ,--,               ,-+-. /  |    |   | :,' ,'/ /||  |,                 
:  |   /\   \ |  ' |      ,---.   |'. \/ .`|   ,--.--.    ,--.'|'   |    |   | |'  | |' |`--'_      ,--.--.    
|  :  ' ;.   :'  | |     /     \  '  \/  / ;  /       \  |   |  ,"' |  ,--.__| ||  |   ,',' ,'|    /       \   
|  |  ;/  \   \  | :    /    /  |  \  \.' /  .--.  .-. | |   | /  | | /   ,'   |'  :  /  '  | |   .--.  .-. |  
'  :  | \  \ ,'  : |__ .    ' / |   \  ;  ;   \__\/: . . |   | |  | |.   '  /  ||  | '   |  | :    \__\/: . .  
|  |  '  '--' |  | '.'|'   ;   /|  / \  \  \  ," .--.; | |   | |  |/ '   ; |:  |;  : |   '  : |__  ," .--.; |  
|  :  :       ;  :    ;'   |  / |./__;   ;  \/  /  ,.  | |   | |--'  |   | '/  '|  , ;   |  | '.'|/  /  ,.  |  
|  | ,'       |  ,   / |   :    ||   :/\  \ ;  :   .'   \|   |/      |   :    :| ---'    ;  :    ;  :   .'   \ 
`--''          ---`-'   \   \  / `---'  `--`|  ,     .-./'---'        \   \  /           |  ,   /|  ,     .-./ 
                         `----'              `--`---'                  `----'             ---`-'  `--`---'     
                                                                                                               
"""

COMMAND_HELP = [
    ("add", "add a new item (book or sheet music)"),
    ("edit", "edit an item by reference"),
    ("details", "show detailed view for one item"),
    ("bulk edit", "bulk-update language/location/genre/tags/series on filtered items"),
    ("list", "list items with essential columns"),
    ("list full", "list all columns for every item"),
    ("list read", "list only read items"),
    ("list unread", "list only unread items"),
    ("list sheet", "list only sheet music items"),
    ("list genre <name>", "list items in a specific genre"),
    ("list language <name>", "list items in a specific language"),
    ("list instrument <name>", "list sheet music by instrumentation"),
    ("list tag <name>", "list items by tag"),
    ("sort by <field>", "sort by title | author | type | year | pages | language"),
    ("find title", "search items by title"),
    ("find author", "search items by author"),
    ("find composer", "search sheet music by composer"),
    ("authors", "list authors with counts and top genres/tags"),
    ("find notes", "search full-text notes"),
    ("search <query>", "advanced search (e.g. marx lang:german rating>=4 unread)"),
    ("metadata autofill [reference|all]", "fetch missing metadata from online sources with confirmation"),
    ("dedup scan", "scan for likely duplicate items"),
    ("dedup merge", "merge two duplicate items"),
    ("doctor [fix]", "validate data integrity and optionally auto-fix common issues"),
    ("check", "show one item by reference"),
    ("remove", "remove an item by reference"),
    ("mark read", "mark an item as read by reference"),
    ("mark unread", "mark an item as unread by reference"),
    ("notes", "add or update notes by reference"),
    ("tag add", "add tags to an item"),
    ("tag remove", "remove tags from an item"),
    ("tag set", "replace all tags on an item"),
    ("tag clear", "clear all tags from an item"),
    ("rate", "set rating 1-5 by reference"),
    ("progress", "set reading progress (pages) by reference"),
    ("language", "set language to German/English/French/Japanese by reference"),
    ("location", "set location to Pforta or Zuhause by reference"),
    ("practice", "set sheet music practice status by reference"),
    ("practice log", "log sheet-music practice minutes and bpm"),
    ("practice tempo", "set tempo target bpm for sheet music"),
    ("series set", "set series name/index for one item"),
    ("series next [name]", "show next unread item per series or for one series"),
    ("reading add", "add an item to reading list by reference"),
    ("reading list", "show reading list"),
    ("reading remove", "remove from reading list by reference"),
    ("reading plan [weeks]", "build a weekly reading plan from capacity and progress"),
    ("reading smart preview [count]", "preview smart recommendations based on interests"),
    ("reading smart generate [count]", "replace reading list with smart recommendations"),
    ("reading smart append [count]", "append smart recommendations to reading list"),
    ("interests set", "set smart recommendation interests"),
    ("interests show", "show current smart recommendation interests"),
    ("interests clear", "clear smart recommendation interests"),
    ("smart add", "create or update a smart list"),
    ("smart list", "list all smart lists"),
    ("smart run", "run a smart list"),
    ("smart remove", "remove a smart list"),
    ("goal show", "show monthly and yearly goals"),
    ("goal set monthly", "set monthly reading goal"),
    ("goal set yearly", "set yearly reading goal"),
    ("goal clear monthly", "clear monthly goal"),
    ("goal clear yearly", "clear yearly goal"),
    ("calendar add", "schedule reading/practice session"),
    ("calendar list [date]", "list scheduled sessions for one date"),
    ("calendar done", "mark one scheduled session as done"),
    ("calendar streak [reading|practice]", "show current completion streak"),
    ("inbox add", "quick-capture unstructured item idea"),
    ("inbox list", "list inbox items"),
    ("inbox process", "convert inbox item into full library entry"),
    ("inbox done", "mark inbox item as done"),
    ("inbox remove", "remove inbox item"),
    ("snapshot create [name]", "create named restore snapshot"),
    ("snapshot list", "list available snapshots"),
    ("snapshot restore", "restore state from snapshot"),
    ("profile show", "show active data profile"),
    ("profile list", "list available profiles"),
    ("profile new <name>", "create a new profile and switch to it"),
    ("profile use <name>", "switch active profile"),
    ("ai status", "show AI/Ollama integration status"),
    ("ai mode [safe|fast]", "set AI safety mode (preview+approve or fast apply)"),
    ("ai model <name>", "set default Ollama model"),
    ("ai recommend [count]", "show smart recommendations with explicit reasons"),
    ("ai enrich [reference|all]", "generate summary/description/tags with preview+approve"),
    ("stats", "show collection and reading stats"),
    ("sheet stats", "show sheet music specific statistics"),
    ("backup", "create backup file"),
    ("restore", "restore from backup/export JSON"),
    ("export", "export as JSON or CSV"),
    ("export obsidian <vault_path>", "export collection as Obsidian markdown vault notes"),
    ("obsidian", "show obsidian integration status and usage"),
    ("obsidian sync [vault_path]", "sync managed Alexandria notes into an Obsidian vault"),
    ("obsidian doctor [vault_path]", "validate Obsidian vault path, write access, and folders"),
    ("obsidian open [book-id|vault_path]", "open vault or jump directly to one managed note"),
    ("import", "import from JSON or CSV"),
    ("man <command>", "show bundled man page for a specific command"),
    ("compact [on|off|toggle]", "toggle compact table mode"),
    ("theme [name|list|preview|set|clear|color]", "set theme, preview, and personalize colors"),
    ("undo", "undo last change"),
    ("history", "show command history"),
    ("help [command]", "print help or command-specific help"),
    ("quit", "exit program"),
]
COMMANDS = sorted(
    {
        name.split(" <")[0].split(" [")[0].strip()
        for name, _ in COMMAND_HELP
    }
)
PROMPT_BASE = "alexandria"
CANCELED = object()
UNDO_LIMIT = 100
YES_VALUES = {"y", "yes"}
SNAPSHOT_DIR_NAME = "snapshots"
ALIASES = {
    "rm": "remove",
    "ls": "list",
    "q": "quit",
    "mr": "mark read",
    "mu": "mark unread",
}

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "black": "\033[30m",
    "cyan": "\033[36m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "white": "\033[37m",
    "bright_black": "\033[90m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    "bright_white": "\033[97m",
}
THEMES = {
    "classic": {"accent": "#35c2ff", "success": "#2ecc71", "warning": "#f1c40f", "error": "#ff5c57"},
    "ocean": {"accent": "#4aa3ff", "success": "#35d07f", "warning": "#ffd166", "error": "#ff6b8a"},
    "clean": {"accent": "#d8e2f1", "success": "#8de99a", "warning": "#ffd166", "error": "#ff8787"},
    "sunset": {"accent": "#ffb347", "success": "#7bd389", "warning": "#ffd166", "error": "#ff6b6b"},
    "mono": {"accent": "white", "success": "bright_white", "warning": "bright_black", "error": "bright_white"},
    "forest": {"accent": "#8bcf6a", "success": "#45b97c", "warning": "#e7c86e", "error": "#ff7a7a"},
}
THEME_ROLES = ("accent", "success", "warning", "error")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
COLOR_CHOICES = tuple(
    sorted(
        key for key in ANSI.keys() if key not in {"reset", "bold", "dim"}
    )
)
ACTIVE_THEME = "classic"
THEME_OVERRIDES: dict[str, str] = {}
USE_COLOR = sys.stdout.isatty()
UI_COMPACT_MODE = True
SHOW_MOTION = sys.stdout.isatty()
BOOK_HEADERS_FULL = [
    "ID",
    "Type",
    "Title",
    "Author",
    "ISBN",
    "Year",
    "Genre",
    "Language",
    "Cover",
    "Instrument",
    "Pages",
    "Progress",
    "Rating",
    "Read",
    "Location",
    "Tags",
    "Notes",
]
BOOK_HEADERS_COMPACT = ["ID", "Type", "Title", "Author", "Progress", "Read", "Location"]
NUMERIC_HEADERS = {"Year", "Pages", "Rating"}
TABLE_MAX_WIDTHS_FULL = {
    "ID": 6,
    "Type": 11,
    "Title": 24,
    "Author": 20,
    "ISBN": 16,
    "Year": 6,
    "Genre": 22,
    "Language": 10,
    "Cover": 10,
    "Instrument": 16,
    "Pages": 7,
    "Progress": 13,
    "Rating": 8,
    "Read": 6,
    "Location": 10,
    "Tags": 28,
    "Notes": 22,
}
TABLE_MAX_WIDTHS_COMPACT = {
    "ID": 6,
    "Type": 11,
    "Title": 28,
    "Author": 24,
    "Progress": 14,
    "Read": 6,
    "Location": 10,
}
TABLE_MIN_WIDTHS = {
    "ID": 4,
    "Type": 5,
    "Title": 10,
    "Author": 10,
    "ISBN": 8,
    "Year": 4,
    "Genre": 10,
    "Language": 8,
    "Cover": 8,
    "Instrument": 8,
    "Pages": 5,
    "Progress": 8,
    "Rating": 6,
    "Read": 4,
    "Location": 8,
    "Tags": 10,
    "Notes": 10,
}
TABLE_SHRINK_PRIORITY = ["Notes", "Tags", "Genre", "Instrument", "Title", "Author", "ISBN", "Progress", "Location"]
COMMAND_INDEX = {command: description for command, description in COMMAND_HELP}
COMMAND_EXAMPLES = {
    command: f"alexandria> {command}"
    for command in COMMAND_INDEX
}
COMMAND_EXAMPLES.update(
    {
        "list genre <name>": "alexandria> list genre fantasy",
        "list language <name>": "alexandria> list language german",
        "list instrument <name>": "alexandria> list instrument piano",
        "list tag <name>": "alexandria> list tag classics",
        "find composer": "alexandria> find composer bach",
        "search <query>": "alexandria> search marx lang:german rating>=4 unread",
        "metadata autofill [reference|all]": "alexandria> metadata autofill all",
        "dedup scan": "alexandria> dedup scan",
        "dedup merge": "alexandria> dedup merge",
        "doctor [fix]": "alexandria> doctor fix",
        "sort by <field>": "alexandria> sort by language",
        "authors": "alexandria> authors",
        "bulk edit": "alexandria> bulk edit",
        "practice": "alexandria> practice",
        "practice log": "alexandria> practice log",
        "practice tempo": "alexandria> practice tempo",
        "series set": "alexandria> series set",
        "series next [name]": "alexandria> series next dune",
        "sheet stats": "alexandria> sheet stats",
        "reading plan [weeks]": "alexandria> reading plan 4",
        "calendar add": "alexandria> calendar add",
        "calendar list [date]": "alexandria> calendar list 2026-04-01",
        "calendar done": "alexandria> calendar done",
        "calendar streak [reading|practice]": "alexandria> calendar streak reading",
        "inbox add": "alexandria> inbox add",
        "inbox list": "alexandria> inbox list",
        "inbox process": "alexandria> inbox process",
        "snapshot create [name]": "alexandria> snapshot create before-import",
        "snapshot list": "alexandria> snapshot list",
        "snapshot restore": "alexandria> snapshot restore",
        "profile show": "alexandria> profile show",
        "profile list": "alexandria> profile list",
        "profile new <name>": "alexandria> profile new school",
        "profile use <name>": "alexandria> profile use school",
        "ai status": "alexandria> ai status",
        "ai mode [safe|fast]": "alexandria> ai mode safe",
        "ai model <name>": "alexandria> ai model llama3.2",
        "ai recommend [count]": "alexandria> ai recommend 10",
        "ai enrich [reference|all]": "alexandria> ai enrich b0001",
        "export obsidian <vault_path>": "alexandria> export obsidian ~/Documents/MyVault",
        "obsidian sync [vault_path]": "alexandria> obsidian sync",
        "obsidian doctor [vault_path]": "alexandria> obsidian doctor",
        "obsidian open [book-id|vault_path]": "alexandria> obsidian open b0001",
        "help [command]": "alexandria> help progress",
        "man <command>": "alexandria> man reading add",
        "reading smart preview [count]": "alexandria> reading smart preview 10",
        "reading smart generate [count]": "alexandria> reading smart generate 8",
        "reading smart append [count]": "alexandria> reading smart append 5",
        "interests set": "alexandria> interests set",
        "interests show": "alexandria> interests show",
        "interests clear": "alexandria> interests clear",
        "compact [on|off|toggle]": "alexandria> compact toggle",
        "theme [name|list|preview|set|clear|color]": "alexandria> theme set accent #35c2ff",
    }
)


def parse_cli_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--theme", choices=sorted(THEMES.keys()))
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--no-motion", action="store_true")
    parser.add_argument("--profile", type=str, default="")
    parser.add_argument("--no-gui-server", action="store_true")
    parser.add_argument("--gui-port", type=int, default=8765)
    parser.add_argument("--gui-host", type=str, default="127.0.0.1")
    parser.add_argument("--open-gui", action="store_true")
    parser.add_argument("--help", action="store_true")
    args, _unknown = parser.parse_known_args()
    return args


def resolve_command_alias(raw_cmd: str) -> str:
    trimmed = raw_cmd.strip()
    if not trimmed:
        return trimmed
    lower = trimmed.lower()
    for alias, canonical in ALIASES.items():
        if lower == alias:
            return canonical
        if lower.startswith(alias + " "):
            return canonical + trimmed[len(alias):]
    return trimmed


def theme_color(role: str) -> str:
    override = THEME_OVERRIDES.get(role)
    if override and _style_code(override):
        return override
    candidate = THEMES.get(ACTIVE_THEME, THEMES["classic"]).get(role, "#35c2ff")
    if _style_code(candidate):
        return candidate
    return "cyan"


def _style_code(style_name: str) -> str:
    key = str(style_name).strip()
    if not key:
        return ""
    if key in ANSI:
        return ANSI[key]
    if HEX_COLOR_RE.fullmatch(key):
        red = int(key[1:3], 16)
        green = int(key[3:5], 16)
        blue = int(key[5:7], 16)
        return f"\033[38;2;{red};{green};{blue}m"
    return ""


def _is_valid_color_value(value: str) -> bool:
    key = str(value).strip()
    return key in COLOR_CHOICES or bool(HEX_COLOR_RE.fullmatch(key))


def style(text: str, *styles: str) -> str:
    if not USE_COLOR or not styles:
        return text
    style_codes = "".join(_style_code(name) for name in styles)
    # Reset first so shell-inherited colors cannot leak into app output.
    prefix = ANSI["reset"] + style_codes
    return f"{prefix}{text}{ANSI['reset']}"


def themed(text: str, role: str, *, bold: bool = False, dim: bool = False) -> str:
    styles = [theme_color(role)]
    if bold:
        styles.append("bold")
    if dim:
        styles.append("dim")
    return style(text, *styles)


def print_status(message: str, level: str = "info") -> None:
    labels = {
        "info": "[INFO]",
        "ok": "[OK]",
        "warn": "[WARN]",
        "error": "[ERROR]",
    }
    role_map = {
        "info": "accent",
        "ok": "success",
        "warn": "warning",
        "error": "error",
    }
    label = labels.get(level, "[INFO]")
    role = role_map.get(level, "accent")
    print(f"{themed(label, role, bold=(level != 'info'))} {message}")


def print_result(action: str, result: str, details: str = "") -> None:
    lowered = result.casefold()
    if lowered in {"saved", "updated", "done"}:
        level = "ok"
    elif lowered in {"no change", "canceled"}:
        level = "warn" if lowered == "no change" else "info"
    elif lowered in {"failed"}:
        level = "error"
    else:
        level = "info"
    suffix = f" {details}" if details else ""
    print_status(f"{action}: {result}.{suffix}".strip(), level)


def format_hint(label: str, value: str) -> str:
    return f"{label}. Use: {value}"


def _sanitize_profile_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(name or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "default"


def _profiles_root() -> Path:
    return Path.home() / ".library_of_alexandria" / "profiles"


def _profile_data_file(profile_name: str) -> Path:
    sanitized = _sanitize_profile_name(profile_name)
    return _profiles_root() / f"{sanitized}.json"


def resolve_data_file(profile_name: str | None = None) -> Path:
    configured = os.getenv("LIBRARY_DATA_FILE", "").strip()
    if configured and not profile_name:
        return Path(configured).expanduser()

    if profile_name:
        return _profile_data_file(profile_name)

    candidates = [
        Path.home() / ".library_of_alexandria" / "library_data.json",
        Path("/tmp") / "library_of_alexandria" / "library_data.json",
        Path(__file__).resolve().with_name("library_data.json"),
    ]
    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            probe = candidate.parent / ".loa_write_test"
            with probe.open("w", encoding="utf-8") as handle:
                handle.write("ok")
            probe.unlink(missing_ok=True)
            return candidate
        except OSError:
            continue

    return Path.cwd() / "library_data.json"


def profile_name_from_data_file(data_file: Path) -> str:
    try:
        rel = data_file.resolve().relative_to(_profiles_root().resolve())
    except ValueError:
        return "default"
    if rel.parts:
        return Path(rel.parts[0]).stem
    return "default"


def build_prompt(library: Library, profile_name: str | None = None) -> str:
    total = len(library.books)
    word = "book" if total == 1 else "books"
    profile = (profile_name or "").strip()
    if profile and profile != "default":
        return f"{PROMPT_BASE}[{profile}] ({total} {word})> "
    return f"{PROMPT_BASE} ({total} {word})> "


def confirm_action(message: str) -> bool:
    reply = input(f"{message} [y/N]: ").strip().lower()
    return reply in YES_VALUES


def prompt_apply_skip_cancel(message: str) -> str:
    reply = input(f"{message} [y/N/c]: ").strip().lower()
    if reply in {"c", "cancel"}:
        return "cancel"
    if reply in YES_VALUES:
        return "apply"
    return "skip"


@contextmanager
def spinner(message: str):
    if not SHOW_MOTION:
        yield
        return
    done = threading.Event()
    frames = itertools.cycle(("|", "/", "-", "\\"))

    def animate():
        while not done.is_set():
            frame = next(frames)
            print(f"\r{themed(message, 'accent')} {frame}", end="", flush=True)
            time.sleep(0.08)

    thread = threading.Thread(target=animate, daemon=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join(timeout=0.2)
        print("\r" + (" " * (len(message) + 4)) + "\r", end="", flush=True)


def update_progress(prefix: str, current: int, total: int, last_percent: int) -> int:
    if not SHOW_MOTION or total <= 0:
        return last_percent
    percent = int((current / total) * 100)
    if percent >= last_percent + 5 or percent == 100:
        print(f"\r{themed(prefix, 'accent')} {percent:>3}% ({current}/{total})", end="", flush=True)
        return percent
    return last_percent


def end_progress() -> None:
    if SHOW_MOTION:
        print()


def frame_ascii_art(text: str) -> str:
    lines = text.strip("\n").splitlines()
    if not lines:
        return text
    width = max(len(line) for line in lines)
    top = "┌" + ("─" * (width + 2)) + "┐"
    bottom = "└" + ("─" * (width + 2)) + "┘"
    body = [f"│ {line.ljust(width)} │" for line in lines]
    return "\n".join([top, *body, bottom])


def print_banner(data_file: Path):
    if USE_COLOR:
        print(ANSI["reset"], end="")
    print(themed(frame_ascii_art(ASCII_BANNER), "accent"))
    print(style("Type 'help' to see commands. Type 'quit' to exit.", "dim"))
    print(style(f"Data file: {data_file}", "dim"))
    print()


def summarize_theme_overrides() -> str:
    if not THEME_OVERRIDES:
        return "-"
    entries = [f"{role}={color}" for role, color in THEME_OVERRIDES.items()]
    return ", ".join(entries)


def print_theme_palette(title: str, palette: dict[str, str]) -> None:
    print(style(title, "bold"))
    for role in THEME_ROLES:
        color = palette.get(role, "cyan")
        swatch = style("■■■", color)
        print(f"  {role.ljust(7)} {swatch}  {style(color, color)}")
    print()


def print_theme_preview() -> None:
    print(style("Theme Preview", "bold"))
    print(f"  Theme:      {ACTIVE_THEME}")
    print(f"  Color mode: {'ON' if USE_COLOR else 'OFF'}")
    print(f"  Overrides:  {summarize_theme_overrides()}")
    print()
    print_status("This is an info message.", "info")
    print_status("This is a success message.", "ok")
    print_status("This is a warning message.", "warn")
    print_status("This is an error message.", "error")
    print()


def normalize_help_topic(topic: str) -> str | None:
    value = topic.strip().lower()
    if not value:
        return None
    if value in ALIASES:
        return ALIASES[value]
    if value in COMMAND_INDEX:
        return value
    for command in COMMAND_INDEX:
        command_stub = command.split(" <")[0].split(" [")[0].strip().lower()
        if value == command_stub:
            return command
    if value.startswith("help "):
        nested = value[5:].strip()
        if nested in COMMAND_INDEX:
            return nested
    return None


def _command_base(command: str) -> str:
    tokens = []
    for token in command.lower().split():
        if token.startswith("<") or token.startswith("["):
            continue
        tokens.append(token)
    return " ".join(tokens).strip()


def resolve_man_page(topic: str) -> Path | None:
    man_dir = Path(__file__).resolve().with_name("man")
    value = topic.strip().lower()
    if not value:
        return None

    normalized = " ".join(resolve_command_alias(value).strip().lower().split())
    normalized = normalized.removesuffix(".1")
    if normalized.startswith("loa-"):
        normalized = normalized[4:].replace("-", " ")

    man_map: dict[str, Path] = {}
    for command, _description in COMMAND_HELP:
        base = _command_base(command)
        slug = base.replace(" ", "-")
        man_map[base] = man_dir / f"loa-{slug}.1"

    page = man_map.get(normalized)
    if page and page.exists():
        return page
    for base, candidate in man_map.items():
        if normalized.startswith(base + " ") and candidate.exists():
            return candidate
    return None


def show_man_page(topic: str) -> None:
    if not topic.strip():
        print_status("Usage: man <command>. Example: man add", "warn")
        return

    page = resolve_man_page(topic)
    if page is None:
        print_status("Man page not found for that exact command. Try: help", "warn")
        return

    man_cmd = shutil.which("man")
    if man_cmd:
        try:
            subprocess.run([man_cmd, str(page)], check=False)
            return
        except OSError as exc:
            print_status(f"Could not open man command ({exc}). Showing plain text fallback.", "warn")

    try:
        print(style(page.read_text(encoding="utf-8"), "dim"))
    except OSError as exc:
        print_status(f"Could not read man page: {exc}", "error")


def print_help(topic: str | None = None):
    if topic:
        resolved = normalize_help_topic(topic)
        if not resolved:
            print_status("Unknown help topic. Use: help <command>", "warn")
            return
        description = COMMAND_INDEX[resolved]
        example = COMMAND_EXAMPLES.get(resolved, f"alexandria> {resolved}")
        print(themed("Command Help", "accent", bold=True))
        print(f"  Command: {resolved}")
        print(f"  What:    {description}")
        print(f"  Example: {example}")
        print()
        return

    print(style("Commands", "bold"))
    width = max(len(command) for command, _ in COMMAND_HELP)
    for command, description in COMMAND_HELP:
        print(f"  {command.ljust(width)}  {description}")
    print()
    print(style("Aliases", "bold"))
    for alias, command in sorted(ALIASES.items()):
        print(f"  {alias.ljust(4)} -> {command}")
    print(style("Tip: help <command> for contextual help.", "dim"))
    print()


def setup_autocomplete():
    completion_pool = sorted(
        set(
            COMMANDS
            + list(ALIASES.keys())
            + [f"help {command}" for command in COMMANDS]
            + [f"man {command}" for command in COMMANDS]
            + [
                "compact on",
                "compact off",
                "compact toggle",
                "compact status",
                "list sheet",
                "list instrument piano",
                "find composer bach",
                "sheet stats",
                "practice",
                "export obsidian ~/Documents/MyVault",
                "obsidian sync",
                "obsidian sync ~/Documents/MyVault",
                "obsidian doctor",
                "obsidian doctor ~/Documents/MyVault",
                "obsidian open",
                "obsidian open b0001",
                "obsidian open ~/Documents/MyVault",
                "theme list",
                "theme preview",
                "theme color on",
                "theme color off",
                "theme color toggle",
                "theme color status",
                "theme set accent bright_cyan",
                "theme set accent #35c2ff",
                "theme set success bright_green",
                "theme set warning bright_yellow",
                "theme set error bright_red",
                "theme set error #ff5c57",
                "theme clear",
            ]
        )
    )

    def completer(text, state):
        buffer = readline.get_line_buffer()
        prefix = buffer if buffer else text
        options = [item for item in completion_pool if item.startswith(prefix)]
        return options[state] if state < len(options) else None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind('"\\C-r": reverse-search-history')


def prompt_or_cancel(prompt):
    text = input(prompt).strip()
    if text.lower() == "cancel":
        return None
    return text


def get_optional_int(prompt):
    while True:
        text = input(prompt).strip()
        if text == "":
            return None
        if text.lower() == "cancel":
            return CANCELED
        try:
            return int(text)
        except ValueError:
            print_status(format_hint("Invalid number", "blank, cancel, or an integer"), "warn")


def parse_location(value: str) -> str | None:
    text = value.strip().lower()
    if text == "pforta":
        return "Pforta"
    if text == "zuhause":
        return "Zuhause"
    return None


def parse_cover(value: str) -> str | None:
    text = value.strip().lower().replace("-", "").replace(" ", "")
    if text in {"hard", "hardcover", "hc"}:
        return "Hardcover"
    if text in {"soft", "softcover", "sc", "paperback", "pb"}:
        return "Softcover"
    return None


def parse_language(value: str) -> str | None:
    text = value.strip().lower()
    if text in {"german", "de", "deutsch"}:
        return "German"
    if text in {"english", "en", "englisch"}:
        return "English"
    if text in {"french", "fr", "francais", "français"}:
        return "French"
    if text in {"japanese", "jp", "ja", "japanisch"}:
        return "Japanese"
    return None


def parse_item_type(value: str) -> str | None:
    text = value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if text in {"book", "b"}:
        return "Book"
    if text in {"sheet", "sheetmusic", "music", "score", "s"}:
        return "SheetMusic"
    return None


def parse_practice_status(value: str) -> str | None:
    text = value.strip().lower()
    if text in {"unstarted", "new"}:
        return "Unstarted"
    if text in {"learning", "learn"}:
        return "Learning"
    if text in {"rehearsing", "rehearse"}:
        return "Rehearsing"
    if text in {"performance-ready", "performanceready", "ready"}:
        return "Performance-ready"
    if text in {"mastered", "done"}:
        return "Mastered"
    return None


def parse_tags(value: str) -> list[str]:
    seen = set()
    tags = []
    for part in value.split(","):
        tag = " ".join(part.strip().split()).lower()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def parse_keywords(value: str) -> list[str]:
    seen = set()
    items = []
    for part in value.split(","):
        token = " ".join(part.strip().split()).casefold()
        if token and token not in seen:
            seen.add(token)
            items.append(token)
    return items


def parse_optional_location(value: str) -> str | None:
    text = value.strip()
    if not text or text.lower() in {"any", "*"}:
        return None
    return parse_location(text)


def parse_positive_int_arg(value: str, default: int) -> int:
    text = value.strip()
    if not text:
        return default
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError("Count must be a positive integer.") from exc
    if number <= 0:
        raise ValueError("Count must be a positive integer.")
    return number


def parse_read_filter(value: str) -> bool | None:
    text = value.strip().lower()
    if text in {"", "any", "*"}:
        return None
    if text in {"read", "true", "yes", "y", "1"}:
        return True
    if text in {"unread", "false", "no", "n", "0"}:
        return False
    raise ValueError("Read filter must be read, unread, or any.")


def smart_filters_to_label(filters: dict[str, object]) -> str:
    parts = []
    read_value = filters.get("read")
    if read_value is True:
        parts.append("read")
    elif read_value is False:
        parts.append("unread")
    if filters.get("location"):
        parts.append(f"location={filters['location']}")
    if filters.get("genre"):
        parts.append(f"genre={filters['genre']}")
    if filters.get("min_rating") is not None:
        parts.append(f"rating>={filters['min_rating']}")
    tags = filters.get("tags") or []
    if tags:
        parts.append("tags=" + ",".join(tags))
    return " | ".join(parts) if parts else "no filters"


def push_undo(undo_stack, snapshot):
    undo_stack.append(snapshot)
    if len(undo_stack) > UNDO_LIMIT:
        undo_stack.pop(0)


def truncate(value, max_len=42):
    text = str(value)
    if max_len <= 1:
        return "…"
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _table_width(col_widths: list[int]) -> int:
    # left border + widths + padding/spacers + right border
    return sum(col_widths) + (3 * len(col_widths)) + 1


def _shrink_col_widths_for_terminal(col_widths: list[int], headers: list[str]) -> list[int]:
    term_width = shutil.get_terminal_size((120, 20)).columns
    widths = col_widths[:]
    overflow = _table_width(widths) - term_width
    if overflow <= 0:
        return widths

    priority_indices = [
        index
        for name in TABLE_SHRINK_PRIORITY
        for index, header in enumerate(headers)
        if header == name
    ]
    # Fallback if none matched
    if not priority_indices:
        priority_indices = list(range(len(headers)))

    while overflow > 0:
        changed = False
        for index in priority_indices:
            header = headers[index]
            min_width = TABLE_MIN_WIDTHS.get(header, len(header))
            if widths[index] > min_width:
                widths[index] -= 1
                overflow -= 1
                changed = True
                if overflow <= 0:
                    break
        if not changed:
            break

    return widths


def print_table(
    rows,
    headers,
    *,
    right_align: set[int] | None = None,
    max_widths: dict[str, int] | None = None,
):
    if not rows:
        return

    right_align = right_align or set()
    normalized = [[str(cell) for cell in row] for row in rows]
    col_widths = [
        max(len(str(header)), *(len(str(row[i])) for row in normalized))
        for i, header in enumerate(headers)
    ]
    if max_widths:
        col_widths = [min(width, max_widths.get(headers[i], width)) for i, width in enumerate(col_widths)]

    col_widths = _shrink_col_widths_for_terminal(col_widths, headers)
    normalized = [[truncate(cell, col_widths[i]) for i, cell in enumerate(row)] for row in normalized]

    def border(left, middle, right):
        return left + middle.join("─" * (width + 2) for width in col_widths) + right

    print(themed(border("┌", "┬", "┐"), "accent", dim=True))
    header_line = (
        "│ "
        + " │ ".join(
            str(header).rjust(col_widths[i]) if i in right_align else str(header).ljust(col_widths[i])
            for i, header in enumerate(headers)
        )
        + " │"
    )
    print(themed(header_line, "accent", bold=True))
    print(themed(border("├", "┼", "┤"), "accent", dim=True))
    for row in normalized:
        row_line = (
            "│ "
            + " │ ".join(
                str(row[i]).rjust(col_widths[i]) if i in right_align else str(row[i]).ljust(col_widths[i])
                for i in range(len(headers))
            )
            + " │"
        )
        print(style(row_line, "reset"))
    print(themed(border("└", "┴", "┘"), "accent", dim=True))


def book_row(book: Book, compact: bool = False) -> list[str]:
    tags_text = "-"
    if book.tags:
        head = book.tags[:3]
        rest = len(book.tags) - len(head)
        tags_text = ", ".join(head)
        if rest > 0:
            tags_text = f"{tags_text}, +{rest}"

    genre_text = book.genre or "-"
    if "," in genre_text:
        parts = [part.strip() for part in genre_text.split(",") if part.strip()]
        if len(parts) > 2:
            genre_text = f"{', '.join(parts[:2])}, +{len(parts) - 2}"
        elif parts:
            genre_text = ", ".join(parts)

    notes_text = " ".join((book.notes or "-").split())
    item_type_text = "Sheet" if book.item_type == "SheetMusic" else "Book"
    if compact:
        return [
            book.book_id or "-",
            item_type_text,
            book.title,
            book.author,
            book.progress_label(),
            "yes" if book.read else "no",
            book.location,
        ]
    return [
        book.book_id or "-",
        item_type_text,
        book.title,
        book.author,
        book.isbn or "-",
        str(book.year) if book.year is not None else "-",
        genre_text,
        book.language,
        book.cover,
        book.instrumentation or "-",
        str(book.pages) if book.pages is not None else "-",
        book.progress_label(),
        str(book.rating) if book.rating is not None else "-",
        "yes" if book.read else "no",
        book.location,
        tags_text,
        notes_text,
    ]


def print_books(books, title, *, compact: bool | None = None):
    if not books:
        print_status("No items to show. Try: add", "info")
        return
    print(themed(title, "accent", bold=True))
    compact = UI_COMPACT_MODE if compact is None else compact
    headers = BOOK_HEADERS_COMPACT if compact else BOOK_HEADERS_FULL
    rows = [book_row(book, compact=compact) for book in books]
    right_align = {i for i, header in enumerate(headers) if header in NUMERIC_HEADERS}
    max_widths = TABLE_MAX_WIDTHS_COMPACT if compact else TABLE_MAX_WIDTHS_FULL
    print_table(rows, headers, right_align=right_align, max_widths=max_widths)
    print()


def print_goals(library):
    stats = library.stats()
    monthly_goal = stats["monthly_goal"]
    yearly_goal = stats["yearly_goal"]
    print(style("Reading Goals", "bold"))
    if monthly_goal:
        monthly_percent = int(round((stats["this_month"] / monthly_goal) * 100))
        print(f"  Monthly: {stats['this_month']}/{monthly_goal} ({monthly_percent}%)")
    else:
        print("  Monthly: not set")
    if yearly_goal:
        yearly_percent = int(round((stats["this_year"] / yearly_goal) * 100))
        print(f"  Yearly:  {stats['this_year']}/{yearly_goal} ({yearly_percent}%)")
    else:
        print("  Yearly:  not set")
    print()


def print_stats(library):
    stats = library.stats()
    print(style("Library Stats", "bold"))
    print(f"  Total items:      {stats['total']}")
    print(f"  Books:            {stats.get('books_only', 0)}")
    print(f"  Sheet music:      {stats.get('sheet_music', 0)}")
    print(f"  Read / unread:    {stats['read']} / {stats['unread']}")
    print(f"  Reading list:     {stats['reading_list']}")
    print(f"  Smart lists:      {stats['smart_lists']}")
    print(f"  Smart interests:  {'active' if stats.get('recommendation_profile_active') else 'not set'}")
    print(f"  Read this month:  {stats['this_month']}")
    print(f"  Read this year:   {stats['this_year']}")
    print(f"  At Pforta:        {stats['location_counts'].get('Pforta', 0)}")
    print(f"  At Zuhause:       {stats['location_counts'].get('Zuhause', 0)}")
    if stats["average_rating"] is not None:
        print(f"  Average rating:   {stats['average_rating']}/5")
    else:
        print("  Average rating:   -")
    if stats["top_genres"]:
        joined = ", ".join(f"{name} ({count})" for name, count in stats["top_genres"])
        print(f"  Top genres:       {joined}")
    else:
        print("  Top genres:       -")
    if stats["top_tags"]:
        joined_tags = ", ".join(f"{name} ({count})" for name, count in stats["top_tags"])
        print(f"  Top tags:         {joined_tags}")
    else:
        print("  Top tags:         -")
    print()
    print_goals(library)


def print_author_overview(library: Library) -> None:
    summary = library.author_overview(top_genres=3, top_tags=3)
    if not summary:
        print_status("No authors to show. Try: add", "info")
        return

    rows = []
    for item in summary:
        genres_text = ", ".join(item.get("main_genres", [])) or "-"
        tags_text = ", ".join(item.get("main_tags", [])) or "-"
        rows.append([item.get("author", "-"), str(item.get("books", 0)), genres_text, tags_text])

    print(style("Author Overview", "bold"))
    print_table(
        rows,
        ["Author", "Books", "Main Genres", "Main Tags"],
        right_align={1},
        max_widths={"Author": 24, "Books": 5, "Main Genres": 36, "Main Tags": 36},
    )
    print()


def print_sheet_stats(library: Library) -> None:
    stats = library.sheet_stats()
    if stats.get("total", 0) <= 0:
        print_status("No sheet music entries yet. Try: add", "info")
        return

    print(style("Sheet Music Stats", "bold"))
    print(f"  Total sheet music: {stats['total']}")
    print()

    def _rows(items: list[tuple[str, int]]) -> list[list[str]]:
        return [[name, str(count)] for name, count in items]

    composers = stats.get("top_composers", [])
    if composers:
        print(style("Top Composers", "bold"))
        print_table(_rows(composers), ["Composer", "Count"], right_align={1}, max_widths={"Composer": 36, "Count": 7})
        print()

    instrumentation = stats.get("top_instrumentation", [])
    if instrumentation:
        print(style("Top Instrumentation", "bold"))
        print_table(
            _rows(instrumentation),
            ["Instrumentation", "Count"],
            right_align={1},
            max_widths={"Instrumentation": 36, "Count": 7},
        )
        print()

    difficulty = stats.get("by_difficulty", [])
    if difficulty:
        print(style("Difficulty Split", "bold"))
        print_table(_rows(difficulty), ["Difficulty", "Count"], right_align={1}, max_widths={"Difficulty": 24, "Count": 7})
        print()

    practice = stats.get("by_practice_status", [])
    if practice:
        print(style("Practice Status", "bold"))
        print_table(_rows(practice), ["Status", "Count"], right_align={1}, max_widths={"Status": 24, "Count": 7})
        print()


OBSIDIAN_MANAGED_DIR = "Alexandria"
OBSIDIAN_PATH_MARKER = ".alexandria_obsidian_vault_path"
OBSIDIAN_BLOCK_START = "<!-- ALEXANDRIA:START -->"
OBSIDIAN_BLOCK_END = "<!-- ALEXANDRIA:END -->"
OBSIDIAN_NOTE_INDEX_FILE = "note_index.json"
OBSIDIAN_SNIPPET_REL_PATH = Path(".obsidian") / "snippets" / "alexandria.css"
OBSIDIAN_SCHEMA_VERSION = "alexandria.v2"
OBSIDIAN_FRONTMATTER_ORDER = [
    "alexandria_schema",
    "managed_by",
    "type",
    "title",
    "alexandria_id",
    "item_type",
    "creator",
    "author",
    "composer",
    "language",
    "genre",
    "genres",
    "tags",
    "rating",
    "progress",
    "read",
    "location",
    "cover",
    "year",
    "pages",
    "isbn",
    "in_reading_list",
    "updated_at",
]
OBSIDIAN_FRONTMATTER_DEFAULTS: dict[str, object] = {
    "alexandria_schema": OBSIDIAN_SCHEMA_VERSION,
    "managed_by": "alexandria",
    "type": "note",
    "title": "",
    "alexandria_id": None,
    "item_type": None,
    "creator": "",
    "author": "",
    "composer": "",
    "language": "",
    "genre": "",
    "genres": [],
    "tags": [],
    "rating": None,
    "progress": 0,
    "read": False,
    "location": "",
    "cover": "",
    "year": None,
    "pages": None,
    "isbn": "",
    "in_reading_list": False,
    "updated_at": "",
}


def _command_tail(raw_cmd: str, prefix: str) -> str:
    prefix_tokens = [token for token in prefix.strip().split() if token]
    if not prefix_tokens:
        return raw_cmd.strip()
    pattern = r"^\s*" + r"\s+".join(re.escape(token) for token in prefix_tokens) + r"(?:\s+(.*))?\s*$"
    match = re.match(pattern, raw_cmd, flags=re.IGNORECASE)
    if match:
        return (match.group(1) or "").strip()
    return ""


def _sanitize_note_name(value: str, fallback: str = "Untitled") -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", " ", str(value or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).rstrip(".").strip()
    return cleaned or fallback


def _wiki_target(rel_path: str) -> str:
    path_text = str(rel_path).replace("\\", "/").strip()
    return path_text[:-3] if path_text.lower().endswith(".md") else path_text


def _wiki_link(rel_path: str, alias: str | None = None) -> str:
    target = _wiki_target(rel_path)
    label = (alias or "").strip()
    if label:
        return f"[[{target}|{label}]]"
    return f"[[{target}]]"


def _obsidian_config_path(data_file: Path) -> Path:
    return data_file.parent / OBSIDIAN_PATH_MARKER


def _load_obsidian_vault_path(data_file: Path) -> Path | None:
    marker = _obsidian_config_path(data_file)
    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    return Path(raw).expanduser()


def _store_obsidian_vault_path(data_file: Path, vault_path: Path) -> None:
    marker = _obsidian_config_path(data_file)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(vault_path.resolve()) + "\n", encoding="utf-8")


def _resolve_obsidian_vault_path(path_hint: str | None, data_file: Path, prompt_if_missing: bool) -> Path | None:
    candidate_text = (path_hint or "").strip()
    if candidate_text:
        return Path(candidate_text).expanduser()

    configured = _load_obsidian_vault_path(data_file)
    if configured is not None:
        return configured

    if prompt_if_missing:
        entered = input("Obsidian vault path: ").strip()
        if entered:
            return Path(entered).expanduser()
    return None


def _split_values(raw: str) -> list[str]:
    return [part.strip() for part in str(raw or "").split(",") if part.strip()]


def _unique_note_path(directory: Path, title: str, used_paths: set[Path]) -> Path:
    stem = _sanitize_note_name(title, "Untitled")
    candidate = directory / f"{stem}.md"
    index = 2
    while candidate in used_paths:
        candidate = directory / f"{stem} ({index}).md"
        index += 1
    used_paths.add(candidate)
    return candidate


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _yaml_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_list(values: list[object]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(_yaml_scalar(value) for value in values) + "]"


def _normalize_frontmatter(meta: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key in OBSIDIAN_FRONTMATTER_ORDER:
        default = OBSIDIAN_FRONTMATTER_DEFAULTS.get(key)
        normalized[key] = list(default) if isinstance(default, list) else default

    for key, value in meta.items():
        if key in {"tags", "genres"}:
            if value is None:
                normalized[key] = []
            elif isinstance(value, str):
                normalized[key] = _split_values(value)
            elif isinstance(value, (list, tuple, set)):
                normalized[key] = [str(item).strip() for item in value if str(item).strip()]
            else:
                normalized[key] = [str(value).strip()] if str(value).strip() else []
            continue
        normalized[key] = value

    return normalized


def _frontmatter_text(meta: dict[str, object]) -> str:
    payload = _normalize_frontmatter(meta)
    lines = ["---"]
    for key in OBSIDIAN_FRONTMATTER_ORDER:
        value = payload.get(key)
        if isinstance(value, list):
            lines.append(f"{key}: {_yaml_list(value)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    for key in sorted(payload):
        if key in OBSIDIAN_FRONTMATTER_ORDER:
            continue
        value = payload[key]
        if isinstance(value, list):
            lines.append(f"{key}: {_yaml_list(value)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def _split_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith("---\n"):
        end_index = text.find("\n---\n", 4)
        if end_index != -1:
            frontmatter = text[4:end_index]
            body = text[end_index + 5 :]
            return frontmatter, body
    return "", text


def _extract_section_text(body: str, heading: str) -> str:
    pattern = re.compile(rf"(?ms)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)")
    match = pattern.search(body)
    if not match:
        return ""
    return match.group(1).strip()


def _extract_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    pattern = re.compile(r"(?ms)^##\s+([^\n]+?)\s*\n(.*?)(?=^##\s+|\Z)")
    for match in pattern.finditer(body):
        heading = match.group(1).strip().casefold()
        sections[heading] = match.group(2).strip()
    return sections


def _strip_managed_block(text: str) -> str:
    start_index = text.find(OBSIDIAN_BLOCK_START)
    if start_index == -1:
        return text.strip()
    end_index = text.find(OBSIDIAN_BLOCK_END, start_index)
    if end_index == -1:
        return text.strip()
    end_index += len(OBSIDIAN_BLOCK_END)
    return (text[:start_index] + text[end_index:]).strip()


def _render_managed_block(lines: list[str]) -> str:
    inner = "\n".join(lines).strip()
    if inner:
        return f"{OBSIDIAN_BLOCK_START}\n{inner}\n{OBSIDIAN_BLOCK_END}"
    return f"{OBSIDIAN_BLOCK_START}\n{OBSIDIAN_BLOCK_END}"


def _replace_managed_block(existing_body: str, managed_block: str, title: str) -> str:
    sections = _extract_sections(existing_body)
    preserved_connections = sections.get("connections", "").strip()
    preserved_analysis = sections.get("analysis", "").strip()
    preserved_notes = sections.get("notes", "").strip()
    preserved_metadata = sections.get("metadata", "").strip()
    metadata_tail = _strip_managed_block(preserved_metadata)

    if not sections:
        legacy_payload = _strip_managed_block(existing_body).strip()
        if legacy_payload:
            preserved_notes = "### Preserved from previous sync\n\n" + legacy_payload

    metadata_block = managed_block
    if metadata_tail:
        metadata_block = managed_block + "\n\n" + metadata_tail

    body_lines = [
        f"# {title}",
        "",
        "## Metadata",
        metadata_block,
        "",
        "## Connections",
        preserved_connections or "Add manual wiki links to related ideas.",
        "",
        "## Analysis",
        preserved_analysis or "Write your analysis here.",
        "",
        "## Notes",
        preserved_notes or "Write your notes here.",
        "",
    ]
    return "\n".join(body_lines)


def _write_text_file(path: Path, text: str) -> str:
    existed = path.exists()
    previous = ""
    if existed:
        try:
            previous = path.read_text(encoding="utf-8")
        except OSError:
            previous = ""
    if existed and previous == text:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return "updated" if existed else "added"


def _write_managed_note(path: Path, title: str, frontmatter: dict[str, object], managed_lines: list[str]) -> str:
    existing_text = ""
    existed = path.exists()
    if existed:
        try:
            existing_text = path.read_text(encoding="utf-8")
        except OSError:
            existing_text = ""

    _frontmatter, existing_body = _split_frontmatter(existing_text)
    managed_block = _render_managed_block(managed_lines)
    merged_body = _replace_managed_block(existing_body, managed_block, title)
    meta_payload = dict(frontmatter)
    meta_payload.setdefault("title", title)
    composed = _frontmatter_text(meta_payload).rstrip() + "\n\n" + merged_body.rstrip() + "\n"
    if existed and composed == existing_text:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(composed, encoding="utf-8")
    return "updated" if existed else "added"


def _cleanup_empty_dirs(root: Path) -> None:
    for current, _dirs, files in os.walk(root, topdown=False):
        current_path = Path(current)
        if current_path == root:
            continue
        # Keep first-level managed folders stable even when currently empty.
        if current_path.parent == root:
            continue
        if files:
            continue
        try:
            if not any(current_path.iterdir()):
                current_path.rmdir()
        except OSError:
            continue


def _path_within(parent: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _is_alexandria_managed_note(path: Path) -> bool:
    try:
        snippet = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return OBSIDIAN_BLOCK_START in snippet or "managed_by: \"alexandria\"" in snippet or "managed_by: alexandria" in snippet


def _looks_like_alexandria_managed_root(path: Path) -> bool:
    if not path.is_dir():
        return False
    note_index = path / "Meta" / OBSIDIAN_NOTE_INDEX_FILE
    if note_index.exists():
        return True
    index_note = path / "Library Of Alexandria.md"
    if index_note.exists() and _is_alexandria_managed_note(index_note):
        return True
    required_dirs = ("Books", "Authors", "Genres", "Tags", "Languages", "Locations")
    present = sum(1 for name in required_dirs if (path / name).is_dir())
    return present >= 4 and index_note.exists()


def _progress_percent(book: Book) -> int:
    if book.pages and book.pages > 0:
        current = book.progress_pages if book.progress_pages is not None else (book.pages if book.read else 0)
        return max(0, min(100, int(round((current / book.pages) * 100))))
    if book.read:
        return 100
    if book.progress_pages is not None:
        return max(0, min(100, book.progress_pages))
    return 0


def _looks_like_path(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    return text.startswith(("~", "/", "./", "../")) or "\\" in text or "/" in text or (len(text) > 1 and text[1] == ":")


def _load_note_index(vault_path: Path) -> dict[str, object] | None:
    index_path = vault_path.expanduser().resolve() / OBSIDIAN_MANAGED_DIR / "Meta" / OBSIDIAN_NOTE_INDEX_FILE
    try:
        raw = index_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _read_json_object(path: Path) -> dict[str, object] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _write_json_file(path: Path, payload: dict[str, object]) -> str:
    return _write_text_file(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _configure_obsidian_core_plugins(vault_root: Path) -> str:
    path = vault_root / ".obsidian" / "core-plugins.json"
    payload = _read_json_object(path) or {}
    required_plugins = {
        "file-explorer": True,
        "global-search": True,
        "graph": True,
        "bookmarks": True,
        "templates": True,
        "properties": True,
        "bases": True,
    }
    for key, value in required_plugins.items():
        payload[key] = value
    return _write_json_file(path, payload)


def _configure_obsidian_templates(vault_root: Path, template_folder: str) -> str:
    path = vault_root / ".obsidian" / "templates.json"
    payload = _read_json_object(path) or {}
    payload["folder"] = template_folder
    payload.setdefault("dateFormat", "YYYY-MM-DD")
    payload.setdefault("timeFormat", "HH:mm")
    return _write_json_file(path, payload)


def _configure_obsidian_graph(vault_root: Path) -> str:
    path = vault_root / ".obsidian" / "graph.json"
    payload = _read_json_object(path) or {}
    payload.update(
        {
            "search": 'path:"Alexandria"',
            "showTags": False,
            "showAttachments": False,
            "showOrphans": False,
            "showArrow": False,
            "close": True,
        }
    )
    return _write_json_file(path, payload)


def _walk_workspace_leaves(node: object) -> list[dict[str, object]]:
    if not isinstance(node, dict):
        return []
    node_type = node.get("type")
    if node_type == "leaf":
        return [node]
    leaves: list[dict[str, object]] = []
    for child in node.get("children", []):
        leaves.extend(_walk_workspace_leaves(child))
    return leaves


def _configure_obsidian_workspace(vault_root: Path, default_file: str, search_query: str) -> str:
    path = vault_root / ".obsidian" / "workspace.json"
    payload = _read_json_object(path) or {}
    main = payload.get("main")
    leaves = _walk_workspace_leaves(main)
    if not leaves:
        leaf_id = "alexandria-main-leaf"
        payload["main"] = {
            "id": "alexandria-main-split",
            "type": "split",
            "direction": "vertical",
            "children": [
                {
                    "id": "alexandria-main-tabs",
                    "type": "tabs",
                    "children": [{"id": leaf_id, "type": "leaf", "state": {}}],
                }
            ],
        }
        leaves = _walk_workspace_leaves(payload["main"])

    main_leaf = leaves[0]
    main_leaf["state"] = {
        "type": "markdown",
        "state": {
            "file": default_file,
            "mode": "preview",
            "source": False,
        },
        "icon": "lucide-file-text",
        "title": Path(default_file).stem,
    }
    payload["active"] = main_leaf.get("id", payload.get("active", "alexandria-main-leaf"))

    left_leaves = _walk_workspace_leaves(payload.get("left"))
    for leaf in left_leaves:
        state = leaf.get("state")
        if not isinstance(state, dict):
            continue
        if state.get("type") != "search":
            continue
        search_state = state.setdefault("state", {})
        if isinstance(search_state, dict):
            search_state["query"] = search_query
            search_state.setdefault("matchingCase", False)
            search_state.setdefault("explainSearch", False)
            search_state.setdefault("collapseAll", False)
            search_state.setdefault("extraContext", False)
            search_state.setdefault("sortOrder", "alphabetical")
        break

    last_open = payload.get("lastOpenFiles")
    dedup: list[str] = []
    seen: set[str] = set()
    for entry in [default_file, "Alexandria/MOC/Library.md", "Alexandria/Dashboards/Saved Searches.md"] + (
        list(last_open) if isinstance(last_open, list) else []
    ):
        text = str(entry).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        dedup.append(text)
    payload["lastOpenFiles"] = dedup[:20]

    return _write_json_file(path, payload)


def _configure_obsidian_bookmarks(vault_root: Path, entries: list[tuple[str, str]]) -> str:
    path = vault_root / ".obsidian" / "bookmarks.json"
    payload = _read_json_object(path) or {}
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
    filtered = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).strip() == "group" and str(item.get("title", "")).strip().casefold() == "alexandria":
            continue
        filtered.append(item)

    now_ms = int(time.time() * 1000)
    group_items: list[dict[str, object]] = []
    for index, (title, rel_path) in enumerate(entries):
        group_items.append(
            {
                "type": "file",
                "ctime": now_ms + index,
                "path": rel_path,
                "title": title,
            }
        )
    alex_group = {
        "type": "group",
        "ctime": now_ms,
        "title": "Alexandria",
        "items": group_items,
    }
    payload["items"] = [alex_group, *filtered]
    return _write_json_file(path, payload)


def _write_obsidian_vault(library: Library, vault_path: Path) -> dict[str, object]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    vault_root = vault_path.expanduser().resolve()
    vault_root.mkdir(parents=True, exist_ok=True)
    managed_root = vault_root / OBSIDIAN_MANAGED_DIR
    managed_root.mkdir(parents=True, exist_ok=True)
    managed_root_resolved = managed_root.resolve()

    legacy_roots_removed: list[Path] = []
    for sibling in sorted(vault_root.iterdir(), key=lambda item: item.name.casefold()):
        if not sibling.is_dir():
            continue
        sibling_resolved = sibling.resolve()
        if sibling_resolved == managed_root_resolved:
            continue
        key = sibling.name.strip().casefold().replace("_", " ")
        has_name_hint = "alexandria" in key or "library of alexandria" in key
        if not has_name_hint:
            continue
        if not _looks_like_alexandria_managed_root(sibling):
            continue
        try:
            shutil.rmtree(sibling)
            legacy_roots_removed.append(sibling_resolved)
        except OSError:
            continue

    dirs = {
        "root": managed_root,
        "books": managed_root / "Books",
        "sheet": managed_root / "Sheet Music",
        "authors": managed_root / "Authors",
        "genres": managed_root / "Genres",
        "tags": managed_root / "Tags",
        "languages": managed_root / "Languages",
        "locations": managed_root / "Locations",
        "bases": managed_root / "Bases",
        "templates": managed_root / "Templates",
        "dashboards": managed_root / "Dashboards",
        "moc": managed_root / "MOC",
        "analysis": managed_root / "Analysis",
        "reports": managed_root / "Reports",
        "meta": managed_root / "Meta",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)

    existing_markdown_files = {path.resolve() for path in managed_root.rglob("*.md") if path.is_file()}

    changes: dict[str, list[Path]] = {
        "added": [],
        "updated": [],
        "unchanged": [],
        "removed": [],
    }
    target_paths: set[Path] = set()

    used_paths: set[Path] = set()
    item_by_id: dict[str, Book] = {}
    item_note_path: dict[str, Path] = {}
    item_tags: dict[str, list[str]] = {}
    author_display: dict[str, str] = {}
    author_items: dict[str, list[str]] = {}
    genre_display: dict[str, str] = {}
    genre_items: dict[str, list[str]] = {}
    tag_display: dict[str, str] = {}
    tag_items: dict[str, list[str]] = {}
    language_display: dict[str, str] = {}
    language_items: dict[str, list[str]] = {}
    location_display: dict[str, str] = {}
    location_items: dict[str, list[str]] = {}

    def register(map_display: dict[str, str], map_items: dict[str, list[str]], value: str, item_id: str) -> str | None:
        cleaned = str(value or "").strip()
        if not cleaned:
            return None
        key = cleaned.casefold()
        if key not in map_display:
            map_display[key] = cleaned
        entries = map_items.setdefault(key, [])
        if item_id not in entries:
            entries.append(item_id)
        return key

    genre_keys_global: set[str] = set()
    for book in library.books:
        for genre in _split_values(book.genre):
            normalized = genre.casefold().strip()
            if normalized:
                genre_keys_global.add(normalized)
    overlap_tags_filtered = 0

    for index, book in enumerate(library.books, start=1):
        base_id = book.book_id or f"i{index:04d}"
        item_id = base_id
        suffix = 2
        while item_id in item_by_id:
            item_id = f"{base_id}-{suffix:02d}"
            suffix += 1
        item_by_id[item_id] = book
        note_dir = dirs["sheet"] if book.item_type == "SheetMusic" else dirs["books"]
        note_path = note_dir / f"{_sanitize_note_name(item_id, item_id)}.md"
        while note_path in used_paths:
            note_path = _unique_note_path(note_dir, item_id, used_paths)
        used_paths.add(note_path)
        item_note_path[item_id] = note_path

        creator = (book.composer or book.author or "Unknown").strip() or "Unknown"
        register(author_display, author_items, creator, item_id)
        for genre in _split_values(book.genre):
            register(genre_display, genre_items, genre, item_id)
        filtered_tags: list[str] = []
        seen_tags: set[str] = set()
        for tag in book.tags:
            cleaned_tag = str(tag).strip()
            if not cleaned_tag:
                continue
            tag_key = cleaned_tag.casefold()
            if tag_key in seen_tags:
                continue
            seen_tags.add(tag_key)
            if tag_key in genre_keys_global:
                overlap_tags_filtered += 1
                continue
            filtered_tags.append(cleaned_tag)
            register(tag_display, tag_items, cleaned_tag, item_id)
        item_tags[item_id] = filtered_tags
        register(language_display, language_items, book.language or "Unknown", item_id)
        register(location_display, location_items, book.location or "Unknown", item_id)

    def build_lookup(display_map: dict[str, str], directory: Path) -> dict[str, Path]:
        lookup: dict[str, Path] = {}
        for key, name in sorted(display_map.items(), key=lambda item: item[1].casefold()):
            lookup[key] = _unique_note_path(directory, name, used_paths)
        return lookup

    author_note_path = build_lookup(author_display, dirs["authors"])
    genre_note_path = build_lookup(genre_display, dirs["genres"])
    tag_note_path = build_lookup(tag_display, dirs["tags"])
    language_note_path = build_lookup(language_display, dirs["languages"])
    location_note_path = build_lookup(location_display, dirs["locations"])

    reading_lookup = {item.casefold() for item in library.reading_list}

    def rel(path: Path) -> str:
        return path.relative_to(managed_root).as_posix()

    def item_link(item_id: str) -> str:
        book = item_by_id[item_id]
        return _wiki_link(rel(item_note_path[item_id]), f"{book.title} ({item_id})")

    def write_note(path: Path, title: str, meta: dict[str, object], managed_lines: list[str]) -> None:
        status = _write_managed_note(path, title, meta, managed_lines)
        resolved = path.resolve()
        target_paths.add(resolved)
        changes[status].append(resolved)

    def note_meta(note_type: str, **overrides: object) -> dict[str, object]:
        meta: dict[str, object] = {
            "type": note_type,
            "author": "Alexandria",
            "creator": "Alexandria",
            "language": "",
            "genre": "",
            "genres": [],
            "rating": None,
            "progress": 0,
            "read": False,
            "location": "",
            "updated_at": generated_at,
            "managed_by": "alexandria",
            "tags": [],
        }
        meta.update(overrides)
        return meta

    for item_id, path in sorted(item_note_path.items(), key=lambda entry: entry[0].casefold()):
        book = item_by_id[item_id]
        tags_for_note = item_tags.get(item_id, [])
        creator = (book.composer or book.author or "Unknown").strip() or "Unknown"
        creator_key = creator.casefold()
        creator_link = _wiki_link(rel(author_note_path[creator_key]), author_display[creator_key]) if creator_key in author_note_path else "-"

        genre_links = []
        for genre in _split_values(book.genre):
            key = genre.casefold()
            if key in genre_note_path:
                genre_links.append(_wiki_link(rel(genre_note_path[key]), genre_display[key]))

        tag_links = []
        for tag in tags_for_note:
            key = tag.casefold()
            if key in tag_note_path:
                tag_links.append(_wiki_link(rel(tag_note_path[key]), tag_display[key]))

        language_key = (book.language or "Unknown").casefold()
        language_link = _wiki_link(rel(language_note_path[language_key]), language_display[language_key]) if language_key in language_note_path else "-"
        location_key = (book.location or "Unknown").casefold()
        location_link = _wiki_link(rel(location_note_path[location_key]), location_display[location_key]) if location_key in location_note_path else "-"

        managed_lines = [
            f"- ID: `{item_id}`",
            f"- Type: `{book.item_type}`",
            f"- Title: {book.title}",
            f"- Author: {book.author or '-'}",
            f"- ISBN: `{book.isbn or '-'}`",
            f"- Year: `{book.year if book.year is not None else '-'}`",
            f"- Genre: {book.genre or '-'}",
            f"- Language: {book.language}",
            f"- Cover: {book.cover}",
            f"- Pages: `{book.pages if book.pages is not None else '-'}`",
            f"- Progress: `{book.progress_label()}`",
            f"- Rating: `{book.rating if book.rating is not None else '-'}`",
            f"- Read: `{'yes' if book.read else 'no'}`",
            f"- Location: {book.location}",
            f"- Reading list: `{'yes' if item_id.casefold() in reading_lookup else 'no'}`",
            f"- Tags: {', '.join(tags_for_note) if tags_for_note else '-'}",
            "",
            "### Auto Connections",
            f"- Creator note: {creator_link}",
            f"- Language note: {language_link}",
            f"- Location note: {location_link}",
            f"- Genre notes: {', '.join(genre_links) if genre_links else '-'}",
            f"- Tag notes: {', '.join(tag_links) if tag_links else '-'}",
        ]
        if book.item_type == "SheetMusic":
            managed_lines.extend(
                [
                    "",
                    "### Sheet Music Specs",
                    f"- Composer: {book.composer or '-'}",
                    f"- Instrumentation: {book.instrumentation or '-'}",
                    f"- Catalog / Work Number: {book.catalog_number or '-'}",
                    f"- Key Signature: {book.key_signature or '-'}",
                    f"- Era / Style: {book.era_style or '-'}",
                    f"- Difficulty: {book.difficulty or '-'}",
                    f"- Duration: `{book.duration_minutes if book.duration_minutes is not None else '-'} min`",
                    f"- Publisher: {book.publisher or '-'}",
                    f"- Practice Status: {book.practice_status or '-'}",
                    f"- Last Practiced: {book.last_practiced or '-'}",
                ]
            )

        note_type = "sheet_music" if book.item_type == "SheetMusic" else "book"
        genres_for_note = _split_values(book.genre)
        primary_genre = genres_for_note[0] if genres_for_note else ""
        write_note(
            path,
            f"{book.title} ({item_id})",
            note_meta(
                note_type,
                author=book.author or creator,
                creator=creator,
                composer=book.composer or "",
                language=book.language,
                genre=primary_genre,
                genres=genres_for_note,
                rating=book.rating,
                progress=_progress_percent(book),
                read=book.read,
                location=book.location,
                cover=book.cover,
                year=book.year,
                pages=book.pages,
                isbn=book.isbn,
                item_type=book.item_type,
                alexandria_id=item_id,
                in_reading_list=item_id.casefold() in reading_lookup,
                read_at=book.read_at,
                progress_label=book.progress_label(),
                tags=list(tags_for_note),
            ),
            managed_lines,
        )

    for key, path in sorted(author_note_path.items(), key=lambda item: author_display[item[0]].casefold()):
        ids = sorted(author_items.get(key, []), key=lambda item_id: (item_by_id[item_id].title.casefold(), item_id.casefold()))
        genre_counts: dict[str, int] = {}
        tag_counts: dict[str, int] = {}
        for item_id in ids:
            book = item_by_id[item_id]
            for genre in _split_values(book.genre):
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
            for tag in item_tags.get(item_id, []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_genres = sorted(genre_counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:8]
        top_tags = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:10]
        managed_lines = [
            f"- Author: {author_display[key]}",
            f"- Items: `{len(ids)}`",
            f"- Top Genres: {', '.join(f'{name} ({count})' for name, count in top_genres) if top_genres else '-'}",
            f"- Top Tags: {', '.join(f'{name} ({count})' for name, count in top_tags) if top_tags else '-'}",
            "",
            "### Items",
            *(f"- {item_link(item_id)}" for item_id in ids),
        ]
        write_note(
            path,
            f"Author: {author_display[key]}",
            note_meta(
                "author",
                author=author_display[key],
                creator=author_display[key],
                items_count=len(ids),
            ),
            managed_lines,
        )

    def write_collection_group(
        note_type: str,
        note_paths: dict[str, Path],
        item_groups: dict[str, list[str]],
        labels: dict[str, str],
    ) -> None:
        for key, path in sorted(note_paths.items(), key=lambda item: labels[item[0]].casefold()):
            ids = sorted(item_groups.get(key, []), key=lambda item_id: (item_by_id[item_id].title.casefold(), item_id.casefold()))
            managed_lines = [f"- Label: {labels[key]}", f"- Items: `{len(ids)}`", "", "### Items"]
            managed_lines.extend(f"- {item_link(item_id)}" for item_id in ids)
            write_note(
                path,
                f"{note_type.capitalize()}: {labels[key]}",
                note_meta(
                    note_type,
                    language=labels[key] if note_type == "language" else "",
                    genre=labels[key] if note_type == "genre" else "",
                    location=labels[key] if note_type == "location" else "",
                    items_count=len(ids),
                ),
                managed_lines,
            )

    write_collection_group("genre", genre_note_path, genre_items, genre_display)
    write_collection_group("tag", tag_note_path, tag_items, tag_display)
    write_collection_group("language", language_note_path, language_items, language_display)
    write_collection_group("location", location_note_path, location_items, location_display)

    book_ids = [item_id for item_id, book in item_by_id.items() if book.item_type == "Book"]
    sheet_ids = [item_id for item_id, book in item_by_id.items() if book.item_type == "SheetMusic"]

    base_specs: list[tuple[str, str, str]] = [
        (
            "all",
            "All Items.base",
            """filters:
  or:
    - file.inFolder("Alexandria/Books")
    - file.inFolder("Alexandria/Sheet Music")
properties:
  alexandria_id:
    displayName: ID
  item_type:
    displayName: Type
  title:
    displayName: Title
  creator:
    displayName: Creator
  language:
    displayName: Language
  genre:
    displayName: Genre
  rating:
    displayName: Rating
  progress:
    displayName: Progress
  read:
    displayName: Read
  location:
    displayName: Location
  updated_at:
    displayName: Updated
views:
  - type: table
    name: "Alle Bücher"
    order:
      - alexandria_id
      - item_type
      - title
      - creator
      - language
      - genre
      - rating
      - progress
      - read
      - location
      - updated_at
  - type: cards
    name: "Karten"
    order:
      - title
      - creator
      - language
      - genre
      - rating
      - progress
      - location
""",
        ),
        (
            "unread",
            "Unread.base",
            """filters:
  or:
    - file.inFolder("Alexandria/Books")
    - file.inFolder("Alexandria/Sheet Music")
views:
  - type: table
    name: "Ungelesen"
    filters:
      - read == false
    order:
      - alexandria_id
      - item_type
      - title
      - creator
      - language
      - genre
      - rating
      - progress
      - location
  - type: cards
    name: "Ungelesen Karten"
    filters:
      - read == false
    order:
      - title
      - creator
      - language
      - genre
      - rating
      - progress
      - location
""",
        ),
        (
            "top_rated",
            "Top Rated.base",
            """filters:
  or:
    - file.inFolder("Alexandria/Books")
    - file.inFolder("Alexandria/Sheet Music")
views:
  - type: table
    name: "Top Rated"
    filters:
      - rating >= 4
    order:
      - alexandria_id
      - item_type
      - title
      - creator
      - rating
      - progress
      - read
      - location
  - type: cards
    name: "Top Rated Karten"
    filters:
      - rating >= 4
    order:
      - title
      - creator
      - rating
      - progress
      - location
""",
        ),
        (
            "by_language",
            "By Language.base",
            """filters:
  or:
    - file.inFolder("Alexandria/Books")
    - file.inFolder("Alexandria/Sheet Music")
views:
  - type: table
    name: "Nach Sprache"
    groupBy:
      property: language
      direction: ASC
    order:
      - language
      - alexandria_id
      - title
      - creator
      - genre
      - rating
      - progress
      - read
      - location
""",
        ),
        (
            "by_genre",
            "By Genre.base",
            """filters:
  or:
    - file.inFolder("Alexandria/Books")
    - file.inFolder("Alexandria/Sheet Music")
views:
  - type: table
    name: "Nach Genre"
    filters:
      - genre != ""
    groupBy:
      property: genre
      direction: ASC
    order:
      - genre
      - alexandria_id
      - title
      - creator
      - language
      - rating
      - progress
      - read
      - location
""",
        ),
    ]
    base_links: dict[str, str] = {}
    for key, filename, content in base_specs:
        base_path = dirs["bases"] / filename
        status = _write_text_file(base_path, content.rstrip() + "\n")
        resolved = base_path.resolve()
        target_paths.add(resolved)
        changes[status].append(resolved)
        base_links[key] = _wiki_link(rel(base_path), filename.replace(".base", ""))

    def write_dashboard(title: str, filename: str, query_lines: list[str], summary_lines: list[str] | None = None) -> None:
        lines = summary_lines[:] if summary_lines else []
        if lines:
            lines.append("")
        lines.extend(["### Dataview Query", "```dataview", *query_lines, "```"])
        write_note(
            dirs["dashboards"] / filename,
            f"Dashboard: {title}",
            note_meta("dashboard"),
            lines,
        )

    write_dashboard(
        "Unread",
        "Unread.md",
        [
            "TABLE alexandria_id AS ID, type AS Type, author AS Author, genre AS Genre, language AS Language, rating AS Rating, progress AS Progress, location AS Location",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "WHERE read = false",
            "SORT rating DESC, updated_at DESC",
        ],
        [
            f"- Unread items in library: `{sum(1 for book in library.books if not book.read)}`",
            f"- Base view: {base_links['unread']}",
        ],
    )
    write_dashboard(
        "Top Rated",
        "Top Rated.md",
        [
            "TABLE alexandria_id AS ID, type AS Type, author AS Author, rating AS Rating, progress AS Progress",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "WHERE rating >= 4",
            "SORT rating DESC, progress DESC, updated_at DESC",
        ],
        [f"- Base view: {base_links['top_rated']}"],
    )
    write_dashboard(
        "By Language",
        "By Language.md",
        [
            "TABLE WITHOUT ID language AS Language, length(rows) AS Count",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "GROUP BY language",
            "SORT Count DESC",
        ],
        [f"- Base view: {base_links['by_language']}"],
    )
    write_dashboard(
        "By Genre",
        "By Genre.md",
        [
            "TABLE WITHOUT ID genre AS Genre, length(rows) AS Count",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "WHERE genre",
            "GROUP BY genre",
            "SORT Count DESC",
        ],
        [f"- Base view: {base_links['by_genre']}"],
    )
    write_dashboard(
        "Reading List",
        "Reading List.md",
        [
            "TABLE alexandria_id AS ID, type AS Type, author AS Author, rating AS Rating, progress AS Progress, location AS Location",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "WHERE in_reading_list = true",
            "SORT updated_at DESC",
        ],
        [
            f"- Reading list entries: `{sum(1 for item_id in item_by_id if item_id.casefold() in reading_lookup)}`",
            f"- Start in main base: {base_links['all']}",
        ],
    )
    write_dashboard(
        "Progress",
        "Progress.md",
        [
            "TABLE alexandria_id AS ID, author AS Author, progress AS Progress, rating AS Rating, read AS Read",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "WHERE progress > 0",
            "SORT progress DESC, updated_at DESC",
        ],
        [f"- Main base: {base_links['all']}"],
    )

    def search_uri(query_text: str) -> str:
        return f"obsidian://search?vault={quote(vault_root.name)}&query={quote(query_text)}"

    saved_searches = [
        ("Unread", 'path:"Alexandria" [read: false]'),
        ("Top Rated", 'path:"Alexandria" [rating: 5] OR [rating: 4]'),
        ("Reading List", 'path:"Alexandria" [in_reading_list: true]'),
        ("German Books", 'path:"Alexandria" [language: German]'),
        ("By Genre (edit value)", 'path:"Alexandria" [genre: philosophy]'),
    ]

    write_note(
        dirs["dashboards"] / "GUI Home.md",
        "Dashboard: GUI Home",
        note_meta("dashboard"),
        [
            "- This is the primary GUI entry point for daily work in Obsidian.",
            "",
            "### Bases (Main UI)",
            f"- {base_links['all']}",
            f"- {base_links['unread']}",
            f"- {base_links['top_rated']}",
            f"- {base_links['by_language']}",
            f"- {base_links['by_genre']}",
            "",
            "### Dashboards",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'Unread.md'), 'Unread')}",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'Top Rated.md'), 'Top Rated')}",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'By Language.md'), 'By Language')}",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'By Genre.md'), 'By Genre')}",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'Reading List.md'), 'Reading List')}",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'Progress.md'), 'Progress')}",
            "",
            "### Navigation",
            f"- {_wiki_link(rel(dirs['moc'] / 'Library.md'), 'MOC: Library')}",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'Saved Searches.md'), 'Saved Searches')}",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'Bookmarks.md'), 'Bookmarks')}",
            "",
            "### Graph",
            "- Use graph only for exploration. Daily browsing/sorting is faster in Bases and dashboards.",
        ],
    )

    write_note(
        dirs["dashboards"] / "Saved Searches.md",
        "Dashboard: Saved Searches",
        note_meta("dashboard"),
        [
            "- Reusable Obsidian search queries for fast filtering.",
            "",
            "### Queries",
            *(
                f"- {label}: `{query_text}`  ([Open]({search_uri(query_text)}))"
                for label, query_text in saved_searches
            ),
            "",
            "### Tip",
            "- Bookmark this page and pin the queries you use most.",
        ],
    )

    write_note(
        dirs["dashboards"] / "Bookmarks.md",
        "Dashboard: Bookmarks",
        note_meta("dashboard"),
        [
            "- Suggested bookmarks for frequent actions.",
            "",
            "### Bases",
            f"- {base_links['all']}",
            f"- {base_links['unread']}",
            f"- {base_links['top_rated']}",
            f"- {base_links['by_language']}",
            f"- {base_links['by_genre']}",
            "",
            "### Key Pages",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'GUI Home.md'), 'GUI Home')}",
            f"- {_wiki_link(rel(dirs['dashboards'] / 'Saved Searches.md'), 'Saved Searches')}",
            f"- {_wiki_link(rel(dirs['moc'] / 'Library.md'), 'MOC: Library')}",
            f"- {_wiki_link(rel(dirs['moc'] / 'Authors.md'), 'MOC: Authors')}",
            f"- {_wiki_link(rel(dirs['moc'] / 'Genres.md'), 'MOC: Genres')}",
            f"- {_wiki_link(rel(dirs['moc'] / 'Tags.md'), 'MOC: Tags')}",
        ],
    )

    dashboard_links = [
        _wiki_link(rel(dirs["dashboards"] / "GUI Home.md"), "GUI Home"),
        _wiki_link(rel(dirs["dashboards"] / "Unread.md"), "Unread"),
        _wiki_link(rel(dirs["dashboards"] / "Top Rated.md"), "Top Rated"),
        _wiki_link(rel(dirs["dashboards"] / "By Language.md"), "By Language"),
        _wiki_link(rel(dirs["dashboards"] / "By Genre.md"), "By Genre"),
        _wiki_link(rel(dirs["dashboards"] / "Reading List.md"), "Reading List"),
        _wiki_link(rel(dirs["dashboards"] / "Progress.md"), "Progress"),
        _wiki_link(rel(dirs["dashboards"] / "Saved Searches.md"), "Saved Searches"),
        _wiki_link(rel(dirs["dashboards"] / "Bookmarks.md"), "Bookmarks"),
    ]

    author_moc_entries = [
        _wiki_link(rel(path), f"{author_display[key]} ({len(author_items.get(key, []))})")
        for key, path in sorted(author_note_path.items(), key=lambda item: author_display[item[0]].casefold())
    ]
    tag_moc_entries = [
        _wiki_link(rel(path), f"{tag_display[key]} ({len(tag_items.get(key, []))})")
        for key, path in sorted(tag_note_path.items(), key=lambda item: tag_display[item[0]].casefold())
    ]
    genre_moc_entries = [
        _wiki_link(rel(path), f"{genre_display[key]} ({len(genre_items.get(key, []))})")
        for key, path in sorted(genre_note_path.items(), key=lambda item: genre_display[item[0]].casefold())
    ]
    book_entries = [item_link(item_id) for item_id in sorted(book_ids, key=str.casefold)]
    sheet_entries = [item_link(item_id) for item_id in sorted(sheet_ids, key=str.casefold)]

    write_note(
        dirs["moc"] / "Library.md",
        "MOC: Library",
        note_meta("moc"),
        [
            f"- Generated: `{generated_at}`",
            f"- Total items: `{len(item_by_id)}`",
            f"- Books: `{len(book_ids)}`",
            f"- Sheet Music: `{len(sheet_ids)}`",
            f"- Authors: `{len(author_note_path)}`",
            f"- Genres: `{len(genre_note_path)}`",
            f"- Tags: `{len(tag_note_path)}`",
            "",
            "### Bases (Main UI)",
            f"- {base_links['all']}",
            f"- {base_links['unread']}",
            f"- {base_links['top_rated']}",
            f"- {base_links['by_language']}",
            f"- {base_links['by_genre']}",
            "",
            "### Maps of Content",
            f"- {_wiki_link(rel(dirs['moc'] / 'Books.md'), 'Books')}",
            f"- {_wiki_link(rel(dirs['moc'] / 'Sheet Music.md'), 'Sheet Music')}",
            f"- {_wiki_link(rel(dirs['moc'] / 'Authors.md'), 'Authors')}",
            f"- {_wiki_link(rel(dirs['moc'] / 'Genres.md'), 'Genres')}",
            f"- {_wiki_link(rel(dirs['moc'] / 'Tags.md'), 'Tags')}",
            "",
            "### Dashboards",
            *(f"- {entry}" for entry in dashboard_links),
            "",
            "### Smart Analysis",
            f"- {_wiki_link(rel(dirs['analysis'] / 'Reading Velocity.md'), 'Reading Velocity')}",
            f"- {_wiki_link(rel(dirs['analysis'] / 'Unfinished High-Rated.md'), 'Unfinished High-Rated')}",
            f"- {_wiki_link(rel(dirs['analysis'] / 'Neglected Genres.md'), 'Neglected Genres')}",
            f"- {_wiki_link(rel(dirs['analysis'] / 'Author Concentration.md'), 'Author Concentration')}",
        ],
    )

    write_note(
        dirs["root"] / "Library Of Alexandria.md",
        "Library Of Alexandria",
        note_meta("index"),
        [
            f"- Welcome to the managed Alexandria vault export.",
            f"- Open {_wiki_link(rel(dirs['moc'] / 'Library.md'), 'MOC: Library')} for fast navigation.",
            f"- Open {_wiki_link(rel(dirs['dashboards'] / 'GUI Home.md'), 'Dashboard: GUI Home')} for the main interface.",
            f"- Open {base_links['all']} for table/card browsing.",
            f"- Open {_wiki_link(rel(dirs['reports'] / 'Sync Report.md'), 'Sync Report')} for latest sync status.",
        ],
    )

    def write_moc(title: str, filename: str, entries: list[str], note_type: str = "moc") -> None:
        lines = [f"- Total entries: `{len(entries)}`", "", "### Entries"]
        lines.extend(f"- {entry}" for entry in entries)
        write_note(
            dirs["moc"] / filename,
            f"MOC: {title}",
            note_meta(note_type),
            lines,
        )

    write_moc("Books", "Books.md", book_entries)
    write_moc("Sheet Music", "Sheet Music.md", sheet_entries)
    write_moc("Authors", "Authors.md", author_moc_entries)
    write_moc("Genres", "Genres.md", genre_moc_entries)
    write_moc("Tags", "Tags.md", tag_moc_entries)

    stats = library.stats()
    completed_dates = []
    for book in library.books:
        if not book.read_at:
            continue
        try:
            completed_dates.append(datetime.fromisoformat(book.read_at).date())
        except ValueError:
            continue
    now_date = datetime.now().date()
    recent_90 = sum(1 for item_date in completed_dates if (now_date.toordinal() - item_date.toordinal()) <= 90)
    velocity_per_month = round(recent_90 / 3, 2) if recent_90 else 0.0

    write_note(
        dirs["analysis"] / "Reading Velocity.md",
        "Smart Analysis: Reading Velocity",
        note_meta("analysis"),
        [
            f"- Completed this month: `{stats['this_month']}`",
            f"- Completed this year: `{stats['this_year']}`",
            f"- Completed in last 90 days: `{recent_90}`",
            f"- Estimated monthly velocity (rolling): `{velocity_per_month}` books/month",
            "",
            "### Dataview Query",
            "```dataview",
            "TABLE alexandria_id AS ID, author AS Author, date(read_at) AS Finished",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "WHERE read = true AND read_at",
            "SORT read_at DESC",
            "```",
        ],
    )

    write_note(
        dirs["analysis"] / "Unfinished High-Rated.md",
        "Smart Analysis: Unfinished High-Rated Books",
        note_meta("analysis"),
        [
            "- Shows books/sheet music with high ratings that are still unfinished.",
            "",
            "### Dataview Query",
            "```dataview",
            "TABLE alexandria_id AS ID, type AS Type, author AS Author, rating AS Rating, progress AS Progress, location AS Location",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "WHERE read = false AND rating >= 4",
            "SORT rating DESC, progress DESC, updated_at DESC",
            "```",
        ],
    )

    genre_totals: dict[str, int] = {}
    genre_unread: dict[str, int] = {}
    for book in library.books:
        genres = _split_values(book.genre) or (["(none)"] if not book.genre.strip() else [])
        for genre in genres:
            genre_totals[genre] = genre_totals.get(genre, 0) + 1
            if not book.read:
                genre_unread[genre] = genre_unread.get(genre, 0) + 1
    neglected = []
    for genre_name, total in genre_totals.items():
        unread_count = genre_unread.get(genre_name, 0)
        if total < 2:
            continue
        ratio = unread_count / total
        if ratio >= 0.6:
            neglected.append((genre_name, unread_count, total, ratio))
    neglected.sort(key=lambda item: (-item[3], -item[2], item[0].casefold()))
    neglected_snapshot_lines: list[str]
    if neglected:
        neglected_snapshot_lines = [
            f"- {name}: {unread}/{total} unread ({int(round(ratio * 100))}%)"
            for name, unread, total, ratio in neglected[:12]
        ]
    else:
        neglected_snapshot_lines = ["- No neglected genre detected (threshold: >= 60% unread and at least 2 items)."]

    write_note(
        dirs["analysis"] / "Neglected Genres.md",
        "Smart Analysis: Neglected Genres",
        note_meta("analysis"),
        [
            "- Genres with a high unread ratio in your current collection.",
            "",
            "### Computed Snapshot",
            *neglected_snapshot_lines,
            "",
            "### Dataview Query",
            "```dataview",
            "TABLE WITHOUT ID genre AS Genre, length(rows) AS UnreadCount",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "WHERE read = false AND genre",
            "GROUP BY genre",
            "SORT UnreadCount DESC",
            "```",
        ],
    )

    author_counts: dict[str, int] = {}
    for book in library.books:
        name = (book.composer or book.author or "Unknown").strip() or "Unknown"
        author_counts[name] = author_counts.get(name, 0) + 1
    sorted_authors = sorted(author_counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    total_items = max(len(library.books), 1)
    concentration = sum((count / total_items) ** 2 for _, count in sorted_authors)

    write_note(
        dirs["analysis"] / "Author Concentration.md",
        "Smart Analysis: Author Concentration",
        note_meta("analysis"),
        [
            f"- Concentration index (HHI): `{round(concentration, 4)}`",
            f"- Unique authors/composers: `{len(sorted_authors)}`",
            "",
            "### Top Authors / Composers",
            *(f"- {name}: {count} items" for name, count in sorted_authors[:15]),
            "",
            "### Dataview Query",
            "```dataview",
            "TABLE WITHOUT ID author AS Author, length(rows) AS Count",
            'FROM "Alexandria/Books" OR "Alexandria/Sheet Music"',
            "GROUP BY author",
            "SORT Count DESC",
            "```",
        ],
    )

    report_path = dirs["reports"] / "Sync Report.md"
    target_paths.add(report_path.resolve())

    for stale_path in sorted(existing_markdown_files):
        if stale_path in target_paths:
            continue
        if not _path_within(managed_root, stale_path):
            continue
        if not _is_alexandria_managed_note(stale_path):
            continue
        try:
            stale_path.unlink()
            changes["removed"].append(stale_path)
        except OSError:
            continue

    _cleanup_empty_dirs(managed_root)

    def format_rel_paths(paths: list[Path], limit: int = 30) -> list[str]:
        if not paths:
            return ["- (none)"]
        rel_paths = []
        for path in sorted(paths):
            try:
                rel_paths.append(path.relative_to(managed_root).as_posix())
            except ValueError:
                rel_paths.append(str(path))
        lines = [f"- `{entry}`" for entry in rel_paths[:limit]]
        if len(rel_paths) > limit:
            lines.append(f"- ... +{len(rel_paths) - limit} more")
        return lines

    type_counts: dict[str, int] = {}
    for book in library.books:
        type_counts[book.item_type] = type_counts.get(book.item_type, 0) + 1
    tag_counts: dict[str, int] = {}
    for item_id in item_by_id:
        for tag in item_tags.get(item_id, []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    top_author_counts = sorted(author_counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    top_tag_counts = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    author_summary_lines = [f"- {name}: {count}" for name, count in top_author_counts[:20]] or ["- (none)"]
    tag_summary_lines = [f"- {name}: {count}" for name, count in top_tag_counts[:25]] or ["- (none)"]
    type_summary_lines = [f"- {name}: {count}" for name, count in sorted(type_counts.items(), key=lambda item: item[0].casefold())] or ["- (none)"]

    report_lines = [
        f"- Generated: `{generated_at}`",
        f"- Vault: `{vault_root}`",
        f"- Managed root: `{managed_root}`",
        f"- Notes added: `{len(changes['added'])}`",
        f"- Notes updated: `{len(changes['updated'])}`",
        f"- Notes removed: `{len(changes['removed'])}`",
        f"- Notes unchanged: `{len(changes['unchanged'])}`",
        f"- Legacy Alexandria roots removed: `{len(legacy_roots_removed)}`",
        f"- Genre/tag overlaps filtered from tags: `{overlap_tags_filtered}`",
        "",
        "### Added Notes",
        *format_rel_paths(changes["added"]),
        "",
        "### Updated Notes",
        *format_rel_paths(changes["updated"]),
        "",
        "### Removed Notes",
        *format_rel_paths(changes["removed"]),
        "",
        "### Removed Legacy Roots",
        *([f"- `{path}`" for path in legacy_roots_removed] if legacy_roots_removed else ["- (none)"]),
        "",
        "### Totals by Type",
        *type_summary_lines,
        "",
        "### Totals by Author",
        *author_summary_lines,
        "",
        "### Totals by Tag",
        *tag_summary_lines,
    ]
    report_status = _write_managed_note(
        report_path,
        "Sync Report",
        note_meta("report"),
        report_lines,
    )

    note_index_path = dirs["meta"] / OBSIDIAN_NOTE_INDEX_FILE
    note_index_payload = {
        "generated_at": generated_at,
        "vault_root": str(vault_root),
        "managed_root": str(managed_root),
        "items": {item_id: rel(path) for item_id, path in sorted(item_note_path.items(), key=lambda entry: entry[0].casefold())},
    }
    note_index_status = _write_text_file(
        note_index_path,
        json.dumps(note_index_payload, indent=2, ensure_ascii=False) + "\n",
    )

    template_book_path = dirs["templates"] / "Book Template.md"
    template_book_text = """---
alexandria_schema: alexandria.v2
managed_by: alexandria
type: book
title: "{{title}}"
author: "{{author}}"
language: "{{language}}"
genre: "{{genre}}"
genres: []
tags: []
rating: null
progress: 0
read: false
location: "{{location}}"
updated_at: "{{updated_at}}"
---

# {{title}}

## Metadata
<!-- ALEXANDRIA:START -->
- ID: `{{alexandria_id}}`
- Type: `Book`
- Author: {{author}}
- Language: {{language}}
- Genre: {{genre}}
- Rating: `{{rating}}`
- Progress: `{{progress}}`
- Location: {{location}}
<!-- ALEXANDRIA:END -->

## Connections
Add manual wiki links to related ideas.

## Analysis
Write your analysis here.

## Notes
Write your notes here.
"""
    template_book_status = _write_text_file(template_book_path, template_book_text.rstrip() + "\n")
    target_paths.add(template_book_path.resolve())
    changes[template_book_status].append(template_book_path.resolve())

    template_sheet_path = dirs["templates"] / "Sheet Music Template.md"
    template_sheet_text = """---
alexandria_schema: alexandria.v2
managed_by: alexandria
type: sheet_music
title: "{{title}}"
creator: "{{composer}}"
author: "{{author}}"
composer: "{{composer}}"
language: "{{language}}"
genre: "{{genre}}"
genres: []
tags: []
rating: null
progress: 0
read: false
location: "{{location}}"
updated_at: "{{updated_at}}"
---

# {{title}}

## Metadata
<!-- ALEXANDRIA:START -->
- ID: `{{alexandria_id}}`
- Type: `SheetMusic`
- Composer: {{composer}}
- Instrumentation: {{instrumentation}}
- Language: {{language}}
- Genre: {{genre}}
- Rating: `{{rating}}`
- Progress: `{{progress}}`
- Location: {{location}}
<!-- ALEXANDRIA:END -->

## Connections
Add manual wiki links to related ideas.

## Analysis
Write your analysis here.

## Notes
Write your notes here.
"""
    template_sheet_status = _write_text_file(template_sheet_path, template_sheet_text.rstrip() + "\n")
    target_paths.add(template_sheet_path.resolve())
    changes[template_sheet_status].append(template_sheet_path.resolve())

    core_plugins_status = _configure_obsidian_core_plugins(vault_root)
    templates_cfg_status = _configure_obsidian_templates(vault_root, f"{OBSIDIAN_MANAGED_DIR}/Templates")
    graph_cfg_status = _configure_obsidian_graph(vault_root)
    workspace_status = _configure_obsidian_workspace(
        vault_root,
        "Alexandria/Dashboards/GUI Home.md",
        'path:"Alexandria" [read: false]',
    )
    bookmarks_status = _configure_obsidian_bookmarks(
        vault_root,
        [
            ("GUI Home", "Alexandria/Dashboards/GUI Home.md"),
            ("Saved Searches", "Alexandria/Dashboards/Saved Searches.md"),
            ("MOC Library", "Alexandria/MOC/Library.md"),
            ("MOC Authors", "Alexandria/MOC/Authors.md"),
            ("MOC Genres", "Alexandria/MOC/Genres.md"),
            ("MOC Tags", "Alexandria/MOC/Tags.md"),
            ("Base All Items", "Alexandria/Bases/All Items.base"),
            ("Base Unread", "Alexandria/Bases/Unread.base"),
            ("Base Top Rated", "Alexandria/Bases/Top Rated.base"),
        ],
    )

    snippet_css = """/* Alexandria Obsidian snippet */
.workspace-split.mod-root .view-content {
  line-height: 1.55;
}

.markdown-preview-view h1,
.markdown-source-view.mod-cm6 .cm-header-1 {
  letter-spacing: 0.01em;
}

.markdown-preview-view h2,
.markdown-source-view.mod-cm6 .cm-header-2 {
  border-bottom: 1px solid var(--background-modifier-border);
  padding-bottom: 0.2em;
}

.markdown-preview-view ul li {
  margin: 0.15rem 0;
}

.markdown-preview-view code {
  border-radius: 4px;
  padding: 0.1em 0.35em;
}
"""
    snippet_path = vault_root / OBSIDIAN_SNIPPET_REL_PATH
    snippet_status = _write_text_file(snippet_path, snippet_css.rstrip() + "\n")

    return {
        "vault_root": str(vault_root),
        "managed_root": str(managed_root),
        "items": len(item_by_id),
        "books": len(book_ids),
        "sheet_music": len(sheet_ids),
        "authors": len(author_note_path),
        "genres": len(genre_note_path),
        "tags": len(tag_note_path),
        "added": len(changes["added"]),
        "updated": len(changes["updated"]),
        "removed": len(changes["removed"]),
        "unchanged": len(changes["unchanged"]),
        "report_status": report_status,
        "note_index_status": note_index_status,
        "snippet_status": snippet_status,
        "template_book_status": template_book_status,
        "template_sheet_status": template_sheet_status,
        "core_plugins_status": core_plugins_status,
        "templates_cfg_status": templates_cfg_status,
        "graph_cfg_status": graph_cfg_status,
        "workspace_status": workspace_status,
        "bookmarks_status": bookmarks_status,
        "report_path": str(report_path),
        "snippet_path": str(snippet_path),
        "legacy_roots_removed": len(legacy_roots_removed),
        "overlap_tags_filtered": overlap_tags_filtered,
    }


def export_obsidian_flow(
    library: Library,
    data_file: Path,
    path_hint: str | None,
    action_name: str = "Obsidian export",
) -> None:
    vault_path = _resolve_obsidian_vault_path(path_hint, data_file, prompt_if_missing=True)
    if vault_path is None:
        print_result(action_name, "Canceled")
        return

    try:
        with spinner(f"{action_name} in progress"):
            summary = _write_obsidian_vault(library, vault_path)
    except OSError as exc:
        print_result(action_name, "Failed", str(exc))
        return

    try:
        _store_obsidian_vault_path(data_file, Path(summary["vault_root"]))
    except OSError as exc:
        print_status(f"Saved vault, but could not persist default vault path ({exc}).", "warn")

    print_result(
        action_name,
        "Saved",
        (
            f"{summary['items']} items, notes +{summary['added']} ~{summary['updated']} -{summary['removed']} "
            f"(legacy roots removed={summary['legacy_roots_removed']}, tag/genre overlaps filtered={summary['overlap_tags_filtered']}) "
            f"-> {summary['managed_root']}"
        ),
    )


def _open_obsidian_vault(vault_path: Path) -> tuple[bool, str]:
    resolved = vault_path.expanduser().resolve()
    if not resolved.exists():
        return False, f"Vault path does not exist: {resolved}"

    commands: list[list[str]] = []
    system_name = platform.system().lower()
    if system_name == "darwin":
        commands.append(["open", "-a", "Obsidian", str(resolved)])
    elif system_name == "windows":
        commands.append(["cmd", "/c", "start", "", str(resolved)])
    else:
        uri = f"obsidian://open?path={quote(str(resolved))}"
        try:
            if webbrowser.open(uri):
                return True, "Opened via obsidian:// URI"
        except Exception:
            pass
        if shutil.which("obsidian"):
            commands.append(["obsidian", str(resolved)])
        if shutil.which("xdg-open"):
            commands.append(["xdg-open", str(resolved)])

    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return True, f"Opened with: {' '.join(command[:2])}"

    return False, "Could not launch Obsidian automatically"


def _launch_uri(uri: str) -> bool:
    system_name = platform.system().lower()
    commands: list[list[str]] = []
    if system_name == "darwin":
        commands.append(["open", uri])
    elif system_name == "windows":
        commands.append(["cmd", "/c", "start", "", uri])
    else:
        if shutil.which("xdg-open"):
            commands.append(["xdg-open", uri])
        if shutil.which("obsidian"):
            commands.append(["obsidian", uri])

    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return True
    if system_name in {"darwin", "windows"}:
        return False
    try:
        return bool(webbrowser.open(uri))
    except Exception:
        return False


def _open_obsidian_note(note_path: Path) -> tuple[bool, str]:
    resolved = note_path.expanduser().resolve()
    if not resolved.exists():
        return False, f"Note does not exist: {resolved}"
    uri = f"obsidian://open?path={quote(str(resolved))}"
    if _launch_uri(uri):
        return True, "Opened note via obsidian://"
    return False, "Could not launch Obsidian URI for note"


def _resolve_obsidian_note_for_reference(library: Library, vault_path: Path, reference: str) -> tuple[Path | None, str]:
    book = resolve_book_reference(library, reference)
    if not book:
        return None, "Item not found. Use ID/ISBN/title/author/composer."
    if not book.book_id:
        return None, "Item has no ID. Run a sync first."

    payload = _load_note_index(vault_path)
    if payload and isinstance(payload.get("items"), dict):
        items = payload["items"]
        direct = items.get(book.book_id)
        if direct:
            candidate = (vault_path.expanduser().resolve() / str(direct)).resolve()
            if candidate.exists():
                return candidate, ""
        key = book.book_id.casefold()
        for item_id, rel_path in items.items():
            if str(item_id).casefold() == key:
                candidate = (vault_path.expanduser().resolve() / str(rel_path)).resolve()
                if candidate.exists():
                    return candidate, ""

    folder = "Sheet Music" if book.item_type == "SheetMusic" else "Books"
    fallback = vault_path.expanduser().resolve() / OBSIDIAN_MANAGED_DIR / folder / f"{book.book_id}.md"
    if fallback.exists():
        return fallback, ""
    return None, "Managed note was not found. Run: obsidian sync"


def obsidian_doctor_flow(data_file: Path, path_hint: str | None = None) -> None:
    vault_path = _resolve_obsidian_vault_path(path_hint, data_file, prompt_if_missing=False)
    if vault_path is None:
        print_status("No vault configured. Use: export obsidian <vault_path>", "warn")
        return

    resolved = vault_path.expanduser().resolve()
    rows: list[list[str]] = []
    has_error = False

    if resolved.exists() and resolved.is_dir():
        rows.append(["vault path", "OK", str(resolved)])
    elif resolved.exists():
        rows.append(["vault path", "ERROR", f"Path exists but is not a directory: {resolved}"])
        has_error = True
    else:
        rows.append(["vault path", "WARN", f"Directory does not exist yet: {resolved}"])

    write_ok = False
    if resolved.exists() and resolved.is_dir():
        probe = resolved / ".alexandria_doctor_write_probe"
        try:
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink(missing_ok=True)
            write_ok = True
            rows.append(["write access", "OK", "Vault root is writable"])
        except OSError as exc:
            rows.append(["write access", "ERROR", f"Cannot write to vault root: {exc}"])
            has_error = True
    else:
        rows.append(["write access", "WARN", "Skipped (vault directory missing)"])

    required_folders = [
        Path(OBSIDIAN_MANAGED_DIR),
        Path(OBSIDIAN_MANAGED_DIR) / "Books",
        Path(OBSIDIAN_MANAGED_DIR) / "Sheet Music",
        Path(OBSIDIAN_MANAGED_DIR) / "Bases",
        Path(OBSIDIAN_MANAGED_DIR) / "Templates",
        Path(OBSIDIAN_MANAGED_DIR) / "Dashboards",
        Path(OBSIDIAN_MANAGED_DIR) / "MOC",
        Path(OBSIDIAN_MANAGED_DIR) / "Analysis",
        Path(OBSIDIAN_MANAGED_DIR) / "Reports",
        Path(".obsidian") / "snippets",
    ]
    if resolved.exists() and resolved.is_dir():
        missing = [entry for entry in required_folders if not (resolved / entry).exists()]
        if missing:
            rows.append(
                [
                    "folders",
                    "WARN",
                    "Missing: " + ", ".join(str(entry) for entry in missing),
                ]
            )
        else:
            rows.append(["folders", "OK", "All required folders are present"])
    else:
        rows.append(["folders", "WARN", "Skipped (vault directory missing)"])

    required_files = [
        Path(OBSIDIAN_MANAGED_DIR) / "Dashboards" / "GUI Home.md",
        Path(OBSIDIAN_MANAGED_DIR) / "Dashboards" / "Saved Searches.md",
        Path(OBSIDIAN_MANAGED_DIR) / "Dashboards" / "Bookmarks.md",
        Path(OBSIDIAN_MANAGED_DIR) / "MOC" / "Genres.md",
        Path(OBSIDIAN_MANAGED_DIR) / "Bases" / "All Items.base",
        Path(".obsidian") / "templates.json",
        Path(".obsidian") / "bookmarks.json",
    ]
    if resolved.exists() and resolved.is_dir():
        missing_files = [entry for entry in required_files if not (resolved / entry).exists()]
        if missing_files:
            rows.append(
                [
                    "files",
                    "WARN",
                    "Missing: " + ", ".join(str(entry) for entry in missing_files),
                ]
            )
        else:
            rows.append(["files", "OK", "GUI files/config are present"])
    else:
        rows.append(["files", "WARN", "Skipped (vault directory missing)"])

    print(style("Obsidian Doctor", "bold"))
    print_table(rows, ["Check", "Status", "Details"], max_widths={"Check": 16, "Status": 8, "Details": 100})
    print()
    if has_error:
        print_result("Obsidian doctor", "Failed", "Fix errors above")
    elif write_ok:
        print_result("Obsidian doctor", "Done", "Vault looks healthy")
    else:
        print_result("Obsidian doctor", "Done", "Warnings only")


def obsidian_command_flow(raw_cmd: str, library: Library, data_file: Path) -> None:
    normalized = " ".join(raw_cmd.strip().lower().split())
    if normalized == "obsidian":
        configured = _load_obsidian_vault_path(data_file)
        if configured:
            print_status(f"Configured vault: {configured}", "info")
        else:
            print_status("No vault configured yet. Use: export obsidian <vault_path>", "info")
        print_status(
            "Usage: obsidian sync [vault_path] | obsidian doctor [vault_path] | obsidian open [book-id|vault_path]",
            "info",
        )
        return

    if normalized.startswith("obsidian sync"):
        path_hint = _command_tail(raw_cmd, "obsidian sync")
        export_obsidian_flow(library, data_file, path_hint or None, action_name="Obsidian sync")
        return

    if normalized.startswith("obsidian doctor"):
        path_hint = _command_tail(raw_cmd, "obsidian doctor")
        obsidian_doctor_flow(data_file, path_hint or None)
        return

    if normalized.startswith("obsidian open"):
        path_hint = _command_tail(raw_cmd, "obsidian open")
        if path_hint and _looks_like_path(path_hint):
            vault_path = Path(path_hint).expanduser()
            opened, detail = _open_obsidian_vault(vault_path)
            if opened:
                print_result("Obsidian open", "Done", detail)
            else:
                print_result("Obsidian open", "Failed", detail)
            return

        if path_hint:
            vault_path = _resolve_obsidian_vault_path(None, data_file, prompt_if_missing=False)
            if vault_path is None:
                print_status("No vault configured. Use: export obsidian <vault_path>", "warn")
                return
            note_path, error = _resolve_obsidian_note_for_reference(library, vault_path, path_hint)
            if note_path is None:
                print_result("Obsidian open", "Failed", error)
                return
            opened, detail = _open_obsidian_note(note_path)
            if opened:
                print_result("Obsidian open", "Done", f"{detail} ({note_path.name})")
            else:
                print_result("Obsidian open", "Failed", detail)
            return

        vault_path = _resolve_obsidian_vault_path(None, data_file, prompt_if_missing=False)
        if vault_path is None:
            print_status("No vault configured. Use: export obsidian <vault_path>", "warn")
            return
        opened, detail = _open_obsidian_vault(vault_path)
        if opened:
            print_result("Obsidian open", "Done", detail)
        else:
            print_result("Obsidian open", "Failed", detail)
        return

    print_status(
        "Usage: obsidian sync [vault_path] | obsidian doctor [vault_path] | obsidian open [book-id|vault_path]",
        "warn",
    )


def export_command_flow(raw_cmd: str, library: Library, data_file: Path) -> None:
    normalized = " ".join(raw_cmd.strip().lower().split())
    if normalized == "export":
        export_flow(library, data_file)
        return
    if normalized.startswith("export obsidian"):
        path_hint = _command_tail(raw_cmd, "export obsidian")
        export_obsidian_flow(library, data_file, path_hint or None, action_name="Obsidian export")
        return
    print_status("Usage: export | export obsidian <vault_path>", "warn")


def print_summary(library):
    total = len(library.books)
    read_count = sum(1 for book in library.books if book.read)
    reading_list_count = len(library.reading_list)
    print_status(f"Loaded {total} items | Read: {read_count} | Reading list: {reading_list_count}", "ok")


def print_dashboard(library: Library) -> None:
    stats = library.stats()
    active_goals = int(bool(stats.get("monthly_goal"))) + int(bool(stats.get("yearly_goal")))
    lines = [
        "Dashboard",
        f"Total items : {stats['total']}",
        f"Unread      : {stats['unread']}",
        f"Reading list: {stats['reading_list']}",
        f"Active goals: {active_goals}",
        f"Interests   : {'active' if stats.get('recommendation_profile_active') else 'not set'}",
    ]
    width = max(len(line) for line in lines)
    print(themed("┌" + ("─" * (width + 2)) + "┐", "accent"))
    for line in lines:
        print(themed(f"│ {line.ljust(width)} │", "accent"))
    print(themed("└" + ("─" * (width + 2)) + "┘", "accent"))
    print()


def _print_detail_block(label: str, value: str | None) -> None:
    print(f"  {label}:")
    text = str(value or "").strip()
    if not text:
        print("    -")
        return
    for line in text.splitlines():
        print(f"    {line}")


def print_book_details(book: Book) -> None:
    print(themed("Item Details", "accent", bold=True))
    print(f"  ID:        {book.book_id or '-'}")
    print(f"  Type:      {book.item_type}")
    print(f"  Title:     {book.title}")
    print(f"  Author:    {book.author}")
    if book.item_type == "SheetMusic":
        print(f"  Composer:  {book.composer or book.author}")
        print(f"  Instr.:    {book.instrumentation or '-'}")
        print(f"  Catalog:   {book.catalog_number or '-'}")
        print(f"  Key:       {book.key_signature or '-'}")
        print(f"  Era/Style: {book.era_style or '-'}")
        print(f"  Difficulty:{' ' + (book.difficulty or '-')}")
        print(f"  Duration:  {str(book.duration_minutes) + ' min' if book.duration_minutes is not None else '-'}")
        print(f"  Publisher: {book.publisher or '-'}")
        print(f"  Practice:  {book.practice_status or '-'}")
        print(f"  Last prac: {book.last_practiced or '-'}")
        print(f"  Tempo tgt: {book.tempo_target_bpm if book.tempo_target_bpm is not None else '-'}")
        print(f"  Practiced: {str(book.practice_minutes_total) + ' min' if book.practice_minutes_total is not None else '-'}")
    print(f"  ISBN:      {book.isbn or '-'}")
    print(f"  Year:      {book.year if book.year is not None else '-'}")
    print(f"  Genre:     {book.genre or '-'}")
    print(f"  Language:  {book.language}")
    print(f"  Cover:     {book.cover}")
    print(f"  Pages:     {book.pages if book.pages is not None else '-'}")
    print(f"  Progress:  {book.progress_label()}")
    print(f"  Rating:    {book.rating if book.rating is not None else '-'}")
    print(f"  Read:      {'yes' if book.read else 'no'}")
    print(f"  Location:  {book.location}")
    print(f"  Series:    {book.series_name or '-'}")
    print(f"  Series #:  {book.series_index if book.series_index is not None else '-'}")
    print(f"  Tags:      {', '.join(book.tags) if book.tags else '-'}")
    print(f"  AI Tags:   {', '.join(book.ai_tags) if book.ai_tags else '-'}")
    print(f"  Finished:  {book.read_at or '-'}")
    _print_detail_block("AI Summary", book.ai_summary)
    _print_detail_block("AI Author", book.ai_author_note)
    _print_detail_block("Notes", book.notes)
    print()


def print_interest_profile(profile: dict[str, object]) -> None:
    genres = ", ".join(profile.get("genres", [])) or "-"
    tags = ", ".join(profile.get("tags", [])) or "-"
    authors = ", ".join(profile.get("authors", [])) or "-"
    min_rating = profile.get("min_rating")
    location = profile.get("location") or "any"
    prefer_unread = "yes" if profile.get("prefer_unread", True) else "no"

    print(themed("Smart Interests", "accent", bold=True))
    print(f"  Genres:        {genres}")
    print(f"  Tags:          {tags}")
    print(f"  Authors:       {authors}")
    print(f"  Min rating:    {min_rating if min_rating is not None else '-'}")
    print(f"  Location:      {location}")
    print(f"  Prefer unread: {prefer_unread}")
    print()


def interests_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    cmd = raw_cmd.strip().lower()
    profile = library.get_recommendation_profile()

    if cmd == "interests show":
        print_interest_profile(profile)
        return

    if cmd == "interests clear":
        snapshot = library.export_state()
        try:
            changed = library.clear_recommendation_profile()
        except StorageError as exc:
            print_result("Interests", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Interests", "Updated", "Cleared")
        else:
            print_result("Interests", "No change")
        return

    if cmd != "interests set":
        print_status("Usage: interests set | interests show | interests clear", "warn")
        return

    print(style("Set smart interests (blank keeps current, 'none' clears field)", "bold"))

    def ask_list(label: str, current: list[str], parser) -> list[str]:
        current_text = ", ".join(current) if current else "-"
        value = input(f"{label} [{current_text}]: ").strip()
        if value.lower() == "cancel":
            return CANCELED
        if value == "":
            return current
        if value.lower() == "none":
            return []
        return parser(value)

    def ask_min_rating(current: int | None) -> int | None | object:
        while True:
            current_text = str(current) if current is not None else "-"
            value = input(f"Minimum rating 1-5 [{current_text}]: ").strip().lower()
            if value == "cancel":
                return CANCELED
            if value == "":
                return current
            if value in {"none", "any", "*"}:
                return None
            try:
                number = int(value)
            except ValueError:
                print_status(format_hint("Invalid minimum rating", "1 to 5 | none"), "warn")
                continue
            if not (1 <= number <= 5):
                print_status(format_hint("Invalid minimum rating", "1 to 5"), "warn")
                continue
            return number

    def ask_location(current: str | None) -> str | None | object:
        while True:
            current_text = current if current else "any"
            value = input(f"Preferred location (Pforta/Zuhause/any) [{current_text}]: ").strip()
            if value.lower() == "cancel":
                return CANCELED
            if value == "":
                return current
            parsed = parse_optional_location(value)
            if parsed is None and value.strip().lower() not in {"", "any", "*"}:
                print_status(format_hint("Invalid location", "Pforta | Zuhause | any"), "warn")
                continue
            return parsed

    def ask_prefer_unread(current: bool) -> bool | object:
        while True:
            current_text = "yes" if current else "no"
            value = input(f"Prefer unread books? (y/n) [{current_text}]: ").strip().lower()
            if value == "cancel":
                return CANCELED
            if value == "":
                return current
            if value in YES_VALUES:
                return True
            if value in {"n", "no"}:
                return False
            print_status(format_hint("Invalid choice", "y | n"), "warn")

    genres = ask_list("Genres (comma-separated)", list(profile.get("genres", [])), parse_keywords)
    tags = ask_list("Tags (comma-separated)", list(profile.get("tags", [])), parse_tags)
    authors = ask_list("Authors (comma-separated)", list(profile.get("authors", [])), parse_keywords)
    min_rating = ask_min_rating(profile.get("min_rating"))
    location = ask_location(profile.get("location"))
    prefer_unread = ask_prefer_unread(bool(profile.get("prefer_unread", True)))

    values = [genres, tags, authors, min_rating, location, prefer_unread]
    if any(value is CANCELED for value in values):
        print_result("Interests", "Canceled")
        return

    new_profile = {
        "genres": genres,
        "tags": tags,
        "authors": authors,
        "min_rating": min_rating,
        "location": location,
        "prefer_unread": prefer_unread,
    }

    snapshot = library.export_state()
    try:
        changed = library.set_recommendation_profile(new_profile)
    except (StorageError, ValueError) as exc:
        print_result("Interests", "Failed", str(exc))
        return
    if changed:
        push_undo(undo_stack, snapshot)
        print_result("Interests", "Saved")
    else:
        print_result("Interests", "No change")


def reading_smart_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    cmd = " ".join(raw_cmd.strip().lower().split())
    parts = cmd.split()
    if len(parts) < 3:
        print_status("Usage: reading smart preview|generate|append [count]", "warn")
        return

    mode = parts[2]
    count_text = parts[3] if len(parts) > 3 else ""
    try:
        count = parse_positive_int_arg(count_text, default=10)
    except ValueError as exc:
        print_status(str(exc), "warn")
        return

    if mode == "preview":
        try:
            books = library.recommended_books(limit=count, include_existing_reading=False)
        except ValueError as exc:
            print_status(str(exc), "warn")
            return
        if not books:
            print_status("No recommendations yet. Try: interests set", "info")
            return
        print_books(books, f"Smart Reading Preview (Top {len(books)})")
        return

    if mode not in {"generate", "append"}:
        print_status("Usage: reading smart preview|generate|append [count]", "warn")
        return

    snapshot = library.export_state()
    try:
        result = library.apply_recommended_reading_list(
            limit=count,
            mode="replace" if mode == "generate" else "append",
        )
    except (StorageError, ValueError) as exc:
        print_result("Reading smart", "Failed", str(exc))
        return

    if result["changed"]:
        push_undo(undo_stack, snapshot)
        print_result(
            "Reading smart",
            "Updated",
            f"mode={result['mode']}, added={result['added']}, removed={result['removed']}, total={result['total']}",
        )
    else:
        print_result("Reading smart", "No change")

    books = result.get("books", [])
    if books:
        print_books(books, f"Smart Recommendations Used ({len(books)})")


def choose_backup_path(data_file: Path) -> Path:
    backup_dir = data_file.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return backup_dir / f"library_backup_{stamp}.json"


def latest_backup_path(data_file: Path) -> Path | None:
    backup_dir = data_file.parent / "backups"
    backups = sorted(backup_dir.glob("library_backup_*.json"))
    return backups[-1] if backups else None


def export_csv(path: Path, library: Library, show_progress: bool = False):
    fieldnames = [
        "book_id",
        "item_type",
        "title",
        "author",
        "composer",
        "instrumentation",
        "catalog_number",
        "key_signature",
        "era_style",
        "difficulty",
        "duration_minutes",
        "publisher",
        "practice_status",
        "last_practiced",
        "year",
        "isbn",
        "genre",
        "language",
        "cover",
        "pages",
        "read",
        "read_at",
        "notes",
        "rating",
        "progress_pages",
        "location",
        "tags",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        total = len(library.books)
        last_percent = -1
        for index, book in enumerate(library.books, 1):
            writer.writerow(book.to_dict())
            if show_progress and total >= 200:
                last_percent = update_progress("Export", index, total, last_percent)
        if show_progress and total >= 200:
            end_progress()


def load_books_from_csv(path: Path, show_progress: bool = False):
    books = []
    invalid = 0
    total_rows = 0
    if show_progress:
        try:
            with path.open("r", encoding="utf-8") as counter:
                total_rows = max(sum(1 for _ in counter) - 1, 0)
        except OSError:
            total_rows = 0
    last_percent = -1
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, 1):
            normalized = {(key or "").strip().lower(): value for key, value in row.items()}
            payload = {
                "book_id": normalized.get("book_id", ""),
                "item_type": normalized.get("item_type", "Book"),
                "title": normalized.get("title", ""),
                "author": normalized.get("author", ""),
                "composer": normalized.get("composer", ""),
                "instrumentation": normalized.get("instrumentation", ""),
                "catalog_number": normalized.get("catalog_number", ""),
                "key_signature": normalized.get("key_signature", ""),
                "era_style": normalized.get("era_style", ""),
                "difficulty": normalized.get("difficulty", ""),
                "duration_minutes": normalized.get("duration_minutes"),
                "publisher": normalized.get("publisher", ""),
                "practice_status": normalized.get("practice_status", ""),
                "last_practiced": normalized.get("last_practiced"),
                "year": normalized.get("year"),
                "isbn": normalized.get("isbn", ""),
                "genre": normalized.get("genre", ""),
                "language": normalized.get("language", "English"),
                "cover": normalized.get("cover", "Softcover"),
                "pages": normalized.get("pages"),
                "read": normalized.get("read"),
                "read_at": normalized.get("read_at"),
                "notes": normalized.get("notes", ""),
                "rating": normalized.get("rating"),
                "progress_pages": normalized.get("progress_pages"),
                "location": normalized.get("location", "Zuhause"),
                "tags": normalized.get("tags", ""),
            }
            try:
                books.append(Book.from_dict(payload))
            except ValueError:
                invalid += 1
            if show_progress and total_rows >= 200:
                last_percent = update_progress("Import", index, total_rows, last_percent)
    if show_progress and total_rows >= 200:
        end_progress()
    return books, invalid


def fuzzy_find_books(library: Library, query: str) -> list[Book]:
    key = query.strip().casefold()
    if not key:
        return []
    matches = [
        book
        for book in library.books
        if key in book.title.casefold()
        or key in book.author.casefold()
        or key in (book.composer or "").casefold()
        or key in (book.instrumentation or "").casefold()
        or key in (book.isbn or "").casefold()
    ]
    matches.sort(key=lambda book: (book.title.casefold(), book.author.casefold()))
    return matches


def select_book_from_matches(matches: list[Book], query: str) -> Book | None:
    if not matches:
        return None
    if len(matches) == 1:
        chosen = matches[0]
        print_status(f"Resolved '{query}' to {chosen.book_id} ({chosen.title}).", "info")
        return chosen
    print_status(f"Found {len(matches)} matches for '{query}'. Select one:", "info")
    rows = [
        [
            str(i),
            book.book_id,
            "Sheet" if book.item_type == "SheetMusic" else "Book",
            truncate(book.title, 32),
            truncate(book.author, 24),
        ]
        for i, book in enumerate(matches[:12], 1)
    ]
    print_table(rows, ["#", "ID", "Type", "Title", "Author"])
    choice = input("Number (blank cancels): ").strip()
    if not choice:
        return None
    try:
        index = int(choice)
    except ValueError:
        print_status(format_hint("Invalid selection", "a row number from the table"), "warn")
        return None
    if not (1 <= index <= len(rows)):
        print_status(format_hint("Invalid selection", f"1 to {len(rows)}"), "warn")
        return None
    return matches[index - 1]


def resolve_book_reference(library: Library, raw_reference: str) -> Book | None:
    value = raw_reference.strip()
    if not value:
        return None
    exact = library.get_by_reference(value)
    if exact:
        return exact
    matches = fuzzy_find_books(library, value)
    return select_book_from_matches(matches, value)


def ask_book_reference(library: Library, prompt: str) -> Book | None:
    raw_reference = input(prompt).strip()
    if not raw_reference:
        return None
    return resolve_book_reference(library, raw_reference)


def add_book_flow(library: Library, undo_stack):
    print(style("Add a new item (book or sheet music). Type 'cancel' to abort.", "bold"))
    title = prompt_or_cancel("Title: ")
    if title is None or title == "":
        print_result("Add", "Canceled", "Missing title")
        return

    item_type_input = prompt_or_cancel(f"Type ({'/'.join(ALLOWED_ITEM_TYPES)}, default Book): ")
    if item_type_input is None:
        print_result("Add", "Canceled")
        return
    item_type = "Book" if not item_type_input else parse_item_type(item_type_input)
    if item_type is None:
        print_status(format_hint("Invalid type", " | ".join(ALLOWED_ITEM_TYPES)), "warn")
        return

    sheet_composer = ""
    sheet_instrumentation = ""
    sheet_catalog_number = ""
    sheet_key_signature = ""
    sheet_era_style = ""
    sheet_difficulty = ""
    sheet_duration_minutes: int | None = None
    sheet_publisher = ""
    sheet_practice_status = "Unstarted"

    if item_type == "SheetMusic":
        composer = prompt_or_cancel("Composer: ")
        if composer is None or composer == "":
            print_result("Add", "Canceled", "Missing composer")
            return
        author = composer
        sheet_composer = composer
        instrumentation = prompt_or_cancel("Instrumentation (optional, e.g. Piano solo): ")
        if instrumentation is None:
            print_result("Add", "Canceled")
            return
        sheet_instrumentation = instrumentation or ""
        catalog_number = prompt_or_cancel("Catalog/work number (optional, e.g. BWV 846): ")
        if catalog_number is None:
            print_result("Add", "Canceled")
            return
        sheet_catalog_number = catalog_number or ""
        key_signature = prompt_or_cancel("Key signature (optional): ")
        if key_signature is None:
            print_result("Add", "Canceled")
            return
        sheet_key_signature = key_signature or ""
        era_style = prompt_or_cancel("Era/style (optional): ")
        if era_style is None:
            print_result("Add", "Canceled")
            return
        sheet_era_style = era_style or ""
        difficulty = prompt_or_cancel("Difficulty (optional, e.g. Beginner/Advanced): ")
        if difficulty is None:
            print_result("Add", "Canceled")
            return
        sheet_difficulty = difficulty or ""
        duration = get_optional_int("Duration in minutes (optional): ")
        if duration is CANCELED:
            print_result("Add", "Canceled")
            return
        if duration is not None and duration < 0:
            print_status(format_hint("Invalid duration", "a non-negative number"), "warn")
            return
        sheet_duration_minutes = duration
        publisher = prompt_or_cancel("Publisher/Edition (optional): ")
        if publisher is None:
            print_result("Add", "Canceled")
            return
        sheet_publisher = publisher or ""
        practice_input = prompt_or_cancel(
            f"Practice status ({'/'.join(ALLOWED_PRACTICE_STATUSES)}, default Unstarted): "
        )
        if practice_input is None:
            print_result("Add", "Canceled")
            return
        if practice_input:
            parsed_practice = parse_practice_status(practice_input)
            if parsed_practice is None:
                print_status(
                    format_hint(
                        "Invalid practice status",
                        " | ".join(ALLOWED_PRACTICE_STATUSES),
                    ),
                    "warn",
                )
                return
            sheet_practice_status = parsed_practice
    else:
        author = prompt_or_cancel("Author: ")
        if author is None or author == "":
            print_result("Add", "Canceled", "Missing author")
            return

    year = get_optional_int("Year (optional): ")
    if year is CANCELED:
        print_result("Add", "Canceled")
        return

    isbn = prompt_or_cancel("ISBN (optional but recommended): ")
    if isbn is None:
        print_result("Add", "Canceled")
        return
    isbn = isbn or ""

    genre = prompt_or_cancel("Genre (optional): ")
    if genre is None:
        print_result("Add", "Canceled")
        return
    genre = genre or ""

    language_input = prompt_or_cancel(
        f"Language ({'/'.join(ALLOWED_LANGUAGES)}, default English): "
    )
    if language_input is None:
        print_result("Add", "Canceled")
        return
    if not language_input:
        language = "English"
    else:
        language = parse_language(language_input)
        if language is None:
            print_status(format_hint("Invalid language", "German | English | French | Japanese"), "warn")
            return

    cover_input = prompt_or_cancel(f"Cover ({'/'.join(ALLOWED_COVERS)}, default Softcover): ")
    if cover_input is None:
        print_result("Add", "Canceled")
        return
    if not cover_input:
        cover = "Softcover"
    else:
        cover = parse_cover(cover_input)
        if cover is None:
            print_status(format_hint("Invalid cover", "Hardcover | Softcover"), "warn")
            return

    pages = get_optional_int("Pages (optional): ")
    if pages is CANCELED:
        print_result("Add", "Canceled")
        return

    progress = get_optional_int("Current page progress (optional): ")
    if progress is CANCELED:
        print_result("Add", "Canceled")
        return
    if progress is not None and progress < 0:
        print_status(format_hint("Invalid progress", "a non-negative number"), "warn")
        return
    if pages is not None and progress is not None and progress > pages:
        print_status(format_hint("Invalid progress", f"0 to {pages}"), "warn")
        return

    read_input = prompt_or_cancel("Mark as read? (y/n, optional): ")
    if read_input is None:
        print_result("Add", "Canceled")
        return
    read = str(read_input).strip().lower() in YES_VALUES

    rating = get_optional_int("Rating 1-5 (optional): ")
    if rating is CANCELED:
        print_result("Add", "Canceled")
        return
    if rating is not None and not (1 <= rating <= 5):
        print_status(format_hint("Invalid rating", "1 to 5"), "warn")
        return

    location_input = prompt_or_cancel("Location (Pforta/Zuhause, default Zuhause): ")
    if location_input is None:
        print_result("Add", "Canceled")
        return
    if not location_input:
        location = "Zuhause"
    else:
        location = parse_location(location_input)
        if location is None:
            print_status(format_hint("Invalid location", "Pforta | Zuhause"), "warn")
            return

    tags_input = prompt_or_cancel("Tags (optional, comma-separated): ")
    if tags_input is None:
        print_result("Add", "Canceled")
        return
    tags = parse_tags(tags_input)

    notes = prompt_or_cancel("Notes (optional): ")
    if notes is None:
        print_result("Add", "Canceled")
        return
    notes = notes or ""

    book = Book(
        title=title,
        author=author,
        year=year,
        isbn=isbn,
        genre=genre,
        language=language,
        cover=cover,
        pages=pages,
        read=read,
        notes=notes,
        rating=rating,
        progress_pages=progress,
        location=location,
        tags=tags,
        item_type=item_type,
        composer=sheet_composer,
        instrumentation=sheet_instrumentation,
        catalog_number=sheet_catalog_number,
        key_signature=sheet_key_signature,
        era_style=sheet_era_style,
        difficulty=sheet_difficulty,
        duration_minutes=sheet_duration_minutes,
        publisher=sheet_publisher,
        practice_status=sheet_practice_status,
    )
    snapshot = library.export_state()
    try:
        changed = library.add_book(book)
    except StorageError as exc:
        print_result("Add", "Failed", str(exc))
        return
    if changed:
        push_undo(undo_stack, snapshot)
        print_result("Add", "Saved", f"(ID: {book.book_id})")
    else:
        print_result("Add", "No change", "Duplicate ISBN or duplicate edition/signature")


def edit_book_flow(library: Library, undo_stack):
    current = ask_book_reference(library, "Item reference (ID/ISBN/title/author) to edit: ")
    if not current:
        print_status("Item not found or selection canceled.", "warn")
        return

    print_books([current], "Current Item Data")
    print(style("Press Enter to keep a value. Type 'none' to clear optional fields.", "dim"))

    def ask_text(label, current_value):
        value = input(f"{label} [{current_value if current_value else '-'}]: ").strip()
        if value.lower() == "cancel":
            return CANCELED
        if value == "":
            return current_value
        if value.lower() == "none":
            return ""
        return value

    def ask_optional_int(label, current_value):
        display = "-" if current_value is None else str(current_value)
        while True:
            value = input(f"{label} [{display}]: ").strip()
            if value.lower() == "cancel":
                return CANCELED
            if value == "":
                return current_value
            if value.lower() == "none":
                return None
            try:
                return int(value)
            except ValueError:
                print_status("Please enter an integer, none, or leave blank.", "warn")

    title = ask_text("Title", current.title)
    item_type_input = ask_text(f"Type ({'/'.join(ALLOWED_ITEM_TYPES)})", current.item_type)
    if item_type_input is CANCELED:
        print_result("Edit", "Canceled")
        return
    parsed_type = parse_item_type(str(item_type_input))
    if parsed_type is None:
        print_status(format_hint("Invalid type", " | ".join(ALLOWED_ITEM_TYPES)), "warn")
        return

    author = ask_text("Author", current.author)
    composer = current.composer
    instrumentation = current.instrumentation
    catalog_number = current.catalog_number
    key_signature = current.key_signature
    era_style = current.era_style
    difficulty = current.difficulty
    duration_minutes = current.duration_minutes
    publisher = current.publisher
    practice_status = current.practice_status

    if parsed_type == "SheetMusic":
        composer = ask_text("Composer", current.composer or current.author)
        instrumentation = ask_text("Instrumentation", current.instrumentation)
        catalog_number = ask_text("Catalog/work number", current.catalog_number)
        key_signature = ask_text("Key signature", current.key_signature)
        era_style = ask_text("Era/style", current.era_style)
        difficulty = ask_text("Difficulty", current.difficulty)
        duration_minutes = ask_optional_int("Duration in minutes", current.duration_minutes)
        publisher = ask_text("Publisher/Edition", current.publisher)
        practice_status_input = ask_text(
            f"Practice status ({'/'.join(ALLOWED_PRACTICE_STATUSES)})",
            current.practice_status or "Unstarted",
        )
        sheet_values = [
            composer,
            instrumentation,
            catalog_number,
            key_signature,
            era_style,
            difficulty,
            duration_minutes,
            publisher,
            practice_status_input,
        ]
        if any(value is CANCELED for value in sheet_values):
            print_result("Edit", "Canceled")
            return
        if practice_status_input:
            parsed_practice = parse_practice_status(practice_status_input)
            if parsed_practice is None:
                print_status(
                    format_hint(
                        "Invalid practice status",
                        " | ".join(ALLOWED_PRACTICE_STATUSES),
                    ),
                    "warn",
                )
                return
            practice_status = parsed_practice
        else:
            practice_status = "Unstarted"
    else:
        composer = ""
        instrumentation = ""
        catalog_number = ""
        key_signature = ""
        era_style = ""
        difficulty = ""
        duration_minutes = None
        publisher = ""
        practice_status = ""

    if parsed_type == "SheetMusic":
        if not composer:
            print_status("Composer is required for sheet music.", "warn")
            return
        author = composer

    year = ask_optional_int("Year", current.year)
    new_isbn = ask_text("ISBN", current.isbn)
    genre = ask_text("Genre", current.genre)
    language_input = ask_text("Language (German/English/French/Japanese)", current.language)
    cover_input = ask_text("Cover (Hardcover/Softcover)", current.cover)
    pages = ask_optional_int("Pages", current.pages)
    progress = ask_optional_int("Current progress pages", current.progress_pages)
    rating = ask_optional_int("Rating 1-5", current.rating)
    location_input = ask_text("Location (Pforta/Zuhause)", current.location)
    tags_input = ask_text("Tags (comma-separated)", ", ".join(current.tags))
    notes = ask_text("Notes", current.notes)

    values = [
        title,
        author,
        year,
        new_isbn,
        genre,
        language_input,
        cover_input,
        pages,
        progress,
        rating,
        location_input,
        tags_input,
        notes,
        composer,
        instrumentation,
        catalog_number,
        key_signature,
        era_style,
        difficulty,
        duration_minutes,
        publisher,
        practice_status,
    ]
    if any(value is CANCELED for value in values):
        print_result("Edit", "Canceled")
        return

    read_input = input(f"Read status [current: {'yes' if current.read else 'no'}] (y/n/blank keep): ").strip().lower()
    if read_input == "cancel":
        print_result("Edit", "Canceled")
        return
    if read_input in YES_VALUES:
        read_value = True
    elif read_input in {"n", "no"}:
        read_value = False
    elif read_input == "":
        read_value = current.read
    else:
        print_status(format_hint("Invalid read value", "y | n | blank"), "warn")
        return

    if rating is not None and not (1 <= rating <= 5):
        print_status(format_hint("Invalid rating", "1 to 5"), "warn")
        return
    if progress is not None and progress < 0:
        print_status(format_hint("Invalid progress", "a non-negative number"), "warn")
        return
    if pages is not None and progress is not None and progress > pages:
        print_status(format_hint("Invalid progress", f"0 to {pages}"), "warn")
        return
    if duration_minutes is not None and duration_minutes < 0:
        print_status(format_hint("Invalid duration", "a non-negative number"), "warn")
        return
    parsed_location = parse_location(str(location_input))
    if parsed_location is None:
        print_status(format_hint("Invalid location", "Pforta | Zuhause"), "warn")
        return
    parsed_cover = parse_cover(str(cover_input))
    if parsed_cover is None:
        print_status(format_hint("Invalid cover", "Hardcover | Softcover"), "warn")
        return
    parsed_language = parse_language(str(language_input))
    if parsed_language is None:
        print_status(format_hint("Invalid language", "German | English | French | Japanese"), "warn")
        return
    tags = parse_tags(tags_input) if tags_input else []

    snapshot = library.export_state()
    try:
        changed = library.edit_book(
            current.book_id,
            title=title,
            author=author,
            year=year,
            item_type=parsed_type,
            new_isbn=new_isbn,
            genre=genre,
            language=parsed_language,
            cover=parsed_cover,
            pages=pages,
            progress_pages=progress,
            rating=rating,
            location=parsed_location,
            read=read_value,
            tags=tags,
            notes=notes,
            composer=composer,
            instrumentation=instrumentation,
            catalog_number=catalog_number,
            key_signature=key_signature,
            era_style=era_style,
            difficulty=difficulty,
            duration_minutes=duration_minutes,
            publisher=publisher,
            practice_status=practice_status,
        )
    except (StorageError, ValueError) as exc:
        print_result("Edit", "Failed", str(exc))
        return
    if changed:
        push_undo(undo_stack, snapshot)
        print_result("Edit", "Updated", f"(ID: {current.book_id})")
    else:
        print_result("Edit", "No change", "Duplicate ISBN/signature or unchanged")


def list_command_flow(raw_cmd: str, library: Library):
    cmd = raw_cmd.strip().lower()
    if cmd == "list":
        print_books(library.books, "Library Collection")
        return
    if cmd == "list full":
        print_books(library.books, "Library Collection (Full)", compact=False)
        return
    if cmd == "list read":
        print_books(library.books_by_read_status(True), "Read Items")
        return
    if cmd == "list unread":
        print_books(library.books_by_read_status(False), "Unread Items")
        return
    if cmd == "list sheet":
        print_books(library.books_by_item_type("SheetMusic"), "Sheet Music")
        return
    if cmd.startswith("list genre"):
        parts = raw_cmd.split(maxsplit=2)
        genre = parts[2].strip() if len(parts) == 3 else ""
        if not genre:
            genre = input("Genre: ").strip()
        if not genre:
            print_status("Usage: list genre <name>", "warn")
            return
        print_books(library.books_by_genre(genre), f"Genre: {genre}")
        return
    if cmd.startswith("list language"):
        parts = raw_cmd.split(maxsplit=2)
        language = parts[2].strip() if len(parts) == 3 else ""
        if not language:
            language = input("Language (German/English/French/Japanese): ").strip()
        if not language:
            print_status("Usage: list language <name>", "warn")
            return
        parsed = parse_language(language)
        if parsed is None:
            print_status(format_hint("Invalid language", "German | English | French | Japanese"), "warn")
            return
        print_books(library.books_by_language(parsed), f"Language: {parsed}")
        return
    if cmd.startswith("list instrument"):
        parts = raw_cmd.split(maxsplit=2)
        instrument = parts[2].strip() if len(parts) == 3 else ""
        if not instrument:
            instrument = input("Instrumentation: ").strip()
        if not instrument:
            print_status("Usage: list instrument <name>", "warn")
            return
        print_books(library.sheets_by_instrumentation(instrument), f"Instrumentation: {instrument}")
        return
    if cmd.startswith("list tag"):
        parts = raw_cmd.split(maxsplit=2)
        tag = parts[2].strip() if len(parts) == 3 else ""
        if not tag:
            tag = input("Tag: ").strip()
        if not tag:
            print_status("Usage: list tag <name>", "warn")
            return
        print_books(library.books_by_tag(tag), f"Tag: {tag}")
        return
    print_status(
        "Usage: list | list full | list read | list unread | list sheet | list genre <name> | list language <name> | list instrument <name> | list tag <name>",
        "warn",
    )


def sort_command_flow(cmd: str, library: Library):
    parts = cmd.split(maxsplit=2)
    if len(parts) < 3 or parts[0] != "sort" or parts[1] != "by":
        print_status("Usage: sort by <title|author|type|year|pages|language>", "warn")
        return
    field = parts[2].strip()
    try:
        books = library.sorted_books(field)
    except ValueError as exc:
        print_status(str(exc), "warn")
        return
    print_books(books, f"Sorted by {field}")


def goal_command_flow(cmd: str, library: Library, undo_stack):
    if cmd in {"goal", "goal show"}:
        print_goals(library)
        return

    parts = cmd.split()
    if len(parts) >= 3 and parts[1] == "set":
        period = parts[2].strip().lower()
        if period not in {"monthly", "yearly"}:
            print_status("Goal period must be monthly or yearly.", "warn")
            return
        target = get_optional_int(f"{period.capitalize()} goal target (books): ")
        if target is CANCELED:
            print_status("Goal update canceled.", "warn")
            return
        if target is None or target <= 0:
            print_status("Goal target must be a positive integer.", "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.set_goal(period, target)
        except (StorageError, ValueError) as exc:
            print_status(f"Goal update failed: {exc}", "error")
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_status(f"{period.capitalize()} goal set to {target}.", "ok")
        else:
            print_status("Goal already set to this value.", "warn")
        return

    if len(parts) >= 3 and parts[1] == "clear":
        period = parts[2].strip().lower()
        if period not in {"monthly", "yearly"}:
            print_status("Goal period must be monthly or yearly.", "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.clear_goal(period)
        except (StorageError, ValueError) as exc:
            print_status(f"Goal update failed: {exc}", "error")
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_status(f"{period.capitalize()} goal cleared.", "ok")
        else:
            print_status("Goal was not set.", "warn")
        return

    print_status("Usage: goal show | goal set monthly|yearly | goal clear monthly|yearly", "warn")


def compact_command_flow(raw_cmd: str):
    global UI_COMPACT_MODE
    parts = raw_cmd.strip().lower().split()
    mode = parts[1] if len(parts) > 1 else "toggle"
    if mode == "on":
        UI_COMPACT_MODE = True
    elif mode == "off":
        UI_COMPACT_MODE = False
    elif mode == "toggle":
        UI_COMPACT_MODE = not UI_COMPACT_MODE
    elif mode == "status":
        print_status(f"Compact mode is {'ON' if UI_COMPACT_MODE else 'OFF'}.", "info")
        return
    else:
        print_status(format_hint("Invalid compact mode", "on | off | toggle | status"), "warn")
        return
    print_result("Compact mode", "Updated", "ON" if UI_COMPACT_MODE else "OFF")


def theme_command_flow(raw_cmd: str):
    global ACTIVE_THEME
    global USE_COLOR

    tokens = raw_cmd.strip().lower().split()
    if len(tokens) == 1:
        print_status(f"Theme: {ACTIVE_THEME} | color={'ON' if USE_COLOR else 'OFF'}", "info")
        print_status(f"Overrides: {summarize_theme_overrides()}", "info")
        palette = {role: theme_color(role) for role in THEME_ROLES}
        print_theme_palette("Active Palette", palette)
        return

    sub = tokens[1]
    if sub == "list":
        print(style("Themes", "bold"))
        for theme_name in sorted(THEMES):
            marker = "*" if theme_name == ACTIVE_THEME else " "
            palette = THEMES[theme_name]
            swatches = " ".join(style("■", palette.get(role, "cyan")) for role in THEME_ROLES)
            detail = ", ".join(f"{role}={palette.get(role, '-')}" for role in THEME_ROLES)
            print(f"  {marker} {theme_name.ljust(8)} {swatches}  {detail}")
        if THEME_OVERRIDES:
            print()
            print(style(f"Active overrides: {summarize_theme_overrides()}", "dim"))
        print()
        return

    if sub == "preview":
        print_theme_preview()
        return

    if sub == "set":
        if len(tokens) != 4:
            print_status("Usage: theme set <accent|success|warning|error> <color>", "warn")
            print_status(format_hint("Colors", " | ".join(COLOR_CHOICES) + " | #RRGGBB"), "info")
            return
        role = tokens[2]
        color = tokens[3]
        if role not in THEME_ROLES:
            print_status(format_hint("Invalid role", "accent | success | warning | error"), "warn")
            return
        if not _is_valid_color_value(color):
            print_status(format_hint("Invalid color", " | ".join(COLOR_CHOICES) + " | #RRGGBB"), "warn")
            return
        THEME_OVERRIDES[role] = color
        print_result("Theme", "Updated", f"{role}={color}")
        return

    if sub == "clear":
        if len(tokens) == 2:
            if not THEME_OVERRIDES:
                print_result("Theme", "No change", "No overrides")
                return
            THEME_OVERRIDES.clear()
            print_result("Theme", "Updated", "Overrides cleared")
            return
        if len(tokens) == 3:
            role = tokens[2]
            if role not in THEME_ROLES:
                print_status(format_hint("Invalid role", "accent | success | warning | error"), "warn")
                return
            if role not in THEME_OVERRIDES:
                print_result("Theme", "No change", f"No override for {role}")
                return
            THEME_OVERRIDES.pop(role, None)
            print_result("Theme", "Updated", f"Cleared override for {role}")
            return
        print_status("Usage: theme clear [accent|success|warning|error]", "warn")
        return

    if sub == "color":
        if len(tokens) == 2 or tokens[2] == "status":
            print_status(f"Color mode: {'ON' if USE_COLOR else 'OFF'}", "info")
            return
        option = tokens[2]
        if option == "on":
            USE_COLOR = True
        elif option == "off":
            USE_COLOR = False
        elif option == "toggle":
            USE_COLOR = not USE_COLOR
        else:
            print_status(format_hint("Invalid color mode", "on | off | toggle | status"), "warn")
            return
        print_result("Color mode", "Updated", "ON" if USE_COLOR else "OFF")
        return

    if sub not in THEMES:
        print_status(
            format_hint(
                "Invalid theme",
                f"{' | '.join(sorted(THEMES))} | list | preview | set | clear | color",
            ),
            "warn",
        )
        return
    ACTIVE_THEME = sub
    print_result("Theme", "Updated", sub)


def backup_flow(library: Library, data_file: Path):
    try:
        library.save()
    except StorageError as exc:
        print_result("Backup", "Failed", str(exc))
        return

    if not data_file.exists():
        print_status("No data file exists yet. Try: add", "warn")
        return

    backup_file = choose_backup_path(data_file)
    try:
        shutil.copy2(data_file, backup_file)
    except OSError as exc:
        print_result("Backup", "Failed", str(exc))
        return
    print_result("Backup", "Saved", str(backup_file))


def restore_flow(library: Library, undo_stack, data_file: Path):
    choice = input("Restore file path (blank = latest backup): ").strip()
    if not choice:
        path = latest_backup_path(data_file)
        if not path:
            print_status("No backup files found.", "warn")
            return
    else:
        path = Path(choice).expanduser()
    if not path.exists():
        print_status(f"File not found: {path}", "warn")
        return
    if not confirm_action(f"Restore from {path}? This overwrites current in-memory state."):
        print_result("Restore", "Canceled")
        return

    try:
        with spinner("Reading restore file"):
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print_result("Restore", "Failed", str(exc))
        return

    snapshot = library.export_state()
    try:
        with spinner("Applying restore"):
            library.restore_state(payload, persist=True)
    except (StorageError, ValueError) as exc:
        print_result("Restore", "Failed", str(exc))
        return

    push_undo(undo_stack, snapshot)
    print_result("Restore", "Updated", str(path))
    print_summary(library)


def export_flow(library: Library, data_file: Path):
    fmt = input("Export format (json/csv): ").strip().lower()
    if fmt not in {"json", "csv"}:
        print_status(format_hint("Invalid format", "json | csv"), "warn")
        return

    export_dir = data_file.parent / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    default_name = f"library_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
    default_path = export_dir / default_name
    path_input = input(f"Output path [{default_path}]: ").strip()
    path = Path(path_input).expanduser() if path_input else default_path
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if fmt == "json":
            with spinner("Exporting JSON"):
                with path.open("w", encoding="utf-8") as handle:
                    json.dump(library.export_state(), handle, indent=2, ensure_ascii=False)
                    handle.write("\n")
        else:
            export_csv(path, library, show_progress=True)
    except OSError as exc:
        print_result("Export", "Failed", str(exc))
        return
    print_result("Export", "Saved", f"{len(library.books)} books -> {path}")


def import_flow(library: Library, undo_stack):
    path_input = input("Import file path: ").strip()
    if not path_input:
        print_result("Import", "Canceled")
        return
    path = Path(path_input).expanduser()
    if not path.exists():
        print_status(f"File not found: {path}", "warn")
        return

    suffix = path.suffix.lower().lstrip(".")
    if suffix not in {"json", "csv"}:
        suffix = input("Format (json/csv): ").strip().lower()
    if suffix not in {"json", "csv"}:
        print_status(format_hint("Invalid format", "json | csv"), "warn")
        return

    snapshot = library.export_state()
    try:
        if suffix == "json":
            with spinner("Reading JSON import"):
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            apply_meta = False
            if isinstance(payload, dict) and (
                "reading_list" in payload
                or "goals" in payload
                or "smart_lists" in payload
                or "recommendation_profile" in payload
            ):
                apply_meta = (
                    input("Apply reading list, goals, smart lists, and interests from file too? (y/n): ").strip().lower()
                    in YES_VALUES
                )
            with spinner("Importing books"):
                result = library.import_payload(payload, apply_metadata=apply_meta)
        else:
            books, invalid_rows = load_books_from_csv(path, show_progress=True)
            with spinner("Saving imported books"):
                result = library.import_books(books)
            result["invalid"] += invalid_rows
    except (OSError, json.JSONDecodeError) as exc:
        print_result("Import", "Failed", str(exc))
        return
    except (StorageError, ValueError) as exc:
        print_result("Import", "Failed", str(exc))
        return

    changed = result["added"] > 0 or result.get("metadata_updated", 0) > 0
    if changed:
        push_undo(undo_stack, snapshot)
    result_label = "Updated" if changed else "No change"
    print_result("Import", result_label, f"added={result['added']}, skipped={result['skipped']}, invalid={result['invalid']}")
    if result.get("metadata_updated"):
        print_result("Import metadata", "Updated")


def tag_command_flow(cmd: str, library: Library, undo_stack):
    if cmd == "tag clear":
        book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
        if not book:
            print_status("Item not found or selection canceled.", "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.clear_tags(book.book_id)
        except StorageError as exc:
            print_result("Tag clear", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Tag clear", "Updated", f"(ID: {book.book_id})")
        else:
            print_result("Tag clear", "No change")
        return

    if cmd not in {"tag add", "tag remove", "tag set"}:
        print_status("Usage: tag add | tag remove | tag set | tag clear", "warn")
        return

    book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
    if not book:
        print_status("Item not found or selection canceled.", "warn")
        return
    tags_input = input("Tags (comma-separated): ").strip()
    tags = parse_tags(tags_input)

    snapshot = library.export_state()
    try:
        if cmd == "tag add":
            changed = library.add_tags(book.book_id, tags)
            success_message = "Tags added and saved."
            failure_message = "Item not found, no tags provided, or no new tags were added."
        elif cmd == "tag remove":
            changed = library.remove_tags(book.book_id, tags)
            success_message = "Tags removed and saved."
            failure_message = "Item not found, no tags provided, or none of those tags exist on the book."
        else:
            changed = library.set_tags(book.book_id, tags)
            success_message = "Tags replaced and saved."
            failure_message = "Item not found or tags unchanged."
    except StorageError as exc:
        print_result("Tag update", "Failed", str(exc))
        return

    if changed:
        push_undo(undo_stack, snapshot)
        print_result("Tag update", "Updated", success_message)
    else:
        print_result("Tag update", "No change", failure_message)


def practice_command_flow(library: Library, undo_stack) -> None:
    book = ask_book_reference(library, "Sheet music reference (ID/ISBN/title/composer): ")
    if not book:
        print_status("Item not found or selection canceled.", "warn")
        return
    if book.item_type != "SheetMusic":
        print_status("Practice status can only be set for sheet music entries.", "warn")
        return

    print_status(f"Current practice status: {book.practice_status or 'Unstarted'}", "info")
    status_input = input(
        f"Practice status ({'/'.join(ALLOWED_PRACTICE_STATUSES)}): "
    ).strip()
    parsed = parse_practice_status(status_input)
    if parsed is None:
        print_status(
            format_hint("Invalid practice status", " | ".join(ALLOWED_PRACTICE_STATUSES)),
            "warn",
        )
        return

    snapshot = library.export_state()
    try:
        changed = library.set_practice_status(book.book_id, parsed)
    except (StorageError, ValueError) as exc:
        print_result("Practice", "Failed", str(exc))
        return
    if changed:
        push_undo(undo_stack, snapshot)
        print_result("Practice", "Updated", f"(ID: {book.book_id}, status={parsed})")
    else:
        print_result("Practice", "No change")


def smart_command_flow(raw_cmd: str, library: Library, undo_stack):
    cmd = raw_cmd.strip()
    lower = cmd.lower()

    if lower == "smart list":
        entries = library.list_smart_lists()
        if not entries:
            print_status("No smart lists saved yet. Try: smart add", "info")
            return
        rows = [[name, smart_filters_to_label(filters)] for name, filters in entries]
        print(style("Smart Lists", "bold"))
        print_table(rows, ["Name", "Filters"])
        print()
        return

    if lower.startswith("smart run"):
        name = cmd[9:].strip() if len(cmd) > 9 else ""
        if not name:
            name = input("Smart list name: ").strip()
        if not name:
            print_status("Smart list name is required.", "warn")
            return
        found = library.get_smart_list(name)
        if not found:
            print_status("Smart list not found. Try: smart list", "warn")
            return
        list_name, filters = found
        books = library.run_smart_list(list_name)
        print_status(f"Running smart list '{list_name}' ({smart_filters_to_label(filters)}).", "info")
        print_books(books, f"Smart List: {list_name}")
        return

    if lower.startswith("smart remove"):
        name = cmd[12:].strip() if len(cmd) > 12 else ""
        if not name:
            name = input("Smart list name to remove: ").strip()
        if not name:
            print_status("Smart list name is required.", "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.remove_smart_list(name)
        except StorageError as exc:
            print_status(f"Smart list update failed: {exc}", "error")
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Smart list", "Updated", "Removed")
        else:
            print_result("Smart list", "No change", "Not found")
        return

    if lower.startswith("smart add"):
        name = cmd[9:].strip() if len(cmd) > 9 else ""
        if not name:
            name = input("Smart list name: ").strip()
        if not name:
            print_status("Smart list name is required.", "warn")
            return

        try:
            read_filter = parse_read_filter(input("Read filter (read/unread/any): ").strip())
        except ValueError as exc:
            print_status(format_hint("Invalid read filter", "read | unread | any"), "warn")
            return

        location_raw = input("Location filter (Pforta/Zuhause/any): ").strip()
        if not location_raw or location_raw.lower() in {"any", "*"}:
            location_filter = None
        else:
            location_filter = parse_location(location_raw)
            if location_filter is None:
                print_status(format_hint("Invalid location filter", "Pforta | Zuhause | any"), "warn")
                return

        genre_filter = input("Genre filter (optional): ").strip() or None
        min_rating = get_optional_int("Minimum rating 1-5 (optional): ")
        if min_rating is CANCELED:
            print_result("Smart list", "Canceled")
            return
        if min_rating is not None and not (1 <= min_rating <= 5):
            print_status(format_hint("Invalid minimum rating", "1 to 5"), "warn")
            return
        tags_filter = parse_tags(input("Required tags (comma-separated, optional): ").strip())

        snapshot = library.export_state()
        try:
            changed = library.save_smart_list(
                name,
                {
                    "read": read_filter,
                    "location": location_filter,
                    "genre": genre_filter,
                    "min_rating": min_rating,
                    "tags": tags_filter,
                },
            )
        except (StorageError, ValueError) as exc:
            print_status(f"Smart list update failed: {exc}", "error")
            return

        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Smart list", "Saved", name)
        else:
            print_result("Smart list", "No change")
        return

    print_status("Usage: smart add | smart list | smart run | smart remove", "warn")


def _format_rating_filter(value: str) -> tuple[str, int] | None:
    match = re.match(r"^rating(<=|>=|=|<|>)(\d)$", value.strip().lower())
    if not match:
        return None
    operator = match.group(1)
    rating_value = int(match.group(2))
    if not (1 <= rating_value <= 5):
        return None
    return operator, rating_value


def _book_matches_rating(book: Book, operator: str, value: int) -> bool:
    if book.rating is None:
        return False
    if operator == "=":
        return book.rating == value
    if operator == ">=":
        return book.rating >= value
    if operator == "<=":
        return book.rating <= value
    if operator == ">":
        return book.rating > value
    if operator == "<":
        return book.rating < value
    return False


def parse_search_query(query: str) -> tuple[dict[str, Any], list[str]]:
    filters: dict[str, Any] = {}
    free_terms: list[str] = []
    try:
        tokens = shlex.split(query)
    except ValueError:
        tokens = query.split()

    for token in tokens:
        lower = token.lower()
        if lower in {"read", "unread"}:
            filters["read"] = lower == "read"
            continue
        rating_filter = _format_rating_filter(lower)
        if rating_filter:
            filters["rating_filter"] = rating_filter
            continue
        if ":" in token:
            key, value = token.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if not value:
                continue
            if key in {"lang", "language"}:
                parsed_language = parse_language(value)
                if parsed_language:
                    filters["language"] = parsed_language
                    continue
            if key == "location":
                parsed_location = parse_location(value)
                if parsed_location:
                    filters["location"] = parsed_location
                    continue
            if key == "genre":
                filters["genre"] = value.casefold()
                continue
            if key == "tag":
                filters.setdefault("tags", set()).add(value.casefold())
                continue
            if key in {"type", "item"}:
                parsed_type = parse_item_type(value)
                if parsed_type:
                    filters["item_type"] = parsed_type
                    continue
            if key == "author":
                filters["author"] = value.casefold()
                continue
            if key == "title":
                filters["title"] = value.casefold()
                continue
            if key == "composer":
                filters["composer"] = value.casefold()
                continue
        free_terms.append(token.casefold())
    return filters, free_terms


def run_advanced_search(library: Library, query: str) -> list[Book]:
    filters, free_terms = parse_search_query(query)
    results: list[Book] = []
    for book in library.books:
        if "read" in filters and book.read != filters["read"]:
            continue
        if "language" in filters and book.language != filters["language"]:
            continue
        if "location" in filters and book.location != filters["location"]:
            continue
        if "item_type" in filters and book.item_type != filters["item_type"]:
            continue
        if "genre" in filters and filters["genre"] not in (book.genre or "").casefold():
            continue
        if "author" in filters and filters["author"] not in (book.author or "").casefold():
            continue
        if "title" in filters and filters["title"] not in (book.title or "").casefold():
            continue
        if "composer" in filters and filters["composer"] not in (book.composer or "").casefold():
            continue
        tags_filter = filters.get("tags")
        if tags_filter:
            tag_keys = {tag.casefold() for tag in book.tags}
            if not set(tags_filter).issubset(tag_keys):
                continue
        if "rating_filter" in filters:
            operator, value = filters["rating_filter"]
            if not _book_matches_rating(book, operator, value):
                continue
        if free_terms:
            haystack = " ".join(
                [
                    book.title,
                    book.author,
                    book.composer or "",
                    book.genre or "",
                    " ".join(book.tags),
                    book.notes or "",
                    book.instrumentation or "",
                    book.language,
                    book.location,
                ]
            ).casefold()
            if not all(term in haystack for term in free_terms):
                continue
        results.append(book)
    results.sort(
        key=lambda book: (
            book.read,
            -(book.rating if book.rating is not None else 0),
            book.title.casefold(),
        )
    )
    return results


def search_command_flow(raw_cmd: str, library: Library) -> None:
    query = _command_tail(raw_cmd, "search")
    if not query:
        query = input("Search query: ").strip()
    if not query:
        print_status("Usage: search <query>", "warn")
        return
    results = run_advanced_search(library, query)
    if not results:
        print_status("No matches.", "info")
        return
    print_books(results, f"Search results ({len(results)}): {query}")


def _request_json(url: str, *, timeout: float = 7.0) -> dict[str, Any] | None:
    request = Request(
        url,
        headers={
            "User-Agent": "LibraryOfAlexandria/1.0 (+https://github.com/stealthdev-del0/library_of_alexandria)"
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError, TimeoutError, OSError):
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _openlibrary_metadata_by_isbn(isbn: str) -> dict[str, Any] | None:
    clean = isbn.strip()
    if not clean:
        return None
    encoded = quote(clean)
    url = (
        "https://openlibrary.org/api/books"
        f"?bibkeys=ISBN:{encoded}&format=json&jscmd=data"
    )
    payload = _request_json(url)
    if not payload:
        return None
    return payload.get(f"ISBN:{clean}")


def _openlibrary_metadata_by_title_author(title: str, author: str) -> dict[str, Any] | None:
    params = urlencode({"title": title, "author": author, "limit": 1})
    url = f"https://openlibrary.org/search.json?{params}"
    payload = _request_json(url)
    if not payload:
        return None
    docs = payload.get("docs")
    if not isinstance(docs, list) or not docs:
        return None
    doc = docs[0]
    if not isinstance(doc, dict):
        return None
    subjects = doc.get("subject") or []
    if not isinstance(subjects, list):
        subjects = []
    return {
        "publish_year": doc.get("first_publish_year"),
        "number_of_pages_median": doc.get("number_of_pages_median"),
        "subjects": subjects[:8],
    }


def _metadata_updates_for_book(book: Book) -> dict[str, Any] | None:
    if book.item_type != "Book":
        return None
    source = None
    if book.isbn:
        source = _openlibrary_metadata_by_isbn(book.isbn)
    if source is None:
        source = _openlibrary_metadata_by_title_author(book.title, book.author)
    if source is None:
        return None

    updates: dict[str, Any] = {}
    year_value = source.get("publish_year")
    if isinstance(year_value, list):
        year_value = next((item for item in year_value if isinstance(item, int)), None)
    if isinstance(year_value, int) and book.year is None:
        updates["year"] = year_value

    pages_value = source.get("number_of_pages")
    if pages_value is None:
        pages_value = source.get("number_of_pages_median")
    if isinstance(pages_value, int) and pages_value > 0 and book.pages is None:
        updates["pages"] = pages_value

    subjects = source.get("subjects") or source.get("subject") or []
    subject_names: list[str] = []
    if isinstance(subjects, list):
        for entry in subjects:
            if isinstance(entry, dict):
                name = str(entry.get("name", "")).strip()
            else:
                name = str(entry).strip()
            if name:
                subject_names.append(name)
    if subject_names:
        if not book.genre:
            updates["genre"] = ", ".join(subject_names[:2])
        incoming_tags = parse_tags(",".join(subject_names[:6]))
        if incoming_tags:
            merged = parse_tags(",".join(book.tags + incoming_tags))
            if merged != book.tags:
                updates["tags"] = merged
    return updates or None


def metadata_autofill_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    tail = _command_tail(raw_cmd, "metadata autofill")
    target_arg = tail.strip().lower()
    if not target_arg:
        target_arg = input("Target (reference/all): ").strip().lower()
    if target_arg == "all":
        targets = [book for book in library.books if book.item_type == "Book"]
    else:
        book = resolve_book_reference(library, target_arg) if target_arg else None
        if not book:
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
        if not book:
            print_status("Item not found.", "warn")
            return
        targets = [book]

    safe_mode = bool(library.ai_settings.get("safe_mode", True))
    updated_count = 0
    skipped_count = 0
    snapshot = library.export_state()

    with spinner("Fetching metadata"):
        for item in targets:
            updates = _metadata_updates_for_book(item)
            if not updates:
                skipped_count += 1
                continue
            if safe_mode:
                summary = ", ".join(f"{key}={value}" for key, value in updates.items())
                if not confirm_action(f"Apply metadata to {item.book_id} ({item.title}) -> {summary}?"):
                    skipped_count += 1
                    continue
            try:
                changed = library.edit_book(item.book_id, **updates)
            except (StorageError, ValueError):
                skipped_count += 1
                continue
            if changed:
                updated_count += 1
            else:
                skipped_count += 1

    if updated_count > 0:
        push_undo(undo_stack, snapshot)
        print_result("Metadata autofill", "Updated", f"updated={updated_count}, skipped={skipped_count}")
    else:
        print_result("Metadata autofill", "No change", f"skipped={skipped_count}")


def dedup_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    normalized = raw_cmd.strip().lower()
    if normalized.startswith("dedup scan"):
        tail = _command_tail(raw_cmd, "dedup scan")
        threshold = 0.88
        if tail:
            try:
                threshold = float(tail)
            except ValueError:
                print_status(format_hint("Invalid threshold", "a number like 0.88"), "warn")
                return
        findings = library.find_potential_duplicates(threshold=threshold)
        if not findings:
            print_status("No potential duplicates found.", "info")
            return
        rows = [
            [
                item["left_id"],
                truncate(item["left_title"], 28),
                item["right_id"],
                truncate(item["right_title"], 28),
                f"{item['score']:.3f}",
                truncate(item["reason"], 28),
            ]
            for item in findings[:60]
        ]
        print(style(f"Potential Duplicates ({len(findings)})", "bold"))
        print_table(rows, ["ID A", "Title A", "ID B", "Title B", "Score", "Reason"], right_align={4})
        print()
        return

    if normalized.startswith("dedup merge"):
        first = ask_book_reference(library, "Primary item reference (kept): ")
        if not first:
            print_status("Primary item not found.", "warn")
            return
        second = ask_book_reference(library, "Duplicate item reference (removed): ")
        if not second:
            print_status("Duplicate item not found.", "warn")
            return
        if first.book_id == second.book_id:
            print_status("Choose two different items.", "warn")
            return
        if not confirm_action(
            f"Merge duplicate {second.book_id} into {first.book_id} and remove {second.book_id}?"
        ):
            print_result("Dedup merge", "Canceled")
            return
        snapshot = library.export_state()
        try:
            changed = library.merge_items(first.book_id, second.book_id)
        except (StorageError, ValueError) as exc:
            print_result("Dedup merge", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Dedup merge", "Updated", f"kept={first.book_id}, removed={second.book_id}")
        else:
            print_result("Dedup merge", "No change")
        return

    print_status("Usage: dedup scan [threshold] | dedup merge", "warn")


def doctor_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    fix = raw_cmd.strip().lower() in {"doctor fix", "doctor --fix", "doctor -f"}
    snapshot = library.export_state() if fix else None
    report = library.doctor_data(fix=fix)
    rows = [
        ["Items", str(report.get("items", 0))],
        ["Invalid language", str(report.get("invalid_language", 0))],
        ["Invalid cover", str(report.get("invalid_cover", 0))],
        ["Invalid location", str(report.get("invalid_location", 0))],
        ["Invalid rating", str(report.get("invalid_rating", 0))],
        ["Negative progress", str(report.get("negative_progress", 0))],
        ["Duplicate tags", str(report.get("duplicate_tags", 0))],
    ]
    if fix:
        rows.append(["Fixed entries", str(report.get("fixed", 0))])
    print(style("Data Doctor", "bold"))
    print_table(rows, ["Metric", "Value"], right_align={1})
    print()
    if fix and report.get("fixed", 0) > 0 and snapshot is not None:
        push_undo(undo_stack, snapshot)
        print_result("Doctor", "Updated", f"fixed={report.get('fixed', 0)}")
    elif fix:
        print_result("Doctor", "No change")
    else:
        print_result("Doctor", "Done", "Use `doctor fix` to auto-fix")


def bulk_edit_command_flow(library: Library, undo_stack) -> None:
    mode = input("Target mode (references/filter): ").strip().lower()
    references: list[str] | None = None
    filters: dict[str, Any] | None = None
    if mode in {"references", "ref"}:
        raw_refs = input("References (comma-separated IDs/ISBN/titles): ").strip()
        refs = [item.strip() for item in raw_refs.split(",") if item.strip()]
        if not refs:
            print_status("At least one reference is required.", "warn")
            return
        references = refs
    elif mode in {"filter", "filters"}:
        filters = {}
        read_raw = input("Read filter (read/unread/any): ").strip()
        try:
            filters["read"] = parse_read_filter(read_raw)
        except ValueError:
            print_status(format_hint("Invalid read filter", "read | unread | any"), "warn")
            return
        location_raw = input("Location filter (Pforta/Zuhause/any): ").strip()
        location_value = parse_optional_location(location_raw)
        if location_raw and location_value is None and location_raw.lower() not in {"any", "*"}:
            print_status(format_hint("Invalid location filter", "Pforta | Zuhause | any"), "warn")
            return
        filters["location"] = location_value
        genre_raw = input("Genre filter (optional): ").strip()
        if genre_raw:
            filters["genre"] = genre_raw
        min_rating_raw = input("Minimum rating filter 1-5 (optional): ").strip()
        if min_rating_raw:
            try:
                filters["min_rating"] = int(min_rating_raw)
            except ValueError:
                print_status(format_hint("Invalid rating filter", "1 to 5"), "warn")
                return
        tags_raw = input("Required tags filter (comma-separated, optional): ").strip()
        if tags_raw:
            filters["tags"] = parse_tags(tags_raw)
    else:
        print_status(format_hint("Invalid mode", "references | filter"), "warn")
        return

    updates: dict[str, Any] = {}
    genre_update = input("Set genre (blank = unchanged): ").strip()
    if genre_update:
        updates["genre"] = genre_update
    language_update_raw = input("Set language (German/English/French/Japanese, blank = unchanged): ").strip()
    if language_update_raw:
        parsed_language = parse_language(language_update_raw)
        if parsed_language is None:
            print_status(format_hint("Invalid language", "German | English | French | Japanese"), "warn")
            return
        updates["language"] = parsed_language
    location_update_raw = input("Set location (Pforta/Zuhause, blank = unchanged): ").strip()
    if location_update_raw:
        parsed_location = parse_location(location_update_raw)
        if parsed_location is None:
            print_status(format_hint("Invalid location", "Pforta | Zuhause"), "warn")
            return
        updates["location"] = parsed_location
    cover_update_raw = input("Set cover (Hardcover/Softcover, blank = unchanged): ").strip()
    if cover_update_raw:
        parsed_cover = parse_cover(cover_update_raw)
        if parsed_cover is None:
            print_status(format_hint("Invalid cover", "Hardcover | Softcover"), "warn")
            return
        updates["cover"] = parsed_cover
    set_tags_raw = input("Set tags (comma-separated, blank = unchanged): ").strip()
    if set_tags_raw:
        updates["set_tags"] = parse_tags(set_tags_raw)
    add_tags_raw = input("Add tags (comma-separated, blank = unchanged): ").strip()
    if add_tags_raw:
        updates["add_tags"] = parse_tags(add_tags_raw)
    remove_tags_raw = input("Remove tags (comma-separated, blank = unchanged): ").strip()
    if remove_tags_raw:
        updates["remove_tags"] = parse_tags(remove_tags_raw)
    series_name_update = input("Set series name (blank = unchanged): ").strip()
    if series_name_update:
        updates["series_name"] = series_name_update
    series_index_raw = input("Set series index (positive integer, blank = unchanged): ").strip()
    if series_index_raw:
        try:
            updates["series_index"] = int(series_index_raw)
        except ValueError:
            print_status(format_hint("Invalid series index", "a positive integer"), "warn")
            return

    if not updates:
        print_result("Bulk edit", "Canceled", "No updates provided")
        return

    snapshot = library.export_state()
    try:
        result = library.bulk_edit(references=references, filters=filters, updates=updates)
    except (StorageError, ValueError) as exc:
        print_result("Bulk edit", "Failed", str(exc))
        return
    if result.get("updated", 0) > 0:
        push_undo(undo_stack, snapshot)
        print_result(
            "Bulk edit",
            "Updated",
            f"targets={result.get('targets', 0)}, updated={result.get('updated', 0)}, skipped={result.get('skipped', 0)}",
        )
    else:
        print_result(
            "Bulk edit",
            "No change",
            f"targets={result.get('targets', 0)}, skipped={result.get('skipped', 0)}",
        )


def practice_extended_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    cmd = raw_cmd.strip().lower()
    if cmd == "practice":
        practice_command_flow(library, undo_stack)
        return
    if cmd.startswith("practice tempo"):
        book = ask_book_reference(library, "Sheet music reference (ID/ISBN/title/composer): ")
        if not book:
            print_status("Item not found.", "warn")
            return
        bpm_text = input("Tempo target bpm (blank clears): ").strip()
        bpm_value: int | None
        if not bpm_text:
            bpm_value = None
        else:
            try:
                bpm_value = int(bpm_text)
            except ValueError:
                print_status(format_hint("Invalid bpm", "a positive integer"), "warn")
                return
        snapshot = library.export_state()
        try:
            changed = library.set_tempo_target(book.book_id, bpm_value)
        except (StorageError, ValueError) as exc:
            print_result("Practice tempo", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Practice tempo", "Updated", f"(ID: {book.book_id})")
        else:
            print_result("Practice tempo", "No change")
        return
    if cmd.startswith("practice log"):
        book = ask_book_reference(library, "Sheet music reference (ID/ISBN/title/composer): ")
        if not book:
            print_status("Item not found.", "warn")
            return
        minutes_raw = input("Practice minutes: ").strip()
        try:
            minutes = int(minutes_raw)
        except ValueError:
            print_status(format_hint("Invalid minutes", "a positive integer"), "warn")
            return
        bpm_raw = input("BPM reached (optional): ").strip()
        bpm_value = None
        if bpm_raw:
            try:
                bpm_value = int(bpm_raw)
            except ValueError:
                print_status(format_hint("Invalid bpm", "a positive integer"), "warn")
                return
        date_raw = input("Practice date YYYY-MM-DD (blank = today): ").strip() or None
        status_raw = input("Set practice status (optional): ").strip()
        status_value = parse_practice_status(status_raw) if status_raw else None
        if status_raw and status_value is None:
            print_status(
                format_hint("Invalid practice status", " | ".join(ALLOWED_PRACTICE_STATUSES)),
                "warn",
            )
            return
        snapshot = library.export_state()
        try:
            changed = library.log_practice(
                book.book_id,
                minutes=minutes,
                bpm=bpm_value,
                practiced_on=date_raw,
                mark_done_status=status_value,
            )
        except (StorageError, ValueError) as exc:
            print_result("Practice log", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Practice log", "Updated", f"(ID: {book.book_id}, +{minutes} min)")
        else:
            print_result("Practice log", "No change")
        return
    print_status("Usage: practice | practice log | practice tempo", "warn")


def series_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    cmd = raw_cmd.strip().lower()
    if cmd.startswith("series set"):
        book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
        if not book:
            print_status("Item not found.", "warn")
            return
        name = input("Series name (blank clears): ").strip()
        index_raw = input("Series index (blank clears): ").strip()
        index_value = None
        if index_raw:
            try:
                index_value = int(index_raw)
            except ValueError:
                print_status(format_hint("Invalid series index", "a positive integer"), "warn")
                return
        snapshot = library.export_state()
        try:
            changed = library.set_series(book.book_id, name, index_value)
        except (StorageError, ValueError) as exc:
            print_result("Series set", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Series set", "Updated", f"(ID: {book.book_id})")
        else:
            print_result("Series set", "No change")
        return

    if cmd.startswith("series next"):
        name = _command_tail(raw_cmd, "series next")
        items = library.next_in_series(name or None)
        if not items:
            print_status("No unread series entries found.", "info")
            return
        label = f"Next in series: {name}" if name else "Next in all series"
        print_books(items, label)
        return

    print_status("Usage: series set | series next [name]", "warn")


def reading_plan_command_flow(raw_cmd: str, library: Library) -> None:
    weeks_raw = _command_tail(raw_cmd, "reading plan")
    weeks = 4
    if weeks_raw:
        try:
            weeks = int(weeks_raw)
        except ValueError:
            print_status(format_hint("Invalid weeks", "a positive integer"), "warn")
            return
    minutes_raw = input("Available minutes per week: ").strip()
    try:
        minutes = int(minutes_raw)
    except ValueError:
        print_status(format_hint("Invalid minutes", "a positive integer"), "warn")
        return
    try:
        plan = library.create_reading_plan(minutes, weeks=weeks)
    except ValueError as exc:
        print_status(str(exc), "warn")
        return
    if not plan:
        print_status("No plan could be generated.", "info")
        return
    print(style("Reading Plan", "bold"))
    for week in plan:
        print(
            f"Week {week['week']}: {week['planned_pages']}/{week['capacity_pages']} planned pages"
        )
        for entry in week["entries"]:
            print(f"  - {entry['book_id']}: {entry['title']} ({entry['planned_pages']} p)")
    print()


def calendar_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    cmd = raw_cmd.strip().lower()
    if cmd.startswith("calendar add"):
        book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
        if not book:
            print_status("Item not found.", "warn")
            return
        when_raw = input("Date (YYYY-MM-DD): ").strip()
        if not when_raw:
            when_raw = date.today().isoformat()
        minutes_raw = input("Minutes: ").strip()
        try:
            minutes = int(minutes_raw)
        except ValueError:
            print_status(format_hint("Invalid minutes", "a positive integer"), "warn")
            return
        kind_raw = input("Kind (reading/practice, default reading): ").strip().lower() or "reading"
        if kind_raw not in {"reading", "practice"}:
            print_status(format_hint("Invalid kind", "reading | practice"), "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.schedule_session(book.book_id, when=when_raw, minutes=minutes, kind=kind_raw)
        except (StorageError, ValueError) as exc:
            print_result("Calendar add", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Calendar add", "Saved", f"(ID: {book.book_id}, date={when_raw})")
        else:
            print_result("Calendar add", "No change")
        return

    if cmd.startswith("calendar list"):
        day = _command_tail(raw_cmd, "calendar list") or date.today().isoformat()
        sessions = library.sessions_on(day)
        if not sessions:
            print_status(f"No sessions on {day}.", "info")
            return
        rows = []
        for session in sessions:
            book = library.get_by_book_id(str(session.get("book_id", "")))
            title = book.title if book else "-"
            rows.append(
                [
                    str(session.get("id", "-")),
                    str(session.get("kind", "-")),
                    title,
                    str(session.get("minutes", "-")),
                    "yes" if session.get("done") else "no",
                ]
            )
        print(style(f"Calendar {day}", "bold"))
        print_table(rows, ["Session", "Kind", "Title", "Minutes", "Done"], right_align={3})
        print()
        return

    if cmd.startswith("calendar done"):
        session_id = _command_tail(raw_cmd, "calendar done")
        if not session_id:
            session_id = input("Session ID: ").strip()
        if not session_id:
            print_status("Session ID is required.", "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.mark_session_done(session_id)
        except StorageError as exc:
            print_result("Calendar done", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Calendar done", "Updated", session_id)
        else:
            print_result("Calendar done", "No change")
        return

    if cmd.startswith("calendar streak"):
        tail = _command_tail(raw_cmd, "calendar streak").strip().lower()
        kind = "reading"
        if tail in {"reading", "practice"}:
            kind = tail
        elif tail:
            print_status(format_hint("Invalid streak kind", "reading | practice"), "warn")
            return
        value = library.streak(kind=kind)
        print_result("Calendar streak", "Done", f"{kind}={value} day(s)")
        return

    print_status("Usage: calendar add | calendar list [date] | calendar done | calendar streak [reading|practice]", "warn")


def inbox_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    cmd = raw_cmd.strip().lower()
    if cmd.startswith("inbox add"):
        text = _command_tail(raw_cmd, "inbox add")
        if not text:
            text = input("Inbox text: ").strip()
        if not text:
            print_status("Inbox text is required.", "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.add_inbox_item(text)
        except StorageError as exc:
            print_result("Inbox add", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Inbox add", "Saved")
        else:
            print_result("Inbox add", "No change")
        return

    if cmd.startswith("inbox list"):
        status = _command_tail(raw_cmd, "inbox list").strip().lower() or None
        if status not in {None, "open", "done", "processed"}:
            print_status(format_hint("Invalid status", "open | done | processed"), "warn")
            return
        items = library.list_inbox_items(status=status)
        if not items:
            print_status("Inbox is empty.", "info")
            return
        rows = [
            [
                item.get("id", "-"),
                truncate(item.get("text", "-"), 44),
                item.get("status", "-"),
                item.get("created_at", "-"),
            ]
            for item in items
        ]
        print(style("Inbox", "bold"))
        print_table(rows, ["ID", "Text", "Status", "Created"], max_widths={"Text": 48})
        print()
        return

    if cmd.startswith("inbox done"):
        inbox_id = _command_tail(raw_cmd, "inbox done")
        if not inbox_id:
            inbox_id = input("Inbox ID: ").strip()
        if not inbox_id:
            print_status("Inbox ID is required.", "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.set_inbox_status(inbox_id, "done")
        except StorageError as exc:
            print_result("Inbox done", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Inbox done", "Updated", inbox_id)
        else:
            print_result("Inbox done", "No change")
        return

    if cmd.startswith("inbox remove"):
        inbox_id = _command_tail(raw_cmd, "inbox remove")
        if not inbox_id:
            inbox_id = input("Inbox ID: ").strip()
        if not inbox_id:
            print_status("Inbox ID is required.", "warn")
            return
        if not confirm_action(f"Remove inbox entry {inbox_id}?"):
            print_result("Inbox remove", "Canceled")
            return
        snapshot = library.export_state()
        try:
            changed = library.remove_inbox_item(inbox_id)
        except StorageError as exc:
            print_result("Inbox remove", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("Inbox remove", "Updated", inbox_id)
        else:
            print_result("Inbox remove", "No change")
        return

    if cmd.startswith("inbox process"):
        inbox_id = _command_tail(raw_cmd, "inbox process")
        if not inbox_id:
            inbox_id = input("Inbox ID to process: ").strip()
        if not inbox_id:
            print_status("Inbox ID is required.", "warn")
            return
        item = next((entry for entry in library.list_inbox_items() if str(entry.get("id", "")).casefold() == inbox_id.casefold()), None)
        if not item:
            print_status("Inbox item not found.", "warn")
            return
        if str(item.get("status", "")).lower() not in {"open", "todo", ""}:
            print_status("Inbox item is already processed/done.", "warn")
            return
        print(style(f"Processing inbox: {item.get('text', '')}", "bold"))
        title = input(f"Title [{item.get('text', '')}]: ").strip() or str(item.get("text", "")).strip()
        item_type_raw = input("Type (Book/SheetMusic, default Book): ").strip()
        item_type = parse_item_type(item_type_raw) if item_type_raw else "Book"
        if item_type is None:
            print_status(format_hint("Invalid type", "Book | SheetMusic"), "warn")
            return
        if item_type == "SheetMusic":
            composer = input("Composer: ").strip()
            if not composer:
                print_status("Composer is required for sheet music.", "warn")
                return
            author = composer
            instrumentation = input("Instrumentation (optional): ").strip()
            practice_status = "Unstarted"
        else:
            author = input("Author: ").strip()
            if not author:
                print_status("Author is required.", "warn")
                return
            composer = ""
            instrumentation = ""
            practice_status = ""
        genre = input("Genre (optional): ").strip()
        language_raw = input("Language (German/English/French/Japanese, default English): ").strip()
        language = "English" if not language_raw else parse_language(language_raw)
        if language is None:
            print_status(format_hint("Invalid language", "German | English | French | Japanese"), "warn")
            return
        location_raw = input("Location (Pforta/Zuhause, default Zuhause): ").strip()
        location = "Zuhause" if not location_raw else parse_location(location_raw)
        if location is None:
            print_status(format_hint("Invalid location", "Pforta | Zuhause"), "warn")
            return
        cover_raw = input("Cover (Hardcover/Softcover, default Softcover): ").strip()
        cover = "Softcover" if not cover_raw else parse_cover(cover_raw)
        if cover is None:
            print_status(format_hint("Invalid cover", "Hardcover | Softcover"), "warn")
            return
        tags = parse_tags(input("Tags (comma-separated, optional): ").strip())
        new_entry = Book(
            title=title,
            author=author,
            genre=genre,
            language=language,
            location=location,
            cover=cover,
            tags=tags,
            item_type=item_type,
            composer=composer,
            instrumentation=instrumentation,
            practice_status=practice_status,
        )
        snapshot = library.export_state()
        try:
            added = library.add_book(new_entry)
            processed = library.set_inbox_status(inbox_id, "processed")
        except (StorageError, ValueError) as exc:
            print_result("Inbox process", "Failed", str(exc))
            return
        if added or processed:
            push_undo(undo_stack, snapshot)
            print_result("Inbox process", "Updated", f"added={new_entry.book_id or '-'}")
        else:
            print_result("Inbox process", "No change", "Duplicate entry")
        return

    print_status("Usage: inbox add | inbox list [status] | inbox process | inbox done | inbox remove", "warn")


def _snapshot_dir(data_file: Path) -> Path:
    path = data_file.parent / SNAPSHOT_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_files(data_file: Path) -> list[Path]:
    directory = _snapshot_dir(data_file)
    return sorted(directory.glob("snapshot_*.json"), reverse=True)


def snapshot_command_flow(raw_cmd: str, library: Library, data_file: Path, undo_stack) -> None:
    cmd = raw_cmd.strip().lower()
    if cmd.startswith("snapshot create"):
        name = _command_tail(raw_cmd, "snapshot create")
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{safe_name}" if safe_name else ""
        path = _snapshot_dir(data_file) / f"snapshot_{stamp}{suffix}.json"
        try:
            with path.open("w", encoding="utf-8") as handle:
                json.dump(library.export_state(), handle, indent=2, ensure_ascii=False)
                handle.write("\n")
        except OSError as exc:
            print_result("Snapshot create", "Failed", str(exc))
            return
        print_result("Snapshot create", "Saved", str(path))
        return

    if cmd.startswith("snapshot list"):
        files = _snapshot_files(data_file)
        if not files:
            print_status("No snapshots found.", "info")
            return
        rows = [[str(index), file.name, datetime.fromtimestamp(file.stat().st_mtime).isoformat(sep=" ", timespec="seconds")] for index, file in enumerate(files, 1)]
        print(style("Snapshots", "bold"))
        print_table(rows, ["#", "File", "Modified"], right_align={0})
        print()
        return

    if cmd.startswith("snapshot restore"):
        files = _snapshot_files(data_file)
        if not files:
            print_status("No snapshots found.", "warn")
            return
        choice = _command_tail(raw_cmd, "snapshot restore")
        if not choice:
            print(style("Snapshots", "bold"))
            for index, file in enumerate(files, 1):
                print(f"  {index:>2}. {file.name}")
            choice = input("Snapshot number or filename: ").strip()
        if not choice:
            print_result("Snapshot restore", "Canceled")
            return
        target: Path | None = None
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(files):
                target = files[index - 1]
        if target is None:
            for file in files:
                if file.name == choice or choice in file.name:
                    target = file
                    break
        if target is None:
            print_status("Snapshot not found.", "warn")
            return
        if not confirm_action(f"Restore snapshot {target.name}?"):
            print_result("Snapshot restore", "Canceled")
            return
        snapshot = library.export_state()
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            library.restore_state(payload, persist=True)
        except (OSError, json.JSONDecodeError, StorageError, ValueError) as exc:
            print_result("Snapshot restore", "Failed", str(exc))
            return
        push_undo(undo_stack, snapshot)
        print_result("Snapshot restore", "Updated", target.name)
        return

    print_status("Usage: snapshot create [name] | snapshot list | snapshot restore", "warn")


def profile_command_flow(raw_cmd: str, library: Library, data_file: Path) -> tuple[Library, Path, bool]:
    cmd = raw_cmd.strip().lower()
    active_profile = profile_name_from_data_file(data_file)
    if cmd.startswith("profile show"):
        print(style("Profile", "bold"))
        print(f"  Active: {active_profile}")
        print(f"  Data:   {data_file}")
        print()
        return library, data_file, False

    if cmd.startswith("profile list"):
        root = _profiles_root()
        root.mkdir(parents=True, exist_ok=True)
        profiles = sorted(path.stem for path in root.glob("*.json"))
        if "default" not in profiles:
            profiles.insert(0, "default")
        rows = [[name, "*" if name == active_profile else "", str(resolve_data_file(name if name != "default" else None))] for name in profiles]
        print(style("Profiles", "bold"))
        print_table(rows, ["Name", "Active", "Data file"])
        print()
        return library, data_file, False

    if cmd.startswith("profile new"):
        name = _command_tail(raw_cmd, "profile new")
        if not name:
            name = input("New profile name: ").strip()
        sanitized = _sanitize_profile_name(name)
        if not sanitized:
            print_status("Profile name is required.", "warn")
            return library, data_file, False
        target = resolve_data_file(sanitized)
        if target.exists():
            print_status("Profile already exists. Switching to existing profile.", "info")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                target.write_text(json.dumps(Library(data_path=target).export_state(), indent=2) + "\n", encoding="utf-8")
            except OSError as exc:
                print_result("Profile new", "Failed", str(exc))
                return library, data_file, False
        next_library = load_library(target)
        print_result("Profile", "Updated", f"active={sanitized}")
        return next_library, target, True

    if cmd.startswith("profile use"):
        name = _command_tail(raw_cmd, "profile use")
        if not name:
            name = input("Profile name: ").strip()
        sanitized = _sanitize_profile_name(name)
        if not sanitized:
            print_status("Profile name is required.", "warn")
            return library, data_file, False
        target = resolve_data_file(sanitized)
        next_library = load_library(target)
        print_result("Profile", "Updated", f"active={sanitized}")
        return next_library, target, True

    print_status("Usage: profile show | profile list | profile new <name> | profile use <name>", "warn")
    return library, data_file, False


def _ollama_api_request(path: str, payload: dict[str, Any] | None = None, timeout: float = 20.0) -> dict[str, Any] | None:
    url = f"http://127.0.0.1:11434{path}"
    data_bytes = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
    request = Request(url, headers=headers, data=data_bytes, method="POST" if payload is not None else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError, TimeoutError, OSError):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _ai_status_summary(model_name: str) -> tuple[bool, list[str]]:
    payload = _ollama_api_request("/api/tags")
    if not payload:
        return False, []
    models = payload.get("models", [])
    if not isinstance(models, list):
        return True, []
    names = []
    for model in models:
        if isinstance(model, dict):
            name = str(model.get("name", "")).strip()
            if name:
                names.append(name)
    has_model = any(name == model_name or name.startswith(model_name + ":") for name in names)
    return has_model, names


def _fallback_ai_description(book: Book) -> tuple[str, str, list[str]]:
    creator = book.composer if book.item_type == "SheetMusic" else book.author
    summary = (
        f"{book.title} by {creator} is tracked in your Alexandria library."
        f" Genre: {book.genre or 'n/a'}, language: {book.language}, location: {book.location}."
    )
    if book.item_type == "SheetMusic":
        author_note = (
            f"{creator} appears in your sheet-music collection."
            f" Instrumentation: {book.instrumentation or 'n/a'}."
        )
    else:
        author_note = (
            f"{creator} appears in your library."
            f" Read status: {'read' if book.read else 'unread'}."
        )
    tags = parse_tags(",".join([book.genre, *book.tags, book.language, book.location]))
    return summary, author_note, tags[:8]


def _ollama_enrich_book(book: Book, model_name: str) -> tuple[str, str, list[str]] | None:
    creator = book.composer if book.item_type == "SheetMusic" else book.author
    prompt = (
        "Return strict JSON with keys summary, author_note, tags."
        " Keep summary under 60 words and author_note under 40 words."
        " tags must be an array of 3-8 lowercase tags.\n"
        f"Item type: {book.item_type}\n"
        f"Title: {book.title}\n"
        f"Creator: {creator}\n"
        f"Genre: {book.genre}\n"
        f"Language: {book.language}\n"
        f"Existing tags: {', '.join(book.tags)}\n"
        f"Notes: {book.notes[:280]}\n"
    )
    payload = _ollama_api_request(
        "/api/generate",
        {"model": model_name, "prompt": prompt, "stream": False, "format": "json"},
        timeout=35.0,
    )
    if not payload:
        return None
    response_text = str(payload.get("response", "")).strip()
    if not response_text:
        return None
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    summary = str(parsed.get("summary", "")).strip()
    author_note = str(parsed.get("author_note", "")).strip()
    tags = parse_tags(",".join(str(item) for item in parsed.get("tags", []) if str(item).strip()))
    if not summary:
        return None
    return summary, author_note, tags


def ai_command_flow(raw_cmd: str, library: Library, undo_stack) -> None:
    cmd = raw_cmd.strip().lower()
    safe_mode = bool(library.ai_settings.get("safe_mode", True))
    model_name = str(library.ai_settings.get("model", "llama3.2")).strip() or "llama3.2"

    if cmd.startswith("ai status"):
        available, models = _ai_status_summary(model_name)
        print(style("AI Status", "bold"))
        print(f"  Safe mode: {'safe (preview+approve)' if safe_mode else 'fast (auto-apply)'}")
        print(f"  Model:     {model_name}")
        print(f"  Ollama:    {'online' if models else 'offline'}")
        if models:
            print(f"  Installed: {', '.join(models[:8])}")
        print()
        if models and not available:
            print_status("Configured model not installed in Ollama.", "warn")
        return

    if cmd.startswith("ai mode"):
        mode = _command_tail(raw_cmd, "ai mode").strip().lower()
        if not mode:
            print_result("AI mode", "Done", "safe" if safe_mode else "fast")
            return
        if mode not in {"safe", "fast"}:
            print_status(format_hint("Invalid mode", "safe | fast"), "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.set_ai_settings(safe_mode=(mode == "safe"))
        except StorageError as exc:
            print_result("AI mode", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("AI mode", "Updated", mode)
        else:
            print_result("AI mode", "No change")
        return

    if cmd.startswith("ai model"):
        model = _command_tail(raw_cmd, "ai model").strip()
        if not model:
            print_status("Usage: ai model <name>", "warn")
            return
        snapshot = library.export_state()
        try:
            changed = library.set_ai_settings(model=model)
        except StorageError as exc:
            print_result("AI model", "Failed", str(exc))
            return
        if changed:
            push_undo(undo_stack, snapshot)
            print_result("AI model", "Updated", model)
        else:
            print_result("AI model", "No change")
        return

    if cmd.startswith("ai recommend"):
        tail = _command_tail(raw_cmd, "ai recommend").strip()
        count = 10
        if tail:
            try:
                count = int(tail)
            except ValueError:
                print_status(format_hint("Invalid count", "a positive integer"), "warn")
                return
        try:
            recommendations = library.recommend_books_with_reasons(limit=count)
        except ValueError as exc:
            print_status(str(exc), "warn")
            return
        if not recommendations:
            print_status("No recommendations found.", "info")
            return
        rows = [
            [
                item["book"].book_id,
                truncate(item["book"].title, 26),
                truncate(item["book"].author, 20),
                f"{item['score']:.2f}",
                truncate(", ".join(item["reasons"]), 44),
            ]
            for item in recommendations
        ]
        print(style("AI Recommendations", "bold"))
        print_table(rows, ["ID", "Title", "Author", "Score", "Reasons"], right_align={3})
        print()
        return

    if cmd.startswith("ai enrich"):
        tail = _command_tail(raw_cmd, "ai enrich").strip()
        if not tail:
            tail = input("Target (reference/all): ").strip()
        if tail.lower() in {"c", "cancel"}:
            print_result("AI enrich", "Canceled")
            return
        if not tail:
            print_status("Usage: ai enrich [reference|all]", "warn")
            return
        if tail.lower() == "all":
            targets = library.books[:]
        else:
            selected = resolve_book_reference(library, tail)
            if not selected:
                print_status("Item not found.", "warn")
                return
            targets = [selected]
        if not targets:
            print_status("No items available for enrichment.", "info")
            return
        snapshot = library.export_state()
        updated = 0
        skipped = 0
        aborted = False
        try:
            for index, book in enumerate(targets, 1):
                with spinner(f"Generating AI enrichment ({index}/{len(targets)})"):
                    generated = _ollama_enrich_book(book, model_name)
                if generated is None:
                    generated = _fallback_ai_description(book)
                summary, author_note, ai_tags = generated
                preview = f"summary='{truncate(summary, 56)}', tags={', '.join(ai_tags[:5]) or '-'}"
                if safe_mode:
                    decision = prompt_apply_skip_cancel(
                        f"Apply AI enrichment to {book.book_id} ({book.title}) -> {preview}?"
                    )
                    if decision == "cancel":
                        aborted = True
                        break
                    if decision == "skip":
                        skipped += 1
                        continue
                try:
                    changed = library.edit_book(
                        book.book_id,
                        ai_summary=summary,
                        ai_author_note=author_note,
                        ai_tags=ai_tags,
                    )
                except (StorageError, ValueError):
                    skipped += 1
                    continue
                if changed:
                    updated += 1
                else:
                    skipped += 1
        except KeyboardInterrupt:
            print()
            aborted = True
        if updated > 0:
            push_undo(undo_stack, snapshot)
        if aborted:
            remaining = max(0, len(targets) - updated - skipped)
            print_result("AI enrich", "Canceled", f"updated={updated}, skipped={skipped}, remaining={remaining}")
        elif updated > 0:
            print_result("AI enrich", "Updated", f"updated={updated}, skipped={skipped}")
        else:
            print_result("AI enrich", "No change", f"skipped={skipped}")
        return

    print_status("Usage: ai status | ai mode [safe|fast] | ai model <name> | ai recommend [count] | ai enrich [reference|all]", "warn")


def interactive_demo(
    library: Library,
    data_file: Path,
    runtime: SharedRuntime | None = None,
) -> tuple[Library, Path]:
    history: list[str] = []
    undo_stack: list[dict[str, Any]] = []
    current_data_file = data_file
    active_profile = profile_name_from_data_file(current_data_file)

    while True:
        try:
            raw_input_cmd = input(themed(build_prompt(library, active_profile), "accent", bold=True)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print_status("Goodbye.", "info")
            break

        raw_cmd = resolve_command_alias(raw_input_cmd)
        cmd = raw_cmd.lower().strip()
        if raw_input_cmd:
            history.append(raw_input_cmd)
        if not cmd:
            continue

        if cmd in ("quit", "exit"):
            print_status("Goodbye.", "info")
            break
        if cmd == "help" or cmd.startswith("help "):
            topic = raw_cmd[4:].strip() if len(raw_cmd) > 4 else ""
            print_help(topic or None)
            continue
        if cmd == "man" or cmd.startswith("man "):
            topic = raw_cmd[3:].strip() if len(raw_cmd) > 3 else ""
            show_man_page(topic)
            continue
        if cmd.startswith("profile"):
            library, current_data_file, switched = profile_command_flow(raw_cmd, library, current_data_file)
            if switched:
                active_profile = profile_name_from_data_file(current_data_file)
                undo_stack.clear()
                if runtime is not None:
                    runtime.library = library
                    runtime.data_file = current_data_file
                print_dashboard(library)
                print_summary(library)
            continue
        if cmd == "add":
            add_book_flow(library, undo_stack)
            continue
        if cmd == "edit":
            edit_book_flow(library, undo_stack)
            continue
        if cmd == "details":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
            if not book:
                print_status("Item not found. Use ID, ISBN, title, or author.", "warn")
                continue
            print_book_details(book)
            continue
        if cmd == "bulk edit":
            bulk_edit_command_flow(library, undo_stack)
            continue
        if cmd == "list" or cmd.startswith("list "):
            list_command_flow(raw_cmd, library)
            continue
        if cmd.startswith("sort "):
            sort_command_flow(cmd, library)
            continue
        if cmd == "authors":
            print_author_overview(library)
            continue
        if cmd.startswith("compact"):
            compact_command_flow(raw_cmd)
            continue
        if cmd.startswith("theme"):
            theme_command_flow(raw_cmd)
            continue
        if cmd == "sheet stats":
            print_sheet_stats(library)
            continue
        if cmd == "obsidian" or cmd.startswith("obsidian "):
            obsidian_command_flow(raw_cmd, library, current_data_file)
            continue
        if cmd == "search" or cmd.startswith("search "):
            search_command_flow(raw_cmd, library)
            continue
        if cmd.startswith("metadata autofill"):
            metadata_autofill_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd.startswith("dedup"):
            dedup_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd == "doctor" or cmd.startswith("doctor "):
            doctor_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd.startswith("find"):
            parts = cmd.split(maxsplit=1)
            if len(parts) != 2 or parts[1] not in ("title", "author", "composer", "notes"):
                print_status("Usage: find title | find author | find composer | find notes", "warn")
                continue
            if parts[1] == "title":
                query = input("Title search: ").strip()
                results = library.find_book_by_title(query)
                label = f"Title matches for: {query}"
            elif parts[1] == "author":
                query = input("Author search: ").strip()
                results = library.find_book_by_author(query)
                label = f"Author matches for: {query}"
            elif parts[1] == "composer":
                query = input("Composer search: ").strip()
                results = library.find_sheet_by_composer(query)
                label = f"Composer matches for: {query}"
            else:
                query = input("Notes search: ").strip()
                results = library.find_books_by_notes(query)
                label = f"Notes matches for: {query}"
            if not results:
                print_status("No matches.", "info")
                continue
            print_books(results, label)
            continue
        if cmd.startswith("interests"):
            interests_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd == "check":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
            if not book:
                print_status("Item not found. Use ID, ISBN, title, or author.", "info")
                continue
            print_result("Check", "Done", f"(ID: {book.book_id})")
            print_book_details(book)
            continue
        if cmd == "remove":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author) to remove: ")
            if not book:
                print_status("Item not found. Use ID, ISBN, title, or author.", "warn")
                continue
            if not confirm_action(f"Remove '{book.title}' by {book.author}?"):
                print_result("Remove", "Canceled")
                continue
            snapshot = library.export_state()
            try:
                changed = library.remove_book(book.book_id)
            except StorageError as exc:
                print_result("Remove", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Remove", "Updated", f"(ID: {book.book_id})")
            else:
                print_result("Remove", "No change")
            continue
        if cmd == "mark read":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
            if not book:
                print_status("Item reference is required.", "warn")
                continue
            snapshot = library.export_state()
            try:
                changed = library.set_read(book.book_id, True)
            except StorageError as exc:
                print_result("Mark read", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Mark read", "Updated", f"(ID: {book.book_id})")
            else:
                print_result("Mark read", "No change")
            continue
        if cmd == "mark unread":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
            if not book:
                print_status("Item reference is required.", "warn")
                continue
            snapshot = library.export_state()
            try:
                changed = library.set_read(book.book_id, False)
            except StorageError as exc:
                print_result("Mark unread", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Mark unread", "Updated", f"(ID: {book.book_id})")
            else:
                print_result("Mark unread", "No change")
            continue
        if cmd == "notes":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
            if not book:
                print_status("Item reference is required.", "warn")
                continue
            note = input("Notes: ").strip()
            snapshot = library.export_state()
            try:
                changed = library.set_notes(book.book_id, note)
            except StorageError as exc:
                print_result("Notes", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Notes", "Updated", f"(ID: {book.book_id})")
            else:
                print_result("Notes", "No change")
            continue
        if cmd.startswith("tag"):
            tag_command_flow(cmd, library, undo_stack)
            continue
        if cmd == "practice" or cmd.startswith("practice "):
            practice_extended_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd == "series set" or cmd.startswith("series next"):
            series_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd == "rate":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
            if not book:
                print_status("Item reference is required.", "warn")
                continue
            rating = get_optional_int("Rating 1-5 (blank clears): ")
            if rating is CANCELED:
                print_result("Rating", "Canceled")
                continue
            if rating is not None and not (1 <= rating <= 5):
                print_status(format_hint("Invalid rating", "1 to 5"), "warn")
                continue
            snapshot = library.export_state()
            try:
                changed = library.set_rating(book.book_id, rating)
            except (StorageError, ValueError) as exc:
                print_result("Rating", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Rating", "Updated", f"(ID: {book.book_id})")
            else:
                print_result("Rating", "No change")
            continue
        if cmd == "progress":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
            if not book:
                print_status("Item reference is required.", "warn")
                continue
            if book.pages is not None:
                print_status(f"Item has {book.pages} pages.", "info")
            progress = get_optional_int("Current progress page: ")
            if progress in (None, CANCELED):
                print_result("Progress", "Canceled")
                continue
            snapshot = library.export_state()
            try:
                changed = library.set_progress(book.book_id, progress)
            except (StorageError, ValueError) as exc:
                print_result("Progress", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Progress", "Updated", f"(ID: {book.book_id})")
            else:
                print_result("Progress", "No change")
            continue
        if cmd == "language":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
            if not book:
                print_status("Item reference is required.", "warn")
                continue
            language_input = input(f"Language ({'/'.join(ALLOWED_LANGUAGES)}): ").strip()
            language = parse_language(language_input)
            if language is None:
                print_status(format_hint("Invalid language", "German | English | French | Japanese"), "warn")
                continue
            snapshot = library.export_state()
            try:
                changed = library.edit_book(book.book_id, language=language)
            except StorageError as exc:
                print_result("Language", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Language", "Updated", f"(ID: {book.book_id})")
            else:
                print_result("Language", "No change")
            continue
        if cmd == "location":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author): ")
            if not book:
                print_status("Item reference is required.", "warn")
                continue
            location_input = input(f"Location ({'/'.join(ALLOWED_LOCATIONS)}): ").strip()
            location = parse_location(location_input)
            if location is None:
                print_status(format_hint("Invalid location", "Pforta | Zuhause"), "warn")
                continue
            snapshot = library.export_state()
            try:
                changed = library.set_location(book.book_id, location)
            except StorageError as exc:
                print_result("Location", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Location", "Updated", f"(ID: {book.book_id})")
            else:
                print_result("Location", "No change")
            continue
        if cmd == "reading add":
            book = ask_book_reference(library, "Item reference (ID/ISBN/title/author) to add: ")
            if not book:
                print_status("Item not found. Use ID, ISBN, title, or author.", "warn")
                continue
            snapshot = library.export_state()
            try:
                changed = library.add_to_reading_list(book.book_id)
            except StorageError as exc:
                print_result("Reading list add", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Reading list add", "Updated", f"(ID: {book.book_id})")
            else:
                print_result("Reading list add", "No change")
            continue
        if cmd.startswith("reading smart"):
            reading_smart_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd == "reading list":
            books = library.reading_list_books()
            if not books:
                print_status("Reading list is empty. Try: reading add", "info")
            else:
                print_books(books, "Reading List")
            continue
        if cmd == "reading remove":
            raw_reference = input("Item reference (ID/ISBN/title/author) to remove: ").strip()
            if not raw_reference:
                print_status("Item reference is required.", "warn")
                continue
            book = resolve_book_reference(library, raw_reference)
            reference = book.book_id if book else raw_reference
            snapshot = library.export_state()
            try:
                changed = library.remove_from_reading_list(reference)
            except StorageError as exc:
                print_result("Reading list remove", "Failed", str(exc))
                continue
            if changed:
                push_undo(undo_stack, snapshot)
                print_result("Reading list remove", "Updated")
            else:
                print_result("Reading list remove", "No change")
            continue
        if cmd == "reading plan" or cmd.startswith("reading plan "):
            reading_plan_command_flow(raw_cmd, library)
            continue
        if cmd.startswith("smart"):
            smart_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd.startswith("goal"):
            goal_command_flow(cmd, library, undo_stack)
            continue
        if cmd == "calendar add" or cmd.startswith("calendar "):
            calendar_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd == "inbox add" or cmd.startswith("inbox "):
            inbox_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd == "snapshot create" or cmd.startswith("snapshot "):
            snapshot_command_flow(raw_cmd, library, current_data_file, undo_stack)
            continue
        if cmd == "ai status" or cmd.startswith("ai "):
            ai_command_flow(raw_cmd, library, undo_stack)
            continue
        if cmd == "stats":
            print_stats(library)
            continue
        if cmd == "backup":
            backup_flow(library, current_data_file)
            continue
        if cmd == "restore":
            restore_flow(library, undo_stack, current_data_file)
            continue
        if cmd == "export" or cmd.startswith("export "):
            export_command_flow(raw_cmd, library, current_data_file)
            continue
        if cmd == "import":
            import_flow(library, undo_stack)
            continue
        if cmd == "undo":
            if not undo_stack:
                print_status("Nothing to undo.", "warn")
                continue
            payload = undo_stack.pop()
            try:
                library.restore_state(payload, persist=True)
            except (StorageError, ValueError) as exc:
                undo_stack.append(payload)
                print_result("Undo", "Failed", str(exc))
                continue
            print_result("Undo", "Updated")
            continue
        if cmd == "history":
            if not history:
                print_status("No commands yet.", "info")
            else:
                print(style("Command History", "bold"))
                for index, value in enumerate(history, 1):
                    print(f"{index:>2}. {value}")
            continue

        candidates = [candidate for candidate in sorted(set(COMMANDS + list(ALIASES.keys()))) if candidate.startswith(cmd)]
        if candidates:
            print_status("Unknown command. Did you mean:", "warn")
            for candidate in candidates:
                print(f"  {candidate}")
        else:
            print_status("Unknown command. Use: help", "warn")

    return library, current_data_file


def load_library(data_file: Path) -> Library:
    try:
        return Library.load(data_file)
    except StorageError as exc:
        print_status(f"Could not load existing data ({exc}). Starting with an empty library.", "error")
        return Library(data_path=data_file)


def main():
    global USE_COLOR
    global ACTIVE_THEME
    global UI_COMPACT_MODE
    global SHOW_MOTION

    args = parse_cli_args()
    if args.help:
        theme_choices = "|".join(sorted(THEMES.keys()))
        print(
            "Usage: python3 main.py "
            f"[--no-color] [--theme {theme_choices}] [--compact] [--no-motion] [--profile <name>] "
            "[--no-gui-server] [--gui-host <host>] [--gui-port <port>] [--open-gui]"
        )
        return
    if args.no_color:
        USE_COLOR = False
    if args.theme:
        ACTIVE_THEME = args.theme
    if args.compact:
        UI_COMPACT_MODE = True
    if args.no_motion:
        SHOW_MOTION = False

    requested_profile = _sanitize_profile_name(args.profile) if args.profile else ""
    data_file = resolve_data_file(requested_profile or None)
    library = load_library(data_file)
    runtime = SharedRuntime(library=library, data_file=data_file)
    gui_server: AlexandriaGUIServer | None = None

    print_banner(data_file)
    print_dashboard(library)
    print_summary(library)
    if not args.no_gui_server:
        try:
            gui_server = AlexandriaGUIServer(runtime=runtime, host=args.gui_host, port=max(0, args.gui_port))
            host, port = gui_server.start()
            print_status(f"GUI available at http://{host}:{port}", "ok")
            if args.open_gui:
                try:
                    webbrowser.open(f"http://{host}:{port}", new=2)
                except Exception:
                    pass
        except OSError as exc:
            print_status(f"GUI server could not start: {exc}", "warn")

    try:
        setup_autocomplete()
    except Exception:
        pass

    library, data_file = interactive_demo(library, data_file, runtime=runtime)
    runtime.library = library
    runtime.data_file = data_file

    try:
        library.save()
    except StorageError as exc:
        print_status(f"Final save failed: {exc}", "error")
    finally:
        if gui_server is not None:
            gui_server.stop()


if __name__ == "__main__":
    main()
