# sheet-dj — plan

This is the agreed design and the order of work. `CLAUDE.md` holds the standing rules: the
vocabulary, the tuba-line writing rules, the architecture, and the testing discipline. This file
holds the decisions, the error catalogue and the steps.

**How to use it:**

- Steps are executed one at a time, when asked ("do Step 2").
- A step is done when its *Done when* list holds **and** `pytest`, `ruff` and `mypy` are clean.
- Tick the step's checkbox and add anything learned under it. Spike results go into the step
  itself, not into a new file.
- Phase 1 ends with the app running on a local Linux server. Phase 2 makes it a Windows product.

---

## Scope

**In:**

- Load one or many multi-instrument MusicXML scores (`.musicxml`, `.xml`, `.mxl`).
- Split each score into songs at rehearsal marks and hold them in memory.
- List the songs.
- Build a set list by dragging, with Ctrl and Shift multi-select and button equivalents.
- Shuffle the set list, or move *n* random songs into it.
- Edit the output name.
- Download `{name}.zip`, containing `{name}.musicxml` (the set list as one score) and
  `{name}_tuba.csv` (one tuba line per song, in set-list order).

**Out:**

- Editing notes.
- Playing audio.
- Reading PDFs or `.mscz`. Those are friendly errors that tell the user how to export MusicXML.
- Saving set lists between sessions.
- Multiple users, or access from another machine.
- Rendering sheet music in the browser.

---

## Decision log

Each entry gives the decision, why, and the alternative that was rejected. Entries marked
**[confirm]** were taken by default during planning; change them before the step that uses them if
the user disagrees.

**D1. Flask + waitress, a browser UI, bound to `127.0.0.1:5118`.**
- *Why:* the same shape as the sibling app the users already run. waitress is pure Python and has
  no fork, so it behaves the same on Windows.
- *Port:* 5118 rather than 5117, so the two apps can run side by side.
- *Rejected:* a desktop GUI toolkit such as Qt or Tk (no browser). It is harder to make pleasant,
  and drag and drop with multi-select is far more work there than with an existing JS library.

**D2. music21 is the only MusicXML library.**
- *Uses:* parsing, rehearsal marks, `expandRepeats()`, measure slicing with context
  (`Part.measures(a, b, collect=(...Clef, TimeSignature, KeySignature, Instrument,
  MetronomeMark))`), and writing back to MusicXML bytes (`musicxml.m21ToXml.GeneralObjectExporter`).
- *Why:* it already handles `<divisions>` differences between files, carrying attributes forward,
  `.mxl` containers, ties and transposition.
- *Rejected:* splicing raw XML with lxml. It would keep the file byte-faithful, but every one of
  those cases would become our code.
- **Gate:** Step 0 checks this against real scores. If slicing loses voltas, repeats or ties, stop
  and revisit before Step 3.

**D3. State is an in-memory library, as the user asked.**
- One process-wide `Library`, because there is one user on the local machine. It is guarded by a
  `threading.Lock`.
- It holds each loaded score's music21 object (read-only after parsing) and its `Song` records,
  with tuba lines **precomputed at upload**. Errors therefore appear when the user adds a file, and
  export only assembles.
- *Two tabs share one library.* That is acceptable, and arguably what the user expects.
- *Rejected:* a stateless server where the browser re-sends the files on export. It would mean
  reparsing on every download (about 1–2 s per large score) and a heavier page.
- *Rejected:* a session or database. There is nothing worth persisting.

**D4. Song splitting rules** are in `CLAUDE.md` *How a score is split into songs*. They cover:
- marks from any part, matched by measure index;
- a repeated mark continuing the current song;
- the untitled leading section;
- gap-measure trimming;
- uuid song ids.

**D5. The tuba line follows nearest-neighbour arrows and is a minimal cycle or the whole line.**
- The rules are in `CLAUDE.md` *Writing rules*; this part was confirmed with the user.
- They were derived from an older hand-written format and its converter.
- They deliberately fix that converter's inconsistent arrow handling. Arrows are now computed from
  semitone distance, and the rule is the same for ↑ and ↓.
