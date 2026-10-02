"""The page and its routes. Messages shown here come from the catalogue, never from exceptions."""

import io
import logging
import re
from dataclasses import dataclass
from enum import Enum

from flask import (
    Blueprint,
    Flask,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from markupsafe import Markup, escape
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.wrappers import Response

from sheet_dj.config import APP_NAME, Config
from sheet_dj.export import output_name, set_list_zip, tuba_csv
from sheet_dj.library import Library
from sheet_dj.model import ScoreSummary, UserError
from sheet_dj.parsing import no_tuba_message

logger = logging.getLogger(__name__)
bp = Blueprint("sheet_dj", __name__)

E01_NO_FILE = (
    "No score was chosen. Click *Add scores* and pick one or more MusicXML files "
    "exported from MuseScore."
)
E04_TOO_LARGE = "These files are too large to add at once (limit {n} MB). Add them a few at a time."
E08_EMPTY_SET_LIST = (
    "The set list is empty. Move songs from *Songs* into *Set list* first, then download."
)
E12_UNEXPECTED = (
    "Something went wrong and the app could not finish. Your songs are still loaded. "
    "Try again; if it keeps happening, close the app and open it again."
)
ADDED = "Added *{file}*: {count}."
ITALICS = re.compile(r"\*(.+?)\*")


class Kind(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Notice:
    """A message for the top of the page."""

    kind: Kind
    text: str


def init_app(app: Flask, config: Config, library: Library) -> None:
    """Attach the library, the upload limit, the routes and the error handlers to `app`."""
    app.config["MAX_CONTENT_LENGTH"] = config.max_upload_mb * 1024 * 1024
    app.extensions["sheet_dj_config"] = config
    app.extensions["sheet_dj_library"] = library
    app.add_template_filter(italics)
    app.register_blueprint(bp)
    app.register_error_handler(RequestEntityTooLarge, too_large)
    app.register_error_handler(Exception, unexpected)


def italics(message: str) -> Markup:
    """Render a catalogue message: escape it, then turn *this* into italics."""
    return Markup(ITALICS.sub(r"<em>\1</em>", str(escape(message))))


def _library() -> Library:
    library: Library = current_app.extensions["sheet_dj_library"]
    return library


def _config() -> Config:
    config: Config = current_app.extensions["sheet_dj_config"]
    return config


def _page(*notices: Notice, set_list_ids: list[str] | None = None, name: str = "") -> str:
    """Render the page with the library as it is, and the set list and name the user had."""
    library = _library()
    scores = library.scores()
    songs = library.songs()
    by_id = {song.id: song for song in songs}
    chosen = [i for i in dict.fromkeys(set_list_ids or []) if i in by_id]
    default_name = scores[0].summary.name if scores else ""
    return render_template(
        "index.html",
        notices=list(dict.fromkeys(notices)),
        scores=[(s.summary, _warning(s.summary)) for s in scores],
        available=[song for song in songs if song.id not in chosen],
        set_list=[by_id[i] for i in chosen],
        position={song.id: index for index, song in enumerate(songs)},
        default_name=default_name,
        name=name or default_name,
    )


def _warning(summary: ScoreSummary) -> str | None:
    return no_tuba_message(summary.file_name) if summary.tuba_part_name is None else None


def _error(text: str) -> Notice:
    return Notice(Kind.ERROR, text)


@bp.get("/")
def index() -> str:
    """The page."""
    return _page()


@bp.get("/healthz")
def healthz() -> Response:
    """Tell the launcher that this port is served by this app."""
    return jsonify(app=APP_NAME)


@bp.post("/scores")
def add_scores() -> str:
    """Add each chosen file independently; one bad file never blocks the others."""
    files = [file for file in request.files.getlist("scores") if file.filename]
    if not files:
        return _page(_error(E01_NO_FILE))
    notices: list[Notice] = []
    for file in files:
        name = file.filename or ""
        try:
            parsed = _library().add(file.read(), name)
        except UserError as exc:
            logger.warning("Could not add %s (%s)", name, exc.catalogue_id, exc_info=exc)
            notices.append(_error(exc.message))
        else:
            count = len(parsed.summary.songs)
            notices.append(
                Notice(
                    Kind.INFO,
                    ADDED.format(
                        file=parsed.summary.file_name, count=f"{count} song{'s' * (count != 1)}"
                    ),
                )
            )
    return _page(*notices)


@bp.post("/scores/clear")
def clear_scores() -> Response:
    """Empty the library."""
    _library().clear()
    return redirect(url_for("sheet_dj.index"))


@bp.post("/export")
def export() -> Response | str:
    """Download the set list as a zip, or show the page again with what went wrong."""
    song_ids = request.form.getlist("song")
    requested = request.form.get("name", "")
    if not song_ids:
        return _page(_error(E08_EMPTY_SET_LIST), name=requested)
    scores = _library().scores()
    name = output_name(requested, scores[0].summary.name if scores else "")
    try:
        musicxml, songs = _library().build_set_list(song_ids, name)
    except UserError as exc:
        return _page(_error(exc.message), set_list_ids=song_ids, name=requested)
    data = set_list_zip(name, musicxml, tuba_csv(songs))
    return send_file(
        io.BytesIO(data),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{name}.zip",
    )


def too_large(_: RequestEntityTooLarge) -> str:
    """Show E04 for an upload over the limit."""
    return _page(_error(E04_TOO_LARGE.format(n=_config().max_upload_mb)))


def unexpected(exc: Exception) -> Response | str:
    """The one top-level handler: log the traceback, show E12 with the user's work kept."""
    if isinstance(exc, HTTPException):
        return exc.get_response()
    logger.error("Unexpected error on %s %s", request.method, request.path, exc_info=exc)
    return _page(
        _error(E12_UNEXPECTED),
        set_list_ids=request.form.getlist("song"),
        name=request.form.get("name", ""),
    )
