"""Build the set-list score from songs of loaded scores. With `parsing`, the only music21 user."""

import copy
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from music21 import (
    bar,
    clef,
    expressions,
    instrument,
    key,
    metadata,
    meter,
    note,
    spanner,
    stream,
    tempo,
)
from music21.common.enums import GatherSpanners
from music21.musicxml.m21ToXml import GeneralObjectExporter

from sheet_dj.model import Song
from sheet_dj.parsing import ParsedScore

TUBA_PART_NAME = "Tuba"
DEFAULT_BAR_LENGTH = 4.0
DEFAULTS_ELEMENT = re.compile(r"<defaults\s*/>|<defaults>.*?</defaults>", re.DOTALL)
FIRST_AFTER_DEFAULTS = re.compile(r"<credit[\s>]|<part-list")
KEPT_IN_RESTS = (bar.Barline, meter.TimeSignature, key.KeySignature)
# What a song's first measure must state itself, because the song may follow one in another key.
CONTEXT_CLASSES = (clef.Clef, meter.TimeSignature, key.KeySignature, tempo.MetronomeMark)

# Identifies an output part: the part's normalised name and which of that name it is in its score
# (two parts may share a name), or None for the tuba, whatever its source name was.
type PartKey = tuple[str, int] | None
# A run of measures, with the spanners (endings, slurs) that lie wholly inside it.
type Piece = stream.Stream[Any]


@dataclass(frozen=True)
class SongRef:
    """One song of the set list and the loaded score it comes from."""

    score: ParsedScore
    song: Song


def assemble_set_list(
    songs: Sequence[SongRef], title: str, layout_defaults: str | None = None
) -> bytes:
    """Return the MusicXML of the songs in order, as one score called `title`.

    `layout_defaults` is a `<defaults>` element to give the score, so it is laid out like a source.
    """
    result = stream.Score()
    # An empty composer stops music21 from printing its own name there.
    result.metadata = metadata.Metadata(title=title, composer="")
    for position, (part_key, name) in enumerate(_output_part_names(songs).items()):
        result.insert(0, _build_part(part_key, name, songs, with_titles=position == 0))
    exported: bytes = GeneralObjectExporter(result).parse()
    if layout_defaults is None:
        return exported
    return _with_defaults(exported.decode("utf-8"), layout_defaults).encode("utf-8")


def _with_defaults(musicxml: str, defaults: str) -> str:
    """Replace the score's `<defaults>`; the schema puts it before the credits and part list."""
    musicxml = DEFAULTS_ELEMENT.sub("", musicxml)
    anchor = FIRST_AFTER_DEFAULTS.search(musicxml)
    if anchor is None:
        return musicxml
    return f"{musicxml[: anchor.start()]}{defaults}\n  {musicxml[anchor.start() :]}"


def _part_name(part: stream.Part, index: int) -> str:
    return str(part.partName or f"Part {index + 1}").strip()


def _part_keys(parsed: ParsedScore) -> dict[PartKey, int]:
    """Map each part of a score to its output part key, in part order."""
    keys: dict[PartKey, int] = {}
    seen: Counter[str] = Counter()
    for index, part in enumerate(parsed.score.parts):
        if index == parsed.tuba_index:
            keys[None] = index
            continue
        name = _part_name(part, index).casefold()
        keys[(name, seen[name])] = index
        seen[name] += 1
    return keys


def _output_part_names(songs: Sequence[SongRef]) -> dict[PartKey, str]:
    """The union of the songs' parts in order of first appearance, with the name to give each."""
    names: dict[PartKey, str] = {}
    for ref in songs:
        for part_key, index in _part_keys(ref.score).items():
            if part_key not in names:
                part = ref.score.score.parts[index]
                names[part_key] = TUBA_PART_NAME if part_key is None else _part_name(part, index)
    return names