- **[confirm]** A one-measure cycle with several notes is written four times, like the
  single-note case: `F Ab | F Ab | F Ab | F Ab`.
- **[confirm]** Rest-only measures are dropped from the tuba line, because there is no rest
  symbol.
- **[confirm]** The line uses written pitch, not sounding pitch. This matters only for a transposing
  tuba part.

**D6. Tuba detection uses metadata, and a missing tuba is a warning, not an error.**
- The rules are in `CLAUDE.md` *Where the tuba part comes from*.
- Inputs are multi-instrument band scores. If a score has no tuba part, the user may still want its
  songs in the set list, so the score loads and warning E07 is shown.

**D7. Set-list assembly** follows `CLAUDE.md` *The set-list score*:
- the union of parts, matched by name;
- one canonical "Tuba" part;
- rests for missing parts;
- a rehearsal mark and the full context at each song start;
- renumbered measures.

*Why:* the export must re-import to the same song list. That round trip is the main end-to-end
test.

**D8. The front end is SortableJS + MultiDrag, plus plain JS and Pico.css, all vendored.**
- *Mouse:* Ctrl/⌘-click toggles a song's selection, Shift-click selects a range, and dragging a
  selection moves it between the lists.
- *Buttons:* every drag action also has a button.
- *Rejected:* native HTML5 drag and drop with our own selection logic, which is more code and
  violates the package rule.
- *Rejected:* htmx or a JS framework, which isn't needed for one page.

**D9. Output name.**
- A text field, defaulting to the stem of the first loaded score.
- Sanitised with `pathvalidate.sanitize_filename(platform="windows")`.
- If it is empty after sanitising, the default is used.

**D10. CSV format.**
- **[confirm]** **UTF-8 with BOM** (`utf-8-sig`) and CRLF, the `csv` module's default for Excel.
  Excel on Windows shows ♭ and ↑ correctly only with the BOM.
- No header row.
- The encoding is one constant, `CSV_ENCODING`, in `export.py`, so flipping it is a one-line
  change.

**D11. Nothing touches the disk.**
- Uploads are parsed from bytes where music21 allows. Otherwise they go through a `delete=False`
  temp file that is unlinked in `finally`.
- The zip is built in a `BytesIO`, and the `.musicxml` inside it is stored uncompressed.

**D12. Testing.** Three layers:
- golden fixtures, from input score to expected csv or `.error`;
- one parametrised test per layer for the error catalogue;
- the export → re-import scenario.

Optional: one Playwright smoke test for drag, Shuffle and Random n, kept behind a `pytest -m e2e`
marker and the `e2e` extra.

**D13. UI language.**
- **[confirm]** Messages are in English, as written in the catalogue below. The users speak
  Portuguese; if the UI should be Portuguese, translate the catalogue column and the templates
  **before Step 5**.
- No i18n library: one language, plain strings.

**D14. The Windows packaging route is left open until Phase 2 starts.** See the options there.

---

## Module map (`src/sheet_dj/`)

| module | layer | contents |
|---|---|---|
| `model.py` | core | frozen dataclasses: `Note(name: str, midi: int)`; `Song(id, title, score_name, first_measure, last_measure, tuba_line)`; `ScoreSummary(name, digest, songs, tuba_part_name: str \| None)` |
| `notation.py` | core | `write_tuba_line(measures: Sequence[Sequence[Note]]) -> str`, built from small helpers: `find_cycle`, `fold_groups`, `spell`, `arrow` |
| `parsing.py` | core, music21 boundary | `parse_score(data: bytes, filename: str) -> ParsedScore`; `ScoreError(catalogue_id, message)` |
| `assembly.py` | core, music21 boundary | `assemble_set_list(songs: Sequence[SongRef], title: str) -> bytes` |
| `export.py` | core | `tuba_csv(songs) -> bytes`; `set_list_zip(name, musicxml, csv) -> bytes`; `CSV_ENCODING` |
| `library.py` | shell | `Library`: `add(data, filename)`, `clear()`, `songs()`, `resolve(ids)`; lock; limits |
| `views.py` | shell | blueprint: routes, error rendering, the single top-level handler |
| `config.py` | shell | `Config` dataclass read from the environment once |
| `server.py` | shell | `create_app()`, logging setup, `main()` → `waitress.serve` |
| `templates/index.html`, `static/` | shell | the page; vendored `Sortable.min.js`, `pico.min.css`, their licence files, and `app.js` |
| `launcher.py`, `idle.py` | shell | Phase 2 |

