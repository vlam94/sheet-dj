"""The tuba-line writing rules, from measures of notes to text (CLAUDE.md, "The tuba line")."""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby

from sheet_dj.model import Note

type Measure = tuple[Note, ...]

ONE_MEASURE_CYCLE_REPEATS = 4
MIN_GROUP_LENGTH = 2
SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
NOTE_NAMES = frozenset(SHARP_NAMES + FLAT_NAMES)


@dataclass(frozen=True)
class Group:
    """A block of measures written once and played `times` times back to back."""

    measures: tuple[Measure, ...]
    times: int


def write_tuba_line(measures: Sequence[Sequence[Note]]) -> str:
    """Write the measures of one song's tuba part as a tuba line."""
    played = [m for m in (_collapse(measure) for measure in measures) if m]
    cycle = find_cycle(played)
    if cycle == 1:
        written = played[:1] * ONE_MEASURE_CYCLE_REPEATS
    elif cycle is not None:
        written = played[:cycle]
    else:
        written = played
    return _write_items(fold_groups(written))


def find_cycle(measures: Sequence[Measure]) -> int | None:
    """Return the smallest `p` such that the measures are `measures[:p]` repeated, or None.

    The last repetition may be cut short, but there must be at least two.
    """
    keys = [_pitches(m) for m in measures]
    for p in range(1, len(keys) // 2 + 1):
        if all(keys[i] == keys[i % p] for i in range(p, len(keys))):
            return p
    return None


def fold_groups(measures: Sequence[Measure]) -> list[Measure | Group]:
    """Fold blocks of two or more measures that repeat back to back into groups."""
    keys = [_pitches(m) for m in measures]
    items: list[Measure | Group] = []
    position = 0
    while position < len(measures):
        block = _best_block(keys, position)
        if block is None:
            items.append(measures[position])
            position += 1
        else:
            length, times = block
            items.append(Group(tuple(measures[position : position + length]), times))
            position += length * times
    return items


def spell(note: Note) -> str:
    """Return the note name, respelled into the 17 allowed names when it is not one of them."""
    if note.name in NOTE_NAMES:
        return note.name
    names = SHARP_NAMES if "#" in note.name else FLAT_NAMES
    return names[note.midi % 12]


def arrow(previous: int, current: int) -> str:
    """Return the octave arrows that make `current` be read nearest to `previous`."""
    distance = current - previous
    nearest = (distance + 5) % 12 - 5
    octaves = (distance - nearest) // 12
    return ("↑" if octaves > 0 else "↓") * abs(octaves)


def _pitches(measure: Measure) -> tuple[int, ...]:
    return tuple(note.midi for note in measure)


def _collapse(measure: Sequence[Note]) -> Measure:
    return tuple(next(notes) for _, notes in groupby(measure, key=lambda note: note.midi))


def _best_block(keys: Sequence[tuple[int, ...]], start: int) -> tuple[int, int] | None:
    """Return (length, times) of the block at `start` covering most measures; shortest on a tie."""
    best: tuple[int, int] | None = None
    for length in range(MIN_GROUP_LENGTH, (len(keys) - start) // 2 + 1):
        block = keys[start : start + length]
        if len(set(block)) == 1:
            continue  # a single measure repeated is never folded
        times = 1
        while keys[start + times * length : start + (times + 1) * length] == block:
            times += 1
        if times >= 2 and (best is None or length * times > best[0] * best[1]):
            best = (length, times)
    return best


def _write_items(items: Sequence[Measure | Group]) -> str:
    previous: int | None = None
    segments: list[str] = []
    run: list[Measure] = []
    for item in items:
        if isinstance(item, Group):
            if run:
                text, previous = _write_measures(run, previous)
                segments.append(text)
                run = []
            text, previous = _write_measures(item.measures, previous)
            segments.append(f"( {text} ) x{item.times}")
        else:
            run.append(item)
    if run:
        segments.append(_write_measures(run, previous)[0])
    return " ".join(segments)


def _write_measures(measures: Sequence[Measure], previous: int | None) -> tuple[str, int | None]:
    texts: list[str] = []
    for measure in measures:
        words: list[str] = []
        for note in measure:
            words.append(spell(note) + ("" if previous is None else arrow(previous, note.midi)))
            previous = note.midi
        texts.append(" ".join(words))
    return " | ".join(texts), previous
