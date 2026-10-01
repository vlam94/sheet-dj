# examples

These files are for people and for manual smoke tests (PLAN.md Step 7). Tests never read from here.

## `eletro_farra_trombone.musicxml`

A real medley exported from MuseScore 4.7. It holds **16 songs** split by rehearsal marks.

It is a *single-part* (Trombone) export, so it has **no tuba part**: loading it must show warning
E07, and its tuba lines are empty. It is useful for checking the split rules against real-world
quirks:

- "Heads will roll" and "Blinding lights" each carry their rehearsal mark twice. Each must still be
  **one** song.
- Every song is followed by a rest-only gap measure carrying the next song's tempo, and sometimes
  its key change. "I will find" switches to one flat and the gap after it switches back to four.
- Repeat barlines and 1st/2nd endings (voltas) appear throughout.

It is about 267 KB; use it to time parsing.

## `songs_format_reference.csv`

Tuba lines a musician wrote **by hand** before this app existed. It is the origin of the CSV format:
no header, `Title,line`, measures separated by `|`, `( … ) xN` groups, and `↑`/`↓` arrows.

It is a reference for the **format**, not for the arrow rule. The arrows here were written by ear
and do not consistently follow the nearest-neighbour rule in `CLAUDE.md`. Some lines also hold
free-text comments in parentheses (`(não é reto)`, "it's not straight"). Do not use it as expected
output.
