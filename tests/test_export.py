import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from sheet_dj.assembly import SongRef, assemble_set_list
from sheet_dj.export import output_name, set_list_zip, tuba_csv
from sheet_dj.model import Song
from sheet_dj.parsing import ParsedScore, parse_score

FIXTURES = Path(__file__).parent / "fixtures"
SCENARIOS = sorted(path for path in (FIXTURES / "scenarios").iterdir() if path.is_dir())


def load(*names: str) -> list[ParsedScore]:
    return [parse_score((FIXTURES / "input" / name).read_bytes(), name) for name in names]


def pick(scores: list[ParsedScore], *titles: str) -> list[SongRef]:
    by_title = {
        song.title: SongRef(parsed, song) for parsed in scores for song in parsed.summary.songs
    }
    return [by_title[title] for title in titles]


def export(refs: list[SongRef], name: str = "set") -> bytes:
    songs = [ref.song for ref in refs]
    return set_list_zip(name, assemble_set_list(refs, name), tuba_csv(songs))


def unzip(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def reimport(data: bytes, name: str = "set") -> list[list[str]]:
    parsed = parse_score(unzip(data)[f"{name}.musicxml"], f"{name}.musicxml")
    return [[song.title, song.tuba_line] for song in parsed.summary.songs]


def csv_rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline="")))


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda path: path.name)
def test_scenario_exports_and_reimports_to_the_expected_lines(scenario: Path) -> None:
    inputs = (scenario / "inputs.txt").read_text(encoding="utf-8").split()
    order = (scenario / "order.txt").read_text(encoding="utf-8").splitlines()
    expected = csv_rows((scenario / "expected.csv").read_text(encoding="utf-8"))
    files = unzip(export(pick(load(*inputs), *order)))
    assert csv_rows(files["set_tuba.csv"].decode("utf-8-sig")) == expected
    assert reimport(export(pick(load(*inputs), *order))) == expected


class TestZip:
    def test_members_are_named_after_the_output(self) -> None:
        files = unzip(export(pick(load("whole_line.musicxml"), "I Will Find"), "My Show"))
        assert sorted(files) == ["My Show.musicxml", "My Show_tuba.csv"]

    def test_musicxml_is_stored_uncompressed(self) -> None:
        data = export(pick(load("whole_line.musicxml"), "I Will Find"))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert archive.getinfo("set.musicxml").compress_type == zipfile.ZIP_STORED


class TestCsv:
    def test_has_a_bom_and_keeps_the_arrows(self) -> None:
        songs = [s for p in load("medley_two_songs.musicxml") for s in p.summary.songs]
        data = tuba_csv(songs)
        assert data.startswith(b"\xef\xbb\xbf")
        assert "Heads Will Roll,Bb Ab | Eb↑" in data.decode("utf-8-sig")

    def test_has_no_header_and_one_row_per_song_in_order(self) -> None:
        songs = [s for p in load("medley_two_songs.musicxml") for s in p.summary.songs]
        rows = csv_rows(tuba_csv(songs).decode("utf-8-sig"))
        assert [row[0] for row in rows] == ["Love Parade", "Heads Will Roll"]

    def test_a_title_with_a_comma_is_quoted(self) -> None:
        song = Song("1", "Hello, World", "score", 0, 0, "F | Ab")
        assert tuba_csv([song]).decode("utf-8-sig") == '"Hello, World",F | Ab\r\n'

    def test_a_song_without_a_tuba_line_keeps_its_row(self) -> None:
        song = Song("1", "Satisfaction", "score", 0, 0, "")
        assert tuba_csv([song]).decode("utf-8-sig") == "Satisfaction,\r\n"


class TestOutputName:
    @pytest.mark.parametrize(
        ("requested", "expected"),
        [
            pytest.param("set:list?", "setlist", id="forbidden-characters"),
            pytest.param("  My Show  ", "My Show", id="surrounding-spaces"),
            pytest.param("", "default", id="empty-uses-the-default"),
            pytest.param("???", "default", id="nothing-left-uses-the-default"),
            pytest.param("..", "default", id="only-dots"),
            pytest.param("CON", "CON_", id="reserved-windows-name"),
            pytest.param("Show ♭ ré", "Show ♭ ré", id="unicode-kept"),
        ],
    )
    def test_sanitised_for_windows(self, requested: str, expected: str) -> None:
        assert output_name(requested, "default") == expected

    def test_falls_back_when_the_default_is_unusable_too(self) -> None:
        assert output_name("", "???") == "set list"


