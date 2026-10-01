"""Turn score bytes into songs and tuba lines. With `assembly`, the only module using music21."""

import contextlib
import hashlib
import re
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from music21 import (
    bar,
    chord,
    converter,
    expressions,
    instrument,
    note,
    pitch,
    repeat,
    spanner,
    stream,
)

from sheet_dj.model import Note, ScoreSummary, Song, UserError
from sheet_dj.notation import write_tuba_line

MUSESCORE_SUFFIXES = frozenset({".mscz", ".mscx"})
PICTURE_SUFFIXES = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
)
ZIP_MAGIC = b"PK\x03\x04"
TUBA_NAME = re.compile(r"tuba|sousaf|sousaph|helicon", re.IGNORECASE)
TUBA_MIDI_PROGRAM = 58  # music21 counts from 0; MusicXML's <midi-program>59 is the tuba
TIE_CONTINUATIONS = frozenset({"stop", "continue"})
DEFAULT_TUBA_LABEL = "Tuba"

E02_MUSESCORE_FILE = (
    "Could not read *{file}*. This is a MuseScore project file — open it in MuseScore, "
    "use *File → Export → MusicXML*, and add that file instead."
)
E03_PICTURE = (
    "*{file}* is a picture or PDF of sheet music, not a score file. Open the score in "
    "MuseScore and use *File → Export → MusicXML*, then add that file."
)
E05_UNREADABLE = (
    "Could not read *{file}*. It looks damaged or is not a MusicXML score. Export it again "
    "from MuseScore (*File → Export → MusicXML*) and add the new file."
)
E06_NO_NOTES = (
    "*{file}* has no notes in it. Check that you exported the full score and not an empty part."
)
E07_NO_TUBA = (
    "No tuba part was found in *{file}*. Its songs were added, but their tuba lines are empty. "
    'If the score has a tuba, name its part "Tuba" in MuseScore and export again.'
)


class ScoreError(UserError):
    """A score could not be loaded; the message says why in the user's terms."""


@dataclass(frozen=True)
class ParsedScore:
    """A loaded score: what the page shows, plus the music21 score the export assembles from."""

    summary: ScoreSummary
    score: stream.Score  # read-only after parsing; only parsing.py and assembly.py look inside
    tuba_index: int | None


@dataclass(frozen=True)
class _Span:
    title: str
    first: int
    last: int


def base_name(filename: str) -> str:
    """The file name without any folder, whichever separator the browser used."""
    return PureWindowsPath(filename).name or "score"


def no_tuba_message(filename: str) -> str:
    """The E07 warning for a score that loaded without a tuba part."""
    return E07_NO_TUBA.format(file=filename)


def parse_score(data: bytes, filename: str) -> ParsedScore:
    """Parse one uploaded score into songs with their tuba lines, or raise `ScoreError`."""
    file = base_name(filename)
    _reject_unsupported(file)
    try:
        return _parse(data, file)
    except ScoreError:
        raise
    except Exception as exc:  # music21's failures are open-ended; the user gets one message
        raise ScoreError("E05", E05_UNREADABLE.format(file=file)) from exc


def _reject_unsupported(file: str) -> None:
    suffix = Path(file).suffix.lower()
    if suffix in MUSESCORE_SUFFIXES:
        raise ScoreError("E02", E02_MUSESCORE_FILE.format(file=file))
    if suffix in PICTURE_SUFFIXES:
        raise ScoreError("E03", E03_PICTURE.format(file=file))


def _parse(data: bytes, file: str) -> ParsedScore:
    score = _read_score(data)
    parts = [list(part.getElementsByClass(stream.Measure)) for part in score.parts]
    count = max(map(len, parts), default=0)
    has_notes = [any(i < len(p) and _has_notes(p[i]) for p in parts) for i in range(count)]
    if not any(has_notes):
        raise ScoreError("E06", E06_NO_NOTES.format(file=file))
    name = PureWindowsPath(file).stem
    has_repeat = [any(i < len(p) and _has_repeat(p[i]) for p in parts) for i in range(count)]
    spans = _split_songs(
        _rehearsal_marks(parts), has_notes, has_repeat, _untitled_title(score, name)
    )
    tuba_index = _find_tuba(score.parts)
    tuba = None if tuba_index is None else score.parts[tuba_index]
    songs = tuple(
        Song(
            id=uuid.uuid4().hex,
            title=span.title,
            score_name=name,
            first_measure=span.first,
            last_measure=span.last,
            tuba_line="" if tuba is None else _tuba_line(tuba, span),
        )
        for span in spans
    )
    summary = ScoreSummary(
        file_name=file,
        name=name,
        digest=hashlib.sha256(data).hexdigest(),
        songs=songs,
        tuba_part_name=None if tuba is None else _part_label(tuba),
    )
    return ParsedScore(summary, score, tuba_index)


def _read_score(data: bytes) -> stream.Score:
    parsed: object  # a compressed .mxl is read by music21 only from a path
    parsed = (
        _parse_from_temp_file(data) if data.startswith(ZIP_MAGIC) else converter.parseData(data)
    )
    if not isinstance(parsed, stream.Score):
        raise ValueError("not a single score")
    return parsed


