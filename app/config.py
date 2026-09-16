"""Deployment mode.

Local (default): loopback only, plain HTTP, account lockout.

Hosted (--hosted): a public demonstration behind a TLS-terminating proxy such
as Render's. The process binds 0.0.0.0 on $PORT, cookies are marked Secure,
HSTS is sent, the database is erased and reseeded on every start, and sign-in
throttling is keyed on the connection instead of the account -- on a shared
demo, per-account lockout would let any visitor lock every other visitor out.

Modules read `config.HOSTED` at call time, never at import, so tests can flip it.
"""

HOSTED = False


def enable_hosted() -> None:
    global HOSTED
    HOSTED = True


def disable_hosted() -> None:
    global HOSTED
    HOSTED = False
