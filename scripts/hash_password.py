"""Genereer een argon2-wachtwoordhash voor in .env.

Gebruik (vanuit de root van het project):
    backend\\.venv\\Scripts\\python scripts\\hash_password.py     (Windows)
    backend/.venv/bin/python scripts/hash_password.py            (Linux/Mac)
Of via Docker:
    docker compose run --rm backend python /scripts/hash_password.py

Het wachtwoord wordt onzichtbaar getypt en verschijnt nergens in logs.
"""

import getpass
import sys

from argon2 import PasswordHasher


def main() -> None:
    password = getpass.getpass("Wachtwoord: ")
    if len(password) < 8:
        print("Wachtwoord moet minstens 8 tekens lang zijn.", file=sys.stderr)
        sys.exit(1)
    if password != getpass.getpass("Nog eens ter bevestiging: "):
        print("Wachtwoorden komen niet overeen.", file=sys.stderr)
        sys.exit(1)
    print()
    print("Zet deze hash in .env (bv. SIMON_PASSWORD_HASH=...):")
    print(PasswordHasher().hash(password))


if __name__ == "__main__":
    main()