The music21 score object travels as an opaque field of `ParsedScore`, which lives in
`parsing.py`. Only `parsing.py` and `assembly.py` look inside it.

## HTTP endpoints

| method | path | does |
|---|---|---|
| GET | `/` | Renders the page: loaded scores (with tuba-part status), the song list, an empty set list and the default name. |
| POST | `/scores` | Multipart field `scores` (many files). Each file is parsed and added independently; renders `/` with one notice per file. |
| POST | `/scores/clear` | Empties the library and redirects to `/`. |
| POST | `/export` | Form fields `song` (repeated, in set-list order) and `name`. Returns `{name}.zip` as an attachment, or renders `/` with the error, the set list and the name preserved. |

`MAX_CONTENT_LENGTH` is `SHEETDJ_MAX_UPLOAD_MB`. A 413 is caught and rendered as E04.

## UI (one page)

1. **Header.** An *Add scores* file picker (multiple; it also accepts a drop onto the page) and
   *Clear all*. Below it, one chip per loaded score:
   - "Tuba part: *Tuba*", or
   - the E07 warning.
2. **Two lists side by side: *Songs* and *Set list*.**
   - Each card shows the title, the score name in small type, and the tuba line in monospace.
   - Selection: click selects one; Ctrl/⌘-click toggles one; Shift-click selects a range.
   - Moving songs: drag the selection between or within the lists, or double-click a song to move
     it across.
3. **Buttons between the lists:**
   - Add →
   - ← Remove
   - Move up
   - Move down
   - Select all, in each list
4. **Above the set list:**
   - **Shuffle** randomises the set list in place (Fisher–Yates in JS).
   - **Random [n]** moves *n* random songs from *Songs* to the end of the set list. `n` is clamped
     to the number available; if `n` is 0 or empty, nothing happens.
5. **Footer.**
   - An *Output name* field, pre-filled.
   - A **Download set list** button, which submits the form with the set list's ids as hidden
     inputs.

On page load, the set list is restored from `sessionStorage`; ids that are no longer in the library
are ignored.

---

## Error catalogue (single source of truth)

`{file}` is the file name as uploaded, shown in italics; `{n}` is the configured limit. Tests assert
these messages verbatim or by a stable fragment; change both together.

| id | situation | caught in | message |
|---|---|---|---|
| E01 | Add pressed with no file chosen | `views.py` | No score was chosen. Click *Add scores* and pick one or more MusicXML files exported from MuseScore. |
| E02 | `.mscz` / `.mscx` file | `parsing.py` | Could not read *{file}*. This is a MuseScore project file — open it in MuseScore, use *File → Export → MusicXML*, and add that file instead. |
| E03 | PDF or image file | `parsing.py` | *{file}* is a picture or PDF of sheet music, not a score file. Open the score in MuseScore and use *File → Export → MusicXML*, then add that file. |
| E04 | upload larger than the limit | `views.py` | These files are too large to add at once (limit {n} MB). Add them a few at a time. |
| E05 | unreadable, damaged, or not MusicXML | `parsing.py` | Could not read *{file}*. It looks damaged or is not a MusicXML score. Export it again from MuseScore (*File → Export → MusicXML*) and add the new file. |
| E06 | a score with no notes | `parsing.py` | *{file}* has no notes in it. Check that you exported the full score and not an empty part. |
| E07 | no tuba part (warning; the score still loads) | `parsing.py` | No tuba part was found in *{file}*. Its songs were added, but their tuba lines are empty. If the score has a tuba, name its part "Tuba" in MuseScore and export again. |
| E08 | Download pressed with an empty set list | `views.py` | The set list is empty. Move songs from *Songs* into *Set list* first, then download. |
| E09 | the set list names songs that are no longer loaded (the app restarted) | `library.py` | Some songs in your set list are no longer loaded — the app was closed while idle. Add your scores again and rebuild the set list. |
| E10 | the same file added twice (same content) | `library.py` | *{file}* is already loaded, so it was skipped. |
| E11 | more scores than the limit | `library.py` | Only {n} scores can be loaded at once. Use *Clear all* and add the ones you need. |

