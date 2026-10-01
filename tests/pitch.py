"""Test helpers to write notes as text: `F2`, `Bb2`, `C##3`, measures as `F2 G2 | A2`."""

import re

from sheet_dj.model import Note

STEP_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NOTE_PATTERN = re.compile(r"([A-G])(#{0,2}|b{0,2})(-?\d)")


def note(text: str) -> Note:
    """`Ab2` becomes Note("Ab", 44): MIDI 60 is C4."""
    match = NOTE_PATTERN.fullmatch(text)
    assert match, f"not a note: {text!r}"
    step, accidental, octave = match.groups()
    alter = accidental.count("#") - accidental.count("b")
    return Note(step + accidental, 12 * (int(octave) + 1) + STEP_PITCH_CLASS[step] + alter)


def measures(text: str) -> list[list[Note]]:
    """`F2 G2 | A2 | -` is three measures; `-` is an empty one."""
    return [[note(word) for word in part.split() if word != "-"] for part in text.split("|")]
