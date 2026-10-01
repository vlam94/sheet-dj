import csv
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from notation_reader import read_line
from pitch import measures, note
from sheet_dj.model import Note
from sheet_dj.notation import (
    FLAT_NAMES,
    SHARP_NAMES,
    arrow,
    find_cycle,
    spell,
    write_tuba_line,
)

OUTPUT_DIR = Path(__file__).parent / "fixtures" / "output"


def expected_line(fixture: str, title: str) -> str:
    with (OUTPUT_DIR / f"{fixture}.csv").open(encoding="utf-8", newline="") as file:
        return dict(csv.reader(file))[title]


def line(text: str) -> str:
    return write_tuba_line(measures(text))


# The tuba part of each fixture after extraction, one case per expected csv row.
FIXTURE_CASES = [
    ("cycle_single_note", "Satisfaction", "Bb2 | Bb2 | Bb2 | Bb2 | Bb2 | Bb2"),
    (
        "cycle_four_measures",
        "Love Story",
        "F2 F2 F2 F2 | Ab2 | Db2 Eb2 | F2 | F2 F2 F2 F2 | Ab2 | Db2 Eb2 | F2",
    ),
    (
        "cycle_with_folding",
        "Blue Monday",
        "Ab2 G2 | F2 | Ab2 G2 | F2 | Ab2 G2 | F2 | Bb2 Eb2 | F2"
        " | Ab2 G2 | F2 | Ab2 G2 | F2 | Ab2 G2 | F2 | Bb2 Eb2 | F2",
    ),
    ("whole_line", "I Will Find", "Bb2 | A2 | D2 | D2 | F2 G2 | A2"),
    ("whole_line_with_folding", "What's Next", "Bb2 | A2 | D2 | F2 | D2 | F2 | G2"),
    ("ties_rests_chords", "Ties", "F2 G2 | A2 | C3 Bb2 | F2"),
    ("repeats_and_voltas", "Repeats", "F2 | Ab2 | Db2 Eb2 | F2 | Ab2 | C2"),
    ("medley_two_songs", "Love Parade", "C3 | C3 | C3"),
    ("medley_two_songs", "Heads Will Roll", "Bb2 Ab2 | Eb3 | Bb2 Ab2 | Eb3"),
    ("leading_untitled", "Pump It Up", "Bb2 | Bb2"),
    ("leading_untitled", "Party All the Time", "F2 G2 | Ab2 | F2 G2 | Ab2"),
    ("no_rehearsal_mark", "Rise Up", "F2 | Ab2 | C3 | C3 | F2 | Ab2 | C3 | C3"),
    ("tuba_by_midi_program", "I'll Fly With You", "F2 | A2 | D3 | Bb2"),
]


@pytest.mark.parametrize(
    ("fixture", "title", "tuba_part"),
    [pytest.param(*case, id=f"{case[0]}-{case[1]}") for case in FIXTURE_CASES],
)
def test_fixture_lines(fixture: str, title: str, tuba_part: str) -> None:
    assert line(tuba_part) == expected_line(fixture, title)


def test_no_measures_gives_an_empty_line() -> None:
    assert write_tuba_line([]) == ""
    assert line("- | -") == ""


class TestExtractedMeasures:
    def test_consecutive_identical_pitches_collapse(self) -> None:
        assert line("F2 F2 F2 | Ab2 Ab2 F2") == "F | Ab F"

    def test_empty_measures_are_dropped(self) -> None:
        assert line("F2 | - | Ab2") == "F | Ab"

    def test_measures_are_compared_by_pitch_not_spelling(self) -> None:
        assert line("Ab2 | G#2") == "Ab | Ab | Ab | Ab"


class TestCycle:
    def test_last_repetition_may_be_cut_short(self) -> None:
        assert line("F2 | G2 | A2 | F2 | G2 | A2 | F2 | G2") == "F | G | A"

    def test_needs_two_full_repetitions_of_the_start(self) -> None:
        assert line("F2 | G2 | A2 | F2 | G2") == "F | G | A | F | G"

    def test_the_smallest_period_wins(self) -> None:
        assert find_cycle([tuple(m) for m in measures("F2 | G2 | F2 | G2")]) == 2

    def test_no_cycle_in_a_single_measure(self) -> None:
        assert line("F2") == "F"


class TestOneMeasureCycle:
    @pytest.mark.parametrize(
        ("part", "expected"),
        [
            pytest.param("Bb2 | Bb2", "Bb | Bb | Bb | Bb", id="two-measures"),
            pytest.param("F2 Ab2 | F2 Ab2 | F2 Ab2", "F Ab | F Ab | F Ab | F Ab", id="two-notes"),
        ],
    )
    def test_written_four_times_as_plain_measures(self, part: str, expected: str) -> None:
        assert line(part) == expected


