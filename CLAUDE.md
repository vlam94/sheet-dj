# sheet-dj

A local-only Flask app that builds a **set list** from band scores. The user loads one or more
MusicXML scores, each holding several songs back to back. They drag the songs into the order the
band will play them, then download one zip holding:

- `xyz.musicxml` — every song in the set list, in order, as one score;
- `xyz_tuba.csv` — one **tuba line** per song.

It installs in one step, launches from a desktop icon that opens the browser, and shuts itself down
once you stop using it.

**The product runs on Windows.** Development happens on Linux, but a feature is not done until it
works on Windows — see *Windows is the target platform*, below. The people using this are
musicians, not programmers. They will never open a terminal, read a log, or know what MusicXML is.
Design every visible surface for them.

This directory is self-contained. It does not read from, import from, or need to be compared
against anything outside itself. `PLAN.md` is the agreed design, the decision log, and the source of
truth for scope. Read it before making structural changes, and work through its steps in order.

## Domain vocabulary

Use these words in code and in conversation. They are the project's own terms, not generic ones.

- **score** — one uploaded MusicXML file: a multi-instrument band arrangement, usually holding
  several songs back to back.
- **song** — a run of measures that begins at a rehearsal mark; the mark's text is the song's
  title. Modelled as `Song`.
- **library** — every song from every score currently loaded. It lives in memory only.
- **set list** — the songs the user picked, in the order they will be played. This is what gets
  exported.
- **tuba part** — the part of a score identified as the tuba from its metadata.
- **tuba line** — the text form of one song's tuba part, written as one CSV row per song.
- **cycle** — the shortest block of measures that, repeated, makes up a song's whole tuba part.
- **group** — `( … ) xN`: a block of measures written once and played N times back to back.
- **gap measure** — a measure with only rests in every part, sitting between two songs. It usually
  carries the next song's tempo or key change.

## How a score is split into songs

1. A song starts at every measure that holds a rehearsal mark
   (`<direction><direction-type><rehearsal>`). MuseScore puts the mark on the top part only, so
   marks are collected from **all** parts. They are matched by **measure index**, not by the
   `number` attribute, because numbers can repeat or be missing on pickups.
2. A mark whose text equals the current song's title **continues** that song; it does not start a
   new one. Real scores repeat the mark at a section change inside the same song.
3. Measures before the first mark become a song if they contain any notes. Its title is
   `<work-title>`, else `<movement-title>`, else the file name without extension. If they hold only
   rests, they are dropped. A score with no marks at all is therefore one song.
4. Gap measures at the end of a song are trimmed from it. The next song still gets the tempo and key
   they carried, because slicing a song collects its context (key, time, clef, instrument, tempo)
   onto its first measure.
5. Song ids are random (`uuid4().hex`), never positions. Two scores may both contain a song called
   "Love Story".

## The tuba line (the notation)

The CSV has no header. Each row is `Title,line`, written by the `csv` module, so a title containing
a comma gets quoted. A song whose score has no tuba part gets an empty line (`Title,`).

The line format:

- Measures are joined by ` | ` and notes by a single space.
- A group is `( m1 | m2 ) xN`.
- Plain runs of measures and groups are separated by one space.
- An octave move is an arrow straight after the note name: `↑` or `↓`, repeated if the move is more
  than one octave.

```
Love Story,F | Ab | Db↓ Eb | F
Blue Monday,( Ab G | F ) x3 Bb Eb↓ | F
What's Next,Bb | A ( D↓ | F ) x2 G
```

### Writing rules

These are the whole contract. `notation.py` implements them, and `tests/test_notation.py` pins each
one.

