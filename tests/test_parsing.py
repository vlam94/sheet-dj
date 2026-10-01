import csv
import io
import re
import zipfile
from pathlib import Path

import pytest

from sheet_dj.parsing import ParsedScore, ScoreError, _split_songs, no_tuba_message, parse_score

FIXTURES = Path(__file__).parent / "fixtures"
INPUTS = sorted((FIXTURES / "input").iterdir())
OUTPUTS = FIXTURES / "output"


def expected_rows(csv_path: Path) -> list[list[str]]:
    with csv_path.open(encoding="utf-8", newline="") as file:
        return list(csv.reader(file))


def parse_fixture(name: str) -> ParsedScore:
    return parse_score((FIXTURES / "input" / name).read_bytes(), name)


def rows(parsed: ParsedScore) -> list[list[str]]:
    return [[song.title, song.tuba_line] for song in parsed.summary.songs]


@pytest.mark.parametrize("path", INPUTS, ids=lambda path: path.stem)
def test_every_input_has_an_expected_output(path: Path) -> None:
    assert (OUTPUTS / f"{path.stem}.csv").exists() or (OUTPUTS / f"{path.stem}.error").exists()


@pytest.mark.parametrize("path", INPUTS, ids=lambda path: path.stem)
def test_input_matches_its_expected_output(path: Path) -> None:
    error_file = OUTPUTS / f"{path.stem}.error"
    if error_file.exists():
        with pytest.raises(ScoreError) as raised:
            parse_fixture(path.name)
        assert raised.value.catalogue_id == error_file.read_text(encoding="utf-8").strip()
    else:
        assert rows(parse_fixture(path.name)) == expected_rows(OUTPUTS / f"{path.stem}.csv")


class TestTubaPart:
    def test_found_by_name(self) -> None:
        assert parse_fixture("cycle_single_note.musicxml").summary.tuba_part_name == "Tuba"

    def test_found_by_midi_program_when_the_name_says_nothing(self) -> None:
        assert parse_fixture("tuba_by_midi_program.musicxml").summary.tuba_part_name == "Baixo"

    def test_missing_part_still_loads_with_empty_lines(self) -> None:
        parsed = parse_fixture("no_tuba_part.musicxml")
        assert parsed.summary.tuba_part_name is None
        assert parsed.tuba_index is None
        assert [song.tuba_line for song in parsed.summary.songs] == [""]

    def test_missing_part_warning_names_the_file(self) -> None:
        assert "*show.musicxml*" in no_tuba_message("show.musicxml")


class TestSongs:
    def test_ids_are_random_per_load_not_positions(self) -> None:
        first = parse_fixture("medley_two_songs.musicxml").summary.songs
        second = parse_fixture("medley_two_songs.musicxml").summary.songs
        ids = [song.id for song in first + second]
        assert len(set(ids)) == 4

    def test_song_records_its_score_and_measures(self) -> None:
        songs = parse_fixture("medley_two_songs.musicxml").summary.songs
        assert [(s.score_name, s.first_measure, s.last_measure) for s in songs] == [
            ("medley_two_songs", 0, 2),  # the gap measure after it is trimmed
            ("medley_two_songs", 4, 7),  # the repeated mark does not start a new song
        ]

    def test_a_rest_measure_closing_a_repeat_stays_in_its_song(self) -> None:
        songs = parse_fixture("rest_closes_repeat.musicxml").summary.songs
        assert [(s.title, s.first_measure, s.last_measure) for s in songs] == [
            ("Reprise", 0, 2),
            ("Next Song", 4, 6),
        ]

    def test_unbalanced_repeats_do_not_reject_the_score(self) -> None:
        text = (FIXTURES / "input" / "rest_closes_repeat.musicxml").read_text(encoding="utf-8")
        unbalanced = re.sub(r'<repeat direction="backward"\s*/>', "", text)
        assert unbalanced != text
        parsed = parse_score(unbalanced.encode("utf-8"), "odd.musicxml")
        assert rows(parsed)[0] == ["Reprise", "F | Ab"]

    def test_title_falls_back_to_the_file_name(self) -> None:
        text = (FIXTURES / "input" / "no_rehearsal_mark.musicxml").read_text(encoding="utf-8")
        untitled = re.sub(r"<work>.*?</work>", "", text, flags=re.DOTALL)
        parsed = parse_score(untitled.encode("utf-8"), "My Set.musicxml")
        assert [song.title for song in parsed.summary.songs] == ["My Set"]

    def test_same_content_gives_the_same_digest(self) -> None:
        assert (
            parse_fixture("whole_line.musicxml").summary.digest
            == parse_fixture("whole_line.musicxml").summary.digest
        )
        assert (
            parse_fixture("whole_line.musicxml").summary.digest
            != parse_fixture("tuba_by_midi_program.musicxml").summary.digest
        )


