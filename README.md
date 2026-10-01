# sheet-dj

A local-only web app that builds a **set list** from band scores.

Load one or more MusicXML scores (exported from MuseScore), each holding several songs back to
back. Drag the songs into the order the band will play them, then download one zip containing:

- `<name>.musicxml`: every song of the set list, in order, as one score;
- `<name>_tuba.csv`: one **tuba line** per song, written as text, for example
  `Love Story,F | Ab | Db↓ Eb | F`.

The app runs on your own machine and binds to `127.0.0.1` only. It has no login, and nothing is
written to disk apart from a log file: loaded scores live in memory until the app stops.

> **Status:** Phase 1 (the app, running on Linux) is done. Phase 2 (Windows launcher, idle shutdown,
> installer) is not started. See [`PLAN.md`](PLAN.md).

## How it works

- A **song** starts at each rehearsal mark in a score. The mark's text is the song's title.
- The **tuba part** is found from the score's metadata (a Tuba instrument, MIDI program 59, or a
  part named tuba/sousaphone/helicon). A score without one still loads; its tuba lines are empty.
- The **tuba line** follows fixed writing rules (cycles, `( … ) xN` groups, `↑`/`↓` octave arrows).
  The rules are in [`CLAUDE.md`](CLAUDE.md), and `tests/test_notation.py` pins each one.
- Files accepted: `.musicxml`, `.xml`, `.mxl`. MuseScore project files (`.mscz`), PDFs and images
  get a message that says how to export MusicXML instead.

## Run it locally on Linux

Requirements: Python 3.12 or newer.

```sh
git clone <this repository> sheet-dj
cd sheet-dj

python -m venv .venv
.venv/bin/pip install -e .

.venv/bin/python -m sheet_dj.server
```

Then open <http://127.0.0.1:5118> in a browser. Stop the server with Ctrl+C.

The `sheet-dj-server` command installed in the venv does the same thing:

```sh
.venv/bin/sheet-dj-server
```

### Using it

1. Click **Choose Files**, pick one or more score files, then click **Add scores**. You can also
   drop files anywhere on the page.
2. Select songs: click one, Ctrl-click to add to the selection, Shift-click for a range.
3. Move them to the **Set list** by dragging, double-clicking, pressing Enter, or with **Add →**.
   **Remove**, **Move up**, **Move down**, **Shuffle** and **Random** (moves *n* random songs) help
   with the order.
4. Edit the **Output name** if you like and click **Download set list**.

Reloading the page keeps the loaded songs and your set list. Stopping the server forgets the
scores; add them again.

### Configuration

Set these environment variables before starting the server:

| variable | default | meaning |
|---|---|---|
| `SHEETDJ_PORT` | 5118 | port to listen on |
| `SHEETDJ_IDLE_MINUTES` | 20 | reserved for Phase 2 (idle shutdown) |
| `SHEETDJ_MAX_UPLOAD_MB` | 20 | largest upload accepted at once |
| `SHEETDJ_MAX_FILES` | 20 | most scores loaded at once |

```sh
SHEETDJ_PORT=6000 .venv/bin/python -m sheet_dj.server
```

The server log is at `~/.local/state/sheet_dj/log/server.log`.

## Development

```sh
.venv/bin/pip install -e '.[dev]'

.venv/bin/pytest                                   # unit and view tests
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
PYTHONUTF8=0 LC_ALL=C .venv/bin/pytest             # catches reliance on a UTF-8 default
```

Browser tests (Playwright) are opt-in:

```sh
.venv/bin/pip install -e '.[e2e]'
.venv/bin/playwright install chromium firefox
.venv/bin/pytest -m e2e --browser chromium --browser firefox
```

### Layout

```
src/sheet_dj/
  model.py  notation.py  export.py        pure core (no Flask, no music21 in notation/export)
  parsing.py  assembly.py                 the only modules that import music21
  library.py  views.py  server.py  config.py   shell: state, HTTP, process
  templates/  static/                     the page; SortableJS and Pico.css are vendored
tests/
  fixtures/                               hand-written scores and expected outputs
  e2e/                                    browser tests
```

- [`CLAUDE.md`](CLAUDE.md): the vocabulary, the tuba-line rules, the architecture and the testing
  rules.
- [`PLAN.md`](PLAN.md): the design decisions, the error catalogue (E01–E12) and the steps.
- [`examples/`](examples): a real score for manual smoke tests (tests never read from it).

## Licences

SortableJS (MIT) and Pico.css (MIT) are vendored in `src/sheet_dj/static/vendor/` with their licence
files. The app loads nothing from the network.
