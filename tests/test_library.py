import io
import zipfile
from pathlib import Path

from sheet_dj.library import Library
from sheet_dj.parsing import parse_score

INPUTS = Path(__file__).parent / "fixtures" / "input"
DEFAULTS = (
    "<defaults><scaling><millimeters>6.5</millimeters><tenths>40</tenths></scaling>"
    "<page-layout><page-height>1234</page-height><page-width>987</page-width></page-layout>"
    "</defaults>"
)


def with_defaults(name: str) -> bytes:
    text = (INPUTS / name).read_text(encoding="utf-8")
    return text.replace("<part-list>", f"{DEFAULTS}<part-list>", 1).encode("utf-8")


def plain(name: str) -> bytes:
    return (INPUTS / name).read_bytes()


def exported(library: Library, title: str) -> str:
    song = next(s for s in library.songs() if s.title == title)
    data, _ = library.build_set_list([song.id], "out")
    return data.decode("utf-8")


class TestLayoutDefaults:
    def test_a_score_remembers_its_defaults_element(self) -> None:
        parsed = parse_score(with_defaults("whole_line.musicxml"), "a.musicxml")
        assert parsed.layout_defaults is not None
        assert "<page-height>1234</page-height>" in parsed.layout_defaults

    def test_a_score_without_defaults_has_none(self) -> None:
        assert parse_score(plain("whole_line.musicxml"), "a.musicxml").layout_defaults is None

    def test_a_compressed_mxl_keeps_its_defaults_too(self) -> None:
        container = (
            '<?xml version="1.0"?><container><rootfiles>'
            '<rootfile full-path="score.xml"/></rootfiles></container>'
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("score.xml", with_defaults("whole_line.musicxml"))
        parsed = parse_score(buffer.getvalue(), "a.mxl")
        assert parsed.layout_defaults is not None
        assert "<page-width>987</page-width>" in parsed.layout_defaults

    def test_the_export_copies_the_first_loaded_files_defaults(self) -> None:
        library = Library(max_scores=5)
        library.add(with_defaults("whole_line.musicxml"), "first.musicxml")
        library.add(plain("tuba_by_midi_program.musicxml"), "second.musicxml")
        musicxml = exported(library, "I'll Fly With You")  # a song of the second file
        assert musicxml.count("<defaults") == 1
        assert "<page-height>1234</page-height>" in musicxml
        assert musicxml.index("<defaults") < musicxml.index("<part-list")
        credit = musicxml.find("<credit")
        assert credit == -1 or musicxml.index("<defaults") < credit

    def test_the_exported_file_still_reads_back(self) -> None:
        library = Library(max_scores=5)
        library.add(with_defaults("whole_line.musicxml"), "first.musicxml")
        reread = parse_score(exported(library, "I Will Find").encode("utf-8"), "out.musicxml")
        assert [s.tuba_line for s in reread.summary.songs] == ["Bb | A | D↓ | D | F G | A"]

    def test_a_first_file_without_defaults_leaves_the_export_as_built(self) -> None:
        library = Library(max_scores=5)
        library.add(plain("whole_line.musicxml"), "first.musicxml")
        library.add(with_defaults("tuba_by_midi_program.musicxml"), "second.musicxml")
        assert "<page-height>1234</page-height>" not in exported(library, "I Will Find")
