"""Foto-opslag voor recepten: download (externe URL) of geüploade bytes.

Foto's staan in ``backend/data/recipe_photos/`` (gitignored; op de mini-PC een
Docker-volume). In de db komt enkel de bestandsnaam (``recipes.photo_path``) —
nooit een externe URL. Mislukt de opslag, dan wordt het recept gewoon zonder
foto opgeslagen (niet-fataal).
"""

import logging
import re
import uuid
from pathlib import Path

from app.config import get_settings
from app.weekmenu.errors import WeekmenuError
from app.weekmenu.url_security import MAX_PHOTO_BYTES, fetch_url

logger = logging.getLogger(__name__)


def _default_photos_dir() -> Path:
    """Dev-fallback: backend/data/recipe_photos.

    Tests verleggen dit via monkeypatch naar tmp_path.
    """
    return Path(__file__).resolve().parents[2] / "data" / "recipe_photos"


# WEEKMENU_PHOTOS_DIR-override (zie config.py) zodat dit in Docker naar het
# gemounte /data-volume wijst i.p.v. de container-eigen laag.
_configured_dir = get_settings().weekmenu_photos_dir
PHOTOS_DIR = Path(_configured_dir) if _configured_dir else _default_photos_dir()

_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MEDIA_TYPES = {ext.lstrip("."): media_type for media_type, ext in _EXTENSIONS.items()}

# uuid4().hex + bekende extensie — de enige vorm die wij ooit wegschrijven.
PHOTO_FILENAME_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|gif)$")


def media_type_for(filename: str) -> str:
    """Media type voor een geldige (regex-gematchte) foto-bestandsnaam."""
    return _MEDIA_TYPES[filename.rsplit(".", 1)[1]]


def save_photo_bytes(data: bytes, media_type: str) -> str | None:
    """Schrijf afbeeldingsbytes weg en geef de lokale bestandsnaam terug (None bij falen)."""
    extension = _EXTENSIONS.get(media_type)
    if extension is None:
        logger.warning(
            "Receptfoto niet weggeschreven: media type %r is geen afbeelding", media_type
        )
        return None
    filename = f"{uuid.uuid4().hex}{extension}"
    try:
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        (PHOTOS_DIR / filename).write_bytes(data)
    except OSError:
        logger.warning("Receptfoto niet weggeschreven naar %s", PHOTOS_DIR, exc_info=True)
        return None
    return filename


def save_photo_from_url(photo_url: str) -> str | None:
    """Download de foto SSRF-veilig en geef de lokale bestandsnaam terug (None bij falen)."""
    try:
        result = fetch_url(photo_url, MAX_PHOTO_BYTES)
    except WeekmenuError as exc:
        logger.warning("Receptfoto niet gedownload (%s): %s", photo_url, exc.message)
        return None
    if result.content_type not in _EXTENSIONS:
        logger.warning(
            "Receptfoto niet gedownload (%s): content-type %r is geen afbeelding",
            photo_url,
            result.content_type,
        )
        return None
    return save_photo_bytes(result.content, result.content_type)


def delete_photo(filename: str | None) -> None:
    """Verwijder een fotobestand best-effort; een fout mag nooit een request breken."""
    if not filename or not PHOTO_FILENAME_RE.fullmatch(filename):
        return
    try:
        (PHOTOS_DIR / filename).unlink(missing_ok=True)
    except OSError:
        logger.warning("Receptfoto %s niet verwijderd uit %s", filename, PHOTOS_DIR, exc_info=True)
