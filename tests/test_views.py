import html
import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from sheet_dj.config import Config
from sheet_dj.library import Library
from sheet_dj.server import create_app

FIXTURES = Path(__file__).parent / "fixtures" / "input"
LOADED_TITLES = ["I Will Find", "I'll Fly With You"]  # what every test starts with


def make_app(**settings: int) -> Flask:
    app = create_app(Config(**settings))
    app.config["TESTING"] = True
    return app


def library_of(app: Flask) -> Library:
    library: Library = app.extensions["sheet_dj_library"]
    return library


def upload(client: FlaskClient, *names: str, extra: dict[str, bytes] | None = None) -> TestResponse:
    files = [(io.BytesIO((FIXTURES / name).read_bytes()), name) for name in names]
    files += [(io.BytesIO(data), name) for name, data in (extra or {}).items()]
    return client.post("/scores", data={"scores": files}, content_type="multipart/form-data")


def text_of(response: TestResponse) -> str:
    """The visible text of a page: tags dropped, entities decoded, spaces collapsed."""
    markup = re.sub(r"</?em>", "", response.get_data(as_text=True))
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def plain(message: str) -> str:
    """A catalogue message as it reads on the page: without the *italics* marks."""
    return " ".join(message.replace("*", "").split())


def set_list_ids(raw_page: str) -> list[str]:
    """The song ids the page puts in the set list, in order."""
    section = re.search(r'<ul id="set-list".*?</ul>', raw_page, re.DOTALL)
    assert section
    return re.findall(r'data-id="(\w+)"', section.group(0))


def song_ids(app: Flask) -> dict[str, str]:
    return {song.title: song.id for song in library_of(app).songs()}


@pytest.fixture
def app() -> Flask:
    app = make_app()
    with app.test_client() as client:
        upload(client, "whole_line.musicxml", "tuba_by_midi_program.musicxml")
    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@dataclass(frozen=True)
class Case:
    """One catalogue entry: how to provoke it, and what the page must say and keep."""

    provoke: Callable[[Flask], TestResponse]
    message: str  # exact, as in the catalogue but without the *italics* marks
    keeps_set_list: bool = False
    loaded: tuple[str, ...] = tuple(LOADED_TITLES)  # songs that must still be on the page


def after_upload(
    *names: str, extra: dict[str, bytes] | None = None
) -> Callable[[Flask], TestResponse]:
    return lambda app: upload(app.test_client(), *names, extra=extra)


def e04(_: Flask) -> TestResponse:
    client = make_app(max_upload_mb=1).test_client()
    upload(client, "whole_line.musicxml")
    return upload(client, extra={"big.musicxml": b"x" * (2 * 1024 * 1024)})


def e11(_: Flask) -> TestResponse:
    app = make_app(max_files=1)
    return upload(app.test_client(), "whole_line.musicxml", "tuba_by_midi_program.musicxml")


def export_with(*, ids: Callable[[Flask], list[str]], name: str) -> Callable[[Flask], TestResponse]:
    return lambda app: app.test_client().post("/export", data={"song": ids(app), "name": name})


def e12(app: Flask) -> TestResponse:
    from sheet_dj import views

    original = views.set_list_zip

    def boom(*_: object) -> bytes:
        raise RuntimeError("boom from deep inside")

    views.set_list_zip = boom  # type: ignore[assignment]
    try:
        return export_with(ids=lambda a: list(song_ids(a).values()), name="Mine")(app)
    finally:
        views.set_list_zip = original


