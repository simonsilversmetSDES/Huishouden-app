"""Foto-download bij het opslaan van een recept (Fase 2-beslissing).

De parsers geven een EXTERNE foto-URL terug; bij POST /recipes wordt die hier
gedownload naar ``backend/data/recipe_photos/`` (gitignored; op de mini-PC een
Docker-volume). In de db komt enkel de bestandsnaam (``recipes.photo_path``) —
nooit een externe URL. Mislukt de download, dan wordt het recept gewoon zonder
foto opgeslagen (niet-fataal).
"""

import logging
import uuid
from pathlib import Path

from app.weekmenu.errors import WeekmenuError
from app.weekmenu.url_security import MAX_PHOTO_BYTES, fetch_url

logger = logging.getLogger(__name__)

# backend/data/recipe_photos — tests verleggen dit via monkeypatch naar tmp_path.
PHOTOS_DIR = Path(__file__).resolve().parents[2] / "data" / "recipe_photos"

_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def save_photo_from_url(photo_url: str) -> str | None:
    """Download de foto SSRF-veilig en geef de lokale bestandsnaam terug (None bij falen)."""
    try:
        result = fetch_url(photo_url, MAX_PHOTO_BYTES)
    except WeekmenuError as exc:
        logger.warning("Receptfoto niet gedownload (%s): %s", photo_url, exc.message)
        return None
    extension = _EXTENSIONS.get(result.content_type)
    if extension is None:
        logger.warning(
            "Receptfoto niet gedownload (%s): content-type %r is geen afbeelding",
            photo_url,
            result.content_type,
        )
        return None
    filename = f"{uuid.uuid4().hex}{extension}"
    try:
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        (PHOTOS_DIR / filename).write_bytes(result.content)
    except OSError:
        logger.warning("Receptfoto niet weggeschreven naar %s", PHOTOS_DIR, exc_info=True)
        return None
    return filename
