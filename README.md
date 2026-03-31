# Library Of Alexandria

A terminal-first personal library tracker with:

- a custom ASCII startup banner
- colorful status output and boxed tables
- automatic persistence after every change
- mixed catalog mode for books and sheet music
- goals, stats, import/export, backup/restore, and undo
- Obsidian vault export/sync/open integration with a Bases-first GUI, dashboards, MOCs, saved searches, bookmarks, and templates
- on-demand command help (clean startup, no command wall)

## Run

```bash
python3 main.py
```

Optional UI flags:

```bash
python3 main.py --theme ocean --compact
python3 main.py --no-color --no-motion
```

## Install System-Wide (User Install)

Recommended (no Python packaging dependencies):

```bash
./install.sh
```

Then start it anywhere with:

```bash
alexandria
```

If `alexandria` is not found, add your install dir to `PATH` (default is `~/.local/bin`):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Optional alternative (if `setuptools` is installed):

```bash
python3 -m pip install --user --no-build-isolation .
```

## Data Safety

- Data is auto-saved to `~/.library_of_alexandria/library_data.json` by default.
- If home storage is not writable, the app falls back to `/tmp/library_of_alexandria/library_data.json`.
- Saves are atomic (write temp file, then replace).
- Use `backup` to create timestamped snapshots in `backups/`.
- Use `undo` to revert the last in-session change.
- Use `restore` to load from backup/export JSON.

Optional custom data file:

```bash
LIBRARY_DATA_FILE=/path/to/your/library.json python3 main.py
```

## Commands (Updated)

Catalog and search:

- `add`, `edit`, `details`, `remove`, `check`
- `list`, `list full`, `list read`, `list unread`, `list sheet`
- `list genre <name>`, `list language <name>`, `list instrument <name>`, `list tag <name>`
- `sort by <field>`, `find title`, `find author`, `find composer`, `find notes`
- `search <query>` (advanced filters like `lang:german rating>=4 unread`)
- `metadata autofill [reference|all]`
- `dedup scan`, `dedup merge`
- `doctor [fix]`
- `authors`

Reading and progress:

- `mark read`, `mark unread`, `rate`, `progress`, `notes`
- `language`, `location`
- `tag add`, `tag remove`, `tag set`, `tag clear`
- `reading add`, `reading list`, `reading remove`
- `reading plan [weeks]`
- `reading smart preview [count]`, `reading smart generate [count]`, `reading smart append [count]`
- `interests set`, `interests show`, `interests clear`
- `goal show`, `goal set monthly`, `goal set yearly`, `goal clear monthly`, `goal clear yearly`
- `smart add`, `smart list`, `smart run`, `smart remove`

Sheet music:

- `practice`
- `practice log`
- `practice tempo`
- `series set`
- `series next [name]`
- `sheet stats`

Planning and workflow:

- `calendar add`, `calendar list [date]`, `calendar done`, `calendar streak [reading|practice]`
- `inbox add`, `inbox list`, `inbox process`, `inbox done`, `inbox remove`
- `snapshot create [name]`, `snapshot list`, `snapshot restore`
- `bulk edit`

AI and profiles:

- `profile show`, `profile list`, `profile new <name>`, `profile use <name>`
- `ai status`, `ai mode [safe|fast]`, `ai model <name>`, `ai recommend [count]`, `ai enrich [reference|all]`

Data, export, and Obsidian:

- `backup`, `restore`, `export`, `import`
- `export obsidian <vault_path>`
- `obsidian`, `obsidian sync [vault_path]`, `obsidian doctor [vault_path]`, `obsidian open [book-id|vault_path]`

UX and docs:

- `help [command]`, `man <command>`, `theme`, `compact`, `undo`, `history`, `quit`

## Smart Reading List

You can generate a recommendation-based reading list from personal interests:

1. Configure interests:

```bash
interests set
```

2. Preview recommendations:

```bash
reading smart preview 10
```

3. Write recommendations into your reading list:

```bash
reading smart generate 10   # replace list
reading smart append 5      # append to list
```

Interest profile fields include:

- genres (comma-separated)
- tags (comma-separated)
- authors (comma-separated)
- minimum rating
- preferred location (`Pforta` / `Zuhause` / any)
- unread preference

## Author Overview

Use the `authors` command to get a compact overview of your collection by author:

```bash
authors
```

It shows:

- number of stored items per author/composer
- main genres associated with each author
- main tags associated with each author

## Utility Commands

- `history` - show command history
- `help` - show command list or contextual help (`help progress`)
- `quit` - exit

Power aliases:

- `ls` -> `list`
- `rm` -> `remove`
- `q` -> `quit`
- `mr` -> `mark read`
- `mu` -> `mark unread`

## Obsidian Integration (Advanced)

