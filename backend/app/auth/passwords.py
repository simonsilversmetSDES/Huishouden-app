from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# Dummy-hash zodat een login met onbekend e-mailadres evenveel tijd kost als
# een met fout wachtwoord (geen timing-verschil dat accounts verraadt).
_DUMMY_HASH = _hasher.hash("dummy-wachtwoord-voor-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, ValueError):
        return False
