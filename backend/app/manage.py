"""Server-side maintenance, run inside the backend container by ./senti-server (shell access to the server = trusted).

    python -m app.manage reset-admin EMAIL NEW_PASSWORD   new password, two-factor sign-in set up again, every session ended
"""
from __future__ import annotations

import sys

from .db import Base, SessionLocal, engine, migrate
from .models import Admin, ChangeLog
from .security import hash_password


def reset_admin(email: str, password: str) -> int:
    Base.metadata.create_all(engine)
    migrate(engine)
    with SessionLocal() as db:
        a = db.query(Admin).filter_by(email=email.strip().lower()).first() or db.query(Admin).first()
        if a is None:
            print("no admin account", file=sys.stderr)
            return 1
        a.password_hash = hash_password(password)
        a.token_version = (a.token_version or 0) + 1  # signs out every open session
        a.totp_secret, a.totp_enabled, a.totp_last_step = "", False, 0  # the next sign-in sets up the authenticator again
        db.add(ChangeLog(actor="server console", action="admin.reset", target=a.email))
        db.commit()
        print(a.email)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "reset-admin":
        return reset_admin(argv[1], argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