Launcher cases (Phase 2) start at **E20**.

---

## Phase 1 — local server on Linux

### [x] Step 0 — Spike (scratch only; record the results here)
Answer each question with evidence, using `tests/fixtures/input/*` and
`examples/eletro_farra_trombone.musicxml`:

1. Does `Part.measures(a, b, collect=...)`, run on each part, keep:
   - repeat barlines;
   - voltas (the `RepeatBracket` spanners);
   - ties across the slice;
   - the key, tempo and time context from the gap measure before the song?
2. Does `expandRepeats()` work on one song's slice, and on `repeats_and_voltas`?
3. How long does parsing the 267 KB example take? Is `converter.parseData(bytes)` enough for both
   `.musicxml` and `.mxl`, or is a temp file needed?
4. Does building a new `Score` from slices of two different files, then exporting with
   `GeneralObjectExporter` to bytes, open in MuseScore (`mscore out.musicxml`) with repeats intact?
   Does re-parsing it find the inserted rehearsal marks?
5. How are instruments detected? What does music21 give for the "Baixo" part with
   `<midi-program>59` in `tuba_by_midi_program`?
6. Does SortableJS MultiDrag support Shift-click range selection out of the box? Which versions of
   Sortable and Pico should be vendored?

*Done when:* each question has a short answer here, and D2 is confirmed or reopened.

**Results** (music21 10.5.0, Python 3.12, MuseScore 4.7.4):

1. **Slicing keeps what we need.** `Part.measures(a, b, indicesNotNumbers=True)` keeps repeat
   barlines, the `RepeatBracket` spanners (when both endings are inside the slice) and ties.
   Use `indicesNotNumbers=True`: measure numbers can repeat. The end index is **exclusive**
   (`measures(4, 8, ...)` gives indices 4–7). The context collected from before the slice (key,
   time, clef, instrument) lands on the **slice Part at offset 0**, not inside its first measure, and
   the tempo likewise. A song after a gap measure therefore gets the gap's key and tempo (checked:
   a song after a 5-flat gap measure gets 5 flats and the 132 tempo). Assembly must move those
   context elements into the first measure itself.
2. **`expandRepeats()` works on a slice** and on a whole part. `repeats_and_voltas` gives
   `1 2 3 1 2 4` both ways; on the real score, "I will find" expands to its 16 measures twice,
   then the gap measure.
3. **Parsing is fast:** 0.09 s for the 267 KB example. `converter.parseData(bytes)` is enough for
   `.musicxml` and `.xml`, **not** for `.mxl` (it raises `ConverterException`). `.mxl` goes through
   a `delete=False` temp file and `converter.parse(path)`, which works. A truncated XML file raises
   `xml.etree.ElementTree.ParseError`; empty, garbage, PDF and zip bytes raise
   `ConverterException`. Both are caught in the one `except Exception` in `parsing.py`.
4. **Assembly works.** A `Score` built from deep-copied slices of two files (spanners re-inserted
   into the output part, measures renumbered) exports with `GeneralObjectExporter`, keeps the
   repeat signs and both `<ending>` elements, and re-parses with the same measures and
   `expandRepeats()` order. MuseScore 4.7.4 opens the file headless
   (`QT_QPA_PLATFORM=offscreen mscore -o out.mscx out.musicxml`).