Alexandria writes a managed folder:

- `<vault>/Alexandria`

### Managed-block sync + enforced template shape

Each generated note contains:

- `<!-- ALEXANDRIA:START -->`
- `<!-- ALEXANDRIA:END -->`

On `obsidian sync`, only this managed block is replaced.
Your own text in `Connections`, `Analysis`, and `Notes` sections remains intact.
Sync also re-enforces one stable note layout:

- `Metadata`
- `Connections`
- `Analysis`
- `Notes`

Sync also auto-cleans legacy duplicate Alexandria export roots in the same vault,
so one canonical managed root remains: `<vault>/Alexandria`.

### Rich frontmatter on every generated note

Every generated note follows one unified schema, including:

- `alexandria_schema`
- `managed_by`
- `type`
- `title`
- `alexandria_id`
- `item_type`
- `creator`
- `author`
- `composer`
- `language`
- `genre`
- `genres`
- `tags`
- `rating`
- `progress`
- `read`
- `location`
- `cover`
- `year`
- `pages`
- `isbn`
- `in_reading_list`
- `updated_at`

To avoid taxonomy confusion, Obsidian-exported tags are automatically filtered:
if a tag value matches any genre value, that tag is omitted from vault tag views/frontmatter.

### Bases-first GUI

Generated under `Alexandria/Bases/`:

- `All Items.base` (table + cards)
- `Unread.base`
- `Top Rated.base`
- `By Language.base`
- `By Genre.base`

Daily workflow entry point:

- `Alexandria/Dashboards/GUI Home.md`

Graph stays available, but is configured for exploration-only (`path:"Alexandria"`).

### Dashboards (Dataview-ready)

- `GUI Home`
- `Unread`
- `Top Rated`
- `By Language`
- `By Genre`
- `Reading List`
- `Progress`
- `Saved Searches`
- `Bookmarks`

MOC pages:

- `Library`
- `Authors`
- `Genres`
- `Tags`
- `Books`
- `Sheet Music`

Smart analysis pages:

- `Reading Velocity`
- `Unfinished High-Rated`
- `Neglected Genres`
- `Author Concentration`

Additional files:

- `Alexandria/Bases/*.base`
- `Alexandria/Templates/Book Template.md`
- `Alexandria/Templates/Sheet Music Template.md`
- `Alexandria/Reports/Sync Report.md`
- `Alexandria/Meta/note_index.json`
- `.obsidian/templates.json`
- `.obsidian/bookmarks.json`
- `.obsidian/workspace.json`
- `.obsidian/snippets/alexandria.css`

## Man Pages

This project includes dedicated man pages for every CLI command in `man/`.

- Open the command index:

```bash
man ./man/loa.1
```

- Open a specific command page (example):

```bash
man ./man/loa-location.1
man ./man/loa-import.1
```

Each page explains command usage, behavior, prompts, and examples.

## CLI Personalization

Use `theme` to personalize colors during a session:

```bash
theme                       # show active theme + palette
theme list                  # list all built-in themes
theme preview               # preview status colors live
theme sunset                # switch to built-in theme
theme set accent bright_cyan
theme set accent #35c2ff
theme set success bright_green
theme clear warning         # clear one override
theme clear                 # clear all overrides
theme color off             # disable ANSI colors in-session
theme color on              # re-enable colors
```

Notes:

- color roles are `accent`, `success`, `warning`, `error`
- supported color names are shown on invalid input hints (`#RRGGBB` is supported too)
- `theme list` shows a colored swatch preview for each built-in theme
- theme output is applied with explicit ANSI reset, so existing shell colors do not override app themes
- startup now shows banner + dashboard only; use `help` when you want the full command list

## Notes

- Every item gets a stable internal ID (`b0001`, `b0002`, ...).
- ISBN is optional. Commands that target one item accept `ID`, `ISBN`, or fuzzy `title/author/composer`.
- Duplicate protection:
  - same ISBN is rejected
  - `Book`: same title + author + language + cover is rejected
  - `SheetMusic`: same title + composer + instrumentation + catalog/work number + publisher is rejected
- Supported locations are exactly: `Pforta`, `Zuhause`.
- Supported languages are exactly: `German`, `English`, `French`, `Japanese`.
- Supported cover types are exactly: `Hardcover`, `Softcover`.
- Supported item types are exactly: `Book`, `SheetMusic`.
- Sheet-music metadata supports: composer, instrumentation, catalog/work number, key signature, era/style, difficulty, duration, publisher, practice status.
- Tags are stored as comma-separated labels and can be filtered via `list tag`.
- Smart lists can combine filters for read state, location, genre, min rating, and required tags.
- Smart reading recommendations are based on the saved interests profile and can auto-fill reading list entries.
