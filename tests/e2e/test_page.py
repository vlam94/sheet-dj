"""Browser tests of the page. Run with `pytest -m e2e` (needs the e2e extra and a browser)."""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
import waitress
from playwright.sync_api import Page, expect

from sheet_dj.config import Config
from sheet_dj.library import Library
from sheet_dj.server import create_app

pytestmark = pytest.mark.e2e

INPUTS = Path(__file__).parent.parent / "fixtures" / "input"
SCORES = ["cycle_single_note", "whole_line", "tuba_by_midi_program", "medley_two_songs"]
LIBRARY_TITLES = [
    "Satisfaction",
    "I Will Find",
    "I'll Fly With You",
    "Love Parade",
    "Heads Will Roll",
]


@pytest.fixture
def page_url() -> Iterator[str]:
    app = create_app(Config())
    library: Library = app.extensions["sheet_dj_library"]
    for name in SCORES:
        library.add((INPUTS / f"{name}.musicxml").read_bytes(), f"{name}.musicxml")
    server = waitress.create_server(app, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.effective_port}/"
    server.close()


@pytest.fixture
def page(page: Page, page_url: str) -> Page:
    page.goto(page_url)
    return page


def titles(page: Page, list_id: str) -> list[str]:
    return page.locator(f"#{list_id} li .title").all_inner_texts()


def song(page: Page, title: str, list_id: str = "songs"):
    return page.locator(f"#{list_id} li", has=page.locator(".title", has_text=title)).first


def test_the_songs_are_listed_in_library_order(page: Page) -> None:
    assert titles(page, "songs") == LIBRARY_TITLES
    assert titles(page, "set-list") == []


def test_dragging_a_song_into_the_set_list(page: Page) -> None:
    song(page, "Love Parade").drag_to(page.locator("#set-list"))
    assert titles(page, "set-list") == ["Love Parade"]
    assert "Love Parade" not in titles(page, "songs")


def test_ctrl_click_selects_several_and_add_moves_them_in_order(page: Page) -> None:
    song(page, "Love Parade").click()
    song(page, "Satisfaction").click(modifiers=["Control"])
    page.get_by_role("button", name="Add →").click()
    assert titles(page, "set-list") == [
        "Satisfaction",
        "Love Parade",
    ]  # list order, not click order


def test_a_plain_click_selects_only_that_song(page: Page) -> None:
    song(page, "Satisfaction").click()
    song(page, "Love Parade").click()
    assert page.locator("#songs li.selected").count() == 1


def test_shift_click_selects_a_range(page: Page) -> None:
    song(page, "I Will Find").click()
    song(page, "Love Parade").click(modifiers=["Shift"])
    page.get_by_role("button", name="Add →").click()
    assert titles(page, "set-list") == ["I Will Find", "I'll Fly With You", "Love Parade"]


def test_double_click_moves_a_song_across_and_back(page: Page) -> None:
    song(page, "Heads Will Roll").dblclick()
    assert titles(page, "set-list") == ["Heads Will Roll"]
    song(page, "Heads Will Roll", "set-list").dblclick()
    assert titles(page, "songs") == LIBRARY_TITLES  # back in library order


def test_keyboard_selects_and_moves(page: Page) -> None:
    song(page, "I Will Find").focus()
    page.keyboard.press("Space")
    page.get_by_role("button", name="Add →").click()
    assert titles(page, "set-list") == ["I Will Find"]
    song(page, "Satisfaction").focus()
    page.keyboard.press("Enter")
    assert titles(page, "set-list") == ["I Will Find", "Satisfaction"]


def test_remove_sends_selected_songs_back(page: Page) -> None:
    page.get_by_role("button", name="Select all").first.click()
    page.get_by_role("button", name="Add →").click()
    assert titles(page, "songs") == []
    song(page, "Love Parade", "set-list").click()
    page.get_by_role("button", name="← Remove").click()
    assert titles(page, "songs") == ["Love Parade"]
    assert len(titles(page, "set-list")) == 4


def test_move_up_and_down_reorder_the_set_list(page: Page) -> None:
    page.get_by_role("button", name="Select all").first.click()
    page.get_by_role("button", name="Add →").click()
    song(page, "Love Parade", "set-list").click()
    page.get_by_role("button", name="Move up").click()
    assert titles(page, "set-list")[2] == "Love Parade"
    page.get_by_role("button", name="Move down").click()
    page.get_by_role("button", name="Move down").click()
    assert titles(page, "set-list")[4] == "Love Parade"
    page.get_by_role("button", name="Move down").click()  # already last: stays
    assert titles(page, "set-list")[4] == "Love Parade"


def test_shuffle_keeps_the_same_songs(page: Page) -> None:
    page.get_by_role("button", name="Select all").first.click()
    page.get_by_role("button", name="Add →").click()
    page.get_by_role("button", name="Shuffle").click()
    assert sorted(titles(page, "set-list")) == sorted(LIBRARY_TITLES)


def test_random_moves_exactly_n_songs(page: Page) -> None:
    page.fill("#random-count", "2")
    page.get_by_role("button", name="Random").click()
    assert len(titles(page, "set-list")) == 2
    assert len(titles(page, "songs")) == 3
    page.fill("#random-count", "10")  # more than are left: moves what is there
    page.get_by_role("button", name="Random").click()
    assert len(titles(page, "set-list")) == 5
    assert titles(page, "songs") == []


def test_random_with_nothing_typed_does_nothing(page: Page) -> None:
    page.fill("#random-count", "")
    page.get_by_role("button", name="Random").click()
    assert titles(page, "set-list") == []


def test_the_set_list_and_name_survive_a_reload(page: Page) -> None:
    song(page, "Love Parade").dblclick()
    song(page, "Satisfaction").dblclick()
    page.fill("input[name=name]", "Friday")
    page.reload()
    assert titles(page, "set-list") == ["Love Parade", "Satisfaction"]
    assert page.input_value("input[name=name]") == "Friday"


def test_download_sends_the_set_list_as_a_zip(page: Page) -> None:
    song(page, "Love Parade").dblclick()
    page.fill("input[name=name]", "My Show")
    with page.expect_download() as download:
        page.get_by_role("button", name="Download set list").click()
    assert download.value.suggested_filename == "My Show.zip"


def test_download_with_an_empty_set_list_says_why(page: Page) -> None:
    page.get_by_role("button", name="Download set list").click()
    expect(page.get_by_role("alert")).to_contain_text("The set list is empty")
    assert titles(page, "songs") == LIBRARY_TITLES


def test_adding_a_file_shows_the_songs_and_keeps_the_set_list(page: Page) -> None:
    song(page, "Love Parade").dblclick()
    page.set_input_files("input[name=scores]", str(INPUTS / "ties_rests_chords.musicxml"))
    page.get_by_role("button", name="Add scores").click()
    expect(page.get_by_role("alert")).to_contain_text("Added ties_rests_chords.musicxml")
    assert "Ties" in titles(page, "songs")
    assert titles(page, "set-list") == ["Love Parade"]
    assert page.url.endswith("/")