5. **Instruments.** music21 gives the part named "Baixo" with `<midi-program>59</midi-program>` an
   `instrument.Tuba` (`midiProgram` 58, 0-based); the Trombone part gets `Trombone` (57). So
   `isinstance(part.getInstrument(returnDefault=False), instrument.Tuba)` covers the MIDI rule;
   the name regex is the fallback.
6. **MultiDrag has Shift-click range selection built in** (SortableJS 1.15.7, `shiftKey` in
   `MultiDrag`); no custom JS is needed. Vendor **SortableJS 1.15.7** (`Sortable.min.js` is the
   complete build, MIT) and **Pico.css 2.1.1** (`pico.min.css`, MIT).

**D2 is confirmed.**

### [ ] Step 1 — Scaffold
- `pyproject.toml`:
  - build backend: hatchling;
  - runtime dependencies: `flask`, `waitress`, `music21`, `pathvalidate`, `platformdirs`;
  - extras: `dev = pytest, ruff, mypy`, `e2e = pytest-playwright`;
  - ruff, mypy (strict, with the music21 override) and pytest configuration;
  - `[project.scripts] sheet-dj-server = "sheet_dj.server:main"`.
- `src/sheet_dj/__init__.py` and empty modules from the module map. Add `tests/` and `.gitignore`.
- *Done when:* `pip install -e '.[dev]'` works; `pytest` collects (no tests yet); `ruff` and `mypy`
  are clean.

### [ ] Step 2 — `model.py` + `notation.py` (pure, no music21)
- `tests/test_notation.py` holds table-driven cases, one parametrised group per writing rule
  (cycle, one-measure, folding, spelling, arrows, groups). Use the lines in
  `tests/fixtures/output/*.csv` as cases, with their measures written as `Note` lists.
- `tests/notation_reader.py` is a test-only reader of the line format. A property test checks that
  for any measure list, `read(write(M))` gives the same note names and the same intervals
  between consecutive notes as the written cycle or line.
- *Done when:* every writing rule has at least one case, including a tritone (counts as up), a
  move of more than an octave (two arrows), and a respelled double accidental.

### [ ] Step 3 — `parsing.py`
- `parse_score(data, filename)` does, in order:
  1. reject by type: `.mscz` → E02, PDF or image → E03;
  2. parse with music21;
  3. find the tuba part;
  4. split into songs;
  5. extract each song's tuba measures (repeats expanded) and call `write_tuba_line`;
  6. if the score has no notes → E06;
  7. any other failure → E05.
- `tests/test_parsing.py` is a golden test: every `input/*.musicxml` or `.mscz` matches its
  `output/*.csv` or `output/*.error`. Plus a test that every input has an expected output.
- *Done when:* every fixture passes.

### [ ] Step 4 — `assembly.py` + `export.py`
- `assemble_set_list` follows D7. `tuba_csv` and `set_list_zip` follow D9–D11.
- `tests/test_export.py` covers:
  - **every** directory under `fixtures/scenarios/`: load the inputs, order the songs by title,
    export, unzip, re-parse the `.musicxml`, and compare titles and lines to `expected.csv`;
  - the zip's member names;
  - the CSV BOM and the arrows surviving `utf-8-sig` decoding;
  - sanitising of the output name.
- *Done when:* the scenario passes and the exported file opens in MuseScore (checked once by hand;
  note the result here).

### [ ] Step 5 — `library.py`, `config.py`, `views.py`, `server.py`, a bare template
- Endpoints as above. Logging goes to the platformdirs log file; there is one top-level handler.
- `tests/test_views.py`:
  - one parametrised test over the catalogue E01–E11 (`id="E0x"`). Each case asserts the message,
    a 200 rendered page, and that loaded songs, set list and name survived;
  - a happy-path test: upload two fixtures, then POST `/export`, and receive a zip;
  - a test that one bad file in a batch does not block the good ones.
- *Done when:* `python -m sheet_dj.server` serves the page and a manual upload → export works
  with the plain template.