CATALOGUE = [
    pytest.param(
        Case(
            lambda app: app.test_client().post("/scores", data={"scores": (io.BytesIO(b""), "")}),
            "No score was chosen. Click Add scores and pick one or more MusicXML files "
            "exported from MuseScore.",
        ),
        id="E01",
    ),
    pytest.param(
        Case(
            after_upload("project_file.mscz"),
            "Could not read project_file.mscz. This is a MuseScore project file — open it in "
            "MuseScore, use File → Export → MusicXML, and add that file instead.",
        ),
        id="E02",
    ),
    pytest.param(
        Case(
            after_upload(extra={"scan.pdf": b"%PDF-1.4"}),
            "scan.pdf is a picture or PDF of sheet music, not a score file. Open the score in "
            "MuseScore and use File → Export → MusicXML, then add that file.",
        ),
        id="E03",
    ),
    pytest.param(
        Case(
            e04,
            "These files are too large to add at once (limit 1 MB). Add them a few at a time.",
            loaded=("I Will Find",),
        ),
        id="E04",
    ),
    pytest.param(
        Case(
            after_upload("broken_xml.musicxml"),
            "Could not read broken_xml.musicxml. It looks damaged or is not a MusicXML score. "
            "Export it again from MuseScore (File → Export → MusicXML) and add the new file.",
        ),
        id="E05",
    ),
    pytest.param(
        Case(
            after_upload("empty_score.musicxml"),
            "empty_score.musicxml has no notes in it. Check that you exported the full score "
            "and not an empty part.",
        ),
        id="E06",
    ),
    pytest.param(
        Case(
            after_upload("no_tuba_part.musicxml"),
            "No tuba part was found in no_tuba_part.musicxml. Its songs were added, but their "
            'tuba lines are empty. If the score has a tuba, name its part "Tuba" in MuseScore '
            "and export again.",
        ),
        id="E07",
    ),
    pytest.param(
        Case(
            export_with(ids=lambda app: [], name="Mine"),
            "The set list is empty. Move songs from Songs into Set list first, then download.",
        ),
        id="E08",
    ),
    pytest.param(
        Case(
            export_with(
                ids=lambda app: [*song_ids(app).values(), "gone"],
                name="Mine",
            ),
            "Some songs in your set list are no longer loaded — the app was closed while idle. "
            "Add your scores again and rebuild the set list.",
            keeps_set_list=True,
        ),
        id="E09",
    ),
    pytest.param(
        Case(
            after_upload("whole_line.musicxml"),
            "whole_line.musicxml is already loaded, so it was skipped.",
        ),
        id="E10",
    ),
    pytest.param(
        Case(
            e11,
            "Only 1 scores can be loaded at once. Use Clear all and add the ones you need.",
            loaded=("I Will Find",),
        ),
        id="E11",
    ),
    pytest.param(
        Case(
            e12,
            "Something went wrong and the app could not finish. Your songs are still loaded. "
            "Try again; if it keeps happening, close the app and open it again.",
            keeps_set_list=True,
        ),
        id="E12",
    ),
]


@pytest.mark.parametrize("case", CATALOGUE)
def test_catalogue_entry(case: Case, app: Flask, caplog: pytest.LogCaptureFixture) -> None:
    response = case.provoke(app)
    page = text_of(response)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "Traceback" not in page
    assert case.message in page
    if case.message.startswith("Something went wrong"):
        assert "boom" not in page  # the cause is logged, never shown
        assert "boom from deep inside" in caplog.text
    assert all(title in page for title in case.loaded)  # the songs loaded survived
    if case.keeps_set_list:
        raw = response.get_data(as_text=True)
        assert set_list_ids(raw) == list(song_ids(app).values())
        assert 'name="name" value="Mine"' in raw


def test_catalogue_e08_keeps_the_name(app: Flask) -> None:
    response = app.test_client().post("/export", data={"name": "Mine"})
    assert 'name="name" value="Mine"' in response.get_data(as_text=True)