class TestSplit:
    def test_a_mark_on_the_first_measure_leaves_no_untitled_song(self) -> None:
        spans = _split_songs({0: "A", 2: "B"}, [True] * 4, [False] * 4, "Untitled")
        assert [(s.title, s.first, s.last) for s in spans] == [("A", 0, 1), ("B", 2, 3)]

    def test_rests_before_the_first_mark_are_dropped(self) -> None:
        spans = _split_songs({1: "A"}, [False, True], [False, False], "Untitled")
        assert [s.title for s in spans] == ["A"]

    def test_a_song_of_only_rests_is_dropped(self) -> None:
        spans = _split_songs({0: "A", 1: "B", 2: "C"}, [True, False, True], [False] * 3, "Untitled")
        assert [s.title for s in spans] == ["A", "C"]

    def test_gap_measures_inside_a_song_stay(self) -> None:
        spans = _split_songs({0: "A"}, [True, False, True, False], [False] * 4, "Untitled")
        assert [(s.first, s.last) for s in spans] == [(0, 2)]

    def test_a_rest_measure_that_closes_a_repeat_is_not_a_gap(self) -> None:
        spans = _split_songs({0: "A"}, [True, False, False], [False, True, False], "Untitled")
        assert [(s.first, s.last) for s in spans] == [(0, 1)]


class TestFileHandling:
    def test_compressed_mxl_is_read(self) -> None:
        raw = (FIXTURES / "input" / "tuba_by_midi_program.musicxml").read_bytes()
        container = (
            '<?xml version="1.0"?><container><rootfiles>'
            '<rootfile full-path="score.xml"/></rootfiles></container>'
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("score.xml", raw)
        parsed = parse_score(buffer.getvalue(), "fly.mxl")
        assert rows(parsed) == expected_rows(OUTPUTS / "tuba_by_midi_program.csv")

    def test_xml_extension_is_read(self) -> None:
        raw = (FIXTURES / "input" / "whole_line.musicxml").read_bytes()
        assert parse_score(raw, "line.xml").summary.songs

    def test_error_names_the_file_without_its_folder(self) -> None:
        with pytest.raises(ScoreError) as raised:
            parse_score(b"PK", "C:\\Users\\me\\Music\\show.mscz")
        assert "*show.mscz*" in raised.value.message
        assert "Users" not in raised.value.message

    @pytest.mark.parametrize(
        ("name", "data", "catalogue_id"),
        [
            pytest.param("score.PDF", b"%PDF-1.4", "E03", id="pdf"),
            pytest.param("scan.png", b"\x89PNG", "E03", id="image"),
            pytest.param("empty.musicxml", b"", "E05", id="empty-file"),
            pytest.param("notes.musicxml", b"just some text", "E05", id="text"),
            pytest.param("odd.mxl", b"PK\x03\x04garbage", "E05", id="damaged-zip"),
        ],
    )
    def test_unusable_files_give_a_plain_message(
        self, name: str, data: bytes, catalogue_id: str
    ) -> None:
        with pytest.raises(ScoreError) as raised:
            parse_score(data, name)
        assert raised.value.catalogue_id == catalogue_id
        assert name in raised.value.message
        assert "Exception" not in raised.value.message