def _build_part(
    part_key: PartKey, name: str, songs: Sequence[SongRef], *, with_titles: bool
) -> stream.Part:
    result = stream.Part()
    result.partName = name
    pieces: list[Piece | None] = []
    for ref in songs:
        index = _part_keys(ref.score).get(part_key)
        if index is None:
            pieces.append(None)
            continue
        source = ref.score.score.parts[index]
        if not result.getElementsByClass(instrument.Instrument):
            result.insert(0, _instrument_for(source, name))
        pieces.append(_song_piece(source, ref.song))
    default_clef = _first_clef(pieces)
    for ref, piece in zip(songs, pieces, strict=True):
        whole = _fill_with_rests(piece, ref, default_clef)
        _retitle(whole, ref.song.title if with_titles else None)
        for spanning in whole.getElementsByClass(spanner.Spanner):
            result.insert(0, spanning)
        for measure in _measures(whole):
            result.append(measure)
    for number, measure in enumerate(_measures(result), start=1):
        measure.number = number
    return result


def _measures(part: Piece) -> list[stream.Measure]:
    return list(part.getElementsByClass(stream.Measure))


def _instrument_for(source: stream.Part, name: str) -> instrument.Instrument:
    played_by = source.getInstrument(returnDefault=False)
    result = copy.deepcopy(played_by) if played_by is not None else instrument.Instrument()
    result.partName = name
    if name == TUBA_PART_NAME:
        result.instrumentName = name
    return result


def _song_piece(source: stream.Part, song: Song) -> Piece:
    """A copy of the song's measures, with the key, time, clef and tempo in force at its start."""
    piece = copy.deepcopy(
        source.measures(
            song.first_measure,
            song.last_measure + 1,
            indicesNotNumbers=True,
            gatherSpanners=GatherSpanners.COMPLETE_ONLY,
        )
    )
    measures = _measures(piece)
    if measures:
        for context in piece.getElementsByClass(CONTEXT_CLASSES):
            measures[0].insert(0, context)  # music21 collects them on the part, not the measure
    return piece


def _first_clef(pieces: Sequence[Piece | None]) -> clef.Clef:
    for piece in pieces:
        measures = [] if piece is None else _measures(piece)
        if measures and (found := measures[0].getElementsByClass(clef.Clef)):
            return copy.deepcopy(found[0])
    return clef.TrebleClef()


def _fill_with_rests(piece: Piece | None, ref: SongRef, default_clef: clef.Clef) -> Piece:
    """Complete a song's piece to the song's length in measures, with full-measure rests.

    A part the score lacks gets rests all through; a part shorter than the others, rests at the
    end. The rests copy the barlines, key, time and endings of the score's first part: every part
    must agree on the repeats, or MuseScore drops them.
    """
    wanted = ref.song.last_measure - ref.song.first_measure + 1
    result = stream.Part() if piece is None else piece
    have = len(_measures(result))
    if have >= wanted:
        return result
    shape = _song_piece(ref.score.score.parts[0], ref.song)
    shaped = _measures(shape)
    for position in range(have, wanted):
        like = shaped[min(position, len(shaped) - 1)] if shaped else stream.Measure()
        length = like.highestTime or DEFAULT_BAR_LENGTH
        result.append(_rests_like(shaped[position] if position < len(shaped) else None, length))
    if have == 0:
        _measures(result)[0].insert(0, copy.deepcopy(default_clef))
        for ending in shape.getElementsByClass(spanner.RepeatBracket):
            result.insert(0, ending)
    return result


def _rests_like(measure: stream.Measure | None, length: float) -> stream.Measure:
    """A measure of one full rest that keeps only the barlines, key and time of `measure`."""
    result = measure if measure is not None else stream.Measure()
    for element in list(result):
        if not isinstance(element, KEPT_IN_RESTS):
            result.remove(element)
    result.insert(0, note.Rest(quarterLength=length))
    return result


def _retitle(piece: Piece, title: str | None) -> None:
    """Drop the marks on the song's first measure; on the top part, put the song's title there."""
    first = _measures(piece)[0]
    first.removeByClass(expressions.RehearsalMark)
    if title is not None:
        first.insert(0, expressions.RehearsalMark(title))
