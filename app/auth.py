"""Authentication, role-based access control and session handling."""

from __future__ import annotations

import time
from typing import Optional

from . import crypto
from .db import Store, now

IDLE_TIMEOUT = 15 * 60          # HIPAA-style automatic logoff
ABSOLUTE_TIMEOUT = 12 * 60 * 60
MAX_FAILED = 5
LOCKOUT_SECONDS = 15 * 60

PERMISSIONS = {
    "clinician": {
        "patient.read", "patient.write", "eval.read", "eval.write", "eval.sign",
        "report.generate", "report.edit", "report.sign", "report.release",
        "auth.manage", "assistant.use", "audit.read.own",
    },
    "supervisor": {
        "patient.read", "patient.write", "eval.read", "eval.write", "eval.sign",
        "report.generate", "report.edit", "report.sign", "report.release",
        "auth.manage", "assistant.use", "audit.read", "admin",
    },
    # Front desk: scheduling and demographics only. No clinical content.
    "staff": {"patient.read.demographics", "patient.write.demographics", "auth.manage"},
    # Compliance auditor: the log, and nothing else.
    "auditor": {"audit.read"},
}

ROLE_LABELS = {
    "clinician": "Clinician (treating psychiatrist)",
    "supervisor": "Supervising psychiatrist / administrator",
    "staff": "Front desk (demographics only)",
    "auditor": "Compliance auditor (audit log only)",
}


def can(user: Optional[dict], permission: str) -> bool:
    if not user:
        return False
    return permission in PERMISSIONS.get(user["role"], set())


def create_user(store: Store, username: str, password: str, display_name: str, role: str,
                credentials: str = "", npi: str = "") -> int:
    if role not in PERMISSIONS:
        raise ValueError("unknown role: " + role)
    cur = store.execute(
        "INSERT INTO users(username,display_name,credentials,npi,role,password_hash,created_at)"
        " VALUES(?,?,?,?,?,?,?)",
        (username.lower().strip(), display_name, credentials, npi, role,
         crypto.hash_password(password), now()),
    )
    return cur.lastrowid


def _row_to_user(row) -> dict:
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"],
            "credentials": row["credentials"], "npi": row["npi"], "role": row["role"]}


def authenticate(store: Store, username: str, password: str, lock_accounts: bool = True):
    """Returns (user, error).  Timing is not the threat model for a local
    single-tenant demo, but lockout and hashed storage are still enforced.

    lock_accounts=False is for the hosted demo, where throttling is applied per
    connection by the caller instead (see api.login)."""
    row = store.one("SELECT * FROM users WHERE username=?", (username.lower().strip(),))
    if row is None:
        crypto.hash_password(password)  # keep the work factor uniform
        return None, "Incorrect username or password."
    if not row["active"]:
        return None, "This account is disabled."
    if lock_accounts and row["locked_until"] > time.time():
        remaining = int((row["locked_until"] - time.time()) / 60) + 1
        return None, f"Account locked after repeated failed sign-ins. Try again in {remaining} minute(s)."
    if not crypto.verify_password(password, row["password_hash"]):
        if not lock_accounts:
            return None, "Incorrect username or password."
        failed = row["failed_logins"] + 1
        locked = time.time() + LOCKOUT_SECONDS if failed >= MAX_FAILED else 0
        store.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?",
                      (failed, locked, row["id"]))
        if locked:
            return None, "Too many failed attempts. The account is locked for 15 minutes."
        return None, f"Incorrect username or password. {MAX_FAILED - failed} attempt(s) remaining."
    store.execute("UPDATE users SET failed_logins=0, locked_until=0 WHERE id=?", (row["id"],))
    return _row_to_user(row), None


def start_session(store: Store, user_id: int) -> str:
    token = crypto.new_token()
    store.execute("INSERT INTO sessions(token_hash,user_id,created_at,last_seen) VALUES(?,?,?,?)",
                  (crypto.token_fingerprint(token), user_id, now(), now()))
    return token


def resolve_session(store: Store, token: str):
    """Returns (user, error). Enforces idle and absolute session limits."""
    if not token:
        return None, None
    row = store.one("SELECT * FROM sessions WHERE token_hash=?", (crypto.token_fingerprint(token),))
    if row is None or row["revoked"]:
        return None, "Your session is no longer valid. Please sign in again."
    age, idle = now() - row["created_at"], now() - row["last_seen"]
    if idle > IDLE_TIMEOUT:
        end_session(store, token)
        return None, "Signed out automatically after 15 minutes of inactivity."
    if age > ABSOLUTE_TIMEOUT:
        end_session(store, token)
        return None, "Session expired. Please sign in again."
    store.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now(), row["token_hash"]))
    user_row = store.one("SELECT * FROM users WHERE id=? AND active=1", (row["user_id"],))
    if user_row is None:
        return None, "This account is no longer active."
    return _row_to_user(user_row), None


def end_session(store: Store, token: str) -> None:
    store.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (crypto.token_fingerprint(token),))