1. **Extract.** Take the song's measures from the tuba part with repeats and voltas (1st/2nd
   endings) expanded. In each measure, keep the note attacks in order:
   - skip rests, grace notes, and the continuation of a tie (`tie` type `stop` or `continue`; only
     the tie's starting note counts);
   - a chord contributes its lowest pitch;
   - use the pitch **as written** in the part, which is what the player reads, with no
     transposition;
   - collapse consecutive identical pitches inside one measure, because the line carries pitch
     changes, not rhythm;
   - drop a measure that ends up empty, because the notation has no rest symbol.

   Call the result `M`, a list of measures. Measures are compared by MIDI number, never by
   spelling.
2. **Cycle.** Find the smallest `p` with `len(M) >= 2p` and `M[i] == M[i % p]` for every `i`. The
   last repetition may be cut short. If there is such a `p`, write `M[:p]`; otherwise write all of
   `M`.
3. **One-measure cycle.** If `p == 1`, write that measure four times as plain measures:
   `Bb | Bb | Bb | Bb`.
4. **Folding.** Go through what is being written, left to right:
   - At each position, look for a block of **two or more measures** repeated back to back **two or
     more** times.
   - If there is one, prefer the block covering the most measures (on a tie, the shorter block),
     write it as a group, and continue after it.
   - Otherwise write the measure plainly and move on.

   Single repeated measures are never folded (`F | F` stays as written). Groups are never nested,
   and `x1` is never written.
5. **Spelling.** A note name is the step plus `#` or `b`, taken from the score's own spelling. The
   result is always one of the 17 names `C C# Db D D# Eb E F F# Gb G G# Ab A A# Bb B`. Double
   accidentals and `E# B# Cb Fb` are respelled to the enharmonic in that set.
6. **Arrows (nearest neighbour).** The first written note is bare. For every later note, in reading
   order:
   - `d` = its MIDI number minus the previous note's MIDI number;
   - `r = ((d + 5) mod 12) − 5`, which lies in −5…+6, so a tritone counts as *up*;
   - `k = (d − r) / 12`.

   `k == 0` means bare, `k > 0` means `k`×`↑`, and `k < 0` means `|k|`×`↓`. In plain words: a note
   is read at the closest position to the note before it, and an arrow means "the other way".
7. **Reading groups.** The first note of a group is relative to the note before the group. Every
   repetition of a group has the same pitches, so the jump from a group's end back to its start is
   never a reading context. The note after a group is relative to the group's last note.
8. **No absolute octave.** The line does not say which octave it starts in; the player knows the
   instrument's register. Round-trip tests therefore compare note names and intervals, not
   absolute octaves.

Worked example of rule 6: from A2 to D2, `d = −7`, `r = 5`, `k = −1`, so the line reads `A | D↓`.
Without the arrow, D would be read a fourth *up*.

### Where the tuba part comes from

A score's tuba part is the first part that meets either condition:

- music21 gives it an `instrument.Tuba`, or a MIDI program of 58 (music21 counts from 0; MusicXML's
  `<midi-program>59` is the tuba);
- its part name, abbreviation or instrument name matches `tuba|sousaf|sousaph|helicon`, ignoring
  case.

If no part matches, the score still loads, its songs get empty lines, and the page shows warning
E07.

## The set-list score

`assembly.py` builds the exported `.musicxml` from the set list:

- **Output parts** are the union of all source parts in order of first appearance, matched by part
  name. Matching ignores case and surrounding whitespace.
- **The tuba part is canonical.** Each song's detected tuba part goes into one output part called
  "Tuba", whatever its source name was. This keeps a set list with one "Tuba" and one "Baixo"
  source in a single tuba part.
- **Missing parts.** A song that lacks a part gets full-measure rests in that part for its
  measures.
- **Context.** Each song's first measure carries its title as a rehearsal mark on the top part,
  plus its key, time, clef and tempo. Re-importing the exported file therefore gives back the same
  songs, in the same order, with the same tuba lines; `tests/test_export.py` relies on this.
  Exception: two adjacent songs with the same title merge on re-import (rule 2 of the split).
- **Numbering and title.** Measures are renumbered from 1. The score title is the output name.
- **Repeats** are kept as written; they are only expanded when reading a tuba line.

## Architecture: pure core, imperative shell

This split is the main structural rule. Keep it.

**Pure core:** `model.py`, `notation.py`, `export.py`, and the music21 boundary modules
`parsing.py` and `assembly.py`. They contain no Flask, no `request`, no environment reads and no
`print`. Functions take data and return data. Everything worth testing lives here and is tested
without a request context.

- `notation.py` is the writing rules above. It knows nothing about music21: it takes measures of
  `Note(name, midi)` and returns a string.
- `parsing.py` turns score bytes and a file name into `ParsedScore` (songs plus the music21 score).
  It converts every music21 or XML failure into one `ScoreError` that carries a user-facing
  message and a catalogue id.
- `assembly.py` turns an ordered list of song references into `.musicxml` bytes.
- `export.py` turns a set list into csv bytes and zip bytes.
- **Only `parsing.py` and `assembly.py` import music21.** No other module imports it, not even to
  catch an exception.

**Imperative shell:** `library.py`, `views.py`, `server.py`, `config.py`, and in Phase 2
`launcher.py` and `idle.py`. These own state, I/O, HTTP and process lifetime. Keep them thin enough
that a bug is unlikely to hide in them.

- `library.py` is the only stateful object: the in-memory library behind a `threading.Lock`.
  Scores are parsed once at upload and treated as read-only afterwards. Assembly works on copies.

If you are tempted to import `flask` into `notation.py`, or to pass a `FileStorage` into
`parsing.py`, the boundary is being crossed and the design needs a different shape.

## Prefer an existing package over new code

This is an explicit constraint from the user, and it is stronger than the usual preference. Before
writing a helper, check whether a well-maintained package already does the job, and use that.

| need | package |
|---|---|
| MusicXML read/write, repeats, measure slicing with context, `.mxl` containers | `music21` |
| web app / WSGI server (Windows-friendly, no fork) | `flask` / `waitress` |
| Windows-safe output file names | `pathvalidate` |
| per-user log directory | `platformdirs` |
| CSV and zip | `csv`, `zipfile` (stdlib) |
| drag and drop with Ctrl/Shift multi-select | SortableJS + MultiDrag (vendored JS) |
| minimal pleasant styling | Pico.css (vendored CSS) |

The deliberate exceptions, each small:

- `notation.py` — it encodes this project's own notation, so by definition nothing external
  implements it.
- `idle.py` (Phase 2) — an idle-shutdown watchdog of roughly twenty lines of `threading`. It stops
  waitress through waitress's own API, not with `SIGTERM`; on Windows,
  `os.kill(pid, SIGTERM)` is `TerminateProcess`, a hard kill.
- Range selection with Shift-click, about 15 lines of JS, **only if** the Step 0 spike shows that
  MultiDrag lacks it. Record the spike result in `PLAN.md` before writing it.

Any further exception needs a justification added here.

## User-friendly by default

The user is a musician with scores exported from MuseScore and no interest in how this works.
Every decision about the visible surface follows from that.

- **Zero required choices.** Loading files and pressing one button must produce a correct zip:
  - the tuba part is detected;
  - the output name defaults to the first score's name;
  - Shuffle and *Random n* are shortcuts, never steps.
- **Plain words.** No "MusicXML parse error", "part id", "413", or exception class names on the
  page. Say "score", "song", "instrument", "file too large". Terms the musicians already use (set
  list, tuba, rehearsal mark) are fine.
- **Every message answers three things:** what went wrong, in the user's terms; which file it
  concerns (name it); and what to do next. For example: "Could not read *show.mscz*. This is a
  MuseScore project file — open it in MuseScore, use *File → Export → MusicXML*, and add that file
  instead." Not "Unsupported file type".
- **One bad file never blocks the others.** When several files are added at once, the good ones
  load and each bad one gets its own message.
- **Keep the user's work.**
  - A failed export re-renders the page with the set list and the output name intact.
  - Reloading the page keeps the loaded songs, because they are on the server.
  - The set-list order is kept in `sessionStorage`. Every access is wrapped in try/catch, because
    storage can be unavailable.
- **Both mouse and keyboard work.** Every drag action has a button too: Add →, ← Remove, Move up,
  Move down, Select all. Double-clicking a song moves it to the other list.
- **Nothing to manage.** No terminal window left open, no process to kill, no files to clean up.
  A second click on the icon opens a tab; walking away shuts it down.
- The launcher is the one place a failure can happen with no page to show it on. There, show a
  native dialog (`tkinter.messagebox`, which ships with the Windows Python installer) with the same
  three-part message, not a console that flashes and vanishes.

## Human errors are the main test surface

Wrong input is the normal case for this app, not the edge case. The mistakes it handles are listed
once, in the **Error catalogue** in `PLAN.md`. Each has an ID (`E01`, `E02`, …), the module that
catches it, and its message. That table is the single source of truth: do not copy it here or
anywhere else, and refer to entries by ID.

Every catalogue entry has a test that asserts all of the following:

- the **exact user-facing message**, or a stable fragment of it;
- that the response is a rendered page, not a traceback;
- that the user's work survived: the loaded songs, the set list and the output name.

Put them in one parametrized test per layer: `test_views.py` for upload and export cases,
`test_launcher.py` for launcher cases. Use the catalogue ID as the test case id
(`pytest.param(..., id="E02")`), so each row maps to exactly one test and `pytest -k E02` finds it.

When a real user hits a mistake not in the catalogue:

1. add a row to `PLAN.md` with the next free ID;
2. add a failing test;
3. then fix it.

When a message's wording changes, change it in the catalogue and the test together.

`ScoreError` carries a user-facing message, written where the failure is understood (in
`parsing.py`). `views.py` renders that message; it does not compose its own from exception text.
Never show `str(exc)` from a third-party library to the user. Log it, and show the plain message.

## Test fixtures

`tests/fixtures/` holds these files:

- `input/<name>.musicxml` — one score per concern.
- `output/<name>.csv` — the tuba CSV you get by exporting **all** of that score's songs in source
  order. It is stored as UTF-8 **without** the BOM; one dedicated test checks the BOM on the real
  export.
- `output/<name>.error` — for an input expected to fail; holds only the catalogue ID (`E05`).
- `scenarios/<name>/` — multi-file export cases. Each has three files:
  - `inputs.txt`: the fixture file names to load, in order;
  - `order.txt`: the set list, given as titles;
  - `expected.csv`: the result.

  The scenario test exports, re-imports the `.musicxml`, and compares titles and lines.

`tests/fixtures/README.md` lists each fixture's concern.

Fixture rules:

- **Hand-authored minimal MusicXML only.** A few measures each, two parts (Trombone + Tuba) unless
  the concern is about parts. Do not copy real scores into `tests/`; they are large, they drown the
  case under test, and their licensing is someone else's. Real scores belong in `examples/`, for
  manual smoke tests only.
- **Expected outputs are derived by hand from the writing rules, never generated by running the
  implementation.** A golden file regenerated from the code tests nothing.
- **Ties need both elements.** A tied note needs `<tie type="…"/>` (the sound element, which music21
  reads) as well as `<notations><tied/></notations>` (the drawing, which it ignores). MuseScore
  writes both, and a fixture with only `<tied>` silently tests nothing.

Prefer asserting the final text end to end over poking at intermediate objects; the text is what
the user actually gets. Compare as UTF-8 text with normalized line endings, so the same test passes
on Windows.

## Clean code and Python practice

- **Python 3.12+**, `src/` layout (`src/sheet_dj/`), everything declared in `pyproject.toml`. No
  `requirements.txt` alongside it.
- `ruff` for linting and formatting, `mypy --strict` for types; both run clean before a change is
  done. Configure them in `pyproject.toml`, not in separate dotfiles. music21 has no type stubs;
  give it an `ignore_missing_imports` override, and keep music21 objects behind typed functions in
  `parsing.py` and `assembly.py`.
- Type-annotate every function signature. Prefer `frozen=True` dataclasses over dicts and tuples
  for anything crossing a module boundary. Use `Enum` over magic strings for closed sets.
- Small functions that do one thing, named with the domain vocabulary above. If a function needs a
  comment explaining *what* it does, it needs a better name or a split; comments explain *why*.
- Docstrings on public functions, one line unless the behaviour genuinely needs more.
- No bare `except:` and no `except Exception` outside two places: the single top-level handler in
  the shell, which turns an unexpected error into a friendly page plus a logged traceback, and the
  one place in `parsing.py` where music21's open-ended failures become `ScoreError`.
- `logging`, never `print`, in the shell. The pure core does not log.
- Constants at module top in `UPPER_CASE`; no mutable default arguments; no module-level side
  effects beyond definitions. The app is built in `create_app()`, not at import time, and the
  library is created there too, not as a module global.
- Write the test first when fixing a bug: a failing test that reproduces it, then the fix.

## Windows is the target platform

Code is written on Linux and shipped to Windows. These rules keep it portable:

- **`pathlib.Path` for every path**, never string concatenation with `/`. Per-user locations come
  from `platformdirs` (`user_log_dir("sheet_dj")`), never a hardcoded `~/.cache`.
- **Always pass `encoding="utf-8"`** when opening text. Windows' default is `cp1252`, which cannot
  hold `♭`, `↑`, or `ré`.
- **The exported CSV is UTF-8 with a BOM** (`utf-8-sig`), so Excel on Windows shows the arrows. The
  zip is served as `application/zip` with a `Content-Disposition` file name.
- **Temp files:** a `NamedTemporaryFile` that is still open cannot be reopened by name on Windows.
  Create it with `delete=False`, write, close, parse, and `unlink` in the `finally`. Prefer parsing
  from bytes where music21 allows it.
- **Output names go through `pathvalidate.sanitize_filename(..., platform="windows")`** even when
  developing on Linux.
- **No POSIX-only process calls.** No `signal.SIGTERM` for shutdown, and no `start_new_session`
  without its Windows counterpart. The launcher spawns the server detached with no console window
  (`DETACHED_PROCESS | CREATE_NO_WINDOW` on Windows); isolate that branch in one function.
- **No console windows.** The icon's entry point is a `[project.gui-scripts]` entry, so Windows
  builds it as a windowless `.exe`.
- The icon ships as `.ico` for Windows alongside the `.svg`.
- Keep platform branches (`sys.platform == "win32"`) inside the shell, and keep them few. Cover
  each one with a test that runs on both platforms, or that is explicitly skipped on one with a
  reason.

### How it is tested from Linux

Three layers, cheapest first:

1. **Every change, locally on Linux:** `pytest`, `ruff`, `mypy`. Also run the suite once with
   `PYTHONUTF8=0 LC_ALL=C` to flush out code that silently relies on a UTF-8 default encoding.
2. **Every push, CI on real Windows:** a GitHub Actions matrix of `ubuntu-latest` and
   `windows-latest` running the same commands. This is the check that actually proves Windows
   compatibility; a Windows-only failure blocks the change like any other.
3. **Before handing a build to users, a Windows VM.** Install, click the icon, load scores, build
   and download a set list, click again, leave it idle, uninstall. The checklist is in `PLAN.md`
   *Phase 2*. On Manjaro, `quickemu` (`quickget windows 11`) produces a working VM without a
   licence key. Wine is not a substitute; it does not behave like Windows for venvs, process
   spawning, or shortcuts.

## Running

For development on Linux:

```sh
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest                               # tests
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy src
.venv/bin/python -m sheet_dj.server            # serve in the foreground on 127.0.0.1:5118
.venv/bin/sheet-dj                             # Phase 2: what the icon runs (start-or-attach, open browser)
```

Configuration is environment-driven and read once into `Config`:

| variable | default |
|---|---|
| `SHEETDJ_PORT` | 5118 |
| `SHEETDJ_IDLE_MINUTES` | 20 |
| `SHEETDJ_MAX_UPLOAD_MB` | 20 |
| `SHEETDJ_MAX_FILES` | 20 |

The server log lives in `platformdirs.user_log_dir("sheet_dj")`:

- Windows: `%LOCALAPPDATA%\sheet_dj\Logs\server.log`
- Linux: `~/.local/state/sheet_dj/log/server.log`

## Conventions

- Failures reaching the user are plain-language messages rendered into the page. A traceback in
  the browser is a bug; see *Human errors are the main test surface*.
- **The library in memory is the only state, by design.**
  - Nothing persistent is written: no database, no uploads directory, no job queue.
  - Uploads are parsed and discarded.
  - The zip is built in a `BytesIO`.
  - When the app shuts down, the library is gone. That is expected: the user adds the scores
    again (catalogue E09 covers a set list that outlived its library).
- The server binds `127.0.0.1` only. It has no authentication. Do not change the binding unless
  the user asks for it.
- No CDN links in templates. JS and CSS are vendored into `static/` with their licence files, so
  the app works offline.
- `examples/` is for humans and manual smoke tests. Tests never read from it.
