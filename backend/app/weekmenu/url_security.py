"""SSRF-veilige URL-validatie en fetch voor Weekmenu (WEEKMENU_BUILD.md Fase 2).

De app staat publiek bereikbaar; elke door de gebruiker aangeleverde URL (recept-HTML
én foto-download) gaat door ``validate_external_url`` + ``fetch_url``. Redirects worden
handmatig gevolgd zodat elke tussenstap opnieuw gevalideerd wordt.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from app.weekmenu.errors import WeekmenuError

FETCH_TIMEOUT_SECONDS = 15.0
MAX_REDIRECTS = 10
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_PHOTO_BYTES = 10 * 1024 * 1024


def _invalid(message: str) -> WeekmenuError:
    return WeekmenuError(400, "invalid_url", message)


def _fetch_failed(message: str) -> WeekmenuError:
    return WeekmenuError(502, "fetch_failed", message)


def validate_external_url(url: str) -> None:
    """Weiger alles behalve http(s) naar een publiek IP.

    De hostnaam wordt geresolved (getaddrinfo) en ÉLK opgelost adres moet publiek
    zijn — zo worden ook hostnames die naar een intern IP wijzen geweigerd, niet
    alleen letterlijke IP's in de URL (localhost, 127.0.0.1, 10.x, 192.168.x,
    169.254.x, 172.16/12, ::1, 0.0.0.0, ...).
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise _invalid("Alleen http- en https-URL's zijn toegestaan.")
    host = parts.hostname
    if not host:
        raise _invalid("Deze URL bevat geen geldige hostnaam.")

    try:
        addr_info = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise _fetch_failed("De hostnaam kon niet opgezocht worden.") from exc

    for info in addr_info:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise _invalid("Deze URL is niet toegestaan (intern adres).")


@dataclass
class FetchResult:
    content: bytes
    content_type: str  # zonder parameters, bv. "text/html"
    final_url: str  # URL na eventuele redirects (bron-URL voor het recept)


def fetch_url(url: str, max_bytes: int) -> FetchResult:
    """Haal een externe URL op met SSRF-check op elke redirect-stap.

    Timeout en groottelimiet zorgen dat een trage of te grote URL de backend niet
    laat hangen; de response wordt gestreamd en afgebroken zodra ``max_bytes``
    overschreden wordt. Eén client voor de hele redirect-keten (cookies blijven
    dus bewaard tussen stappen) — sommige sites (bv. Roularta-titels als
    Libelle Lekker) doen een silent-SSO-redirect die zonder sessiecookie
    faalt en op een loginpagina eindigt in plaats van het artikel.
    """
    current = url
    with httpx.Client(
        follow_redirects=False,
        timeout=FETCH_TIMEOUT_SECONDS,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept-Language": "nl-BE,nl;q=0.9,en;q=0.6",
        },
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_external_url(current)
            try:
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise _fetch_failed("De pagina stuurde een kapotte redirect.")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        raise _fetch_failed(
                            f"De pagina kon niet opgehaald worden (HTTP {response.status_code})."
                        )
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise _fetch_failed("De pagina of afbeelding is te groot.")
                        chunks.append(chunk)
                    content_type = response.headers.get("content-type", "")
                    return FetchResult(
                        content=b"".join(chunks),
                        content_type=content_type.split(";")[0].strip().lower(),
                        final_url=current,
                    )
            except httpx.HTTPError as exc:
                raise _fetch_failed("De pagina kon niet opgehaald worden.") from exc
    raise _fetch_failed("Te veel redirects.")
