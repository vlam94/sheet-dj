"""A test-only reader of the tuba-line format, to check that what is written can be read back."""

import re

from sheet_dj.model import Note

TOKEN = re.compile(r"\(|\)|\||x\d+|[A-G][#b]?[↑↓]*")
PITCH_CLASS = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
    "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}  # fmt: skip
START_OCTAVE_BASE = 60


def read_line(line: str) -> list[list[Note]]:
    """Read a line into its played measures, with groups expanded.

    The first note is placed in an arbitrary octave: a line does not say which one.
    """
    return _Reader(TOKEN.findall(line)).read(in_group=False)


class _Reader:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.position = 0
        self.previous: int | None = None

    def read(self, *, in_group: bool) -> list[list[Note]]:
        done: list[list[Note]] = []
        current: list[Note] = []
        while self.position < len(self.tokens):
            token = self.tokens[self.position]
            if token == ")":
                assert in_group, "unbalanced )"
                break
            self.position += 1
            if token == "|":
                done.append(current)
                current = []
            elif token == "(":
                if current:
                    done.append(current)
                    current = []
                done.extend(self._read_group())
            else:
                current.append(self._read_note(token))
        if current:
            done.append(current)
        return done

    def _read_group(self) -> list[list[Note]]:
        body = self.read(in_group=True)
        self.position += 1  # the closing parenthesis
        times = int(self.tokens[self.position][1:])
        self.position += 1
        return body * times  # every repetition has the same pitches

    def _read_note(self, token: str) -> Note:
        name = token.rstrip("↑↓")
        octaves = token.count("↑") - token.count("↓")
        pitch_class = PITCH_CLASS[name]
        if self.previous is None:
            midi = START_OCTAVE_BASE + pitch_class
        else:
            nearest = (pitch_class - self.previous % 12 + 5) % 12 - 5
            midi = self.previous + nearest + 12 * octaves
        self.previous = midi
        return Note(name, midi)