class TestFolding:
    def test_block_repeated_back_to_back_is_a_group(self) -> None:
        assert line("C3 | D3 | E3 | D3 | E3 | D3 | E3 | F3") == "C ( D | E ) x3 F"

    def test_shorter_block_wins_a_tie_on_measures_covered(self) -> None:
        assert line("C3 | D3 | E3 | D3 | E3 | D3 | E3 | D3 | E3 | F3") == "C ( D | E ) x4 F"

    def test_longer_block_wins_when_it_covers_more_measures(self) -> None:
        part = "C3 | D3 | E3 | F3 | D3 | E3 | F3 | D3 | E3 | F3 | D3 | E3 | F3 | G3"
        assert line(part) == "C ( D | E | F ) x4 G"

    def test_leftover_measures_stay_plain(self) -> None:
        assert line("C3 | D3 | E3 | D3 | E3 | D3 | F3") == "C ( D | E ) x2 D | F"

    def test_a_single_repeated_measure_is_never_folded(self) -> None:
        assert line("C3 | D3 | D3 | D3 | D3 | E3") == "C | D | D | D | D | E"

    def test_groups_are_never_nested(self) -> None:
        part = "C3 | D3 | E3 | D3 | E3 | F3 | D3 | E3 | D3 | E3 | F3 | G3"
        assert line(part) == "C ( D | E | D | E | F ) x2 G"

    def test_blocks_are_compared_by_pitch(self) -> None:
        assert line("C3 | Db3 | E3 | C#3 | E3 | F3") == "C ( Db | E ) x2 F"


class TestSpelling:
    @pytest.mark.parametrize(
        ("name", "midi", "expected"),
        [
            pytest.param("Bb", 46, "Bb", id="flat-kept"),
            pytest.param("F#", 54, "F#", id="sharp-kept"),
            pytest.param("E#", 53, "F", id="E#"),
            pytest.param("B#", 60, "C", id="B#"),
            pytest.param("Cb", 59, "B", id="Cb"),
            pytest.param("Fb", 64, "E", id="Fb"),
            pytest.param("C##", 62, "D", id="C##"),
            pytest.param("F##", 67, "G", id="F##"),
            pytest.param("A##", 71, "B", id="A##"),
            pytest.param("E##", 54, "F#", id="E##"),
            pytest.param("B##", 61, "C#", id="B##"),
            pytest.param("Bbb", 57, "A", id="Bbb"),
            pytest.param("Ebb", 50, "D", id="Ebb"),
            pytest.param("Cbb", 58, "Bb", id="Cbb"),
            pytest.param("Fbb", 51, "Eb", id="Fbb"),
        ],
    )
    def test_respelled_into_the_17_names(self, name: str, midi: int, expected: str) -> None:
        assert spell(Note(name, midi)) == expected

    def test_a_line_uses_the_respelled_names(self) -> None:
        assert line("E#2 | C##3 | Cb3") == "F | D↑ | B"


class TestArrows:
    @pytest.mark.parametrize(
        ("distance", "expected"),
        [
            pytest.param(0, "", id="unison"),
            pytest.param(5, "", id="fourth-up"),
            pytest.param(-5, "", id="fourth-down"),
            pytest.param(7, "↑", id="fifth-up"),
            pytest.param(-7, "↓", id="fifth-down"),
            pytest.param(6, "", id="tritone-up-is-bare"),
            pytest.param(-6, "↓", id="tritone-down-needs-an-arrow"),
            pytest.param(12, "↑", id="octave-up"),
            pytest.param(-12, "↓", id="octave-down"),
            pytest.param(17, "↑", id="octave-and-a-fourth"),
            pytest.param(19, "↑↑", id="more-than-an-octave"),
            pytest.param(-19, "↓↓", id="more-than-an-octave-down"),
            pytest.param(24, "↑↑", id="two-octaves"),
        ],
    )
    def test_arrow_by_distance(self, distance: int, expected: str) -> None:
        assert arrow(60, 60 + distance) == expected

    def test_worked_example_from_the_rules(self) -> None:
        assert line("A2 | D2") == "A | D↓"

    def test_the_first_note_is_bare(self) -> None:
        assert line("G5") == "G"

    def test_arrows_follow_notes_inside_and_across_measures(self) -> None:
        assert line("C2 G2 | C3") == "C G↑ | C"


class TestGroups:
    def test_first_note_is_read_against_the_note_before_the_group(self) -> None:
        assert line("D3 | G3 | C3 | G3 | C3 | A3") == "D ( G | C↓ ) x2 A↑"

    def test_note_after_a_group_is_read_against_its_last_note(self) -> None:
        # A3 is 2 above G3 (bare) but 9 above C3, which is what the group ends on: it needs ↑.
        assert line("D3 | G3 | C3 | G3 | C3 | A3").endswith("A↑")


def note_from(midi: int, *, sharp: bool) -> Note:
    names = SHARP_NAMES if sharp else FLAT_NAMES
    return Note(names[midi % 12], midi)


pitched = st.tuples(st.integers(36, 72), st.booleans())
measure_pool = st.lists(st.lists(pitched, max_size=3), min_size=1, max_size=4)
song_parts = measure_pool.flatmap(lambda pool: st.lists(st.sampled_from(pool), max_size=16))


@given(song_parts)
def test_reading_a_written_line_gives_back_the_song(part: list[list[tuple[int, bool]]]) -> None:
    song = [[note_from(m, sharp=s) for m, s in measure] for measure in part]
    played = [[n for i, n in enumerate(m) if i == 0 or n.midi != m[i - 1].midi] for m in song if m]
    text = write_tuba_line(song)
    if not played:
        assert text == ""
        return
    read = read_line(text)
    shift = played[0][0].midi - read[0][0].midi  # the line does not say which octave
    for i, expected in enumerate(played):
        actual = read[i % len(read)]
        assert [spell(n) for n in expected] == [n.name for n in actual]
        assert [n.midi + shift for n in actual] == [n.midi for n in expected]


def test_note_helper_places_middle_c_at_60() -> None:
    assert note("C4").midi == 60
    assert note("Bb2") == Note("Bb", 46)
