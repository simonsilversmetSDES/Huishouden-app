"""SSRF-validatie en fetch-limieten voor Weekmenu. Geen netwerk in tests."""

import ipaddress
from contextlib import contextmanager

import pytest

from app.weekmenu import url_security
from app.weekmenu.errors import WeekmenuError
from app.weekmenu.url_security import fetch_url, validate_external_url


def _fake_getaddrinfo(ip: str):
    def fake(host, port, *args, **kwargs):
        try:
            ipaddress.ip_address(host)  # IP-literal resolvet naar zichzelf
            return [(2, 1, 6, "", (host, 0))]
        except ValueError:
            return [(2, 1, 6, "", (ip, 0))]

    return fake


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/recept",
        "file:///etc/passwd",
        "gopher://example.com/",
        "http://localhost/recept",
        "http://127.0.0.1/recept",
        "http://127.0.0.1:8000/recept",
        "http://192.168.1.5/recept",
        "http://10.0.0.1/recept",
        "http://169.254.1.1/recept",
        "http://172.16.0.1/recept",
        "http://[::1]/recept",
        "http://0.0.0.0/recept",
        "https:///pad-zonder-host",
    ],
)
def test_interne_en_ongeldige_urls_geweigerd(url: str) -> None:
    with pytest.raises(WeekmenuError) as exc_info:
        validate_external_url(url)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_url"


def test_hostnaam_die_naar_intern_ip_resolvet_geweigerd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ook een publiek ogende hostnaam wordt ná DNS-resolutie gecheckt."""
    monkeypatch.setattr(url_security.socket, "getaddrinfo", _fake_getaddrinfo("10.0.0.5"))
    with pytest.raises(WeekmenuError) as exc_info:
        validate_external_url("https://ogenschijnlijk-publiek.example.com/recept")
    assert exc_info.value.code == "invalid_url"


def test_publieke_hostnaam_toegestaan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(url_security.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    validate_external_url("https://example.com/recept")  # geen exception


def test_onbekende_hostnaam_geeft_fetch_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_gaierror(*args, **kwargs):
        raise OSError("naam niet gevonden")

    monkeypatch.setattr(url_security.socket, "getaddrinfo", raise_gaierror)
    with pytest.raises(WeekmenuError) as exc_info:
        validate_external_url("https://bestaat-niet.example.invalid/")
    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "fetch_failed"


class _FakeResponse:
    def __init__(self, status_code: int = 200, headers: dict | None = None, body: bytes = b""):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body

    @property
    def is_redirect(self) -> bool:
        return 300 <= self.status_code < 400

    def iter_bytes(self):
        # In stukjes zodat de groottelimiet per chunk getest wordt.
        for i in range(0, len(self._body), 1024):
            yield self._body[i : i + 1024]


class _FakeClient:
    """Vervangt httpx.Client; geeft per URL een vooraf bepaalde response terug."""

    responses: dict[str, _FakeResponse] = {}

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @contextmanager
    def stream(self, method: str, url: str):
        yield self.responses[url]


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    """Geen netwerk in tests: httpx.Client en DNS vervangen door fakes."""
    _FakeClient.responses = {}
    monkeypatch.setattr(url_security.httpx, "Client", _FakeClient)
    monkeypatch.setattr(url_security.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    return _FakeClient


def test_fetch_volgt_redirect_en_geeft_content(fake_http: type[_FakeClient]) -> None:
    fake_http.responses = {
        "https://example.com/kort": _FakeResponse(302, {"location": "https://example.com/lang"}),
        "https://example.com/lang": _FakeResponse(
            200, {"content-type": "text/html; charset=utf-8"}, b"<html>recept</html>"
        ),
    }
    result = fetch_url("https://example.com/kort", max_bytes=1024)
    assert result.content == b"<html>recept</html>"
    assert result.content_type == "text/html"
    assert result.final_url == "https://example.com/lang"


def test_redirect_naar_intern_adres_geweigerd(fake_http: type[_FakeClient]) -> None:
    fake_http.responses = {
        "https://example.com/r": _FakeResponse(302, {"location": "http://192.168.1.5/intern"}),
    }
    with pytest.raises(WeekmenuError) as exc_info:
        fetch_url("https://example.com/r", max_bytes=1024)
    assert exc_info.value.code == "invalid_url"


def test_te_grote_response_afgebroken(fake_http: type[_FakeClient]) -> None:
    fake_http.responses = {
        "https://example.com/groot": _FakeResponse(200, {}, b"x" * 10_000),
    }
    with pytest.raises(WeekmenuError) as exc_info:
        fetch_url("https://example.com/groot", max_bytes=4096)
    assert exc_info.value.code == "fetch_failed"


def test_http_fout_geeft_fetch_failed(fake_http: type[_FakeClient]) -> None:
    fake_http.responses = {"https://example.com/dood": _FakeResponse(404)}
    with pytest.raises(WeekmenuError) as exc_info:
        fetch_url("https://example.com/dood", max_bytes=1024)
    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "fetch_failed"


def test_fetch_gebruikt_een_client_voor_de_hele_redirect_keten(
    fake_http: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressietest: één httpx.Client (en dus cookiejar) voor de volledige keten.

    Sommige sites (bv. Roularta-titels als Libelle Lekker) doen een silent-SSO-
    redirect die op een sessiecookie steunt; een nieuwe Client per hop gooit die
    cookie weg en laat de flow eindigen op een loginpagina i.p.v. het artikel.
    """
    instantiations: list[int] = []
    original_init = _FakeClient.__init__

    def counting_init(self, *args, **kwargs):
        instantiations.append(1)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(fake_http, "__init__", counting_init)
    fake_http.responses = {
        "https://example.com/stap1": _FakeResponse(
            302, {"location": "https://example.com/stap2"}
        ),
        "https://example.com/stap2": _FakeResponse(
            302, {"location": "https://example.com/stap3"}
        ),
        "https://example.com/stap3": _FakeResponse(
            200, {"content-type": "text/html"}, b"<html>recept</html>"
        ),
    }
    result = fetch_url("https://example.com/stap1", max_bytes=1024)
    assert result.final_url == "https://example.com/stap3"
    assert len(instantiations) == 1


def test_te_veel_redirects_geweigerd(fake_http: type[_FakeClient]) -> None:
    fake_http.responses = {
        "https://example.com/loop": _FakeResponse(302, {"location": "https://example.com/loop"}),
    }
    with pytest.raises(WeekmenuError) as exc_info:
        fetch_url("https://example.com/loop", max_bytes=1024)
    assert exc_info.value.code == "fetch_failed"
