"""The in-memory library: every score loaded so far. The app's only state."""

import threading
from collections.abc import Sequence

from sheet_dj.assembly import SongRef, assemble_set_list
from sheet_dj.model import Song, UserError
from sheet_dj.parsing import ParsedScore, base_name, parse_score

E09_SONGS_GONE = (
    "Some songs in your set list are no longer loaded — the app was closed while idle. "
    "Add your scores again and rebuild the set list."
)
E10_DUPLICATE = "*{file}* is already loaded, so it was skipped."
E11_TOO_MANY = "Only {n} scores can be loaded at once. Use *Clear all* and add the ones you need."


class LibraryError(UserError):
    """The library cannot do what was asked; the message says why in the user's terms."""


class Library:
    """Scores parsed once at upload and read-only afterwards, behind one lock."""

    def __init__(self, max_scores: int) -> None:
        self._max_scores = max_scores
        self._scores: list[ParsedScore] = []
        self._lock = threading.Lock()

    def add(self, data: bytes, filename: str) -> ParsedScore:
        """Parse and add a score; raises `ScoreError` or `LibraryError` and adds nothing."""
        parsed = parse_score(data, filename)  # slow, so outside the lock
        with self._lock:
            if any(each.summary.digest == parsed.summary.digest for each in self._scores):
                raise LibraryError("E10", E10_DUPLICATE.format(file=base_name(filename)))
            if len(self._scores) >= self._max_scores:
                raise LibraryError("E11", E11_TOO_MANY.format(n=self._max_scores))
            self._scores.append(parsed)
        return parsed

    def clear(self) -> None:
        """Forget every score."""
        with self._lock:
            self._scores.clear()

    def scores(self) -> list[ParsedScore]:
        """The loaded scores, in the order they were added."""
        with self._lock:
            return list(self._scores)

    def songs(self) -> list[Song]:
        """Every loaded song, score by score."""
        return [song for parsed in self.scores() for song in parsed.summary.songs]

    def build_set_list(self, song_ids: Sequence[str], title: str) -> tuple[bytes, list[Song]]:
        """Assemble the songs, in the order given, into one score; also return the songs.

        The score takes its page layout from the first score loaded.

        Raises `LibraryError` (E09) if any id is no longer loaded. Assembly runs under the lock
        because it reads the shared music21 scores.
        """
        with self._lock:
            by_id = {
                song.id: SongRef(parsed, song)
                for parsed in self._scores
                for song in parsed.summary.songs
            }
            if any(song_id not in by_id for song_id in song_ids):
                raise LibraryError("E09", E09_SONGS_GONE)
            refs = [by_id[song_id] for song_id in dict.fromkeys(song_ids)]
            layout = self._scores[0].layout_defaults if self._scores else None
            return assemble_set_list(refs, title, layout), [ref.song for ref in refs]
