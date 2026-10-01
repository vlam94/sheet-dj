"""The plain data the rest of the app passes around."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Note:
    """One note attack: the score's own spelling (`Bb`, `E#`, `C##`) and its MIDI number."""

    name: str
    midi: int


@dataclass(frozen=True)
class Song:
    """A run of measures from one score, starting at a rehearsal mark.

    `first_measure` and `last_measure` are 0-based indices into the score's measures, inclusive.
    """

    id: str
    title: str
    score_name: str
    first_measure: int
    last_measure: int
    tuba_line: str


@dataclass(frozen=True)
class ScoreSummary:
    """What the page needs to know about one loaded score."""

    file_name: str
    name: str
    digest: str
    songs: tuple[Song, ...]
    tuba_part_name: str | None


class UserError(Exception):
    """A failure the user can fix: `message` goes on the page, `catalogue_id` is its E-number."""

    def __init__(self, catalogue_id: str, message: str) -> None:
        super().__init__(message)
        self.catalogue_id = catalogue_id
        self.message = message
