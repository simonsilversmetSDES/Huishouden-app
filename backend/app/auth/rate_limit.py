"""In-memory rate limiting voor de login (bescherming tegen brute-force).

Bewust geen externe dependency (slowapi e.d.): die zijn IP-gebaseerd en kennen
geen per-account-sleutels of oplopende backoff zonder omwegen. Deze app draait
als één uvicorn-proces met 2 vaste accounts, dus een teller in het geheugen met
een lock volstaat. Herstart wist de tellers — acceptabel: een aanvaller kan de
app niet herstarten en argon2 houdt elke poging sowieso traag.

Werking: per sleutel (IP én account) telt het aantal opeenvolgende mislukte
pogingen. Vanaf `max_attempts` wordt de sleutel geblokkeerd met een oplopende
wachttijd (base × 2^extra, gecapt). Een geslaagde login wist de teller.

Client-IP achter Cloudflare Tunnel: het socket-IP is altijd de interne proxy
(nginx/cloudflared), waardoor iedereen in één bucket zou vallen. Daarom leest
`client_ip` eerst CF-Connecting-IP (door Cloudflare zelf gezet — de tunnel is
outbound-only, dus de origin is niet rechtstreeks bereikbaar en de header is
niet te spoofen), dan X-Forwarded-For, en pas dan het socket-IP. Zou iemand de
header tóch kunnen roteren, dan vangt de per-account-limiet gerichte
brute-force alsnog af.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Request

# Entries zonder activiteit langer dan dit worden opgeruimd (geheugenbegrenzing).
_PRUNE_AFTER_SECONDS = 6 * 3600


def client_ip(request: Request) -> str:
    """Echte client-IP: Cloudflare-header eerst, dan XFF, dan het socket-IP."""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()  # eerste hop = oorspronkelijke client
    return request.client.host if request.client else "onbekend"


@dataclass
class _Entry:
    fails: int = 0
    blocked_until: float = 0.0
    last_seen: float = 0.0


@dataclass
class LoginRateLimiter:
    """Teller per sleutel met exponentiële backoff; thread-safe via een lock."""

    clock: Callable[[], float] = time.monotonic  # injecteerbaar voor tests
    _entries: dict[str, _Entry] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def retry_after(self, keys: list[str]) -> int | None:
        """Resterende blokkade in seconden (grootste over de sleutels), of None."""
        now = self.clock()
        with self._lock:
            self._prune(now)
            remaining = max(
                (e.blocked_until - now for k in keys if (e := self._entries.get(k))),
                default=0.0,
            )
        # Naar boven afronden: "Retry-After: 0" zou de blokkade meteen opheffen.
        return max(1, int(remaining + 0.999)) if remaining > 0 else None

    def register_failure(
        self,
        keys: list[str],
        max_attempts: int,
        base_block_seconds: int,
        max_block_seconds: int,
    ) -> None:
        """Mislukte poging bijtellen; vanaf `max_attempts` blokkeren met backoff."""
        now = self.clock()
        with self._lock:
            for key in keys:
                entry = self._entries.setdefault(key, _Entry())
                entry.fails += 1
                entry.last_seen = now
                extra = entry.fails - max_attempts
                if extra >= 0:
                    block = min(base_block_seconds * (2**extra), max_block_seconds)
                    entry.blocked_until = now + block

    def reset(self, keys: list[str]) -> None:
        """Geslaagde login: tellers van deze sleutels wissen."""
        with self._lock:
            for key in keys:
                self._entries.pop(key, None)

    def clear(self) -> None:
        """Alles wissen (test-isolatie)."""
        with self._lock:
            self._entries.clear()

    def _prune(self, now: float) -> None:
        """Verlopen, inactieve entries opruimen zodat de dict niet blijft groeien."""
        stale = [
            k
            for k, e in self._entries.items()
            if e.blocked_until < now and now - e.last_seen > _PRUNE_AFTER_SECONDS
        ]
        for key in stale:
            del self._entries[key]


# Eén proces, dus één gedeelde limiter voor de login-route.
login_limiter = LoginRateLimiter()