### [ ] Step 6 — UI
- Vendor Sortable (with MultiDrag) and Pico, with their licence files.
- `static/app.js` implements:
  - selection, the buttons and double-click;
  - Shuffle and Random n;
  - `sessionStorage` restore, wrapped in try/catch;
  - filling the hidden inputs on submit.
- Optional `tests/e2e/test_page.py` (Playwright, `-m e2e`): drag a song, Ctrl-select two and move
  them, Shuffle keeps the same set, Random 2 moves exactly two.
- *Done when:* the manual checklist in Step 7 passes in Firefox and Chromium.

### [ ] Step 7 — Manual check on Linux
Run `python -m sheet_dj.server`, then:
1. Add all fixtures plus `examples/eletro_farra_trombone.musicxml` in one go:
   - `broken_xml`, `empty_score` and `project_file` show E05, E06 and E02;
   - Eletro Farra shows E07 and lists 16 songs;
   - the rest load.
2. Build a set list using drag, Ctrl, Shift, the buttons, Shuffle and Random 3. Reload the page:
   the songs and the set list are still there.
3. Rename the output with a forbidden character (`set:list?`) and download. Check the zip.
4. Open the `.musicxml` in MuseScore: the songs are in order, each has its rehearsal mark, and the
   key, tempo and repeats are right.
5. Open the CSV in LibreOffice: the arrows and flats display correctly, one row per song.
6. Stop the server, press Download in the stale tab, and check that the page shows E09 after a
   restart.

---

## Phase 2 — Windows product (decide at the start of the phase)

The work, in order. Each item becomes a step when the phase starts.

1. **`launcher.py`** (the `[project.gui-scripts] sheet-dj` entry): start the server or attach to a
   running one.
   - It probes `127.0.0.1:SHEETDJ_PORT` for a health endpoint (`/healthz`, which returns the app
     name, so a foreign program on the port is detected).
   - If nothing answers, it spawns the server detached with no console
     (`DETACHED_PROCESS | CREATE_NO_WINDOW`), waits for it to be ready, and opens the browser.
   - Failures show a `tkinter.messagebox` dialog: **E20** port taken by another program, **E21**
     server did not start in time (with the log location).
2. **`idle.py`**: a watchdog that stops waitress through its own API after
   `SHEETDJ_IDLE_MINUTES` with no requests. The page sends a light heartbeat while open, so an
   open tab keeps the app alive.
3. **Icon:** `sheet-dj.svg` and `sheet-dj.ico`.
4. **Installer — choose one, then write the install/uninstall steps here. Both must be safe to
   re-run.**
   - *A. PowerShell + venv:* install Python from python.org if missing, create a per-user venv,
     `pip install` the wheel, and create Desktop and Start-menu shortcuts.
     - Pros: small, transparent.
     - Cons: needs network at install time, and music21 pulls in a sizeable dependency tree.
   - *B. PyInstaller one-folder + Inno Setup:* a real `setup.exe` with uninstall support, working
     offline.
     - Pros: the most "normal" for users.
     - Cons: a big bundle, a Windows build machine or CI job, and false positives from antivirus
       software.
5. **CI:** GitHub Actions matrix `ubuntu-latest` × `windows-latest` running pytest, ruff and mypy.
   Add the `PYTHONUTF8=0 LC_ALL=C` run on Ubuntu.
6. **VM checklist** (quickemu `quickget windows 11`):
   1. install;
   2. click the icon (the browser opens);
   3. load scores, build a set list, download, open the files;
   4. click the icon again (a new tab, the same library);
   5. leave it idle (the process exits);
   6. uninstall (nothing is left behind except the log directory);
   7. reinstall.

---

## Open questions (resolve before the step named)

- D5, three **[confirm]** items: the one-measure cycle written ×4, rest measures dropped, written
  pitch. Resolve before Step 2.
- D10 **[confirm]**: CSV with BOM. Resolve before Step 4.
- D13 **[confirm]**: UI language. Resolve before Step 5.
- If a set list contains two songs with the same title next to each other, re-import merges them.
  Is that acceptable, or should the export add " (2)"? Resolve before Step 4.