class TestUpload:
    def test_one_bad_file_does_not_block_the_good_ones(self, client: FlaskClient) -> None:
        response = upload(
            client, "cycle_single_note.musicxml", "broken_xml.musicxml", "project_file.mscz"
        )
        page = text_of(response)
        assert "Satisfaction" in page
        assert "Added cycle_single_note.musicxml: 1 song." in page
        assert "Could not read broken_xml.musicxml" in page
        assert "Could not read project_file.mscz" in page

    def test_reloading_keeps_the_loaded_songs(self, client: FlaskClient) -> None:
        page = text_of(client.get("/"))
        assert all(title in page for title in LOADED_TITLES)

    def test_shows_the_tuba_part_of_each_score(self, client: FlaskClient) -> None:
        page = text_of(client.get("/"))
        assert "whole_line.musicxml Tuba part: Tuba" in page
        assert "tuba_by_midi_program.musicxml Tuba part: Baixo" in page

    def test_shows_each_songs_tuba_line(self, client: FlaskClient) -> None:
        assert "Bb | A | D↓ | D | F G | A" in text_of(client.get("/"))

    def test_titles_from_a_score_are_escaped(self, app: Flask) -> None:
        text = (FIXTURES / "no_tuba_part.musicxml").read_text(encoding="utf-8")
        evil = text.replace("Satisfaction", "&lt;script&gt;alert(1)&lt;/script&gt;")
        response = upload(app.test_client(), extra={"evil.musicxml": evil.encode("utf-8")})
        assert "<script>alert(1)" not in response.get_data(as_text=True)
        assert "<script>alert(1)</script>" in text_of(response)

    def test_clear_all_empties_the_library(self, client: FlaskClient, app: Flask) -> None:
        response = client.post("/scores/clear")
        assert response.status_code == 302
        assert library_of(app).songs() == []
        assert "I Will Find" not in text_of(client.get("/"))

    def test_each_app_has_its_own_library(self, app: Flask) -> None:
        assert library_of(make_app()).songs() == []
        assert library_of(app).songs()


class TestExport:
    def ids(self, app: Flask, *titles: str) -> list[str]:
        by_title = song_ids(app)
        return [by_title[title] for title in titles]

    def test_downloads_a_zip_in_the_order_given(self, client: FlaskClient, app: Flask) -> None:
        ids = self.ids(app, "I'll Fly With You", "I Will Find")
        response = client.post("/export", data={"song": ids, "name": "My Show"})
        assert response.status_code == 200
        assert response.mimetype == "application/zip"
        assert 'filename="My Show.zip"' in response.headers["Content-Disposition"]
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            assert archive.namelist() == ["My Show.musicxml", "My Show_tuba.csv"]
            rows = archive.read("My Show_tuba.csv").decode("utf-8-sig").splitlines()
        assert rows == ["I'll Fly With You,F | A | D | Bb", "I Will Find,Bb | A | D↓ | D | F G | A"]

    def test_the_name_is_made_safe_for_windows(self, client: FlaskClient, app: Flask) -> None:
        ids = self.ids(app, "I Will Find")
        response = client.post("/export", data={"song": ids, "name": "set:list?"})
        assert "filename=setlist.zip" in response.headers["Content-Disposition"]

    def test_an_empty_name_defaults_to_the_first_score(
        self, client: FlaskClient, app: Flask
    ) -> None:
        ids = self.ids(app, "I Will Find")
        response = client.post("/export", data={"song": ids, "name": "  "})
        assert "filename=whole_line.zip" in response.headers["Content-Disposition"]

    def test_a_song_listed_twice_is_exported_once(self, client: FlaskClient, app: Flask) -> None:
        ids = self.ids(app, "I Will Find") * 2
        response = client.post("/export", data={"song": ids, "name": "x"})
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            csv_text = archive.read("x_tuba.csv").decode("utf-8-sig")
        assert csv_text.count("I Will Find") == 1


def test_unknown_page_is_not_a_traceback(client: FlaskClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert "Traceback" not in response.get_data(as_text=True)


class TestOffline:
    ASSETS = (
        "vendor/Sortable.min.js",
        "vendor/Sortable.LICENSE",
        "vendor/pico.min.css",
        "vendor/pico.LICENSE.md",
        "app.js",
        "app.css",
    )

    def test_the_page_links_nothing_outside_the_app(self, client: FlaskClient) -> None:
        links = re.findall(r'(?:src|href|action)="([^"]*)"', client.get("/").get_data(as_text=True))
        assert links
        assert all(link.startswith("/") for link in links)

    @pytest.mark.parametrize("asset", ASSETS)
    def test_vendored_and_own_assets_are_served_with_their_licences(
        self, client: FlaskClient, asset: str
    ) -> None:
        assert client.get(f"/static/{asset}").status_code == 200


def test_healthz_names_the_app(client: FlaskClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"app": "sheet-dj"}