class TestRoundTrip:
    def test_repeats_and_voltas_survive(self) -> None:
        refs = pick(load("repeats_and_voltas.musicxml"), "Repeats")
        data = export(refs)
        assert reimport(data) == [["Repeats", "F | Ab | Db↓ Eb | F | Ab | C↓"]]
        assert unzip(data)["set.musicxml"].count(b"<ending ") >= 2

    def test_a_song_after_a_gap_keeps_its_key_and_tempo(self) -> None:
        refs = pick(load("medley_two_songs.musicxml"), "Heads Will Roll")
        musicxml = unzip(export(refs))["set.musicxml"].decode("utf-8")
        assert "<fifths>-5</fifths>" in musicxml
        assert re.search(r'tempo="132(\.0+)?"', musicxml)
        assert "<rehearsal" in musicxml
        assert "Heads Will Roll" in musicxml

    def test_the_score_is_titled_and_does_not_credit_music21(self) -> None:
        refs = pick(load("whole_line.musicxml"), "I Will Find")
        root = ET.fromstring(unzip(export(refs, "My Show"))["My Show.musicxml"])
        assert root.findtext(".//work-title") == "My Show"
        assert "Music21" not in ET.tostring(root, encoding="unicode").split("<part-list>")[0]

    def test_exporting_twice_gives_the_same_result(self) -> None:
        refs = pick(load("medley_two_songs.musicxml"), "Heads Will Roll", "Love Parade")
        assert reimport(export(refs)) == reimport(export(refs))

    def test_a_rest_measure_closing_a_repeat_keeps_its_repeat(self) -> None:
        refs = pick(load("rest_closes_repeat.musicxml"), "Reprise", "Next Song")
        assert reimport(export(refs)) == [["Reprise", "F | Ab"], ["Next Song", "Bb | A | D↓"]]
        assert b'<repeat direction="backward"' in unzip(export(refs))["set.musicxml"]

    def test_the_same_song_title_in_two_scores_stays_two_songs(self) -> None:
        first, second = load("whole_line.musicxml", "whole_line.musicxml")
        refs = [SongRef(first, first.summary.songs[0]), SongRef(second, second.summary.songs[0])]
        refs.insert(1, pick(load("tuba_by_midi_program.musicxml"), "I'll Fly With You")[0])
        assert [row[0] for row in reimport(export(refs))] == [
            "I Will Find",
            "I'll Fly With You",
            "I Will Find",
        ]


class TestParts:
    @staticmethod
    def flute_score() -> ParsedScore:
        text = (FIXTURES / "input" / "no_tuba_part.musicxml").read_text(encoding="utf-8")
        return parse_score(text.replace("Trombone", "Flute").encode("utf-8"), "flute.musicxml")

    def test_parts_are_the_union_in_order_of_first_appearance_and_all_equally_long(self) -> None:
        flute = self.flute_score()
        refs = [
            SongRef(flute, flute.summary.songs[0]),
            *pick(load("medley_two_songs.musicxml"), "Love Parade"),
        ]
        root = ET.fromstring(unzip(export(refs))["set.musicxml"])
        names = [e.findtext("part-name") for e in root.iter("score-part")]
        assert names == ["Flute", "Trombone", "Tuba"]
        lengths = {len(part.findall("measure")) for part in root.findall("part")}
        assert len(lengths) == 1
        assert reimport(export(refs)) == [["Satisfaction", ""], ["Love Parade", "C | C | C | C"]]

    def test_rests_for_a_missing_part_keep_the_songs_repeats_and_endings(self) -> None:
        text = (FIXTURES / "input" / "repeats_and_voltas.musicxml").read_text(encoding="utf-8")
        no_tuba = text.replace("Tuba", "Flute").replace("<midi-program>59", "<midi-program>74")
        flute = parse_score(no_tuba.encode("utf-8"), "flute.musicxml")
        refs = [
            SongRef(flute, flute.summary.songs[0]),
            *pick(load("medley_two_songs.musicxml"), "Love Parade"),
        ]
        root = ET.fromstring(unzip(export(refs))["set.musicxml"])

        def barlines(part: ET.Element) -> list[tuple[str | None, str, list[str | None]]]:
            return [
                (
                    m.get("number"),
                    b.get("location", ""),
                    [e.get("direction") for e in b.iter("repeat")]
                    + [e.get("type") for e in b.iter("ending")],
                )
                for m in part.findall("measure")
                for b in m.findall("barline")
            ]

        by_part = {p.get("id"): barlines(p) for p in root.findall("part")}
        assert len(by_part) == 3  # Trombone, Flute, Tuba
        first = next(iter(by_part.values()))
        assert first  # the song has repeats
        assert all(lines == first for lines in by_part.values())

    def test_part_names_match_ignoring_case_and_spaces(self) -> None:
        text = (FIXTURES / "input" / "no_tuba_part.musicxml").read_text(encoding="utf-8")
        shouting = parse_score(
            text.replace("<part-name>Trombone", "<part-name>  TROMBONE ").encode("utf-8"),
            "shouting.musicxml",
        )
        refs = [
            SongRef(shouting, shouting.summary.songs[0]),
            *pick(load("medley_two_songs.musicxml"), "Love Parade"),
        ]
        root = ET.fromstring(unzip(export(refs))["set.musicxml"])
        assert len(list(root.iter("score-part"))) == 2  # Trombone and Tuba, not three parts