def _parse_from_temp_file(data: bytes) -> object:
    # An open temp file cannot be reopened by name on Windows: close it before parsing.
    with tempfile.NamedTemporaryFile(suffix=".mxl", delete=False) as file:
        file.write(data)
    try:
        return converter.parse(file.name, forceSource=True)  # forceSource: no pickle cache on disk
    finally:
        Path(file.name).unlink(missing_ok=True)


def _has_notes(measure: stream.Measure) -> bool:
    return any(True for _ in measure.recurse().notes)


def _has_repeat(measure: stream.Measure) -> bool:
    """Whether the measure carries a repeat sign or sits in a 1st/2nd ending."""
    barlines = (measure.leftBarline, measure.rightBarline)
    return any(isinstance(line, bar.Repeat) for line in barlines) or any(
        isinstance(site, spanner.RepeatBracket) for site in measure.getSpannerSites()
    )


def _rehearsal_marks(parts: Sequence[Sequence[stream.Measure]]) -> dict[int, str]:
    """The first rehearsal mark text of each measure index, looking through every part.

    MuseScore puts the marks on the top part only, so all parts are searched. Marks are matched
    by index: measure numbers can repeat or be missing on pickups.
    """
    marks: dict[int, str] = {}
    for measures in parts:
        for index, measure in enumerate(measures):
            if index in marks:
                continue
            for mark in measure.recurse().getElementsByClass(expressions.RehearsalMark):
                text = str(mark.content).strip()
                if text:
                    marks[index] = text
                    break
    return marks


def _untitled_title(score: stream.Score, file_stem: str) -> str:
    metadata = score.metadata
    for title in (None, None) if metadata is None else (metadata.title, metadata.movementName):
        if title and str(title).strip():
            return str(title).strip()
    return file_stem


def _split_songs(
    marks: Mapping[int, str],
    has_notes: Sequence[bool],
    has_repeat: Sequence[bool],
    untitled_title: str,
) -> list[_Span]:
    """Cut the measures into songs at rehearsal marks and trim each song's trailing gap measures.

    A gap measure holds only rests. One that closes a repeat or an ending is part of its song.
    """
    starts: list[tuple[int, str]] = []
    if not marks or min(marks) > 0:
        starts.append((0, untitled_title))
    for index in sorted(marks):
        if not starts or starts[-1][1] != marks[index]:  # a repeated mark continues the song
            starts.append((index, marks[index]))
    ends = [start - 1 for start, _ in starts[1:]] + [len(has_notes) - 1]
    spans: list[_Span] = []
    for (first, title), last in zip(starts, ends, strict=True):
        while last >= first and not (has_notes[last] or has_repeat[last]):
            last -= 1
        if any(has_notes[first : last + 1]):
            spans.append(_Span(title, first, last))
    return spans


def _find_tuba(parts: Sequence[stream.Part]) -> int | None:
    return next((i for i, part in enumerate(parts) if _is_tuba(part)), None)


def _is_tuba(part: stream.Part) -> bool:
    names = [part.partName, part.partAbbreviation]
    played_by = part.getInstrument(returnDefault=False)
    if played_by is not None:
        if isinstance(played_by, instrument.Tuba) or played_by.midiProgram == TUBA_MIDI_PROGRAM:
            return True
        names.append(played_by.instrumentName)
    return any(name and TUBA_NAME.search(name) for name in names)


def _part_label(part: stream.Part) -> str:
    return str(part.partName or DEFAULT_TUBA_LABEL).strip()


def _tuba_line(tuba: stream.Part, span: _Span) -> str:
    piece = tuba.measures(span.first, span.last + 1, collect=(), indicesNotNumbers=True)
    # Repeats that cannot be expanded: write the song as it stands rather than reject the score.
    with contextlib.suppress(repeat.ExpanderException):
        piece = piece.expandRepeats()
    played = piece.getElementsByClass(stream.Measure)
    return write_tuba_line([_attacks(measure) for measure in played])


def _attacks(measure: stream.Measure) -> list[Note]:
    """The notes a tuba player attacks: no rests, grace notes or continuations of a tie."""
    attacks: list[Note] = []
    for element in measure.flatten().notes:
        if not isinstance(element, note.Note | chord.Chord) or element.duration.isGrace:
            continue
        lowest = _lowest(element)
        if lowest.tie is None or lowest.tie.type not in TIE_CONTINUATIONS:
            attacks.append(_to_note(lowest.pitch))
    return attacks


def _lowest(element: note.Note | chord.Chord) -> note.Note:
    if isinstance(element, chord.Chord):
        return min(element.notes, key=lambda each: each.pitch.midi)
    return element


def _to_note(written: pitch.Pitch) -> Note:
    alter = round(written.accidental.alter) if written.accidental is not None else 0
    accidental = "#" * alter if alter > 0 else "b" * -alter
    return Note(written.step + accidental, int(written.midi))
